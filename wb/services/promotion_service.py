from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import func

from app.db import SessionLocal
from app.models import WBAdvertCampaign, WBAdvertDailyStat, WBAdvertProductDailyStat
from wb.promotion import PromotionAPI
from wb.repositories.promotion_repository import PromotionRepository

logger = logging.getLogger(__name__)


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _expense_identity(item: dict[str, Any]) -> str:
    # Names and statuses may change after an operation. They must not change its identity.
    identity = {
        key: item.get(key)
        for key in ("updNum", "advertId", "updTime", "updSum", "paymentType")
    }
    return json.dumps(identity, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _expense_hash(item: dict[str, Any]) -> str:
    return hashlib.sha256(_expense_identity(item).encode()).hexdigest()


def _date_chunks(date_from: date, date_to: date, days: int = 31):
    if date_from > date_to:
        raise ValueError("date_from must not be later than date_to")
    cursor = date_from
    while cursor <= date_to:
        end = min(cursor + timedelta(days=days - 1), date_to)
        yield cursor, end
        cursor = end + timedelta(days=1)


class PromotionService:
    def __init__(
        self,
        api: PromotionAPI | None = None,
        session_factory: Callable[..., Any] = SessionLocal,
        request_delay: float = 0.5,
    ):
        self.api = api or PromotionAPI()
        self.session_factory = session_factory
        self.request_delay = request_delay

    def sync_campaigns(self) -> int:
        items = self.api.campaigns()
        with self.session_factory() as session:
            repository = PromotionRepository(session)
            campaigns = repository.campaigns_by_wb_id()
            for item in items:
                advert_id = int(item["advertId"])
                row = repository.get_or_create_campaign(advert_id, campaigns)
                row.advert_type = item.get("type")
                row.status = item.get("status")
                row.change_time = _dt(item.get("changeTime"))
                row.raw_data = item
            session.commit()
        return len(items)

    def sync_campaign_details(self, advert_ids: list[int] | None = None) -> int:
        if advert_ids is None:
            with self.session_factory() as session:
                advert_ids = PromotionRepository(session).campaign_ids()
        received = 0
        for offset in range(0, len(advert_ids), 50):
            items = self.api.campaign_details(advert_ids[offset : offset + 50])
            with self.session_factory() as session:
                repository = PromotionRepository(session)
                campaigns = repository.campaigns_by_wb_id()
                for item in items:
                    advert_id = int(item.get("id") or item.get("advertId") or 0)
                    if not advert_id:
                        continue
                    settings = item.get("settings") or {}
                    timestamps = item.get("timestamps") or {}
                    row = repository.get_or_create_campaign(advert_id, campaigns)
                    row.name = settings.get("name") or item.get("name") or row.name
                    row.status = item.get("status", row.status)
                    row.change_time = _dt(timestamps.get("updated") or item.get("changeTime")) or row.change_time
                    row.raw_data = item
                    received += 1
                session.commit()
        return received

    def sync_account_balance(self) -> dict[str, Any]:
        item = self.api.balance()
        with self.session_factory() as session:
            PromotionRepository(session).add_account_snapshot(
                balance=_decimal(item.get("balance")),
                net=_decimal(item.get("net")),
                bonus=_decimal(item.get("bonus")),
                cashbacks=item.get("cashbacks") or [],
                raw_data=item,
            )
            session.commit()
        return item

    def sync_campaign_budgets(self, advert_ids: list[int] | None = None) -> int:
        if advert_ids is None:
            with self.session_factory() as session:
                advert_ids = PromotionRepository(session).campaign_ids()
        updated = 0
        for position, advert_id in enumerate(advert_ids):
            if position:
                time.sleep(0.25)
            item = self.api.campaign_budget(advert_id)
            with self.session_factory() as session:
                repository = PromotionRepository(session)
                campaign = repository.get_or_create_campaign(advert_id, repository.campaigns_by_wb_id())
                campaign.budget_cash = _decimal(item.get("cash"))
                campaign.budget_netting = _decimal(item.get("netting"))
                campaign.budget_total = _decimal(item.get("total"))
                campaign.budget_fetched_at = datetime.utcnow()
                session.commit()
            updated += 1
        return updated

    def sync_payments(self, date_from: date, date_to: date) -> int:
        items = self.api.payments(date_from, date_to)
        inserted = 0
        with self.session_factory() as session:
            repository = PromotionRepository(session)
            existing = repository.existing_payment_hashes()
            for item in items:
                source_hash = hashlib.sha256(
                    json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
                ).hexdigest()
                if source_hash in existing:
                    continue
                repository.add_payment(
                    source_hash=source_hash,
                    payment_time=_dt(item.get("date") or item.get("paymentDate") or item.get("updTime")),
                    amount=_decimal(item.get("sum") or item.get("amount") or item.get("updSum")),
                    payment_type=item.get("type") or item.get("paymentType"),
                    raw_data=item,
                )
                existing.add(source_hash)
                inserted += 1
            session.commit()
        return inserted

    def sync_expenses(self, date_from: date, date_to: date) -> int:
        items = self.api.expenses(date_from, date_to)
        inserted = 0
        with self.session_factory() as session:
            repository = PromotionRepository(session)
            campaigns = repository.campaigns_by_wb_id()
            existing_expenses = repository.existing_expenses()
            existing_hashes = {source_hash for source_hash, _ in existing_expenses}
            existing_identities = {_expense_identity(raw_data) for _, raw_data in existing_expenses}
            for item in items:
                upd_num = int(item["updNum"]) if item.get("updNum") is not None else None
                identity = _expense_identity(item)
                source_hash = _expense_hash(item)
                if identity in existing_identities or source_hash in existing_hashes:
                    continue
                advert_id = int(item.get("advertId") or 0)
                campaign = None
                if advert_id:
                    campaign = repository.get_or_create_campaign(
                        advert_id,
                        campaigns,
                        name=item.get("campName"),
                        advert_type=item.get("advertType"),
                        status=item.get("advertStatus"),
                    )
                repository.add_expense(
                    campaign=campaign,
                    upd_num=upd_num,
                    source_hash=source_hash,
                    expense_time=_dt(item.get("updTime")),
                    amount=_decimal(item.get("updSum")),
                    currency=item.get("currency") or "RUB",
                    payment_type=item.get("paymentType"),
                    advert_type=item.get("advertType"),
                    advert_status=item.get("advertStatus"),
                    campaign_name=item.get("campName"),
                    raw_data=item,
                )
                existing_identities.add(identity)
                existing_hashes.add(source_hash)
                inserted += 1
            session.commit()
        return inserted

    def sync_stats(self, advert_ids: list[int], date_from: date, date_to: date) -> int:
        items = self.api.full_stats(advert_ids, date_from, date_to)
        count = 0
        with self.session_factory() as session:
            repository = PromotionRepository(session)
            campaigns = repository.campaigns_by_wb_id()
            products = repository.product_ids_by_nm_id()
            for campaign_data in items:
                advert_id = int(campaign_data["advertId"])
                campaign = repository.get_or_create_campaign(advert_id, campaigns)
                for day in campaign_data.get("days") or []:
                    stat_date = _dt(day.get("date"))
                    if stat_date is None:
                        continue
                    row = repository.get_or_create_daily_stat(campaign, stat_date)
                    self._metrics(row, day)
                    row.raw_data = day
                    row.fetched_at = datetime.utcnow()
                    existing = repository.product_stats_by_key(row.id)
                    received: set[tuple[int, int]] = set()
                    for app in day.get("apps") or []:
                        app_type = int(app.get("appType") or 0)
                        for nm in app.get("nms") or []:
                            nm_id = int(nm.get("nmId") or 0)
                            key = (app_type, nm_id)
                            received.add(key)
                            product_row = existing.get(key)
                            if product_row is None:
                                product_row = WBAdvertProductDailyStat(
                                    daily_stat=row, nm_id=nm_id, app_type=app_type, raw_data={}
                                )
                                session.add(product_row)
                            product_row.product_id = products.get(nm_id)
                            product_row.product_name = nm.get("name")
                            product_row.raw_data = nm
                            self._metrics(product_row, nm)
                    repository.remove_product_stats([value for key, value in existing.items() if key not in received])
                    count += 1
            session.commit()
        return count

    def sync_all(self, date_from: date, date_to: date) -> dict[str, int]:
        """Synchronize any period, respecting WB limits for dates and campaign IDs."""
        result = {
            "campaigns_received": self.sync_campaigns(),
            "campaign_details_received": 0,
            "campaign_budgets_updated": 0,
            "payments_inserted": 0,
            "expenses_inserted": 0,
            "daily_stats_upserted": 0,
        }
        with self.session_factory() as session:
            advert_ids = PromotionRepository(session).campaign_ids()
        result["campaign_details_received"] = self.sync_campaign_details(advert_ids)
        self.sync_account_balance()
        with self.session_factory() as session:
            budget_ids = PromotionRepository(session).campaign_ids(statuses=(4, 9, 11))
        result["campaign_budgets_updated"] = self.sync_campaign_budgets(budget_ids)
        requests_made = 0
        for chunk_from, chunk_to in _date_chunks(date_from, date_to):
            result["payments_inserted"] += self.sync_payments(chunk_from, chunk_to)
            result["expenses_inserted"] += self.sync_expenses(chunk_from, chunk_to)
            requests_made += 1
            for offset in range(0, len(advert_ids), 50):
                if requests_made and self.request_delay:
                    time.sleep(self.request_delay)
                result["daily_stats_upserted"] += self.sync_stats(
                    advert_ids[offset : offset + 50], chunk_from, chunk_to
                )
                requests_made += 1
        logger.info("WB Promotion synchronization completed: %s", result)
        return result

    @staticmethod
    def _metrics(row: Any, item: dict[str, Any]) -> None:
        for field in ("views", "clicks", "atbs", "orders", "canceled", "shks"):
            setattr(row, field, int(item.get(field) or 0))
        row.spend = _decimal(item.get("sum"))
        row.order_sum = _decimal(item.get("sum_price"))
        row.ctr = _decimal(item.get("ctr"))
        row.cpc = _decimal(item.get("cpc"))
        row.cr = _decimal(item.get("cr"))

    def efficiency_summary(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
        advert_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        with self.session_factory() as session:
            query = session.query(
                func.coalesce(func.sum(WBAdvertDailyStat.spend), 0),
                func.coalesce(func.sum(WBAdvertDailyStat.order_sum), 0),
                func.coalesce(func.sum(WBAdvertDailyStat.orders), 0),
            ).join(WBAdvertCampaign)
            if date_from is not None:
                query = query.filter(WBAdvertDailyStat.stat_date >= date_from)
            if date_to is not None:
                query = query.filter(WBAdvertDailyStat.stat_date < date_to + timedelta(days=1))
            if advert_ids:
                query = query.filter(WBAdvertCampaign.advert_wb_id.in_(advert_ids))
            spend, revenue, orders = query.one()
        spend, revenue, orders = Decimal(spend), Decimal(revenue), int(orders)
        return {
            "spend": str(spend),
            "attributed_revenue": str(revenue),
            "orders": orders,
            "roas": round(float(revenue / spend), 4) if spend else None,
            "drr_percent": round(float(spend / revenue * 100), 2) if revenue else None,
            "cpo": round(float(spend / orders), 2) if orders else None,
        }
