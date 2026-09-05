from __future__ import annotations

from datetime import date
from typing import Any

from yandex_market.client import YandexMarketClient
from yandex_market.endpoints import business_orders
from yandex_market.exceptions import YandexMarketParseError


class YandexMarketOrdersAPI:
    """Read cabinet orders through the current business-level endpoint."""

    def __init__(self, client: YandexMarketClient | None = None) -> None:
        self.client = client or YandexMarketClient()

    def list(
        self,
        *,
        business_id: int,
        date_from: date,
        date_to: date,
        campaign_ids: list[int] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if business_id < 1:
            raise ValueError("business_id must be positive")
        if date_to < date_from:
            raise ValueError("date_to must not be before date_from")
        if (date_to - date_from).days > 30:
            raise ValueError("Yandex Market order range must not exceed 30 days")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")

        body: dict[str, Any] = {
            "dates": {
                "creationDateFrom": date_from.isoformat(),
                "creationDateTo": date_to.isoformat(),
            },
            "fake": False,
        }
        if campaign_ids:
            body["campaignIds"] = campaign_ids

        rows: list[dict[str, Any]] = []
        page_token: str | None = None
        seen_tokens: set[str] = set()
        while True:
            params: dict[str, Any] = {"limit": limit}
            if page_token:
                params["pageToken"] = page_token
            payload = self.client.post(
                business_orders(business_id),
                params=params,
                json_body=body,
            )
            result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
            orders = result.get("orders")
            if not isinstance(orders, list):
                raise YandexMarketParseError("Yandex Market orders response has no orders list")
            rows.extend(item for item in orders if isinstance(item, dict))
            paging = result.get("paging") or payload.get("paging") or {}
            if not isinstance(paging, dict):
                raise YandexMarketParseError("Yandex Market orders paging is not an object")
            next_token = str(paging.get("nextPageToken") or "")
            if not next_token:
                return rows
            if next_token == page_token or next_token in seen_tokens:
                raise YandexMarketParseError("Yandex Market orders pagination token did not advance")
            seen_tokens.add(next_token)
            page_token = next_token
