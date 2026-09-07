import argparse
import json

from supply_movement_report.service import DEFAULT_PATH, SupplyMovementReportService


def main() -> None:
    parser = argparse.ArgumentParser(description="Build all-history marketplace supplies and returns workbook")
    parser.add_argument("--output", default=str(DEFAULT_PATH))
    parser.add_argument("--send-telegram", action="store_true")
    parser.add_argument("--without-live-returns", action="store_true", help="build quickly without WB/Ozon return API calls")
    args = parser.parse_args()
    service = SupplyMovementReportService()
    result = service.send_telegram(args.output) if args.send_telegram else service.save(args.output, include_live_returns=not args.without_live_returns)
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__": main()
