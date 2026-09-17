from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    WBProduct,
    WBSalesFunnelAccountDaily,
    WBSalesFunnelDaily,
    WBSalesFunnelSyncRun,
)
from wb.sales_funnel import SalesFunnelAPI
from wb.sales_funnel_sync import SalesFunnelSyncService


MOSCOW = ZoneInfo("Europe/Moscow")


class QueueClient:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.calls = []

    def post(self, path, *, json_body=None, retries=3):
        self.calls.append((path, json_body, retries))
        return next(self.payloads)


def test_sales_funnel_api_chunks_nm_ids_and_observes_rate_interval():
    client = QueueClient([[{"product": {"nmId": 1}, "history": [], "currency": "RUB"}], []])
    sleeps = []
    api = SalesFunnelAPI(client, request_interval_seconds=20, sleeper=sleeps.append)

    result = api.history(date(2026, 9, 2), date(2026, 9, 8), range(1, 22))

    assert len(result) == 1
    assert len(client.calls) == 2
    assert len(client.calls[0][1]["nmIds"]) == 20
    assert client.calls[0][1]["selectedPeriod"] == {"start": "2026-09-02", "end": "2026-09-08"}
    assert sleeps == [20]


def test_sales_funnel_api_gets_unfiltered_cabinet_totals():
    client = QueueClient([{"data": [{"history": []}]}])
    api = SalesFunnelAPI(client, request_interval_seconds=0)

    result = api.grouped_history(date(2026, 9, 2), date(2026, 9, 8))

    assert result == [{"history": []}]
    path, body, _ = client.calls[0]
    assert path == "/api/analytics/v3/sales-funnel/grouped/history"
    assert body["brandNames"] == []
    assert body["subjectIds"] == []
    assert body["tagIds"] == []
    assert body["skipDeletedNm"] is False


class FakeSalesFunnelAPI:
    def pause(self):
        return None

    def history(self, date_from, date_to, nm_ids):
        assert nm_ids == [101]
        return [{
            "product": {"nmId": 101, "vendorCode": "SKU-101", "title": "Товар"},
            "currency": {"name": "RUB"},
            "history": [{
                "openCount": 10, "cartCount": 5,
                "date": "2026-09-08", "orderCount": 4, "orderSum": 12000,
                "buyoutCount": 2, "buyoutSum": 5500,
            }],
        }]

    def grouped_history(self, date_from, date_to):
        return [{
            "group": {"subjectName": "Все товары"},
            "currency": {"name": "RUB"},
            "history": [{
                "openCount": 10, "cartCount": 5,
                "date": "2026-09-08", "orderCount": 4, "orderSum": 12000,
                "buyoutCount": 2, "buyoutSum": 5500,
            }],
        }]


class RecordingEmptyAPI:
    def __init__(self):
        self.history_calls = []
        self.grouped_calls = []
        self.pauses = 0

    def pause(self):
        self.pauses += 1

    def history(self, date_from, date_to, nm_ids):
        self.history_calls.append((date_from, date_to, nm_ids))
        return []

    def grouped_history(self, date_from, date_to):
        self.grouped_calls.append((date_from, date_to))
        return []


def test_sales_funnel_sync_upserts_daily_preliminary_metrics():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    with session_factory() as session:
        session.add(WBProduct(nm_id=101, vendor_code="SKU-101", title="Товар", raw_data={}))
        session.commit()
    service = SalesFunnelSyncService(api=FakeSalesFunnelAPI(), session_factory=session_factory)
    now = datetime(2026, 9, 8, 12, 0, tzinfo=MOSCOW)

    service.sync(now)
    service.sync(now)

    with session_factory() as session:
        row = session.query(WBSalesFunnelDaily).one()
        assert row.open_count == 10
        assert row.cart_count == 5
        assert row.order_count == 4
        assert row.buyout_count == 2
        assert row.cancel_count == 0
        assert row.order_sum == Decimal("12000")
        assert session.query(WBSalesFunnelAccountDaily).count() == 7
        account = session.get(WBSalesFunnelAccountDaily, date(2026, 9, 8))
        assert account is not None
        assert account.order_count == 4
        assert account.order_sum == Decimal("12000")
        assert account.open_count == 10
        assert session.query(WBSalesFunnelSyncRun).filter_by(status="completed").count() == 2


def test_sales_funnel_sync_splits_explicit_backfill_into_seven_day_windows():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    with session_factory() as session:
        session.add(WBProduct(nm_id=101, vendor_code="SKU-101", title="Product", raw_data={}))
        session.commit()
    api = RecordingEmptyAPI()
    service = SalesFunnelSyncService(api=api, session_factory=session_factory)

    result = service.sync(
        datetime(2026, 9, 17, 12, 0, tzinfo=MOSCOW),
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 16),
    )

    assert result["windows"] == 3
    assert [(start, end) for start, end, _ in api.history_calls] == [
        (date(2026, 9, 1), date(2026, 9, 7)),
        (date(2026, 9, 8), date(2026, 9, 14)),
        (date(2026, 9, 15), date(2026, 9, 16)),
    ]
    assert api.grouped_calls == [
        (date(2026, 9, 1), date(2026, 9, 7)),
        (date(2026, 9, 8), date(2026, 9, 14)),
        (date(2026, 9, 15), date(2026, 9, 16)),
    ]
    # One pause separates product and account endpoints, another separates windows.
    assert api.pauses == 5


def test_sales_funnel_sync_rejects_incomplete_or_reversed_explicit_period():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    service = SalesFunnelSyncService(api=RecordingEmptyAPI(), session_factory=session_factory)

    try:
        service.sync(date_from=date(2026, 9, 1))
        raise AssertionError("missing date_to must fail")
    except ValueError as exc:
        assert "provided together" in str(exc)

    try:
        service.sync(date_from=date(2026, 9, 2), date_to=date(2026, 9, 1))
        raise AssertionError("reversed range must fail")
    except ValueError as exc:
        assert "later than" in str(exc)
