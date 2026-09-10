from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import distinct, func

from app.config import (
    YANDEX_MARKET_AD_POLL_ATTEMPTS,
    YANDEX_MARKET_AD_POLL_SECONDS,
    YANDEX_MARKET_AD_HISTORY_DAYS,
    YANDEX_MARKET_AD_REFRESH_DAYS,
    YANDEX_MARKET_BUSINESS_ID,
    YANDEX_MARKET_HISTORY_FROM,
    YANDEX_MARKET_TIMEZONE,
)
from app.db import SessionLocal
from app.models import YandexMarketAdDailyStat, YandexMarketBusiness
from yandex_market.advertising import YandexMarketAdvertisingAPI


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


class YandexMarketAdvertisingService:
    SOURCES = ("sales_boost", "shows_boost", "shelves", "banners")

    def __init__(
        self,
        api: YandexMarketAdvertisingAPI | None = None,
        *,
        session_factory: Callable[..., Any] = SessionLocal,
        business_id: int | None = YANDEX_MARKET_BUSINESS_ID,
    ) -> None:
        self.api = api or YandexMarketAdvertisingAPI()
        self.session_factory = session_factory
        self.business_id = business_id

    def sync(self, *, stat_date: date | None = None) -> dict[str, Any]:
        business_id = self._business_id()
        today = datetime.now(ZoneInfo(YANDEX_MARKET_TIMEZONE)).date()
        stat_date = stat_date or self._target_date(today)
        results: dict[str, Any] = {}
        errors: list[str] = []
        sources = self._sources_for_date(stat_date)
        for source in sources:
            try:
                report_id = self.api.generate(
                    source, business_id=business_id, stat_date=stat_date
                )
                report = self.api.wait(
                    report_id,
                    attempts=YANDEX_MARKET_AD_POLL_ATTEMPTS,
                    pause_seconds=YANDEX_MARKET_AD_POLL_SECONDS,
                )
                rows = self._select_rows(source, report["rows"])
                saved = self._replace(source, stat_date, rows, business_id=business_id)
                results[source] = {
                    "status": str(report["status"]).lower(),
                    "report_id": report_id,
                    "rows": len(rows),
                    "saved": saved,
                }
            except Exception as exc:
                message = f"{source}: {type(exc).__name__}: {exc}"
                results[source] = {"status": "failed", "error": message}
                errors.append(message)
        if errors:
            raise RuntimeError("; ".join(errors))
        return {"date": stat_date.isoformat(), "sources": results}

    def _sources_for_date(self, stat_date: date) -> tuple[str, ...]:
        """Backfill only missing reports; refresh all sources on a complete day."""
        with self.session_factory() as session:
            present = {
                source for source, in session.query(
                    distinct(YandexMarketAdDailyStat.source)
                ).filter(YandexMarketAdDailyStat.stat_date == stat_date).all()
            }
        missing = tuple(source for source in self.SOURCES if source not in present)
        return missing or self.SOURCES

    def _target_date(self, today: date) -> date:
        """Backfill one day per run, then continuously refresh recent attribution."""
        if YANDEX_MARKET_AD_HISTORY_DAYS < 1:
            raise ValueError("YANDEX_MARKET_AD_HISTORY_DAYS must be positive")
        if YANDEX_MARKET_AD_REFRESH_DAYS < 1:
            raise ValueError("YANDEX_MARKET_AD_REFRESH_DAYS must be positive")
        history_from = max(
            date.fromisoformat(YANDEX_MARKET_HISTORY_FROM),
            today - timedelta(days=YANDEX_MARKET_AD_HISTORY_DAYS - 1),
        )
        with self.session_factory() as session:
            complete = {
                day
                for day, count in (
                    session.query(
                        YandexMarketAdDailyStat.stat_date,
                        func.count(distinct(YandexMarketAdDailyStat.source)),
                    )
                    .filter(YandexMarketAdDailyStat.stat_date.between(history_from, today))
                    .group_by(YandexMarketAdDailyStat.stat_date)
                    .all()
                )
                if count == len(self.SOURCES)
            }
            # Newest-first makes the operational dashboard useful while older
            # history is being filled in the background.
            cursor = today
            while cursor >= history_from:
                if cursor not in complete:
                    return cursor
                cursor -= timedelta(days=1)
            refresh_from = max(
                history_from, today - timedelta(days=YANDEX_MARKET_AD_REFRESH_DAYS - 1)
            )
            oldest = (
                session.query(
                    YandexMarketAdDailyStat.stat_date,
                    func.min(YandexMarketAdDailyStat.fetched_at),
                )
                .filter(YandexMarketAdDailyStat.stat_date.between(refresh_from, today))
                .group_by(YandexMarketAdDailyStat.stat_date)
                .order_by(func.min(YandexMarketAdDailyStat.fetched_at))
                .first()
            )
        return oldest[0] if oldest else today

    def _business_id(self) -> int:
        if self.business_id:
            return self.business_id
        with self.session_factory() as session:
            values = [value for value, in session.query(YandexMarketBusiness.business_id).all()]
        if len(values) == 1:
            return int(values[0])
        if not values:
            raise ValueError(
                "Yandex Market business is unknown; run the identity task or configure "
                "YANDEX_MARKET_BUSINESS_ID"
            )
        raise ValueError(
            "multiple Yandex Market businesses found; configure YANDEX_MARKET_BUSINESS_ID"
        )

    @staticmethod
    def _select_rows(
        source: str, files: list[tuple[str, list[dict[str, Any]]]]
    ) -> list[dict[str, Any]]:
        expected = {
            "sales_boost": "business_boost_consolidated",
            "shows_boost": "business_shows_boost_consolidated_campaigns",
            "shelves": "shelfs_statistics_summary",
            "banners": "banners_statistics_report_consolidated",
        }[source]
        for filename, rows in files:
            stem = PurePosixPath(filename).stem.lower()
            if stem == expected:
                return rows
        # Yandex may append a period or report id to the documented file name.
        for filename, rows in files:
            if expected in PurePosixPath(filename).stem.lower():
                return rows
        raise ValueError(f"Yandex Market {source} report has no {expected} sheet")

    def _replace(
        self,
        source: str,
        stat_date: date,
        rows: list[dict[str, Any]],
        *,
        business_id: int | None = None,
    ) -> int:
        business_id = business_id or self._business_id()
        grouped: dict[int, dict[str, Any]] = defaultdict(lambda: {
            "campaign_name": None,
            "views": 0,
            "clicks": 0,
            "orders": 0,
            "spend": Decimal("0"),
            "attributed_revenue": Decimal("0"),
            "rows": [],
        })
        for row in rows:
            campaign_id = 0 if source == "sales_boost" else int(
                row.get("saleCampaignId") or row.get("campaignId") or 0
            )
            item = grouped[campaign_id]
            item["campaign_name"] = (
                row.get("saleCampaignName") or row.get("campaignName") or item["campaign_name"]
            )
            if source == "sales_boost":
                item["views"] += int(row.get("showsWithFee") or 0)
                item["clicks"] += int(row.get("clicksVendorWithFee") or 0)
                item["orders"] += int(row.get("orderItemsDeliveredWithFee") or 0)
                item["spend"] += _decimal(row.get("billedAmount"))
                item["attributed_revenue"] += _decimal(row.get("ordersGvmDeliveredWithFee"))
            else:
                item["views"] += int(row.get("shows") or 0)
                item["clicks"] += int(row.get("clicks") or 0)
                item["orders"] += int(row.get("orderedCount") or 0)
                item["spend"] += _decimal(
                    row.get("realCost") if row.get("realCost") is not None else row.get("cost")
                )
                item["attributed_revenue"] += _decimal(row.get("orderedAmount"))
            item["rows"].append(row)
        if not grouped:
            grouped[0]

        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            session.query(YandexMarketAdDailyStat).filter_by(
                stat_date=stat_date, source=source
            ).delete(synchronize_session=False)
            for campaign_id, item in grouped.items():
                session.add(YandexMarketAdDailyStat(
                    stat_date=stat_date,
                    source=source,
                    business_id=business_id,
                    campaign_id=campaign_id,
                    campaign_name=item["campaign_name"],
                    views=item["views"],
                    clicks=item["clicks"],
                    orders=item["orders"],
                    spend=item["spend"],
                    attributed_revenue=item["attributed_revenue"],
                    raw_data={"rows": item["rows"]},
                    fetched_at=now,
                ))
            session.commit()
        return len(grouped)
