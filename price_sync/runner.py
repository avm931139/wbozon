from __future__ import annotations

import uuid
import zlib
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import text

from app.db import SessionLocal
from app.models import MarketplacePriceSyncRun
from price_sync.service import MarketplacePriceService


class PriceSyncAlreadyRunning(RuntimeError):
    pass


class MarketplacePriceRunner:
    def __init__(
        self,
        service: MarketplacePriceService | None = None,
        *,
        session_factory: Callable[..., Any] = SessionLocal,
    ) -> None:
        self.service = service or MarketplacePriceService(session_factory=session_factory)
        self.session_factory = session_factory

    def run(self, marketplace: str) -> dict[str, Any]:
        if marketplace not in self.service.MARKETPLACES:
            raise ValueError(f"unknown price marketplace: {marketplace}")
        run_id = uuid.uuid4().hex
        with self.session_factory() as lock_session:
            if not self._acquire_lock(lock_session, marketplace):
                raise PriceSyncAlreadyRunning(f"{marketplace} price sync is already running")
            try:
                self._create_run(run_id, marketplace)
                result = self.service.sync(marketplace, run_id)
                self._finish_run(
                    run_id,
                    "completed",
                    rows_received=int(result["received"]),
                    rows_saved=int(result["snapshots_saved"]),
                )
                return {"run_id": run_id, "status": "completed", "result": result}
            except Exception as exc:
                self._finish_run(run_id, "failed", error=f"{type(exc).__name__}: {exc}")
                raise
            finally:
                self._release_lock(lock_session, marketplace)

    def _create_run(self, run_id: str, marketplace: str) -> None:
        with self.session_factory() as session:
            session.add(MarketplacePriceSyncRun(
                id=run_id,
                marketplace=marketplace,
                started_at=datetime.now(timezone.utc),
                status="running",
            ))
            session.commit()

    def _finish_run(
        self,
        run_id: str,
        status: str,
        *,
        rows_received: int = 0,
        rows_saved: int = 0,
        error: str | None = None,
    ) -> None:
        with self.session_factory() as session:
            row = session.get(MarketplacePriceSyncRun, run_id)
            if row is None:
                return
            row.finished_at = datetime.now(timezone.utc)
            row.status = status
            row.rows_received = rows_received
            row.rows_saved = rows_saved
            row.error = error
            session.commit()

    @staticmethod
    def _lock_id(marketplace: str) -> int:
        return zlib.crc32(f"wbozon:prices:{marketplace}".encode("utf-8"))

    @classmethod
    def _acquire_lock(cls, session: Any, marketplace: str) -> bool:
        if session.get_bind().dialect.name != "postgresql":
            return True
        return bool(session.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": cls._lock_id(marketplace)},
        ).scalar())

    @classmethod
    def _release_lock(cls, session: Any, marketplace: str) -> None:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": cls._lock_id(marketplace)},
            )
