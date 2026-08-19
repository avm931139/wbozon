from __future__ import annotations
from datetime import date
from typing import Any
from ozon.performance.client import OzonPerformanceClient


class OzonPerformanceAPI:
    def __init__(self, client: OzonPerformanceClient | None = None) -> None: self.client = client or OzonPerformanceClient()
    def campaigns(self) -> list[dict[str, Any]]:
        payload = self.client.request("GET", "/api/client/campaign")
        return [x for x in payload.get("list", []) if isinstance(x, dict)] if isinstance(payload, dict) else []
    def statistics(self, campaign_ids: list[str], date_from: date, date_to: date) -> Any:
        return self.client.request("POST", "/api/client/statistics/json", json_body={"campaigns": campaign_ids, "dateFrom": date_from.isoformat(), "dateTo": date_to.isoformat()})
    def daily_statistics(self, date_from: date, date_to: date) -> list[dict[str, Any]]:
        payload = self.client.request("GET", "/api/client/statistics/daily/json", params={"dateFrom": date_from.isoformat(), "dateTo": date_to.isoformat()})
        return [x for x in payload.get("rows", []) if isinstance(x, dict)] if isinstance(payload, dict) else []
