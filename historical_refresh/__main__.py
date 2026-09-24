from __future__ import annotations

import argparse
import json
import logging
from datetime import date

from analytics_facts.service import MARKETPLACES
from historical_refresh.service import HistoricalRefreshService


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Refresh mutable marketplace history and rebuild analytical facts"
    )
    parser.add_argument(
        "--marketplace", choices=("all",) + MARKETPLACES, default="all"
    )
    parser.add_argument("--mode", choices=("rolling", "full"), default="rolling")
    parser.add_argument("--date-from", type=date.fromisoformat)
    parser.add_argument("--date-to", type=date.fromisoformat)
    parser.add_argument("--without-advertising", action="store_true")
    args = parser.parse_args()
    result = HistoricalRefreshService().run(
        marketplace=args.marketplace,
        mode=args.mode,
        date_from=args.date_from,
        date_to=args.date_to,
        include_advertising=not args.without_advertising,
    )
    print(json.dumps(result, ensure_ascii=False, default=str))
    raise SystemExit(1 if result["status"] == "partial" else 0)


if __name__ == "__main__":
    main()
