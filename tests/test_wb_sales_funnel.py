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
        account = session.query(WBSalesFunnelAccountDaily).one()
        assert account.order_count == 4
        assert account.order_sum == Decimal("12000")
        assert account.open_count == 10
        assert session.query(WBSalesFunnelSyncRun).filter_by(status="completed").count() == 2
