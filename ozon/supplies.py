from __future__ import annotations

from typing import Any
from ozon.client import OzonClient


class OzonSuppliesAPI:
    def __init__(self, client: OzonClient | None = None) -> None:
        self.client = client or OzonClient()

    def list(self, *, limit: int = 100) -> list[dict[str, Any]]:
        """Return supply order identifiers.

        The Seller API method has no creation-date filter. Callers that need a
        bounded history must filter the details returned by :meth:`get`.
        """
        rows: list[dict[str, Any]] = []
        last_id = ""
        while True:
            body = {"filter": {"states": list(range(1, 11))}, "limit": limit, "last_id": last_id, "sort_by": 1}
            payload = self.client.post("/v3/supply-order/list", json_body=body)
            result = payload if isinstance(payload, dict) else {}
            page = result.get("order_ids", [])
            rows.extend({"supply_order_id": int(x)} for x in page)
            next_id = str(result.get("last_id") or "") if isinstance(result, dict) else ""
            if not page or not next_id or next_id == last_id:
                return rows
            last_id = next_id

    def get(self, supply_order_id: int) -> dict[str, Any]:
        payload = self.client.post("/v3/supply-order/get", json_body={"order_ids": [supply_order_id]})
        orders = payload.get("orders", []) if isinstance(payload, dict) else []
        return orders[0] if orders else {}
