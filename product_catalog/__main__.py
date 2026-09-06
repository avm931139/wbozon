from __future__ import annotations

import argparse
import json

from product_catalog.service import ProductCatalogService


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize product cards and download media")
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--download-limit", type=int)
    args = parser.parse_args()
    kwargs = {} if args.download_limit is None else {"download_limit": args.download_limit}
    result = ProductCatalogService(**kwargs).run(download=not args.no_download)
    print(json.dumps(result, ensure_ascii=False, default=str))
    if result["status"] == "partial":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
