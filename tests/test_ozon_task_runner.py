from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import OzonSyncRun
from ozon.business_time import ozon_today
from ozon.task_runner import OzonTaskRunner


class Service:
    @staticmethod
    def task_names():
        return ("products", "orders")

    def run_task(self, task):
        if task == "orders":
            raise RuntimeError("API unavailable")
        return [1, 2, 3]


class PartialService(Service):
    def run_task(self, task):
        return {"reviews": 0, "questions": 12, "reviews_error": "OzonAuthError: HTTP 403"}


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


def test_task_runner_records_completed_result(session_factory):
    result = OzonTaskRunner(Service(), session_factory=session_factory).run("products")
    assert result == {"task": "products", "status": "completed", "result": {"count": 3}}
    with session_factory() as session:
        row = session.query(OzonSyncRun).one()
        assert row.task == "products"
        assert row.status == "completed"
        assert row.result == {"count": 3}
        assert row.finished_at is not None


def test_task_runner_records_failure_and_raises(session_factory):
    with pytest.raises(RuntimeError, match="API unavailable"):
        OzonTaskRunner(Service(), session_factory=session_factory).run("orders")
    with session_factory() as session:
        row = session.query(OzonSyncRun).one()
        assert row.status == "failed"
        assert row.error == "RuntimeError: API unavailable"


def test_task_runner_records_partial_result_as_error(session_factory):
    result = OzonTaskRunner(PartialService(), session_factory=session_factory).run("products")
    assert result["status"] == "partial"
    with session_factory() as session:
        row = session.query(OzonSyncRun).one()
        assert row.status == "partial"
        assert row.error == "reviews_error=OzonAuthError: HTTP 403"


def test_ozon_business_date_uses_moscow_timezone():
    from datetime import datetime, timezone

    assert ozon_today(datetime(2026, 8, 19, 21, 30, tzinfo=timezone.utc)) == date(2026, 8, 20)
