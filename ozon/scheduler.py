from __future__ import annotations

import logging
from threading import Event
from typing import Any, Callable

from app.config import OZON_SYNC_INTERVAL_SECONDS, OZON_SYNC_RUN_ON_START
from ozon.services.sync_service import OzonSyncService

logger = logging.getLogger(__name__)


class OzonPeriodicSync:
    def __init__(
        self,
        service: OzonSyncService | None = None,
        *,
        interval_seconds: int = OZON_SYNC_INTERVAL_SECONDS,
        run_on_start: bool = OZON_SYNC_RUN_ON_START,
        stop_event: Event | None = None,
    ) -> None:
        if interval_seconds < 1:
            raise ValueError("OZON_SYNC_INTERVAL_SECONDS must be positive")
        self.service = service or OzonSyncService()
        self.interval_seconds = interval_seconds
        self.run_on_start = run_on_start
        self.stop_event = stop_event or Event()

    def run_cycle(self) -> dict[str, dict[str, Any]]:
        tasks: list[tuple[str, Callable[[], Any]]] = [
            ("products", self.service.sync_products),
            ("orders", self.service.sync_orders),
            ("supplies", self.service.sync_supplies),
            ("communications", self.service.sync_communications),
            ("daily_sales", self.service.sync_daily_sales),
            ("finances", self.service.sync_finances),
            ("ads", self.service.sync_ads),
        ]
        results: dict[str, dict[str, Any]] = {}
        for name, callback in tasks:
            if self.stop_event.is_set():
                break
            try:
                value = callback()
                count = len(value) if isinstance(value, list) else value
                results[name] = {"status": "ok", "result": count}
                logger.info("Ozon sync task %s completed: %s", name, count)
            except Exception as exc:
                results[name] = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
                logger.exception("Ozon sync task %s failed", name)
        return results

    def run_forever(self) -> None:
        if not self.run_on_start and self.stop_event.wait(self.interval_seconds):
            return
        while not self.stop_event.is_set():
            self.run_cycle()
            if self.stop_event.wait(self.interval_seconds):
                break

    def stop(self) -> None:
        self.stop_event.set()
