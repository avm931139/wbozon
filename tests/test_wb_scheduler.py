from datetime import date

import pytest

from wb.scheduler import SyncSettings, WBPeriodicSync


class RecordingService:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def call(**kwargs):
            self.calls.append((name, kwargs))
            return 1

        return call


def test_scheduler_runs_sections_in_dependency_order(monkeypatch):
    service = RecordingService()
    scheduler = WBPeriodicSync(
        service=service,
        settings=SyncSettings(
            interval_seconds=60,
            history_start=date(2026, 1, 1),
            promotion_lookback_days=7,
        ),
    )
    monkeypatch.setattr(scheduler, "_sync_incremental_fbs_orders", lambda: service.calls.append(("fbs_orders", {})) or 0)
    monkeypatch.setattr(scheduler, "_sales_start_date", lambda: date(2026, 1, 1))
    monkeypatch.setattr(scheduler, "_acquiring_start_date", lambda: date(2026, 1, 1))

    result = scheduler.run_cycle()

    assert [name for name, _ in service.calls] == [
        "sync_categories",
        "sync_products",
        "sync_fbs_warehouses",
        "fbs_orders",
        "sync_sales_operations",
        "sync_fbw_supplies_max_history",
        "sync_financial_sales_reports",
        "sync_financial_sales_details",
        "sync_financial_acquiring_reports",
        "sync_financial_acquiring_details",
        "sync_customer_communications",
        "sync_advertising",
    ]
    assert all(item["status"] == "ok" for item in result.values())


def test_scheduler_records_failure_and_continues():
    scheduler = WBPeriodicSync(service=RecordingService())
    calls = []

    def fail():
        calls.append("first")
        raise RuntimeError("broken")

    scheduler._tasks = lambda: [("first", fail), ("second", lambda: calls.append("second") or 2)]

    result = scheduler.run_cycle()

    assert calls == ["first", "second"]
    assert result["first"]["status"] == "error"
    assert result["second"]["result"] == 2


def test_scheduler_rejects_overlapping_cycle():
    scheduler = WBPeriodicSync(service=RecordingService())
    scheduler._running = True

    with pytest.raises(RuntimeError, match="already running"):
        scheduler.run_cycle()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"interval_seconds": 0},
        {"promotion_lookback_days": 0},
        {"fbs_order_overlap_days": -1},
        {"finance_overlap_days": -1},
    ],
)
def test_scheduler_validates_settings(kwargs):
    with pytest.raises(ValueError):
        SyncSettings(**kwargs)
