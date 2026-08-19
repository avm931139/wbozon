from __future__ import annotations

from datetime import date
from typing import Any

from ozon.client import OzonClient


class OzonAnalyticsAPI:
    PATH = "/v1/analytics/data"

    def __init__(self, client: OzonClient | None = None) -> None:
        self.client = client or OzonClient()

    def daily_sales(self, date_from: date, date_to: date, limit: int = 1000) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            payload = self.client.post(self.PATH, json_body={
                "date_from": date_from.isoformat(), "date_to": date_to.isoformat(),
                "metrics": ["revenue", "ordered_units", "delivered_units", "returns", "cancellations"],
                "dimension": ["day", "sku"], "limit": limit, "offset": offset,
            })
            result = payload.get("result", {}) if isinstance(payload, dict) else {}
            page = result.get("data", []) if isinstance(result, dict) else []
            for value in page:
                if isinstance(value, dict):
                    value["metric_names"] = ["revenue", "ordered_units", "delivered_units", "returns", "cancellations"]
                    rows.append(value)
            if len(page) < limit:
                return rows
            offset += len(page)
