from __future__ import annotations

from typing import Any

from yandex_market.client import YandexMarketClient
from yandex_market.endpoints import CAMPAIGNS, FULFILLMENT_WAREHOUSES, partner_warehouses
from yandex_market.exceptions import YandexMarketParseError


class YandexMarketIdentityAPI:
    """Read businesses and campaigns available to the configured API key."""

    def __init__(self, client: YandexMarketClient | None = None) -> None:
        self.client = client or YandexMarketClient()

    def campaigns(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        rows: list[dict[str, Any]] = []
        page_token: str | None = None
        seen_tokens: set[str] = set()
        while True:
            params: dict[str, Any] = {"limit": limit}
            if page_token:
                params["pageToken"] = page_token
            payload = self.client.get(CAMPAIGNS, params=params)
            campaigns = payload.get("campaigns")
            if not isinstance(campaigns, list):
                raise YandexMarketParseError("Yandex Market campaigns response has no campaigns list")
            rows.extend(item for item in campaigns if isinstance(item, dict))
            paging = payload.get("paging") or {}
            if not isinstance(paging, dict):
                raise YandexMarketParseError("Yandex Market campaigns paging is not an object")
            next_token = str(paging.get("nextPageToken") or "")
            if not next_token:
                return rows
            if next_token == page_token or next_token in seen_tokens:
                raise YandexMarketParseError("Yandex Market campaigns pagination token did not advance")
            seen_tokens.add(next_token)
            page_token = next_token

    def contexts(self) -> tuple[list[dict[str, Any]], set[int]]:
        campaigns = self.campaigns()
        business_ids = {
            int(item["business"]["id"])
            for item in campaigns
            if isinstance(item.get("business"), dict) and item["business"].get("id")
        }
        return campaigns, business_ids

    def partner_warehouses(
        self,
        *,
        business_id: int,
        campaign_ids: list[int],
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        page_token: str | None = None
        seen_tokens: set[str] = set()
        while True:
            params: dict[str, Any] = {"limit": limit}
            if page_token:
                params["pageToken"] = page_token
            payload = self.client.post(
                partner_warehouses(business_id),
                params=params,
                json_body={
                    "components": ["ADDRESS", "STATUS"],
                    "campaignIds": campaign_ids,
                },
            )
            result = payload.get("result")
            if not isinstance(result, dict) or not isinstance(result.get("warehouses"), list):
                raise YandexMarketParseError("Yandex Market partner warehouses response is invalid")
            rows.extend(item for item in result["warehouses"] if isinstance(item, dict))
            paging = result.get("paging") or {}
            next_token = str(paging.get("nextPageToken") or "") if isinstance(paging, dict) else ""
            if not next_token:
                return rows
            if next_token == page_token or next_token in seen_tokens:
                raise YandexMarketParseError("Yandex Market warehouses pagination token did not advance")
            seen_tokens.add(next_token)
            page_token = next_token

    def fulfillment_warehouses(self, *, campaign_id: int) -> list[dict[str, Any]]:
        payload = self.client.get(FULFILLMENT_WAREHOUSES, params={"campaignId": campaign_id})
        result = payload.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("warehouses"), list):
            raise YandexMarketParseError("Yandex Market fulfillment warehouses response is invalid")
        return [item for item in result["warehouses"] if isinstance(item, dict)]
