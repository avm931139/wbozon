from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ozon.client import OzonClient
from ozon.endpoints import OzonEndpoints
from ozon.exceptions import OzonParseError


class OzonWarehouseStocksAPI:
    """Read-only API adapter used by ``inventory_sync`` for warehouse stocks."""

    def __init__(self, client: OzonClient | None = None) -> None:
        self.client = client or OzonClient()

    def list_fbo(
        self,
        *,
        skus: Sequence[int] = (),
        offer_ids: Sequence[str] = (),
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        if not skus and not offer_ids:
            raise ValueError("skus or offer_ids must be specified")
        body: dict[str, Any] = {"limit": self._validate_limit(limit)}
        if skus:
            body["skus"] = self._unique(skus)
        if offer_ids:
            body["offer_ids"] = self._unique(offer_ids)
        return self._list_cursor_products(OzonEndpoints.FBO_STOCKS_BY_WAREHOUSE, body)

    def list_fbs(self, *, skus: Sequence[int], limit: int = 1000) -> list[dict[str, Any]]:
        if not skus:
            raise ValueError("skus must be specified")
        return self._list_cursor_products(
            OzonEndpoints.FBS_STOCKS_BY_WAREHOUSE,
            {"sku": self._unique(skus), "limit": self._validate_limit(limit)},
        )

    def list_analytics(self, *, skus: Sequence[int], batch_size: int = 100) -> list[dict[str, Any]]:
        if not skus:
            raise ValueError("skus must be specified")
        if not 1 <= batch_size <= 100:
            raise ValueError("batch_size must be between 1 and 100")

        result: list[dict[str, Any]] = []
        unique_skus = self._unique(skus)
        for offset in range(0, len(unique_skus), batch_size):
            payload = self.client.post(
                OzonEndpoints.ANALYTICS_STOCKS,
                json_body={"skus": unique_skus[offset : offset + batch_size]},
            )
            items = payload.get("items", []) if isinstance(payload, dict) else []
            if not isinstance(items, list):
                raise OzonParseError("Ozon analytics stocks response has no items list")
            result.extend(item for item in items if isinstance(item, dict))
        return result

    def _list_cursor_products(self, path: str, body: dict[str, Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        cursor = ""
        while True:
            payload = self.client.post(path, json_body={**body, "cursor": cursor})
            if not isinstance(payload, dict):
                raise OzonParseError("Ozon warehouse stocks response is not an object")
            products = payload.get("products", [])
            if not isinstance(products, list):
                raise OzonParseError("Ozon warehouse stocks response has no products list")
            result.extend(product for product in products if isinstance(product, dict))

            if not payload.get("has_next"):
                return result
            next_cursor = str(payload.get("cursor") or "")
            if not next_cursor or next_cursor == cursor:
                raise OzonParseError("Ozon warehouse stocks pagination cursor did not advance")
            cursor = next_cursor

    @staticmethod
    def _validate_limit(limit: int) -> int:
        if not 1 <= int(limit) <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        return int(limit)

    @staticmethod
    def _unique(values: Sequence[Any]) -> list[Any]:
        return list(dict.fromkeys(values))
