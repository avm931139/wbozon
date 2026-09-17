from datetime import date, datetime, timezone

from sqlalchemy import Column, Integer, String, create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.query_utils import rows_by_keys
from app.db import Base
from app.models import (
    WBCustomerFeedback,
    WBCustomerQuestion,
    WBFinancialSalesReport,
    WBOperationalOrder,
)
from wb.services.finance_service import FinanceService
from wb.services.sales_service import SalesService
from wb.services.customer_communication_service import CustomerCommunicationService


def test_rows_by_keys_batches_queries_and_never_scans_the_table():
    base = declarative_base()

    class Example(base):
        __tablename__ = "incremental_query_examples"
        id = Column(Integer, primary_key=True)
        source_key = Column(String, nullable=False, unique=True)

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        session.add_all(Example(source_key=f"key-{index}") for index in range(10))
        session.commit()

    statements: list[str] = []
    event.listen(
        engine,
        "before_cursor_execute",
        lambda _conn, _cursor, statement, _params, _context, _many: statements.append(statement),
    )
    with factory() as session:
        loaded = rows_by_keys(
            session,
            Example,
            Example.source_key,
            ["key-1", "key-3", "key-5", "key-7", "key-9"],
            batch_size=2,
        )

    assert set(loaded) == {"key-1", "key-3", "key-5", "key-7", "key-9"}
    selects = [statement for statement in statements if "FROM incremental_query_examples" in statement]
    assert len(selects) == 3
    assert all("WHERE" in statement and " IN (" in statement for statement in selects)


def _financial_report(report_wb_id: int, amount: int) -> WBFinancialSalesReport:
    timestamp = datetime(2026, 9, 1, tzinfo=timezone.utc)
    return WBFinancialSalesReport(
        report_wb_id=report_wb_id,
        date_from=timestamp,
        date_to=timestamp,
        create_date=timestamp,
        currency="RUB",
        report_type=1,
        retail_amount_sum=amount,
        raw_data={"old": report_wb_id},
    )


def test_finance_report_sync_queries_only_incoming_report_ids(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        session.add_all((_financial_report(10, 1), _financial_report(999, 999)))
        session.commit()

    class API:
        @staticmethod
        def sales_reports(_date_from, _date_to):
            return [{
                "reportId": 10,
                "dateFrom": "2026-09-01T00:00:00Z",
                "dateTo": "2026-09-07T00:00:00Z",
                "createDate": "2026-09-08T00:00:00Z",
                "currency": "RUB",
                "reportType": 1,
                "retailAmountSum": 123,
            }]

    monkeypatch.setattr("wb.services.finance_service.SessionLocal", factory)
    service = FinanceService()
    service.api = API()
    statements: list[str] = []
    event.listen(
        engine,
        "before_cursor_execute",
        lambda _conn, _cursor, statement, _params, _context, _many: statements.append(statement),
    )

    assert service.sync_sales_reports(date(2026, 9, 1), date(2026, 9, 7)) == 1

    report_selects = [
        statement for statement in statements
        if "FROM wb_financial_sales_reports" in statement
    ]
    assert report_selects and all("WHERE" in statement and " IN (" in statement for statement in report_selects)
    with factory() as session:
        assert session.query(WBFinancialSalesReport).filter_by(report_wb_id=10).one().retail_amount_sum == 123
        untouched = session.query(WBFinancialSalesReport).filter_by(report_wb_id=999).one()
        assert untouched.retail_amount_sum == 999
        assert untouched.raw_data == {"old": 999}


def test_operational_order_sync_queries_only_incoming_srids(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True)
    timestamp = datetime(2026, 9, 1, tzinfo=timezone.utc)
    with factory() as session:
        session.add_all((
            WBOperationalOrder(
                id=1, srid="target", order_date=timestamp, last_change_date=timestamp,
                is_cancel=False, finished_price=1, price_with_discount=1, raw_data={},
            ),
            WBOperationalOrder(
                id=2, srid="unrelated", order_date=timestamp, last_change_date=timestamp,
                is_cancel=False, finished_price=999, price_with_discount=999,
                raw_data={"old": True},
            ),
        ))
        session.commit()

    class API:
        @staticmethod
        def orders(_date_from):
            return [{
                "srid": "target",
                "date": "2026-09-02T10:00:00+03:00",
                "lastChangeDate": "2026-09-02T11:00:00+03:00",
                "nmId": 0,
                "finishedPrice": 123,
                "priceWithDisc": 120,
                "isCancel": False,
            }]

    monkeypatch.setattr("wb.services.sales_service.SessionLocal", factory)
    service = SalesService(api=API())
    statements: list[str] = []
    event.listen(
        engine,
        "before_cursor_execute",
        lambda _conn, _cursor, statement, _params, _context, _many: statements.append(statement),
    )

    assert service.sync_orders(date(2026, 9, 1)) == 1

    order_selects = [
        statement for statement in statements if "FROM wb_operational_orders" in statement
    ]
    assert order_selects and all("WHERE" in statement and " IN (" in statement for statement in order_selects)
    with factory() as session:
        assert session.query(WBOperationalOrder).filter_by(srid="target").one().finished_price == 123
        untouched = session.query(WBOperationalOrder).filter_by(srid="unrelated").one()
        assert untouched.finished_price == 999
        assert untouched.raw_data == {"old": True}


def test_customer_quality_summary_uses_database_aggregates(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True)
    timestamp = datetime(2026, 9, 1, tzinfo=timezone.utc)
    with factory() as session:
        session.add_all((
            WBCustomerQuestion(
                question_wb_id="q1", text="Question", is_answered=True,
                created_date=timestamp, response_seconds=7200, sla_hours=24,
                sla_breached=False, answer_quality_score=80, raw_data={},
            ),
            WBCustomerQuestion(
                question_wb_id="q2", text="Question", is_answered=False,
                created_date=timestamp, sla_hours=24, sla_breached=True, raw_data={},
            ),
            WBCustomerFeedback(
                feedback_wb_id="f1", text="Feedback", product_valuation=5,
                is_answered=True, created_date=timestamp, response_seconds=3600,
                sla_hours=24, sla_breached=False, answer_quality_score=90,
                raw_data={},
            ),
        ))
        session.commit()

    monkeypatch.setattr("wb.services.customer_communication_service.SessionLocal", factory)
    statements: list[str] = []
    event.listen(
        engine,
        "before_cursor_execute",
        lambda _conn, _cursor, statement, _params, _context, _many: statements.append(statement),
    )

    result = CustomerCommunicationService.quality_summary()

    assert result["questions"] == {
        "total": 2,
        "answered": 1,
        "overdue": 1,
        "sla_breached": 1,
        "avg_response_hours": 2.0,
        "avg_quality_score": 80.0,
    }
    assert result["feedbacks"]["avg_response_hours"] == 1.0
    communication_selects = [
        statement for statement in statements
        if "FROM wb_customer_" in statement
    ]
    assert len(communication_selects) == 2
    assert all("avg(" in statement.lower() for statement in communication_selects)
