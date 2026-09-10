from __future__ import annotations

import time
from datetime import date
from typing import Any, Callable, Iterable

from app.config import WB_ANALYTICS_BASE_URL, WB_SALES_FUNNEL_REQUEST_INTERVAL_SECONDS
from wb.client import WBClient
from wb.exceptions import WBParseError


class SalesFunnelAPI:
    """Preliminary product metrics from WB Sales Funnel analytics."""

    def __init__(
        self,
        client: WBClient | None = None,
        *,
        request_interval_seconds: float = WB_SALES_FUNNEL_REQUEST_INTERVAL_SECONDS,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if request_interval_seconds < 0:
            raise ValueError("request_interval_seconds must not be negative")
        self.client = client or WBClient(base_url=WB_ANALYTICS_BASE_URL)
        self.request_interval_seconds = request_interval_seconds
        self.sleeper = sleeper

    def history(self, date_from: date, date_to: date, nm_ids: Iterable[int]) -> list[dict[str, Any]]:
        if date_from > date_to:
            raise ValueError("date_from must not be later than date_to")
        if (date_to - date_from).days > 6:
            raise ValueError("WB Sales Funnel history supports no more than seven days")
        identifiers = list(dict.fromkeys(int(value) for value in nm_ids if int(value) > 0))
        result: list[dict[str, Any]] = []
        for offset in range(0, len(identifiers), 20):
            if offset and self.request_interval_seconds:
                self.sleeper(self.request_interval_seconds)
            payload = self.client.post(
                "/api/analytics/v3/sales-funnel/products/history",
                json_body={
                    "selectedPeriod": {"start": date_from.isoformat(), "end": date_to.isoformat()},
                    "nmIds": identifiers[offset : offset + 20],
                    "aggregationLevel": "day",
                    "skipDeletedNm": False,
                },
                retries=3,
            )
            page = payload.get("data") if isinstance(payload, dict) else payload
            if not isinstance(page, list):
                raise WBParseError("WB Sales Funnel response is not a list")
            result.extend(item for item in page if isinstance(item, dict))
        return result

    def pause(self) -> None:
        """Observe the shared Analytics API interval before a different report."""
        if self.request_interval_seconds:
            self.sleeper(self.request_interval_seconds)

    def grouped_history(self, date_from: date, date_to: date) -> list[dict[str, Any]]:
        if date_from > date_to:
            raise ValueError("date_from must not be later than date_to")
        if (date_to - date_from).days > 6:
            raise ValueError("WB grouped Sales Funnel history supports no more than seven days")
        payload = self.client.post(
            "/api/analytics/v3/sales-funnel/grouped/history",
            json_body={
                "selectedPeriod": {"start": date_from.isoformat(), "end": date_to.isoformat()},
                "brandNames": [],
                "subjectIds": [],
                "tagIds": [],
                "aggregationLevel": "day",
                "skipDeletedNm": False,
            },
            retries=3,
        )
        page = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(page, list):
            raise WBParseError("WB grouped Sales Funnel response is not a list")
        return [item for item in page if isinstance(item, dict)]
