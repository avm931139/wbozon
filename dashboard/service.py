from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import mimetypes
from pathlib import Path
from typing import Any, Callable
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import DASHBOARD_DATABASE_URL, PRODUCT_MEDIA_STORAGE_DIR
from app.models import MasterProduct, ProductCostImportRun, ProductCostRecord


def _number(value: Any) -> float:
    return float(Decimal(str(value or 0)))


def _kopecks(value: Any) -> int:
    return int((Decimal(str(value or 0)) * 100).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    ))


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

    def stock_details(
        self,
        value: str | None,
        wb_warehouse: str | None = None,
        ozon_warehouse: str | None = None,
        yandex_warehouse: str | None = None,
    ) -> dict[str, Any]:
        """Return one product row with WB, Ozon and Yandex stock as of a date."""
        requested = date.fromisoformat(value) if value else date.today()
        if requested > date.today():
            raise ValueError("stock date cannot be in the future")
        wb_warehouse = str(wb_warehouse or "").strip() or None
        if wb_warehouse and len(wb_warehouse) > 200:
            raise ValueError("invalid WB warehouse")
        try:
            ozon_warehouse_id = int(ozon_warehouse) if ozon_warehouse else None
            yandex_warehouse_id = int(yandex_warehouse) if yandex_warehouse else None
        except (TypeError, ValueError):
            raise ValueError("invalid warehouse ID")
        current = requested == date.today()
        if current:
            sources = {
                "wb": """SELECT coalesce(p.nm_id::text,x.vendor_code) external_id,
                        x.vendor_code source_article,p.title source_name,
                        x.quantity units,x.fetched_at refreshed_at,
                        CAST(:d AS date) data_date
                    FROM wb_warehouse_remains x
                    LEFT JOIN LATERAL (
                        SELECT nm_id,vendor_code,title FROM wb_products
                        WHERE vendor_code=x.vendor_code ORDER BY id LIMIT 1
                    ) p ON TRUE
                    WHERE x.warehouse_name=coalesce(:wbw,'Всего находится на складах')""",
                "ozon": ("""SELECT x.product_id::text external_id,p.offer_id source_article,
                        p.name source_name,x.present units,x.fetched_at refreshed_at,
                        CAST(:d AS date) data_date
                    FROM ozon_stocks x LEFT JOIN ozon_products p ON p.product_id=x.product_id"""
                    if ozon_warehouse_id is None else
                    """SELECT x.product_id::text external_id,p.offer_id source_article,
                        p.name source_name,x.present units,x.fetched_at refreshed_at,
                        CAST(:d AS date) data_date
                    FROM ozon_warehouse_stocks x
                    JOIN ozon_warehouses w ON w.id=x.warehouse_id
                    LEFT JOIN ozon_products p ON p.product_id=x.product_id
                    WHERE w.ozon_warehouse_id=:ozw"""),
                "yandex_market": """SELECT x.offer_id external_id,x.offer_id source_article,
                        o.name source_name,x.count units,x.fetched_at refreshed_at,
                        CAST(:d AS date) data_date
                    FROM yandex_market_stocks x
                    LEFT JOIN yandex_market_campaigns c ON c.campaign_id=x.campaign_id
                    LEFT JOIN yandex_market_offers o ON o.offer_id=x.offer_id
                        AND o.business_id=c.business_id
                    WHERE x.stock_type='AVAILABLE'
                      AND (CAST(:ymw AS bigint) IS NULL
                           OR x.warehouse_id=CAST(:ymw AS bigint))""",
            }
        else:
            sources = {
                "wb": """SELECT coalesce(p.nm_id::text,x.vendor_code) external_id,
                        x.vendor_code source_article,p.title source_name,
                        x.quantity units,x.captured_at refreshed_at,
                        x.snapshot_date data_date
                    FROM wb_warehouse_remain_snapshots x
                    LEFT JOIN LATERAL (
                        SELECT nm_id,vendor_code,title FROM wb_products
                        WHERE vendor_code=x.vendor_code ORDER BY id LIMIT 1
                    ) p ON TRUE
                    WHERE x.warehouse_name=coalesce(:wbw,'Всего находится на складах')
                      AND x.snapshot_date=(SELECT max(snapshot_date)
                          FROM wb_warehouse_remain_snapshots WHERE snapshot_date<=:d)""",
                "ozon": ("""SELECT x.product_id::text external_id,p.offer_id source_article,
                        p.name source_name,x.present units,x.captured_at refreshed_at,
                        x.snapshot_date data_date
                    FROM ozon_stock_snapshots x LEFT JOIN ozon_products p ON p.product_id=x.product_id
                    WHERE x.snapshot_date=(SELECT max(snapshot_date) FROM ozon_stock_snapshots WHERE snapshot_date<=:d)"""
                    if ozon_warehouse_id is None else
                    """SELECT x.product_id::text external_id,p.offer_id source_article,
                        p.name source_name,x.present units,x.captured_at refreshed_at,
                        x.snapshot_date data_date
                    FROM ozon_warehouse_stock_snapshots x
                    JOIN ozon_warehouses w ON w.id=x.warehouse_id
                    LEFT JOIN ozon_products p ON p.product_id=x.product_id
                    WHERE w.ozon_warehouse_id=:ozw
                      AND x.snapshot_date=(SELECT max(snapshot_date)
                          FROM ozon_warehouse_stock_snapshots WHERE snapshot_date<=:d)"""),
                "yandex_market": """SELECT x.offer_id external_id,x.offer_id source_article,
                        o.name source_name,x.count units,x.captured_at refreshed_at,
                        x.snapshot_date data_date
                    FROM yandex_market_stock_snapshots x
                    LEFT JOIN yandex_market_campaigns c ON c.campaign_id=x.campaign_id
                    LEFT JOIN yandex_market_offers o ON o.offer_id=x.offer_id
                        AND o.business_id=c.business_id
                    WHERE x.stock_type='AVAILABLE'
                      AND (CAST(:ymw AS bigint) IS NULL
                           OR x.warehouse_id=CAST(:ymw AS bigint))
                      AND x.snapshot_date=(SELECT max(snapshot_date) FROM yandex_market_stock_snapshots WHERE snapshot_date<=:d)""",
            }
        grouped = []
        for marketplace, source in sources.items():
            grouped.append(f"""{marketplace}_raw AS ({source}),
                {marketplace} AS (
                    SELECT coalesce('m:'||link.master_product_id::text,'{marketplace}:'||r.external_id) row_key,
                        link.master_product_id,min(r.external_id) external_id,
                        max(r.source_article) source_article,max(r.source_name) source_name,
                        coalesce(sum(r.units),0)::bigint units,max(r.refreshed_at) refreshed_at,
                        max(r.data_date) data_date
                    FROM {marketplace}_raw r
                    LEFT JOIN LATERAL (
                        SELECT master_product_id FROM marketplace_product_links l
                        WHERE l.marketplace='{marketplace}' AND l.active
                          AND l.external_product_id=r.external_id LIMIT 1
                    ) link ON TRUE
                    GROUP BY row_key,link.master_product_id
                )""")
        sql = "WITH " + ",".join(grouped) + """,
            product_keys AS (
                SELECT 'm:'||id::text row_key,id master_product_id FROM master_products WHERE active
                UNION SELECT row_key,master_product_id FROM wb
                UNION SELECT row_key,master_product_id FROM ozon
                UNION SELECT row_key,master_product_id FROM yandex_market
            ), media_ranked AS (
                SELECT pm.id,pm.marketplace,
                    coalesce('m:'||pm.master_product_id::text,
                             pm.marketplace||':'||pm.external_product_id) row_key,
                    row_number() OVER (
                        PARTITION BY pm.marketplace,
                            coalesce('m:'||pm.master_product_id::text,
                                     pm.marketplace||':'||pm.external_product_id)
                        ORDER BY CASE WHEN lower(pm.role) IN ('main','primary','cover')
                                      THEN 0 ELSE 1 END,pm.position,pm.id
                    ) rank
                FROM marketplace_product_media pm
                WHERE pm.media_type='image' AND pm.active
                  AND pm.download_status='downloaded' AND pm.local_path IS NOT NULL
            ), images AS (
                SELECT id,marketplace,row_key FROM media_ranked WHERE rank=1
            ), costs AS (
                SELECT DISTINCT ON (master_product_id) master_product_id,unit_cost,effective_at
                FROM product_cost_records
                ORDER BY master_product_id,effective_at DESC,id DESC
            )
            SELECT k.row_key,k.master_product_id,
                   coalesce(mp.article,wb.source_article,ozon.source_article,
                       yandex_market.source_article) article,
                   coalesce(mp.name,wb.source_name,ozon.source_name,yandex_market.source_name) name,
                   costs.unit_cost,costs.effective_at cost_updated_at,
                   wb.units wb_units,wb.refreshed_at wb_updated_at,wb.data_date wb_data_date,
                   ozon.units ozon_units,ozon.refreshed_at ozon_updated_at,ozon.data_date ozon_data_date,
                   yandex_market.units yandex_units,yandex_market.refreshed_at yandex_updated_at,
                   yandex_market.data_date yandex_data_date,
                   wb_image.id wb_image_id,ozon_image.id ozon_image_id,
                   yandex_image.id yandex_image_id
            FROM product_keys k LEFT JOIN master_products mp ON mp.id=k.master_product_id
            LEFT JOIN costs ON costs.master_product_id=k.master_product_id
            LEFT JOIN wb ON wb.row_key=k.row_key LEFT JOIN ozon ON ozon.row_key=k.row_key
            LEFT JOIN yandex_market ON yandex_market.row_key=k.row_key
            LEFT JOIN images wb_image ON wb_image.row_key=k.row_key AND wb_image.marketplace='wb'
            LEFT JOIN images ozon_image ON ozon_image.row_key=k.row_key AND ozon_image.marketplace='ozon'
            LEFT JOIN images yandex_image ON yandex_image.row_key=k.row_key
                AND yandex_image.marketplace='yandex_market'
            ORDER BY coalesce(mp.article,wb.source_article,ozon.source_article,
                              yandex_market.source_article),k.row_key"""
        params = {
            "d": requested, "wbw": wb_warehouse,
            "ozw": ozon_warehouse_id, "ymw": yandex_warehouse_id,
        }
        with self.session_factory() as db:
            records = [dict(row) for row in db.execute(text(sql), params).mappings().all()]
            warehouse_options = self._stock_warehouse_options(db, requested, current)
        rows = []
        for record in records:
            row = {"key": record["row_key"],
                   "master_product_id": record.get("master_product_id"),
                   "article": record.get("article") or "—",
                   "name": record.get("name") or "",
                   "unit_cost": _number(record["unit_cost"]) if record.get("unit_cost") is not None else None,
                   "cost_updated_at": record.get("cost_updated_at")}
            for marketplace, prefix in (("wb", "wb"), ("ozon", "ozon"),
                                        ("yandex_market", "yandex")):
                image_id = record.get(f"{prefix}_image_id")
                row[marketplace] = {
                    "quantity": int(record.get(f"{prefix}_units") or 0),
                    "updated_at": record.get(f"{prefix}_updated_at"),
                    "data_date": record.get(f"{prefix}_data_date"),
                    "image_url": f"/api/product-image?id={image_id}" if image_id else None,
                }
            rows.append(row)
        totals = {
            marketplace: {
                "quantity": sum(row[marketplace]["quantity"] for row in rows),
                "updated_at": max((row[marketplace]["updated_at"] for row in rows
                                   if row[marketplace]["updated_at"]), default=None),
                "data_date": max((row[marketplace]["data_date"] for row in rows
                                  if row[marketplace]["data_date"]), default=None),
            }
            for marketplace in ("wb", "ozon", "yandex_market")
        }
        return {
            "requested_date": requested, "current": current,
            "totals": totals, "rows": rows,
            "warehouse_filters": {
                "options": warehouse_options,
                "selected": {
                    "wb": wb_warehouse,
                    "ozon": str(ozon_warehouse_id) if ozon_warehouse_id is not None else None,
                    "yandex_market": (
                        str(yandex_warehouse_id) if yandex_warehouse_id is not None else None
                    ),
                },
            },
        }

    @staticmethod
    def _stock_warehouse_options(
        db: Any, requested: date, current: bool
    ) -> dict[str, list[dict[str, Any]]]:
        if current:
            wb_table = "wb_warehouse_remains"
            ozon_table = "ozon_warehouse_stocks"
            yandex_table = "yandex_market_stocks"
            date_filters = {"wb": "", "ozon": "", "yandex": ""}
        else:
            wb_table = "wb_warehouse_remain_snapshots"
            ozon_table = "ozon_warehouse_stock_snapshots"
            yandex_table = "yandex_market_stock_snapshots"
            date_filters = {
                "wb": "AND snapshot_date=(SELECT max(snapshot_date) FROM wb_warehouse_remain_snapshots WHERE snapshot_date<=:d)",
                "ozon": "AND s.snapshot_date=(SELECT max(snapshot_date) FROM ozon_warehouse_stock_snapshots WHERE snapshot_date<=:d)",
                "yandex": "AND s.snapshot_date=(SELECT max(snapshot_date) FROM yandex_market_stock_snapshots WHERE snapshot_date<=:d)",
            }
        wb_rows = db.execute(text(f"""SELECT warehouse_name value,warehouse_name label,
                coalesce(sum(quantity),0)::bigint units
            FROM {wb_table} WHERE warehouse_name<>'Всего находится на складах'
              AND warehouse_name NOT LIKE 'В пути%' {date_filters['wb']}
            GROUP BY warehouse_name HAVING sum(quantity)>0
            ORDER BY warehouse_name"""), {"d": requested}).mappings().all()
        ozon_rows = db.execute(text(f"""SELECT w.ozon_warehouse_id::text value,
                concat_ws(' · ',w.name,w.cluster_name) label,
                coalesce(sum(s.present),0)::bigint units
            FROM {ozon_table} s JOIN ozon_warehouses w ON w.id=s.warehouse_id
            WHERE TRUE {date_filters['ozon']}
            GROUP BY w.ozon_warehouse_id,w.name,w.cluster_name
            HAVING sum(s.present)>0 ORDER BY w.name,w.ozon_warehouse_id"""), {"d": requested}).mappings().all()
        yandex_rows = db.execute(text(f"""SELECT s.warehouse_id::text value,
                concat_ws(' · ',coalesce(max(w.name),'ID '||s.warehouse_id::text),
                    max(w.warehouse_type)) label,
                coalesce(sum(s.count),0)::bigint units
            FROM {yandex_table} s
            LEFT JOIN yandex_market_campaigns c ON c.campaign_id=s.campaign_id
            LEFT JOIN yandex_market_warehouses w ON w.business_id=c.business_id
                AND w.warehouse_id=s.warehouse_id
            WHERE s.stock_type='AVAILABLE' {date_filters['yandex']}
            GROUP BY s.warehouse_id HAVING sum(s.count)>0
            ORDER BY label,s.warehouse_id"""), {"d": requested}).mappings().all()
        return {
            "wb": [dict(row) for row in wb_rows],
            "ozon": [dict(row) for row in ozon_rows],
            "yandex_market": [dict(row) for row in yandex_rows],
        }

    def update_product_cost(self, master_product_id: int, value: Any) -> dict[str, Any]:
        if isinstance(master_product_id, bool) or master_product_id <= 0:
            raise ValueError("invalid master product ID")
        try:
            unit_cost = Decimal(str(value)).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            )
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("invalid unit cost")
        if unit_cost < 0 or unit_cost > Decimal("1000000000"):
            raise ValueError("unit cost is outside the allowed range")

        now = datetime.now(timezone.utc)
        run_id = uuid.uuid4().hex
        source_hash = hashlib.sha256(
            f"dashboard:{run_id}:{master_product_id}:{unit_cost}".encode()
        ).hexdigest()
        with self.session_factory() as session:
            product = session.get(MasterProduct, master_product_id)
            if product is None or not product.active:
                raise ValueError("active master product was not found")
            previous = session.query(ProductCostRecord).filter_by(
                master_product_id=master_product_id
            ).order_by(
                ProductCostRecord.effective_at.desc(), ProductCostRecord.id.desc()
            ).first()
            session.add(ProductCostImportRun(
                id=run_id, source_file="dashboard-manual-edit",
                source_sha256=source_hash, started_at=now, finished_at=now,
                status="completed", rows_total=1, rows_imported=1,
                rows_skipped_blank=0,
            ))
            session.add(ProductCostRecord(
                import_run_id=run_id, master_product_id=product.id,
                article=product.article, product_name=product.name,
                unit_cost=unit_cost,
                quantity=int(previous.quantity if previous else 0),
                currency="RUB", effective_at=now, source_row=1,
                note="Изменено вручную на странице остатков", created_at=now,
            ))
            session.commit()
            article = product.article
        return {
            "master_product_id": master_product_id, "article": article,
            "unit_cost": float(unit_cost), "effective_at": now.isoformat(),
        }

    def product_image(self, media_id: int) -> tuple[Path, str]:
        with self.session_factory() as db:
            row = db.execute(text("""SELECT local_path,content_type FROM marketplace_product_media
                WHERE id=:id AND active AND media_type='image' AND download_status='downloaded'
                  AND local_path IS NOT NULL"""), {"id": media_id}).mappings().one_or_none()
        if row is None:
            raise FileNotFoundError("product image not found")
        root = Path(PRODUCT_MEDIA_STORAGE_DIR).expanduser().resolve()
        target = (root / row["local_path"]).resolve(strict=True)
        if target == root or root not in target.parents or not target.is_file():
            raise FileNotFoundError("product image not found")
        content_type = row["content_type"] or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return target, content_type

    @staticmethod
    def _one(db: Any, sql: str, **params: Any) -> dict[str, Any]:
        try:
            return dict(db.execute(text(sql), params).mappings().one())
        except Exception as exc:
            db.rollback()
            return {"error": f"{type(exc).__name__}: {exc}"}

    @staticmethod
    def _many(db: Any, sql: str, **params: Any) -> list[dict[str, Any]]:
        try:
            return [dict(row) for row in db.execute(text(sql), params).mappings().all()]
        except Exception as exc:
            db.rollback()
            return [{"error": f"{type(exc).__name__}: {exc}"}]

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
                CROSS JOIN (SELECT greatest(coalesce(-sum(
                        (fee->'accrued'->>'amount')::numeric
                    ),0),0) finance_spend
                    FROM ozon_finance_accruals a
                    CROSS JOIN LATERAL jsonb_path_query(
                        a.raw_data::jsonb,
                        'strict $.** ? (exists(@.type_id) && exists(@.accrued))'
                    ) fee
                    JOIN ozon_finance_accrual_types t
                      ON t.type_id=(fee->>'type_id')::integer
                    WHERE a.accrual_date BETWEEN :b AND :e
                      AND t.name IN ('PayPerClick','Promotion')
                ) finance""",
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
            "wb": one("""WITH period_metrics AS (
                    SELECT count(*) snapshot_rows,
                        coalesce(sum(open_count),0) views,coalesce(sum(cart_count),0) to_cart,
                        coalesce(sum(order_count),0) ordered_items,coalesce(sum(order_sum),0) ordered_amount,
                        coalesce(sum(buyout_count),0) purchased_items,coalesce(sum(buyout_sum),0) purchased_amount,
                        coalesce(sum(cancel_count),0) cancelled_items,coalesce(sum(cancel_sum),0) cancelled_amount,
                        max(fetched_at) fetched_at
                    FROM wb_sales_funnel_period_products
                    WHERE period_from=:b AND period_to=:e
                ), product_metrics AS (
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
                ) SELECT
                    CASE WHEN period_metrics.snapshot_rows>0 THEN period_metrics.views ELSE account_metrics.views END views,
                    CASE WHEN period_metrics.snapshot_rows>0 THEN period_metrics.to_cart ELSE account_metrics.to_cart END to_cart,
                    CASE WHEN period_metrics.snapshot_rows>0 THEN period_metrics.ordered_items ELSE account_metrics.ordered_items END ordered_items,
                    CASE WHEN period_metrics.snapshot_rows>0 THEN period_metrics.ordered_amount ELSE account_metrics.ordered_amount END ordered_amount,
                    CASE WHEN period_metrics.snapshot_rows>0 THEN period_metrics.purchased_items ELSE account_metrics.purchased_items END purchased_items,
                    CASE WHEN period_metrics.snapshot_rows>0 THEN period_metrics.purchased_amount ELSE account_metrics.purchased_amount END purchased_amount,
                    CASE WHEN period_metrics.snapshot_rows>0 THEN period_metrics.cancelled_items ELSE 0 END cancelled_items,
                    CASE WHEN period_metrics.snapshot_rows>0 THEN period_metrics.cancelled_amount ELSE 0 END cancelled_amount,
                    CASE WHEN period_metrics.snapshot_rows>0 THEN CAST(:e AS date)-CAST(:b AS date)+1 ELSE account_metrics.coverage_days END coverage_days,
                    CASE WHEN period_metrics.snapshot_rows>0 THEN period_metrics.views ELSE product_metrics.product_views END product_views,
                    CASE WHEN period_metrics.snapshot_rows>0 THEN period_metrics.ordered_items ELSE product_metrics.product_ordered_items END product_ordered_items,
                    CASE WHEN period_metrics.snapshot_rows>0 THEN period_metrics.ordered_amount ELSE product_metrics.product_ordered_amount END product_ordered_amount,
                    CASE WHEN period_metrics.snapshot_rows>0 THEN 0 ELSE account_metrics.ordered_items-product_metrics.product_ordered_items END item_delta,
                    CASE WHEN period_metrics.snapshot_rows>0 THEN 0 ELSE account_metrics.ordered_amount-product_metrics.product_ordered_amount END amount_delta,
                    CAST(:e AS date)-CAST(:b AS date)+1 expected_days,
                    period_metrics.snapshot_rows>0 OR account_metrics.coverage_days=CAST(:e AS date)-CAST(:b AS date)+1 complete,
                    CASE WHEN period_metrics.snapshot_rows>0
                        THEN 'WB Sales Funnel products period snapshot'
                        ELSE 'WB Sales Funnel grouped/history' END source,
                    period_metrics.fetched_at period_snapshot_fetched_at
                FROM period_metrics CROSS JOIN product_metrics CROSS JOIN account_metrics""", b=begin, e=finish),
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
                            - coalesce(sum(
                                delivery_service+penalty+paid_storage+paid_acceptance+deduction
                                +coalesce(nullif(raw_data->>'paymentSchedule','')::numeric,0)
                            ),0) net_payout
                    FROM wb_financial_sales_rows WHERE rr_date>=:b AND rr_date<:u
                ) SELECT rows,finance_buyouts,finance_buyouts_amount,compensation,
                    finance_buyouts_amount+compensation revenue,
                    finance_buyouts_amount+compensation-net_payout expenses,
                    coverage.finance_from,coverage.finance_through,coverage.covered
                FROM ledger CROSS JOIN coverage""", b=begin, e=finish, u=until),
            "ozon": one("""WITH ledger AS (
                    SELECT count(*) rows,coalesce(sum(amount),0) net_accrual,
                        coalesce(sum(amount) FILTER (WHERE accrual_type='NON_ITEM' AND amount>0),0) compensation,
                        min(accrual_date) finance_from,max(accrual_date) finance_through
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
                    sales.finance_buyouts_amount+ledger.compensation-ledger.net_accrual expenses,
                    ledger.finance_from,ledger.finance_through
                FROM ledger CROSS JOIN sales""", b=begin, e=finish),
            "yandex_market": one("""WITH ledger AS (
                    SELECT *,transaction_at::date transaction_date,
                        transaction_type IN ('Начисление','Возврат') AND quantity>0 product_transaction
                    FROM yandex_market_finance_transactions
                    WHERE transaction_at>=:b AND transaction_at<:u
                ), product_events AS (
                    SELECT business_id,order_id,offer_id,transaction_date,transaction_type,
                        max(quantity) quantity,sum(amount) amount
                    FROM ledger WHERE product_transaction
                    GROUP BY business_id,order_id,offer_id,transaction_date,transaction_type
                ), totals AS (
                    SELECT count(*) rows,
                        coalesce(sum(amount) FILTER (WHERE product_transaction),0) revenue,
                        greatest(-coalesce(sum(amount) FILTER (WHERE NOT product_transaction),0),0) expenses,
                        min(transaction_at)::date finance_from,max(transaction_at)::date finance_through
                    FROM ledger
                ), units AS (
                    SELECT coalesce(sum(CASE WHEN transaction_type='Начисление' THEN quantity
                        WHEN transaction_type='Возврат' THEN -quantity ELSE 0 END),0) finance_buyouts
                    FROM product_events
                )
                SELECT totals.*,units.finance_buyouts FROM totals CROSS JOIN units""", b=begin, u=until),
        }
        costs = {
            "wb": one("""WITH operational AS (SELECT coalesce(sum(coalesce(c.unit_cost,0)),0) cost_of_goods,count(*) FILTER (WHERE c.unit_cost IS NOT NULL) costed_units
                    FROM wb_operational_sales s LEFT JOIN marketplace_product_links l ON l.marketplace='wb' AND l.active AND l.external_product_id=s.nm_id::text
                    LEFT JOIN LATERAL (
                        SELECT cost.unit_cost FROM product_cost_records cost
                        WHERE cost.master_product_id=l.master_product_id
                        ORDER BY CASE WHEN cost.effective_at::date<=s.event_date::date THEN 0 ELSE 1 END,
                            CASE WHEN cost.effective_at::date<=s.event_date::date THEN cost.effective_at END DESC,
                            CASE WHEN cost.effective_at::date>s.event_date::date THEN cost.effective_at END ASC,cost.id DESC
                        LIMIT 1
                    ) c ON TRUE WHERE s.operation_type='sale' AND s.event_date>=:b AND s.event_date<:u),
                financial AS (SELECT coalesce(sum((CASE WHEN s.seller_operation_name='Возврат' THEN -s.quantity ELSE s.quantity END)*coalesce(c.unit_cost,0)) FILTER (WHERE s.seller_operation_name IN ('Продажа','Возврат','Бронирование товара через самовывоз')),0) cost_of_goods,
                    coalesce(sum((CASE WHEN s.seller_operation_name='Возврат' THEN -s.quantity ELSE s.quantity END)) FILTER (WHERE s.seller_operation_name IN ('Продажа','Возврат','Бронирование товара через самовывоз') AND c.unit_cost IS NOT NULL),0) costed_units
                    FROM wb_financial_sales_rows s LEFT JOIN marketplace_product_links l ON l.marketplace='wb' AND l.active AND l.external_product_id=s.nm_id::text
                    LEFT JOIN LATERAL (
                        SELECT cost.unit_cost FROM product_cost_records cost
                        WHERE cost.master_product_id=l.master_product_id
                        ORDER BY CASE WHEN cost.effective_at::date<=s.rr_date::date THEN 0 ELSE 1 END,
                            CASE WHEN cost.effective_at::date<=s.rr_date::date THEN cost.effective_at END DESC,
                            CASE WHEN cost.effective_at::date>s.rr_date::date THEN cost.effective_at END ASC,cost.id DESC
                        LIMIT 1
                    ) c ON TRUE WHERE s.rr_date>=:b AND s.rr_date<:u)
                SELECT operational.cost_of_goods,operational.costed_units,
                    financial.cost_of_goods finance_cost_of_goods,financial.costed_units finance_costed_units,
                    funnel.cost_of_goods funnel_cost_of_goods,funnel.costed_units funnel_costed_units
                FROM operational CROSS JOIN financial CROSS JOIN (
                    SELECT coalesce(sum(f.buyout_count*coalesce(c.unit_cost,0)),0) cost_of_goods,
                        coalesce(sum(f.buyout_count) FILTER (WHERE c.unit_cost IS NOT NULL),0) costed_units
                    FROM wb_sales_funnel_daily f
                    LEFT JOIN marketplace_product_links l ON l.marketplace='wb' AND l.active AND l.external_product_id=f.nm_id::text
                    LEFT JOIN LATERAL (
                        SELECT cost.unit_cost FROM product_cost_records cost
                        WHERE cost.master_product_id=l.master_product_id
                        ORDER BY CASE WHEN cost.effective_at::date<=f.stat_date THEN 0 ELSE 1 END,
                            CASE WHEN cost.effective_at::date<=f.stat_date THEN cost.effective_at END DESC,
                            CASE WHEN cost.effective_at::date>f.stat_date THEN cost.effective_at END ASC,cost.id DESC
                        LIMIT 1
                    ) c ON TRUE
                    WHERE f.stat_date>=:b AND f.stat_date<=:e
                ) funnel""", b=begin, e=finish, u=until),
            "ozon": one("""WITH sku_master AS (SELECT DISTINCT ON (p.sku) p.sku,l.master_product_id
                    FROM ozon_products p JOIN marketplace_product_links l ON l.marketplace='ozon' AND l.active AND l.external_product_id=p.product_id::text
                    WHERE p.sku IS NOT NULL ORDER BY p.sku,l.id),
                sold AS (SELECT p.sku,p.accrual_date,CASE WHEN p.seller_price<0 THEN -coalesce(p.quantity,0) ELSE coalesce(p.quantity,0) END quantity
                    FROM ozon_finance_posting_accruals p JOIN ozon_finance_accrual_types t ON t.type_id=p.type_id
                    WHERE t.name='SaleCommission' AND p.accrual_date>=:b AND p.accrual_date<=:e)
                SELECT coalesce(sum(s.quantity*coalesce(c.unit_cost,0)),0) cost_of_goods,
                    coalesce(sum(s.quantity) FILTER (WHERE c.unit_cost IS NOT NULL),0) costed_units
                FROM sold s LEFT JOIN sku_master m ON m.sku=s.sku
                LEFT JOIN LATERAL (
                    SELECT cost.unit_cost FROM product_cost_records cost
                    WHERE cost.master_product_id=m.master_product_id
                    ORDER BY CASE WHEN cost.effective_at::date<=s.accrual_date THEN 0 ELSE 1 END,
                        CASE WHEN cost.effective_at::date<=s.accrual_date THEN cost.effective_at END DESC,
                        CASE WHEN cost.effective_at::date>s.accrual_date THEN cost.effective_at END ASC,cost.id DESC
                    LIMIT 1
                ) c ON TRUE""", b=begin, e=finish),
            "yandex_market": one("""WITH events AS (SELECT business_id,order_id,offer_id,transaction_at::date transaction_date,transaction_type,
                        max(quantity) quantity
                    FROM yandex_market_finance_transactions
                    WHERE transaction_at>=:b AND transaction_at<:u AND offer_id IS NOT NULL
                        AND transaction_type IN ('Начисление','Возврат') AND quantity>0
                    GROUP BY business_id,order_id,offer_id,transaction_at::date,transaction_type),
                sold AS (SELECT business_id,offer_id,transaction_date,
                    sum(CASE WHEN transaction_type='Начисление' THEN quantity
                        WHEN transaction_type='Возврат' THEN -quantity ELSE 0 END) quantity
                    FROM events GROUP BY business_id,offer_id,transaction_date)
                SELECT coalesce(sum(s.quantity*coalesce(c.unit_cost,0)),0) cost_of_goods,
                    coalesce(sum(s.quantity) FILTER (WHERE c.unit_cost IS NOT NULL),0) costed_units
                FROM sold s LEFT JOIN marketplace_product_links l ON l.marketplace='yandex_market' AND l.active
                    AND l.account_id=s.business_id::text AND l.external_product_id=s.offer_id
                LEFT JOIN LATERAL (
                    SELECT cost.unit_cost FROM product_cost_records cost
                    WHERE cost.master_product_id=l.master_product_id
                    ORDER BY CASE WHEN cost.effective_at::date<=s.transaction_date THEN 0 ELSE 1 END,
                        CASE WHEN cost.effective_at::date<=s.transaction_date THEN cost.effective_at END DESC,
                        CASE WHEN cost.effective_at::date>s.transaction_date THEN cost.effective_at END ASC,cost.id DESC
                    LIMIT 1
                ) c ON TRUE""", b=begin, u=until),
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
        values.update({
            "finance_rows": finance.get("rows"),
            "finance_from": finance.get("finance_from"),
            "finance_through": finance.get("finance_through"),
        })
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
            "wb": self._one(db, c + """ p AS (SELECT DISTINCT ON (vendor_code) vendor_code,nm_id FROM wb_products WHERE vendor_code IS NOT NULL ORDER BY vendor_code,id),s AS (SELECT coalesce(p.nm_id::text,x.vendor_code) k,x.quantity q FROM wb_warehouse_remains x LEFT JOIN p ON p.vendor_code=x.vendor_code WHERE x.warehouse_name='Всего находится на складах') SELECT coalesce(sum(s.q),0) units,coalesce(sum(s.q*coalesce(c.unit_cost,0)),0) cost_value FROM s LEFT JOIN marketplace_product_links l ON l.marketplace='wb' AND l.active AND l.external_product_id=s.k LEFT JOIN c ON c.master_product_id=l.master_product_id"""),
            "ozon": self._one(db, c + """ s AS (SELECT product_id::text k,sum(present) q FROM ozon_stocks GROUP BY product_id) SELECT coalesce(sum(s.q),0) units,coalesce(sum(s.q*coalesce(c.unit_cost,0)),0) cost_value FROM s LEFT JOIN marketplace_product_links l ON l.marketplace='ozon' AND l.active AND l.external_product_id=s.k LEFT JOIN c ON c.master_product_id=l.master_product_id"""),
            "yandex_market": self._one(db, c + """ s AS (SELECT offer_id k,sum(count) q FROM yandex_market_stocks WHERE stock_type='AVAILABLE' GROUP BY offer_id) SELECT coalesce(sum(s.q),0) units,coalesce(sum(s.q*coalesce(c.unit_cost,0)),0) cost_value FROM s LEFT JOIN marketplace_product_links l ON l.marketplace='yandex_market' AND l.active AND l.external_product_id=s.k LEFT JOIN c ON c.master_product_id=l.master_product_id"""),
        }
        for item in stocks.values(): self._convert(item)
        return stocks

    def _historical_stocks(self, db: Any, as_of: date) -> dict[str, Any]:
        c = """WITH c AS (SELECT DISTINCT ON (master_product_id) master_product_id,unit_cost FROM product_cost_records ORDER BY master_product_id,effective_at DESC,id DESC),"""
        stocks = {
            "wb": self._one(db, c + """ p AS (SELECT DISTINCT ON (vendor_code) vendor_code,nm_id FROM wb_products WHERE vendor_code IS NOT NULL ORDER BY vendor_code,id),s AS (SELECT coalesce(p.nm_id::text,x.vendor_code) k,x.quantity q FROM wb_warehouse_remain_snapshots x LEFT JOIN p ON p.vendor_code=x.vendor_code WHERE x.warehouse_name='Всего находится на складах' AND x.snapshot_date=(SELECT max(snapshot_date) FROM wb_warehouse_remain_snapshots WHERE snapshot_date<=:d)) SELECT coalesce(sum(s.q),0) units,coalesce(sum(s.q*coalesce(c.unit_cost,0)),0) cost_value FROM s LEFT JOIN marketplace_product_links l ON l.marketplace='wb' AND l.active AND l.external_product_id=s.k LEFT JOIN c ON c.master_product_id=l.master_product_id""", d=as_of),
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
            "revenue": revenue, "sales_revenue": revenue - _number(values.get("compensation")),
            "compensation": _number(values.get("compensation")),
            "expenses": expenses, "expense_ratio": expenses / revenue * 100 if revenue else 0,
            "net_payout": revenue - expenses, "cost_of_goods": cost,
            "cost_missing": bool(values.get("cost_missing")),
            "profit": revenue - expenses - cost,
            "profit_margin": (revenue - expenses - cost) / revenue * 100 if revenue else 0,
            "sold_units": values.get("buyouts"),
            "finance_from": values.get("finance_from"), "finance_through": values.get("finance_through"),
        }

    @staticmethod
    def _expense_category(label: str) -> tuple[str, str]:
        normalized = label.casefold()
        if "размещение товарных предложений" in normalized:
            return "commission", "Комиссия и вознаграждение площадки"
        if "приём платежа" in normalized or "прием платежа" in normalized:
            return "acquiring", "Эквайринг и платежи"
        if any(pattern in normalized for pattern in (
            "реклам", "продвиж", "буст", "рассыл", "отзывы за баллы",
            "promotion", "payperclick", "campaign",
        )):
            return "advertising", "Реклама и продвижение"
        if (
            "возврат списания" in normalized
            or "скидк" in normalized
            or "совместных акц" in normalized
        ):
            return "discounts", "Скидки и корректировки акций"
        categories = (
            ("advertising", "Реклама и продвижение", ("реклам", "продвиж", "буст", "рассыл", "отзывы за баллы", "promotion", "payperclick", "campaign")),
            ("returns", "Возвраты и обратная логистика", ("возврат", "return", "обратн")),
            ("logistics", "Логистика и доставка", ("логист", "достав", "delivery", "перевоз", "crossdock", "кросс-док")),
            ("storage", "Хранение", ("хран", "размещ", "storage", "placement")),
            ("acceptance", "Приёмка", ("прием", "приём", "обработк", "acceptance", "supplyinbound")),
            ("commission", "Комиссия и вознаграждение площадки", ("комисс", "вознагражд", "commission", "agency")),
            ("acquiring", "Эквайринг и платежи", ("эквайр", "платеж", "payment", "acquiring")),
            ("partner_services", "Услуги партнёров", ("партнер", "партнёр", "partner")),
            ("penalties", "Штрафы", ("штраф", "penalt")),
        )
        for key, title, patterns in categories:
            if any(pattern in normalized for pattern in patterns):
                return key, title
        return "other", "Прочие услуги и корректировки"

    @staticmethod
    def _expense_lines(
        rows: list[dict[str, Any]],
        *,
        revenue: float,
        expected_total: float,
        source: str,
    ) -> list[dict[str, Any]]:
        lines: list[dict[str, Any]] = []
        allocated = 0.0
        for index, row in enumerate(rows):
            if row.get("error"):
                continue
            amount = _number(row.get("amount"))
            if abs(amount) < 0.005:
                continue
            label = str(row.get("label") or "Прочая операция")
            key = str(row.get("key") or f"line-{index}")
            # Marketplace dictionaries often provide a readable Russian label and
            # a more stable English operation code.  Use both for categorisation:
            # for example, "Оплата за клик" is identified by PayPerClick.
            category, category_label = DashboardService._expense_category(f"{label} {key}")
            allocated += amount
            lines.append({
                "key": key,
                "label": label,
                "category": category,
                "category_label": category_label,
                "amount": amount,
                "share_percent": amount / revenue * 100 if revenue else 0,
                "source": source,
            })
        residual = expected_total - allocated
        if abs(residual) >= 0.01:
            lines.append({
                "key": "reconciliation_adjustment",
                "label": "Нераспределённая финансовая корректировка",
                "category": "other",
                "category_label": "Прочие услуги и корректировки",
                "amount": residual,
                "share_percent": residual / revenue * 100 if revenue else 0,
                "source": "расчётная сверка с итогом финансового отчёта",
            })
        return lines

    def _pnl_expense_breakdowns(
        self,
        db: Any,
        begin: date,
        finish: date,
        views: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        until = finish + timedelta(days=1)
        wb = self._one(db, """SELECT
            coalesce(sum(CASE
                WHEN seller_operation_name='Возврат'
                    THEN -(retail_price_with_discount*quantity-for_pay-acquiring_fee)
                WHEN seller_operation_name IN ('Продажа','Бронирование товара через самовывоз')
                    THEN retail_price_with_discount*quantity-for_pay-acquiring_fee
                ELSE 0 END),0) commission,
            coalesce(sum(delivery_service),0) logistics,
            coalesce(sum(paid_storage),0) storage,
            coalesce(sum(paid_acceptance),0) acceptance,
            coalesce(sum(CASE
                WHEN seller_operation_name='Возврат' THEN -acquiring_fee
                WHEN seller_operation_name IN ('Продажа','Бронирование товара через самовывоз') THEN acquiring_fee
                ELSE 0 END),0) acquiring,
            coalesce(sum(penalty),0) penalties,
            coalesce(sum(deduction),0) deductions,
            coalesce(sum(coalesce(nullif(x.raw_data->>'paymentSchedule','')::numeric,0)),0) payment_schedule,
            max(r.details_synced_at) updated_at
            FROM wb_financial_sales_rows x
            JOIN wb_financial_sales_reports r ON r.id=x.report_id
            WHERE x.rr_date>=:b AND x.rr_date<:u""", b=begin, u=until)
        wb_advertising = self._one(db, """SELECT coalesce(sum(amount),0) amount,
            max(fetched_at) updated_at FROM wb_advert_expenses
            WHERE expense_time>=:b AND expense_time<:u""", b=begin, u=until)
        wb_rows = [] if "error" in wb else [
            {"key": "commission", "label": "Комиссия Wildberries", "amount": wb.get("commission")},
            {"key": "logistics", "label": "Логистика и доставка", "amount": wb.get("logistics")},
            {"key": "storage", "label": "Хранение", "amount": wb.get("storage")},
            {"key": "acceptance", "label": "Платная приёмка", "amount": wb.get("acceptance")},
            {"key": "acquiring", "label": "Эквайринг", "amount": wb.get("acquiring")},
            {"key": "penalties", "label": "Штрафы", "amount": wb.get("penalties")},
            {"key": "deductions", "label": "Прочие удержания", "amount": (
                _number(wb.get("deductions")) - _number(wb_advertising.get("amount"))
            )},
            {"key": "payment_schedule", "label": "Изменение срока единовременной выплаты", "amount": wb.get("payment_schedule")},
            {"key": "advertising", "label": "Реклама Wildberries", "amount": wb_advertising.get("amount")},
        ]
        ozon_rows = self._many(db, """WITH expense_rows AS (
            SELECT t.name key,
                   coalesce(nullif(t.description,''),t.name) label,
                   sum(nullif(fee->'accrued'->>'amount','')::numeric) signed_amount
            FROM ozon_finance_accruals a
            CROSS JOIN LATERAL jsonb_path_query(
                a.raw_data::jsonb,
                'strict $.** ? (exists(@.type_id) && exists(@.accrued))'
            ) fee
            JOIN ozon_finance_accrual_types t
              ON t.type_id=(fee->>'type_id')::integer
            WHERE a.accrual_date BETWEEN :b AND :e
              AND t.name<>'SaleCommission'
            GROUP BY t.name,t.description
            UNION ALL
            SELECT t.name key,
                   coalesce(nullif(t.description,''),t.name) label,
                   sum(p.accrued) signed_amount
            FROM ozon_finance_posting_accruals p
            JOIN ozon_finance_accrual_types t ON t.type_id=p.type_id
            WHERE p.accrual_date BETWEEN :b AND :e
              AND t.name='SaleCommission'
            GROUP BY t.name,t.description
        )
        SELECT key,label,greatest(-sum(signed_amount),0) amount
        FROM expense_rows
        GROUP BY key,label
        HAVING sum(signed_amount)<0
        ORDER BY greatest(-sum(signed_amount),0) DESC""", b=begin, e=finish)
        yandex_rows = self._many(db, """SELECT
            concat_ws(' · ',nullif(product_or_service,''),nullif(transaction_source,''),transaction_type) label,
            coalesce(product_or_service,'')||':'||coalesce(transaction_source,'')||':'||coalesce(transaction_type,'unknown') key,
            -sum(amount) amount
            FROM yandex_market_finance_transactions
            WHERE transaction_at>=:b AND transaction_at<:u
              AND NOT (transaction_type IN ('Начисление','Возврат') AND quantity>0)
            GROUP BY product_or_service,transaction_source,transaction_type
            HAVING abs(sum(amount))>=0.005
            ORDER BY abs(sum(amount)) DESC""", b=begin, u=until)
        metadata = {
            "wb": {
                "table": "wb_financial_sales_rows",
                "endpoint": "WB financial sales report details",
                "updated_at": wb.get("updated_at") if "error" not in wb else None,
                "rows": wb_rows,
            },
            "ozon": {
                "table": "ozon_finance_accruals + ozon_finance_posting_accruals",
                "endpoint": "/v1/finance/accrual/by-day + /v1/finance/accrual/postings",
                "updated_at": self._one(
                    db,
                    "SELECT max(fetched_at) updated_at FROM ozon_finance_accruals WHERE accrual_date BETWEEN :b AND :e",
                    b=begin, e=finish,
                ).get("updated_at"),
                "rows": ozon_rows,
            },
            "yandex_market": {
                "table": "yandex_market_finance_transactions",
                "endpoint": "United Netting Report",
                "updated_at": self._one(
                    db,
                    "SELECT max(fetched_at) updated_at FROM yandex_market_finance_transactions WHERE transaction_at>=:b AND transaction_at<:u",
                    b=begin, u=until,
                ).get("updated_at"),
                "rows": yandex_rows,
            },
        }
        result = {}
        for marketplace, meta in metadata.items():
            view = views[marketplace]
            revenue = _number(view.get("revenue")) if view.get("available") else 0
            expenses = _number(view.get("expenses")) if view.get("available") else 0
            result[marketplace] = {
                "lines": self._expense_lines(
                    meta["rows"], revenue=revenue, expected_total=expenses,
                    source=f"{meta['endpoint']} → {meta['table']}",
                ) if view.get("available") else [],
                "source_table": meta["table"],
                "source_endpoint": meta["endpoint"],
                "updated_at": meta["updated_at"],
            }
        return result

    def _pnl_unallocated(
        self,
        db: Any,
        begin: date,
        finish: date,
    ) -> dict[str, dict[str, Any]]:
        rows = self._many(db, """SELECT marketplace,
            coalesce(sum(revenue_kopecks),0) revenue_kopecks,
            coalesce(sum(marketplace_expense_kopecks),0) expense_kopecks,
            coalesce(sum(logistics_kopecks),0) logistics_kopecks,
            coalesce(sum(advertising_kopecks),0) advertising_kopecks,
            coalesce(sum(cost_kopecks),0) cost_kopecks,
            coalesce(sum(profit_kopecks),0) profit_kopecks
            FROM fact_product_economics_daily
            WHERE is_unallocated IS TRUE
              AND business_date BETWEEN :b AND :e
            GROUP BY marketplace""", b=begin, e=finish)
        by_marketplace = {str(row["marketplace"]): row for row in rows if not row.get("error")}
        result: dict[str, dict[str, Any]] = {}
        for marketplace in ("wb", "ozon", "yandex_market"):
            row = by_marketplace.get(marketplace, {})
            revenue = int(row.get("revenue_kopecks") or 0) / 100
            expenses = int(row.get("expense_kopecks") or 0) / 100
            logistics = int(row.get("logistics_kopecks") or 0) / 100
            advertising = int(row.get("advertising_kopecks") or 0) / 100
            cost = int(row.get("cost_kopecks") or 0) / 100
            profit = int(row.get("profit_kopecks") or 0) / 100
            components = [
                {"key": "revenue", "label": "Корректировки выручки", "amount": revenue},
                {"key": "other_expenses", "label": "Комиссии, услуги и прочие удержания", "amount": expenses - logistics},
                {"key": "logistics", "label": "Логистика", "amount": logistics},
                {"key": "cost", "label": "Корректировка себестоимости", "amount": cost},
                {"key": "advertising", "label": "Реклама без надёжной привязки к SKU", "amount": advertising},
            ]
            result[marketplace] = {
                "profit": profit,
                "revenue": revenue,
                "expenses": expenses,
                "logistics": logistics,
                "advertising": advertising,
                "cost": cost,
                "components": [item for item in components if abs(item["amount"]) >= 0.01],
                "available": bool(row),
            }
        return result

    @staticmethod
    def _total_pnl(views: dict[str, dict[str, Any]]) -> dict[str, Any]:
        available = [value for value in views.values() if value.get("available")]
        revenue = sum(_number(value.get("revenue")) for value in available)
        expenses = sum(_number(value.get("expenses")) for value in available)
        cost = sum(_number(value.get("cost_of_goods")) for value in available)
        categorized: dict[str, dict[str, Any]] = {}
        for value in available:
            for line in value.get("expense_lines", []):
                key = str(line["category"])
                item = categorized.setdefault(key, {
                    "key": key, "label": line["category_label"], "amount": 0.0,
                })
                item["amount"] += _number(line["amount"])
        expense_lines = sorted(categorized.values(), key=lambda item: abs(item["amount"]), reverse=True)
        for line in expense_lines:
            line["share_percent"] = line["amount"] / revenue * 100 if revenue else 0
        profit = revenue - expenses - cost
        return {
            "covered": len(available), "revenue": revenue,
            "sales_revenue": sum(_number(value.get("sales_revenue")) for value in available),
            "compensation": sum(_number(value.get("compensation")) for value in available),
            "expenses": expenses, "expense_ratio": expenses / revenue * 100 if revenue else 0,
            "cost_of_goods": cost, "net_payout": revenue - expenses,
            "profit": profit, "profit_margin": profit / revenue * 100 if revenue else 0,
            "cost_missing": any(value.get("cost_missing") for value in available),
            "expense_lines": expense_lines,
        }

    def pnl(self, start: str | None, end: str | None) -> dict[str, Any]:
        begin, finish = self.period(start, end)
        previous_begin, previous_finish = self.previous_period(begin, finish)
        with self.session_factory() as db:
            current_raw = self._period_metrics(db, begin, finish)["marketplaces"]
            previous_raw = self._period_metrics(db, previous_begin, previous_finish)["marketplaces"]
            current = {key: self._pnl_view(values, key) for key, values in current_raw.items()}
            previous = {key: self._pnl_view(values, key) for key, values in previous_raw.items()}
            current_breakdowns = self._pnl_expense_breakdowns(db, begin, finish, current)
            previous_breakdowns = self._pnl_expense_breakdowns(
                db, previous_begin, previous_finish, previous
            )
            current_unallocated = self._pnl_unallocated(db, begin, finish)
            previous_unallocated = self._pnl_unallocated(
                db, previous_begin, previous_finish
            )
        for key in current:
            current[key].update(current_breakdowns[key])
            current[key]["expense_lines"] = current[key].pop("lines")
            current[key]["unallocated"] = current_unallocated[key]
            previous[key].update(previous_breakdowns[key])
            previous[key]["expense_lines"] = previous[key].pop("lines")
            previous[key]["unallocated"] = previous_unallocated[key]
        return {
            "period": {"from": begin.isoformat(), "to": finish.isoformat()},
            "previous_period": {"from": previous_begin.isoformat(), "to": previous_finish.isoformat()},
            "marketplaces": current, "previous_marketplaces": previous,
            "total": self._total_pnl(current),
            "previous_total": self._total_pnl(previous),
        }

    @staticmethod
    def _allocate_kopecks(total: int, weights: dict[str, int]) -> dict[str, int]:
        """Allocate an integer total without losing a kopeck."""
        positive = {key: max(int(value), 0) for key, value in weights.items()}
        denominator = sum(positive.values())
        if not denominator:
            return {key: 0 for key in weights}
        sign = -1 if total < 0 else 1
        absolute = abs(int(total))
        allocated: dict[str, int] = {}
        remainders: list[tuple[int, str]] = []
        for key, weight in positive.items():
            amount, remainder = divmod(absolute * weight, denominator)
            allocated[key] = amount * sign
            remainders.append((remainder, key))
        residual = absolute - sum(abs(value) for value in allocated.values())
        for _, key in sorted(remainders, key=lambda item: (-item[0], item[1]))[:residual]:
            allocated[key] += sign
        return allocated

    @staticmethod
    def _abc_categories(values: dict[str, int], *, loss_class: bool = False) -> dict[str, str]:
        """Classify positive contributions as 80/15/5 while keeping ties together."""
        result = {
            key: ("У" if loss_class and int(value) <= 0 else "—")
            for key, value in values.items()
        }
        positive = [(key, int(value)) for key, value in values.items() if int(value) > 0]
        total = sum(value for _, value in positive)
        if not total:
            return result
        cumulative = 0
        by_value: dict[int, list[str]] = {}
        for key, value in positive:
            by_value.setdefault(value, []).append(key)
        for value in sorted(by_value, reverse=True):
            share_before = cumulative / total
            category = "A" if share_before < 0.80 else "B" if share_before < 0.95 else "C"
            for key in sorted(by_value[value]):
                result[key] = category
            cumulative += value * len(by_value[value])
        return result

    @staticmethod
    def _closed_month_period(start: str | None, end: str | None) -> tuple[date, date]:
        if start or end:
            return DashboardService.period(start, end)
        first_current = date.today().replace(day=1)
        finish = first_current - timedelta(days=1)
        return finish.replace(day=1), finish

    def _legacy_abc_unused(self, start: str | None, end: str | None) -> dict[str, Any]:
        """Build a P&L-reconciled product matrix from financial facts."""
        begin, finish = self._closed_month_period(start, end)
        pnl = self.pnl(begin.isoformat(), finish.isoformat())
        market_keys = ("wb", "ozon", "yandex_market")
        with self.session_factory() as db:
            products = self._many(db, """SELECT mp.id master_product_id,mp.article,mp.name,
                    (SELECT media.id FROM marketplace_product_media media
                     WHERE media.master_product_id=mp.id AND media.active
                       AND media.media_type='image' AND media.download_status='downloaded'
                       AND media.local_path IS NOT NULL
                     ORDER BY CASE media.marketplace WHEN 'wb' THEN 0 WHEN 'ozon' THEN 1 ELSE 2 END,
                       CASE WHEN lower(media.role) IN ('main','primary','cover') THEN 0 ELSE 1 END,
                       media.position,media.id LIMIT 1) image_id
                FROM master_products mp WHERE mp.active ORDER BY mp.article""")
            facts = self._many(db, """WITH base AS (
                    SELECT f.marketplace,f.master_product_id,
                        coalesce('m:'||f.master_product_id::text,
                            f.marketplace||':'||coalesce(f.seller_sku,f.offer_id,
                                f.marketplace_sku,'unmatched')) row_key,
                        coalesce(mp.article,f.seller_sku,f.offer_id,f.marketplace_sku,'—') article,
                        coalesce(mp.name,f.seller_sku,f.offer_id,f.marketplace_sku,'') name,
                        f.quantity,f.net_revenue_kopecks,
                        coalesce(f.cost_amount_kopecks,0) cost_amount_kopecks,
                        f.cost_status
                    FROM fact_sales f LEFT JOIN master_products mp ON mp.id=f.master_product_id
                    WHERE f.business_date BETWEEN :b AND :e AND f.is_financial
                ) SELECT marketplace,master_product_id,row_key,max(article) article,max(name) name,
                    sum(quantity)::bigint units,sum(net_revenue_kopecks)::bigint revenue_kopecks,
                    sum(cost_amount_kopecks)::bigint cost_kopecks,
                    count(*) FILTER (WHERE cost_status<>'matched') missing_cost_rows
                FROM base GROUP BY marketplace,master_product_id,row_key""", b=begin, e=finish)
            ad_rows = self._many(db, """WITH wb AS (
                    SELECT 'wb' marketplace,l.master_product_id,
                        sum(p.spend) spend
                    FROM wb_advert_product_daily_stats p
                    JOIN wb_advert_daily_stats d ON d.id=p.daily_stat_id
                    LEFT JOIN marketplace_product_links l ON l.marketplace='wb' AND l.active
                        AND l.external_product_id=p.nm_id::text
                    WHERE d.stat_date>=:b AND d.stat_date<CAST(:e AS date)+1
                    GROUP BY l.master_product_id
                ), ozon AS (
                    SELECT 'ozon' marketplace,l.master_product_id,sum(a.spend) spend
                    FROM ozon_ad_daily_stats a
                    LEFT JOIN ozon_products p ON p.sku=a.sku
                    LEFT JOIN marketplace_product_links l ON l.marketplace='ozon' AND l.active
                        AND l.external_product_id=p.product_id::text
                    WHERE a.stat_date BETWEEN :b AND :e GROUP BY l.master_product_id
                ) SELECT * FROM wb UNION ALL SELECT * FROM ozon""", b=begin, e=finish)
            advertising = self._advertising_metrics(db, begin, finish)

        rows: dict[str, dict[str, Any]] = {}
        for product in products:
            if product.get("error"):
                raise RuntimeError(product["error"])
            key = f"m:{product['master_product_id']}"
            rows[key] = {
                "key": key, "master_product_id": product["master_product_id"],
                "article": product.get("article") or "—", "name": product.get("name") or "",
                "image_url": f"/api/product-image?id={product['image_id']}" if product.get("image_id") else None,
                **{marketplace: None for marketplace in market_keys},
            }
        grouped_facts: dict[str, dict[str, dict[str, Any]]] = {key: {} for key in market_keys}
        for fact in facts:
            if fact.get("error"):
                raise RuntimeError(fact["error"])
            marketplace = fact["marketplace"]
            row_key = fact["row_key"]
            rows.setdefault(row_key, {
                "key": row_key, "master_product_id": fact.get("master_product_id"),
                "article": fact.get("article") or "—", "name": fact.get("name") or "",
                "image_url": None, **{key: None for key in market_keys},
            })
            grouped_facts[marketplace][row_key] = fact

        direct_ads: dict[str, dict[str, int]] = {key: {} for key in market_keys}
        unlinked_advertising = {key: 0 for key in market_keys}
        for ad in ad_rows:
            if ad.get("error"):
                raise RuntimeError(ad["error"])
            marketplace = ad["marketplace"]
            amount = _kopecks(ad.get("spend"))
            if ad.get("master_product_id") is None:
                unlinked_advertising[marketplace] += amount
            else:
                key = f"m:{ad['master_product_id']}"
                direct_ads[marketplace][key] = direct_ads[marketplace].get(key, 0) + amount

        allocation_notes: dict[str, dict[str, Any]] = {}
        for marketplace in market_keys:
            view = pnl["marketplaces"][marketplace]
            facts_by_key = grouped_facts[marketplace]
            if not view.get("available"):
                allocation_notes[marketplace] = {
                    "available": False, "notice": view.get("notice"),
                    "unallocated_advertising_kopecks": 0,
                }
                continue
            weights = {key: max(int(fact.get("revenue_kopecks") or 0), 0)
                       for key, fact in facts_by_key.items()}
            if not sum(weights.values()):
                weights = {key: abs(int(fact.get("revenue_kopecks") or 0))
                           for key, fact in facts_by_key.items()}
            revenue_target = _kopecks(view.get("revenue"))
            expense_target = _kopecks(view.get("expenses"))
            cost_target = _kopecks(view.get("cost_of_goods"))
            revenue_raw = sum(int(fact.get("revenue_kopecks") or 0) for fact in facts_by_key.values())
            cost_raw = sum(int(fact.get("cost_kopecks") or 0) for fact in facts_by_key.values())
            revenue_adjustments = self._allocate_kopecks(revenue_target - revenue_raw, weights)
            expense_allocations = self._allocate_kopecks(expense_target, weights)
            cost_adjustments = self._allocate_kopecks(cost_target - cost_raw, weights)
            logistics_target = sum(
                _kopecks(line.get("amount")) for line in view.get("expense_lines", [])
                if line.get("category") in {"logistics", "returns"}
            )
            logistics_allocations = self._allocate_kopecks(logistics_target, weights)
            ad_target = _kopecks(advertising.get(marketplace, {}).get("performance_spend"))
            if marketplace == "yandex_market":
                ads_by_key = self._allocate_kopecks(ad_target, weights)
                ad_method = "allocated_by_revenue"
                ad_unallocated = ad_target - sum(ads_by_key.values())
            else:
                ads_by_key = direct_ads[marketplace]
                ad_method = "direct_product_report"
                ad_unallocated = ad_target - sum(ads_by_key.values())
            ad_unallocated += unlinked_advertising[marketplace]
            for key, fact in facts_by_key.items():
                revenue = int(fact.get("revenue_kopecks") or 0) + revenue_adjustments.get(key, 0)
                cost = int(fact.get("cost_kopecks") or 0) + cost_adjustments.get(key, 0)
                expense = expense_allocations.get(key, 0)
                units = int(fact.get("units") or 0)
                logistics = logistics_allocations.get(key, 0)
                ads = ads_by_key.get(key, 0)
                rows[key][marketplace] = {
                    "available": True, "units": units,
                    "revenue_kopecks": revenue, "expense_kopecks": expense,
                    "cost_kopecks": cost, "profit_kopecks": revenue - expense - cost,
                    "advertising_kopecks": ads, "advertising_method": ad_method,
                    "logistics_kopecks": logistics,
                    "missing_cost_rows": int(fact.get("missing_cost_rows") or 0),
                    "allocated_revenue_adjustment_kopecks": revenue_adjustments.get(key, 0),
                    "allocated_expense_kopecks": expense,
                    "allocated_cost_adjustment_kopecks": cost_adjustments.get(key, 0),
                }
            allocation_notes[marketplace] = {
                "available": True, "advertising_method": ad_method,
                "unallocated_advertising_kopecks": ad_unallocated,
                "revenue_target_kopecks": revenue_target,
                "expense_target_kopecks": expense_target,
                "cost_target_kopecks": cost_target,
                "logistics_target_kopecks": logistics_target,
            }

        for row in rows.values():
            total = {
                "available": any(row[key] and row[key].get("available") for key in market_keys),
                "units": 0, "revenue_kopecks": 0, "expense_kopecks": 0,
                "cost_kopecks": 0, "profit_kopecks": 0,
                "advertising_kopecks": 0, "logistics_kopecks": 0,
                "missing_cost_rows": 0,
            }
            for marketplace in market_keys:
                values = row[marketplace]
                if not values:
                    continue
                for field in ("units", "revenue_kopecks", "expense_kopecks", "cost_kopecks",
                              "profit_kopecks", "advertising_kopecks", "logistics_kopecks",
                              "missing_cost_rows"):
                    total[field] += int(values.get(field) or 0)
            row["total"] = total

        scopes = ("total", *market_keys)
        for scope in scopes:
            values = {key: int(row[scope]["revenue_kopecks"])
                      for key, row in rows.items() if row.get(scope) and row[scope].get("available")}
            profits = {key: int(row[scope]["profit_kopecks"])
                       for key, row in rows.items() if row.get(scope) and row[scope].get("available")}
            revenue_classes = self._abc_categories(values)
            profit_classes = self._abc_categories(profits, loss_class=True)
            positive_revenue = sum(max(value, 0) for value in values.values())
            positive_profit = sum(max(value, 0) for value in profits.values())
            for key, revenue in values.items():
                metric = rows[key][scope]
                profit = profits[key]
                metric.update({
                    "revenue_category": revenue_classes[key],
                    "revenue_share_percent": revenue / positive_revenue * 100 if positive_revenue else 0,
                    "profit_category": profit_classes[key],
                    "profit_share_percent": profit / positive_profit * 100 if positive_profit else 0,
                    "profit_margin_percent": profit / revenue * 100 if revenue else 0,
                    "advertising_drr_percent": metric["advertising_kopecks"] / revenue * 100 if revenue else 0,
                    "logistics_share_percent": metric["logistics_kopecks"] / revenue * 100 if revenue else 0,
                    "logistics_per_unit_kopecks": (
                        int(round(metric["logistics_kopecks"] / metric["units"]))
                        if metric["units"] > 0 else None
                    ),
                })

        result_rows = sorted(rows.values(), key=lambda row: (
            -int(row["total"].get("revenue_kopecks") or 0), row["article"], row["key"]
        ))
        total_metric = {
            field: sum(int(row["total"].get(field) or 0) for row in result_rows)
            for field in ("revenue_kopecks", "profit_kopecks", "advertising_kopecks", "logistics_kopecks")
        }
        total_metric.update({
            "sku_count": sum(bool(row["total"].get("revenue_kopecks")) for row in result_rows),
            "unprofitable_count": sum(row["total"].get("profit_category") == "У" for row in result_rows),
            "classes": {
                kind: {category: sum(row["total"].get(f"{kind}_category") == category for row in result_rows)
                       for category in ("A", "B", "C", "У")}
                for kind in ("revenue", "profit")
            },
        })
        controls = {}
        for marketplace in market_keys:
            expected = pnl["marketplaces"][marketplace]
            actual_revenue = sum(int(row.get(marketplace, {}).get("revenue_kopecks") or 0)
                                 for row in result_rows)
            actual_profit = sum(int(row.get(marketplace, {}).get("profit_kopecks") or 0)
                                for row in result_rows)
            controls[marketplace] = {
                "available": bool(expected.get("available")),
                "revenue_expected_kopecks": _kopecks(expected.get("revenue")) if expected.get("available") else None,
                "revenue_actual_kopecks": actual_revenue,
                "revenue_delta_kopecks": actual_revenue - _kopecks(expected.get("revenue")) if expected.get("available") else None,
                "profit_expected_kopecks": _kopecks(expected.get("profit")) if expected.get("available") else None,
                "profit_actual_kopecks": actual_profit,
                "profit_delta_kopecks": actual_profit - _kopecks(expected.get("profit")) if expected.get("available") else None,
            }
        return {
            "period": {"from": begin.isoformat(), "to": finish.isoformat()},
            "rows": result_rows, "summary": total_metric,
            "allocation": allocation_notes, "controls": controls,
            "methodology": {
                "abc": "A=first 80%, B=next 15%, C=last 5%; ties stay together",
                "profit": "financial revenue - P&L expenses allocated by net revenue - product cost",
                "logistics": "P&L logistics and return-logistics allocated by net revenue",
            },
        }

    def abc(self, start: str | None, end: str | None) -> dict[str, Any]:
        """Read the ABC matrix exclusively from normalized analytical facts."""
        begin, finish = self._closed_month_period(start, end)
        pnl = self.pnl(begin.isoformat(), finish.isoformat())
        market_keys = ("wb", "ozon", "yandex_market")
        expected_days = (finish - begin).days + 1
        with self.session_factory() as db:
            products = self._many(db, """SELECT mp.id master_product_id,mp.article,mp.name,
                    (SELECT media.id FROM marketplace_product_media media
                     WHERE media.master_product_id=mp.id AND media.active
                       AND media.media_type='image' AND media.download_status='downloaded'
                       AND media.local_path IS NOT NULL
                     ORDER BY CASE media.marketplace WHEN 'wb' THEN 0 WHEN 'ozon' THEN 1 ELSE 2 END,
                       CASE WHEN lower(media.role) IN ('main','primary','cover') THEN 0 ELSE 1 END,
                       media.position,media.id LIMIT 1) image_id
                FROM master_products mp WHERE mp.active ORDER BY mp.article""")
            facts = self._many(db, """SELECT marketplace,product_key,
                    max(master_product_id) master_product_id,max(seller_sku) seller_sku,
                    max(product_name) product_name,bool_or(is_unallocated) is_unallocated,
                    sum(quantity) units,sum(revenue_kopecks) revenue_kopecks,
                    sum(marketplace_expense_kopecks) expense_kopecks,
                    sum(logistics_kopecks) logistics_kopecks,
                    sum(advertising_kopecks) advertising_kopecks,
                    sum(cost_kopecks) cost_kopecks,sum(profit_kopecks) profit_kopecks,
                    sum(missing_cost_rows) missing_cost_rows,
                    min(expense_allocation_method) expense_allocation_method,
                    min(advertising_allocation_method) advertising_allocation_method
                FROM fact_product_economics_daily
                WHERE business_date BETWEEN :b AND :e
                GROUP BY marketplace,product_key""", b=begin, e=finish)
            control_rows = self._many(db, """SELECT marketplace,
                    count(DISTINCT business_date) FILTER (WHERE source_complete) coverage_days,
                    min(business_date) FILTER (WHERE source_complete) data_from,
                    max(business_date) FILTER (WHERE source_complete) data_to,
                    sum(revenue_kopecks) revenue_kopecks,
                    sum(marketplace_expense_kopecks) expense_kopecks,
                    sum(logistics_kopecks) logistics_kopecks,
                    sum(advertising_kopecks) advertising_kopecks,
                    sum(advertising_unallocated_kopecks) advertising_unallocated_kopecks,
                    sum(cost_kopecks) cost_kopecks,sum(profit_kopecks) profit_kopecks,
                    sum(unmatched_rows) unmatched_rows,max(normalized_at) normalized_at
                FROM fact_product_economics_controls
                WHERE business_date BETWEEN :b AND :e GROUP BY marketplace""", b=begin, e=finish)

        rows: dict[str, dict[str, Any]] = {}
        for product in products:
            if product.get("error"):
                raise RuntimeError(product["error"])
            key = f"m:{product['master_product_id']}"
            rows[key] = {
                "key": key, "master_product_id": product["master_product_id"],
                "article": product.get("article") or "—", "name": product.get("name") or "",
                "image_url": f"/api/product-image?id={product['image_id']}" if product.get("image_id") else None,
                "is_unallocated": False,
                **{marketplace: None for marketplace in market_keys},
            }
        controls = {key: {
            "available": False, "coverage_days": 0, "expected_days": expected_days,
            "notice": "аналитический слой не покрывает выбранный период",
        } for key in market_keys}
        for control in control_rows:
            if control.get("error"):
                raise RuntimeError(control["error"])
            marketplace = control["marketplace"]
            coverage_days = int(control.get("coverage_days") or 0)
            available = coverage_days == expected_days
            controls[marketplace] = {
                **control, "coverage_days": coverage_days,
                "expected_days": expected_days, "available": available,
                "notice": None if available else f"покрытие {coverage_days}/{expected_days} дней",
            }
        for fact in facts:
            if fact.get("error"):
                raise RuntimeError(fact["error"])
            marketplace = fact["marketplace"]
            key = fact["product_key"]
            is_unallocated = bool(fact.get("is_unallocated"))
            rows.setdefault(key, {
                "key": key, "master_product_id": fact.get("master_product_id"),
                "article": "НЕРАСПРЕДЕЛЕНО" if is_unallocated else fact.get("seller_sku") or "—",
                "name": fact.get("product_name") or ("Нераспределённые финансовые операции" if is_unallocated else ""),
                "image_url": None, "is_unallocated": is_unallocated,
                **{item: None for item in market_keys},
            })
            if controls[marketplace]["available"]:
                fact["available"] = True
                rows[key][marketplace] = fact

        for row in rows.values():
            total = {
                "available": False, "units": 0, "revenue_kopecks": 0,
                "expense_kopecks": 0, "cost_kopecks": 0, "profit_kopecks": 0,
                "advertising_kopecks": 0, "logistics_kopecks": 0,
                "missing_cost_rows": 0,
            }
            for marketplace in market_keys:
                values = row.get(marketplace)
                if not values:
                    continue
                total["available"] = True
                for field in ("units", "revenue_kopecks", "expense_kopecks", "cost_kopecks",
                              "profit_kopecks", "advertising_kopecks", "logistics_kopecks",
                              "missing_cost_rows"):
                    total[field] += int(values.get(field) or 0)
            row["total"] = total

        scopes = ("total", *market_keys)
        for scope in scopes:
            revenue_values = {
                key: int(row[scope]["revenue_kopecks"])
                for key, row in rows.items()
                if not row["is_unallocated"] and row.get(scope) and row[scope].get("available")
            }
            profit_values = {
                key: int(row[scope]["profit_kopecks"])
                for key, row in rows.items()
                if not row["is_unallocated"] and row.get(scope) and row[scope].get("available")
            }
            revenue_classes = self._abc_categories(revenue_values)
            profit_classes = self._abc_categories(profit_values, loss_class=True)
            positive_revenue = sum(max(value, 0) for value in revenue_values.values())
            positive_profit = sum(max(value, 0) for value in profit_values.values())
            for key, revenue in revenue_values.items():
                metric = rows[key][scope]
                profit = profit_values[key]
                metric.update({
                    "revenue_category": revenue_classes[key],
                    "revenue_share_percent": revenue / positive_revenue * 100 if positive_revenue else 0,
                    "profit_category": profit_classes[key],
                    "profit_share_percent": profit / positive_profit * 100 if positive_profit else 0,
                    "profit_margin_percent": profit / revenue * 100 if revenue else 0,
                    "advertising_drr_percent": metric["advertising_kopecks"] / revenue * 100 if revenue else 0,
                    "logistics_share_percent": metric["logistics_kopecks"] / revenue * 100 if revenue else 0,
                    "logistics_per_unit_kopecks": (
                        int(round(metric["logistics_kopecks"] / metric["units"]))
                        if metric["units"] > 0 else None
                    ),
                })

        result_rows = sorted(rows.values(), key=lambda row: (
            row["is_unallocated"], -int(row["total"].get("revenue_kopecks") or 0),
            row["article"], row["key"],
        ))
        summary = {
            field: sum(int(row["total"].get(field) or 0) for row in result_rows)
            for field in ("revenue_kopecks", "profit_kopecks", "advertising_kopecks", "logistics_kopecks")
        }
        summary.update({
            "sku_count": sum(not row["is_unallocated"] and bool(row["total"].get("revenue_kopecks")) for row in result_rows),
            "unprofitable_count": sum(not row["is_unallocated"] and row["total"].get("profit_category") == "У" for row in result_rows),
            "classes": {
                kind: {category: sum(not row["is_unallocated"] and row["total"].get(f"{kind}_category") == category for row in result_rows)
                       for category in ("A", "B", "C", "У")}
                for kind in ("revenue", "profit")
            },
        })
        product_rows = [row for row in result_rows if not row["is_unallocated"]]
        unallocated_rows = [row for row in result_rows if row["is_unallocated"]]
        summary.update({
            "product_profit_kopecks": sum(
                int(row["total"].get("profit_kopecks") or 0) for row in product_rows
            ),
            "unallocated_profit_kopecks": sum(
                int(row["total"].get("profit_kopecks") or 0) for row in unallocated_rows
            ),
            "unallocated_expense_kopecks": sum(
                int(row["total"].get("expense_kopecks") or 0) for row in unallocated_rows
            ),
        })
        for marketplace, control in controls.items():
            actual_revenue = sum(int((row.get(marketplace) or {}).get("revenue_kopecks") or 0) for row in result_rows)
            actual_profit = sum(int((row.get(marketplace) or {}).get("profit_kopecks") or 0) for row in result_rows)
            actual_advertising = sum(int((row.get(marketplace) or {}).get("advertising_kopecks") or 0) for row in result_rows)
            actual_logistics = sum(int((row.get(marketplace) or {}).get("logistics_kopecks") or 0) for row in result_rows)
            if control.get("available"):
                control["revenue_actual_kopecks"] = actual_revenue
                control["revenue_delta_kopecks"] = actual_revenue - int(control.get("revenue_kopecks") or 0)
                control["profit_actual_kopecks"] = actual_profit
                control["profit_delta_kopecks"] = actual_profit - int(control.get("profit_kopecks") or 0)
            pnl_view = pnl["marketplaces"][marketplace]
            if pnl_view.get("available"):
                pnl_advertising = sum(
                    _kopecks(line.get("amount")) for line in pnl_view.get("expense_lines", [])
                    if line.get("category") == "advertising"
                )
                pnl_logistics = sum(
                    _kopecks(line.get("amount")) for line in pnl_view.get("expense_lines", [])
                    if line.get("category") in {"logistics", "returns"}
                )
                expected = {
                    "revenue": _kopecks(pnl_view.get("revenue")),
                    "profit": _kopecks(pnl_view.get("profit")),
                    "advertising": pnl_advertising,
                    "logistics": pnl_logistics,
                }
                actual = {
                    "revenue": actual_revenue,
                    "profit": actual_profit,
                    "advertising": actual_advertising,
                    "logistics": actual_logistics,
                }
                control["pnl_reconciliation"] = {
                    key: {
                        "expected_kopecks": expected[key],
                        "actual_kopecks": actual[key],
                        "delta_kopecks": actual[key] - expected[key],
                    }
                    for key in expected
                }
                # Product allocation rounds at daily/SKU boundaries. A two-
                # kopeck tolerance prevents misleading "0 ₽" mismatch warnings
                # without hiding a material accounting difference.
                control["pnl_reconciled"] = all(
                    abs(actual[key] - expected[key]) <= 2 for key in expected
                )
        pnl_profit_kopecks = sum(
            _kopecks(view.get("profit"))
            for view in pnl["marketplaces"].values()
            if view.get("available")
        )
        summary["pnl_profit_kopecks"] = pnl_profit_kopecks
        summary["profit_delta_kopecks"] = summary["profit_kopecks"] - pnl_profit_kopecks
        summary["profit_reconciled"] = abs(summary["profit_delta_kopecks"]) <= 2
        return {
            "period": {"from": begin.isoformat(), "to": finish.isoformat()},
            # Unallocated ledger operations participate in the headline totals
            # and reconciliation with P&L, but they are not a product.  Do not
            # expose them as a pseudo-SKU or distort any real SKU profitability.
            "rows": product_rows,
            "summary": summary, "controls": controls,
            "methodology": {
                "source": "fact_product_economics_daily + fact_product_economics_controls",
                "abc": "A=first 80%, B=next 15%, C=last 5%; ties stay together",
                "profit": "headline = sum of SKU profit + unallocated financial result; P&L is the reconciliation control",
                "logistics": "financial logistics and return logistics stay on source SKU; unlinked operations affect headline only",
            },
        }
