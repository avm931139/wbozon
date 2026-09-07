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
        wb = one("""SELECT count(*) orders,
            coalesce(sum(seller_price),0) orders_amount,
            count(*) FILTER (WHERE status='cancel') cancelled,
            coalesce(sum(seller_price) FILTER (WHERE status='cancel'),0) cancelled_amount,
            (SELECT count(*) FROM wb_operational_sales WHERE operation_type='sale' AND event_date>=:b AND event_date<:u) buyouts,
            (SELECT coalesce(sum(finished_price),0) FROM wb_operational_sales WHERE operation_type='sale' AND event_date>=:b AND event_date<:u) buyouts_amount
            FROM wb_order_feed_orders WHERE order_date>=:b AND order_date<:u""", b=begin, u=until)
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
            "wb": one("""SELECT coalesce(sum(additional_payment),0) compensation,
                coalesce(sum(delivery_service+acquiring_fee+ppvz_sales_commission+penalty+rebill_logistic_cost+paid_storage+deduction+paid_acceptance),0) expenses
                FROM wb_financial_sales_rows WHERE rr_date>=:b AND rr_date<:u""", b=begin, u=until),
            "ozon": one("""SELECT coalesce(sum(amount) FILTER (WHERE amount>0 AND accrual_type<>'POSTING'),0) compensation,
                abs(coalesce(sum(amount) FILTER (WHERE amount<0),0)) expenses
                FROM ozon_finance_accruals WHERE accrual_date>=:b AND accrual_date<=:e""", b=begin, e=finish),
            "yandex_market": one("""SELECT coalesce(sum(amount) FILTER (WHERE amount>0),0) revenue,
                abs(coalesce(sum(amount) FILTER (WHERE amount<0),0)) expenses,count(*) rows
                FROM yandex_market_finance_transactions WHERE transaction_at>=:b AND transaction_at<:u""", b=begin, u=until),
        }
        costs = {
            "wb": one("""WITH c AS (SELECT DISTINCT ON (master_product_id) master_product_id,unit_cost FROM product_cost_records ORDER BY master_product_id,effective_at DESC,id DESC)
                SELECT coalesce(sum(coalesce(c.unit_cost,0)),0) cost_of_goods,count(*) FILTER (WHERE c.unit_cost IS NOT NULL) costed_units
                FROM wb_operational_sales s LEFT JOIN marketplace_product_links l ON l.marketplace='wb' AND l.active AND l.external_product_id=s.nm_id::text
                LEFT JOIN c ON c.master_product_id=l.master_product_id WHERE s.operation_type='sale' AND s.event_date>=:b AND s.event_date<:u""", b=begin, u=until),
            "ozon": one("""WITH c AS (SELECT DISTINCT ON (master_product_id) master_product_id,unit_cost FROM product_cost_records ORDER BY master_product_id,effective_at DESC,id DESC),
                sold AS (SELECT p->>'offer_id' offer_id,coalesce((p->>'quantity')::int,0) quantity FROM ozon_postings o CROSS JOIN LATERAL jsonb_array_elements(o.products::jsonb) p WHERE lower(o.status)='delivered' AND o.in_process_at>=:b AND o.in_process_at<:u)
                SELECT coalesce(sum(s.quantity*coalesce(c.unit_cost,0)),0) cost_of_goods,coalesce(sum(s.quantity) FILTER (WHERE c.unit_cost IS NOT NULL),0) costed_units
                FROM sold s LEFT JOIN marketplace_product_links l ON l.marketplace='ozon' AND l.active AND l.offer_id=s.offer_id LEFT JOIN c ON c.master_product_id=l.master_product_id""", b=begin, u=until),
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
                        coalesce(sum(seller_price),0) revenue
                    FROM wb_order_feed_orders WHERE order_date>=:b AND order_date<:u GROUP BY 1
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
