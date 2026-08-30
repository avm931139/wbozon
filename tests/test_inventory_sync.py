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
    YandexMarketStock,
    YandexMarketStockSnapshot,
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


class YandexMarketAPI:
    def __init__(self):
        self.rows = [{
            "campaignId": 300,
            "warehouseId": 800,
            "offerId": "market-sku-1",
            "stocks": [
                {"type": "AVAILABLE", "count": 12},
                {"type": "FREEZE", "count": 2},
            ],
            "updatedAt": "2026-08-30T12:00:00Z",
        }]

    def list(self, *, campaign_id):
        assert campaign_id == 300
        return self.rows


class DuplicateOzonWarehouseAPI(OzonWarehouseAPI):
    def list_fbo(self, *, skus):
        row = super().list_fbo(skus=skus)[0]
        return [row, dict(row)]


class MetadataFailureOzonWarehouseAPI(OzonWarehouseAPI):
    def list_analytics(self, *, skus):
        raise OzonHTTPError("temporary analytics failure")


class UnexpectedAPI:
    def list(self, **kwargs):
        raise AssertionError("unrelated marketplace API must not be called")


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

    assert result == {
        "wb_fbs": 1,
        "wb_fbo": 1,
        "ozon": 1,
        "ozon_warehouse": 1,
        "yandex_market": 0,
    }
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


def test_yandex_market_inventory_is_stored_snapshotted_and_zeroed(inventory_db):
    api = YandexMarketAPI()
    service = InventorySyncService(
        wb_fbs_api=FBSAPI(),
        wb_fbo_api=FBOAPI(),
        ozon_api=OzonAPI(),
        ozon_warehouse_api=OzonWarehouseAPI(),
        yandex_market_api=api,
        yandex_market_campaign_ids=(300,),
        session_factory=inventory_db,
        request_pause_seconds=0,
        sleeper=lambda value: None,
    )
    snapshot_day = date(2026, 8, 30)

    result = service.snapshot(
        snapshot_day,
        scheduled_for=datetime(2026, 8, 30, 0, 0, tzinfo=ZoneInfo("Europe/Moscow")),
    )

    assert result["yandex_market"] == 2
    with inventory_db() as session:
        available = session.query(YandexMarketStock).filter_by(stock_type="AVAILABLE").one()
        assert available.count == 12
        assert available.source_updated_at.replace(tzinfo=timezone.utc) == datetime(
            2026, 8, 30, 12, 0, tzinfo=timezone.utc
        )
        assert session.query(YandexMarketStockSnapshot).filter_by(snapshot_date=snapshot_day).count() == 2
        run = session.query(InventorySyncRun).filter_by(snapshot_date=snapshot_day).one()
        assert run.yandex_market_rows == 2

    api.rows = []
    assert service.refresh()["yandex_market"] == 0
    with inventory_db() as session:
        assert {row.count for row in session.query(YandexMarketStock).all()} == {0}


def test_marketplace_worker_does_not_call_or_change_other_marketplaces(inventory_db):
    service = InventorySyncService(
        marketplace="wb",
        wb_fbs_api=FBSAPI(),
        wb_fbo_api=FBOAPI(),
        ozon_api=UnexpectedAPI(),
        yandex_market_api=UnexpectedAPI(),
        session_factory=inventory_db,
        request_pause_seconds=0,
        sleeper=lambda value: None,
    )

    result = service.refresh()

    assert result == {
        "wb_fbs": 1,
        "wb_fbo": 1,
        "ozon": 0,
        "ozon_warehouse": 0,
        "yandex_market": 0,
    }
    with inventory_db() as session:
        assert session.query(OzonStock).filter_by(product_id=200).one().present == 11
        run = session.query(InventorySyncRun).one()
        assert run.marketplace == "wb"


def test_ozon_worker_is_not_affected_by_yandex_market_failure(inventory_db):
    service = InventorySyncService(
        marketplace="ozon",
        wb_fbs_api=UnexpectedAPI(),
        wb_fbo_api=UnexpectedAPI(),
        ozon_api=OzonAPI(),
        ozon_warehouse_api=OzonWarehouseAPI(),
        yandex_market_api=UnexpectedAPI(),
        session_factory=inventory_db,
    )

    result = service.refresh()

    assert result["ozon"] == 1
    assert result["ozon_warehouse"] == 1
    assert result["wb_fbs"] == 0
    assert result["yandex_market"] == 0
    with inventory_db() as session:
        assert session.query(OzonStock).filter_by(product_id=100).one().present == 9
        assert session.query(WBFBSStock).filter_by(sku="old-fbs").one().quantity == 5
        assert session.query(InventorySyncRun).one().marketplace == "ozon"


def test_marketplace_snapshot_only_writes_its_own_tables(inventory_db):
    service = InventorySyncService(
        marketplace="wb",
        wb_fbs_api=FBSAPI(),
        wb_fbo_api=FBOAPI(),
        session_factory=inventory_db,
        request_pause_seconds=0,
        sleeper=lambda value: None,
    )
    snapshot_day = date(2026, 8, 31)

    service.snapshot(
        snapshot_day,
        scheduled_for=datetime(2026, 8, 31, 0, 0, tzinfo=ZoneInfo("Europe/Moscow")),
    )

    with inventory_db() as session:
        assert session.query(WBFBSStockSnapshot).filter_by(snapshot_date=snapshot_day).count() > 0
        assert session.query(WBFboStockSnapshot).filter_by(snapshot_date=snapshot_day).count() > 0
        assert session.query(OzonStockSnapshot).filter_by(snapshot_date=snapshot_day).count() == 0
        assert session.query(YandexMarketStockSnapshot).filter_by(snapshot_date=snapshot_day).count() == 0


def test_yandex_market_worker_requires_campaign_ids(inventory_db):
    service = InventorySyncService(
        marketplace="yandex_market",
        yandex_market_api=YandexMarketAPI(),
        yandex_market_campaign_ids=(),
        session_factory=inventory_db,
    )

    with pytest.raises(RuntimeError, match="YANDEX_MARKET_CAMPAIGN_IDS"):
        service.refresh()


def test_inventory_workers_use_distinct_locks_and_all_mode_reserves_each_one():
    wb = InventorySyncService(marketplace="wb", wb_fbs_api=FBSAPI(), wb_fbo_api=FBOAPI())
    ozon = InventorySyncService(
        marketplace="ozon",
        ozon_api=OzonAPI(),
        ozon_warehouse_api=OzonWarehouseAPI(),
    )
    yandex = InventorySyncService(
        marketplace="yandex_market",
        yandex_market_api=YandexMarketAPI(),
        yandex_market_campaign_ids=(300,),
    )
    combined = InventorySyncService(
        wb_fbs_api=FBSAPI(),
        wb_fbo_api=FBOAPI(),
        ozon_api=OzonAPI(),
        ozon_warehouse_api=OzonWarehouseAPI(),
        yandex_market_api=YandexMarketAPI(),
        yandex_market_campaign_ids=(300,),
    )

    isolated = wb._lock_ids() + ozon._lock_ids() + yandex._lock_ids()
    assert len(set(isolated)) == 3
    assert set(isolated).issubset(combined._lock_ids())


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
