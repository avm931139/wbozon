import pytest
from dashboard.__main__ import HTML, PNL_HTML
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


def test_operational_dashboard_contains_only_operational_metrics():
    assert "Выкупленные товары" in HTML
    assert "Финансовый результат" not in HTML
    assert "v.buyouts_amount" in HTML
    assert "Оперативный дашборд" in HTML
    assert "每日订单" in HTML
    assert "bar.empty" in HTML
    assert "v.amount" in HTML
    assert "v.profit" not in HTML
    assert "v.revenue" not in HTML
    assert 'id="month" type="month"' in HTML
    assert "function selectMonth()" in HTML
    assert "start.setDate(now.getDate()-6)" in HTML


def test_pnl_dashboard_uses_only_financial_labels_and_separate_endpoint():
    assert "/api/pnl" in PNL_HTML
    assert "Только финансовые отчёты" in PNL_HTML
    assert "Все удержания МП" in PNL_HTML
    assert "v.profit" in PNL_HTML
    assert "v.revenue" in PNL_HTML
    assert "ROAS" not in PNL_HTML
    assert "v.orders_amount" not in PNL_HTML


def test_operational_service_does_not_query_finance_ledgers():
    import inspect

    source = inspect.getsource(DashboardService._operational_period_metrics)
    assert "wb_financial_sales_rows" not in source
    assert "ozon_finance_accruals" not in source
    assert "yandex_market_finance_transactions" not in source
    assert 'values["data_status"] = "operational"' in source


def test_dashboard_uses_historical_marketplace_order_sources():
    import inspect

    source = inspect.getsource(DashboardService._period_metrics)
    assert "wb_fbo_orders" in source
    assert "finance_buyouts" in source
    assert "OzonPosting" not in source
    assert "coalesce(price_with_discount,finished_price,total_price,0)" in source


def test_pnl_uses_finance_rows_for_yandex_cost_of_goods():
    import inspect

    source = inspect.getsource(DashboardService._period_metrics)
    assert "FROM yandex_market_finance_transactions" in source
    assert "yandex_market_order_items" not in source
    assert "united_netting" in source


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
