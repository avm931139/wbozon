from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.config import OZON_CLIENT_ID
from ozon.client import OzonClient
from ozon.exceptions import OzonParseError
from price_sync.types import PriceRecord


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value not in (None, "") else None
    except (InvalidOperation, TypeError, ValueError):
        return None


class OzonPricesAPI:
    PATH = "/v5/product/info/prices"

    def __init__(self, client: OzonClient | None = None) -> None:
        self.client = client or OzonClient()

    def list_all(self, *, limit: int = 1000) -> list[dict[str, Any]]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        rows: list[dict[str, Any]] = []
        cursor = ""
        seen: set[str] = set()
        while True:
            payload = self.client.post(
                self.PATH,
                json_body={
                    "filter": {"visibility": "ALL"},
                    "limit": limit,
                    "cursor": cursor,
                },
            )
            page = payload.get("items") if isinstance(payload, dict) else None
            if not isinstance(page, list):
                raise OzonParseError("Ozon prices response has no items list")
            rows.extend(item for item in page if isinstance(item, dict))
            next_cursor = str(payload.get("cursor") or "")
            if not page or not next_cursor:
                return rows
            if next_cursor == cursor or next_cursor in seen:
                raise OzonParseError("Ozon prices cursor did not advance")
            seen.add(next_cursor)
            cursor = next_cursor

    def records(self) -> list[PriceRecord]:
        records: list[PriceRecord] = []
        for item in self.list_all():
            product_id = item.get("product_id")
            if product_id is None:
                continue
            price = item.get("price") if isinstance(item.get("price"), dict) else {}
            marketing = (
                item.get("marketing_actions")
                if isinstance(item.get("marketing_actions"), dict)
                else {}
            )
            actions = marketing.get("actions") if isinstance(marketing.get("actions"), list) else []
            names = [
                str(action.get("title"))
                for action in actions
                if isinstance(action, dict) and action.get("title")
            ]
            records.append(PriceRecord(
                source_key=str(product_id),
                account_id=str(OZON_CLIENT_ID or ""),
                offer_id=str(item.get("offer_id")) if item.get("offer_id") is not None else None,
                product_id=str(product_id),
                currency=price.get("currency_code"),
                list_price=_decimal(price.get("old_price")),
                seller_price=_decimal(price.get("marketing_seller_price")),
                customer_price=_decimal(price.get("price")),
                min_price=_decimal(price.get("min_price")),
                in_promotion=bool(actions),
                auto_action_enabled=price.get("auto_action_enabled"),
                promotion_names=names,
                raw_data=item,
            ))
        return records
