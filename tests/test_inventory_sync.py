from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
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
    WBProduct,
    WBProductSize,
)
from inventory_sync.scheduler import InventoryScheduler, InventorySyncSettings
from inventory_sync.service import InventorySyncService
from ozon.exceptions import OzonHTTPError


class FBSAPI:
    def list(self, **kwargs):
        return [{"chrtId": 10, "sku": "sku-10", "warehouseId": kwargs["warehouse_id"], "amount": 7}]


class FBOAPI:
    def list(self):
        return [{
            "chrtId": 10,
            "warehouseId": 500,
            "warehouseName": "Коледино",
            "regionName": "Москва",
            "quantity": 8,
            "inWayToClient": 2,
            "inWayFromClient": 1,
        }]


class OzonAPI:
    def list(self):
        return [{
            "product_id": 100,
            "offer_id": "offer-100",
            "stocks": [{"type": "fbo", "sku": 1000, "present": 9, "reserved": 3}],
        }]


class OzonWarehouseAPI:
    def list_fbo(self, *, skus):
        assert skus == [1000]
        return [{
            "product_id": 100,
            "offer_id": "offer-100",
            "sku": 1000,
            "warehouse_id": 700,
            "present": 9,
            "reserved": 3,
        }]

    def list_fbs(self, *, skus):
        assert skus == [1000]
        return []

    def list_analytics(self, *, skus):
        assert skus == [1000]
        return [{
            "sku": 1000,
            "warehouse_id": 700,
            "warehouse_name": "Хоругвино",
            "cluster_id": 77,
            "cluster_name": "Москва",
        }]


class DuplicateOzonWarehouseAPI(OzonWarehouseAPI):
    def list_fbo(self, *, skus):
        row = super().list_fbo(skus=skus)[0]
        return [row, dict(row)]


class MetadataFailureOzonWarehouseAPI(OzonWarehouseAPI):
    def list_analytics(self, *, skus):
        raise OzonHTTPError("temporary analytics failure")


