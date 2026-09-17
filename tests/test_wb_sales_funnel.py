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
    WBSalesFunnelPeriodProduct,
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


def test_sales_funnel_api_gets_arbitrary_period_product_totals():
    client = QueueClient([{"data": {"products": [{"product": {"nmId": 1}}], "currency": {"name": "RUB"}}}])
    api = SalesFunnelAPI(client, request_interval_seconds=0)

    products, currency = api.products(date(2026, 9, 1), date(2026, 9, 16))

    assert products == [{"product": {"nmId": 1}}]
    assert currency == {"name": "RUB"}
    path, body, _ = client.calls[0]
    assert path == "/api/analytics/v3/sales-funnel/products"
    assert body["selectedPeriod"] == {"start": "2026-09-01", "end": "2026-09-16"}
    assert body["skipDeletedNm"] is False
    assert body["limit"] == 1000


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
        self.product_calls = []
        self.pauses = 0

    def pause(self):
        self.pauses += 1

    def history(self, date_from, date_to, nm_ids):
        self.history_calls.append((date_from, date_to, nm_ids))
        return []

    def grouped_history(self, date_from, date_to):
        self.grouped_calls.append((date_from, date_to))
        return []

    def products(self, date_from, date_to):
        self.product_calls.append((date_from, date_to))
        return ([{
            "product": {"nmId": 101, "vendorCode": "SKU-101", "title": "Product"},
            "statistic": {"selected": {
                "openCount": 20, "cartCount": 10,
                "orderCount": 7, "orderSum": 21000,
                "buyoutCount": 4, "buyoutSum": 11000,
                "cancelCount": 2, "cancelSum": 5000,
            }},
        }], {"name": "RUB"})


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


def test_sales_funnel_period_sync_uses_365_day_aggregate_endpoint():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    with session_factory() as session:
        session.add(WBProduct(nm_id=101, vendor_code="SKU-101", title="Product", raw_data={}))
        session.commit()
    api = RecordingEmptyAPI()
    service = SalesFunnelSyncService(api=api, session_factory=session_factory)

    result = service.sync_period(
        date(2026, 9, 1),
        date(2026, 9, 16),
        datetime(2026, 9, 17, 12, 0, tzinfo=MOSCOW),
    )

    assert result["mode"] == "period"
    assert result["rows_upserted"] == 1
    assert api.product_calls == [(date(2026, 9, 1), date(2026, 9, 16))]
    assert api.history_calls == []
    with session_factory() as session:
        row = session.query(WBSalesFunnelPeriodProduct).one()
        assert row.order_count == 7
        assert row.order_sum == Decimal("21000")
        assert row.buyout_count == 4
        assert row.cancel_count == 2


def test_sales_funnel_month_reconciliation_caches_every_month_prefix():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    api = RecordingEmptyAPI()
    service = SalesFunnelSyncService(api=api, session_factory=session_factory)

    result = service.sync_month_prefixes(
        datetime(2026, 9, 3, 1, 35, tzinfo=MOSCOW)
    )

    assert result == {
        "status": "completed",
        "mode": "month_prefixes",
        "period_from": date(2026, 9, 1),
        "period_to": date(2026, 9, 3),
        "snapshots_completed": 3,
        "snapshots_skipped": 0,
        "snapshots_total": 3,
        "rows_upserted": 3,
    }
    assert api.product_calls == [
        (date(2026, 9, 1), date(2026, 9, 1)),
        (date(2026, 9, 1), date(2026, 9, 2)),
        (date(2026, 9, 1), date(2026, 9, 3)),
    ]
    assert api.pauses == 2
    with session_factory() as session:
        assert session.query(WBSalesFunnelPeriodProduct).count() == 3
        assert session.query(WBSalesFunnelSyncRun).filter_by(status="completed").count() == 3


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

    try:
        service.sync(
            datetime(2026, 9, 17, 12, 0, tzinfo=MOSCOW),
            date_from=date(2026, 9, 1),
            date_to=date(2026, 9, 7),
        )
        raise AssertionError("daily history older than the last week must fail")
    except ValueError as exc:
        assert "older than" in str(exc)
