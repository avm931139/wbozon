from copy import deepcopy
from typing import Any

from app.config import WB_CONTENT_BASE_URL
from wb.base import WBAPIBase
from wb.client import WBClient
from wb.endpoints import WBEndpoints


class ProductsAPI(WBAPIBase):
    """API для карточек/товаров Wildberries."""

    def __init__(self, client: WBClient | None = None):
        super().__init__(client or WBClient(base_url=WB_CONTENT_BASE_URL))

    def list(self, **kwargs: Any) -> list[dict[str, Any]]:
        supplied_settings = kwargs.pop("settings", None)
        settings = deepcopy(supplied_settings) if supplied_settings is not None else {}
        requested_limit = kwargs.pop("limit", None)
        settings.update(kwargs)

        cursor = settings.setdefault("cursor", {})
        limit = int(cursor.setdefault("limit", requested_limit or 100))
        cards: list[dict[str, Any]] = []
        previous_cursor: tuple[Any, Any] | None = None

        while True:
            payload = self.client.post(
                WBEndpoints.PRODUCTS_LIST,
                json_body={"settings": settings},
            )
            if not isinstance(payload, dict):
                break

            page = payload.get("cards", [])
            if not isinstance(page, list):
                break
            cards.extend(item for item in page if isinstance(item, dict))

            response_cursor = payload.get("cursor")
            if not isinstance(response_cursor, dict) or response_cursor.get("total", len(page)) < limit:
                break

            next_cursor = (response_cursor.get("updatedAt"), response_cursor.get("nmID"))
            if next_cursor == previous_cursor or all(value is None for value in next_cursor):
                break

            previous_cursor = next_cursor
            cursor.update(
                {
                    "updatedAt": next_cursor[0],
                    "nmID": next_cursor[1],
                }
            )

        return cards
