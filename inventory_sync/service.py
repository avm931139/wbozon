from __future__ import annotations

import logging
import time
import uuid
import zlib
from datetime import date, datetime, timezone
from typing import Any, Callable

from sqlalchemy import text

from app.db import SessionLocal
from app.config import YANDEX_MARKET_CAMPAIGN_IDS
from app.models import (
    InventorySyncRun,
    OzonStock,
    OzonStockSnapshot,
    OzonWarehouse,
    OzonWarehouseStock,
    OzonWarehouseStockSnapshot,
    WBFboStock,
    WBFboStockSnapshot,
    WBFboWarehouse,
    WBFBSStock,
    WBFBSStockSnapshot,
    WBFBSWarehouse,
    WBProductSize,
    YandexMarketStock,
    YandexMarketStockSnapshot,
)
from ozon.exceptions import OzonError
from ozon.stocks import OzonStocksAPI
from ozon.warehouse_stocks import OzonWarehouseStocksAPI
from wb.fbo_stocks import FBOStocksAPI
from wb.stocks import StocksAPI
from yandex_market.stocks import YandexMarketStocksAPI


logger = logging.getLogger(__name__)
LOCK_ID = 846_203_101
MARKETPLACES = ("all", "wb", "ozon", "yandex_market")


class InventorySyncAlreadyRunning(RuntimeError):
    pass


