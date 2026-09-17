from __future__ import annotations

import argparse
import json
import logging
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.config import (
    WB_LOG_DIR,
    WB_LOG_LEVEL,
    WB_SALES_FUNNEL_LOOKBACK_DAYS,
    WB_TG_TIMEZONE,
)
from app.db import SessionLocal
from app.models import (
    WBProduct,
    WBSalesFunnelAccountDaily,
    WBSalesFunnelDaily,
    WBSalesFunnelPeriodProduct,
    WBSalesFunnelSyncRun,
)
from wb.exceptions import WBParseError
from wb.sales_funnel import SalesFunnelAPI
from wb.sync_logging import configure_wb_logging, install_context_filter


logger = logging.getLogger(__name__)
_SYNC_LOCK_ID = 2_026_091_701


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


class SalesFunnelSyncService:
    def __init__(
        self,
        *,
        api: SalesFunnelAPI | None = None,
        session_factory: Callable[..., Any] = SessionLocal,
        timezone_name: str = WB_TG_TIMEZONE,
        lookback_days: int = WB_SALES_FUNNEL_LOOKBACK_DAYS,
    ) -> None:
        if not 1 <= lookback_days <= 7:
            raise ValueError("WB_SALES_FUNNEL_LOOKBACK_DAYS must be between 1 and 7")
        self.api = api or SalesFunnelAPI()
        self.session_factory = session_factory
        self.timezone = ZoneInfo(timezone_name)
        self.lookback_days = lookback_days

    @staticmethod
    def _windows(period_from: date, period_to: date) -> list[tuple[date, date]]:
        windows: list[tuple[date, date]] = []
        cursor = period_from
        while cursor <= period_to:
            end = min(cursor + timedelta(days=6), period_to)
            windows.append((cursor, end))
            cursor = end + timedelta(days=1)
        return windows

    @staticmethod
    def _try_lock(connection: Any) -> bool:
        if connection.dialect.name != "postgresql":
            return True
        return bool(connection.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": _SYNC_LOCK_ID}
        ).scalar())

    @staticmethod
    def _unlock(connection: Any) -> None:
        if connection.dialect.name == "postgresql":
            connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": _SYNC_LOCK_ID}
            )

    def sync(
        self,
        now: datetime | None = None,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, Any]:
        current = now or datetime.now(self.timezone)
        current = current.replace(tzinfo=self.timezone) if current.tzinfo is None else current.astimezone(self.timezone)
        if (date_from is None) != (date_to is None):
            raise ValueError("date_from and date_to must be provided together")
        period_to = date_to or current.date()
        period_from = date_from or (period_to - timedelta(days=self.lookback_days - 1))
        if period_from > period_to:
            raise ValueError("date_from must not be later than date_to")
        if (period_to - period_from).days > 6:
            raise ValueError("WB daily Sales Funnel API supports only the last seven days")
        if period_from < current.date() - timedelta(days=6):
            raise ValueError("WB daily Sales Funnel API cannot return dates older than the last week")
        windows = self._windows(period_from, period_to)
        run_id = uuid.uuid4().hex
        received = upserted = account_rows = 0
        with self.session_factory() as probe_session:
            engine = probe_session.get_bind()
        # Keep a dedicated connection open for the full run. PostgreSQL advisory
        # locks are connection-scoped and must not be returned to the pool early.
        with engine.connect() as lock_connection:
            if not self._try_lock(lock_connection):
                return {"status": "skipped", "reason": "already_running"}
            try:
                with self.session_factory() as session:
                    nm_ids = [int(value) for (value,) in session.query(WBProduct.nm_id).filter(
                        WBProduct.nm_id.isnot(None)
                    ).distinct().all()]
                    session.add(WBSalesFunnelSyncRun(
                        id=run_id, started_at=current, status="running",
                        period_from=period_from, period_to=period_to,
                    ))
                    session.commit()
                for index, (window_from, window_to) in enumerate(windows):
                    payload = self.api.history(window_from, window_to, nm_ids)
                    window_received, window_upserted = self._persist(payload, current)
                    received += window_received
                    upserted += window_upserted
                    self.api.pause()
                    account_payload = self.api.grouped_history(window_from, window_to)
                    account_rows += self._persist_account(
                        account_payload, current, window_from, window_to
                    )
                    if index + 1 < len(windows):
                        self.api.pause()
                self._finish(run_id, "completed", received, upserted, None, datetime.now(self.timezone))
                return {
                    "run_id": run_id, "status": "completed", "period_from": period_from,
                    "period_to": period_to, "windows": len(windows),
                    "rows_received": received, "rows_upserted": upserted,
                    "account_rows_upserted": account_rows,
                }
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                self._finish(run_id, "failed", received, upserted, error, datetime.now(self.timezone))
                logger.exception("WB Sales Funnel synchronization failed")
                raise
            finally:
                self._unlock(lock_connection)

    def sync_period(
        self,
        date_from: date,
        date_to: date,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Store exact cabinet totals for a requested period using the 365-day endpoint."""
        current = now or datetime.now(self.timezone)
        current = current.replace(tzinfo=self.timezone) if current.tzinfo is None else current.astimezone(self.timezone)
        if date_from > date_to:
            raise ValueError("date_from must not be later than date_to")
        if (date_to - date_from).days > 364:
            raise ValueError("WB period Sales Funnel API supports no more than 365 days")
        if date_from < current.date() - timedelta(days=364):
            raise ValueError("WB period Sales Funnel API cannot return dates older than 365 days")
        run_id = uuid.uuid4().hex
        received = 0
        with self.session_factory() as probe_session:
            engine = probe_session.get_bind()
        with engine.connect() as lock_connection:
            if not self._try_lock(lock_connection):
                return {"status": "skipped", "reason": "already_running"}
            try:
                with self.session_factory() as session:
                    session.add(WBSalesFunnelSyncRun(
                        id=run_id, started_at=current, status="running",
                        period_from=date_from, period_to=date_to,
                    ))
                    session.commit()
                payload, currency = self.api.products(date_from, date_to)
                received = len(payload)
                saved = self._persist_period(payload, currency, date_from, date_to, current)
                self._finish(run_id, "completed", received, saved, None, datetime.now(self.timezone))
                return {
                    "run_id": run_id,
                    "status": "completed",
                    "mode": "period",
                    "period_from": date_from,
                    "period_to": date_to,
                    "rows_received": received,
                    "rows_upserted": saved,
                }
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                self._finish(run_id, "failed", received, 0, error, datetime.now(self.timezone))
                logger.exception("WB Sales Funnel period synchronization failed")
                raise
            finally:
                self._unlock(lock_connection)

    def sync_month_prefixes(self, now: datetime | None = None) -> dict[str, Any]:
        """Refresh every month-to-date period so historical dashboard filters stay exact."""
        current = now or datetime.now(self.timezone)
        current = current.replace(tzinfo=self.timezone) if current.tzinfo is None else current.astimezone(self.timezone)
        period_from = current.date().replace(day=1)
        period_to = period_from
        results: list[dict[str, Any]] = []
        while period_to <= current.date():
            results.append(self.sync_period(period_from, period_to, current))
            period_to += timedelta(days=1)
            if period_to <= current.date():
                self.api.pause()
        completed = sum(result.get("status") == "completed" for result in results)
        skipped = sum(result.get("status") == "skipped" for result in results)
        return {
            "status": "completed",
            "mode": "month_prefixes",
            "period_from": period_from,
            "period_to": current.date(),
            "snapshots_completed": completed,
            "snapshots_skipped": skipped,
            "snapshots_total": len(results),
            "rows_upserted": sum(int(result.get("rows_upserted") or 0) for result in results),
        }

    def _persist(self, payload: list[dict[str, Any]], fetched_at: datetime) -> tuple[int, int]:
        parsed: list[tuple[date, int, dict[str, Any], dict[str, Any], Any, str | None]] = []
        for product_row in payload:
            product = product_row.get("product")
            history = product_row.get("history")
            if not isinstance(product, dict) or not isinstance(history, list):
                raise WBParseError("WB Sales Funnel item has no product or history")
            nm_id = int(product.get("nmId") or 0)
            if not nm_id:
                raise WBParseError("WB Sales Funnel item has no nmId")
            currency = product_row.get("currency")
            currency_code = currency.get("name") if isinstance(currency, dict) else currency
            for item in history:
                if not isinstance(item, dict) or not item.get("date"):
                    raise WBParseError(f"WB Sales Funnel history for {nm_id} has no date")
                parsed.append((date.fromisoformat(str(item["date"])), nm_id, product, item,
                               product_row.get("currency"), currency_code))
        if not parsed:
            return 0, 0
        with self.session_factory() as session:
            keys = [(day, nm_id) for day, nm_id, *_ in parsed]
            dates = {key[0] for key in keys}
            ids = {key[1] for key in keys}
            existing = {(row.stat_date, row.nm_id): row for row in session.query(WBSalesFunnelDaily).filter(
                WBSalesFunnelDaily.stat_date.in_(dates), WBSalesFunnelDaily.nm_id.in_(ids)
            ).all()}
            for day, nm_id, product, item, raw_currency, currency in parsed:
                row = existing.get((day, nm_id))
                if row is None:
                    row = WBSalesFunnelDaily(stat_date=day, nm_id=nm_id)
                    session.add(row)
                    existing[(day, nm_id)] = row
                row.vendor_code = product.get("vendorCode")
                row.title = product.get("title")
                row.currency = str(currency) if currency else None
                row.open_count = int(item.get("openCount") or 0)
                row.cart_count = int(item.get("cartCount") or 0)
                row.order_count = int(item.get("orderCount") or 0)
                row.order_sum = _money(item.get("orderSum"))
                row.buyout_count = int(item.get("buyoutCount") or 0)
                row.buyout_sum = _money(item.get("buyoutSum"))
                # Daily history has no cancellation fields. Do not mistake pending orders
                # (orders minus purchases) for cancellations.
                row.cancel_count = 0
                row.cancel_sum = Decimal(0)
                row.raw_data = {"product": product, "metrics": item, "currency": raw_currency}
                row.fetched_at = fetched_at
            session.commit()
        return len(parsed), len(parsed)

    def _persist_account(
        self,
        payload: list[dict[str, Any]],
        fetched_at: datetime,
        period_from: date,
        period_to: date,
    ) -> int:
        totals: dict[date, dict[str, Any]] = {}
        cursor = period_from
        while cursor <= period_to:
            totals[cursor] = {
                "currency": None,
                "open_count": 0, "cart_count": 0,
                "order_count": 0, "order_sum": Decimal(0),
                "buyout_count": 0, "buyout_sum": Decimal(0), "groups": [],
            }
            cursor += timedelta(days=1)
        for group in payload:
            history = group.get("history")
            if not isinstance(history, list):
                raise WBParseError("WB grouped Sales Funnel item has no history")
            currency = group.get("currency")
            currency_code = currency.get("name") if isinstance(currency, dict) else currency
            for item in history:
                if not isinstance(item, dict) or not item.get("date"):
                    raise WBParseError("WB grouped Sales Funnel history has no date")
                day = date.fromisoformat(str(item["date"])[:10])
                if day not in totals:
                    raise WBParseError(
                        f"WB grouped Sales Funnel returned {day} outside "
                        f"requested period {period_from}..{period_to}"
                    )
                row = totals[day]
                if currency_code:
                    row["currency"] = str(currency_code)
                row["open_count"] += int(item.get("openCount") or 0)
                row["cart_count"] += int(item.get("cartCount") or 0)
                row["order_count"] += int(item.get("orderCount") or 0)
                row["order_sum"] += _money(item.get("orderSum"))
                row["buyout_count"] += int(item.get("buyoutCount") or 0)
                row["buyout_sum"] += _money(item.get("buyoutSum"))
                row["groups"].append({"group": group.get("group"), "metrics": item})
        with self.session_factory() as session:
            for day, item in totals.items():
                row = session.get(WBSalesFunnelAccountDaily, day)
                if row is None:
                    row = WBSalesFunnelAccountDaily(stat_date=day)
                    session.add(row)
                for field in ("currency", "open_count", "cart_count", "order_count",
                              "order_sum", "buyout_count", "buyout_sum"):
                    setattr(row, field, item[field])
                row.raw_data = {"groups": item["groups"]}
                row.fetched_at = fetched_at
            session.commit()
        return len(totals)

    def _persist_period(
        self,
        payload: list[dict[str, Any]],
        raw_currency: Any,
        period_from: date,
        period_to: date,
        fetched_at: datetime,
    ) -> int:
        currency = raw_currency.get("name") if isinstance(raw_currency, dict) else raw_currency
        parsed: list[WBSalesFunnelPeriodProduct] = []
        for item in payload:
            product = item.get("product")
            statistic = item.get("statistic")
            selected = statistic.get("selected") if isinstance(statistic, dict) else None
            if not isinstance(product, dict) or not isinstance(selected, dict):
                raise WBParseError("WB Sales Funnel period item has no product or selected statistic")
            nm_id = int(product.get("nmId") or 0)
            if not nm_id:
                raise WBParseError("WB Sales Funnel period item has no nmId")
            parsed.append(WBSalesFunnelPeriodProduct(
                period_from=period_from,
                period_to=period_to,
                nm_id=nm_id,
                vendor_code=product.get("vendorCode"),
                title=product.get("title"),
                currency=str(currency) if currency else None,
                open_count=int(selected.get("openCount") or 0),
                cart_count=int(selected.get("cartCount") or 0),
                order_count=int(selected.get("orderCount") or 0),
                order_sum=_money(selected.get("orderSum")),
                buyout_count=int(selected.get("buyoutCount") or 0),
                buyout_sum=_money(selected.get("buyoutSum")),
                cancel_count=int(selected.get("cancelCount") or 0),
                cancel_sum=_money(selected.get("cancelSum")),
                raw_data={"product": product, "statistic": statistic, "currency": raw_currency},
                fetched_at=fetched_at,
            ))
        with self.session_factory() as session:
            session.query(WBSalesFunnelPeriodProduct).filter_by(
                period_from=period_from, period_to=period_to
            ).delete(synchronize_session=False)
            session.add_all(parsed)
            session.commit()
        return len(parsed)

    def _finish(self, run_id: str, status: str, received: int, upserted: int,
                error: str | None, finished_at: datetime) -> None:
        with self.session_factory() as session:
            run = session.get(WBSalesFunnelSyncRun, run_id)
            if run is not None:
                run.finished_at = finished_at
                run.status = status
                run.rows_received = received
                run.rows_upserted = upserted
                run.error = error
                session.commit()


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synchronize WB Sales Funnel analytics")
    parser.add_argument("--from", dest="date_from", type=date.fromisoformat)
    parser.add_argument("--to", dest="date_to", type=date.fromisoformat)
    parser.add_argument(
        "--reconcile", action="store_true",
        help="refresh every month-to-date aggregate snapshot for the current month",
    )
    args = parser.parse_args()
    if (args.date_from is None) != (args.date_to is None):
        parser.error("--from and --to must be provided together")
    if args.reconcile and args.date_from is not None:
        parser.error("--reconcile cannot be combined with --from/--to")
    return args


def main() -> None:
    configure_wb_logging(log_dir=WB_LOG_DIR, file_prefix="wb_sales_funnel")
    install_context_filter()
    logging.basicConfig(level=getattr(logging, WB_LOG_LEVEL, logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = _arguments()
    service = SalesFunnelSyncService()
    date_from = args.date_from
    date_to = args.date_to
    print(json.dumps(
        service.sync_month_prefixes()
        if args.reconcile
        else service.sync_period(date_from, date_to)
        if date_from is not None and date_to is not None
        else service.sync(),
        ensure_ascii=False,
        default=str,
    ))


if __name__ == "__main__":
    main()
