from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import YandexMarketSalesAnalyticsDaily
from yandex_market.sales_analytics import YandexMarketSalesAnalyticsAPI
from yandex_market.services.sales_analytics_service import YandexMarketSalesAnalyticsService


class FakeClient:
    def __init__(self):
        self.calls = []

    def post(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return {"result": {"reportId": "sales-report"}}


def test_sales_analytics_api_requests_official_offer_report():
    client = FakeClient()
    api = YandexMarketSalesAnalyticsAPI(client)
    report_id = api.generate_sales_analytics(
        business_id=216673578,
        date_from=date(2026, 8, 1),
        date_to=date(2026, 8, 31),
    )
    assert report_id == "sales-report"
    assert client.calls == [(
        "/v2/reports/shows-sales/generate",
        {
            "params": {"format": "JSON"},
            "json_body": {
                "businessId": 216673578,
                "dateFrom": "2026-08-01",
                "dateTo": "2026-08-31",
                "grouping": "OFFERS",
            },
        },
    )]


def test_sales_analytics_service_replaces_daily_offer_rows_idempotently():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True)
    service = YandexMarketSalesAnalyticsService(
        api=object(), session_factory=factory, business_id=216673578
    )
    source = {
        "day": "2026-09-06", "offerId": "NVL0040", "offerName": "Lamp",
        "shows": 100, "clicks": 20, "toCart": 10,
        "orderItems": 4, "orderItemsTotalAmount": 4000,
        "orderItemsDeliveredCount": 3, "orderItemsDeliveredTotalAmount": 3000,
        "orderItemsDeliveredFromOrderedCount": 2,
        "orderItemsDeliveredFromOrderedTotalAmount": 2000,
        "orderItemsCanceledByCreatedAtCount": 1,
        "orderItemsReturnedByCreatedAtCount": 1,
    }
    assert service._replace(
        [source, source], 216673578, date(2026, 9, 1), date(2026, 9, 7)
    ) == 1
    assert service._replace(
        [source], 216673578, date(2026, 9, 1), date(2026, 9, 7)
    ) == 1
    with factory() as session:
        row = session.query(YandexMarketSalesAnalyticsDaily).one()
        assert row.offer_id == "NVL0040"
        assert row.shows == 100
        assert row.order_items == 4
        assert row.order_items_amount == Decimal("4000.000000")
        assert row.delivered_from_ordered_items == 2
        assert row.cancelled_items == 1
        assert row.returned_items == 1
