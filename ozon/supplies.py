from __future__ import annotations

from typing import Any

from ozon.client import OzonClient
from ozon.endpoints import OzonSupplyReconciliationEndpoints
from ozon.exceptions import OzonParseError


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

    def bundle(self, bundle_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        if not bundle_id:
            raise ValueError("bundle_id is required")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        rows: list[dict[str, Any]] = []
        last_id = ""
        while True:
            payload = self.client.post(
                OzonSupplyReconciliationEndpoints.BUNDLE,
                json_body={
                    "bundle_ids": [bundle_id],
                    "limit": limit,
                    "last_id": last_id,
                    "is_asc": True,
                    "sort_field": "SKU",
                },
                retries=6,
            )
            if not isinstance(payload, dict):
                raise OzonParseError("Ozon supply bundle response is not an object")
            page = payload.get("items")
            if not isinstance(page, list) or any(not isinstance(item, dict) for item in page):
                raise OzonParseError("Ozon supply bundle response has invalid items")
            rows.extend(page)
            has_next = payload.get("has_next") is True
            next_id = str(payload.get("last_id") or "")
            if not has_next:
                return rows
            if not next_id or next_id == last_id:
                raise OzonParseError("Ozon supply bundle pagination did not advance")
            last_id = next_id

    def act_summary(self, supply_order_id: int) -> dict[str, Any]:
        payload = self.client.post(
            OzonSupplyReconciliationEndpoints.ACT_SUMMARY,
            json_body={"order_id": supply_order_id},
            retries=6,
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("supplies_acts", []), list):
            raise OzonParseError("Ozon supply act summary response is invalid")
        return payload

    def act_products(self, supply_id: int) -> dict[str, Any]:
        payload = self.client.post(
            OzonSupplyReconciliationEndpoints.ACT_PRODUCTS,
            json_body={"supply_id": supply_id},
            retries=6,
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("supply_acts", []), list):
            raise OzonParseError("Ozon supply act products response is invalid")
        return payload
