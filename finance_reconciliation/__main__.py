from __future__ import annotations

import argparse
import json
import logging

from finance_reconciliation.service import FinanceReconciliationService


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile cabinet financial exports with saved API finance rows")
    parser.add_argument("--file", help="process one .xlsx or .csv file; otherwise scan the inbox")
    parser.add_argument("--marketplace", choices=("wb", "ozon", "yandex_market"), help="override automatic detection")
    parser.add_argument("--no-telegram", action="store_true")
    parser.add_argument("--force", action="store_true", help="repeat comparison even when this SHA-256 was processed")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    service = FinanceReconciliationService()
    if args.file:
        results = [service.process(
            args.file, marketplace=args.marketplace,
            notify=not args.no_telegram, force=args.force,
        )]
    else:
        results = service.scan(notify=not args.no_telegram)
    print(json.dumps([result.__dict__ for result in results], ensure_ascii=False, default=str))
    if any(result.status == "failed" for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
