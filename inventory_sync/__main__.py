from __future__ import annotations

import argparse
import logging
import signal
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from inventory_sync.scheduler import InventoryScheduler, InventorySyncSettings
from inventory_sync.service import InventorySyncService


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Periodic WB, Ozon, and Yandex Market inventory synchronization"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--once", action="store_true", help="refresh current inventory once")
    group.add_argument("--snapshot", action="store_true", help="create today's Moscow-time inventory snapshot")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    settings = InventorySyncSettings()
    service = InventorySyncService()
    if args.once:
        print(service.refresh())
        return
    if args.snapshot:
        timezone = ZoneInfo(settings.timezone_name)
        now = datetime.now(timezone)
        scheduled_for = datetime.combine(now.date(), settings.snapshot_time, timezone)
        print(service.snapshot(now.date(), scheduled_for=scheduled_for))
        return

    scheduler = InventoryScheduler(service, settings=settings)

    def stop(signum: int, frame: Any) -> None:
        scheduler.stop()

    signal.signal(signal.SIGINT, stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop)
    scheduler.run_forever()


if __name__ == "__main__":
    main()
