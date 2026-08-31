from __future__ import annotations

import argparse
import json
import logging
import uuid
import zlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.config import (
    WB_DOCUMENT_DOWNLOAD_LIMIT,
    WB_DOCUMENT_LOOKBACK_DAYS,
    WB_DOCUMENT_TIMEZONE,
)
from app.db import SessionLocal
from app.models import WBDocumentSyncRun
from wb.services.document_service import DocumentService


logger = logging.getLogger(__name__)
LOCK_ID = zlib.crc32(b"wbozon:wb-documents")


class WBDocumentSyncAlreadyRunning(RuntimeError):
    pass


@dataclass(frozen=True)
class WBDocumentSyncSettings:
    timezone_name: str = WB_DOCUMENT_TIMEZONE
    lookback_days: int = WB_DOCUMENT_LOOKBACK_DAYS
    download_limit: int = WB_DOCUMENT_DOWNLOAD_LIMIT

    def __post_init__(self) -> None:
        ZoneInfo(self.timezone_name)
        if self.lookback_days < 1:
            raise ValueError("WB_DOCUMENT_LOOKBACK_DAYS must be positive")
        if self.download_limit < 1:
            raise ValueError("WB_DOCUMENT_DOWNLOAD_LIMIT must be positive")


class WBDocumentSyncRunner:
    """Run independent WB document steps and persist one durable result."""

    def __init__(
        self,
        *,
        service: DocumentService | None = None,
        settings: WBDocumentSyncSettings | None = None,
        session_factory: Callable[..., Any] = SessionLocal,
    ) -> None:
        self.service = service or DocumentService()
        self.settings = settings or WBDocumentSyncSettings()
        self.timezone = ZoneInfo(self.settings.timezone_name)
        self.session_factory = session_factory

    def run(
        self,
        *,
        begin_date: date | None = None,
        end_date: date | None = None,
        all_history: bool = False,
        download_limit: int | None = None,
    ) -> dict[str, Any]:
        if (begin_date is None) != (end_date is None):
            raise ValueError("begin_date and end_date must be specified together")
        if all_history and begin_date is not None:
            raise ValueError("all_history cannot be combined with an explicit period")
        limit = self.settings.download_limit if download_limit is None else download_limit
        if limit < 1:
            raise ValueError("download_limit must be positive")

        current_date = datetime.now(self.timezone).date()
        if not all_history and begin_date is None:
            begin_date = current_date - timedelta(days=self.settings.lookback_days - 1)
            end_date = current_date

        run_id = uuid.uuid4().hex
        started_at = datetime.now(timezone.utc)
        with self.session_factory() as lock_session:
            if not self._acquire_lock(lock_session):
                raise WBDocumentSyncAlreadyRunning("WB document synchronization is already running")
            try:
                self._create_run(run_id, started_at)
                results: dict[str, dict[str, Any]] = {}
                steps = (
                    ("categories", lambda: self.service.sync_categories("ru")),
                    (
                        "documents",
                        lambda: self.service.sync_documents(begin_date, end_date, "ru"),
                    ),
                    ("balance", self.service.sync_balance),
                    ("files", lambda: self.service.sync_missing_files(limit)),
                )
                for name, callback in steps:
                    try:
                        value = callback()
                        if name == "files" and isinstance(value, dict) and value.get("failed"):
                            raise RuntimeError("; ".join(value.get("errors") or ["document download failed"]))
                        results[name] = {"status": "completed", "result": value}
                    except Exception as exc:
                        logger.exception("WB document sync step failed: %s", name)
                        results[name] = {
                            "status": "failed",
                            "error": f"{type(exc).__name__}: {exc}",
                        }

                failed = [name for name, item in results.items() if item["status"] == "failed"]
                succeeded = len(results) - len(failed)
                status = "completed" if not failed else ("partial" if succeeded else "failed")
                error = "; ".join(f"{name}: {results[name]['error']}" for name in failed) or None
                self._finish_run(run_id, status, results, error)
                return {"run_id": run_id, "status": status, "result": results, "error": error}
            finally:
                self._release_lock(lock_session)

    def _create_run(self, run_id: str, started_at: datetime) -> None:
        with self.session_factory() as session:
            session.add(WBDocumentSyncRun(
                id=run_id,
                started_at=started_at,
                status="running",
            ))
            session.commit()

    def _finish_run(
        self,
        run_id: str,
        status: str,
        result: dict[str, Any],
        error: str | None,
    ) -> None:
        with self.session_factory() as session:
            row = session.get(WBDocumentSyncRun, run_id)
            if row is None:
                raise RuntimeError(f"WB document sync run {run_id} disappeared")
            row.finished_at = datetime.now(timezone.utc)
            row.status = status
            row.result = result
            row.error = error
            session.commit()

    @staticmethod
    def _acquire_lock(session: Any) -> bool:
        if session.get_bind().dialect.name != "postgresql":
            return True
        return bool(session.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": LOCK_ID},
        ).scalar())

    @staticmethod
    def _release_lock(session: Any) -> None:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": LOCK_ID},
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronize WB documents and seller balance")
    parser.add_argument("--begin-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument("--all-history", action="store_true")
    parser.add_argument("--download-limit", type=int)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = WBDocumentSyncRunner().run(
        begin_date=args.begin_date,
        end_date=args.end_date,
        all_history=args.all_history,
        download_limit=args.download_limit,
    )
    print(json.dumps(result, ensure_ascii=False, default=str))
    raise SystemExit(0 if result["status"] == "completed" else 1)


if __name__ == "__main__":
    main()
