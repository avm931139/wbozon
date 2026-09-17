from __future__ import annotations

import argparse
import json

from backup.service import BackupService


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up and verify wbozon data")
    parser.add_argument("operation", choices=("init", "run", "verify"))
    args = parser.parse_args()

    service = BackupService.from_env()
    if args.operation == "init":
        result = service.initialize_repository()
    elif args.operation == "run":
        result = service.run_backup()
    else:
        result = service.verify_restore()
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
