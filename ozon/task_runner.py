from __future__ import annotations

import json
import uuid
import zlib
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import text

from app.db import SessionLocal
from app.models import OzonSyncRun
from ozon.services.sync_service import OzonSyncService


class OzonTaskAlreadyRunning(RuntimeError):
    pass


class OzonTaskRunner:
    """Run one Ozon domain task with a DB lock and persistent status journal."""

    def __init__(
        self,
        service: OzonSyncService | None = None,
        *,
        session_factory: Callable[..., Any] = SessionLocal,
    ) -> None:
        self.service = service or OzonSyncService()
        self.session_factory = session_factory

    def run(self, task: str) -> dict[str, Any]:
        if task not in self.service.task_names():
            raise ValueError(f"unknown Ozon task: {task}")
        run_id = uuid.uuid4().hex
        started_at = datetime.now(timezone.utc)
        with self.session_factory() as lock_session:
            if not self._acquire_lock(lock_session, task):
                raise OzonTaskAlreadyRunning(f"Ozon task {task} is already running")
            try:
                self._create_run(run_id, task, started_at)
                result = self.service.run_task(task)
                normalized = self._json_value(result)
                status = "skipped" if isinstance(result, dict) and result.get("skipped") else "completed"
                self._finish_run(run_id, status, result=normalized)
                return {"task": task, "status": status, "result": normalized}
            except Exception as exc:
                self._finish_run(run_id, "failed", error=f"{type(exc).__name__}: {exc}")
                raise
            finally:
                self._release_lock(lock_session, task)

    def _create_run(self, run_id: str, task: str, started_at: datetime) -> None:
        with self.session_factory() as session:
            session.add(OzonSyncRun(id=run_id, task=task, started_at=started_at, status="running"))
            session.commit()

    def _finish_run(
        self,
        run_id: str,
        status: str,
        *,
        result: Any = None,
        error: str | None = None,
    ) -> None:
        with self.session_factory() as session:
            row = session.get(OzonSyncRun, run_id)
            if row is None:
                return
            row.finished_at = datetime.now(timezone.utc)
            row.status = status
            row.result = result
            row.error = error
            session.commit()

    @staticmethod
    def _json_value(value: Any) -> Any:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))

    @staticmethod
    def _lock_id(task: str) -> int:
        return zlib.crc32(f"wbozon:ozon:{task}".encode("utf-8"))

    @classmethod
    def _acquire_lock(cls, session: Any, task: str) -> bool:
        if session.get_bind().dialect.name != "postgresql":
            return True
        return bool(
            session.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": cls._lock_id(task)},
            ).scalar()
        )

    @classmethod
    def _release_lock(cls, session: Any, task: str) -> None:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": cls._lock_id(task)},
            )
