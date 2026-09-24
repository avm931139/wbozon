from datetime import date

from historical_refresh.service import HistoricalRefreshService


def test_rolling_history_refresh_runs_raw_steps_before_analytics(monkeypatch):
    calls = []

    monkeypatch.setattr(
        HistoricalRefreshService,
        "_raw_steps",
        staticmethod(lambda marketplace, start, finish, mode, include_advertising: [
            ("finance", lambda: calls.append(("finance", start, finish)) or {"rows": 1}),
            ("advertising", lambda: calls.append(("advertising", start, finish)) or {"rows": 2}),
        ]),
    )

    class Facts:
        def __init__(self, marketplace):
            self.marketplace = marketplace

        def run(self):
            calls.append(("analytics", self.marketplace))
            return {"status": "completed"}

    monkeypatch.setattr("historical_refresh.service.FinancialSalesFactService", Facts)
    service = HistoricalRefreshService(
        today=lambda: date(2026, 9, 24), lookback_days=10
    )

    result = service.run(marketplace="ozon", mode="rolling")

    assert result["status"] == "completed"
    assert result["marketplaces"]["ozon"]["date_from"] == "2026-09-15"
    assert calls == [
        ("finance", date(2026, 9, 15), date(2026, 9, 24)),
        ("advertising", date(2026, 9, 15), date(2026, 9, 24)),
        ("analytics", "ozon"),
    ]


def test_history_refresh_keeps_marketplaces_independent(monkeypatch):
    def steps(marketplace, start, finish, mode, include_advertising):
        def execute():
            if marketplace == "ozon":
                raise RuntimeError("rate limited")
            return {"rows": 1}

        return [("finance", execute)]

    monkeypatch.setattr(
        HistoricalRefreshService, "_raw_steps", staticmethod(steps)
    )
    monkeypatch.setattr(
        "historical_refresh.service.FinancialSalesFactService",
        lambda marketplace: type("Facts", (), {"run": lambda self: {"status": "completed"}})(),
    )

    result = HistoricalRefreshService(
        today=lambda: date(2026, 9, 24)
    ).run(marketplace="all", mode="full", include_advertising=False)

    assert result["status"] == "partial"
    assert result["marketplaces"]["wb"]["status"] == "completed"
    assert result["marketplaces"]["ozon"]["status"] == "partial"
    assert result["marketplaces"]["yandex_market"]["status"] == "completed"
    assert "rate limited" in result["marketplaces"]["ozon"]["finance_error"]


def test_yandex_rolling_advertising_processes_one_rate_limited_day(monkeypatch):
    calls = []

    class Finance:
        def sync_history(self, **kwargs):
            return kwargs

    class Advertising:
        def sync(self):
            calls.append("sync")
            return {"date": "2026-09-24"}

    monkeypatch.setattr(
        "historical_refresh.service.YandexMarketFinanceService", Finance
    )
    monkeypatch.setattr(
        "historical_refresh.service.YandexMarketAdvertisingService", Advertising
    )
    steps = HistoricalRefreshService._raw_steps(
        "yandex_market",
        date(2026, 5, 1),
        date(2026, 9, 24),
        mode="rolling",
        include_advertising=True,
    )
    dict((name, callback()) for name, callback in steps)

    assert calls == ["sync"]
