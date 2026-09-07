from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import YandexMarketFinanceTransaction
from yandex_market.finance import YandexMarketFinanceAPI
from yandex_market.services.finance_service import YandexMarketFinanceService, _datetime


class FakeClient:
    def __init__(self):
        self.calls = []

    def post(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return {"result": {"reportId": "finance-report"}}


def test_finance_api_generates_official_payment_report():
    client = FakeClient()
    api = YandexMarketFinanceAPI(client)

    report_id = api.generate_payments(
        business_id=216673578,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 7),
    )

    assert report_id == "finance-report"
    assert client.calls == [(
        "/v2/reports/united-netting/generate",
        {
            "params": {"format": "JSON", "language": "RU"},
            "json_body": {
                "businessId": 216673578,
                "dateFrom": "2026-09-01",
                "dateTo": "2026-09-07",
            },
        },
    )]


def test_finance_service_replaces_period_and_signs_retentions():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True)
    service = YandexMarketFinanceService(
        api=object(), session_factory=factory, business_id=216673578
    )
    rows = [
        {
            "transactionDate": "06.09.2026 12:01",
            "transactionId": 1,
            "transactionType": "Начисление",
            "transactionSource": "Платёж покупателя",
            "transactionSum": 1250.50,
            "orderId": 10,
            "shopSku": "SKU-1",
            "count": 1,
        },
        {
            "transactionDate": "06.09.2026 12:02",
            "transactionId": 2,
            "transactionType": "Удержание",
            "transactionSource": "Размещение товаров на витрине",
            "transactionSum": 125.05,
            "orderId": 10,
            "shopSku": "SKU-1",
            "count": 1,
        },
    ]

    assert service._replace(rows, date(2026, 9, 6), date(2026, 9, 6), 216673578) == 2
    assert service._replace(rows, date(2026, 9, 6), date(2026, 9, 6), 216673578) == 2

    with factory() as session:
        saved = session.query(YandexMarketFinanceTransaction).order_by(
            YandexMarketFinanceTransaction.transaction_id
        ).all()
        assert len(saved) == 2
        assert saved[0].amount == Decimal("1250.500000")
        assert saved[1].amount == Decimal("-125.050000")


def test_finance_datetime_is_moscow_aware_and_invalid_value_is_skipped():
    parsed = _datetime("06.09.2026 12:01")
    assert parsed is not None
    assert parsed.utcoffset().total_seconds() == 3 * 60 * 60
    assert _datetime("not-a-date") is None
