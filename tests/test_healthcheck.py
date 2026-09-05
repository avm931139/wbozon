from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import HealthcheckRun, OzonSyncRun, WBDocumentSyncRun, YandexMarketSyncRun
from healthcheck.__main__ import (
    Check,
    OZON_TASK_MAX_AGES,
    _error_message,
    _failure_signature,
    _ozon_task_checks,
    _systemctl_active,
    _yandex_market_task_checks,
    collect_checks,
    record_healthcheck,
)


class Result:
    returncode = 0
    stdout = "active\n"
    stderr = ""


def test_systemctl_active(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return Result()

    monkeypatch.setattr("healthcheck.__main__.subprocess.run", run)
    assert _systemctl_active("wbozon-inventory.service") == (True, "active")
    assert calls == [["systemctl", "is-active", "wbozon-inventory.service"]]


def test_health_error_message_and_signature_only_use_failed_checks():
    checks = [
        Check(True, "cron service", "active"),
        Check(False, "Ozon warehouse snapshot", "0 rows"),
    ]
    now = datetime(2026, 8, 20, 9, 35, tzinfo=ZoneInfo("Europe/Moscow"))
    message = _error_message(checks, now)
    assert "Ozon warehouse snapshot: 0 rows" in message
    assert "cron service" not in message
    assert _failure_signature(checks) == _failure_signature([
        Check(False, "Ozon warehouse snapshot", "a different row count")
    ])


def test_ozon_task_health_uses_latest_status_and_freshness(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    timezone = ZoneInfo("Europe/Moscow")
    now = datetime(2026, 8, 20, 12, 0, tzinfo=timezone)
    with session_factory() as session:
        session.add(OzonSyncRun(
            id="run-1",
            task="orders",
            started_at=datetime(2026, 8, 20, 8, 55, tzinfo=ZoneInfo("UTC")),
            finished_at=datetime(2026, 8, 20, 8, 56, tzinfo=ZoneInfo("UTC")),
            status="completed",
        ))
        session.commit()
        monkeypatch.setattr("healthcheck.__main__.OZON_REQUIRED_TASKS", ("orders", "products"))
        monkeypatch.setitem(OZON_TASK_MAX_AGES, "orders", 600)
        checks = _ozon_task_checks(session, now)

    assert checks[0].ok is True
    assert checks[1] == Check(False, "Ozon products sync", "no runs recorded")


def test_yandex_market_task_health_uses_independent_journal(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    now = datetime(2026, 9, 5, 12, 0, tzinfo=ZoneInfo("Europe/Moscow"))
    with session_factory() as session:
        session.add(YandexMarketSyncRun(
            id="run-1",
            task="orders",
            started_at=datetime(2026, 9, 5, 8, 55, tzinfo=ZoneInfo("UTC")),
            finished_at=datetime(2026, 9, 5, 8, 56, tzinfo=ZoneInfo("UTC")),
            status="completed",
        ))
        session.commit()
        monkeypatch.setattr("healthcheck.__main__.YANDEX_MARKET_REQUIRED_TASKS", ("orders", "catalog"))
        checks = _yandex_market_task_checks(session, now)

    assert checks[0].ok is True
    assert checks[1] == Check(False, "Yandex Market catalog sync", "no runs recorded")


def test_collect_checks_targets_independent_workers_instead_of_cron(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    calls = []

    monkeypatch.setattr("healthcheck.__main__.SessionLocal", session_factory)
    monkeypatch.setattr("healthcheck.__main__.YANDEX_MARKET_CAMPAIGN_IDS", ())
    monkeypatch.setattr("healthcheck.__main__.WB_TG_BOT_TOKEN", None)
    monkeypatch.setattr("healthcheck.__main__.WB_TG_CHAT_ID", None)
    monkeypatch.setattr("healthcheck.__main__.OPERATIONS_TG_BOT_TOKEN", None)
    monkeypatch.setattr("healthcheck.__main__.OPERATIONS_TG_CHAT_ID", None)
    monkeypatch.setattr("healthcheck.__main__.WB_DOCUMENT_SYNC_REQUIRED", False)
    monkeypatch.setattr("healthcheck.__main__.OZON_REQUIRED_TASKS", ())

    collect_checks(
        now=datetime(2026, 8, 20, 0, 1, tzinfo=ZoneInfo("Europe/Moscow")),
        systemctl=lambda unit: calls.append(unit) or (True, "active"),
    )

    assert calls == [
        "wbozon-inventory@wb.service",
        "wbozon-inventory@ozon.service",
        "wbozon-wb.service",
        "wbozon-wb-order-feed.timer",
    ]


def test_collect_checks_monitors_required_wb_document_worker(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    now = datetime(2026, 8, 31, 12, 0, tzinfo=ZoneInfo("Europe/Moscow"))
    with session_factory() as session:
        session.add(WBDocumentSyncRun(
            id="documents-run",
            started_at=datetime(2026, 8, 31, 7, 0, tzinfo=ZoneInfo("UTC")),
            finished_at=datetime(2026, 8, 31, 7, 5, tzinfo=ZoneInfo("UTC")),
            status="completed",
        ))
        session.commit()

    calls = []
    monkeypatch.setattr("healthcheck.__main__.SessionLocal", session_factory)
    monkeypatch.setattr("healthcheck.__main__.YANDEX_MARKET_CAMPAIGN_IDS", ())
    monkeypatch.setattr("healthcheck.__main__.WB_TG_BOT_TOKEN", None)
    monkeypatch.setattr("healthcheck.__main__.WB_TG_CHAT_ID", None)
    monkeypatch.setattr("healthcheck.__main__.OPERATIONS_TG_BOT_TOKEN", None)
    monkeypatch.setattr("healthcheck.__main__.OPERATIONS_TG_CHAT_ID", None)
    monkeypatch.setattr("healthcheck.__main__.WB_DOCUMENT_SYNC_REQUIRED", True)
    monkeypatch.setattr("healthcheck.__main__.OZON_REQUIRED_TASKS", ())

    checks = collect_checks(
        now=now,
        systemctl=lambda unit: calls.append(unit) or (True, "active"),
    )

    assert "wbozon-wb-documents.timer" in calls
    document_check = next(check for check in checks if check.name == "WB documents sync")
    assert document_check.ok is True


def test_healthcheck_journal_emits_only_failure_changes_and_recovery(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    monkeypatch.setattr("healthcheck.__main__.SessionLocal", session_factory)
    now = datetime(2026, 8, 31, 12, 0, tzinfo=ZoneInfo("Europe/Moscow"))
    failed = [Check(False, "Yandex inventory service", "inactive")]

    assert record_healthcheck(failed, now) == "failed"
    assert record_healthcheck(failed, now.replace(minute=5)) == "unchanged"
    assert record_healthcheck(
        [Check(True, "Yandex inventory service", "active")],
        now.replace(minute=10),
    ) == "recovered"
    assert record_healthcheck(
        [Check(True, "Yandex inventory service", "active")],
        now.replace(minute=15),
    ) == "healthy"

    with session_factory() as session:
        statuses = [
            row.status
            for row in session.query(HealthcheckRun).order_by(HealthcheckRun.checked_at)
        ]
    assert statuses == ["failed", "unchanged", "recovered", "healthy"]
