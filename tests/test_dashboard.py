import pytest
from dashboard.__main__ import HTML
from dashboard.service import DashboardService

def test_dashboard_period_defaults_to_current_day():
    start,end=DashboardService.period(None,None)
    assert start == end


def test_previous_period_has_equal_length_and_precedes_current():
    assert DashboardService.previous_period(
        DashboardService.period("2026-09-05", "2026-09-07")[0],
        DashboardService.period("2026-09-05", "2026-09-07")[1],
    ) == (
        DashboardService.period("2026-09-02", "2026-09-04")[0],
        DashboardService.period("2026-09-02", "2026-09-04")[1],
    )

def test_dashboard_rejects_reverse_or_oversized_period():
    with pytest.raises(ValueError): DashboardService.period("2026-09-02","2026-09-01")
    with pytest.raises(ValueError): DashboardService.period("2020-01-01","2026-09-01")


def test_dashboard_labels_actual_buyouts_instead_of_financial_result():
    assert "Выкупленные товары" in HTML
    assert "Финансовый результат" not in HTML
    assert "v.buyouts_amount" in HTML
    assert "收入" in HTML
    assert "利润" in HTML
    assert "每日订单" in HTML
    assert "bar.empty" in HTML
    assert "v.amount" in HTML
    assert "предварительный расчёт" in HTML
    assert "покрытие" not in HTML
    assert "есть товары без себестоимости" in HTML


def test_dashboard_uses_historical_marketplace_order_sources():
    import inspect

    source = inspect.getsource(DashboardService._period_metrics)
    assert "wb_fbo_orders" in source
    assert "finance_buyouts" in source
    assert "OzonPosting" not in source
    assert "coalesce(price_with_discount,finished_price,total_price,0)" in source


def test_dashboard_uses_wb_finance_rows_for_closed_period_metrics():
    import inspect

    source = inspect.getsource(DashboardService._period_metrics)
    assert "retail_price_with_discount*quantity" in source
    assert "finance_buyouts_amount+compensation-net_payout expenses" in source
    assert "wb_finance_exact" in source
    assert "wb_sales_funnel_daily" in source
    assert 'wb["data_status"] = "preliminary"' in source
    assert "Бронирование товара через самовывоз" in source
    net_payout_sql = source.split("net_payout", 1)[0].rsplit("coalesce(sum(", 1)[-1]
    assert "deduction" not in net_payout_sql
    assert "rebill_logistic_cost" not in net_payout_sql


def test_dashboard_uses_ozon_finance_accruals_for_buyouts_and_profit():
    import inspect

    source = inspect.getsource(DashboardService._period_metrics)
    assert "t.name='SaleCommission'" in source
    assert "finance_buyouts_amount" in source
    assert "sales.finance_buyouts_amount+ledger.compensation-ledger.net_accrual expenses" in source
    assert "p.seller_price<0" in source


def test_dashboard_labels_ozon_advertising_without_calling_it_revenue():
    assert "Рекламные кампании" in HTML
    assert "Атрибутированная сумма заказов" in HTML
