from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func

from app.db import SessionLocal
from app.models import (
    WBFinancialSalesReport,
    WBOperationalOrder,
    WBOperationalSale,
    WBOrderFeedOrder,
    WBOrderFeedSyncRun,
    WBProduct,
)
from wb.sales import SalesOperationsAPI

MOSCOW = ZoneInfo("Europe/Moscow")


def _dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value or value.startswith("0001-01-01"):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or MOSCOW)
    except ValueError:
        return None


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal(0)


def operation_type(sale_id: str) -> str:
    prefix = sale_id[:1].upper()
    return "sale" if prefix == "S" else "return" if prefix == "R" else "unknown"


def net_sales_amount(sales: list[Decimal], returns: list[Decimal]) -> tuple[Decimal, Decimal, Decimal]:
    sale_amount = sum(sales, Decimal(0))
    return_signed_amount = sum((-abs(value) for value in returns), Decimal(0))
    return sale_amount, abs(return_signed_amount), sale_amount + return_signed_amount


class SalesService:
    """Persists operational orders/sales and builds non-overlapping reports."""

    def __init__(self, api: SalesOperationsAPI | None = None) -> None:
        self.api = api or SalesOperationsAPI()

    def sync_all(self, overlap_days: int = 2) -> dict[str, int]:
        earliest = date.today() - timedelta(days=89)
        with SessionLocal() as session:
            last_order = session.query(func.max(WBOperationalOrder.last_change_date)).scalar()
            last_sale = session.query(func.max(WBOperationalSale.last_change_date)).scalar()
        order_from = max(earliest, last_order.date() - timedelta(days=overlap_days)) if last_order else earliest
        sale_from = max(earliest, last_sale.date() - timedelta(days=overlap_days)) if last_sale else earliest
        return {
            "orders_received": self.sync_orders(order_from),
            "sales_received": self.sync_sales(sale_from),
        }

    def sync_orders(self, date_from: date | datetime | str) -> int:
        items = self.api.orders(date_from)
        with SessionLocal() as session:
            existing = {row.srid: row for row in session.query(WBOperationalOrder).all()}
            products = {int(row[0]): int(row[1]) for row in session.query(WBProduct.nm_id, WBProduct.id).all()}
            for item in items:
                srid = str(item.get("srid") or "")
                order_date = _dt(item.get("date")); last_change = _dt(item.get("lastChangeDate"))
                if not srid or order_date is None or last_change is None:
                    continue
                row = existing.get(srid)
                if row is None:
                    row = WBOperationalOrder(srid=srid, order_date=order_date, last_change_date=last_change, raw_data=item)
                    session.add(row); existing[srid] = row
                nm_id = int(item.get("nmId") or 0)
                row.product_id = products.get(nm_id); row.nm_id = nm_id or None
                row.order_date = order_date; row.last_change_date = last_change
                row.cancel_date = _dt(item.get("cancelDate")); row.is_cancel = bool(item.get("isCancel"))
                row.warehouse_name = item.get("warehouseName"); row.warehouse_type = item.get("warehouseType")
                row.supplier_article = item.get("supplierArticle"); row.barcode = item.get("barcode")
                row.finished_price = _money(item.get("finishedPrice")); row.price_with_discount = _money(item.get("priceWithDisc"))
                row.raw_data = item; row.fetched_at = datetime.now(MOSCOW).replace(tzinfo=None)
            session.commit()
        return len(items)

    def sync_sales(self, date_from: date | datetime | str) -> int:
        items = self.api.sales(date_from)
        with SessionLocal() as session:
            existing = {row.sale_id: row for row in session.query(WBOperationalSale).all()}
            products = {int(row[0]): int(row[1]) for row in session.query(WBProduct.nm_id, WBProduct.id).all()}
            for item in items:
                sale_id = str(item.get("saleID") or ""); srid = str(item.get("srid") or "")
                event_date = _dt(item.get("date")); last_change = _dt(item.get("lastChangeDate"))
                if not sale_id or not srid or event_date is None or last_change is None:
                    continue
                row = existing.get(sale_id)
                if row is None:
                    row = WBOperationalSale(sale_id=sale_id, srid=srid, operation_type="unknown", event_date=event_date, last_change_date=last_change, raw_data=item)
                    session.add(row); existing[sale_id] = row
                nm_id = int(item.get("nmId") or 0)
                row.operation_type = operation_type(sale_id)
                row.product_id = products.get(nm_id); row.nm_id = nm_id or None
                row.event_date = event_date; row.last_change_date = last_change
                row.warehouse_name = item.get("warehouseName"); row.warehouse_type = item.get("warehouseType")
                row.supplier_article = item.get("supplierArticle"); row.barcode = item.get("barcode")
                row.finished_price = _money(item.get("finishedPrice")); row.price_with_discount = _money(item.get("priceWithDisc")); row.for_pay = _money(item.get("forPay"))
                row.raw_data = item; row.fetched_at = datetime.now(MOSCOW).replace(tzinfo=None)
            session.commit()
        return len(items)

    @staticmethod
    def summary(date_from: date, date_to: date) -> dict[str, Any]:
        if date_from > date_to:
            raise ValueError("date_from must not be later than date_to")
        start = datetime.combine(date_from, time.min, tzinfo=MOSCOW)
        end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=MOSCOW)
        with SessionLocal() as session:
            latest_feed_run = session.query(WBOrderFeedSyncRun).filter_by(status="completed").order_by(
                WBOrderFeedSyncRun.finished_at.desc()
            ).first()
            if latest_feed_run is not None:
                orders = session.query(WBOrderFeedOrder).filter(
                    WBOrderFeedOrder.order_date >= start,
                    WBOrderFeedOrder.order_date < end,
                ).all()
                cancellations = session.query(func.count(WBOrderFeedOrder.id)).filter(
                    WBOrderFeedOrder.status == "cancel",
                    WBOrderFeedOrder.status_updated_at >= start,
                    WBOrderFeedOrder.status_updated_at < end,
                ).scalar() or 0
                last_order_update = latest_feed_run.finished_at
                order_source = "order_feed"
            else:
                orders = session.query(WBOperationalOrder).filter(
                    WBOperationalOrder.order_date >= start,
                    WBOperationalOrder.order_date < end,
                ).all()
                cancellations = session.query(func.count(WBOperationalOrder.id)).filter(
                    WBOperationalOrder.cancel_date >= start,
                    WBOperationalOrder.cancel_date < end,
                ).scalar() or 0
                last_order_update = session.query(func.max(WBOperationalOrder.last_change_date)).scalar()
                order_source = "statistics_fallback"
            operations = session.query(WBOperationalSale).filter(WBOperationalSale.event_date >= start, WBOperationalSale.event_date < end).all()
            last_sale_update = session.query(func.max(WBOperationalSale.last_change_date)).scalar()
            accounting_through = session.query(func.max(WBFinancialSalesReport.date_to)).filter(WBFinancialSalesReport.details_synced_at.isnot(None)).scalar()
            operation_srids = {row.srid for row in operations}
            order_model = WBOrderFeedOrder if latest_feed_run is not None else WBOperationalOrder
            matched_srids = {
                row[0]
                for row in session.query(order_model.srid).filter(order_model.srid.in_(operation_srids)).all()
            } if operation_srids else set()
        sales = [row for row in operations if row.operation_type == "sale"]
        returns = [row for row in operations if row.operation_type == "return"]
        unknown = [row for row in operations if row.operation_type == "unknown"]
        sale_amount, return_amount, net_amount = net_sales_amount(
            [row.finished_price for row in sales], [row.finished_price for row in returns]
        )

        def fulfillment(rows: list[Any]) -> dict[str, int]:
            result = {"fbs": 0, "fbo": 0, "unknown": 0}
            for row in rows:
                if isinstance(row, WBOrderFeedOrder):
                    key = "fbs" if row.is_mp else "fbo"
                else:
                    warehouse_type = str(row.warehouse_type or "").casefold()
                    key = "fbs" if "продав" in warehouse_type else "fbo" if warehouse_type else "unknown"
                result[key] += 1
            return result

        def order_amount(row: Any) -> Decimal:
            return row.seller_price if isinstance(row, WBOrderFeedOrder) else row.price_with_discount

        def order_cancelled(row: Any) -> bool:
            return row.status == "cancel" if isinstance(row, WBOrderFeedOrder) else row.is_cancel

        return {
            "period": {"from": date_from.isoformat(), "to": date_to.isoformat(), "timezone": "Europe/Moscow"},
            "status": "operational_preliminary",
            "orders_placed": len(orders),
            "orders_amount": str(sum((order_amount(row) for row in orders), Decimal(0))),
            "orders_from_period_now_cancelled": sum(order_cancelled(row) for row in orders),
            "cancellations_registered": int(cancellations),
            "buyouts": len(sales),
            "buyouts_amount": str(sale_amount),
            "returns": len(returns),
            "returns_amount": str(return_amount),
            "net_buyouts": len(sales) - len(returns),
            "net_buyouts_amount": str(net_amount),
            "unknown_operations": len(unknown),
            "operations_without_order_row": sum(row.srid not in matched_srids for row in operations),
            "fulfillment": {"orders": fulfillment(orders), "buyouts": fulfillment(sales), "returns": fulfillment(returns)},
            "orders_last_updated_at": last_order_update.isoformat() if last_order_update else None,
            "orders_source": order_source,
            "sales_last_updated_at": last_sale_update.isoformat() if last_sale_update else None,
            "accounting_report_through": accounting_through.date().isoformat() if accounting_through else None,
            "accounting_covers_period": bool(accounting_through and accounting_through.date() >= date_to),
        }
