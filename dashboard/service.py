from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import DASHBOARD_DATABASE_URL


def _number(value: Any) -> float:
    return float(Decimal(str(value or 0)))


class DashboardService:
    def __init__(self, session_factory: Callable[..., Any] | None = None) -> None:
        if session_factory is None:
            engine = create_engine(DASHBOARD_DATABASE_URL, future=True, pool_pre_ping=True)
            session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
        self.session_factory = session_factory

    @staticmethod
    def period(start: str | None, end: str | None) -> tuple[date, date]:
        today = date.today()
        finish = date.fromisoformat(end) if end else today
        begin = date.fromisoformat(start) if start else finish
        if begin > finish or finish > today or (finish - begin).days > 730:
            raise ValueError("invalid period")
        return begin, finish

    @staticmethod
    def previous_period(begin: date, finish: date) -> tuple[date, date]:
        days = (finish - begin).days + 1
        previous_finish = begin - timedelta(days=1)
        return previous_finish - timedelta(days=days - 1), previous_finish

    @staticmethod
    def _one(db: Any, sql: str, **params: Any) -> dict[str, Any]:
        try:
            return dict(db.execute(text(sql), params).mappings().one())
        except Exception as exc:
            db.rollback()
            return {"error": f"{type(exc).__name__}: {exc}"}

    def _advertising_metrics(self, db: Any, begin: date, finish: date) -> dict[str, Any]:
        """Return performance attribution and the actual Yandex marketing charge."""
        one = lambda sql, **params: self._one(db, sql, **params)
        result = {
            "wb": one("""SELECT performance.performance_spend,
                    performance.performance_spend spend,performance.attributed_revenue,
                    finance.finance_spend,'promotion_fullstats' spend_source,
                    'promotion_expenses' finance_spend_source
                FROM (SELECT coalesce(sum(spend),0) performance_spend,
                        coalesce(sum(order_sum),0) attributed_revenue
                    FROM wb_advert_daily_stats WHERE stat_date>=:b AND stat_date<CAST(:e AS date)+1) performance
                CROSS JOIN (SELECT greatest(coalesce(sum(amount),0),0) finance_spend
                    FROM wb_advert_expenses WHERE expense_time>=:b AND expense_time<CAST(:e AS date)+1) finance""",
                b=begin, e=finish),
            "ozon": one("""SELECT performance.performance_spend,
                    performance.performance_spend spend,performance.attributed_revenue,
                    finance.finance_spend,'performance_daily' spend_source,
                    'finance_accrual_by_day' finance_spend_source
                FROM (SELECT coalesce(sum(spend),0) performance_spend,
                        coalesce(sum(orders_money),0) attributed_revenue
                    FROM ozon_ad_daily_stats WHERE stat_date>=:b AND stat_date<=:e) performance
                CROSS JOIN (SELECT greatest(coalesce(-sum(a.amount),0),0) finance_spend
                    FROM ozon_finance_accruals a
                    LEFT JOIN ozon_finance_accrual_types t ON t.type_id=CASE
                        WHEN coalesce(a.raw_data->>'type_id','') ~ '^[0-9]+$'
                        THEN (a.raw_data->>'type_id')::integer END
                    WHERE a.accrual_date BETWEEN :b AND :e
                      AND t.name IN ('PayPerClick','Promotion')) finance""",
                b=begin, e=finish),
            "yandex_market": one("""WITH daily_coverage AS (
                    SELECT stat_date,count(DISTINCT source) sources
                    FROM yandex_market_ad_daily_stats
                    WHERE stat_date>=:b AND stat_date<=:e GROUP BY stat_date
                ), performance AS (
                    SELECT coalesce(sum(spend),0) performance_spend,
                        coalesce(sum(attributed_revenue),0) attributed_revenue
                    FROM yandex_market_ad_daily_stats WHERE stat_date>=:b AND stat_date<=:e
                ), expense AS (
                    SELECT greatest(coalesce(-sum(amount),0),0) spend
                    FROM yandex_market_finance_transactions
                    WHERE transaction_at>=:b AND transaction_at<CAST(:e AS date)+1
                      AND (product_or_service ILIKE '%буст%'
                           OR product_or_service ILIKE '%реклам%'
                           OR product_or_service ILIKE '%продвиж%'
                           OR product_or_service ILIKE '%полк%')
                ) SELECT performance.performance_spend,
                    performance.performance_spend spend,performance.attributed_revenue,
                    expense.spend finance_spend,
                    coalesce((SELECT count(*) FROM daily_coverage WHERE sources=4),0) coverage_days,
                    CAST(:e AS date)-CAST(:b AS date)+1 expected_days,
                    coalesce((SELECT count(*) FROM daily_coverage WHERE sources=4),0)
                        = CAST(:e AS date)-CAST(:b AS date)+1 attribution_complete,
                    'marketing_reports' spend_source,'marketing_reports' attribution_source,
                    'marketing_finance' finance_spend_source
                FROM expense CROSS JOIN performance""", b=begin, e=finish),
        }
        for key in ("wb", "ozon"):
            if "error" not in result[key]:
                result[key]["attribution_complete"] = True
        for values in result.values():
            self._convert(values)
        return result

    def _operational_period_metrics(self, db: Any, begin: date, finish: date) -> dict[str, Any]:
        """Return only fast-changing operational facts, never finance-ledger replacements."""
        until = finish + timedelta(days=1)
        one = lambda sql, **params: self._one(db, sql, **params)
        markets = {
            "wb": one("""WITH marketplace_orders AS (
                    SELECT srid,order_date,status,seller_price FROM wb_order_feed_orders WHERE is_mp IS TRUE
                    UNION ALL
                    SELECT srid,order_date,CASE WHEN is_cancel THEN 'cancel' ELSE 'active' END,
                        coalesce(price_with_discount,finished_price,total_price,0)
                    FROM wb_fbo_orders
                ) SELECT count(*) orders,count(*) order_items,coalesce(sum(seller_price),0) orders_amount,
                    count(*) FILTER (WHERE status='cancel') cancelled,
                    count(*) FILTER (WHERE status='cancel') cancelled_items,
                    coalesce(sum(seller_price) FILTER (WHERE status='cancel'),0) cancelled_amount,
                    (SELECT count(*) FROM wb_operational_sales WHERE operation_type='sale' AND event_date>=:b AND event_date<:u) buyouts,
                    (SELECT coalesce(sum(finished_price),0) FROM wb_operational_sales WHERE operation_type='sale' AND event_date>=:b AND event_date<:u) buyouts_amount
                FROM marketplace_orders WHERE order_date>=:b AND order_date<:u""", b=begin, u=until),
            "ozon": one("""WITH postings AS (SELECT order_id,order_number,posting_number,status,
                    coalesce((SELECT sum(coalesce((p->>'quantity')::int,0)) FROM jsonb_array_elements(products::jsonb) p),0) units,
                    coalesce((SELECT sum(coalesce((CASE WHEN jsonb_typeof(p->'price')='object' THEN coalesce(p->'price'->>'amount',p->'price'->>'value') ELSE p->>'price' END)::numeric,0)*coalesce((p->>'quantity')::int,0)) FROM jsonb_array_elements(products::jsonb) p),0) amount
                    FROM ozon_postings WHERE in_process_at>=:b AND in_process_at<:u)
                SELECT count(DISTINCT coalesce(order_id::text,order_number,posting_number)) orders,
                    coalesce(sum(units),0) order_items,
                    coalesce(sum(amount),0) orders_amount,
                    count(*) FILTER (WHERE lower(status) IN ('cancelled','canceled')) cancelled,
                    coalesce(sum(units) FILTER (WHERE lower(status) IN ('cancelled','canceled')),0) cancelled_items,
                    coalesce(sum(amount) FILTER (WHERE lower(status) IN ('cancelled','canceled')),0) cancelled_amount,
                    coalesce(sum(units) FILTER (WHERE lower(status)='delivered'),0) buyouts,
                    coalesce(sum(amount) FILTER (WHERE lower(status)='delivered'),0) buyouts_amount FROM postings""", b=begin, u=until),
            "yandex_market": one("""SELECT count(*) orders,coalesce(sum(items_count),0) order_items,coalesce(sum(total_amount),0) orders_amount,
                    count(*) FILTER (WHERE status='CANCELLED') cancelled,
                    coalesce(sum(items_count) FILTER (WHERE status='CANCELLED'),0) cancelled_items,
                    coalesce(sum(total_amount) FILTER (WHERE status='CANCELLED'),0) cancelled_amount,
                    coalesce(sum(items_count) FILTER (WHERE status='DELIVERED'),0) buyouts,
                    coalesce(sum(total_amount) FILTER (WHERE status='DELIVERED'),0) buyouts_amount
                FROM yandex_market_orders WHERE created_at>=:b AND created_at<:u""", b=begin, u=until),
        }
        ads = self._advertising_metrics(db, begin, finish)
        for values in markets.values():
            if "error" not in values:
                ordered_items = _number(values.get("order_items"))
                values["cancel_rate"] = _number(values.get("cancelled_items")) / ordered_items * 100 if ordered_items else 0
                values["data_status"] = "operational"
            self._convert(values)
        return {"marketplaces": markets, "ads": ads}

    def _cabinet_analytics(self, db: Any, begin: date, finish: date) -> dict[str, Any]:
        """Return cohort/cabinet facts beside, never instead of, operational orders."""
        one = lambda sql, **params: self._one(db, sql, **params)
        expected_days = (finish - begin).days + 1
        result = {
            "wb": one("""WITH product_metrics AS (
                    SELECT coalesce(sum(open_count),0) product_views,
                        coalesce(sum(order_count),0) product_ordered_items,
                        coalesce(sum(order_sum),0) product_ordered_amount
                    FROM wb_sales_funnel_daily WHERE stat_date BETWEEN :b AND :e
                ), account_metrics AS (
                    SELECT coalesce(sum(open_count),0) views,coalesce(sum(cart_count),0) to_cart,
                        coalesce(sum(order_count),0) ordered_items,coalesce(sum(order_sum),0) ordered_amount,
                        coalesce(sum(buyout_count),0) purchased_items,coalesce(sum(buyout_sum),0) purchased_amount,
                        count(DISTINCT stat_date) coverage_days
                    FROM wb_sales_funnel_account_daily WHERE stat_date BETWEEN :b AND :e
                ) SELECT account_metrics.*,product_metrics.*,
                    account_metrics.ordered_items-product_metrics.product_ordered_items item_delta,
                    account_metrics.ordered_amount-product_metrics.product_ordered_amount amount_delta,
                    CAST(:e AS date)-CAST(:b AS date)+1 expected_days,
                    account_metrics.coverage_days=CAST(:e AS date)-CAST(:b AS date)+1 complete,
                    'WB Sales Funnel grouped/history' source
                FROM product_metrics CROSS JOIN account_metrics""", b=begin, e=finish),
            "ozon": one("""WITH analytics AS (
                    SELECT coalesce(sum(ordered_units),0) ordered_items,
                        coalesce(sum(revenue),0) ordered_amount,
                        coalesce(sum(delivered_units),0) delivered_items,
                        coalesce(sum(returns),0) analytics_returns,
                        coalesce(sum(cancellations),0) cancelled_items,
                        count(DISTINCT sale_date) coverage_days
                    FROM ozon_daily_sales WHERE sale_date BETWEEN :b AND :e
                ), realization AS (SELECT
                    coalesce(sum(coalesce(p.quantity,0)) FILTER (WHERE p.seller_price>0),0) realized_items,
                    coalesce(sum(p.seller_price*coalesce(p.quantity,0)) FILTER (WHERE p.seller_price>0),0) realized_amount,
                    coalesce(sum(coalesce(p.quantity,0)) FILTER (WHERE p.seller_price<0),0) returned_items,
                    CASE WHEN coalesce(sum(coalesce(p.quantity,0)) FILTER (WHERE p.seller_price>0),0)>0
                        THEN sum(p.seller_price*coalesce(p.quantity,0)) FILTER (WHERE p.seller_price>0)
                            /sum(coalesce(p.quantity,0)) FILTER (WHERE p.seller_price>0)
                        ELSE 0 END average_realized_price,
                    min(p.accrual_date) data_from,max(p.accrual_date) data_to
                FROM ozon_finance_posting_accruals p
                JOIN ozon_finance_accrual_types t ON t.type_id=p.type_id
                WHERE t.name='SaleCommission' AND p.accrual_date BETWEEN :b AND :e)
                SELECT analytics.*,realization.*,
                    CAST(:e AS date)-CAST(:b AS date)+1 expected_days,
                    analytics.coverage_days=CAST(:e AS date)-CAST(:b AS date)+1 complete,
                    'Ozon analytics/data + accrual/postings' source
                FROM analytics CROSS JOIN realization""", b=begin, e=finish),
            "yandex_market": one("""WITH metrics AS (
                    SELECT coalesce(sum(shows),0) views,coalesce(sum(clicks),0) clicks,
                        coalesce(sum(to_cart),0) to_cart,
                        coalesce(sum(order_items),0) ordered_items,
                        coalesce(sum(order_items_amount),0) ordered_amount,
                        coalesce(sum(delivered_from_ordered_items),0) purchased_items,
                        coalesce(sum(delivered_from_ordered_amount),0) purchased_amount,
                        coalesce(sum(cancelled_items),0) cancelled_items,
                        coalesce(sum(returned_items),0) returned_items
                    FROM yandex_market_sales_analytics_daily
                    WHERE stat_date BETWEEN :b AND :e
                ), coverage AS (
                    SELECT EXISTS (
                        SELECT 1 FROM yandex_market_sync_runs run
                        WHERE run.task='analytics' AND run.status='completed'
                          AND CAST(run.result->>'date_from' AS date)<=CAST(:b AS date)
                          AND CAST(run.result->>'date_to' AS date)>=CAST(:e AS date)
                    ) complete
                ) SELECT metrics.*,
                    CASE WHEN coverage.complete THEN CAST(:e AS date)-CAST(:b AS date)+1 ELSE 0 END coverage_days,
                    CAST(:e AS date)-CAST(:b AS date)+1 expected_days,coverage.complete,
                    'Yandex Market Sales Analytics' source
                FROM metrics CROSS JOIN coverage""", b=begin, e=finish),
        }
        for values in result.values():
            self._convert(values)
        return result

    def _period_metrics(self, db: Any, begin: date, finish: date) -> dict[str, Any]:
        until = finish + timedelta(days=1)
        one = lambda sql, **params: self._one(db, sql, **params)
        wb = one("""WITH marketplace_orders AS (
            SELECT srid,order_date,status,seller_price FROM wb_order_feed_orders WHERE is_mp IS TRUE
            UNION ALL
            SELECT srid,order_date,CASE WHEN is_cancel THEN 'cancel' ELSE 'active' END,
                coalesce(price_with_discount,finished_price,total_price,0)
            FROM wb_fbo_orders
        ) SELECT count(*) orders,
            coalesce(sum(seller_price),0) orders_amount,
            count(*) FILTER (WHERE status='cancel') cancelled,
            coalesce(sum(seller_price) FILTER (WHERE status='cancel'),0) cancelled_amount,
            (SELECT count(*) FROM wb_operational_sales WHERE operation_type='sale' AND event_date>=:b AND event_date<:u) buyouts,
            (SELECT coalesce(sum(finished_price),0) FROM wb_operational_sales WHERE operation_type='sale' AND event_date>=:b AND event_date<:u) buyouts_amount,
            (SELECT min(event_date) FROM wb_operational_sales) operational_from
            FROM marketplace_orders WHERE order_date>=:b AND order_date<:u""", b=begin, u=until)
        wb_funnel = one("""SELECT count(*) rows,min(stat_date) data_from,max(stat_date) data_to,
            coalesce(sum(order_count),0) orders,coalesce(sum(order_sum),0) orders_amount,
            coalesce(sum(buyout_count),0) buyouts,coalesce(sum(buyout_sum),0) buyouts_amount
            FROM wb_sales_funnel_daily WHERE stat_date>=:b AND stat_date<=:e""", b=begin, e=finish)
        ozon = one("""WITH postings AS (SELECT order_id,order_number,posting_number,status,
            coalesce((SELECT sum(coalesce((p->>'quantity')::int,0)) FROM jsonb_array_elements(products::jsonb) p),0) units,
            coalesce((SELECT sum(coalesce((CASE WHEN jsonb_typeof(p->'price')='object' THEN coalesce(p->'price'->>'amount',p->'price'->>'value') ELSE p->>'price' END)::numeric,0)*coalesce((p->>'quantity')::int,0)) FROM jsonb_array_elements(products::jsonb) p),0) amount
            FROM ozon_postings WHERE in_process_at>=:b AND in_process_at<:u)
            SELECT count(DISTINCT coalesce(order_id::text,order_number,posting_number)) orders,
            coalesce(sum(amount),0) orders_amount,
            count(*) FILTER (WHERE lower(status) IN ('cancelled','canceled')) cancelled,
            coalesce(sum(amount) FILTER (WHERE lower(status) IN ('cancelled','canceled')),0) cancelled_amount,
            coalesce(sum(units) FILTER (WHERE lower(status)='delivered'),0) buyouts,
            coalesce(sum(amount) FILTER (WHERE lower(status)='delivered'),0) buyouts_amount FROM postings""", b=begin, u=until)
        yandex = one("""SELECT count(*) orders,coalesce(sum(total_amount),0) orders_amount,
            count(*) FILTER (WHERE status='CANCELLED') cancelled,
            coalesce(sum(total_amount) FILTER (WHERE status='CANCELLED'),0) cancelled_amount,
            coalesce(sum(items_count) FILTER (WHERE status='DELIVERED'),0) buyouts,
            coalesce(sum(total_amount) FILTER (WHERE status='DELIVERED'),0) buyouts_amount
            FROM yandex_market_orders WHERE created_at>=:b AND created_at<:u""", b=begin, u=until)
        finances = {
            "wb": one("""WITH coverage AS (
                    SELECT min(date_from)::date finance_from,max(date_to)::date finance_through,
                        NOT EXISTS (
                            SELECT 1
                            FROM generate_series(CAST(:b AS date),CAST(:e AS date),interval '1 day') day
                            WHERE NOT EXISTS (
                                SELECT 1 FROM wb_financial_sales_reports report
                                WHERE report.details_synced_at IS NOT NULL
                                  AND day::date BETWEEN report.date_from::date AND report.date_to::date
                            )
                        ) covered
                    FROM wb_financial_sales_reports WHERE details_synced_at IS NOT NULL
                ), ledger AS (
                    SELECT count(*) rows,
                        coalesce(sum(CASE
                            WHEN seller_operation_name='Возврат' THEN -quantity
                            WHEN seller_operation_name IN ('Продажа','Бронирование товара через самовывоз') THEN quantity
                            ELSE 0 END),0) finance_buyouts,
                        coalesce(sum(CASE
                            WHEN seller_operation_name='Возврат' THEN -retail_price_with_discount*quantity
                            WHEN seller_operation_name IN ('Продажа','Бронирование товара через самовывоз') THEN retail_price_with_discount*quantity
                            ELSE 0 END),0) finance_buyouts_amount,
                        coalesce(sum(CASE WHEN seller_operation_name NOT IN ('Продажа','Возврат','Бронирование товара через самовывоз') THEN for_pay ELSE 0 END),0)
                            + coalesce(sum(additional_payment),0) compensation,
                        coalesce(sum(CASE
                            WHEN seller_operation_name='Возврат' THEN -for_pay
                            WHEN seller_operation_name IN ('Продажа','Бронирование товара через самовывоз') THEN for_pay
                            ELSE 0 END),0)
                            + coalesce(sum(CASE WHEN seller_operation_name NOT IN ('Продажа','Возврат','Бронирование товара через самовывоз') THEN for_pay ELSE 0 END),0)
                            + coalesce(sum(additional_payment),0)
                            - coalesce(sum(delivery_service+penalty+paid_storage+paid_acceptance),0) net_payout
                    FROM wb_financial_sales_rows WHERE rr_date>=:b AND rr_date<:u
                ) SELECT rows,finance_buyouts,finance_buyouts_amount,compensation,
                    finance_buyouts_amount+compensation revenue,
                    finance_buyouts_amount+compensation-net_payout expenses,
                    coverage.finance_from,coverage.finance_through,coverage.covered
                FROM ledger CROSS JOIN coverage""", b=begin, e=finish, u=until),
            "ozon": one("""WITH ledger AS (
                    SELECT count(*) rows,coalesce(sum(amount),0) net_accrual,
                        coalesce(sum(amount) FILTER (WHERE accrual_type='NON_ITEM' AND amount>0),0) compensation
                    FROM ozon_finance_accruals WHERE accrual_date>=:b AND accrual_date<=:e
                ), sales AS (
                    SELECT coalesce(sum(CASE WHEN p.seller_price<0 THEN -coalesce(p.quantity,0) ELSE coalesce(p.quantity,0) END),0) finance_buyouts,
                        coalesce(sum(coalesce(p.seller_price,0)*coalesce(p.quantity,0)),0) finance_buyouts_amount
                    FROM ozon_finance_posting_accruals p
                    JOIN ozon_finance_accrual_types t ON t.type_id=p.type_id
                    WHERE p.accrual_date>=:b AND p.accrual_date<=:e AND t.name='SaleCommission'
                ) SELECT ledger.rows,sales.finance_buyouts,sales.finance_buyouts_amount,
                    ledger.compensation,
                    sales.finance_buyouts_amount+ledger.compensation revenue,
                    sales.finance_buyouts_amount+ledger.compensation-ledger.net_accrual expenses
                FROM ledger CROSS JOIN sales""", b=begin, e=finish),
            "yandex_market": one("""SELECT coalesce(sum(amount) FILTER (WHERE amount>0),0) revenue,
                abs(coalesce(sum(amount) FILTER (WHERE amount<0),0)) expenses,count(*) rows,
                coalesce(sum(CASE WHEN transaction_type='Начисление' AND amount>0 AND offer_id IS NOT NULL THEN quantity
                    WHEN transaction_type='Возврат' AND amount<0 AND offer_id IS NOT NULL THEN -quantity ELSE 0 END),0) finance_buyouts
                FROM yandex_market_finance_transactions WHERE transaction_at>=:b AND transaction_at<:u""", b=begin, u=until),
        }
        costs = {
            "wb": one("""WITH c AS (SELECT DISTINCT ON (master_product_id) master_product_id,unit_cost FROM product_cost_records ORDER BY master_product_id,effective_at DESC,id DESC),
                operational AS (SELECT coalesce(sum(coalesce(c.unit_cost,0)),0) cost_of_goods,count(*) FILTER (WHERE c.unit_cost IS NOT NULL) costed_units
                    FROM wb_operational_sales s LEFT JOIN marketplace_product_links l ON l.marketplace='wb' AND l.active AND l.external_product_id=s.nm_id::text
                    LEFT JOIN c ON c.master_product_id=l.master_product_id WHERE s.operation_type='sale' AND s.event_date>=:b AND s.event_date<:u),
                financial AS (SELECT coalesce(sum((CASE WHEN s.seller_operation_name='Возврат' THEN -s.quantity ELSE s.quantity END)*coalesce(c.unit_cost,0)) FILTER (WHERE s.seller_operation_name IN ('Продажа','Возврат','Бронирование товара через самовывоз')),0) cost_of_goods,
                    coalesce(sum((CASE WHEN s.seller_operation_name='Возврат' THEN -s.quantity ELSE s.quantity END)) FILTER (WHERE s.seller_operation_name IN ('Продажа','Возврат','Бронирование товара через самовывоз') AND c.unit_cost IS NOT NULL),0) costed_units
                    FROM wb_financial_sales_rows s LEFT JOIN marketplace_product_links l ON l.marketplace='wb' AND l.active AND l.external_product_id=s.nm_id::text
                    LEFT JOIN c ON c.master_product_id=l.master_product_id WHERE s.rr_date>=:b AND s.rr_date<:u)
                SELECT operational.cost_of_goods,operational.costed_units,
                    financial.cost_of_goods finance_cost_of_goods,financial.costed_units finance_costed_units,
                    funnel.cost_of_goods funnel_cost_of_goods,funnel.costed_units funnel_costed_units
                FROM operational CROSS JOIN financial CROSS JOIN (
                    SELECT coalesce(sum(f.buyout_count*coalesce(c.unit_cost,0)),0) cost_of_goods,
                        coalesce(sum(f.buyout_count) FILTER (WHERE c.unit_cost IS NOT NULL),0) costed_units
                    FROM wb_sales_funnel_daily f
                    LEFT JOIN marketplace_product_links l ON l.marketplace='wb' AND l.active AND l.external_product_id=f.nm_id::text
                    LEFT JOIN c ON c.master_product_id=l.master_product_id
                    WHERE f.stat_date>=:b AND f.stat_date<=:e
                ) funnel""", b=begin, e=finish, u=until),
            "ozon": one("""WITH c AS (SELECT DISTINCT ON (master_product_id) master_product_id,unit_cost FROM product_cost_records ORDER BY master_product_id,effective_at DESC,id DESC),
                sku_master AS (SELECT DISTINCT ON (p.sku) p.sku,l.master_product_id
                    FROM ozon_products p JOIN marketplace_product_links l ON l.marketplace='ozon' AND l.active AND l.external_product_id=p.product_id::text
                    WHERE p.sku IS NOT NULL ORDER BY p.sku,l.id),
                sold AS (SELECT p.sku,CASE WHEN p.seller_price<0 THEN -coalesce(p.quantity,0) ELSE coalesce(p.quantity,0) END quantity
                    FROM ozon_finance_posting_accruals p JOIN ozon_finance_accrual_types t ON t.type_id=p.type_id
                    WHERE t.name='SaleCommission' AND p.accrual_date>=:b AND p.accrual_date<=:e)
                SELECT coalesce(sum(s.quantity*coalesce(c.unit_cost,0)),0) cost_of_goods,
                    coalesce(sum(s.quantity) FILTER (WHERE c.unit_cost IS NOT NULL),0) costed_units
                FROM sold s LEFT JOIN sku_master m ON m.sku=s.sku LEFT JOIN c ON c.master_product_id=m.master_product_id""", b=begin, e=finish),
            "yandex_market": one("""WITH c AS (SELECT DISTINCT ON (master_product_id) master_product_id,unit_cost FROM product_cost_records ORDER BY master_product_id,effective_at DESC,id DESC),
                sold AS (SELECT business_id,offer_id,
                    sum(CASE WHEN transaction_type='Начисление' AND amount>0 THEN quantity
                        WHEN transaction_type='Возврат' AND amount<0 THEN -quantity ELSE 0 END) quantity
                    FROM yandex_market_finance_transactions
                    WHERE transaction_at>=:b AND transaction_at<:u AND offer_id IS NOT NULL GROUP BY business_id,offer_id)
                SELECT coalesce(sum(s.quantity*coalesce(c.unit_cost,0)),0) cost_of_goods,
                    coalesce(sum(s.quantity) FILTER (WHERE c.unit_cost IS NOT NULL),0) costed_units
                FROM sold s LEFT JOIN marketplace_product_links l ON l.marketplace='yandex_market' AND l.active
                    AND l.account_id=s.business_id::text AND l.external_product_id=s.offer_id
                LEFT JOIN c ON c.master_product_id=l.master_product_id""", b=begin, u=until),
        }
        ads = self._advertising_metrics(db, begin, finish)
        markets = {"wb": wb, "ozon": ozon, "yandex_market": yandex}
        wb_finance_exact = "error" not in finances["wb"] and bool(finances["wb"].get("covered"))
        if wb_finance_exact:
            finances["wb"]["available"] = True
            wb["buyouts"] = finances["wb"].get("finance_buyouts", 0)
            wb["buyouts_amount"] = finances["wb"].get("finance_buyouts_amount", 0)
            costs["wb"]["cost_of_goods"] = costs["wb"].get("finance_cost_of_goods", 0)
            costs["wb"]["costed_units"] = costs["wb"].get("finance_costed_units", 0)
            wb["buyouts_source"] = "financial_report"
            wb["data_status"] = "exact"
        else:
            if "error" not in wb_funnel and wb_funnel.get("rows", 0):
                for field in ("orders", "orders_amount", "buyouts", "buyouts_amount"):
                    wb[field] = wb_funnel.get(field, 0)
                costs["wb"]["cost_of_goods"] = costs["wb"].get("funnel_cost_of_goods", 0)
                costs["wb"]["costed_units"] = costs["wb"].get("funnel_costed_units", 0)
                wb["buyouts_source"] = "sales_funnel"
                wb["preliminary_from"] = wb_funnel.get("data_from")
                wb["preliminary_to"] = wb_funnel.get("data_to")
            else:
                wb["buyouts_source"] = "operational_sales_fallback"
            wb["data_status"] = "preliminary"
            finances["wb"] = {
                "rows": 0,
                "revenue": wb.get("buyouts_amount", 0),
                "expenses": None,
                "notice": "closed WB financial report does not cover the full period",
            }
        if "error" not in finances["ozon"] and finances["ozon"].get("rows", 0):
            ozon["buyouts"] = finances["ozon"].get("finance_buyouts", 0)
            ozon["buyouts_amount"] = finances["ozon"].get("finance_buyouts_amount", 0)
            ozon["buyouts_source"] = "finance_accruals"
        if "error" not in finances["yandex_market"] and finances["yandex_market"].get("rows", 0):
            yandex["buyouts"] = finances["yandex_market"].get("finance_buyouts", 0)
            yandex["buyouts_source"] = "united_netting"
        for key, values in markets.items():
            self._complete(values, finances[key], costs[key])
        for item in (*markets.values(), *ads.values()):
            self._convert(item)
        return {"marketplaces": markets, "ads": ads}

    @staticmethod
    def _complete(values: dict[str, Any], finance: dict[str, Any], costs: dict[str, Any]) -> None:
        if "error" in values:
            return
        orders = _number(values.get("orders"))
        buyouts = _number(values.get("buyouts"))
        values["cancel_rate"] = _number(values.get("cancelled")) / orders * 100 if orders else 0
        values.update(costs)
        values["cost_coverage"] = _number(costs.get("costed_units")) / buyouts * 100 if buyouts else 100
        values["cost_missing"] = buyouts > _number(costs.get("costed_units"))
        if values.get("data_status") == "preliminary":
            values.update({"compensation": None, "revenue": _number(values.get("buyouts_amount")),
                "expenses": None, "expense_ratio": None, "profit": None, "profit_margin": None,
                "finance_notice": finance.get("notice")})
            return
        if finance.get("expenses") is None or "error" in finance or (
            finance.get("rows") == 0 and not finance.get("available")
        ):
            values.update({"compensation": None, "revenue": None, "expenses": None, "expense_ratio": None, "profit": None, "profit_margin": None, "finance_notice": finance.get("notice") or finance.get("error")})
            return
        compensation = _number(finance.get("compensation"))
        revenue = _number(finance.get("revenue")) if finance.get("revenue") is not None else _number(values.get("buyouts_amount")) + compensation
        expenses = _number(finance.get("expenses"))
        profit = revenue - expenses - _number(costs.get("cost_of_goods"))
        values.update({"compensation": compensation, "revenue": revenue, "expenses": expenses,
            "expense_ratio": expenses/revenue*100 if revenue else 0, "profit": profit,
            "profit_margin": profit/revenue*100 if revenue else 0})

    def _stocks(self, db: Any) -> dict[str, Any]:
        c = """WITH c AS (SELECT DISTINCT ON (master_product_id) master_product_id,unit_cost FROM product_cost_records ORDER BY master_product_id,effective_at DESC,id DESC),"""
        stocks = {
            "wb": self._one(db, c + """ s AS (SELECT p.nm_id::text k,x.quantity q FROM wb_fbs_stocks x JOIN wb_product_sizes z ON z.id=x.size_id JOIN wb_products p ON p.id=z.product_id UNION ALL SELECT p.nm_id::text,x.quantity FROM wb_fbo_stocks x JOIN wb_product_sizes z ON z.id=x.size_id JOIN wb_products p ON p.id=z.product_id) SELECT coalesce(sum(s.q),0) units,coalesce(sum(s.q*coalesce(c.unit_cost,0)),0) cost_value FROM s LEFT JOIN marketplace_product_links l ON l.marketplace='wb' AND l.active AND l.external_product_id=s.k LEFT JOIN c ON c.master_product_id=l.master_product_id"""),
            "ozon": self._one(db, c + """ s AS (SELECT product_id::text k,sum(present) q FROM ozon_stocks GROUP BY product_id) SELECT coalesce(sum(s.q),0) units,coalesce(sum(s.q*coalesce(c.unit_cost,0)),0) cost_value FROM s LEFT JOIN marketplace_product_links l ON l.marketplace='ozon' AND l.active AND l.external_product_id=s.k LEFT JOIN c ON c.master_product_id=l.master_product_id"""),
            "yandex_market": self._one(db, c + """ s AS (SELECT offer_id k,sum(count) q FROM yandex_market_stocks WHERE stock_type='AVAILABLE' GROUP BY offer_id) SELECT coalesce(sum(s.q),0) units,coalesce(sum(s.q*coalesce(c.unit_cost,0)),0) cost_value FROM s LEFT JOIN marketplace_product_links l ON l.marketplace='yandex_market' AND l.active AND l.external_product_id=s.k LEFT JOIN c ON c.master_product_id=l.master_product_id"""),
        }
        for item in stocks.values(): self._convert(item)
        return stocks

    def _historical_stocks(self, db: Any, as_of: date) -> dict[str, Any]:
        c = """WITH c AS (SELECT DISTINCT ON (master_product_id) master_product_id,unit_cost FROM product_cost_records ORDER BY master_product_id,effective_at DESC,id DESC),"""
        stocks = {
            "wb": self._one(db, c + """ s AS (SELECT p.nm_id::text k,x.quantity q FROM wb_fbs_stock_snapshots x JOIN wb_product_sizes z ON z.id=x.size_id JOIN wb_products p ON p.id=z.product_id WHERE x.snapshot_date=(SELECT max(snapshot_date) FROM wb_fbs_stock_snapshots WHERE snapshot_date<=:d) UNION ALL SELECT p.nm_id::text,x.quantity FROM wb_fbo_stock_snapshots x JOIN wb_product_sizes z ON z.id=x.size_id JOIN wb_products p ON p.id=z.product_id WHERE x.snapshot_date=(SELECT max(snapshot_date) FROM wb_fbo_stock_snapshots WHERE snapshot_date<=:d)) SELECT coalesce(sum(s.q),0) units,coalesce(sum(s.q*coalesce(c.unit_cost,0)),0) cost_value FROM s LEFT JOIN marketplace_product_links l ON l.marketplace='wb' AND l.active AND l.external_product_id=s.k LEFT JOIN c ON c.master_product_id=l.master_product_id""", d=as_of),
            "ozon": self._one(db, c + """ s AS (SELECT product_id::text k,sum(present) q FROM ozon_stock_snapshots WHERE snapshot_date=(SELECT max(snapshot_date) FROM ozon_stock_snapshots WHERE snapshot_date<=:d) GROUP BY product_id) SELECT coalesce(sum(s.q),0) units,coalesce(sum(s.q*coalesce(c.unit_cost,0)),0) cost_value FROM s LEFT JOIN marketplace_product_links l ON l.marketplace='ozon' AND l.active AND l.external_product_id=s.k LEFT JOIN c ON c.master_product_id=l.master_product_id""", d=as_of),
            "yandex_market": self._one(db, c + """ s AS (SELECT offer_id k,sum(count) q FROM yandex_market_stock_snapshots WHERE stock_type='AVAILABLE' AND snapshot_date=(SELECT max(snapshot_date) FROM yandex_market_stock_snapshots WHERE snapshot_date<=:d) GROUP BY offer_id) SELECT coalesce(sum(s.q),0) units,coalesce(sum(s.q*coalesce(c.unit_cost,0)),0) cost_value FROM s LEFT JOIN marketplace_product_links l ON l.marketplace='yandex_market' AND l.active AND l.external_product_id=s.k LEFT JOIN c ON c.master_product_id=l.master_product_id""", d=as_of),
        }
        for item in stocks.values(): self._convert(item)
        return stocks

    @staticmethod
    def _convert(item: dict[str, Any]) -> None:
        for key, value in list(item.items()):
            if isinstance(value, Decimal): item[key] = _number(value)

    def summary(self, start: str | None, end: str | None) -> dict[str, Any]:
        begin, finish = self.period(start, end)
        previous_begin, previous_finish = self.previous_period(begin, finish)
        until = finish + timedelta(days=1)
        with self.session_factory() as db:
            current = self._operational_period_metrics(db, begin, finish)
            previous = self._operational_period_metrics(db, previous_begin, previous_finish)
            cabinet = self._cabinet_analytics(db, begin, finish)
            previous_cabinet = self._cabinet_analytics(db, previous_begin, previous_finish)
            stocks = self._stocks(db)
            previous_stocks = self._historical_stocks(db, previous_finish)
            prices = self._one(db, "SELECT count(*) active,count(*) FILTER (WHERE in_promotion IS TRUE) promotions,count(*) FILTER (WHERE coalesce(seller_price,customer_price,list_price,0)<=0) invalid FROM marketplace_current_prices WHERE active IS TRUE")
            wb_series = """SELECT order_date::date report_day,'wb' marketplace,count(*) orders,
                    coalesce(sum(seller_price),0) revenue FROM (
                        SELECT order_date,seller_price FROM wb_order_feed_orders WHERE is_mp IS TRUE
                        UNION ALL
                        SELECT order_date,coalesce(price_with_discount,finished_price,total_price,0) FROM wb_fbo_orders
                    ) wb_orders WHERE order_date>=:b AND order_date<:u GROUP BY 1"""
            series_result = self._one(db, """SELECT coalesce(json_agg(d ORDER BY report_day,marketplace),'[]'::json) data
                FROM (SELECT report_day,marketplace,sum(orders) orders,sum(revenue) revenue FROM (
                    """ + wb_series + """
                    UNION ALL
                    SELECT in_process_at::date,'ozon',
                        coalesce(sum((SELECT sum(coalesce((p->>'quantity')::int,0))
                            FROM jsonb_array_elements(products::jsonb) p)),0),
                        coalesce(sum((SELECT sum(coalesce(
                            (CASE WHEN jsonb_typeof(p->'price')='object'
                                THEN coalesce(p->'price'->>'amount',p->'price'->>'value')
                                ELSE p->>'price' END)::numeric,0)
                            * coalesce((p->>'quantity')::int,0))
                            FROM jsonb_array_elements(products::jsonb) p)),0)
                    FROM ozon_postings WHERE in_process_at>=:b AND in_process_at<:u GROUP BY 1
                    UNION ALL
                    SELECT created_at::date,'yandex_market',coalesce(sum(items_count),0),coalesce(sum(total_amount),0)
                    FROM yandex_market_orders WHERE created_at>=:b AND created_at<:u GROUP BY 1
                ) x GROUP BY report_day,marketplace) d""", b=begin, u=until)
        self._convert(prices)
        raw = series_result.get("data", []) if "error" not in series_result else []
        series = [{**dict(row), "day": str(row["report_day"]), "revenue": _number(row["revenue"])} for row in raw]
        return {"period":{"from":begin.isoformat(),"to":finish.isoformat()},"previous_period":{"from":previous_begin.isoformat(),"to":previous_finish.isoformat()},"marketplaces":current["marketplaces"],"previous_marketplaces":previous["marketplaces"],"cabinet_analytics":cabinet,"previous_cabinet_analytics":previous_cabinet,"ads":current["ads"],"previous_ads":previous["ads"],"stocks":stocks,"previous_stocks":previous_stocks,"prices":prices,"series":series,"series_error":series_result.get("error")}

    @staticmethod
    def _pnl_view(values: dict[str, Any], marketplace: str) -> dict[str, Any]:
        exact = "error" not in values and values.get("revenue") is not None and values.get("data_status") != "preliminary"
        source = {
            "wb": "детализация отчётов реализации WB",
            "ozon": "отчёт Ozon по начислениям и начисления по отправлениям",
            "yandex_market": "отчёт Яндекс Маркета united-netting",
        }[marketplace]
        if not exact:
            return {"available": False, "source": source, "notice": values.get("finance_notice") or values.get("error") or "финансовый отчёт не покрывает весь выбранный период"}
        revenue = _number(values.get("revenue"))
        expenses = _number(values.get("expenses"))
        cost = _number(values.get("cost_of_goods"))
        return {
            "available": True, "source": source,
            "revenue": revenue, "compensation": values.get("compensation"),
            "expenses": expenses, "expense_ratio": expenses / revenue * 100 if revenue else 0,
            "net_payout": revenue - expenses, "cost_of_goods": cost,
            "cost_missing": bool(values.get("cost_missing")),
            "profit": revenue - expenses - cost,
            "profit_margin": (revenue - expenses - cost) / revenue * 100 if revenue else 0,
            "sold_units": values.get("buyouts"),
            "finance_from": values.get("finance_from"), "finance_through": values.get("finance_through"),
        }

    def pnl(self, start: str | None, end: str | None) -> dict[str, Any]:
        begin, finish = self.period(start, end)
        previous_begin, previous_finish = self.previous_period(begin, finish)
        with self.session_factory() as db:
            current_raw = self._period_metrics(db, begin, finish)["marketplaces"]
            previous_raw = self._period_metrics(db, previous_begin, previous_finish)["marketplaces"]
        current = {key: self._pnl_view(values, key) for key, values in current_raw.items()}
        previous = {key: self._pnl_view(values, key) for key, values in previous_raw.items()}
        available = [values for values in current.values() if values.get("available")]
        total_revenue = sum(_number(values.get("revenue")) for values in available)
        total_expenses = sum(_number(values.get("expenses")) for values in available)
        total_cost = sum(_number(values.get("cost_of_goods")) for values in available)
        return {
            "period": {"from": begin.isoformat(), "to": finish.isoformat()},
            "previous_period": {"from": previous_begin.isoformat(), "to": previous_finish.isoformat()},
            "marketplaces": current, "previous_marketplaces": previous,
            "total": {"covered": len(available), "revenue": total_revenue, "expenses": total_expenses,
                "cost_of_goods": total_cost, "net_payout": total_revenue - total_expenses,
                "profit": total_revenue - total_expenses - total_cost,
                "cost_missing": any(values.get("cost_missing") for values in available)},
        }
