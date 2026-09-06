from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app.config import (
    YANDEX_MARKET_AD_POLL_ATTEMPTS,
    YANDEX_MARKET_AD_POLL_SECONDS,
    YANDEX_MARKET_BUSINESS_ID,
    YANDEX_MARKET_TIMEZONE,
)
from app.db import SessionLocal
from app.models import YandexMarketAdDailyStat
from yandex_market.advertising import YandexMarketAdvertisingAPI


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


class YandexMarketAdvertisingService:
    SOURCES = ("sales_boost", "shows_boost", "banners")

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
        if not self.business_id:
            raise ValueError("YANDEX_MARKET_BUSINESS_ID must be configured for advertising")
        stat_date = stat_date or datetime.now(ZoneInfo(YANDEX_MARKET_TIMEZONE)).date()
        results: dict[str, Any] = {}
        errors: list[str] = []
        for source in self.SOURCES:
            try:
                report_id = self.api.generate(
                    source, business_id=self.business_id, stat_date=stat_date
                )
                report = self.api.wait(
                    report_id,
                    attempts=YANDEX_MARKET_AD_POLL_ATTEMPTS,
                    pause_seconds=YANDEX_MARKET_AD_POLL_SECONDS,
                )
                rows = self._select_rows(source, report["rows"])
                saved = self._replace(source, stat_date, rows)
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

    @staticmethod
    def _select_rows(
        source: str, files: list[tuple[str, list[dict[str, Any]]]]
    ) -> list[dict[str, Any]]:
        expected = {
            "sales_boost": "business_boost_consolidated",
            "shows_boost": "business_shows_boost_consolidated_campaigns",
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

    def _replace(self, source: str, stat_date: date, rows: list[dict[str, Any]]) -> int:
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
                    business_id=self.business_id,
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
