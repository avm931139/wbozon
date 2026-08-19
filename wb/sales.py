from __future__ import annotations

import threading
import time
from datetime import date, datetime
from typing import Any

from app.config import WB_STATISTICS_BASE_URL
from wb.client import WBClient


class SalesOperationsAPI:
    """Operational orders, sales and returns from WB Statistics API."""

    def __init__(
        self,
        client: WBClient | None = None,
        *,
        request_interval_seconds: float = 60.0,
        clock: Any = time.monotonic,
        sleeper: Any = time.sleep,
    ) -> None:
        self.client = client or WBClient(base_url=WB_STATISTICS_BASE_URL)
        self.request_interval_seconds = request_interval_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._lock = threading.Lock()
        self._last_request: float | None = None

    def orders(self, date_from: date | datetime | str) -> list[dict[str, Any]]:
        return self._load("/api/v1/supplier/orders", date_from)

    def sales(self, date_from: date | datetime | str) -> list[dict[str, Any]]:
        return self._load("/api/v1/supplier/sales", date_from)

    def _load(self, path: str, date_from: date | datetime | str) -> list[dict[str, Any]]:
        cursor = date_from.isoformat() if isinstance(date_from, (date, datetime)) else str(date_from)
        result: list[dict[str, Any]] = []
        while True:
            with self._lock:
                now = self._clock()
                if self._last_request is not None:
                    delay = self.request_interval_seconds - (now - self._last_request)
                    if delay > 0:
                        self._sleeper(delay)
                self._last_request = self._clock()
                payload = self.client.get(path, params={"dateFrom": cursor, "flag": 0}, retries=8)
            rows = [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []
            result.extend(rows)
            if len(rows) < 80000:
                return result
            next_cursor = rows[-1].get("lastChangeDate")
            if not next_cursor or next_cursor == cursor:
                return result
            cursor = str(next_cursor)
