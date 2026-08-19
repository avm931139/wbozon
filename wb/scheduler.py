from __future__ import annotations

import logging
import signal
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from threading import Event
from typing import Any, Callable

from sqlalchemy import func

from app.config import (
    WB_SYNC_FBS_ORDER_OVERLAP_DAYS,
    WB_SYNC_FINANCE_OVERLAP_DAYS,
    WB_SYNC_HISTORY_START,
    WB_SYNC_INTERVAL_SECONDS,
    WB_SYNC_PROMOTION_LOOKBACK_DAYS,
    WB_SYNC_RUN_ON_START,
)
from app.db import SessionLocal
from app.models import (
    WBFBSOrder,
    WBFinancialAcquiringRow,
    WBFinancialSalesRow,
)
from wb.services import WBSyncService
from wb.sync_logging import finish_sync_run, report_exception, start_sync_run, summarize_result, sync_context

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncSettings:
    interval_seconds: int = WB_SYNC_INTERVAL_SECONDS
    run_on_start: bool = WB_SYNC_RUN_ON_START
    history_start: date = date.fromisoformat(WB_SYNC_HISTORY_START)
    promotion_lookback_days: int = WB_SYNC_PROMOTION_LOOKBACK_DAYS
    fbs_order_overlap_days: int = WB_SYNC_FBS_ORDER_OVERLAP_DAYS
    finance_overlap_days: int = WB_SYNC_FINANCE_OVERLAP_DAYS

    def __post_init__(self) -> None:
        if self.interval_seconds < 1:
            raise ValueError("interval_seconds must be positive")
        if self.promotion_lookback_days < 1:
            raise ValueError("promotion_lookback_days must be positive")
        if self.fbs_order_overlap_days < 0:
            raise ValueError("fbs_order_overlap_days must not be negative")
        if self.finance_overlap_days < 0:
            raise ValueError("finance_overlap_days must not be negative")


class WBPeriodicSync:
    """Runs a complete read-only WB synchronization cycle in dependency order."""

    def __init__(
        self,
        service: WBSyncService | None = None,
        settings: SyncSettings | None = None,
        stop_event: Event | None = None,
        session_factory: Callable[..., Any] = SessionLocal,
    ) -> None:
        self.service = service or WBSyncService()
        self.settings = settings or SyncSettings()
        self.stop_event = stop_event or Event()
        self.session_factory = session_factory
        self._running = False

    def stop(self) -> None:
        self.stop_event.set()

    def run_cycle(self) -> dict[str, dict[str, Any]]:
        """Run all sections once; a failed section does not hide later results."""
        if self._running:
            raise RuntimeError("WB synchronization cycle is already running")
        self._running = True
        cycle_id = uuid.uuid4().hex
        started = time.monotonic()
        results: dict[str, dict[str, Any]] = {}
        start_sync_run(cycle_id)
        logger.info("WB synchronization cycle %s started", cycle_id)
        try:
            for name, callback in self._tasks():
                if self.stop_event.is_set():
                    break
                task_started = time.monotonic()
                with sync_context(cycle_id, name):
                    logger.info("WB sync task started")
                    try:
                        value = callback()
                        summary = summarize_result(value)
                        results[name] = {
                            "status": "ok",
                            "result": summary,
                            "duration_seconds": round(time.monotonic() - task_started, 3),
                        }
                        logger.info("WB sync task completed: %s", summary)
                    except Exception as exc:  # keep independent sections running
                        event = report_exception(exc, phase="task", details={"task": name})
                        results[name] = {
                            "status": "error",
                            "error": f"{type(exc).__name__}: {exc}",
                            "error_file": event["file"],
                            "error_line": event["line"],
                            "duration_seconds": round(time.monotonic() - task_started, 3),
                        }
                        logger.exception("WB sync task failed")
        finally:
            self._running = False
            errors = sum(item["status"] == "error" for item in results.values())
            duration = time.monotonic() - started
            finish_sync_run(cycle_id, results, duration)
            logger.info(
                "WB synchronization cycle %s finished in %.3f seconds: tasks=%s errors=%s",
                cycle_id,
                duration,
                len(results),
                errors,
            )
        return results

    def run_forever(self, max_cycles: int | None = None) -> None:
        """Run cycles sequentially until stop(); mainly bounded by max_cycles in tests."""
        cycles = 0
        if not self.settings.run_on_start and self.stop_event.wait(self.settings.interval_seconds):
            return
        while not self.stop_event.is_set() and (max_cycles is None or cycles < max_cycles):
            self.run_cycle()
            cycles += 1
            if max_cycles is not None and cycles >= max_cycles:
                break
            if self.stop_event.wait(self.settings.interval_seconds):
                break

    def _tasks(self) -> list[tuple[str, Callable[[], Any]]]:
        today = date.today()
        promotion_start = today - timedelta(days=self.settings.promotion_lookback_days - 1)
        return [
            ("categories", self.service.sync_categories),
            ("products", self.service.sync_products),
            ("fbs_warehouses", self.service.sync_fbs_warehouses),
            ("fbs_orders", self._sync_incremental_fbs_orders),
            ("sales_operations", lambda: self.service.sync_sales_operations(overlap_days=self.settings.fbs_order_overlap_days)),
            ("fbw_supplies", self.service.sync_fbw_supplies_max_history),
            ("financial_sales_reports", lambda: self.service.sync_financial_sales_reports(date_from=self._sales_start_date(), date_to=today)),
            ("financial_sales_details", lambda: self.service.sync_financial_sales_details(date_from=self._sales_start_date(), date_to=today)),
            ("financial_acquiring_reports", lambda: self.service.sync_financial_acquiring_reports(date_from=self._acquiring_start_date(), date_to=today)),
            ("financial_acquiring_details", lambda: self.service.sync_financial_acquiring_details(date_from=self._acquiring_start_date(), date_to=today)),
            ("customer_communications", self.service.sync_customer_communications),
            ("advertising", lambda: self.service.sync_advertising(date_from=promotion_start, date_to=today)),
        ]

    def _sync_incremental_fbs_orders(self) -> int:
        with self.session_factory() as session:
            latest = session.query(func.max(WBFBSOrder.created_at_wb)).scalar()
        if latest is None:
            start = datetime.combine(self.settings.history_start, datetime_time.min, tzinfo=timezone.utc)
        else:
            start = latest if latest.tzinfo else latest.replace(tzinfo=timezone.utc)
            start -= timedelta(days=self.settings.fbs_order_overlap_days)
        return self.service.sync_fbs_orders_max_history(start=start, end=datetime.now(timezone.utc))

    def _sales_start_date(self) -> date:
        with self.session_factory() as session:
            latest = session.query(func.max(WBFinancialSalesRow.rr_date)).scalar()
        return self._overlap_date(latest, self.settings.finance_overlap_days)

    def _acquiring_start_date(self) -> date:
        with self.session_factory() as session:
            latest = session.query(func.max(WBFinancialAcquiringRow.transaction_date)).scalar()
        return self._overlap_date(latest, self.settings.finance_overlap_days)

    def _overlap_date(self, latest: datetime | None, overlap_days: int) -> date:
        return (latest.date() - timedelta(days=overlap_days)) if latest else self.settings.history_start


def install_signal_handlers(scheduler: WBPeriodicSync) -> None:
    def handle_signal(signum: int, frame: Any) -> None:
        logger.info("Received signal %s, stopping WB scheduler", signum)
        scheduler.stop()

    signal.signal(signal.SIGINT, handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_signal)
