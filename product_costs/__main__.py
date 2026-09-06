from __future__ import annotations

import argparse
import json

from product_costs.importer import ProductCostImporter


def main() -> None:
    parser = argparse.ArgumentParser(description="Import product costs from an xlsx template")
    parser.add_argument("filename")
    args = parser.parse_args()
    print(json.dumps(ProductCostImporter().import_file(args.filename), ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
