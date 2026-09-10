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
    with pytest.raises(ValueError): DashboardService.period("2099-01-01", "2099-01-01")


def test_operational_dashboard_contains_only_operational_metrics():
    assert "Выкупленные товары" in HTML
    assert "Финансовый результат" not in HTML
    assert "value.buyouts_amount" in HTML
    assert "Оперативный дашборд" in HTML
    assert "每日各平台订单额" in HTML
    assert "bar.empty" in HTML
    assert "value.amount" in HTML
    assert ".profit" not in HTML
    assert 'id="month" type="month"' in HTML
    assert "function selectMonth()" in HTML
    assert "start.setDate(now.getDate()-6)" in HTML
    assert "lastDay>now?now:lastDay" in HTML
    assert "monthInput.max=today.slice(0,7)" in HTML


def test_operational_dashboard_has_readable_semantic_comparisons_and_help():
    assert "Главное за период" in HTML
    assert "По площадкам" in HTML
    assert "сравнение с равным периодом" in HTML
    assert "points=false,neutral=false,label=''" in HTML
    assert "lowerBetter:true,points:true" in HTML
    assert "neutral:true,label:'расход'" in HTML
    assert 'data-tooltip=' in HTML
    assert "Доля = отменённые товары ÷ заказанные товары × 100%" in HTML
    assert "ROAS = атрибутированная сумма заказов ÷ рекламный расход" in HTML
    assert "Сегодняшний день ещё не завершён" in HTML
    assert "Доля общих заказов" in HTML
    assert "Средняя цена товара" in HTML
    assert "Среднее в день" in HTML
    assert "Прогноз заказов месяца" in HTML
    assert "function monthProjection" in HTML
    assert ".bar.wb" in HTML
    assert "marketKeys=['wb','ozon','yandex_market']" in HTML
    assert "height:${height}%" in HTML
    assert "WB Order Feed и FBO Orders" in HTML
    assert "Ozon Postings" in HTML
    assert "Yandex Market Orders API" in HTML


def test_operational_queries_compare_product_units_with_product_units():
    import inspect

    source = inspect.getsource(DashboardService._operational_period_metrics)
    assert "order_items" in source
    assert "cancelled_items" in source
    assert 'values.get("cancelled_items")' in source
    assert 'values.get("order_items")' in source


def test_cabinet_analytics_is_separate_and_exposes_ozon_realization_price():
    import inspect

    source = inspect.getsource(DashboardService._cabinet_analytics)
    assert "wb_sales_funnel_daily" in source
    assert "yandex_market_sales_analytics_daily" in source
    assert "seller_price*coalesce(p.quantity,0)" in source
    assert "average_realized_price" in source
    summary = inspect.getsource(DashboardService.summary)
    assert '"cabinet_analytics":cabinet' in summary
    assert "Кабинетная аналитика" in HTML
    assert "cabinetComparable=cabinet.complete&&oldCabinet.complete" in HTML
    assert "Реализовано по начислениям" in HTML


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


def test_yandex_advertising_uses_actual_marketing_charges_and_checks_coverage():
    import inspect

    source = inspect.getsource(DashboardService._advertising_metrics)
    assert "yandex_market_finance_transactions" in source
    assert "product_or_service ILIKE" in source
    assert "marketing_finance" in source
    assert "jsonb_path_query" in source
    assert "exists(@.type_id)" in source
    assert "t.name IN ('PayPerClick','Promotion')" in source
    assert "coverage_days" in source
    assert "attribution_complete" in source
    assert "attributionComplete" in HTML
    assert "рекламные отчёты загружаются" in HTML
    assert "Списано по финансовым данным" in HTML
    assert "sources=4" in source


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
    assert "Расход рекламного API" in HTML
    assert "Атрибутированная сумма заказов" in HTML


def test_dashboard_uses_cabinet_wide_wb_and_ozon_order_analytics():
    import inspect

    source = inspect.getsource(DashboardService._cabinet_analytics)
    assert "wb_sales_funnel_account_daily" in source
    assert "item_delta" in source
    assert "FROM ozon_daily_sales" in source
    assert "ordered_units" in source
    assert "Сверка итога с товарами" in HTML
    assert "Заказано по аналитике" in HTML
