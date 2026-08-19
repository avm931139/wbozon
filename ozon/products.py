from __future__ import annotations

from typing import Any

from ozon.client import OzonClient
from ozon.endpoints import OzonEndpoints


class OzonProductsAPI:
    def __init__(self, client: OzonClient | None = None) -> None:
        self.client = client or OzonClient()

    def list(self, *, visibility: str = "ALL", limit: int = 1000) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        last_id = ""
        while True:
            payload = self.client.post(
                OzonEndpoints.PRODUCT_LIST,
                json_body={"filter": {"visibility": visibility}, "last_id": last_id, "limit": limit},
            )
            result = payload.get("result", {}) if isinstance(payload, dict) else {}
            page = result.get("items", []) if isinstance(result, dict) else []
            items.extend(item for item in page if isinstance(item, dict))
            next_id = str(result.get("last_id") or "")
            if not page or len(page) < limit or not next_id or next_id == last_id:
                break
            last_id = next_id
        return items

    def info_list(self, product_ids: list[int], *, batch_size: int = 1000) -> list[dict[str, Any]]:
        details: list[dict[str, Any]] = []
        for offset in range(0, len(product_ids), batch_size):
            payload = self.client.post(
                OzonEndpoints.PRODUCT_INFO_LIST,
                json_body={"product_id": product_ids[offset : offset + batch_size]},
            )
            if not isinstance(payload, dict):
                continue
            result = payload.get("items", payload.get("result", {}).get("items", []))
            if isinstance(result, list):
                details.extend(item for item in result if isinstance(item, dict))
        return details
