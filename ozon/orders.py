from __future__ import annotations

from datetime import datetime
from typing import Any

from ozon.client import OzonClient
from ozon.endpoints import OzonEndpoints


def _ozon_time(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


class OzonOrdersAPI:
    def __init__(self, client: OzonClient | None = None) -> None:
        self.client = client or OzonClient()

    def fbs_list(self, *, since: datetime, until: datetime, limit: int = 100) -> list[dict[str, Any]]:
        return self._list(OzonEndpoints.FBS_POSTINGS, "fbs", since, until, limit)

    def fbo_list(self, *, since: datetime, until: datetime, limit: int = 100) -> list[dict[str, Any]]:
        return self._list(OzonEndpoints.FBO_POSTINGS, "fbo", since, until, limit)

    def _list(self, path: str, scheme: str, since: datetime, until: datetime, limit: int) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100:
            raise ValueError("Ozon postings page limit must be between 1 and 100")
        postings: list[dict[str, Any]] = []
        cursor = ""
        while True:
            body: dict[str, Any] = {
                "sort_dir": "ASC",
                "filter": {"since": _ozon_time(since), "to": _ozon_time(until)},
                "limit": limit,
                "with": {"analytics_data": True, "financial_data": True},
            }
            if cursor:
                body["cursor"] = cursor
            payload = self.client.post(path, json_body=body)
            page = payload.get("postings", []) if isinstance(payload, dict) else []
            has_next = bool(payload.get("has_next")) if isinstance(payload, dict) else False
            next_cursor = str(payload.get("cursor") or "") if isinstance(payload, dict) else ""
            postings.extend(item for item in page if isinstance(item, dict))
            if not page or not has_next:
                break
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
        return postings
