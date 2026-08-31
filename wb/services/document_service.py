from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from app.config import WB_DOCUMENT_DOWNLOAD_LIMIT
from app.db import SessionLocal
from app.models import (
    WBDocument,
    WBDocumentCategory,
    WBDocumentFile,
    WBFinanceBalanceSnapshot,
)
from wb.document_storage import DocumentStorage, StoredDocument
from wb.documents import DocumentsAPI
from wb.finances import FinancesAPI


logger = logging.getLogger(__name__)


def _dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
    except ValueError:
        return None


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _extensions(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    result: list[str] = []
    for item in values:
        if isinstance(item, dict):
            item = item.get("extension") or item.get("name")
        if not isinstance(item, str):
            continue
        extension = item.strip().lstrip(".").lower()
        if extension and extension not in result:
            result.append(extension)
    return result


class DocumentService:
    def __init__(
        self,
        documents_api: DocumentsAPI | None = None,
        finances_api: FinancesAPI | None = None,
        storage: DocumentStorage | None = None,
        session_factory: Any = SessionLocal,
    ) -> None:
        self.api = documents_api or DocumentsAPI()
        self.finances_api = finances_api or FinancesAPI()
        self.storage = storage or DocumentStorage()
        self.session_factory = session_factory

    def sync_categories(self, locale: str = "ru") -> int:
        items = self.api.categories(locale=locale)
        saved = 0
        with self.session_factory() as session:
            existing = {row.name: row for row in session.query(WBDocumentCategory).all()}
            for item in items:
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                row = existing.get(name)
                if row is None:
                    row = WBDocumentCategory(name=name, raw_data=item)
                    session.add(row)
                    existing[name] = row
                row.title = item.get("title")
                row.raw_data = item
                saved += 1
            session.commit()
        return saved

    def sync_documents(
        self,
        begin_time: date | None = None,
        end_time: date | None = None,
        locale: str = "ru",
    ) -> int:
        items = self.api.list(begin_time, end_time, locale=locale)
        saved = 0
        with self.session_factory() as session:
            existing = {row.service_name: row for row in session.query(WBDocument).all()}
            for item in items:
                service_name = str(item.get("serviceName") or "").strip()
                if not service_name:
                    continue
                row = existing.get(service_name)
                if row is None:
                    row = WBDocument(service_name=service_name, raw_data=item, extensions=[])
                    session.add(row)
                    existing[service_name] = row
                row.category = item.get("name")
                row.title = item.get("category")
                row.extensions = _extensions(item.get("extensions") or item.get("extension"))
                row.document_created_at = _dt(
                    item.get("creationTime")
                    or item.get("createTime")
                    or item.get("createdAt")
                    or item.get("date")
                )
                row.viewed = item.get("viewed") if isinstance(item.get("viewed"), bool) else None
                row.raw_data = item
                row.fetched_at = datetime.now(timezone.utc)
                saved += 1
            session.commit()
        return saved

    def sync_balance(self) -> dict[str, Any]:
        data = self.finances_api.balance()
        with self.session_factory() as session:
            session.add(WBFinanceBalanceSnapshot(
                currency=data.get("currency"),
                current=_decimal(data.get("current")),
                for_withdraw=_decimal(data.get("for_withdraw")),
                raw_data=data,
            ))
            session.commit()
        return data

    def download_document(self, service_name: str, extension: str) -> StoredDocument:
        service_name = service_name.strip()
        extension = extension.strip().lstrip(".").lower()
        payload = self.api.download(service_name, extension)
        stored = self.storage.save(
            service_name,
            payload,
            expected_extension=extension,
        )
        normalized_extension = stored.extension.lower()
        with self.session_factory() as session:
            row = session.query(WBDocument).filter(WBDocument.service_name == service_name).one_or_none()
            if row is None:
                row = WBDocument(
                    service_name=service_name,
                    extensions=[normalized_extension],
                    raw_data={},
                )
                session.add(row)
                session.flush()
            elif normalized_extension not in _extensions(row.extensions):
                row.extensions = [*_extensions(row.extensions), normalized_extension]
            file_row = session.query(WBDocumentFile).filter_by(
                document_id=row.id,
                extension=normalized_extension,
            ).one_or_none()
            if file_row is None:
                file_row = WBDocumentFile(
                    document_id=row.id,
                    extension=normalized_extension,
                    local_path=stored.relative_path,
                    file_name=stored.file_name,
                    file_size=stored.size,
                    file_sha256=stored.sha256,
                    downloaded_at=datetime.now(timezone.utc),
                )
                session.add(file_row)
            else:
                file_row.local_path = stored.relative_path
                file_row.file_name = stored.file_name
                file_row.file_size = stored.size
                file_row.file_sha256 = stored.sha256
                file_row.downloaded_at = datetime.now(timezone.utc)
            session.commit()
        return stored

    def sync_missing_files(self, limit: int = WB_DOCUMENT_DOWNLOAD_LIMIT) -> dict[str, Any]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self.session_factory() as session:
            rows = session.query(WBDocument).order_by(WBDocument.document_created_at.desc()).all()
            pending: list[tuple[str, str]] = []
            for row in rows:
                files_by_extension = {file.extension.lower(): file for file in row.files}
                for extension in _extensions(row.extensions):
                    file_row = files_by_extension.get(extension)
                    if file_row and self.storage.verify(
                        file_row.local_path,
                        size=file_row.file_size,
                        sha256=file_row.file_sha256,
                    ):
                        continue
                    pending.append((row.service_name, extension))
            pending = pending[:limit]

        downloaded = 0
        failed = 0
        errors: list[str] = []
        for service_name, extension in pending:
            try:
                self.download_document(service_name, extension)
                downloaded += 1
            except Exception as exc:
                failed += 1
                error = f"{service_name}.{extension}: {type(exc).__name__}: {exc}"
                errors.append(error)
                logger.exception("WB document download failed: %s.%s", service_name, extension)
        return {
            "selected": len(pending),
            "downloaded": downloaded,
            "failed": failed,
            "errors": errors,
        }

    def sync_all(
        self,
        begin_time: date | None = None,
        end_time: date | None = None,
        locale: str = "ru",
        download_limit: int = WB_DOCUMENT_DOWNLOAD_LIMIT,
    ) -> dict[str, Any]:
        return {
            "categories": self.sync_categories(locale),
            "documents": self.sync_documents(begin_time, end_time, locale),
            "balance": self.sync_balance(),
            "files": self.sync_missing_files(download_limit),
        }
