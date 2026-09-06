from __future__ import annotations

import json

from product_master.service import ProductMappingService


def main() -> None:
    print(json.dumps(ProductMappingService().run(), ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
