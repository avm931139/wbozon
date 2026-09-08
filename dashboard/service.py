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
        if begin > finish or (finish - begin).days > 730:
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
            "wb": one("""WITH ledger AS (
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
                            - coalesce(sum(delivery_service+penalty+rebill_logistic_cost+paid_storage+deduction+paid_acceptance),0) net_payout
                    FROM wb_financial_sales_rows WHERE rr_date>=:b AND rr_date<:u
                ) SELECT rows,finance_buyouts,finance_buyouts_amount,compensation,
                    finance_buyouts_amount+compensation revenue,
                    finance_buyouts_amount+compensation-net_payout expenses
                FROM ledger""", b=begin, u=until),
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
                abs(coalesce(sum(amount) FILTER (WHERE amount<0),0)) expenses,count(*) rows
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
                    financial.cost_of_goods finance_cost_of_goods,financial.costed_units finance_costed_units
                FROM operational CROSS JOIN financial""", b=begin, u=until),
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
            "yandex_market": one("""WITH c AS (SELECT DISTINCT ON (master_product_id) master_product_id,unit_cost FROM product_cost_records ORDER BY master_product_id,effective_at DESC,id DESC)
                SELECT coalesce(sum(i.count*coalesce(c.unit_cost,0)),0) cost_of_goods,coalesce(sum(i.count) FILTER (WHERE c.unit_cost IS NOT NULL),0) costed_units
                FROM yandex_market_order_items i JOIN yandex_market_orders o ON o.business_id=i.business_id AND o.order_id=i.order_id
                LEFT JOIN marketplace_product_links l ON l.marketplace='yandex_market' AND l.active AND l.account_id=i.business_id::text AND l.external_product_id=i.offer_id
                LEFT JOIN c ON c.master_product_id=l.master_product_id WHERE o.status='DELIVERED' AND o.created_at>=:b AND o.created_at<:u""", b=begin, u=until),
        }
        ads = {
            "wb": one("SELECT coalesce(sum(spend),0) spend,coalesce(sum(order_sum),0) attributed_revenue FROM wb_advert_daily_stats WHERE stat_date>=:b AND stat_date<=:e", b=begin, e=finish),
            "ozon": one("SELECT coalesce(sum(spend),0) spend,coalesce(sum(orders_money),0) attributed_revenue FROM ozon_ad_daily_stats WHERE stat_date>=:b AND stat_date<=:e", b=begin, e=finish),
            "yandex_market": one("SELECT coalesce(sum(spend),0) spend,coalesce(sum(attributed_revenue),0) attributed_revenue FROM yandex_market_ad_daily_stats WHERE stat_date>=:b AND stat_date<=:e", b=begin, e=finish),
        }
        markets = {"wb": wb, "ozon": ozon, "yandex_market": yandex}
        if "error" not in finances["wb"] and finances["wb"].get("rows", 0):
            wb["buyouts"] = finances["wb"].get("finance_buyouts", 0)
            wb["buyouts_amount"] = finances["wb"].get("finance_buyouts_amount", 0)
            costs["wb"]["cost_of_goods"] = costs["wb"].get("finance_cost_of_goods", 0)
            costs["wb"]["costed_units"] = costs["wb"].get("finance_costed_units", 0)
            wb["buyouts_source"] = "financial_report"
        else:
            wb["buyouts_source"] = "operational_sales"
        if "error" not in finances["ozon"] and finances["ozon"].get("rows", 0):
            ozon["buyouts"] = finances["ozon"].get("finance_buyouts", 0)
            ozon["buyouts_amount"] = finances["ozon"].get("finance_buyouts_amount", 0)
            ozon["buyouts_source"] = "finance_accruals"
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
        if finance.get("expenses") is None or "error" in finance or finance.get("rows") == 0:
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
            current = self._period_metrics(db, begin, finish)
            previous = self._period_metrics(db, previous_begin, previous_finish)
            stocks = self._stocks(db)
            previous_stocks = self._historical_stocks(db, previous_finish)
            prices = self._one(db, "SELECT count(*) active,count(*) FILTER (WHERE in_promotion IS TRUE) promotions,count(*) FILTER (WHERE coalesce(seller_price,customer_price,list_price,0)<=0) invalid FROM marketplace_current_prices WHERE active IS TRUE")
            series_result = self._one(db, """SELECT coalesce(json_agg(d ORDER BY report_day,marketplace),'[]'::json) data
                FROM (SELECT report_day,marketplace,sum(orders) orders,sum(revenue) revenue FROM (
                    SELECT order_date::date report_day,'wb' marketplace,count(*) orders,
                        coalesce(sum(seller_price),0) revenue FROM (
                            SELECT order_date,seller_price FROM wb_order_feed_orders WHERE is_mp IS TRUE
                            UNION ALL
                            SELECT order_date,coalesce(price_with_discount,finished_price,total_price,0) FROM wb_fbo_orders
                        ) wb_orders WHERE order_date>=:b AND order_date<:u GROUP BY 1
                    UNION ALL
                    SELECT in_process_at::date,'ozon',
                        count(DISTINCT coalesce(order_id::text,order_number,posting_number)),
                        coalesce(sum((SELECT sum(coalesce(
                            (CASE WHEN jsonb_typeof(p->'price')='object'
                                THEN coalesce(p->'price'->>'amount',p->'price'->>'value')
                                ELSE p->>'price' END)::numeric,0)
                            * coalesce((p->>'quantity')::int,0))
                            FROM jsonb_array_elements(products::jsonb) p)),0)
                    FROM ozon_postings WHERE in_process_at>=:b AND in_process_at<:u GROUP BY 1
                    UNION ALL
                    SELECT created_at::date,'yandex_market',count(*),coalesce(sum(total_amount),0)
                    FROM yandex_market_orders WHERE created_at>=:b AND created_at<:u GROUP BY 1
                ) x GROUP BY report_day,marketplace) d""", b=begin, u=until)
        self._convert(prices)
        raw = series_result.get("data", []) if "error" not in series_result else []
        series = [{**dict(row), "day": str(row["report_day"]), "revenue": _number(row["revenue"])} for row in raw]
        return {"period":{"from":begin.isoformat(),"to":finish.isoformat()},"previous_period":{"from":previous_begin.isoformat(),"to":previous_finish.isoformat()},"marketplaces":current["marketplaces"],"previous_marketplaces":previous["marketplaces"],"ads":current["ads"],"previous_ads":previous["ads"],"stocks":stocks,"previous_stocks":previous_stocks,"prices":prices,"series":series,"series_error":series_result.get("error")}
