from __future__ import annotations

import json
import logging
import sys
import traceback
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterator

from app.config import WB_LOG_BACKUP_COUNT, WB_LOG_DIR, WB_LOG_LEVEL, WB_LOG_MAX_BYTES

cycle_context: ContextVar[str | None] = ContextVar("wb_cycle_id", default=None)
task_context: ContextVar[str | None] = ContextVar("wb_task", default=None)

_SENSITIVE_PARTS = ("authorization", "api_key", "apikey", "token", "secret", "password")
_MAX_VALUE_LENGTH = 2000
_database_logging_enabled = False


def _safe_value(value: Any, key: str = "") -> Any:
    if any(part in key.casefold() for part in _SENSITIVE_PARTS):
        return "***"
    if isinstance(value, dict):
        return {str(item_key): _safe_value(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, (list, tuple, set)):
        rows = list(value)
        sanitized = [_safe_value(item) for item in rows[:100]]
        if len(rows) > 100:
            sanitized.append(f"... {len(rows) - 100} more items")
        return sanitized
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = str(value)
    return text if len(text) <= _MAX_VALUE_LENGTH else f"{text[:_MAX_VALUE_LENGTH]}... [truncated]"


def summarize_result(value: Any) -> Any:
    """Keep operational logs useful without persisting complete WB payloads."""
    if isinstance(value, list):
        return {"type": "list", "count": len(value)}
    if isinstance(value, tuple):
        return [summarize_result(item) for item in value]
    if isinstance(value, dict):
        return {str(key): summarize_result(item) for key, item in value.items()}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return _safe_value(value)


def build_error_event(
    exc: BaseException,
    *,
    phase: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    frames = traceback.extract_tb(exc.__traceback__) if exc.__traceback__ else []
    origin = frames[-1] if frames else None
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cycle_id": cycle_context.get(),
        "task": task_context.get(),
        "phase": phase,
        "exception_type": type(exc).__name__,
        "message": _safe_value(exc),
        "file": origin.filename if origin else None,
        "line": origin.lineno if origin else None,
        "function": origin.name if origin else None,
        "module": Path(origin.filename).stem if origin else None,
        "source_line": origin.line if origin else None,
        "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        "details": _safe_value(details or {}),
    }


class JsonEventFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "wb_event", None)
        if event is None:
            event = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "cycle_id": cycle_context.get(),
                "task": task_context.get(),
            }
        return json.dumps(event, ensure_ascii=False, default=str)


def configure_wb_logging(
    log_dir: str | Path = WB_LOG_DIR,
    level: str = WB_LOG_LEVEL,
    max_bytes: int = WB_LOG_MAX_BYTES,
    backup_count: int = WB_LOG_BACKUP_COUNT,
) -> tuple[Path, Path]:
    global _database_logging_enabled
    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)
    activity_path = directory / "wb_sync.log"
    error_path = directory / "wb_errors.jsonl"

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s cycle=%(cycle_id)s task=%(task)s: %(message)s"
    )
    activity_handler = RotatingFileHandler(
        activity_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    activity_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    wb_logger = logging.getLogger("wb")
    wb_logger.setLevel(getattr(logging, level, logging.INFO))
    wb_logger.handlers.clear()
    wb_logger.addHandler(activity_handler)
    wb_logger.addHandler(console_handler)
    wb_logger.propagate = False

    error_handler = RotatingFileHandler(
        error_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    error_handler.setFormatter(JsonEventFormatter())
    error_logger = logging.getLogger("wb_errors")
    error_logger.setLevel(logging.ERROR)
    error_logger.handlers.clear()
    error_logger.addHandler(error_handler)
    error_logger.propagate = False
    _database_logging_enabled = True
    return activity_path, error_path


class SyncContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.cycle_id = cycle_context.get() or "-"
        record.task = task_context.get() or "-"
        return True


def install_context_filter() -> None:
    for handler in logging.getLogger("wb").handlers:
        handler.addFilter(SyncContextFilter())


@contextmanager
def sync_context(cycle_id: str | None = None, task: str | None = None) -> Iterator[None]:
    cycle_token = cycle_context.set(cycle_id if cycle_id is not None else cycle_context.get())
    task_token = task_context.set(task if task is not None else task_context.get())
    try:
        yield
    finally:
        task_context.reset(task_token)
        cycle_context.reset(cycle_token)


def report_exception(
    exc: BaseException,
    *,
    phase: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = build_error_event(exc, phase=phase, details=details)
    logging.getLogger("wb_errors").error(event["message"], extra={"wb_event": event})
    if _database_logging_enabled:
        _persist_error_event(event)
    return event


def start_sync_run(cycle_id: str) -> None:
    if not _database_logging_enabled:
        return
    from app.db import SessionLocal
    from app.models import WBSyncRun

    try:
        with SessionLocal() as session:
            session.add(
                WBSyncRun(
                    id=cycle_id,
                    status="running",
                    started_at=datetime.now(timezone.utc),
                    tasks_total=0,
                    tasks_succeeded=0,
                    tasks_failed=0,
                    results={},
                )
            )
            session.commit()
    except Exception as exc:
        _log_persistence_failure(exc, "start_sync_run", {"cycle_id": cycle_id})


def finish_sync_run(cycle_id: str, results: dict[str, Any], duration_seconds: float) -> None:
    if not _database_logging_enabled:
        return
    from app.db import SessionLocal
    from app.models import WBSyncRun

    try:
        with SessionLocal() as session:
            row = session.get(WBSyncRun, cycle_id)
            if row is None:
                return
            failures = sum(item.get("status") == "error" for item in results.values())
            row.status = "partial" if failures else "completed"
            row.finished_at = datetime.now(timezone.utc)
            row.duration_seconds = duration_seconds
            row.tasks_total = len(results)
            row.tasks_failed = failures
            row.tasks_succeeded = len(results) - failures
            row.results = _safe_value(results)
            session.commit()
    except Exception as exc:
        _log_persistence_failure(exc, "finish_sync_run", {"cycle_id": cycle_id})


def _persist_error_event(event: dict[str, Any]) -> None:
    from app.db import SessionLocal
    from app.models import WBSyncError, WBSyncRun

    try:
        with SessionLocal() as session:
            cycle_id = event.get("cycle_id")
            if cycle_id and session.get(WBSyncRun, cycle_id) is None:
                cycle_id = None
            session.add(
                WBSyncError(
                    cycle_id=cycle_id,
                    task=event.get("task"),
                    phase=event["phase"],
                    exception_type=event["exception_type"],
                    message=str(event["message"]),
                    file=event.get("file"),
                    line=event.get("line"),
                    function=event.get("function"),
                    module=event.get("module"),
                    source_line=event.get("source_line"),
                    traceback=event["traceback"],
                    details=event.get("details") or {},
                    created_at=datetime.fromisoformat(event["timestamp"]),
                )
            )
            session.commit()
    except Exception as exc:
        _log_persistence_failure(exc, "persist_error", {"original_event": event})


def _log_persistence_failure(exc: BaseException, operation: str, details: dict[str, Any]) -> None:
    event = build_error_event(exc, phase="logging_database", details={"operation": operation, **details})
    logging.getLogger("wb_errors").error(event["message"], extra={"wb_event": event})
