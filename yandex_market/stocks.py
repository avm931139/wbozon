from __future__ import annotations

from typing import Any

from yandex_market.client import YandexMarketClient
from yandex_market.endpoints import campaign_stocks
from yandex_market.exceptions import YandexMarketParseError


class YandexMarketStocksAPI:
    """Read warehouse-level stock balances for one or more Market campaigns."""

    def __init__(self, client: YandexMarketClient | None = None) -> None:
        self.client = client or YandexMarketClient()

    def list(
        self,
        *,
        campaign_id: int,
        limit: int = 100,
        with_turnover: bool = True,
    ) -> list[dict[str, Any]]:
        if campaign_id < 1:
            raise ValueError("campaign_id must be positive")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        items: list[dict[str, Any]] = []
        page_token: str | None = None
        seen_tokens: set[str] = set()
        while True:
            params: dict[str, Any] = {"limit": limit}
            if page_token:
                params["pageToken"] = page_token
            payload = self.client.post(
                campaign_stocks(campaign_id),
                params=params,
                json_body={"withTurnover": with_turnover},
            )
            result = payload.get("result")
            if not isinstance(result, dict):
                raise YandexMarketParseError("Yandex Market stock response has no result object")
            warehouses = result.get("warehouses")
            if not isinstance(warehouses, list):
                raise YandexMarketParseError("Yandex Market stock response has no warehouses list")

            for warehouse in warehouses:
                if not isinstance(warehouse, dict) or warehouse.get("warehouseId") is None:
                    raise YandexMarketParseError("Yandex Market stock response has an invalid warehouse")
                offers = warehouse.get("offers")
                if not isinstance(offers, list):
                    raise YandexMarketParseError("Yandex Market warehouse has no offers list")
                for offer in offers:
                    if not isinstance(offer, dict):
                        continue
                    items.append(
                        {
                            **offer,
                            "campaignId": campaign_id,
                            "warehouseId": int(warehouse["warehouseId"]),
                        }
                    )

            paging = result.get("paging") or {}
            if not isinstance(paging, dict):
                raise YandexMarketParseError("Yandex Market stock paging is not an object")
            next_token = str(paging.get("nextPageToken") or "")
            if not next_token:
                break
            if next_token == page_token or next_token in seen_tokens:
                raise YandexMarketParseError("Yandex Market stock pagination token did not advance")
            seen_tokens.add(next_token)
            page_token = next_token
        return items
