from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class PriceRecord:
    source_key: str
    account_id: str = ""
    offer_id: str | None = None
    product_id: str | None = None
    variant_id: str | None = None
    product_name: str | None = None
    currency: str | None = None
    list_price: Decimal | None = None
    seller_price: Decimal | None = None
    customer_price: Decimal | None = None
    club_price: Decimal | None = None
    min_price: Decimal | None = None
    discount_percent: Decimal | None = None
    club_discount_percent: Decimal | None = None
    in_promotion: bool | None = None
    auto_action_enabled: bool | None = None
    promotion_names: list[str] = field(default_factory=list)
    source_updated_at: datetime | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)
