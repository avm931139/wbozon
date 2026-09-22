from __future__ import annotations

import argparse
import json

from analytics_facts.service import FinancialSalesFactService, MARKETPLACES


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build normalized financial sales and return facts"
    )
    parser.add_argument(
        "--marketplace", choices=(*MARKETPLACES, "all"), default="all"
    )
    args = parser.parse_args()
    marketplaces = MARKETPLACES if args.marketplace == "all" else (args.marketplace,)
    results = [FinancialSalesFactService(value).run() for value in marketplaces]
    print(json.dumps(results, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
