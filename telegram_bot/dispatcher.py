from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import WBTelegramDelivery
from wb.sync_logging import report_exception, sync_context
from telegram_bot.client import TelegramClient
from telegram_bot.reports import TelegramReportService


class TelegramReportDispatcher:
    def __init__(self, client: TelegramClient, reports: TelegramReportService, *, session_factory: Callable[..., Any] = SessionLocal) -> None:
        self.client = client
        self.reports = reports
        self.session_factory = session_factory

    def send(self, report_type: str, report_key: str, *, now: datetime | None = None, force: bool = False) -> dict[str, Any]:
        with sync_context(cycle_id=None, task=f"telegram_{report_type}"):
            row_id = self._reserve(report_type, report_key, force)
            if row_id is None:
                return {"status": "skipped", "report_key": report_key}
            try:
                text = self.reports.morning(now) if report_type == "morning" else self.reports.operational(now)
                message_ids = self.client.send_text(text)
                with self.session_factory() as session:
                    row = session.get(WBTelegramDelivery, row_id)
                    row.status = "sent"; row.sent_at = datetime.now(timezone.utc)
                    row.message_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                    row.telegram_message_ids = message_ids; row.error_text = None
                    session.commit()
                return {"status": "sent", "report_key": report_key, "message_ids": message_ids}
            except Exception as exc:
                report_exception(exc, phase="telegram_report", details={"report_type": report_type, "report_key": report_key})
                with self.session_factory() as session:
                    row = session.get(WBTelegramDelivery, row_id)
                    if row:
                        row.status = "error"; row.error_text = str(exc)[:4000]; session.commit()
                raise

    def send_document(
        self,
        report_type: str,
        report_key: str,
        document_factory: Callable[[], tuple[str, bytes, str]],
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        """Build an in-memory document only after reserving its delivery key."""
        with sync_context(cycle_id=None, task=f"telegram_{report_type}"):
            row_id = self._reserve(report_type, report_key, force)
            if row_id is None:
                return {"status": "skipped", "report_key": report_key}
            try:
                filename, content, caption = document_factory()
                message_id = self.client.send_document(filename, content, caption=caption)
                digest = hashlib.sha256(content).hexdigest()
                with self.session_factory() as session:
                    row = session.get(WBTelegramDelivery, row_id)
                    row.status = "sent"
                    row.sent_at = datetime.now(timezone.utc)
                    row.message_hash = digest
                    row.telegram_message_ids = [message_id]
                    row.error_text = None
                    session.commit()
                return {
                    "status": "sent",
                    "report_key": report_key,
                    "filename": filename,
                    "message_ids": [message_id],
                }
            except Exception as exc:
                report_exception(exc, phase="telegram_document", details={"report_type": report_type, "report_key": report_key})
                with self.session_factory() as session:
                    row = session.get(WBTelegramDelivery, row_id)
                    if row:
                        row.status = "error"
                        row.error_text = str(exc)[:4000]
                        session.commit()
                raise

    def send_text_content(
        self,
        report_type: str,
        report_key: str,
        text_factory: Callable[[], str],
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        """Send arbitrary generated text with the same durable deduplication ledger."""
        with sync_context(cycle_id=None, task=f"telegram_{report_type}"):
            row_id = self._reserve(report_type, report_key, force)
            if row_id is None:
                return {"status": "skipped", "report_key": report_key}
            try:
                content = text_factory()
                message_ids = self.client.send_text(content)
                with self.session_factory() as session:
                    row = session.get(WBTelegramDelivery, row_id)
                    row.status = "sent"
                    row.sent_at = datetime.now(timezone.utc)
                    row.message_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                    row.telegram_message_ids = message_ids
                    row.error_text = None
                    session.commit()
                return {"status": "sent", "report_key": report_key, "message_ids": message_ids}
            except Exception as exc:
                report_exception(exc, phase="telegram_text", details={"report_type": report_type, "report_key": report_key})
                with self.session_factory() as session:
                    row = session.get(WBTelegramDelivery, row_id)
                    if row:
                        row.status = "error"
                        row.error_text = str(exc)[:4000]
                        session.commit()
                raise

    def _reserve(self, report_type: str, report_key: str, force: bool) -> int | None:
        with self.session_factory() as session:
            existing = session.query(WBTelegramDelivery).filter_by(report_key=report_key).one_or_none()
            if existing and not force and existing.status in {"pending", "sent"}:
                return None
            if existing:
                existing.status = "pending"; existing.error_text = None; existing.created_at = datetime.now(timezone.utc)
                session.commit(); return int(existing.id)
            row = WBTelegramDelivery(report_key=report_key, report_type=report_type, chat_id=self.client.chat_id, status="pending", telegram_message_ids=[], created_at=datetime.now(timezone.utc))
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback(); return None
            return int(row.id)
