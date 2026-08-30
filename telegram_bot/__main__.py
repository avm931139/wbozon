from __future__ import annotations

import argparse
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import (
    WB_TG_BOT_TOKEN, WB_TG_CHAT_ID, WB_TG_LOW_STOCK_THRESHOLD, WB_TG_MORNING_TIME,
    WB_TG_OPERATIONAL_INTERVAL_SECONDS, WB_TG_POLL_SECONDS, WB_TG_REQUEST_TIMEOUT_SECONDS,
    WB_TG_PROXY_URL, WB_TG_TIMEZONE,
)
from wb.sync_logging import configure_wb_logging, install_context_filter
from telegram_bot.client import TelegramClient
from telegram_bot.dispatcher import TelegramReportDispatcher
from telegram_bot.reports import TelegramReportService
from telegram_bot.scheduler import TelegramReportScheduler
from telegram_bot.stock_reports import StockExcelReportService, StockSnapshotNotFound


def build_dispatcher() -> TelegramReportDispatcher:
    client = TelegramClient(
        WB_TG_BOT_TOKEN or "",
        WB_TG_CHAT_ID or "",
        timeout=WB_TG_REQUEST_TIMEOUT_SECONDS,
        proxy_url=WB_TG_PROXY_URL,
    )
    reports = TelegramReportService(timezone_name=WB_TG_TIMEZONE, low_stock_threshold=WB_TG_LOW_STOCK_THRESHOLD)
    return TelegramReportDispatcher(client, reports)


def send_stock_files(
    dispatcher: TelegramReportDispatcher,
    snapshot_date: date,
    *,
    force: bool = False,
    reports: StockExcelReportService | None = None,
) -> list[dict]:
    reports = reports or StockExcelReportService()
    results: list[dict] = []
    errors: list[str] = []
    missing: list[str] = []
    report_factories = (
        ("wb", "Wildberries", reports.wb),
        ("ozon", "Ozon", reports.ozon),
        ("yandex_market", "Яндекс Маркет", reports.yandex_market),
    )
    for marketplace, marketplace_name, factory in report_factories:
        try:
            results.append(dispatcher.send_document(
                f"stock_excel_{marketplace}",
                f"stock_excel:{marketplace}:{snapshot_date.isoformat()}",
                lambda factory=factory: factory(snapshot_date),
                force=force,
            ))
        except StockSnapshotNotFound:
            missing.append(marketplace_name)
        except Exception as exc:
            errors.append(f"{marketplace}: {exc}")
    if missing:
        marketplace_names = ", ".join(missing)
        results.append(dispatcher.send_text_content(
            "stock_snapshot_warning",
            f"stock_warning:{snapshot_date.isoformat()}",
            lambda: (
                f"⚠️ Остатки не выгружены за {snapshot_date:%d.%m.%Y}: {marketplace_names}.\n"
                "Excel-файл не сформирован. Проверьте работу inventory_sync."
            ),
            force=force,
        ))
    if errors:
        raise RuntimeError("; ".join(errors))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="WB Telegram group reports")
    parser.add_argument("--once", choices=("morning", "operational", "stock-files"), help="send one report and exit")
    parser.add_argument("--date", type=date.fromisoformat, help="snapshot date for stock-files (YYYY-MM-DD)")
    parser.add_argument("--force", action="store_true", help="resend even if this report key was delivered")
    args = parser.parse_args()
    configure_wb_logging(); install_context_filter()
    dispatcher = build_dispatcher()
    if args.once:
        now = datetime.now(ZoneInfo(WB_TG_TIMEZONE))
        if args.once == "stock-files":
            print(send_stock_files(dispatcher, args.date or now.date(), force=args.force))
            return
        key = f"manual:{args.once}:{now.strftime('%Y%m%d%H%M')}"
        print(dispatcher.send(args.once, key, now=now, force=args.force))
        return
    TelegramReportScheduler(
        dispatcher, timezone_name=WB_TG_TIMEZONE, morning_time=WB_TG_MORNING_TIME,
        operational_interval_seconds=WB_TG_OPERATIONAL_INTERVAL_SECONDS, poll_seconds=WB_TG_POLL_SECONDS,
    ).run_forever()


if __name__ == "__main__":
    main()
