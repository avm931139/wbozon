from __future__ import annotations

from datetime import date
from typing import Any

from yandex_market.advertising import YandexMarketAdvertisingAPI
from yandex_market.exceptions import YandexMarketParseError


class YandexMarketFinanceAPI(YandexMarketAdvertisingAPI):
    """Generate the official payment ledger in machine-readable JSON."""

    def generate_payments(self, *, business_id: int, date_from: date, date_to: date) -> str:
        payload = self.client.post(
            "/v2/reports/united-netting/generate",
            params={"format": "JSON", "language": "RU"},
            json_body={
                "businessId": business_id,
                "dateFrom": date_from.isoformat(),
                "dateTo": date_to.isoformat(),
            },
        )
        result: dict[str, Any] = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        report_id = result.get("reportId")
        if not report_id:
            raise YandexMarketParseError("Yandex Market finance report has no reportId")
        return str(report_id)
