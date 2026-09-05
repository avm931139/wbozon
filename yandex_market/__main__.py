from __future__ import annotations

import argparse
import json
import logging

from yandex_market.services.sync_service import YandexMarketSyncService
from yandex_market.task_runner import YandexMarketTaskRunner


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Yandex Market Partner API synchronization")
    parser.add_argument("--task", required=True, choices=YandexMarketSyncService.task_names())
    args = parser.parse_args()
    result = YandexMarketTaskRunner().run(args.task)
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
