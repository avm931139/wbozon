from __future__ import annotations

from typing import Any

from ozon.client import OzonClient
from ozon.endpoints import OzonEndpoints


class OzonStocksAPI:
    def __init__(self, client: OzonClient | None = None) -> None:
        self.client = client or OzonClient()

    def list(self, *, visibility: str = "ALL", limit: int = 1000) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor = ""
        while True:
            payload = self.client.post(
                OzonEndpoints.STOCKS,
                json_body={"filter": {"visibility": visibility}, "cursor": cursor, "limit": limit},
            )
            page = payload.get("items", []) if isinstance(payload, dict) else []
            items.extend(item for item in page if isinstance(item, dict))
            next_cursor = str(payload.get("cursor") or "") if isinstance(payload, dict) else ""
            if not page or len(page) < limit or not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
        return items
