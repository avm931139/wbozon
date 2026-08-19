from typing import Any

from app.db import SessionLocal
from app.models import WBFBSStock, WBProductSize
from wb.repositories.stock_repository import StockRepository
from wb.repositories.warehouse_repository import WarehouseRepository
from wb.stocks import StocksAPI


class StockService:
    """Loads stock quantities by WB size (chrtID) and warehouse."""

    def __init__(self):
        self.api = StocksAPI()

    def sync_from_api(self, **kwargs: Any) -> list[dict[str, Any]]:
        payload = self.api.list(**kwargs)
        if not isinstance(payload, list):
            return []

        with SessionLocal() as session:
            warehouse_repository = WarehouseRepository(session)
            stock_repository = StockRepository(session)
            for item in payload:
                chrt_id = item.get("chrtId") or item.get("chrtID")
                sku = item.get("sku")
                warehouse_wb_id = item.get("warehouseId") or kwargs.get("warehouse_id")
                if chrt_id is None or sku is None or warehouse_wb_id is None:
                    continue
                size = session.query(WBProductSize).filter_by(chrt_id=int(chrt_id)).first()
                warehouse = warehouse_repository.get_by_wb_id(int(warehouse_wb_id))
                if size is None or warehouse is None:
                    continue

                stock = stock_repository.get_by_sku_and_warehouse(str(sku), warehouse.id)
                quantity = item.get("amount", item.get("quantity", item.get("stock", 0)))
                if stock is None:
                    stock = stock_repository.add(
                        WBFBSStock(size_id=size.id, warehouse_id=warehouse.id, sku=str(sku))
                    )
                stock.size_id = size.id
                stock.quantity = int(quantity or 0)
                stock.raw_data = item

            session.commit()

        return payload
