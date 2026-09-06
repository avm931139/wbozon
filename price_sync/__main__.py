from __future__ import annotations

import argparse
import json

from price_sync.runner import MarketplacePriceRunner
from price_sync.service import MarketplacePriceService


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture marketplace prices and immutable history")
    parser.add_argument("--marketplace", required=True, choices=MarketplacePriceService.MARKETPLACES)
    args = parser.parse_args()
    print(json.dumps(
        MarketplacePriceRunner().run(args.marketplace),
        ensure_ascii=False,
        default=str,
    ))


if __name__ == "__main__":
    main()
