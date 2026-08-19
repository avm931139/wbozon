from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from app.db import SessionLocal
from app.models import OzonProduct
from ozon.products import OzonProductsAPI
from ozon.repositories.product_repository import OzonProductRepository


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value not in (None, "") else None
    except (InvalidOperation, ValueError):
        return None


class OzonProductService:
    def __init__(self, api: OzonProductsAPI | None = None, *, session_factory: Callable[..., Any] = SessionLocal) -> None:
        self.api = api or OzonProductsAPI()
        self.session_factory = session_factory

    def sync_from_api(self) -> list[dict[str, Any]]:
        index = self.api.list()
        ids = [int(item["product_id"]) for item in index if item.get("product_id") is not None]
        details = self.api.info_list(ids)
        by_id = {int(item["id"]): item for item in details if item.get("id") is not None}
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            repository = OzonProductRepository(session)
            for index_item in index:
                product_id = index_item.get("product_id")
                if product_id is None:
                    continue
                product_id = int(product_id)
                detail = by_id.get(product_id, {})
                merged = {**index_item, **detail}
                row = repository.get(product_id)
                if row is None:
                    row = OzonProduct(product_id=product_id, raw_data=merged, created_at=now, updated_at=now)
                    session.add(row)
                row.offer_id = merged.get("offer_id")
                row.name = merged.get("name")
                row.sku = merged.get("sku")
                row.barcode = merged.get("barcode") or next(iter(merged.get("barcodes") or []), None)
                statuses = merged.get("statuses") or {}
                row.status = statuses.get("moderate_status") or statuses.get("status") or merged.get("status")
                row.visibility = merged.get("visibility")
                row.price = _decimal(merged.get("price"))
                row.old_price = _decimal(merged.get("old_price"))
                row.raw_data = merged
                row.updated_at = now
            session.commit()
        return index
