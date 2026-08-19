import time
from datetime import date, datetime
from typing import Any

from app.db import SessionLocal
from app.models import (
    WBFbwSupply,
    WBFbwSupplyGood,
    WBFbwSupplyPackage,
    WBFbwSupplyPackageGood,
    WBFbwSupplySnapshot,
    WBFbwWarehouse,
    WBProduct,
    WBProductSize,
    WBSizeBarcode,
)
from wb.fbw_supplies import FBWSuppliesAPI


def _dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class FBWSupplyService:
    REQUEST_INTERVAL = 6.1

    def __init__(self):
        self.api = FBWSuppliesAPI()

    def sync_max_history(self) -> dict[str, int]:
        warehouse_rows = self.api.warehouses()
        self._persist_warehouses(warehouse_rows)
        supply_rows = self.api.supplies(date(2019, 1, 1), date.today())
        changed = self._persist_supply_list(supply_rows)
        goods_count = package_count = 0
        for supply_id in changed:
            with SessionLocal() as session:
                supply = session.get(WBFbwSupply, supply_id)
                identifier = supply.supply_wb_id or supply.preorder_wb_id
                is_preorder = supply.supply_wb_id is None
                box_type_id = supply.box_type_id
            time.sleep(self.REQUEST_INTERVAL)
            details = self.api.details(int(identifier), is_preorder)
            time.sleep(self.REQUEST_INTERVAL)
            goods = self.api.goods(int(identifier), is_preorder)
            packages: list[dict[str, Any]] = []
            if not is_preorder and box_type_id in (1, 2, 5, 6):
                time.sleep(self.REQUEST_INTERVAL)
                packages = self.api.packages(int(identifier))
            self._persist_details(supply_id, details, goods, packages)
            goods_count += len(goods)
            package_count += len(packages)
        return {"warehouses": len(warehouse_rows), "supplies": len(supply_rows), "changed": len(changed), "goods": goods_count, "packages": package_count}

    @staticmethod
    def _persist_warehouses(rows: list[dict[str, Any]]) -> None:
        with SessionLocal() as session:
            existing = {x.wb_id: x for x in session.query(WBFbwWarehouse).all()}
            for item in rows:
                wb_id = int(item["ID"])
                warehouse = existing.get(wb_id) or WBFbwWarehouse(wb_id=wb_id, name=str(item.get("name") or wb_id), raw_data=item)
                session.add(warehouse)
                warehouse.name = str(item.get("name") or wb_id); warehouse.address = item.get("address"); warehouse.work_time = item.get("workTime")
                warehouse.is_active = bool(item.get("isActive")); warehouse.is_transit_active = bool(item.get("isTransitActive")); warehouse.raw_data = item
            session.commit()

    @staticmethod
    def _persist_supply_list(rows: list[dict[str, Any]]) -> list[int]:
        changed: list[int] = []
        with SessionLocal() as session:
            for item in rows:
                supply_wb_id = int(item["supplyID"]) if item.get("supplyID") else None
                preorder_wb_id = int(item["preorderID"]) if item.get("preorderID") else None
                supply = None
                if supply_wb_id is not None:
                    supply = session.query(WBFbwSupply).filter_by(supply_wb_id=supply_wb_id).first()
                if supply is None and preorder_wb_id is not None:
                    supply = session.query(WBFbwSupply).filter_by(preorder_wb_id=preorder_wb_id).first()
                incoming_updated = _dt(item.get("updatedDate"))
                if supply is None:
                    supply = WBFbwSupply(preorder_wb_id=preorder_wb_id, create_date=_dt(item.get("createDate")), status_id=int(item.get("statusID") or 0), raw_data=item)
                    session.add(supply); session.flush(); changed.append(supply.id)
                elif supply.source_updated_date != incoming_updated or not (supply.raw_data or {}).get("_fbw_sync_complete"):
                    changed.append(supply.id)
                supply.supply_wb_id = supply_wb_id; supply.preorder_wb_id = preorder_wb_id
                supply.status_id = int(item.get("statusID") or 0); supply.box_type_id = item.get("boxTypeID"); supply.is_box_on_pallet = item.get("isBoxOnPallet")
                supply.create_date = _dt(item.get("createDate")); supply.supply_date = _dt(item.get("supplyDate")); supply.fact_date = _dt(item.get("factDate")); supply.source_updated_date = incoming_updated
                supply.raw_data = item
            session.commit()
        return changed

    @staticmethod
    def _persist_details(supply_id: int, details: dict[str, Any], goods: list[dict[str, Any]], packages: list[dict[str, Any]]) -> None:
        with SessionLocal() as session:
            supply = session.get(WBFbwSupply, supply_id)
            products = {x.nm_id: x for x in session.query(WBProduct).all()}
            barcode_sizes = {x.barcode: x.size for x in session.query(WBSizeBarcode).all()}
            supply.status_id = int(details.get("statusID") or supply.status_id); supply.box_type_id = details.get("boxTypeID"); supply.virtual_type_id = details.get("virtualTypeID")
            supply.is_box_on_pallet = details.get("isBoxOnPallet"); supply.warehouse_wb_id = details.get("warehouseID"); supply.warehouse_name = details.get("warehouseName")
            supply.actual_warehouse_wb_id = details.get("actualWarehouseID"); supply.actual_warehouse_name = details.get("actualWarehouseName")
            supply.transit_warehouse_wb_id = details.get("transitWarehouseID"); supply.transit_warehouse_name = details.get("transitWarehouseName")
            supply.acceptance_cost = details.get("acceptanceCost"); supply.paid_acceptance_coefficient = details.get("paidAcceptanceCoefficient")
            supply.storage_coefficient = details.get("storageCoef"); supply.delivery_coefficient = details.get("deliveryCoef")
            supply.reject_reason = details.get("rejectReason"); supply.supplier_assign_name = details.get("supplierAssignName")
            for field, key in (("quantity", "quantity"), ("accepted_quantity", "acceptedQuantity"), ("ready_for_sale_quantity", "readyForSaleQuantity"), ("unloading_quantity", "unloadingQuantity"), ("depersonalized_quantity", "depersonalizedQuantity")):
                setattr(supply, field, details.get(key))
            supply.can_show_quantity = details.get("canShowQuantity"); supply.raw_data = {**supply.raw_data, "details": details}
            source_updated = _dt(details.get("updatedDate")) or supply.source_updated_date or supply.create_date
            supply.source_updated_date = source_updated

            existing_goods = {x.barcode: x for x in supply.goods}; retained_goods: set[str] = set()
            for item in goods:
                barcode = str(item.get("barcode") or "")
                if not barcode: continue
                row = existing_goods.get(barcode)
                if row is None:
                    row = WBFbwSupplyGood(supply=supply, barcode=barcode, nm_id=int(item.get("nmID") or 0), raw_data=item)
                    session.add(row)
                retained_goods.add(barcode)
                nm_id = int(item.get("nmID") or 0); size = barcode_sizes.get(barcode)
                row.nm_id = nm_id; row.product_id = products.get(nm_id).id if nm_id in products else None; row.size_id = size.id if size else None
                row.vendor_code = item.get("vendorCode"); row.tech_size = item.get("techSize"); row.color = item.get("color"); row.tnved = item.get("tnved"); row.need_kiz = bool(item.get("needKiz"))
                row.supplier_box_amount = item.get("supplierBoxAmount"); row.quantity = int(item.get("quantity") or 0); row.accepted_quantity = int(item.get("acceptedQuantity") or 0)
                row.ready_for_sale_quantity = int(item.get("readyForSaleQuantity") or 0); row.unloading_quantity = int(item.get("unloadingQuantity") or 0); row.raw_data = item
            for barcode, row in existing_goods.items():
                if barcode not in retained_goods: supply.goods.remove(row)

            existing_packages = {x.package_code: x for x in supply.packages}; retained_packages: set[str] = set()
            for item in packages:
                code = str(item.get("packageCode") or "")
                if not code: continue
                package = existing_packages.get(code)
                if package is None:
                    package = WBFbwSupplyPackage(supply=supply, package_code=code, raw_data=item)
                    session.add(package)
                retained_packages.add(code)
                package.quantity = int(item.get("quantity") or 0); package.raw_data = item
                package_goods = {x.barcode: x for x in package.goods}; retained_barcodes: set[str] = set()
                for value in item.get("barcodes") or []:
                    barcode = str(value.get("barcode") or "")
                    if not barcode: continue
                    row = package_goods.get(barcode)
                    if row is None:
                        row = WBFbwSupplyPackageGood(package=package, barcode=barcode)
                        session.add(row)
                    retained_barcodes.add(barcode)
                    row.quantity = int(value.get("quantity") or 0)
                for barcode, row in package_goods.items():
                    if barcode not in retained_barcodes: package.goods.remove(row)
            for code, row in existing_packages.items():
                if code not in retained_packages: supply.packages.remove(row)

            snapshot = session.query(WBFbwSupplySnapshot).filter_by(supply_id=supply.id, source_updated_date=source_updated).first()
            if snapshot is None:
                snapshot = WBFbwSupplySnapshot(supply=supply, source_updated_date=source_updated, status_id=supply.status_id, raw_data=details)
                session.add(snapshot)
            snapshot.quantity = supply.quantity; snapshot.accepted_quantity = supply.accepted_quantity; snapshot.ready_for_sale_quantity = supply.ready_for_sale_quantity
            snapshot.unloading_quantity = supply.unloading_quantity; snapshot.depersonalized_quantity = supply.depersonalized_quantity
            supply.raw_data = {**supply.raw_data, "_fbw_sync_complete": True}
            session.commit()
