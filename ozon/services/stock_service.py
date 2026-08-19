from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from app.db import SessionLocal
from app.models import OzonStock
from ozon.repositories.stock_repository import OzonStockRepository
from ozon.stocks import OzonStocksAPI


class OzonStockService:
    def __init__(self, api: OzonStocksAPI | None = None, *, session_factory: Callable[..., Any] = SessionLocal) -> None:
        self.api = api or OzonStocksAPI()
        self.session_factory = session_factory

    def sync_from_api(self) -> list[dict[str, Any]]:
        items = self.api.list()
        fetched_at = datetime.now(timezone.utc)
        with self.session_factory() as session:
            repository = OzonStockRepository(session)
            for item in items:
                product_id = item.get("product_id")
                if product_id is None:
                    continue
                for stock in item.get("stocks") or []:
                    if not isinstance(stock, dict):
                        continue
                    stock_type = str(stock.get("type") or "unknown").lower()
                    row = repository.get(int(product_id), stock_type)
                    if row is None:
                        row = OzonStock(product_id=int(product_id), stock_type=stock_type, raw_data=stock, fetched_at=fetched_at)
                        session.add(row)
                    row.offer_id = item.get("offer_id")
                    row.present = int(stock.get("present") or 0)
                    row.reserved = int(stock.get("reserved") or 0)
                    row.raw_data = stock
                    row.fetched_at = fetched_at
            session.commit()
        return items
