from __future__ import annotations

import hashlib
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

from sqlalchemy import func

from app.config import (
    INVENTORY_SYNC_INTERVAL_SECONDS,
    INVENTORY_TIMEZONE,
    OZON_ADS_MAX_AGE_SECONDS,
    OZON_COMMUNICATIONS_MAX_AGE_SECONDS,
    OZON_DAILY_SALES_MAX_AGE_SECONDS,
    OZON_FINANCES_MAX_AGE_SECONDS,
    OZON_ORDERS_MAX_AGE_SECONDS,
    OZON_PRODUCTS_MAX_AGE_SECONDS,
    OZON_REQUIRED_TASKS,
    OZON_SUPPLIES_MAX_AGE_SECONDS,
    WB_TG_BOT_TOKEN,
    WB_TG_CHAT_ID,
    WB_TG_MORNING_TIME,
    WB_TG_PROXY_URL,
    WB_TG_REQUEST_TIMEOUT_SECONDS,
    YANDEX_MARKET_CAMPAIGN_IDS,
)
from app.db import SessionLocal
from app.models import (
    InventorySyncRun,
    OzonSyncRun,
    OzonStockSnapshot,
    OzonWarehouseStockSnapshot,
    WBFboStockSnapshot,
    WBFBSStockSnapshot,
    WBTelegramDelivery,
    YandexMarketStockSnapshot,
)
from telegram_bot.client import TelegramClient
from telegram_bot.dispatcher import TelegramReportDispatcher


@dataclass(frozen=True)
class Check:
    ok: bool
    name: str
    detail: str


OZON_TASK_MAX_AGES = {
    "products": OZON_PRODUCTS_MAX_AGE_SECONDS,
    "orders": OZON_ORDERS_MAX_AGE_SECONDS,
    "supplies": OZON_SUPPLIES_MAX_AGE_SECONDS,
    "communications": OZON_COMMUNICATIONS_MAX_AGE_SECONDS,
    "daily_sales": OZON_DAILY_SALES_MAX_AGE_SECONDS,
    "finances": OZON_FINANCES_MAX_AGE_SECONDS,
    "ads": OZON_ADS_MAX_AGE_SECONDS,
}


def _ozon_task_checks(session, current: datetime) -> list[Check]:
    checks: list[Check] = []
    for task in OZON_REQUIRED_TASKS:
        latest = session.query(OzonSyncRun).filter_by(task=task).order_by(
            OzonSyncRun.started_at.desc()
        ).first()
        if latest is None:
            checks.append(Check(False, f"Ozon {task} sync", "no runs recorded"))
            continue
        timestamp = latest.finished_at or latest.started_at
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=ZoneInfo("UTC"))
        age = current - timestamp.astimezone(current.tzinfo)
        max_age = timedelta(seconds=OZON_TASK_MAX_AGES.get(task, 86400))
        ok = latest.status in {"completed", "running"} and age <= max_age
        detail = f"{latest.status}, age {age}, started {latest.started_at}"
        if latest.error:
            detail += f", error={latest.error[:300]}"
        checks.append(Check(ok, f"Ozon {task} sync", detail))
    return checks


def _failure_signature(checks: list[Check]) -> str:
    names = "\n".join(sorted(check.name for check in checks if not check.ok))
    return hashlib.sha256(names.encode("utf-8")).hexdigest()[:16]


def _error_message(checks: list[Check], now: datetime) -> str:
    failures = [check for check in checks if not check.ok]
    lines = [f"⚠️ Ошибки WB/Ozon/Yandex Market — {now:%d.%m.%Y %H:%M} МСК"]
    lines.extend(f"• {check.name}: {check.detail}" for check in failures)
    return "\n".join(lines)


