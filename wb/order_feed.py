from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Callable

from app.config import WB_ANALYTICS_BASE_URL
from wb.client import WBClient
from wb.exceptions import WBParseError


class OrderFeedAPI:
    """Realtime WB Order Feed with snapshot-safe offset pagination."""

    def __init__(
        self,
        client: WBClient | None = None,
        *,
        request_interval_seconds: float = 60.0,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if request_interval_seconds < 0:
            raise ValueError("request_interval_seconds must not be negative")
        self.client = client or WBClient(base_url=WB_ANALYTICS_BASE_URL)
        self.request_interval_seconds = request_interval_seconds
        self.sleeper = sleeper

    def list(self, date_from: datetime, date_to: datetime, limit: int = 10_000) -> list[dict[str, Any]]:
        if date_from > date_to:
            raise ValueError("date_from must not be later than date_to")
        if not 1 <= limit <= 10_000:
            raise ValueError("limit must be between 1 and 10000")
        result: list[dict[str, Any]] = []
        offset = 0
        snapshot_time: str | None = None
        while True:
            pagination: dict[str, Any] = {"limit": limit, "offset": offset}
            if snapshot_time:
                pagination["snapshotTime"] = snapshot_time
            payload = self.client.post(
                "/api/analytics/v1/order-feed",
                json_body={
                    "selectedPeriod": {
                        "start": date_from.isoformat(),
                        "end": date_to.isoformat(),
                    },
                    "brandNames": [],
                    "subjectIds": [],
                    "tagIds": [],
                    "nmIds": [],
                    "pagination": pagination,
                },
                retries=3,
            )
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, dict) or not isinstance(data.get("orders"), list):
                raise WBParseError("WB Order Feed response has no data.orders list")
            page = [item for item in data["orders"] if isinstance(item, dict)]
            result.extend(page)
            if len(page) < limit:
                return result
            new_snapshot = str(data.get("snapshotTime") or "")
            if not new_snapshot:
                raise WBParseError("WB Order Feed pagination has no snapshotTime")
            snapshot_time = snapshot_time or new_snapshot
            offset += len(page)
            if self.request_interval_seconds:
                self.sleeper(self.request_interval_seconds)
