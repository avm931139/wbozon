from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from threading import Event
from typing import Callable
from zoneinfo import ZoneInfo

from app.config import (
    INVENTORY_SNAPSHOT_TIME,
    INVENTORY_SYNC_INTERVAL_SECONDS,
    INVENTORY_SYNC_RUN_ON_START,
    INVENTORY_TIMEZONE,
)
from inventory_sync.service import InventorySyncService


logger = logging.getLogger(__name__)


def _parse_time(value: str) -> time:
    try:
        hour, minute = (int(part) for part in value.split(":"))
        return time(hour=hour, minute=minute)
    except (TypeError, ValueError) as exc:
        raise ValueError("INVENTORY_SNAPSHOT_TIME must use HH:MM format") from exc


@dataclass(frozen=True)
class InventorySyncSettings:
    interval_seconds: int = INVENTORY_SYNC_INTERVAL_SECONDS
    snapshot_time: time = _parse_time(INVENTORY_SNAPSHOT_TIME)
    timezone_name: str = INVENTORY_TIMEZONE
    run_on_start: bool = INVENTORY_SYNC_RUN_ON_START

    def __post_init__(self) -> None:
        if self.interval_seconds < 1:
            raise ValueError("INVENTORY_SYNC_INTERVAL_SECONDS must be positive")
        ZoneInfo(self.timezone_name)


class InventoryScheduler:
    def __init__(
        self,
        service: InventorySyncService | None = None,
        *,
        settings: InventorySyncSettings | None = None,
        stop_event: Event | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.service = service or InventorySyncService()
        self.settings = settings or InventorySyncSettings()
        self.stop_event = stop_event or Event()
        self.timezone = ZoneInfo(self.settings.timezone_name)
        self._now = now or (lambda: datetime.now(self.timezone))
        self._next_refresh: datetime | None = None

    def run_pending(self, now: datetime | None = None) -> list[dict[str, object]]:
        current = (now or self._now()).astimezone(self.timezone)
        results: list[dict[str, object]] = []
        due_date = self._due_snapshot_date(current)
        if due_date is not None:
            scheduled_for = datetime.combine(due_date, self.settings.snapshot_time, self.timezone)
            results.append({"type": "daily_snapshot", "result": self.service.snapshot(due_date, scheduled_for=scheduled_for)})
            self._next_refresh = current + timedelta(seconds=self.settings.interval_seconds)

        if self._next_refresh is None:
            self._next_refresh = current if self.settings.run_on_start else current + timedelta(seconds=self.settings.interval_seconds)
        if current >= self._next_refresh:
            results.append({"type": "periodic", "result": self.service.refresh(scheduled_for=self._next_refresh)})
            self._next_refresh = current + timedelta(seconds=self.settings.interval_seconds)
        return results

    def run_forever(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.run_pending()
            except Exception:
                logger.exception("Inventory synchronization failed; it will be retried on the next interval")
                current = self._now().astimezone(self.timezone)
                self._next_refresh = current + timedelta(seconds=self.settings.interval_seconds)
            current = self._now().astimezone(self.timezone)
            next_snapshot = self._next_snapshot_at(current)
            candidates = [next_snapshot]
            if self._next_refresh is not None:
                candidates.append(self._next_refresh)
            wait_seconds = max(0.1, min((candidate - current).total_seconds() for candidate in candidates))
            if self.stop_event.wait(wait_seconds):
                break

    def stop(self) -> None:
        self.stop_event.set()

    def _due_snapshot_date(self, current: datetime) -> date | None:
        scheduled = datetime.combine(current.date(), self.settings.snapshot_time, self.timezone)
        if current < scheduled or self.service.snapshot_exists(current.date()):
            return None
        return current.date()

    def _next_snapshot_at(self, current: datetime) -> datetime:
        today = datetime.combine(current.date(), self.settings.snapshot_time, self.timezone)
        if current < today and not self.service.snapshot_exists(current.date()):
            return today
        return datetime.combine(current.date() + timedelta(days=1), self.settings.snapshot_time, self.timezone)
