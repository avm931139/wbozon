from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import OzonSyncRun
from healthcheck.__main__ import (
    Check,
    OZON_TASK_MAX_AGES,
    _error_message,
    _failure_signature,
    _ozon_task_checks,
    _systemctl_active,
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
