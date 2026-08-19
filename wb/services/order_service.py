import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.db import SessionLocal
from app.models import (
    WBFboOrder,
    WBFBSOrder,
    WBFBSWarehouse,
    WBProduct,
    WBProductSize,
    WBSizeBarcode,
)
from wb.orders import FBSOrdersAPI, OrdersHistoryAPI


def _dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value or value.startswith("0001-01-01"):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class FBSOrderService:
    def __init__(self):
        self.api = FBSOrdersAPI()

    def sync_max_history(self, start: datetime | None = None, end: datetime | None = None) -> int:
        current = start or datetime(2019, 1, 1, tzinfo=timezone.utc)
        end = end or datetime.now(timezone.utc)
        total = 0
        loaded_ids: list[int] = []
        while current < end:
            period_end = min(current + timedelta(days=30) - timedelta(seconds=1), end)
            rows = self.api.list(current, period_end)
            self._persist(rows)
            loaded_ids.extend(int(row["id"]) for row in rows if row.get("id") is not None)
            total += len(rows)
            current = period_end + timedelta(seconds=1)
            time.sleep(0.21)

        if loaded_ids:
            statuses = self.api.statuses(list(dict.fromkeys(loaded_ids)))
            with SessionLocal() as session:
                for order_id, status in statuses.items():
                    order = session.query(WBFBSOrder).filter_by(order_id=order_id).first()
                    if order:
                        order.supplier_status = status.get("supplierStatus")
                        order.wb_status = status.get("wbStatus")
                session.commit()
        return total

    @staticmethod
    def _persist(rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        with SessionLocal() as session:
            products = {row.nm_id: row for row in session.query(WBProduct).all()}
            sizes = {row.chrt_id: row for row in session.query(WBProductSize).all()}
            warehouses = {row.wb_id: row for row in session.query(WBFBSWarehouse).all()}
            existing = {
                row.order_id: row
                for row in session.query(WBFBSOrder).filter(WBFBSOrder.order_id.in_([int(x["id"]) for x in rows])).all()
            }
            for item in rows:
                order_id = int(item["id"])
                order = existing.get(order_id)
                if order is None:
                    order = WBFBSOrder(order_id=order_id, created_at_wb=_dt(item.get("createdAt")), raw_data=item)
                    session.add(order)
                nm_id, chrt_id, warehouse_wb_id = item.get("nmId"), item.get("chrtId"), item.get("warehouseId")
                order.product_id = products.get(int(nm_id)).id if nm_id is not None and int(nm_id) in products else None
                order.size_id = sizes.get(int(chrt_id)).id if chrt_id is not None and int(chrt_id) in sizes else None
                order.warehouse_id = warehouses.get(int(warehouse_wb_id)).id if warehouse_wb_id is not None and int(warehouse_wb_id) in warehouses else None
                order.warehouse_wb_id = warehouse_wb_id
                order.office_id = item.get("officeId")
                order.order_uid = item.get("orderUid"); order.rid = item.get("rid")
                order.supply_id = item.get("supplyId"); order.delivery_type = item.get("deliveryType")
                order.article = item.get("article"); order.color_code = item.get("colorCode"); order.skus = item.get("skus")
                order.price = item.get("price"); order.scan_price = item.get("scanPrice"); order.converted_price = item.get("convertedPrice")
                order.currency_code = item.get("currencyCode"); order.converted_currency_code = item.get("convertedCurrencyCode")
                order.cargo_type = item.get("cargoType"); order.cross_border_type = item.get("crossBorderType")
                order.is_zero_order = bool(item.get("isZeroOrder")); order.is_b2b = bool((item.get("options") or {}).get("isB2b") or (item.get("options") or {}).get("isB2B"))
                order.address = item.get("address"); order.raw_data = item
            session.commit()


class FBOOrderService:
    def __init__(self):
        self.api = OrdersHistoryAPI()

    def sync_max_history(self, date_from: date | str = "2019-01-01") -> tuple[int, int]:
        rows = self.api.list(date_from)
        fbo_rows = [row for row in rows if "продав" not in str(row.get("warehouseType") or "").casefold()]
        with SessionLocal() as session:
            products = {row.nm_id: row for row in session.query(WBProduct).all()}
            barcode_sizes = {
                barcode.barcode: barcode.size
                for barcode in session.query(WBSizeBarcode).all()
            }
            for item in fbo_rows:
                srid = item.get("srid")
                order_date, last_change = _dt(item.get("date")), _dt(item.get("lastChangeDate"))
                if not srid or order_date is None or last_change is None:
                    continue
                order = session.query(WBFboOrder).filter_by(srid=str(srid)).first()
                if order is None:
                    order = WBFboOrder(srid=str(srid), order_date=order_date, last_change_date=last_change, raw_data=item)
                    session.add(order)
                nm_id = item.get("nmId"); size = barcode_sizes.get(str(item.get("barcode")))
                order.product_id = products.get(int(nm_id)).id if nm_id is not None and int(nm_id) in products else None
                order.size_id = size.id if size else None
                order.order_date = order_date; order.last_change_date = last_change
                order.warehouse_name = item.get("warehouseName"); order.warehouse_type = item.get("warehouseType")
                order.country_name = item.get("countryName"); order.federal_district_name = item.get("oblastOkrugName"); order.region_name = item.get("regionName")
                order.supplier_article = item.get("supplierArticle"); order.barcode = item.get("barcode")
                order.category = item.get("category"); order.subject = item.get("subject"); order.brand = item.get("brand"); order.tech_size = item.get("techSize")
                order.income_id = item.get("incomeID"); order.is_supply = bool(item.get("isSupply")); order.is_realization = bool(item.get("isRealization"))
                order.total_price = item.get("totalPrice"); order.discount_percent = item.get("discountPercent"); order.spp = item.get("spp")
                order.finished_price = item.get("finishedPrice"); order.price_with_discount = item.get("priceWithDisc")
                order.is_cancel = bool(item.get("isCancel")); order.cancel_date = _dt(item.get("cancelDate"))
                order.sticker = item.get("sticker"); order.g_number = item.get("gNumber"); order.raw_data = item
            session.commit()
        return len(rows), len(fbo_rows)
