from __future__ import annotations
from datetime import date
import time
from typing import Any
from ozon.performance.client import OzonPerformanceClient


class OzonPerformanceAPI:
    def __init__(self, client: OzonPerformanceClient | None = None) -> None: self.client = client or OzonPerformanceClient()
    def campaigns(self) -> list[dict[str, Any]]:
        payload = self.client.request("GET", "/api/client/campaign")
        return [x for x in payload.get("list", []) if isinstance(x, dict)] if isinstance(payload, dict) else []
    def statistics(self, campaign_ids: list[str], date_from: date, date_to: date) -> Any:
        return self.client.request("POST", "/api/client/statistics/json", json_body={
            "campaigns": campaign_ids,
            "dateFrom": date_from.isoformat(),
            "dateTo": date_to.isoformat(),
            "groupBy": "DATE",
        })
    def daily_statistics(self, date_from: date, date_to: date) -> list[dict[str, Any]]:
        payload = self.client.request("GET", "/api/client/statistics/daily/json", params={"dateFrom": date_from.isoformat(), "dateTo": date_to.isoformat()})
        return [x for x in payload.get("rows", []) if isinstance(x, dict)] if isinstance(payload, dict) else []

    def historical_product_statistics(
        self,
        campaign_ids: list[str],
        date_from: date,
        date_to: date,
        *,
        poll_attempts: int = 60,
        poll_seconds: float = 2.0,
    ) -> list[dict[str, Any]]:
        if not campaign_ids or len(campaign_ids) > 10:
            raise ValueError("Ozon statistics report requires 1 to 10 campaigns")
        if (date_to - date_from).days > 61:
            raise ValueError("Ozon statistics report period cannot exceed 62 days")
        payload = self.statistics(campaign_ids, date_from, date_to)
        report_id = payload.get("UUID") if isinstance(payload, dict) else None
        if not report_id:
            raise ValueError("Ozon Performance API did not return report UUID")
        status: dict[str, Any] = {}
        for attempt in range(poll_attempts):
            value = self.client.request("GET", f"/api/client/statistics/{report_id}")
            status = value if isinstance(value, dict) else {}
            state = status.get("state")
            if state == "OK":
                break
            if state == "ERROR":
                raise RuntimeError(f"Ozon advertising report failed: {status}")
            if attempt + 1 < poll_attempts:
                time.sleep(poll_seconds)
        else:
            raise TimeoutError(f"Ozon advertising report {report_id} was not ready")
        link = status.get("link")
        if not link:
            raise ValueError("Ozon advertising report has no download link")
        report = self.client.request("GET", link)
        rows: list[dict[str, Any]] = []
        for campaign_id, value in (report.items() if isinstance(report, dict) else []):
            report_rows = (value.get("report") or {}).get("rows") if isinstance(value, dict) else []
            for row in report_rows or []:
                if isinstance(row, dict):
                    rows.append({**row, "campaignId": campaign_id, "reportUUID": report_id})
        return rows
