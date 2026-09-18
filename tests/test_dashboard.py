import pytest
from dashboard.__main__ import HTML, PNL_HTML, STOCKS_HTML
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
    assert "Оперативные события / 实时事件 ${info(" in HTML
    assert "Кабинетная аналитика / 后台分析 ${info(" in HTML
    assert "Данные поступают почти в реальном времени" in HTML
    assert "Это воронка заказов, созданных в выбранном периоде" in HTML
    assert "Поздние выкупы, доставки, отмены и возвраты пересчитываются задним числом" in HTML
    assert "Процент выкупа / отмен" in HTML
    assert "cabinetPurchaseRate=ratio(cabinetPurchased,cabinetOrdered)" in HTML
    assert "useCabinetHeadline=key==='wb'&&cabinet.complete" in HTML
    assert "headlineAmount/days" in HTML
    assert "кабинетная аналитика':'оперативные данные'" in HTML
    assert 'class="analytics-note"' not in HTML


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
    assert "wb_sales_funnel_period_products" in source
    assert "period_metrics.ordered_items ELSE product_metrics.product_ordered_items" in source
    assert "yandex_market_sales_analytics_daily" in source
    assert "seller_price*coalesce(p.quantity,0)" in source
    assert "average_realized_price" in source
    summary = inspect.getsource(DashboardService.summary)
    assert '"cabinet_analytics":cabinet' in summary
    assert "Кабинетная аналитика" in HTML
    assert "Оперативные события" in HTML
    assert "cabinetComparable=cabinet.complete&&oldCabinet.complete" in HTML
    assert "Реализовано по начислениям" in HTML


def test_pnl_dashboard_uses_only_financial_labels_and_separate_endpoint():
    assert "/api/pnl" in PNL_HTML
    assert "Точные финансовые отчёты" in PNL_HTML
    assert "Все расходы МП" in PNL_HTML
    assert "value.profit" in PNL_HTML
    assert "value.revenue" in PNL_HTML
    assert "ROAS" not in PNL_HTML
    assert "value.orders_amount" not in PNL_HTML


def test_pnl_shows_expense_breakdown_comparisons_and_source_tooltips():
    import inspect

    assert 'class="info"' in PNL_HTML
    assert "Расшифровка расходов" in PNL_HTML
    assert "Расходы по категориям" in PNL_HTML
    assert "share_percent" in PNL_HTML
    assert "previous_total" in PNL_HTML
    assert "source_endpoint" in PNL_HTML
    assert "updated_at" in PNL_HTML
    assert "Процент = статья расходов ÷ выручка × 100%" in PNL_HTML
    assert 'class="total-layout"' in PNL_HTML
    assert 'class="total-summary"' in PNL_HTML
    assert 'class="total-breakdown"' in PNL_HTML
    assert "@media(max-width:1000px)" in PNL_HTML
    source = inspect.getsource(DashboardService._pnl_expense_breakdowns)
    assert "wb_financial_sales_rows" in source
    assert "ozon_finance_accruals" in source
    assert "jsonb_path_query" in source
    assert "ozon_finance_posting_accruals" in source
    assert "ozon_finance_accrual_types" in source
    assert "t.name='SaleCommission'" in source
    assert "yandex_market_finance_transactions" in source


def test_pnl_expense_lines_reconcile_to_authoritative_finance_total():
    lines = DashboardService._expense_lines(
        [{"key": "delivery", "label": "Доставка", "amount": 20}],
        revenue=200,
        expected_total=50,
        source="finance table",
    )

    assert sum(line["amount"] for line in lines) == 50
    assert lines[0]["category"] == "logistics"
    assert lines[0]["share_percent"] == 10
    assert lines[1]["key"] == "reconciliation_adjustment"


def test_pnl_expense_category_uses_stable_marketplace_operation_code():
    lines = DashboardService._expense_lines(
        [{"key": "PayPerClick", "label": "Оплата за клик", "amount": 25}],
        revenue=100,
        expected_total=25,
        source="Ozon finance detail",
    )

    assert lines[0]["category"] == "advertising"


def test_stock_dashboard_has_three_market_images_and_refresh_dates():
    assert "/api/stocks?date=" in STOCKS_HTML
    assert "Фото WB" in STOCKS_HTML
    assert "Фото Ozon" in STOCKS_HTML
    assert "Фото Яндекс" in STOCKS_HTML
    assert "WB · остаток / обновлено" in STOCKS_HTML
    assert "Ozon · остаток / обновлено" in STOCKS_HTML
    assert "Яндекс · остаток / обновлено" in STOCKS_HTML
    assert "только товары с остатком" in STOCKS_HTML
    assert 'href="/stocks"' in HTML
    assert 'href="/stocks"' in PNL_HTML


def test_stock_details_uses_current_rows_and_historical_snapshots():
    import inspect

    source = inspect.getsource(DashboardService.stock_details)
    assert "wb_warehouse_remains" in source
    assert "wb_warehouse_remain_snapshots" in source
    assert "Всего находится на складах" in source
    assert "wb_fbs_stocks" not in source
    assert "wb_fbo_stocks" not in source
    assert "ozon_stocks" in source
    assert "yandex_market_stocks" in source
    assert "ozon_stock_snapshots" in source
    assert "yandex_market_stock_snapshots" in source
    assert "snapshot_date<=:d" in source
    assert "marketplace_product_media" in source


def test_wb_dashboard_stock_total_excludes_seller_fbs_stock():
    import inspect

    current = inspect.getsource(DashboardService._stocks)
    historical = inspect.getsource(DashboardService._historical_stocks)
    assert "wb_warehouse_remains" in current
    assert "wb_warehouse_remain_snapshots" in historical
    assert "Всего находится на складах" in current
    assert "Всего находится на складах" in historical
    assert "wb_fbs_stocks" not in current
    assert "wb_fbo_stocks" not in current
    assert "wb_fbs_stock_snapshots" not in historical
    assert "wb_fbo_stock_snapshots" not in historical


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
    assert "Источник кабинетного периода" in HTML
    assert "Отменено и возвращено по воронке" in HTML
    assert "Заказано по аналитике" in HTML