def _systemctl_active(unit: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return False, f"systemctl unavailable: {exc}"
    status = (result.stdout or result.stderr).strip() or f"exit {result.returncode}"
    return result.returncode == 0 and status == "active", status


def collect_checks(
    *,
    now: datetime | None = None,
    systemctl: Callable[[str], tuple[bool, str]] = _systemctl_active,
) -> list[Check]:
    timezone = ZoneInfo(INVENTORY_TIMEZONE)
    current = now or datetime.now(timezone)
    current = current.replace(tzinfo=timezone) if current.tzinfo is None else current.astimezone(timezone)
    checks: list[Check] = []

    inventory_marketplaces = ["wb", "ozon"]
    if YANDEX_MARKET_CAMPAIGN_IDS:
        inventory_marketplaces.append("yandex_market")
    for marketplace in inventory_marketplaces:
        unit = f"wbozon-inventory@{marketplace}.service"
        ok, status = systemctl(unit)
        checks.append(Check(ok, f"{marketplace} inventory service", status))

    wb_ok, wb_status = systemctl("wbozon-wb.service")
    checks.append(Check(wb_ok, "WB synchronization service", wb_status))
    if WB_TG_BOT_TOKEN and WB_TG_CHAT_ID:
        telegram_ok, telegram_status = systemctl("wbozon-telegram.service")
        checks.append(Check(telegram_ok, "Telegram report service", telegram_status))
        stock_timer_ok, stock_timer_status = systemctl("wbozon-telegram-stock.timer")
        checks.append(Check(stock_timer_ok, "Telegram stock timer", stock_timer_status))
        if WB_TG_PROXY_URL:
            relay_ok, relay_status = systemctl("wbozon-telegram-relay.service")
            checks.append(Check(relay_ok, "Telegram relay service", relay_status))

    with SessionLocal() as session:
        for marketplace in inventory_marketplaces:
            latest = session.query(InventorySyncRun).filter_by(marketplace=marketplace).order_by(
                InventorySyncRun.started_at.desc()
            ).first()
            completed = session.query(InventorySyncRun).filter_by(
                marketplace=marketplace, status="completed"
            ).order_by(InventorySyncRun.finished_at.desc()).first()
            if latest is None:
                checks.append(Check(False, f"latest {marketplace} inventory run", "no runs recorded"))
            else:
                detail = f"{latest.status}, started {latest.started_at}, type={latest.run_type}"
                if latest.error:
                    detail += f", error={latest.error[:300]}"
                checks.append(Check(
                    latest.status in {"completed", "running"},
                    f"latest {marketplace} inventory run",
                    detail,
                ))

            if completed is None or completed.finished_at is None:
                checks.append(Check(False, f"{marketplace} inventory freshness", "no completed runs"))
            else:
                finished_at = completed.finished_at
                if finished_at.tzinfo is None:
                    finished_at = finished_at.replace(tzinfo=ZoneInfo("UTC"))
                age = current - finished_at.astimezone(timezone)
                max_age = timedelta(seconds=INVENTORY_SYNC_INTERVAL_SECONDS * 2 + 900)
                checks.append(Check(
                    age <= max_age,
                    f"{marketplace} inventory freshness",
                    f"last success {age} ago",
                ))

        checks.extend(_ozon_task_checks(session, current))

        snapshot_models = [
            ("WB FBS snapshot", WBFBSStockSnapshot),
            ("WB FBO snapshot", WBFboStockSnapshot),
            ("Ozon snapshot", OzonStockSnapshot),
            ("Ozon warehouse snapshot", OzonWarehouseStockSnapshot),
        ]
        if YANDEX_MARKET_CAMPAIGN_IDS:
            snapshot_models.append(("Yandex Market snapshot", YandexMarketStockSnapshot))
        snapshot_grace = current.replace(hour=0, minute=15, second=0, microsecond=0)
        require_snapshot = current >= snapshot_grace
        for name, model in snapshot_models:
            count = session.query(func.count(model.id)).filter(model.snapshot_date == current.date()).scalar() or 0
            checks.append(Check(not require_snapshot or count > 0, name, f"{count} rows for {current.date()}"))

        hour, minute = (int(part) for part in WB_TG_MORNING_TIME.split(":"))
        delivery_grace = current.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(minutes=30)
        if current >= delivery_grace:
            marketplaces = ("wb", "ozon", "yandex_market")
            keys = [
                f"stock_excel:{marketplace}:{current.date().isoformat()}"
                for marketplace in marketplaces
            ]
            sent = session.query(WBTelegramDelivery).filter(
                WBTelegramDelivery.report_key.in_(keys), WBTelegramDelivery.status == "sent"
            ).count()
            warning = session.query(WBTelegramDelivery).filter_by(
                report_key=f"stock_warning:{current.date().isoformat()}", status="sent"
            ).first()
            checks.append(
                Check(
                    sent == len(marketplaces) or warning is not None,
                    "Telegram stock report",
                    f"{sent}/{len(marketplaces)} files sent",
                )
            )

    return checks


def notify_telegram(checks: list[Check], now: datetime | None = None) -> str:
    timezone = ZoneInfo(INVENTORY_TIMEZONE)
    current = now or datetime.now(timezone)
    current = current.replace(tzinfo=timezone) if current.tzinfo is None else current.astimezone(timezone)
    failures = [check for check in checks if not check.ok]
    signature = _failure_signature(checks)
    with SessionLocal() as session:
        latest = session.query(WBTelegramDelivery).filter(
            WBTelegramDelivery.report_type.in_(("health_error", "health_recovery")),
            WBTelegramDelivery.status == "sent",
        ).order_by(WBTelegramDelivery.sent_at.desc()).first()

    if failures:
        if latest and latest.report_type == "health_error" and f":{signature}:" in latest.report_key:
            return "unchanged error; Telegram alert already sent"
        report_type = "health_error"
        report_key = f"health_error:{signature}:{current:%Y%m%d%H%M%S}"
        content = _error_message(checks, current)
    else:
        if latest is None or latest.report_type != "health_error":
            return "healthy; no Telegram notification needed"
        report_type = "health_recovery"
        report_key = f"health_recovery:{current:%Y%m%d%H%M%S}"
        content = f"✅ WB/Ozon/Yandex Market: работа восстановлена — {current:%d.%m.%Y %H:%M} МСК"

    client = TelegramClient(
        WB_TG_BOT_TOKEN or "",
        WB_TG_CHAT_ID or "",
        timeout=WB_TG_REQUEST_TIMEOUT_SECONDS,
        proxy_url=WB_TG_PROXY_URL,
    )
    dispatcher = TelegramReportDispatcher(client, reports=None)
    result = dispatcher.send_text_content(report_type, report_key, lambda: content)
    return f"Telegram {report_type}: {result['status']}"


def main() -> None:
    try:
        checks = collect_checks()
    except Exception as exc:
        print(f"ERROR database/application healthcheck: {type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc
    for check in checks:
        print(f"{'OK' if check.ok else 'ERROR'} {check.name}: {check.detail}")
    failed = sum(not check.ok for check in checks)
    try:
        print(f"NOTIFY: {notify_telegram(checks)}")
    except Exception as exc:
        failed += 1
        print(f"ERROR Telegram health notification: {type(exc).__name__}: {exc}")
    print(f"SUMMARY: {len(checks) - failed} OK, {failed} ERROR")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
