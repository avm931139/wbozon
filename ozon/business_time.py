from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import OZON_TIMEZONE


def ozon_today(now: datetime | None = None, *, timezone_name: str = OZON_TIMEZONE) -> date:
    timezone = ZoneInfo(timezone_name)
    current = now or datetime.now(timezone)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone)
    return current.astimezone(timezone).date()
