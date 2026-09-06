from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.config import WB_API_KEY, WB_PRICES_BASE_URL, WB_TIMEOUT_SECONDS
from price_sync.types import PriceRecord
from wb.client import WBClient
from wb.endpoints import WBPricesEndpoints
from wb.exceptions import WBParseError


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value not in (None, "") else None
    except (InvalidOperation, TypeError, ValueError):
        return None


class WBPricesAPI:
    def __init__(self, client: WBClient | None = None) -> None:
        self.client = client or WBClient(
            api_key=WB_API_KEY,
            base_url=WB_PRICES_BASE_URL,
            timeout=WB_TIMEOUT_SECONDS,
        )

    def list_all(self, *, limit: int = 1000) -> list[dict[str, Any]]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            payload = self.client.get(
                WBPricesEndpoints.LIST,
                params={"limit": limit, "offset": offset},
            )
            data = payload.get("data") if isinstance(payload, dict) else None
            page = data.get("listGoods") if isinstance(data, dict) else None
            if not isinstance(page, list):
                raise WBParseError("WB prices response has no data.listGoods list")
            rows.extend(item for item in page if isinstance(item, dict))
            if not page:
                return rows
            offset += limit

    def records(self) -> list[PriceRecord]:
        records: list[PriceRecord] = []
        for item in self.list_all():
            nm_id = item.get("nmID")
            if nm_id is None:
                continue
            sizes = item.get("sizes") if isinstance(item.get("sizes"), list) else []
            for size in sizes or [{}]:
                if not isinstance(size, dict):
                    continue
                size_id = str(size.get("sizeID") or "default")
                records.append(PriceRecord(
                    source_key=f"{nm_id}:{size_id}",
                    offer_id=str(item.get("vendorCode")) if item.get("vendorCode") is not None else None,
                    product_id=str(nm_id),
                    variant_id=size_id,
                    product_name=item.get("title"),
                    currency=item.get("currencyIsoCode4217"),
                    list_price=_decimal(size.get("price")),
                    seller_price=_decimal(size.get("discountedPrice")),
                    customer_price=_decimal(size.get("discountedPrice")),
                    club_price=_decimal(size.get("clubDiscountedPrice")),
                    discount_percent=_decimal(item.get("discount")),
                    club_discount_percent=_decimal(item.get("clubDiscount")),
                    raw_data={"product": item, "size": size},
                ))
        return records
