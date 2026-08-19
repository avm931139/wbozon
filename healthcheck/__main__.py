from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

from sqlalchemy import func

from app.config import INVENTORY_SYNC_INTERVAL_SECONDS, INVENTORY_TIMEZONE, WB_TG_MORNING_TIME
from app.db import SessionLocal
from app.models import (
    InventorySyncRun,
    OzonStockSnapshot,
    OzonWarehouseStockSnapshot,
    WBFboStockSnapshot,
    WBFBSStockSnapshot,
    WBTelegramDelivery,
)


@dataclass(frozen=True)
class Check:
    ok: bool
    name: str
    detail: str


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


def main() -> None:
    try:
        checks = collect_checks()
    except Exception as exc:
        print(f"ERROR database/application healthcheck: {type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc
    for check in checks:
        print(f"{'OK' if check.ok else 'ERROR'} {check.name}: {check.detail}")
    failed = sum(not check.ok for check in checks)
    print(f"SUMMARY: {len(checks) - failed} OK, {failed} ERROR")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
