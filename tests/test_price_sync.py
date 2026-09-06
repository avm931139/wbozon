from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import MarketplaceCurrentPrice, MarketplacePriceSnapshot, MarketplacePriceSyncRun
from ozon.exceptions import OzonParseError
from ozon.prices import OzonPricesAPI
from price_sync.runner import MarketplacePriceRunner
from price_sync.service import MarketplacePriceService
from price_sync.types import PriceRecord
from wb.prices import WBPricesAPI
from yandex_market.prices import YandexMarketPricesAPI


class QueueClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, path, **kwargs):
        self.calls.append(("get", path, kwargs))
        return self.responses.pop(0)

    def post(self, path, **kwargs):
        self.calls.append(("post", path, kwargs))
        return self.responses.pop(0)


def test_wb_prices_paginate_and_keep_size_level_prices():
    client = QueueClient([
        {"data": {"listGoods": [{
            "nmID": 101,
            "vendorCode": "vendor-101",
            "currencyIsoCode4217": "RUB",
            "discount": 20,
            "clubDiscount": 5,
            "sizes": [{
                "sizeID": 501,
                "price": 1000,
                "discountedPrice": 800,
                "clubDiscountedPrice": 760,
            }],
        }]}},
        {"data": {"listGoods": []}},
    ])

    records = WBPricesAPI(client).records()

    assert len(records) == 1
    assert records[0].source_key == "101:501"
    assert records[0].list_price == Decimal("1000")
    assert records[0].customer_price == Decimal("800")
    assert records[0].club_price == Decimal("760")
    assert client.calls[1][2]["params"] == {"limit": 1000, "offset": 1000}


def test_ozon_prices_follow_cursor_and_keep_promotions(monkeypatch):
    monkeypatch.setattr("ozon.prices.OZON_CLIENT_ID", "cabinet-1")
    client = QueueClient([
        {
            "items": [{
                "product_id": 202,
                "offer_id": "offer-202",
                "price": {
                    "currency_code": "RUB",
                    "old_price": "1500",
                    "marketing_seller_price": "1200",
                    "price": "1100",
                    "min_price": "900",
                    "auto_action_enabled": True,
                },
                "marketing_actions": {"actions": [{"title": "September sale"}]},
            }],
            "cursor": "next",
        },
        {"items": [], "cursor": ""},
    ])

    records = OzonPricesAPI(client).records()

    assert records[0].account_id == "cabinet-1"
    assert records[0].customer_price == Decimal("1100")
    assert records[0].in_promotion is True
    assert records[0].promotion_names == ["September sale"]
    assert client.calls[1][2]["json_body"]["cursor"] == "next"


def test_ozon_prices_reject_repeated_cursor():
    client = QueueClient([
        {"items": [{}], "cursor": "same"},
        {"items": [{}], "cursor": "same"},
    ])
    with pytest.raises(OzonParseError, match="did not advance"):
        OzonPricesAPI(client).list_all()


def test_yandex_prices_follow_token_and_do_not_invent_customer_price():
    client = QueueClient([
        {"result": {
            "offers": [{"offerId": "sku-1", "price": {
                "value": 700,
                "discountBase": 900,
                "currencyId": "RUR",
                "minimumForBestseller": 650,
                "updatedAt": "2026-09-06T12:00:00Z",
            }}],
            "paging": {"nextPageToken": "next"},
        }},
        {"result": {"offers": [], "paging": {}}},
    ])

    records = YandexMarketPricesAPI(client, business_id=303).records()

    assert records[0].source_key == "303:sku-1"
    assert records[0].seller_price == Decimal("700")
    assert records[0].customer_price is None
    assert records[0].min_price == Decimal("650")
    assert client.calls[1][2]["params"]["pageToken"] == "next"


class StubSource:
    def __init__(self, records):
        self._records = records

    def records(self):
        return list(self._records)


class StubPriceService(MarketplacePriceService):
    def __init__(self, source, **kwargs):
        super().__init__(**kwargs)
        self.source = source

    def _source(self, marketplace):
        return self.source


def test_price_service_keeps_unchanged_history_and_updates_current():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    captured = iter([
        datetime(2026, 9, 6, 9, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc),
    ])
    source = StubSource([PriceRecord(
        source_key="101:501",
        product_id="101",
        customer_price=Decimal("800"),
        raw_data={"price": 800},
    )])
    service = StubPriceService(
        source,
        session_factory=session_factory,
        clock=lambda: next(captured),
    )
    with session_factory() as session:
        session.add_all([
            MarketplacePriceSyncRun(
                id="run-1", marketplace="wb", started_at=datetime.now(timezone.utc), status="running"
            ),
            MarketplacePriceSyncRun(
                id="run-2", marketplace="wb", started_at=datetime.now(timezone.utc), status="running"
            ),
        ])
        session.commit()

    service.sync("wb", "run-1")
    service.sync("wb", "run-2")

    with session_factory() as session:
        assert session.query(MarketplaceCurrentPrice).count() == 1
        assert session.query(MarketplacePriceSnapshot).count() == 2
        current = session.query(MarketplaceCurrentPrice).one()
        assert current.customer_price == Decimal("800")
        assert current.captured_at == datetime(2026, 9, 6, 12, 0)


def test_price_runner_records_failed_attempt():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)

    class FailingService:
        MARKETPLACES = ("wb",)

        def sync(self, marketplace, run_id):
            raise RuntimeError("broken price endpoint")

    runner = MarketplacePriceRunner(FailingService(), session_factory=session_factory)
    with pytest.raises(RuntimeError, match="broken price endpoint"):
        runner.run("wb")

    with session_factory() as session:
        run = session.query(MarketplacePriceSyncRun).one()
        assert run.status == "failed"
        assert run.error == "RuntimeError: broken price endpoint"
