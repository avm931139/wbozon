from typing import Any

from sqlalchemy import delete

from app.db import SessionLocal
from app.models import WBFboStock, WBFboWarehouse, WBProductSize
from wb.fbo_stocks import FBOStocksAPI


class FBOStockService:
    """Persists the current FBO inventory snapshot from Seller Analytics."""

    def __init__(self):
        self.api = FBOStocksAPI()

    def sync_from_api(self, **kwargs: Any) -> list[dict[str, Any]]:
        payload = self.api.list(**kwargs)
        full_snapshot = not kwargs.get("nm_ids") and not kwargs.get("chrt_ids")

        with SessionLocal() as session:
            sizes = {size.chrt_id: size for size in session.query(WBProductSize).all()}
            warehouse_keys = {
                self._warehouse_key(item)
                for item in payload
                if item.get("warehouseId") is not None and item.get("chrtId") is not None
            }
            warehouses = {
                (warehouse.wb_id, warehouse.name, warehouse.region_name): warehouse
                for warehouse in session.query(WBFboWarehouse).all()
            }
            for key in warehouse_keys:
                if key not in warehouses:
                    warehouse = WBFboWarehouse(wb_id=key[0], name=key[1], region_name=key[2])
                    session.add(warehouse)
                    warehouses[key] = warehouse
            session.flush()

            existing = {
                (stock.size_id, stock.warehouse_id): stock
                for stock in session.query(WBFboStock).all()
            }
            retained: set[tuple[int, int]] = set()
            for item in payload:
                chrt_id = item.get("chrtId")
                if chrt_id is None:
                    continue
                size = sizes.get(int(chrt_id))
                warehouse = warehouses.get(self._warehouse_key(item))
                if size is None or warehouse is None:
                    continue
                key = (size.id, warehouse.id)
                retained.add(key)
                stock = existing.get(key)
                if stock is None:
                    stock = WBFboStock(size_id=size.id, warehouse_id=warehouse.id)
                    session.add(stock)
                stock.quantity = int(item.get("quantity") or 0)
                stock.in_way_to_client = int(item.get("inWayToClient") or 0)
                stock.in_way_from_client = int(item.get("inWayFromClient") or 0)
                stock.raw_data = item

            if full_snapshot:
                for key, stock in existing.items():
                    if key not in retained:
                        session.delete(stock)
                session.flush()
                used_warehouse_ids = {warehouse_id for _, warehouse_id in retained}
                session.execute(
                    delete(WBFboWarehouse).where(WBFboWarehouse.id.not_in(used_warehouse_ids))
                )

            session.commit()

        return payload

    @staticmethod
    def _warehouse_key(item: dict[str, Any]) -> tuple[int, str, str]:
        return (
            int(item.get("warehouseId") or 0),
            str(item.get("warehouseName") or ""),
            str(item.get("regionName") or ""),
        )
