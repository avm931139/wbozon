from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app.config import (
    YANDEX_MARKET_AD_POLL_ATTEMPTS,
    YANDEX_MARKET_AD_POLL_SECONDS,
    YANDEX_MARKET_ANALYTICS_HISTORY_DAYS,
    YANDEX_MARKET_BUSINESS_ID,
    YANDEX_MARKET_HISTORY_FROM,
    YANDEX_MARKET_TIMEZONE,
)
from app.db import SessionLocal
from app.models import YandexMarketBusiness, YandexMarketSalesAnalyticsDaily
from yandex_market.exceptions import YandexMarketParseError
from yandex_market.sales_analytics import YandexMarketSalesAnalyticsAPI


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


def _integer(value: Any) -> int:
    try:
        return int(Decimal(str(value or 0)))
    except (InvalidOperation, TypeError, ValueError):
        return 0


def _stat_date(row: dict[str, Any]) -> date | None:
    value = row.get("day")
    if value:
        text = str(value).strip()
        for pattern in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(text[:10], pattern).date()
            except ValueError:
                continue
    month = row.get("month")
    year = row.get("year")
    if month and year:
        try:
            return date(int(year), int(month), 1)
        except (TypeError, ValueError):
            pass
    return None


class YandexMarketSalesAnalyticsService:
    def __init__(
        self,
        api: YandexMarketSalesAnalyticsAPI | None = None,
        *,
        session_factory: Callable[..., Any] = SessionLocal,
        business_id: int | None = YANDEX_MARKET_BUSINESS_ID,
        history_days: int = YANDEX_MARKET_ANALYTICS_HISTORY_DAYS,
    ) -> None:
        if history_days < 1:
            raise ValueError("YANDEX_MARKET_ANALYTICS_HISTORY_DAYS must be positive")
        self.api = api or YandexMarketSalesAnalyticsAPI()
        self.session_factory = session_factory
        self.business_id = business_id
        self.history_days = history_days

    def sync(self) -> dict[str, Any]:
        business_id = self._business_id()
        finish = datetime.now(ZoneInfo(YANDEX_MARKET_TIMEZONE)).date()
        begin = max(
            date.fromisoformat(YANDEX_MARKET_HISTORY_FROM),
            finish - timedelta(days=self.history_days - 1),
        )
        report_id = self.api.generate_sales_analytics(
            business_id=business_id, date_from=begin, date_to=finish
        )
        report = self.api.wait(
            report_id,
            attempts=YANDEX_MARKET_AD_POLL_ATTEMPTS,
            pause_seconds=YANDEX_MARKET_AD_POLL_SECONDS,
        )
        rows = [row for _, file_rows in report["rows"] for row in file_rows]
        saved = self._replace(rows, business_id, begin, finish)
        return {
            "date_from": begin.isoformat(),
            "date_to": finish.isoformat(),
            "report_id": report_id,
            "rows_received": len(rows),
            "rows_saved": saved,
        }

    def _business_id(self) -> int:
        if self.business_id:
            return self.business_id
        with self.session_factory() as session:
            values = [
                value
                for value, in session.query(YandexMarketBusiness.business_id).all()
            ]
        if len(values) != 1:
            raise ValueError(
                "configure YANDEX_MARKET_BUSINESS_ID or synchronize one business"
            )
        return int(values[0])

    def _replace(
        self,
        rows: list[dict[str, Any]],
        business_id: int,
        begin: date,
        finish: date,
    ) -> int:
        aggregates: dict[tuple[date, str], dict[str, Any]] = {}
        for source in rows:
            day = _stat_date(source)
            offer_id = str(source.get("offerId") or "").strip()
            if day is None or not offer_id or not begin <= day <= finish:
                continue
            key = (day, offer_id)
            target = aggregates.setdefault(key, {
                "offer_name": source.get("offerName"),
                "category_name": source.get("categoryName"),
                "brand_name": source.get("brandName"),
                "shows": 0,
                "clicks": 0,
                "to_cart": 0,
                "order_items": 0,
                "order_items_amount": Decimal(0),
                "delivered_items": 0,
                "delivered_amount": Decimal(0),
                "delivered_from_ordered_items": 0,
                "delivered_from_ordered_amount": Decimal(0),
                "cancelled_items": 0,
                "returned_items": 0,
                "raw_rows": [],
            })
            target["shows"] += _integer(source.get("shows"))
            target["clicks"] += _integer(source.get("clicks"))
            target["to_cart"] += _integer(source.get("toCart"))
            target["order_items"] += _integer(source.get("orderItems"))
            target["order_items_amount"] += _decimal(source.get("orderItemsTotalAmount"))
            target["delivered_items"] += _integer(source.get("orderItemsDeliveredCount"))
            target["delivered_amount"] += _decimal(source.get("orderItemsDeliveredTotalAmount"))
            target["delivered_from_ordered_items"] += _integer(
                source.get("orderItemsDeliveredFromOrderedCount")
            )
            target["delivered_from_ordered_amount"] += _decimal(
                source.get("orderItemsDeliveredFromOrderedTotalAmount")
            )
            target["cancelled_items"] += _integer(
                source.get("orderItemsCanceledByCreatedAtCount")
            )
            target["returned_items"] += _integer(
                source.get("orderItemsReturnedByCreatedAtCount")
            )
            target["raw_rows"].append(source)

        if rows and not aggregates:
            signatures = sorted({
                ",".join(sorted(str(key) for key in row))
                for row in rows[:20]
                if isinstance(row, dict)
            })
            raise YandexMarketParseError(
                "Yandex Market sales analytics report has no daily offer rows; "
                f"row keys: {' | '.join(signatures[:3]) or 'none'}"
            )
        fetched_at = datetime.now(timezone.utc)
        with self.session_factory() as session:
            session.query(YandexMarketSalesAnalyticsDaily).filter(
                YandexMarketSalesAnalyticsDaily.business_id == business_id,
                YandexMarketSalesAnalyticsDaily.stat_date.between(begin, finish),
            ).delete(synchronize_session=False)
            for (day, offer_id), values in aggregates.items():
                session.add(YandexMarketSalesAnalyticsDaily(
                    business_id=business_id,
                    stat_date=day,
                    offer_id=offer_id,
                    offer_name=values["offer_name"],
                    category_name=values["category_name"],
                    brand_name=values["brand_name"],
                    shows=values["shows"],
                    clicks=values["clicks"],
                    to_cart=values["to_cart"],
                    order_items=values["order_items"],
                    order_items_amount=values["order_items_amount"],
                    delivered_items=values["delivered_items"],
                    delivered_amount=values["delivered_amount"],
                    delivered_from_ordered_items=values["delivered_from_ordered_items"],
                    delivered_from_ordered_amount=values["delivered_from_ordered_amount"],
                    cancelled_items=values["cancelled_items"],
                    returned_items=values["returned_items"],
                    raw_data={"rows": values["raw_rows"]},
                    fetched_at=fetched_at,
                ))
            session.commit()
        return len(aggregates)
