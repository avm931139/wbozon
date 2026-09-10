from __future__ import annotations

from datetime import date
from typing import Any

from yandex_market.advertising import YandexMarketAdvertisingAPI
from yandex_market.exceptions import YandexMarketParseError


class YandexMarketSalesAnalyticsAPI(YandexMarketAdvertisingAPI):
    """Generate the official cabinet "Sales analytics" JSON report."""

    def generate_sales_analytics(
        self, *, business_id: int, date_from: date, date_to: date
    ) -> str:
        if date_from > date_to:
            raise ValueError("date_from must not be later than date_to")
        payload = self.client.post(
            "/v2/reports/shows-sales/generate",
            params={"format": "JSON"},
            json_body={
                "businessId": business_id,
                "dateFrom": date_from.isoformat(),
                "dateTo": date_to.isoformat(),
                "grouping": "OFFERS",
            },
        )
        result: dict[str, Any] = (
            payload.get("result") if isinstance(payload.get("result"), dict) else {}
        )
        report_id = result.get("reportId")
        if not report_id:
            raise YandexMarketParseError(
                "Yandex Market sales analytics report has no reportId"
            )
        return str(report_id)
