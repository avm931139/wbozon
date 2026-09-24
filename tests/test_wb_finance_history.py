from datetime import date

from wb.services.finance_service import FinanceService


def test_wb_finance_history_is_loaded_in_bounded_chunks(monkeypatch):
    service = FinanceService.__new__(FinanceService)
    calls = []

    for name in (
        "sync_sales_reports",
        "sync_sales_details",
        "sync_acquiring_reports",
        "sync_acquiring_details",
    ):
        monkeypatch.setattr(
            service,
            name,
            lambda begin, finish, name=name: calls.append((name, begin, finish)) or 1,
        )

    result = service.sync_history(date(2026, 1, 1), date(2026, 3, 5))

    assert result == {
        "date_from": "2026-01-01",
        "date_to": "2026-03-05",
        "chunks": 3,
        "sales_reports": 3,
        "sales_details": 3,
        "acquiring_reports": 3,
        "acquiring_details": 3,
    }
    assert [item[1:] for item in calls[::4]] == [
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 3, 3)),
        (date(2026, 3, 4), date(2026, 3, 5)),
    ]
