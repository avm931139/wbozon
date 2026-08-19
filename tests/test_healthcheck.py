from datetime import datetime
from zoneinfo import ZoneInfo

from healthcheck.__main__ import Check, _error_message, _failure_signature, _systemctl_active


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
