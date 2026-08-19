import argparse
import logging
import signal
from threading import Thread
from typing import Any

from app.config import (
    WB_TG_BOT_TOKEN,
    WB_TG_CHAT_ID,
    WB_TG_MORNING_TIME,
    WB_TG_OPERATIONAL_INTERVAL_SECONDS,
    WB_TG_POLL_SECONDS,
    WB_TG_TIMEZONE,
)
from wb.scheduler import WBPeriodicSync
from wb.sync_logging import configure_wb_logging, install_context_filter
from telegram_bot.__main__ import build_dispatcher
from telegram_bot.scheduler import TelegramReportScheduler

logger = logging.getLogger(__name__)


def build_report_scheduler() -> TelegramReportScheduler | None:
    """Build Telegram reporting when both required credentials are configured."""
    if not WB_TG_BOT_TOKEN or not WB_TG_CHAT_ID:
        logger.warning(
            "Telegram reports are disabled: WB_TG_BOT_TOKEN and WB_TG_CHAT_ID must be set"
        )
        return None
    return TelegramReportScheduler(
        build_dispatcher(),
        timezone_name=WB_TG_TIMEZONE,
        morning_time=WB_TG_MORNING_TIME,
        operational_interval_seconds=WB_TG_OPERATIONAL_INTERVAL_SECONDS,
        poll_seconds=WB_TG_POLL_SECONDS,
    )


def install_shutdown_handlers(
    sync_scheduler: WBPeriodicSync,
    report_scheduler: TelegramReportScheduler | None,
) -> None:
    def handle_signal(signum: int, frame: Any) -> None:
        logger.info("Received signal %s, stopping schedulers", signum)
        sync_scheduler.stop()
        if report_scheduler:
            report_scheduler.stop()

    signal.signal(signal.SIGINT, handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_signal)


def main() -> None:
    parser = argparse.ArgumentParser(description="Wildberries synchronization and Telegram reports")
    parser.add_argument("--once", action="store_true", help="run one complete cycle and exit")
    parser.add_argument("--sync-only", action="store_true", help="disable Telegram report scheduling")
    args = parser.parse_args()
    configure_wb_logging()
    install_context_filter()
    sync_scheduler = WBPeriodicSync()
    if args.once:
        sync_scheduler.run_cycle()
        return

    report_scheduler = None if args.sync_only else build_report_scheduler()
    install_shutdown_handlers(sync_scheduler, report_scheduler)
    report_thread = None
    if report_scheduler:
        report_thread = Thread(
            target=report_scheduler.run_forever,
            name="telegram-report-scheduler",
            daemon=True,
        )
        report_thread.start()
        logger.info("Telegram report scheduler started alongside WB synchronization")

    try:
        sync_scheduler.run_forever()
    finally:
        sync_scheduler.stop()
        if report_scheduler:
            report_scheduler.stop()
        if report_thread:
            report_thread.join(timeout=max(1, WB_TG_POLL_SECONDS + 1))


if __name__ == "__main__":
    main()
