from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    YandexMarketBusiness,
    YandexMarketCampaign,
    YandexMarketCampaignOffer,
    YandexMarketOffer,
    YandexMarketOrder,
    YandexMarketOrderItem,
    YandexMarketSyncRun,
    YandexMarketWarehouse,
)
from yandex_market.catalog import YandexMarketCatalogAPI
from yandex_market.identity import YandexMarketIdentityAPI
from yandex_market.orders import YandexMarketOrdersAPI
from yandex_market.services.catalog_service import YandexMarketCatalogService
from yandex_market.services.identity_service import YandexMarketIdentityService
from yandex_market.services.order_service import YandexMarketOrderService
from yandex_market.task_runner import YandexMarketTaskRunner


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, path, **kwargs):
        self.calls.append(("get", path, kwargs))
        return self.responses.pop(0)

    def post(self, path, **kwargs):
        self.calls.append(("post", path, kwargs))
        return self.responses.pop(0)


def session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


def campaigns():
    return [{
        "id": 149010920,
        "domain": "shop.example",
        "business": {"id": 777, "name": "Cabinet"},
        "placementType": "FBS",
        "apiAvailability": "AVAILABLE",
    }]


class FakeIdentity:
    def contexts(self):
        return campaigns(), {777}

    def partner_warehouses(self, **kwargs):
        return [{"id": 55, "name": "Склад продавца", "campaignId": 149010920}]

    def fulfillment_warehouses(self, **kwargs):
        return []


def test_identity_api_uses_token_pagination():
    client = FakeClient([
        {"campaigns": campaigns(), "paging": {"nextPageToken": "next"}},
        {"campaigns": [], "paging": {}},
    ])
    assert YandexMarketIdentityAPI(client).campaigns() == campaigns()
    assert client.calls[1][2]["params"]["pageToken"] == "next"


def test_catalog_and_orders_apis_parse_current_business_responses():
    catalog_client = FakeClient([{
        "status": "OK",
        "result": {"offerMappings": [{"offer": {"offerId": "sku-1"}}], "paging": {}},
    }])
    assert YandexMarketCatalogAPI(catalog_client).offer_mappings(business_id=777)[0]["offer"]["offerId"] == "sku-1"

    orders_client = FakeClient([{
        "status": "OK",
        "orders": [{"orderId": 123}],
        "paging": {},
    }])
    rows = YandexMarketOrdersAPI(orders_client).list(
        business_id=777,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 30),
        campaign_ids=[149010920],
    )
    assert rows == [{"orderId": 123}]
    body = orders_client.calls[0][2]["json_body"]
    assert body["dates"]["creationDateFrom"] == "2026-01-01"
    assert body["campaignIds"] == [149010920]


def test_identity_catalog_and_orders_are_persisted(monkeypatch):
    factory = session_factory()
    YandexMarketIdentityService(
        api=FakeIdentity(),
        session_factory=factory,
    ).sync()

    class CatalogAPI:
        def offer_mappings(self, **kwargs):
            return [{
                "offer": {"offerId": "sku-1", "name": "Товар", "vendor": "Brand", "barcodes": ["123"]},
                "mapping": {"marketSku": 444, "marketCategoryName": "Категория"},
                "status": "ACTIVE",
            }]

        def campaign_offers(self, **kwargs):
            return [{"offerId": "sku-1", "status": "PUBLISHED", "price": {"value": 1990}}]

    monkeypatch.setattr("yandex_market.services.catalog_service.YANDEX_MARKET_CAMPAIGN_IDS", (149010920,))
    YandexMarketCatalogService(
        api=CatalogAPI(),
        identity_api=FakeIdentity(),
        session_factory=factory,
    ).sync()

    class OrdersAPI:
        def list(self, **kwargs):
            return [{
                "id": 123,
                "campaignId": 149010920,
                "programType": "FBS",
                "status": "PROCESSING",
                "creationDate": "2026-01-02T09:00:00Z",
                "prices": {
                    "payment": {"value": 1900, "currencyId": "RUR"},
                    "cashback": {"value": 90, "currencyId": "RUR"},
                },
                "items": [{
                    "id": 9,
                    "offerId": "sku-1",
                    "marketSku": 444,
                    "offerName": "Товар",
                    "count": 2,
                    "prices": {"buyerPrice": {"value": 995}},
                }],
            }]

    monkeypatch.setattr("yandex_market.services.order_service.YANDEX_MARKET_CAMPAIGN_IDS", (149010920,))
    monkeypatch.setattr("yandex_market.services.order_service.YANDEX_MARKET_HISTORY_FROM", "2026-01-01")
    result = YandexMarketOrderService(
        api=OrdersAPI(),
        identity_api=FakeIdentity(),
        session_factory=factory,
    ).sync(today=date(2026, 1, 2))

    assert result == {"businesses": 1, "received": 1, "saved": 1}
    with factory() as session:
        assert session.get(YandexMarketBusiness, 777).name == "Cabinet"
        assert session.get(YandexMarketCampaign, 149010920).placement_type == "FBS"
        assert session.query(YandexMarketWarehouse).one().name == "Склад продавца"
        assert session.query(YandexMarketOffer).one().name == "Товар"
        assert session.query(YandexMarketCampaignOffer).one().status == "PUBLISHED"
        assert session.query(YandexMarketOrder).one().items_count == 2
        assert session.query(YandexMarketOrder).one().total_amount == 1990
        assert session.query(YandexMarketOrderItem).one().offer_id == "sku-1"


def test_task_runner_records_success_and_failure():
    factory = session_factory()

    class Service:
        @staticmethod
        def task_names():
            return ("orders",)

        @staticmethod
        def run_task(task):
            return {"saved": 3}

    result = YandexMarketTaskRunner(Service(), session_factory=factory).run("orders")
    assert result["status"] == "completed"
    with factory() as session:
        row = session.query(YandexMarketSyncRun).one()
        assert row.status == "completed"
        assert row.result == {"saved": 3}
