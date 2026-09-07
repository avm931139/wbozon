from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    OzonFinanceAccrual,
    OzonFinanceAccrualType,
    OzonFinancePostingAccrual,
)
from ozon.finances import OzonFinancesAPI
from ozon.services.finance_service import OzonFinanceSyncService
from ozon.exceptions import OzonRateLimitError


class Client:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def post(self, path, *, json_body=None):
        self.calls.append((path, json_body))
        return next(self.responses)


def test_finance_api_contracts_and_pagination():
    client = Client([
        {"accruals": [{"accrual_id": 1}], "last_id": "next"},
        {"accruals": [], "last_id": ""},
        {"accrual_types": [{"id": 10, "name": "Delivery"}]},
        {"posting_accruals": [{"posting_number": "123-1-1", "accruals": []}]},
    ])
    api = OzonFinancesAPI(client)
    assert api.accruals_by_day(date(2026, 9, 1), date(2026, 9, 1)) == [{"accrual_id": 1}]
    assert client.calls[:2] == [
        ("/v1/finance/accrual/by-day", {"date": "2026-09-01", "last_id": ""}),
        ("/v1/finance/accrual/by-day", {"date": "2026-09-01", "last_id": "next"}),
    ]
    assert api.accrual_types()[0]["id"] == 10
    assert api.accruals_by_postings(["123-1-1"])[0]["posting_number"] == "123-1-1"


class FinanceAPI:
    def accrual_types(self):
        return [{"id": 10, "name": "Delivery", "description": "Delivery fee"}]

    def accruals_by_day(self, start, end):
        return [{
            "accrual_id": 501,
            "date": "2026-09-01",
            "unit_number": "123-1-1",
            "accrued_category": "POSTING",
            "total_amount": {"amount": "850.50", "currency": "RUB"},
        }]

    def accruals_by_postings(self, posting_numbers):
        assert posting_numbers == ["123-1-1"]
        return [{
            "posting_number": "123-1-1",
            "accruals": [{
                "accrual_date": "2026-09-01",
                "type_id": 10,
                "sku": 9001,
                "quantity": 2,
                "seller_price": {"amount": "500", "currency": "RUB"},
                "accrued": {"amount": "-149.50", "currency": "RUB"},
            }],
        }]


def test_finance_sync_persists_daily_types_and_posting_details():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, future=True)
    service = OzonFinanceSyncService(
        api=FinanceAPI(),
        session_factory=sessions,
        history_from=date(2026, 9, 1),
        today=lambda: date(2026, 9, 1),
        posting_batch_limit=1,
        request_pause_seconds=0,
    )
    result = service.sync_all()
    assert result == {
        "types": 1,
        "daily": 1,
        "postings": {"requested": 1, "returned": 1, "rows": 1, "batches": 1},
    }
    with sessions() as session:
        daily = session.query(OzonFinanceAccrual).one()
        assert daily.posting_number == "123-1-1"
        assert str(daily.amount) == "850.500000"
        assert session.get(OzonFinanceAccrualType, 10).name == "Delivery"
        detail = session.query(OzonFinancePostingAccrual).one()
        assert detail.sku == 9001
        assert str(detail.accrued) == "-149.500000"

    repeated = service.sync_all()
    assert repeated["postings"]["rows"] == 1
    with sessions() as session:
        assert session.query(OzonFinancePostingAccrual).count() == 1


def test_finance_sync_retries_rate_limit_and_ignores_non_posting_unit_numbers():
    class API(FinanceAPI):
        def __init__(self):
            self.type_calls = 0
            self.posting_calls = 0

        def accrual_types(self):
            self.type_calls += 1
            if self.type_calls == 1:
                raise OzonRateLimitError("limited")
            return super().accrual_types()

        def accruals_by_day(self, start, end):
            rows = super().accruals_by_day(start, end)
            rows.append({
                "accrual_id": 502,
                "date": "2026-09-01",
                "unit_number": "advertising-contract",
                "accrued_category": "POSTING",
                "total_amount": {"amount": "-10", "currency": "RUB"},
            })
            return rows

        def accruals_by_postings(self, posting_numbers):
            self.posting_calls += 1
            return super().accruals_by_postings(posting_numbers)

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, future=True)
    api = API()
    sleeps = []
    result = OzonFinanceSyncService(
        api=api,
        session_factory=sessions,
        history_from=date(2026, 9, 1),
        today=lambda: date(2026, 9, 1),
        posting_batch_limit=1,
        request_pause_seconds=0,
        rate_limit_retries=1,
        rate_limit_backoff_seconds=5,
        sleeper=sleeps.append,
    ).sync_all()
    assert result["daily"] == 2
    assert result["postings"]["requested"] == 1
    assert api.posting_calls == 1
    assert sleeps == [5]
