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

    def fbs_list(self, *, since: datetime, until: datetime, limit: int = 1000) -> list[dict[str, Any]]:
        return self._list(OzonEndpoints.FBS_POSTINGS, "fbs", since, until, limit)

    def fbo_list(self, *, since: datetime, until: datetime, limit: int = 1000) -> list[dict[str, Any]]:
        return self._list(OzonEndpoints.FBO_POSTINGS, "fbo", since, until, limit)

    def _list(self, path: str, scheme: str, since: datetime, until: datetime, limit: int) -> list[dict[str, Any]]:
        postings: list[dict[str, Any]] = []
        offset = 0
        while True:
            body: dict[str, Any] = {
                "dir": "ASC",
                "filter": {"since": _ozon_time(since), "to": _ozon_time(until)},
                "limit": limit,
                "offset": offset,
                "with": {"analytics_data": True, "financial_data": True},
            }
            payload = self.client.post(path, json_body=body)
            result = payload.get("result", {}) if isinstance(payload, dict) else {}
            if isinstance(result, dict):
                page = result.get("postings", [])
                has_next = bool(result.get("has_next"))
            elif isinstance(result, list):
                page = result
                has_next = len(page) >= limit
            else:
                page = []
                has_next = False
            postings.extend(item for item in page if isinstance(item, dict))
            if not page or not has_next:
                break
            offset += len(page)
        return postings
