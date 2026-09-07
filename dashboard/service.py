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
            session_factory = sessionmaker(
                bind=engine, autoflush=False, autocommit=False, future=True
            )
        self.session_factory = session_factory

    @staticmethod
    def period(start: str | None, end: str | None) -> tuple[date, date]:
        today = date.today()
        end_date = date.fromisoformat(end) if end else today
        start_date = date.fromisoformat(start) if start else end_date.replace(day=1)
        if start_date > end_date or (end_date - start_date).days > 730:
            raise ValueError("invalid period")
        return start_date, end_date

    def summary(self, start: str | None, end: str | None) -> dict[str, Any]:
        begin, finish = self.period(start, end); until = finish + timedelta(days=1)
        with self.session_factory() as db:
            def one(sql: str, **params: Any) -> dict[str, Any]:
                try:
                    return dict(db.execute(text(sql), params).mappings().one())
                except Exception as exc:
                    db.rollback()
                    return {"error": f"{type(exc).__name__}: {exc}"}

            wb = one("""SELECT count(*) FILTER (WHERE status <> 'cancel') orders,
                coalesce(sum(seller_price) FILTER (WHERE status <> 'cancel'),0) revenue,
                count(*) FILTER (WHERE status='cancel') cancelled,
                (SELECT count(*) FROM wb_operational_sales
                    WHERE operation_type='sale' AND event_date>=:b AND event_date<:u) buyouts,
                (SELECT coalesce(sum(finished_price),0) FROM wb_operational_sales
                    WHERE operation_type='sale' AND event_date>=:b AND event_date<:u) buyouts_amount
                FROM wb_order_feed_orders WHERE order_date>=:b AND order_date<:u""", b=begin, u=until)
            ozon = one("""WITH postings AS (
                SELECT order_id,order_number,posting_number,status,
                coalesce((SELECT sum(coalesce((p->>'quantity')::int,0))
                    FROM jsonb_array_elements(products::jsonb) p),0) units,
                coalesce((SELECT sum(
                    coalesce((CASE WHEN jsonb_typeof(p->'price')='object'
                        THEN coalesce(p->'price'->>'amount',p->'price'->>'value')
                        ELSE p->>'price' END)::numeric,0)
                    * coalesce((p->>'quantity')::int,0))
                    FROM jsonb_array_elements(products::jsonb) p),0) amount
                FROM ozon_postings WHERE in_process_at>=:b AND in_process_at<:u
                ) SELECT count(DISTINCT coalesce(order_id::text,order_number,posting_number)) orders,
                coalesce(sum(amount),0) revenue,
                count(*) FILTER (WHERE lower(status) IN ('cancelled','canceled')) cancelled
                ,coalesce(sum(units) FILTER (WHERE lower(status)='delivered'),0) buyouts
                ,coalesce(sum(amount) FILTER (WHERE lower(status)='delivered'),0) buyouts_amount
                FROM postings""", b=begin, u=until)
            yandex = one("""SELECT count(*) orders,coalesce(sum(total_amount),0) revenue,
                count(*) FILTER (WHERE status='CANCELLED') cancelled,
                coalesce(sum(items_count) FILTER (WHERE status='DELIVERED'),0) buyouts,
                coalesce(sum(total_amount) FILTER (WHERE status='DELIVERED'),0) buyouts_amount
                FROM yandex_market_orders WHERE created_at>=:b AND created_at<:u""", b=begin, u=until)
            ads = {
                "wb": one("SELECT coalesce(sum(spend),0) spend,coalesce(sum(order_sum),0) revenue FROM wb_advert_daily_stats WHERE stat_date>=:b AND stat_date<:u", b=begin, u=until),
                "ozon": one("SELECT coalesce(sum(spend),0) spend,coalesce(sum(orders_money),0) revenue FROM ozon_ad_daily_stats WHERE stat_date>=:b AND stat_date<=:e", b=begin, e=finish),
                "yandex_market": one("SELECT coalesce(sum(spend),0) spend,coalesce(sum(attributed_revenue),0) revenue FROM yandex_market_ad_daily_stats WHERE stat_date>=:b AND stat_date<=:e", b=begin, e=finish),
            }
            stocks = {
                "wb": one("SELECT coalesce((SELECT sum(quantity) FROM wb_fbs_stocks),0)+coalesce((SELECT sum(quantity) FROM wb_fbo_stocks),0) units"),
                "ozon": one("SELECT coalesce(sum(present),0) units FROM ozon_stocks"),
                "yandex_market": one("SELECT coalesce(sum(count),0) units FROM yandex_market_stocks WHERE stock_type IN ('FIT','AVAILABLE')"),
            }
            prices = one("SELECT count(*) active,count(*) FILTER (WHERE in_promotion IS TRUE) promotions,count(*) FILTER (WHERE coalesce(seller_price,customer_price,list_price,0)<=0) invalid FROM marketplace_current_prices WHERE active IS TRUE")
            supplies = {
                "wb": one("SELECT count(DISTINCT supply_id) supplies,coalesce(sum(quantity),0) sent,coalesce(sum(accepted_quantity),0) accepted FROM wb_fbw_supply_goods"),
                "ozon": one("""SELECT
                    (SELECT count(DISTINCT supply_id) FROM ozon_fbo_supply_declared_items) supplies,
                    (SELECT coalesce(sum(declared_quantity),0) FROM ozon_fbo_supply_declared_items) sent,
                    (SELECT coalesce(sum(fact_quantity),0) FROM ozon_fbo_supply_act_items WHERE upper(act_type)='ACCEPTANCE') accepted"""),
            }
            series_result = one("""SELECT coalesce(json_agg(daily_rows ORDER BY report_day,marketplace),'[]'::json) data FROM (
                SELECT report_day,marketplace,sum(orders) orders,sum(revenue) revenue FROM (
                SELECT order_date::date AS report_day,'wb' AS marketplace,count(*) orders,sum(seller_price) revenue FROM wb_order_feed_orders WHERE order_date>=:b AND order_date<:u AND status<>'cancel' GROUP BY 1
                UNION ALL SELECT in_process_at::date,'ozon',count(DISTINCT coalesce(order_id::text,order_number,posting_number)),0 FROM ozon_postings WHERE in_process_at>=:b AND in_process_at<:u GROUP BY 1
                UNION ALL SELECT created_at::date,'yandex_market',count(*),sum(total_amount) FROM yandex_market_orders WHERE created_at>=:b AND created_at<:u GROUP BY 1
                ) source_rows GROUP BY report_day,marketplace
                ) daily_rows""", b=begin, u=until)
        for item in (wb, ozon, yandex, *ads.values(), *stocks.values(), prices, *supplies.values()):
            for key, value in list(item.items()):
                if isinstance(value, Decimal): item[key] = _number(value)
        raw_series = series_result.get("data", []) if "error" not in series_result else []
        series = [
            {
                **dict(row),
                "day": str(row["report_day"]),
                "revenue": _number(row["revenue"]),
            }
            for row in raw_series
        ]
        return {"period": {"from": begin.isoformat(), "to": finish.isoformat()}, "marketplaces": {"wb": wb, "ozon": ozon, "yandex_market": yandex}, "ads": ads, "stocks": stocks, "prices": prices, "supplies": supplies, "series": series, "series_error": series_result.get("error")}
