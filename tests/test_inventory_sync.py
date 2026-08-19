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
        return [{"product_id": 100, "offer_id": "offer-100", "stocks": [{"type": "fbo", "present": 9, "reserved": 3}]}]


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
        session.add_all([
            WBFBSStock(size_id=missing_size.id, warehouse_id=fbs_warehouse.id, sku="old-fbs", quantity=5),
            WBFboStock(size_id=missing_size.id, warehouse_id=fbo_warehouse.id, quantity=6, in_way_to_client=4, in_way_from_client=2),
            OzonStock(product_id=200, offer_id="old", stock_type="fbo", present=11, reserved=1, raw_data={}, fetched_at=datetime.now(timezone.utc)),
        ])
        session.commit()
    return session_factory


def test_daily_snapshot_updates_current_rows_and_zeroes_missing_inventory(inventory_db):
    service = InventorySyncService(
        wb_fbs_api=FBSAPI(), wb_fbo_api=FBOAPI(), ozon_api=OzonAPI(),
        session_factory=inventory_db, request_pause_seconds=0, sleeper=lambda value: None,
    )
    snapshot_day = date(2026, 8, 16)
    scheduled_for = datetime(2026, 8, 16, 1, tzinfo=ZoneInfo("Europe/Moscow"))

    result = service.snapshot(snapshot_day, scheduled_for=scheduled_for)

    assert result == {"wb_fbs": 1, "wb_fbo": 1, "ozon": 1}
    with inventory_db() as session:
        assert session.query(WBFBSStock).filter_by(sku="sku-10").one().quantity == 7
        assert session.query(WBFBSStock).filter_by(sku="old-fbs").one().quantity == 0
        assert session.query(WBFboStock).filter_by(size_id=2).one().quantity == 0
        assert session.query(OzonStock).filter_by(product_id=200).one().present == 0
        assert session.query(WBFBSStockSnapshot).filter_by(snapshot_date=snapshot_day).count() == 2
        assert session.query(WBFboStockSnapshot).filter_by(snapshot_date=snapshot_day).count() == 2
        assert session.query(OzonStockSnapshot).filter_by(snapshot_date=snapshot_day).count() == 2
        run = session.query(InventorySyncRun).filter_by(snapshot_date=snapshot_day).one()
        assert run.status == "completed"

    assert service.snapshot(snapshot_day, scheduled_for=scheduled_for)["skipped"] is True


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


def test_scheduler_creates_catch_up_snapshot_after_one_am():
    service = RecordingInventoryService()
    scheduler = InventoryScheduler(service, settings=InventorySyncSettings(run_on_start=False))

    scheduler.run_pending(datetime(2026, 8, 16, 4, 30, tzinfo=ZoneInfo("Europe/Moscow")))

    assert [call[0] for call in service.calls] == ["snapshot"]


@pytest.mark.parametrize("interval", [0, -1])
def test_inventory_scheduler_rejects_invalid_interval(interval):
    with pytest.raises(ValueError):
        InventorySyncSettings(interval_seconds=interval)
