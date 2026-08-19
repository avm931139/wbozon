from __future__ import annotations

import logging
import time
import uuid
from datetime import date, datetime, timezone
from typing import Any, Callable

from sqlalchemy import text

from app.db import SessionLocal
from app.models import (
    InventorySyncRun,
    OzonStock,
    OzonStockSnapshot,
    WBFboStock,
    WBFboStockSnapshot,
    WBFboWarehouse,
    WBFBSStock,
    WBFBSStockSnapshot,
    WBFBSWarehouse,
    WBProductSize,
)
from ozon.stocks import OzonStocksAPI
from wb.fbo_stocks import FBOStocksAPI
from wb.stocks import StocksAPI


logger = logging.getLogger(__name__)
LOCK_ID = 846_203_101


class InventorySyncAlreadyRunning(RuntimeError):
    pass


class InventorySyncService:
    """Fetch and atomically persist complete current inventory and daily slices."""

    def __init__(
        self,
        *,
        wb_fbs_api: StocksAPI | None = None,
        wb_fbo_api: FBOStocksAPI | None = None,
        ozon_api: OzonStocksAPI | None = None,
        session_factory: Callable[..., Any] = SessionLocal,
        request_pause_seconds: float = 0.21,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.wb_fbs_api = wb_fbs_api or StocksAPI()
        self.wb_fbo_api = wb_fbo_api or FBOStocksAPI()
        self.ozon_api = ozon_api or OzonStocksAPI()
        self.session_factory = session_factory
        self.request_pause_seconds = request_pause_seconds
        self.sleeper = sleeper

    def refresh(self, *, scheduled_for: datetime | None = None) -> dict[str, int]:
        return self._run("periodic", scheduled_for=scheduled_for)

    def snapshot(self, snapshot_date: date, *, scheduled_for: datetime) -> dict[str, int | bool]:
        if self.snapshot_exists(snapshot_date):
            return {"skipped": True, "wb_fbs": 0, "wb_fbo": 0, "ozon": 0}
        return self._run("daily_snapshot", snapshot_date=snapshot_date, scheduled_for=scheduled_for)

    def snapshot_exists(self, snapshot_date: date) -> bool:
        with self.session_factory() as session:
            return (
                session.query(InventorySyncRun.id)
                .filter_by(run_type="daily_snapshot", snapshot_date=snapshot_date, status="completed")
                .first()
                is not None
            )

    def _run(
        self,
        run_type: str,
        *,
        snapshot_date: date | None = None,
        scheduled_for: datetime | None = None,
    ) -> dict[str, int]:
        run_id = uuid.uuid4().hex
        started_at = datetime.now(timezone.utc)
        with self.session_factory() as lock_session:
            if not self._acquire_lock(lock_session):
                raise InventorySyncAlreadyRunning("another inventory synchronization is already running")
            try:
                self._create_run(run_id, run_type, snapshot_date, scheduled_for, started_at)
                wb_fbs = self._fetch_wb_fbs()
                wb_fbo = self.wb_fbo_api.list()
                ozon = self.ozon_api.list()
                captured_at = datetime.now(timezone.utc)
                counts = self._persist(wb_fbs, wb_fbo, ozon, captured_at, snapshot_date)
                self._finish_run(run_id, "completed", counts=counts)
                return counts
            except Exception as exc:
                self._finish_run(run_id, "failed", error=f"{type(exc).__name__}: {exc}")
                raise
            finally:
                self._release_lock(lock_session)

    def _fetch_wb_fbs(self) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            warehouse_ids = [int(row[0]) for row in session.query(WBFBSWarehouse.wb_id).all()]
            chrt_ids = [int(row[0]) for row in session.query(WBProductSize.chrt_id).all()]
        if not warehouse_ids:
            raise RuntimeError("WB FBS warehouses are not loaded")
        if not chrt_ids:
            raise RuntimeError("WB product sizes are not loaded")

        result: list[dict[str, Any]] = []
        request_number = 0
        for warehouse_id in warehouse_ids:
            for offset in range(0, len(chrt_ids), 1000):
                if request_number:
                    self.sleeper(self.request_pause_seconds)
                result.extend(
                    self.wb_fbs_api.list(
                        warehouse_id=warehouse_id,
                        chrt_ids=chrt_ids[offset : offset + 1000],
                    )
                )
                request_number += 1
        return result

    def _persist(
        self,
        wb_fbs_items: list[dict[str, Any]],
        wb_fbo_items: list[dict[str, Any]],
        ozon_items: list[dict[str, Any]],
        captured_at: datetime,
        snapshot_date: date | None,
    ) -> dict[str, int]:
        with self.session_factory() as session:
            fbs_count = self._persist_wb_fbs(session, wb_fbs_items)
            fbo_count = self._persist_wb_fbo(session, wb_fbo_items)
            ozon_count = self._persist_ozon(session, ozon_items, captured_at)
            session.flush()
            if snapshot_date is not None:
                self._create_snapshots(session, snapshot_date, captured_at)
            session.commit()
        return {"wb_fbs": fbs_count, "wb_fbo": fbo_count, "ozon": ozon_count}

    @staticmethod
    def _persist_wb_fbs(session: Any, items: list[dict[str, Any]]) -> int:
        sizes = {int(row.chrt_id): row for row in session.query(WBProductSize).all()}
        warehouses = {int(row.wb_id): row for row in session.query(WBFBSWarehouse).all()}
        existing = {(row.sku, row.warehouse_id): row for row in session.query(WBFBSStock).all()}
        retained: set[tuple[str, int]] = set()

        for item in items:
            chrt_id = item.get("chrtId") or item.get("chrtID")
            sku = item.get("sku")
            warehouse_wb_id = item.get("warehouseId")
            if chrt_id is None or sku is None or warehouse_wb_id is None:
                continue
            size = sizes.get(int(chrt_id))
            warehouse = warehouses.get(int(warehouse_wb_id))
            if size is None or warehouse is None:
                continue
            key = (str(sku), warehouse.id)
            retained.add(key)
            row = existing.get(key)
            if row is None:
                row = WBFBSStock(size_id=size.id, warehouse_id=warehouse.id, sku=str(sku))
                session.add(row)
                existing[key] = row
            row.size_id = size.id
            row.quantity = int(item.get("amount", item.get("quantity", item.get("stock", 0))) or 0)
            row.raw_data = item

        for key, row in existing.items():
            if key not in retained:
                row.quantity = 0
                row.raw_data = {**(row.raw_data or {}), "amount": 0, "zeroed_by_inventory_sync": True}
        return len(retained)

    @staticmethod
    def _persist_wb_fbo(session: Any, items: list[dict[str, Any]]) -> int:
        sizes = {int(row.chrt_id): row for row in session.query(WBProductSize).all()}
        warehouses = {
            (int(row.wb_id), row.name, row.region_name): row
            for row in session.query(WBFboWarehouse).all()
        }
        for item in items:
            key = InventorySyncService._fbo_warehouse_key(item)
            if item.get("warehouseId") is not None and key not in warehouses:
                warehouse = WBFboWarehouse(wb_id=key[0], name=key[1], region_name=key[2])
                session.add(warehouse)
                warehouses[key] = warehouse
        session.flush()

        existing = {(row.size_id, row.warehouse_id): row for row in session.query(WBFboStock).all()}
        retained: set[tuple[int, int]] = set()
        for item in items:
            chrt_id = item.get("chrtId")
            if chrt_id is None:
                continue
            size = sizes.get(int(chrt_id))
            warehouse = warehouses.get(InventorySyncService._fbo_warehouse_key(item))
            if size is None or warehouse is None:
                continue
            key = (size.id, warehouse.id)
            retained.add(key)
            row = existing.get(key)
            if row is None:
                row = WBFboStock(size_id=size.id, warehouse_id=warehouse.id)
                session.add(row)
                existing[key] = row
            row.quantity = int(item.get("quantity") or 0)
            row.in_way_to_client = int(item.get("inWayToClient") or 0)
            row.in_way_from_client = int(item.get("inWayFromClient") or 0)
            row.raw_data = item

        for key, row in existing.items():
            if key not in retained:
                row.quantity = 0
                row.in_way_to_client = 0
                row.in_way_from_client = 0
                row.raw_data = {
                    **(row.raw_data or {}),
                    "quantity": 0,
                    "inWayToClient": 0,
                    "inWayFromClient": 0,
                    "zeroed_by_inventory_sync": True,
                }
        return len(retained)

    @staticmethod
    def _persist_ozon(session: Any, items: list[dict[str, Any]], captured_at: datetime) -> int:
        existing = {(int(row.product_id), row.stock_type): row for row in session.query(OzonStock).all()}
        retained: set[tuple[int, str]] = set()
        for item in items:
            product_id = item.get("product_id")
            if product_id is None:
                continue
            for stock in item.get("stocks") or []:
                if not isinstance(stock, dict):
                    continue
                stock_type = str(stock.get("type") or "unknown").lower()
                key = (int(product_id), stock_type)
                retained.add(key)
                row = existing.get(key)
                if row is None:
                    row = OzonStock(product_id=key[0], stock_type=key[1], raw_data=stock, fetched_at=captured_at)
                    session.add(row)
                    existing[key] = row
                row.offer_id = item.get("offer_id")
                row.present = int(stock.get("present") or 0)
                row.reserved = int(stock.get("reserved") or 0)
                row.raw_data = stock
                row.fetched_at = captured_at

        for key, row in existing.items():
            if key not in retained:
                row.present = 0
                row.reserved = 0
                row.raw_data = {**(row.raw_data or {}), "present": 0, "reserved": 0, "zeroed_by_inventory_sync": True}
                row.fetched_at = captured_at
        return len(retained)

    @staticmethod
    def _create_snapshots(session: Any, snapshot_date: date, captured_at: datetime) -> None:
        for row in session.query(WBFBSStock).all():
            session.add(WBFBSStockSnapshot(
                snapshot_date=snapshot_date, captured_at=captured_at, size_id=row.size_id,
                warehouse_id=row.warehouse_id, sku=row.sku, quantity=row.quantity, raw_data=row.raw_data,
            ))
        for row in session.query(WBFboStock).all():
            session.add(WBFboStockSnapshot(
                snapshot_date=snapshot_date, captured_at=captured_at, size_id=row.size_id,
                warehouse_id=row.warehouse_id, quantity=row.quantity,
                in_way_to_client=row.in_way_to_client, in_way_from_client=row.in_way_from_client,
                raw_data=row.raw_data,
            ))
        for row in session.query(OzonStock).all():
            session.add(OzonStockSnapshot(
                snapshot_date=snapshot_date, captured_at=captured_at, product_id=row.product_id,
                offer_id=row.offer_id, stock_type=row.stock_type, present=row.present,
                reserved=row.reserved, raw_data=row.raw_data,
            ))

    @staticmethod
    def _fbo_warehouse_key(item: dict[str, Any]) -> tuple[int, str, str]:
        return (
            int(item.get("warehouseId") or 0),
            str(item.get("warehouseName") or ""),
            str(item.get("regionName") or ""),
        )

    def _create_run(
        self,
        run_id: str,
        run_type: str,
        snapshot_date: date | None,
        scheduled_for: datetime | None,
        started_at: datetime,
    ) -> None:
        with self.session_factory() as session:
            session.add(InventorySyncRun(
                id=run_id, run_type=run_type, snapshot_date=snapshot_date,
                scheduled_for=scheduled_for, started_at=started_at, status="running",
            ))
            session.commit()

    def _finish_run(
        self,
        run_id: str,
        status: str,
        *,
        counts: dict[str, int] | None = None,
        error: str | None = None,
    ) -> None:
        with self.session_factory() as session:
            row = session.get(InventorySyncRun, run_id)
            if row is None:
                return
            row.status = status
            row.finished_at = datetime.now(timezone.utc)
            row.error = error
            if counts:
                row.wb_fbs_rows = counts["wb_fbs"]
                row.wb_fbo_rows = counts["wb_fbo"]
                row.ozon_rows = counts["ozon"]
            session.commit()

    @staticmethod
    def _acquire_lock(session: Any) -> bool:
        bind = session.get_bind()
        if bind.dialect.name != "postgresql":
            return True
        return bool(session.execute(text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": LOCK_ID}).scalar())

    @staticmethod
    def _release_lock(session: Any) -> None:
        bind = session.get_bind()
        if bind.dialect.name == "postgresql":
            session.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": LOCK_ID})