@pytest.fixture
def inventory_db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    with session_factory() as session:
        product = WBProduct(nm_id=1)
        session.add(product)
        session.flush()
        current_size = WBProductSize(product_id=product.id, chrt_id=10)
        missing_size = WBProductSize(product_id=product.id, chrt_id=20)
        fbs_warehouse = WBFBSWarehouse(wb_id=50, name="Seller")
        fbo_warehouse = WBFboWarehouse(wb_id=500, name="Коледино", region_name="Москва")
        session.add_all([current_size, missing_size, fbs_warehouse, fbo_warehouse])
        session.flush()
        old_ozon_warehouse = OzonWarehouse(
            ozon_warehouse_id=900,
            name="Old Ozon warehouse",
            stock_types=["fbo"],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(old_ozon_warehouse)
        session.flush()
        session.add_all([
            WBFBSStock(size_id=missing_size.id, warehouse_id=fbs_warehouse.id, sku="old-fbs", quantity=5),
            WBFboStock(size_id=missing_size.id, warehouse_id=fbo_warehouse.id, quantity=6, in_way_to_client=4, in_way_from_client=2),
            OzonStock(product_id=200, offer_id="old", stock_type="fbo", present=11, reserved=1, raw_data={}, fetched_at=datetime.now(timezone.utc)),
            OzonWarehouseStock(
                product_id=200,
                offer_id="old",
                sku=2000,
                warehouse_id=old_ozon_warehouse.id,
                stock_type="fbo",
                present=11,
                reserved=1,
                raw_data={},
                fetched_at=datetime.now(timezone.utc),
            ),
        ])
        session.commit()
    return session_factory


def test_daily_snapshot_updates_current_rows_and_zeroes_missing_inventory(inventory_db):
    service = InventorySyncService(
        wb_fbs_api=FBSAPI(), wb_fbo_api=FBOAPI(), ozon_api=OzonAPI(),
        ozon_warehouse_api=OzonWarehouseAPI(),
        session_factory=inventory_db, request_pause_seconds=0, sleeper=lambda value: None,
    )
    snapshot_day = date(2026, 8, 16)
    scheduled_for = datetime(2026, 8, 16, 1, tzinfo=ZoneInfo("Europe/Moscow"))

    result = service.snapshot(snapshot_day, scheduled_for=scheduled_for)

    assert result == {"wb_fbs": 1, "wb_fbo": 1, "ozon": 1, "ozon_warehouse": 1}
    with inventory_db() as session:
        assert session.query(WBFBSStock).filter_by(sku="sku-10").one().quantity == 7
        assert session.query(WBFBSStock).filter_by(sku="old-fbs").one().quantity == 0
        assert session.query(WBFboStock).filter_by(size_id=2).one().quantity == 0
        assert session.query(OzonStock).filter_by(product_id=200).one().present == 0
        assert session.query(OzonWarehouseStock).filter_by(product_id=200).one().present == 0
        warehouse = session.query(OzonWarehouse).filter_by(ozon_warehouse_id=700).one()
        assert warehouse.name == "Хоругвино"
        assert warehouse.cluster_name == "Москва"
        assert session.query(OzonWarehouseStock).filter_by(product_id=100).one().warehouse_id == warehouse.id
        assert session.query(WBFBSStockSnapshot).filter_by(snapshot_date=snapshot_day).count() == 2
        assert session.query(WBFboStockSnapshot).filter_by(snapshot_date=snapshot_day).count() == 2
        assert session.query(OzonStockSnapshot).filter_by(snapshot_date=snapshot_day).count() == 2
        assert session.query(OzonWarehouseStockSnapshot).filter_by(snapshot_date=snapshot_day).count() == 2
        run = session.query(InventorySyncRun).filter_by(snapshot_date=snapshot_day).one()
        assert run.status == "completed"
        assert run.ozon_warehouse_rows == 1

    assert service.snapshot(snapshot_day, scheduled_for=scheduled_for)["skipped"] is True


def test_duplicate_ozon_warehouse_rows_fail_before_inventory_is_changed(inventory_db):
    service = InventorySyncService(
        wb_fbs_api=FBSAPI(),
        wb_fbo_api=FBOAPI(),
        ozon_api=OzonAPI(),
        ozon_warehouse_api=DuplicateOzonWarehouseAPI(),
        session_factory=inventory_db,
        request_pause_seconds=0,
        sleeper=lambda value: None,
    )

    with pytest.raises(RuntimeError, match="duplicate Ozon warehouse stock identity"):
        service.refresh()

    with inventory_db() as session:
        assert session.query(OzonStock).filter_by(product_id=200).one().present == 11
        assert session.query(OzonWarehouseStock).filter_by(product_id=200).one().present == 11
        assert session.query(InventorySyncRun).filter_by(status="failed").count() == 1


def test_analytics_metadata_failure_does_not_block_stock_quantities(inventory_db):
    service = InventorySyncService(
        wb_fbs_api=FBSAPI(),
        wb_fbo_api=FBOAPI(),
        ozon_api=OzonAPI(),
        ozon_warehouse_api=MetadataFailureOzonWarehouseAPI(),
        session_factory=inventory_db,
        request_pause_seconds=0,
        sleeper=lambda value: None,
    )

    assert service.refresh()["ozon_warehouse"] == 1
    with inventory_db() as session:
        row = session.query(OzonWarehouseStock).filter_by(product_id=100).one()
        assert (row.present, row.reserved) == (9, 3)


class RecordingInventoryService:
    def __init__(self, existing=False):
        self.existing = existing
        self.calls = []

    def snapshot_exists(self, snapshot_date):
        return self.existing

    def snapshot(self, snapshot_date, *, scheduled_for):
        self.calls.append(("snapshot", snapshot_date, scheduled_for))
        self.existing = True
        return {"ok": True}

    def refresh(self, *, scheduled_for=None):
        self.calls.append(("refresh", scheduled_for))
        return {"ok": True}


def test_scheduler_uses_moscow_time_even_when_server_clock_is_utc():
    service = RecordingInventoryService()
    scheduler = InventoryScheduler(
        service,
        settings=InventorySyncSettings(
            interval_seconds=3600,
            snapshot_time=time(1, 0),
            timezone_name="Europe/Moscow",
            run_on_start=True,
        ),
    )

    scheduler.run_pending(datetime(2026, 8, 15, 22, 0, tzinfo=timezone.utc))

    assert [call[0] for call in service.calls] == ["snapshot"]
    assert service.calls[0][1] == date(2026, 8, 16)
    assert service.calls[0][2].hour == 1
    assert service.calls[0][2].tzinfo == ZoneInfo("Europe/Moscow")


def test_scheduler_creates_catch_up_snapshot_after_midnight():
    service = RecordingInventoryService()
    scheduler = InventoryScheduler(service, settings=InventorySyncSettings(run_on_start=False))

    scheduler.run_pending(datetime(2026, 8, 16, 4, 30, tzinfo=ZoneInfo("Europe/Moscow")))

    assert [call[0] for call in service.calls] == ["snapshot"]


def test_scheduler_retries_failed_snapshot_on_next_interval():
    class FlakySnapshotService(RecordingInventoryService):
        def snapshot(self, snapshot_date, *, scheduled_for):
            self.calls.append(("snapshot", snapshot_date, scheduled_for))
            if len(self.calls) == 1:
                raise RuntimeError("temporary API failure")
            self.existing = True
            return {"ok": True}

    service = FlakySnapshotService()
    scheduler = InventoryScheduler(
        service,
        settings=InventorySyncSettings(
            interval_seconds=3600,
            snapshot_time=time(0, 0),
            timezone_name="Europe/Moscow",
            run_on_start=False,
        ),
    )
    with pytest.raises(RuntimeError, match="temporary API failure"):
        scheduler.run_pending(datetime(2026, 8, 20, 0, 0, tzinfo=ZoneInfo("Europe/Moscow")))

    scheduler.run_pending(datetime(2026, 8, 20, 1, 0, tzinfo=ZoneInfo("Europe/Moscow")))

    assert [call[0] for call in service.calls] == ["snapshot", "snapshot"]
    assert service.existing is True


@pytest.mark.parametrize("interval", [0, -1])
def test_inventory_scheduler_rejects_invalid_interval(interval):
    with pytest.raises(ValueError):
        InventorySyncSettings(interval_seconds=interval)


@pytest.mark.parametrize("retry_seconds", [0, -1])
def test_inventory_scheduler_rejects_invalid_snapshot_retry(retry_seconds):
    with pytest.raises(ValueError):
        InventorySyncSettings(snapshot_retry_seconds=retry_seconds)
