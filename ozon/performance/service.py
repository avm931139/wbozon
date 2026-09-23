from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable
from app.db import SessionLocal
from app.models import OzonAdCampaign, OzonAdDailyStat
from app.config import OZON_HISTORY_FROM, OZON_SYNC_OVERLAP_DAYS
from ozon.performance.api import OzonPerformanceAPI
from ozon.business_time import ozon_today

def _money(value: Any) -> Decimal:
    try:
        normalized = str(value or 0).replace("\u00a0", "").replace(" ", "").replace(",", ".")
        return Decimal(normalized)
    except Exception: return Decimal(0)
def _date(value: Any) -> date | None:
    try: return date.fromisoformat(str(value)[:10])
    except ValueError: return None

class OzonPerformanceService:
    def __init__(
        self,
        api: OzonPerformanceAPI | None = None,
        *,
        today: Callable[[], date] = ozon_today,
    ) -> None:
        self.api = api or OzonPerformanceAPI()
        self.today = today
    def sync_campaigns(self) -> list[dict[str, Any]]:
        items = self.api.campaigns(); now = datetime.now(timezone.utc)
        with SessionLocal() as session:
            for item in items:
                cid = int(item["id"]); row = session.query(OzonAdCampaign).filter_by(campaign_id=cid).one_or_none()
                if row is None: row = OzonAdCampaign(campaign_id=cid, raw_data=item, fetched_at=now); session.add(row)
                row.title=item.get("title"); row.state=item.get("state"); row.campaign_type=item.get("advObjectType"); row.payment_type=item.get("PaymentType")
                row.budget=_money(item.get("budget")); row.daily_budget=_money(item.get("dailyBudget")); row.from_date=_date(item.get("fromDate")); row.to_date=_date(item.get("toDate")); row.raw_data=item; row.fetched_at=now
            session.commit()
        return items

    def sync_daily_stats(self) -> int:
        with SessionLocal() as session:
            latest = session.query(OzonAdDailyStat.stat_date).order_by(OzonAdDailyStat.stat_date.desc()).first()
        history_from = date.fromisoformat(OZON_HISTORY_FROM)
        start = max(history_from, latest[0] - timedelta(days=OZON_SYNC_OVERLAP_DAYS)) if latest else history_from
        end = self.today() - timedelta(days=1)
        if start > end: return 0
        rows: list[dict[str, Any]] = []; cursor = start
        while cursor <= end:
            chunk_end = min(end, cursor + timedelta(days=30))
            rows.extend(self.api.daily_statistics(cursor, chunk_end)); cursor = chunk_end + timedelta(days=1)
        now = datetime.now(timezone.utc)
        with SessionLocal() as session:
            for item in rows:
                day = _date(item.get("date")); cid = item.get("id")
                if day is None or cid in (None, ""): continue
                row = session.query(OzonAdDailyStat).filter_by(stat_date=day, campaign_id=int(cid), sku=0).one_or_none()
                if row is None: row = OzonAdDailyStat(stat_date=day,campaign_id=int(cid),sku=0,raw_data=item,fetched_at=now); session.add(row)
                row.views=int(item.get("views") or 0); row.clicks=int(item.get("clicks") or 0); row.orders=int(item.get("orders") or 0)
                row.orders_money=_money(item.get("ordersMoney")); row.spend=_money(item.get("moneySpent")); row.raw_data=item; row.fetched_at=now
            session.commit()
        return len(rows)

    def sync_product_stats(self, *, history_from: date | None = None) -> int:
        history_floor = date.fromisoformat(OZON_HISTORY_FROM)
        end = self.today() - timedelta(days=1)
        with SessionLocal() as session:
            latest = session.query(OzonAdDailyStat.stat_date).filter(
                OzonAdDailyStat.sku != 0
            ).order_by(OzonAdDailyStat.stat_date.desc()).first()
        start = max(history_floor, history_from) if history_from else (
            max(history_floor, latest[0] - timedelta(days=OZON_SYNC_OVERLAP_DAYS))
            if latest else history_floor
        )
        if start > end:
            return 0
        saved = 0
        cursor = start
        while cursor <= end:
            chunk_end = min(end, cursor + timedelta(days=61))
            with SessionLocal() as session:
                campaign_ids = [
                    str(value) for value, in session.query(
                        OzonAdDailyStat.campaign_id
                    ).join(
                        OzonAdCampaign,
                        OzonAdCampaign.campaign_id == OzonAdDailyStat.campaign_id,
                    ).filter(
                        OzonAdCampaign.campaign_type == "SKU",
                        OzonAdDailyStat.sku == 0,
                        OzonAdDailyStat.spend != 0,
                        OzonAdDailyStat.stat_date.between(cursor, chunk_end),
                    ).distinct().order_by(OzonAdDailyStat.campaign_id).all()
                ]
            for offset in range(0, len(campaign_ids), 10):
                batch = campaign_ids[offset:offset + 10]
                rows = self.api.historical_product_statistics(batch, cursor, chunk_end)
                saved += self._replace_product_stats(batch, cursor, chunk_end, rows)
            cursor = chunk_end + timedelta(days=1)
        return saved

    @staticmethod
    def _report_date(value: Any) -> date | None:
        text = str(value or "").strip()
        for pattern in ("%d.%m.%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                pass
        return None

    def _replace_product_stats(
        self,
        campaign_ids: list[str],
        date_from: date,
        date_to: date,
        rows: list[dict[str, Any]],
    ) -> int:
        now = datetime.now(timezone.utc)
        grouped: dict[tuple[date, int, int], dict[str, Any]] = {}
        for item in rows:
            day = self._report_date(item.get("date"))
            campaign_id = item.get("campaignId")
            sku = item.get("sku")
            if day is None or campaign_id in (None, "") or sku in (None, "", "0", 0):
                continue
            key = (day, int(campaign_id), int(sku))
            value = grouped.setdefault(key, {
                "views": 0, "clicks": 0, "orders": 0,
                "orders_money": Decimal("0"), "spend": Decimal("0"), "rows": [],
            })
            value["views"] += int(item.get("views") or 0)
            value["clicks"] += int(item.get("clicks") or 0)
            value["orders"] += int(item.get("orders") or item.get("models") or 0)
            orders_money = _money(item.get("ordersMoney"))
            value["orders_money"] += orders_money or _money(item.get("modelsMoney"))
            value["spend"] += _money(item.get("moneySpent") or item.get("expense"))
            value["rows"].append(item)
        with SessionLocal() as session:
            session.query(OzonAdDailyStat).filter(
                OzonAdDailyStat.campaign_id.in_([int(value) for value in campaign_ids]),
                OzonAdDailyStat.sku != 0,
                OzonAdDailyStat.stat_date.between(date_from, date_to),
            ).delete(synchronize_session=False)
            for (day, campaign_id, sku), item in grouped.items():
                session.add(OzonAdDailyStat(
                    stat_date=day,
                    campaign_id=campaign_id,
                    sku=sku,
                    views=item["views"],
                    clicks=item["clicks"],
                    orders=item["orders"],
                    orders_money=item["orders_money"],
                    spend=item["spend"],
                    raw_data={"rows": item["rows"]},
                    fetched_at=now,
                ))
            session.commit()
        return len(grouped)

    def sync_all(self) -> dict[str, int]:
        campaigns = len(self.sync_campaigns())
        daily_stats = self.sync_daily_stats()
        return {
            "campaigns": campaigns,
            "daily_stats": daily_stats,
            "product_stats": self.sync_product_stats(),
        }

    @staticmethod
    def summary(date_from: date, date_to: date) -> dict[str, Any]:
        with SessionLocal() as session: rows=session.query(OzonAdDailyStat).filter(OzonAdDailyStat.stat_date.between(date_from,date_to)).all()
        spend=sum((x.spend for x in rows),Decimal(0)); revenue=sum((x.orders_money for x in rows),Decimal(0)); orders=sum(x.orders for x in rows)
        return {"spend":str(spend),"orders":orders,"attributed_revenue":str(revenue),"drr_percent":str(spend/revenue*100) if revenue else None,"roas":str(revenue/spend) if spend else None,"cpo":str(spend/orders) if orders else None}
