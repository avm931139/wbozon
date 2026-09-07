import pytest
from dashboard.__main__ import HTML
from dashboard.service import DashboardService

def test_dashboard_period_defaults_to_current_month():
    start,end=DashboardService.period(None,None)
    assert start.day==1 and end>=start

def test_dashboard_rejects_reverse_or_oversized_period():
    with pytest.raises(ValueError): DashboardService.period("2026-09-02","2026-09-01")
    with pytest.raises(ValueError): DashboardService.period("2020-01-01","2026-09-01")


def test_dashboard_labels_actual_buyouts_instead_of_financial_result():
    assert "Выкупленные товары" in HTML
    assert "Финансовый результат" not in HTML
    assert "v.buyouts_amount" in HTML
