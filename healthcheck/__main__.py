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
    WB_TG_BOT_TOKEN,
    WB_TG_CHAT_ID,
    WB_TG_MORNING_TIME,
    WB_TG_REQUEST_TIMEOUT_SECONDS,
)
from app.db import SessionLocal
from app.models import (
    InventorySyncRun,
    OzonStockSnapshot,
    OzonWarehouseStockSnapshot,
    WBFboStockSnapshot,
    WBFBSStockSnapshot,
    WBTelegramDelivery,
)
from telegram_bot.client import TelegramClient
from telegram_bot.dispatcher import TelegramReportDispatcher


@dataclass(frozen=True)
class Check:
    ok: bool
    name: str
    detail: str


def _failure_signature(checks: list[Check]) -> str:
    names = "\n".join(sorted(check.name for check in checks if not check.ok))
    return hashlib.sha256(names.encode("utf-8")).hexdigest()[:16]


def _error_message(checks: list[Check], now: datetime) -> str:
    failures = [check for check in checks if not check.ok]
    lines = [f"⚠️ Ошибки WB/Ozon — {now:%d.%m.%Y %H:%M} МСК"]
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

    inventory_ok, inventory_status = systemctl("wbozon-inventory.service")
    checks.append(Check(inventory_ok, "inventory service", inventory_status))
    cron_ok, cron_status = systemctl("cron.service")
    if not cron_ok and cron_status in {"unknown", "inactive", "exit 4"}:
        cron_ok, cron_status = systemctl("crond.service")
    checks.append(Check(cron_ok, "cron service", cron_status))

    with SessionLocal() as session:
        latest = session.query(InventorySyncRun).order_by(InventorySyncRun.started_at.desc()).first()
        completed = session.query(InventorySyncRun).filter_by(status="completed").order_by(
            InventorySyncRun.finished_at.desc()
        ).first()
        if latest is None:
            checks.append(Check(False, "latest inventory run", "no runs recorded"))
        else:
            detail = f"{latest.status}, started {latest.started_at}, type={latest.run_type}"
            if latest.error:
                detail += f", error={latest.error[:300]}"
            checks.append(Check(latest.status in {"completed", "running"}, "latest inventory run", detail))

        if completed is None or completed.finished_at is None:
            checks.append(Check(False, "inventory freshness", "no completed runs"))
        else:
            finished_at = completed.finished_at
            if finished_at.tzinfo is None:
                finished_at = finished_at.replace(tzinfo=ZoneInfo("UTC"))
            age = current - finished_at.astimezone(timezone)
            max_age = timedelta(seconds=INVENTORY_SYNC_INTERVAL_SECONDS * 2 + 900)
            checks.append(Check(age <= max_age, "inventory freshness", f"last success {age} ago"))

        snapshot_models = (
            ("WB FBS snapshot", WBFBSStockSnapshot),
            ("WB FBO snapshot", WBFboStockSnapshot),
            ("Ozon snapshot", OzonStockSnapshot),
            ("Ozon warehouse snapshot", OzonWarehouseStockSnapshot),
        )
        snapshot_grace = current.replace(hour=0, minute=15, second=0, microsecond=0)
        require_snapshot = current >= snapshot_grace
        for name, model in snapshot_models:
            count = session.query(func.count(model.id)).filter(model.snapshot_date == current.date()).scalar() or 0
            checks.append(Check(not require_snapshot or count > 0, name, f"{count} rows for {current.date()}"))

        hour, minute = (int(part) for part in WB_TG_MORNING_TIME.split(":"))
        delivery_grace = current.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(minutes=30)
        if current >= delivery_grace:
            keys = [f"stock_excel:{marketplace}:{current.date().isoformat()}" for marketplace in ("wb", "ozon")]
            sent = session.query(WBTelegramDelivery).filter(
                WBTelegramDelivery.report_key.in_(keys), WBTelegramDelivery.status == "sent"
            ).count()
            warning = session.query(WBTelegramDelivery).filter_by(
                report_key=f"stock_warning:{current.date().isoformat()}", status="sent"
            ).first()
            checks.append(Check(sent == 2 or warning is not None, "Telegram stock report", f"{sent}/2 files sent"))

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
        content = f"✅ WB/Ozon: работа восстановлена — {current:%d.%m.%Y %H:%M} МСК"

    client = TelegramClient(
        WB_TG_BOT_TOKEN or "",
        WB_TG_CHAT_ID or "",
        timeout=WB_TG_REQUEST_TIMEOUT_SECONDS,
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
