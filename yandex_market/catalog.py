from __future__ import annotations

from typing import Any

from yandex_market.client import YandexMarketClient
from yandex_market.endpoints import campaign_offers, offer_mappings
from yandex_market.exceptions import YandexMarketParseError


class YandexMarketCatalogAPI:
    """Read the cabinet catalog and campaign assortment."""

    def __init__(self, client: YandexMarketClient | None = None) -> None:
        self.client = client or YandexMarketClient()

    def offer_mappings(self, *, business_id: int, limit: int = 100) -> list[dict[str, Any]]:
        return self._paged_post(
            offer_mappings(business_id),
            item_key="offerMappings",
            limit=limit,
            json_body={},
        )

    def campaign_offers(self, *, campaign_id: int, limit: int = 100) -> list[dict[str, Any]]:
        return self._paged_post(
            campaign_offers(campaign_id),
            item_key="offers",
            limit=limit,
            json_body={},
        )

    def _paged_post(
        self,
        path: str,
        *,
        item_key: str,
        limit: int,
        json_body: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        rows: list[dict[str, Any]] = []
        page_token: str | None = None
        seen_tokens: set[str] = set()
        while True:
            params: dict[str, Any] = {"limit": limit}
            if page_token:
                params["pageToken"] = page_token
            payload = self.client.post(path, params=params, json_body=json_body)
            result = payload.get("result")
            if not isinstance(result, dict):
                raise YandexMarketParseError(f"Yandex Market {item_key} response has no result object")
            items = result.get(item_key)
            if not isinstance(items, list):
                raise YandexMarketParseError(f"Yandex Market response has no {item_key} list")
            rows.extend(item for item in items if isinstance(item, dict))
            paging = result.get("paging") or payload.get("paging") or {}
            if not isinstance(paging, dict):
                raise YandexMarketParseError(f"Yandex Market {item_key} paging is not an object")
            next_token = str(paging.get("nextPageToken") or "")
            if not next_token:
                return rows
            if next_token == page_token or next_token in seen_tokens:
                raise YandexMarketParseError(f"Yandex Market {item_key} pagination token did not advance")
            seen_tokens.add(next_token)
            page_token = next_token
