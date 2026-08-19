from __future__ import annotations

import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import (
    WB_TG_BOT_TOKEN, WB_TG_CHAT_ID, WB_TG_LOW_STOCK_THRESHOLD, WB_TG_MORNING_TIME,
    WB_TG_OPERATIONAL_INTERVAL_SECONDS, WB_TG_POLL_SECONDS, WB_TG_REQUEST_TIMEOUT_SECONDS,
    WB_TG_TIMEZONE,
)
from wb.sync_logging import configure_wb_logging, install_context_filter
from telegram_bot.client import TelegramClient
from telegram_bot.dispatcher import TelegramReportDispatcher
from telegram_bot.reports import TelegramReportService
from telegram_bot.scheduler import TelegramReportScheduler


def build_dispatcher() -> TelegramReportDispatcher:
    client = TelegramClient(WB_TG_BOT_TOKEN or "", WB_TG_CHAT_ID or "", timeout=WB_TG_REQUEST_TIMEOUT_SECONDS)
    reports = TelegramReportService(timezone_name=WB_TG_TIMEZONE, low_stock_threshold=WB_TG_LOW_STOCK_THRESHOLD)
    return TelegramReportDispatcher(client, reports)


def main() -> None:
    parser = argparse.ArgumentParser(description="WB Telegram group reports")
    parser.add_argument("--once", choices=("morning", "operational"), help="send one report and exit")
    parser.add_argument("--force", action="store_true", help="resend even if this report key was delivered")
    args = parser.parse_args()
    configure_wb_logging(); install_context_filter()
    dispatcher = build_dispatcher()
    if args.once:
        now = datetime.now(ZoneInfo(WB_TG_TIMEZONE))
        key = f"manual:{args.once}:{now.strftime('%Y%m%d%H%M')}"
        print(dispatcher.send(args.once, key, now=now, force=args.force))
        return
    TelegramReportScheduler(
        dispatcher, timezone_name=WB_TG_TIMEZONE, morning_time=WB_TG_MORNING_TIME,
        operational_interval_seconds=WB_TG_OPERATIONAL_INTERVAL_SECONDS, poll_seconds=WB_TG_POLL_SECONDS,
    ).run_forever()


if __name__ == "__main__":
    main()
