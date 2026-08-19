from __future__ import annotations

import argparse
import json
import signal
from datetime import date
from typing import Any

from wb.sync_logging import configure_wb_logging, install_context_filter
from ozon.scheduler import OzonPeriodicSync
from ozon.services.overview_service import OzonOverviewService


def main() -> None:
    parser = argparse.ArgumentParser(description="Ozon Seller API synchronization")
    parser.add_argument("--once", action="store_true", help="run one complete Ozon cycle and exit")
    parser.add_argument("--report-day", help="build saved daily sales/finance report, YYYY-MM-DD")
    parser.add_argument("--report-month", help="build saved monthly report from daily rows, YYYY-MM")
    parser.add_argument("--sync-ads", action="store_true", help="synchronize Ozon Performance campaigns")
    args = parser.parse_args()
    if args.sync_ads:
        from ozon.performance.service import OzonPerformanceService
        print(OzonPerformanceService().sync_all())
        return
    if args.report_day:
        day = date.fromisoformat(args.report_day)
        print(json.dumps(OzonOverviewService.report(day, day), ensure_ascii=False, indent=2))
        return
    if args.report_month:
        year, month = (int(value) for value in args.report_month.split("-"))
        print(json.dumps(OzonOverviewService.month_report(year, month), ensure_ascii=False, indent=2))
        return
    configure_wb_logging()
    install_context_filter()
    scheduler = OzonPeriodicSync()

    def stop(signum: int, frame: Any) -> None:
        scheduler.stop()

    signal.signal(signal.SIGINT, stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop)
    if args.once:
        print(scheduler.run_cycle())
    else:
        scheduler.run_forever()


if __name__ == "__main__":
    main()
