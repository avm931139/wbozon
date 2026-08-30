from __future__ import annotations

import argparse

from wb.scheduler import WBPeriodicSync, install_signal_handlers
from wb.sync_logging import configure_wb_logging, install_context_filter


def main() -> None:
    parser = argparse.ArgumentParser(description="Wildberries synchronization worker")
    parser.add_argument("--once", action="store_true", help="run one complete WB cycle and exit")
    parser.add_argument(
        "--sync-only",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    configure_wb_logging()
    install_context_filter()
    scheduler = WBPeriodicSync()
    if args.once:
        scheduler.run_cycle()
        return

    install_signal_handlers(scheduler)
    scheduler.run_forever()


if __name__ == "__main__":
    main()
