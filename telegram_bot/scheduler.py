from __future__ import annotations

import logging
from datetime import datetime, time
from threading import Event
from zoneinfo import ZoneInfo

from telegram_bot.dispatcher import TelegramReportDispatcher

logger = logging.getLogger(__name__)


class TelegramReportScheduler:
    def __init__(self, dispatcher: TelegramReportDispatcher, *, timezone_name: str, morning_time: str, operational_interval_seconds: int, poll_seconds: int = 30) -> None:
        self.dispatcher = dispatcher
        self.timezone = ZoneInfo(timezone_name)
        hour, minute = (int(part) for part in morning_time.split(":"))
        self.morning_time = time(hour, minute)
        if operational_interval_seconds < 60:
            raise ValueError("WB_TG_OPERATIONAL_INTERVAL_SECONDS must be at least 60")
        self.interval = operational_interval_seconds
        self.poll_seconds = max(1, poll_seconds)
        self.stop_event = Event()

    def run_pending(self, now: datetime | None = None) -> list[dict]:
        now = (now or datetime.now(self.timezone)).astimezone(self.timezone)
        results = []
        if now.time() >= self.morning_time:
            results.append(self.dispatcher.send("morning", f"morning:{now.date().isoformat()}", now=now))
        bucket = int(now.timestamp()) // self.interval
        results.append(self.dispatcher.send("operational", f"operational:{bucket}", now=now))
        return results

    def run_forever(self) -> None:
        logger.info("Telegram report scheduler started")
        while not self.stop_event.is_set():
            try:
                self.run_pending()
            except Exception:
                logger.exception("Telegram report cycle failed")
            self.stop_event.wait(self.poll_seconds)

    def stop(self) -> None:
        self.stop_event.set()
