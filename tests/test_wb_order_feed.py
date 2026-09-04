from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from zoneinfo import ZoneInfo

from app.db import Base
from app.models import WBOrderFeedOrder, WBOrderFeedSyncRun
from wb.order_feed import OrderFeedAPI
from wb.order_feed_sync import OrderFeedSyncService
from wb.exceptions import WBParseError
from wb.services.sales_service import SalesService


MOSCOW = ZoneInfo("Europe/Moscow")


class QueueClient:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.calls = []

    def post(self, path, *, json_body=None, retries=3):
        self.calls.append((path, json_body, retries))
        return next(self.payloads)


def test_order_feed_uses_data_wrapper_and_snapshot_pagination():
    client = QueueClient([
        {"data": {"orders": [{"srid": "one"}], "snapshotTime": "2026-09-04T12:00:00Z"}},
        {"data": {"orders": [], "snapshotTime": "2026-09-04T12:00:00Z"}},
    ])
    sleeps = []
    api = OrderFeedAPI(client, request_interval_seconds=60, sleeper=sleeps.append)
    start = datetime(2026, 9, 4, 0, 0, tzinfo=MOSCOW)
    end = datetime(2026, 9, 4, 12, 0, tzinfo=MOSCOW)

    assert api.list(start, end, limit=1) == [{"srid": "one"}]
    assert client.calls[0][1]["pagination"] == {"limit": 1, "offset": 0}
    assert client.calls[1][1]["pagination"] == {
        "limit": 1,
        "offset": 1,
        "snapshotTime": "2026-09-04T12:00:00Z",
    }
    assert sleeps == [60]


class FakeOrderFeedAPI:
    def list(self, date_from, date_to):
        return [
            {
                "srid": "fbs-1",
                "nmId": 101,
                "chrtId": 201,
                "createdAt": "2026-09-04T10:00:00+03:00",
                "updatedAt": "2026-09-04T10:00:00+03:00",
                "status": "created",
                "isMp": True,
                "isB2b": False,
                "sellerPrice": 1000,
                "warehouseName": "Склад продавца",
            },
            {
                "srid": "fbo-1",
                "nmId": 102,
                "chrtId": 202,
                "createdAt": "2026-09-04T11:00:00+03:00",
                "updatedAt": "2026-09-04T12:00:00+03:00",
                "status": "cancel",
                "cancelType": "app",
                "isMp": False,
                "isB2b": False,
                "sellerPrice": 2500,
                "warehouseName": "Склад WB",
            },
        ]


def test_order_feed_sync_is_idempotent_and_records_success():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    service = OrderFeedSyncService(
        api=FakeOrderFeedAPI(),
        session_factory=session_factory,
        lookback_days=31,
    )
    now = datetime(2026, 9, 4, 13, 0, tzinfo=MOSCOW)

    first = service.sync(now)
    second = service.sync(now)

    assert first["status"] == "completed"
    assert first["rows_received"] == 2
    assert second["rows_upserted"] == 2
    with session_factory() as session:
        assert session.query(WBOrderFeedOrder).count() == 2
        assert session.query(WBOrderFeedSyncRun).filter_by(status="completed").count() == 2
        assert session.query(WBOrderFeedOrder).filter_by(srid="fbo-1").one().status == "cancel"


def test_order_feed_rejects_incomplete_rows_and_records_failure():
    class InvalidAPI:
        def list(self, date_from, date_to):
            return [{"srid": "broken", "status": "created", "isMp": False}]

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    service = OrderFeedSyncService(api=InvalidAPI(), session_factory=session_factory)

    with pytest.raises(WBParseError):
        service.sync(datetime(2026, 9, 4, 13, 0, tzinfo=MOSCOW))

    with session_factory() as session:
        run = session.query(WBOrderFeedSyncRun).one()
        assert run.status == "failed"
        assert "WBParseError" in run.error
        assert session.query(WBOrderFeedOrder).count() == 0


def test_sales_summary_prefers_complete_order_feed(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    now = datetime(2026, 9, 4, 13, 0, tzinfo=MOSCOW)
    OrderFeedSyncService(
        api=FakeOrderFeedAPI(),
        session_factory=session_factory,
    ).sync(now)
    monkeypatch.setattr("wb.services.sales_service.SessionLocal", session_factory)

    result = SalesService.summary(date(2026, 9, 4), date(2026, 9, 4))

    assert result["orders_source"] == "order_feed"
    assert result["orders_placed"] == 2
    assert Decimal(result["orders_amount"]) == Decimal("3500")
    assert result["orders_from_period_now_cancelled"] == 1
    assert result["cancellations_registered"] == 1
    assert result["fulfillment"]["orders"] == {"fbs": 1, "fbo": 1, "unknown": 0}
