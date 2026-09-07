from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.exc import IntegrityError

from app.config import (
    FINANCE_RECONCILIATION_INBOX,
    FINANCE_RECONCILIATION_REPORTS,
    FINANCE_RECONCILIATION_TG_BOT_TOKEN,
    FINANCE_RECONCILIATION_TG_CHAT_ID,
    FINANCE_RECONCILIATION_TG_PROXY_URL,
    FINANCE_RECONCILIATION_TOLERANCE,
)
from app.db import SessionLocal
from app.models import FinanceReconciliationRun
from finance_reconciliation.parsing import parse_export
from finance_reconciliation.report import compare, write_report
from finance_reconciliation.sources import SOURCE_LOADERS
from telegram_bot.client import TelegramClient


logger = logging.getLogger(__name__)
SUPPORTED_SUFFIXES = {".xlsx", ".csv"}


@dataclass(frozen=True)
class ReconciliationResult:
    run_id: str | None
    source_file: str
    status: str
    marketplace: str | None = None
    report_path: str | None = None
    message: str | None = None


class FinanceReconciliationService:
    def __init__(
        self,
        *,
        inbox: str | Path = FINANCE_RECONCILIATION_INBOX,
        reports: str | Path = FINANCE_RECONCILIATION_REPORTS,
        tolerance: Decimal | str = FINANCE_RECONCILIATION_TOLERANCE,
        session_factory: Callable[..., Any] = SessionLocal,
        telegram: TelegramClient | None = None,
    ) -> None:
        self.inbox = Path(inbox)
        self.reports = Path(reports)
        self.tolerance = Decimal(str(tolerance))
        if self.tolerance < 0:
            raise ValueError("tolerance must not be negative")
        self.session_factory = session_factory
        self.telegram = telegram
        if telegram is None and FINANCE_RECONCILIATION_TG_BOT_TOKEN and FINANCE_RECONCILIATION_TG_CHAT_ID:
            self.telegram = TelegramClient(
                FINANCE_RECONCILIATION_TG_BOT_TOKEN,
                FINANCE_RECONCILIATION_TG_CHAT_ID,
                proxy_url=FINANCE_RECONCILIATION_TG_PROXY_URL,
            )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def scan(self, *, notify: bool = True) -> list[ReconciliationResult]:
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.reports.mkdir(parents=True, exist_ok=True)
        results = []
        for path in sorted(self.inbox.iterdir()):
            if path.is_file() and path.suffix.casefold() in SUPPORTED_SUFFIXES and not path.name.startswith("~$"):
                results.append(self.process(path, notify=notify))
        return results

    def process(
        self,
        path: str | Path,
        *,
        marketplace: str | None = None,
        notify: bool = True,
        force: bool = False,
    ) -> ReconciliationResult:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        file_hash = self._sha256(source)
        with self.session_factory() as session:
            previous = session.query(FinanceReconciliationRun).filter_by(file_sha256=file_hash).one_or_none()
            if previous and not force:
                return ReconciliationResult(previous.id, str(source), "already_processed", previous.marketplace, previous.report_path)

        run_id = previous.id if previous else str(uuid.uuid4())
        started = datetime.now(timezone.utc)
        if previous:
            with self.session_factory() as session:
                stored = session.get(FinanceReconciliationRun, run_id)
                stored.status = "processing"
                stored.error = None
                stored.started_at = started
                stored.finished_at = None
                stored.telegram_message_id = None
                session.commit()
        else:
            row = FinanceReconciliationRun(
                id=run_id, source_file=str(source), file_sha256=file_hash, status="processing",
                details={}, started_at=started,
            )
            try:
                with self.session_factory() as session:
                    session.add(row)
                    session.commit()
            except IntegrityError:
                return ReconciliationResult(None, str(source), "already_processed")

        try:
            parsed = parse_export(source, marketplace)
            if parsed.period_start is None or parsed.period_end is None:
                raise ValueError("report period is not recognized from row dates or filename")
            with self.session_factory() as session:
                api_rows = SOURCE_LOADERS[parsed.marketplace](session, parsed.period_start, parsed.period_end)
            if not api_rows:
                raise ValueError(f"no saved {parsed.marketplace} API finance rows for {parsed.period_start}—{parsed.period_end}")
            comparison = compare(parsed.rows, api_rows, self.tolerance)
            report_path = self.reports / f"{source.stem}__{parsed.marketplace}__{run_id[:8]}.xlsx"
            write_report(report_path, parsed, comparison, source.name)
            difference = comparison.cabinet_total - comparison.api_total
            details = {
                "ignored_sheets": parsed.ignored_sheets,
                "tolerance": str(self.tolerance),
                "source_unchanged": True,
            }
            with self.session_factory() as session:
                stored = session.get(FinanceReconciliationRun, run_id)
                stored.marketplace = parsed.marketplace
                stored.period_start = parsed.period_start
                stored.period_end = parsed.period_end
                stored.status = comparison.status
                stored.cabinet_rows = comparison.cabinet_row_count
                stored.api_rows = comparison.api_row_count
                stored.matched_rows = len(comparison.matched)
                stored.missing_in_api = len(comparison.missing_in_api)
                stored.missing_in_cabinet = len(comparison.missing_in_cabinet)
                stored.amount_mismatches = len(comparison.amount_mismatches)
                stored.cabinet_total = comparison.cabinet_total
                stored.api_total = comparison.api_total
                stored.difference = difference
                stored.report_path = str(report_path)
                stored.details = details
                stored.finished_at = datetime.now(timezone.utc)
                session.commit()
            message_id = None
            if notify and self.telegram:
                status_text = "✅ корректен" if comparison.status == "correct" else "⚠️ содержит расхождения"
                caption = (
                    f"Сверка {parsed.marketplace}: отчёт {status_text}\n"
                    f"Период: {parsed.period_start} — {parsed.period_end}\n"
                    f"Совпало: {len(comparison.matched)}; нет в API: {len(comparison.missing_in_api)}; "
                    f"нет в кабинете: {len(comparison.missing_in_cabinet)}; суммы: {len(comparison.amount_mismatches)}\n"
                    f"Общая разница: {difference:.2f} ₽"
                )
                try:
                    message_id = self.telegram.send_document(report_path.name, report_path.read_bytes(), caption=caption)
                    with self.session_factory() as session:
                        stored = session.get(FinanceReconciliationRun, run_id)
                        stored.telegram_message_id = message_id
                        session.commit()
                except Exception as exc:
                    logger.exception("Reconciliation completed but Telegram delivery failed")
                    with self.session_factory() as session:
                        stored = session.get(FinanceReconciliationRun, run_id)
                        stored.error = f"Telegram delivery: {type(exc).__name__}: {exc}"
                        session.commit()
            return ReconciliationResult(run_id, str(source), comparison.status, parsed.marketplace, str(report_path))
        except Exception as exc:
            logger.exception("Financial report reconciliation failed for %s", source)
            with self.session_factory() as session:
                stored = session.get(FinanceReconciliationRun, run_id)
                stored.status = "failed"
                stored.error = f"{type(exc).__name__}: {exc}"
                stored.finished_at = datetime.now(timezone.utc)
                session.commit()
            if notify and self.telegram:
                try:
                    self.telegram.send_text(f"❌ Не удалось сверить финансовый отчёт {source.name}: {type(exc).__name__}: {exc}")
                except Exception:
                    logger.exception("Failed to deliver reconciliation error to Telegram")
            return ReconciliationResult(run_id, str(source), "failed", message=f"{type(exc).__name__}: {exc}")