class InventorySyncService:
    """Fetch and atomically persist complete current inventory and daily slices."""

    def __init__(
        self,
        *,
        marketplace: str = "all",
        wb_fbs_api: StocksAPI | None = None,
        wb_fbo_api: FBOStocksAPI | None = None,
        ozon_api: OzonStocksAPI | None = None,
        ozon_warehouse_api: OzonWarehouseStocksAPI | None = None,
        yandex_market_api: YandexMarketStocksAPI | None = None,
        yandex_market_campaign_ids: tuple[int, ...] | None = None,
        session_factory: Callable[..., Any] = SessionLocal,
        request_pause_seconds: float = 0.21,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if marketplace not in MARKETPLACES:
            raise ValueError(f"marketplace must be one of: {', '.join(MARKETPLACES)}")
        self.marketplace = marketplace
        self.wb_fbs_api = wb_fbs_api or (StocksAPI() if marketplace in {"all", "wb"} else None)
        self.wb_fbo_api = wb_fbo_api or (FBOStocksAPI() if marketplace in {"all", "wb"} else None)
        self.ozon_api = ozon_api or (OzonStocksAPI() if marketplace in {"all", "ozon"} else None)
        self.ozon_warehouse_api = ozon_warehouse_api or (
            OzonWarehouseStocksAPI() if marketplace in {"all", "ozon"} else None
        )
        self.yandex_market_api = yandex_market_api or (
            YandexMarketStocksAPI() if marketplace in {"all", "yandex_market"} else None
        )
        self.yandex_market_campaign_ids = (
            YANDEX_MARKET_CAMPAIGN_IDS
            if yandex_market_campaign_ids is None
            else tuple(yandex_market_campaign_ids)
        )
        self.session_factory = session_factory
        self.request_pause_seconds = request_pause_seconds
        self.sleeper = sleeper

    def refresh(self, *, scheduled_for: datetime | None = None) -> dict[str, int]:
        return self._run("periodic", scheduled_for=scheduled_for)

    def snapshot(self, snapshot_date: date, *, scheduled_for: datetime) -> dict[str, int | bool]:
        if self.snapshot_exists(snapshot_date):
            return {
                "skipped": True,
                "wb_fbs": 0,
                "wb_fbo": 0,
                "ozon": 0,
                "ozon_warehouse": 0,
                "yandex_market": 0,
            }
        return self._run("daily_snapshot", snapshot_date=snapshot_date, scheduled_for=scheduled_for)

    def snapshot_exists(self, snapshot_date: date) -> bool:
        marketplaces = MARKETPLACES if self.marketplace == "all" else (self.marketplace, "all")
        with self.session_factory() as session:
            return (
                session.query(InventorySyncRun.id)
                .filter(
                    InventorySyncRun.marketplace.in_(marketplaces),
                    InventorySyncRun.run_type == "daily_snapshot",
                    InventorySyncRun.snapshot_date == snapshot_date,
                    InventorySyncRun.status == "completed",
                )
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
                raise InventorySyncAlreadyRunning(
                    f"another inventory synchronization overlaps marketplace={self.marketplace}"
                )
            try:
                self._create_run(run_id, run_type, snapshot_date, scheduled_for, started_at)
                wb_fbs: list[dict[str, Any]] = []
                wb_fbo: list[dict[str, Any]] = []
                ozon: list[dict[str, Any]] = []
                ozon_warehouse: list[dict[str, Any]] = []
                ozon_warehouse_metadata: list[dict[str, Any]] = []
                yandex_market: list[dict[str, Any]] | None = None

                if self.marketplace in {"all", "wb"}:
                    assert self.wb_fbo_api is not None
                    wb_fbs = self._fetch_wb_fbs()
                    wb_fbo = self.wb_fbo_api.list()

                if self.marketplace in {"all", "ozon"}:
                    assert self.ozon_api is not None
                    assert self.ozon_warehouse_api is not None
                    ozon = self.ozon_api.list()
                    ozon_skus = self._ozon_skus(ozon)
                    if ozon and not ozon_skus:
                        raise RuntimeError("Ozon aggregate stock response contains no SKU")
                    if ozon_skus:
                        ozon_warehouse.extend(
                            {**row, "_stock_type": "fbo"}
                            for row in self.ozon_warehouse_api.list_fbo(skus=ozon_skus)
                        )
                        ozon_warehouse.extend(
                            {**row, "_stock_type": "fbs"}
                            for row in self.ozon_warehouse_api.list_fbs(skus=ozon_skus)
                        )
                        self._validate_ozon_warehouse_items(ozon, ozon_warehouse)
                        try:
                            ozon_warehouse_metadata = self.ozon_warehouse_api.list_analytics(skus=ozon_skus)
                        except OzonError:
                            logger.warning(
                                "Ozon warehouse metadata enrichment failed; quantities will still be saved",
                                exc_info=True,
                            )

                if self.marketplace in {"all", "yandex_market"}:
                    yandex_market = self._fetch_yandex_market()
                if yandex_market is not None:
                    self._validate_yandex_market_items(yandex_market)
                captured_at = datetime.now(timezone.utc)
                counts = self._persist(
                    wb_fbs,
                    wb_fbo,
                    ozon,
                    ozon_warehouse,
                    ozon_warehouse_metadata,
                    yandex_market,
                    captured_at,
                    snapshot_date,
                    self.marketplace,
                )
                self._finish_run(run_id, "completed", counts=counts)
                return counts
            except Exception as exc:
                self._finish_run(run_id, "failed", error=f"{type(exc).__name__}: {exc}")
                raise
            finally:
                self._release_lock(lock_session)

    def _fetch_wb_fbs(self) -> list[dict[str, Any]]:
        assert self.wb_fbs_api is not None
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

    def _fetch_yandex_market(self) -> list[dict[str, Any]] | None:
        if not self.yandex_market_campaign_ids:
            if self.marketplace == "yandex_market":
                raise RuntimeError("YANDEX_MARKET_CAMPAIGN_IDS is required for the Yandex Market inventory worker")
            return None
        result: list[dict[str, Any]] = []
        assert self.yandex_market_api is not None
        for campaign_id in self.yandex_market_campaign_ids:
            result.extend(self.yandex_market_api.list(campaign_id=campaign_id))
        return result

    def _persist(
        self,
        wb_fbs_items: list[dict[str, Any]],
        wb_fbo_items: list[dict[str, Any]],
        ozon_items: list[dict[str, Any]],
        ozon_warehouse_items: list[dict[str, Any]],
        ozon_warehouse_metadata: list[dict[str, Any]],
        yandex_market_items: list[dict[str, Any]] | None,
        captured_at: datetime,
        snapshot_date: date | None,
        marketplace: str,
    ) -> dict[str, int]:
        counts = {
            "wb_fbs": 0,
            "wb_fbo": 0,
            "ozon": 0,
            "ozon_warehouse": 0,
            "yandex_market": 0,
        }
        with self.session_factory() as session:
            if marketplace in {"all", "wb"}:
                counts["wb_fbs"] = self._persist_wb_fbs(session, wb_fbs_items)
                counts["wb_fbo"] = self._persist_wb_fbo(session, wb_fbo_items)
            if marketplace in {"all", "ozon"}:
                counts["ozon"] = self._persist_ozon(session, ozon_items, captured_at)
                counts["ozon_warehouse"] = self._persist_ozon_warehouses(
                    session,
                    ozon_warehouse_items,
                    ozon_warehouse_metadata,
                    captured_at,
                )
            if marketplace in {"all", "yandex_market"} and yandex_market_items is not None:
                counts["yandex_market"] = self._persist_yandex_market(
                    session, yandex_market_items, captured_at
                )
            session.flush()
            if snapshot_date is not None:
                self._create_snapshots(session, snapshot_date, captured_at, marketplace)
            session.commit()
        return counts

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
    def _persist_ozon_warehouses(
        session: Any,
        items: list[dict[str, Any]],
        metadata_items: list[dict[str, Any]],
        captured_at: datetime,
    ) -> int:
        metadata = {
            int(item["warehouse_id"]): item
            for item in metadata_items
            if item.get("warehouse_id") is not None
        }
        warehouses = {
            int(row.ozon_warehouse_id): row
            for row in session.query(OzonWarehouse).all()
        }

        for item in items:
            external_id = int(item["warehouse_id"])
            row = warehouses.get(external_id)
            if row is None:
                row = OzonWarehouse(
                    ozon_warehouse_id=external_id,
                    stock_types=[],
                    created_at=captured_at,
                    updated_at=captured_at,
                )
                session.add(row)
                warehouses[external_id] = row

            details = metadata.get(external_id, {})
            name = item.get("warehouse_name") or details.get("warehouse_name")
            if name:
                row.name = str(name)
            for field in ("cluster_id", "macrolocal_cluster_id"):
                value = details.get(field)
                if value is not None:
                    setattr(row, field, int(value))
            if details.get("cluster_name"):
                row.cluster_name = str(details["cluster_name"])
            stock_type = str(item["_stock_type"])
            row.stock_types = sorted(set(row.stock_types or []) | {stock_type})
            row.raw_data = details or {
                "warehouse_id": external_id,
                "warehouse_name": item.get("warehouse_name"),
            }
            row.updated_at = captured_at

        session.flush()

        existing = {
            (int(row.product_id), row.warehouse_id, row.stock_type): row
            for row in session.query(OzonWarehouseStock).all()
        }
        retained: set[tuple[int, int, str]] = set()
        for item in items:
            warehouse = warehouses[int(item["warehouse_id"])]
            stock_type = str(item["_stock_type"])
            key = (int(item["product_id"]), warehouse.id, stock_type)
            retained.add(key)
            row = existing.get(key)
            raw_data = {key: value for key, value in item.items() if key != "_stock_type"}
            if row is None:
                row = OzonWarehouseStock(
                    product_id=key[0],
                    warehouse_id=warehouse.id,
                    stock_type=stock_type,
                    raw_data=raw_data,
                    fetched_at=captured_at,
                )
                session.add(row)
                existing[key] = row
            row.offer_id = item.get("offer_id")
            row.sku = int(item["sku"])
            row.present = int(item.get("present") or 0)
            row.reserved = int(item.get("reserved") or 0)
            row.raw_data = raw_data
            row.fetched_at = captured_at

        for key, row in existing.items():
            if key not in retained:
                row.present = 0
                row.reserved = 0
                row.raw_data = {
                    **(row.raw_data or {}),
                    "present": 0,
                    "reserved": 0,
                    "zeroed_by_inventory_sync": True,
                }
                row.fetched_at = captured_at
        return len(retained)

    @staticmethod
    def _persist_yandex_market(
        session: Any,
        items: list[dict[str, Any]],
        captured_at: datetime,
    ) -> int:
        existing = {
            (int(row.campaign_id), int(row.warehouse_id), row.offer_id, row.stock_type): row
            for row in session.query(YandexMarketStock).all()
        }
        retained: set[tuple[int, int, str, str]] = set()
        for item in items:
            campaign_id = int(item["campaignId"])
            warehouse_id = int(item["warehouseId"])
            offer_id = str(item["offerId"])
            source_updated_at = InventorySyncService._parse_source_datetime(item.get("updatedAt"))
            turnover = item.get("turnoverSummary") or {}
            for stock in item.get("stocks") or []:
                if not isinstance(stock, dict):
                    continue
                stock_type = str(stock["type"]).upper()
                key = (campaign_id, warehouse_id, offer_id, stock_type)
                retained.add(key)
                row = existing.get(key)
                if row is None:
                    row = YandexMarketStock(
                        campaign_id=campaign_id,
                        warehouse_id=warehouse_id,
                        offer_id=offer_id,
                        stock_type=stock_type,
                        raw_data=item,
                        fetched_at=captured_at,
                    )
                    session.add(row)
                    existing[key] = row
                row.count = int(stock.get("count") or 0)
                row.turnover = turnover.get("turnover") if isinstance(turnover, dict) else None
                row.turnover_days = turnover.get("turnoverDays") if isinstance(turnover, dict) else None
                row.source_updated_at = source_updated_at
                row.raw_data = item
                row.fetched_at = captured_at

        for key, row in existing.items():
            if key not in retained:
                row.count = 0
                row.raw_data = {
                    **(row.raw_data or {}),
                    "zeroed_by_inventory_sync": True,
                }
                row.fetched_at = captured_at
        return len(retained)

    @staticmethod
    def _create_snapshots(
        session: Any,
        snapshot_date: date,
        captured_at: datetime,
        marketplace: str,
    ) -> None:
        if marketplace in {"all", "wb"}:
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
        if marketplace in {"all", "ozon"}:
            for row in session.query(OzonStock).all():
                session.add(OzonStockSnapshot(
                    snapshot_date=snapshot_date, captured_at=captured_at, product_id=row.product_id,
                    offer_id=row.offer_id, stock_type=row.stock_type, present=row.present,
                    reserved=row.reserved, raw_data=row.raw_data,
                ))
            for row in session.query(OzonWarehouseStock).all():
                session.add(OzonWarehouseStockSnapshot(
                    snapshot_date=snapshot_date,
                    captured_at=captured_at,
                    product_id=row.product_id,
                    offer_id=row.offer_id,
                    sku=row.sku,
                    warehouse_id=row.warehouse_id,
                    stock_type=row.stock_type,
                    present=row.present,
                    reserved=row.reserved,
                    raw_data=row.raw_data,
                ))
        if marketplace in {"all", "yandex_market"}:
            for row in session.query(YandexMarketStock).all():
                session.add(YandexMarketStockSnapshot(
                    snapshot_date=snapshot_date,
                    captured_at=captured_at,
                    campaign_id=row.campaign_id,
                    warehouse_id=row.warehouse_id,
                    offer_id=row.offer_id,
                    stock_type=row.stock_type,
                    count=row.count,
                    turnover=row.turnover,
                    turnover_days=row.turnover_days,
                    source_updated_at=row.source_updated_at,
                    raw_data=row.raw_data,
                ))

    @staticmethod
    def _ozon_skus(items: list[dict[str, Any]]) -> list[int]:
        return list(dict.fromkeys(
            int(stock["sku"])
            for item in items
            for stock in (item.get("stocks") or [])
            if isinstance(stock, dict) and stock.get("sku") is not None
        ))

    @staticmethod
    def _validate_ozon_warehouse_items(
        aggregate_items: list[dict[str, Any]],
        warehouse_items: list[dict[str, Any]],
    ) -> None:
        required = ("sku", "product_id", "warehouse_id")
        seen: set[tuple[int, int, str]] = set()
        actual: dict[tuple[int, str], tuple[int, int]] = {}
        for item in warehouse_items:
            missing = [field for field in required if item.get(field) is None]
            if missing:
                raise RuntimeError(f"Ozon warehouse stock row has no {', '.join(missing)}")
            stock_type = str(item.get("_stock_type") or "")
            identity = (int(item["product_id"]), int(item["warehouse_id"]), stock_type)
            if identity in seen:
                raise RuntimeError(f"duplicate Ozon warehouse stock identity: {identity}")
            seen.add(identity)
            key = (int(item["sku"]), stock_type)
            present, reserved = actual.get(key, (0, 0))
            actual[key] = (
                present + int(item.get("present") or 0),
                reserved + int(item.get("reserved") or 0),
            )

        expected: dict[tuple[int, str], tuple[int, int]] = {}
        for item in aggregate_items:
            for stock in item.get("stocks") or []:
                if not isinstance(stock, dict) or stock.get("sku") is None:
                    continue
                stock_type = str(stock.get("type") or "").lower()
                if stock_type not in {"fbo", "fbs"}:
                    continue
                expected[(int(stock["sku"]), stock_type)] = (
                    int(stock.get("present") or 0),
                    int(stock.get("reserved") or 0),
                )

        mismatches = [
            (key, expected.get(key), actual.get(key))
            for key in sorted(set(expected) | set(actual))
            if expected.get(key) != actual.get(key)
        ]
        if mismatches:
            logger.warning(
                "Ozon aggregate and warehouse stock totals differ for %s keys; "
                "warehouse rows are authoritative because both APIs are realtime. Examples: %s",
                len(mismatches),
                mismatches[:5],
            )

    @staticmethod
    def _validate_yandex_market_items(items: list[dict[str, Any]]) -> None:
        seen: set[tuple[int, int, str, str]] = set()
        for item in items:
            missing = [
                field
                for field in ("campaignId", "warehouseId", "offerId")
                if item.get(field) is None
            ]
            if missing:
                raise RuntimeError(
                    f"Yandex Market stock row has no {', '.join(missing)}"
                )
            stocks = item.get("stocks")
            if not isinstance(stocks, list):
                raise RuntimeError("Yandex Market stock row has no stocks list")
            for stock in stocks:
                if not isinstance(stock, dict) or not stock.get("type"):
                    raise RuntimeError("Yandex Market stock row has an invalid stock type")
                identity = (
                    int(item["campaignId"]),
                    int(item["warehouseId"]),
                    str(item["offerId"]),
                    str(stock["type"]).upper(),
                )
                if identity in seen:
                    raise RuntimeError(
                        f"duplicate Yandex Market stock identity: {identity}"
                    )
                seen.add(identity)

    @staticmethod
    def _parse_source_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise RuntimeError(f"invalid Yandex Market updatedAt: {value}") from exc
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)

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
                id=run_id, marketplace=self.marketplace, run_type=run_type, snapshot_date=snapshot_date,
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
                row.ozon_warehouse_rows = counts["ozon_warehouse"]
                row.yandex_market_rows = counts["yandex_market"]
            session.commit()

    def _acquire_lock(self, session: Any) -> bool:
        bind = session.get_bind()
        if bind.dialect.name != "postgresql":
            return True
        acquired: list[int] = []
        for lock_id in self._lock_ids():
            locked = bool(session.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": lock_id},
            ).scalar())
            if not locked:
                for acquired_id in reversed(acquired):
                    session.execute(
                        text("SELECT pg_advisory_unlock(:lock_id)"),
                        {"lock_id": acquired_id},
                    )
                return False
            acquired.append(lock_id)
        return True

    def _release_lock(self, session: Any) -> None:
        bind = session.get_bind()
        if bind.dialect.name == "postgresql":
            for lock_id in reversed(self._lock_ids()):
                session.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": lock_id},
                )

    def _lock_ids(self) -> tuple[int, ...]:
        marketplace_ids = tuple(
            zlib.crc32(f"wbozon:inventory:{name}".encode("utf-8"))
            for name in MARKETPLACES
            if name != "all"
        )
        if self.marketplace == "all":
            return (LOCK_ID, *marketplace_ids)
        index = MARKETPLACES.index(self.marketplace) - 1
        return (marketplace_ids[index],)
