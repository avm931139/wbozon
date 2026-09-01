from __future__ import annotations

import calendar
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from app.config import (
    OZON_ACCOUNTING_DOWNLOAD_LIMIT,
    OZON_ACCOUNTING_HISTORY_FROM,
)
from app.db import SessionLocal
from app.models import (
    OzonAccountingReport,
    OzonAccountingReportFile,
    OzonAccountingReportRequest,
    OzonAccountingSnapshot,
)
from ozon.accounting import ASYNC_FINANCE_REPORTS, OzonAccountingAPI
from ozon.accounting_storage import OzonAccountingStorage, OzonReportDownloader
from ozon.business_time import ozon_today
from ozon.exceptions import OzonHTTPError


logger = logging.getLogger(__name__)
REALIZATION_POSTING_REPORT = "REALIZATION_POSTING_REPORT"
FINANCE_REPORT_TYPES = {*ASYNC_FINANCE_REPORTS, REALIZATION_POSTING_REPORT}


def _dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
    except ValueError:
        return None


def _is_not_found(exc: Exception) -> bool:
    return isinstance(exc, OzonHTTPError) and "HTTP 404" in str(exc)


def _month_end(value: date) -> date:
    return value.replace(day=calendar.monthrange(value.year, value.month)[1])


def _next_month(value: date) -> date:
    return date(value.year + (value.month == 12), 1 if value.month == 12 else value.month + 1, 1)


def _complete_months(history_from: date, today: date) -> list[tuple[date, date]]:
    cursor = history_from.replace(day=1)
    current_month = today.replace(day=1)
    result: list[tuple[date, date]] = []
    while cursor < current_month:
        result.append((cursor, _month_end(cursor)))
        cursor = _next_month(cursor)
    return result


def _closed_cash_flow_periods(history_from: date, today: date) -> list[tuple[date, date]]:
    cursor = history_from.replace(day=1)
    result: list[tuple[date, date]] = []
    while cursor <= today:
        month_end = _month_end(cursor)
        first_start = cursor
        first_end = cursor.replace(day=15)
        if first_start <= first_end < today:
            result.append((first_start, first_end))
        second_start = cursor.replace(day=16)
        if second_start <= month_end < today:
            result.append((second_start, month_end))
        cursor = _next_month(cursor)
    return result


class OzonAccountingService:
    """Synchronize Ozon Finance documents independently from accrual accounting."""

    def __init__(
        self,
        *,
        api: OzonAccountingAPI | None = None,
        downloader: OzonReportDownloader | None = None,
        storage: OzonAccountingStorage | None = None,
        session_factory: Callable[..., Any] = SessionLocal,
        history_from: date | None = None,
        today: Callable[[], date] = ozon_today,
    ) -> None:
        self.api = api or OzonAccountingAPI()
        self.downloader = downloader or OzonReportDownloader()
        self.storage = storage or OzonAccountingStorage()
        self.session_factory = session_factory
        self.history_from = history_from or date.fromisoformat(OZON_ACCOUNTING_HISTORY_FROM)
        self.today = today

    def request_missing_reports(self) -> dict[str, Any]:
        periods = _complete_months(self.history_from, self.today())
        requested = 0
        unavailable = 0
        skipped = 0
        errors: list[str] = []
        for period_start, period_end in periods:
            for report_type in sorted(FINANCE_REPORT_TYPES):
                with self.session_factory() as session:
                    exists = session.query(OzonAccountingReportRequest.id).filter_by(
                        report_type=report_type,
                        period_start=period_start,
                    ).first()
                if exists:
                    skipped += 1
                    continue
                try:
                    payload = self.api.create_monthly_report(report_type, period_start)
                    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
                    code = str(result.get("code") or "").strip()
                    if not code:
                        raise ValueError("Ozon report response has no code")
                    now = datetime.now(timezone.utc)
                    with self.session_factory() as session:
                        session.add(OzonAccountingReportRequest(
                            report_type=report_type,
                            period_start=period_start,
                            period_end=period_end,
                            report_code=code,
                            status="requested",
                            raw_data=payload,
                            requested_at=now,
                            updated_at=now,
                        ))
                        session.commit()
                    requested += 1
                except Exception as exc:
                    if _is_not_found(exc):
                        now = datetime.now(timezone.utc)
                        with self.session_factory() as session:
                            session.add(OzonAccountingReportRequest(
                                report_type=report_type,
                                period_start=period_start,
                                period_end=period_end,
                                report_code=f"NOT_FOUND:{report_type}:{period_start:%Y-%m}",
                                status="not_found",
                                raw_data={
                                    "available": False,
                                    "reason": str(exc),
                                },
                                requested_at=now,
                                updated_at=now,
                            ))
                            session.commit()
                        unavailable += 1
                        logger.info(
                            "Ozon accounting report is absent for this period: %s:%s",
                            report_type,
                            period_start.strftime("%Y-%m"),
                        )
                        continue
                    error = f"{report_type}:{period_start:%Y-%m}: {type(exc).__name__}: {exc}"
                    logger.exception("Ozon accounting report request failed: %s", error)
                    errors.append(error)
        return {
            "requested": requested,
            "unavailable": unavailable,
            "skipped": skipped,
            "failed": len(errors),
            "errors": errors,
        }

    def sync_report_registry(self) -> int:
        reports = self.api.reports("ALL")
        with self.session_factory() as session:
            requested_codes = {
                row[0]
                for row in session.query(OzonAccountingReportRequest.report_code).all()
            }
        selected = [
            item for item in reports
            if item.get("report_type") in FINANCE_REPORT_TYPES or item.get("code") in requested_codes
        ]
        known = {str(item.get("code") or "") for item in selected}
        with self.session_factory() as session:
            pending_codes = [
                row.report_code
                for row in session.query(OzonAccountingReportRequest).filter(
                    OzonAccountingReportRequest.status.notin_(("success", "failed", "not_found")),
                    OzonAccountingReportRequest.report_code.notin_(known or {""}),
                ).all()
            ]
        for code in pending_codes:
            try:
                selected.append(self.api.report_info(code))
            except Exception:
                logger.info("Ozon report %s is not available through report/info yet", code)

        saved = 0
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            requests_by_code = {
                row.report_code: row
                for row in session.query(OzonAccountingReportRequest).all()
            }
            for item in selected:
                code = str(item.get("code") or "").strip()
                if not code:
                    continue
                row = session.query(OzonAccountingReport).filter_by(code=code).one_or_none()
                if row is None:
                    row = OzonAccountingReport(
                        code=code,
                        report_type=str(
                            item.get("report_type")
                            or (requests_by_code[code].report_type if code in requests_by_code else "unknown")
                        ),
                        status=str(item.get("status") or "unknown"),
                        params={},
                        raw_data=item,
                        fetched_at=now,
                        updated_at=now,
                    )
                    session.add(row)
                request = requests_by_code.get(code)
                row.report_type = str(item.get("report_type") or (request.report_type if request else "unknown"))
                row.status = str(item.get("status") or "unknown")
                row.error = item.get("error") or None
                row.file_url = item.get("file") or None
                row.params = item.get("params") if isinstance(item.get("params"), dict) else {}
                row.report_created_at = _dt(item.get("created_at"))
                row.expires_at = _dt(item.get("expires_at"))
                row.raw_data = item
                row.fetched_at = now
                row.updated_at = now
                if request is not None:
                    request.status = row.status
                    request.updated_at = now
                saved += 1
            session.commit()
        return saved

    def download_ready_files(self, limit: int = OZON_ACCOUNTING_DOWNLOAD_LIMIT) -> dict[str, Any]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self.session_factory() as session:
            reports = session.query(OzonAccountingReport).filter(
                OzonAccountingReport.status == "success",
                OzonAccountingReport.file_url.is_not(None),
            ).order_by(OzonAccountingReport.report_created_at.desc()).all()
            pending: list[tuple[int, str, str, str]] = []
            for report in reports:
                if report.file and self.storage.verify(
                    report.file.local_path,
                    size=report.file.file_size,
                    sha256=report.file.file_sha256,
                ):
                    continue
                pending.append((report.id, report.report_type, report.code, report.file_url))
            pending = pending[:limit]

        downloaded = 0
        errors: list[str] = []
        for report_id, report_type, code, url in pending:
            try:
                payload = self.downloader.download(url)
                stored = self.storage.save(report_type, code, payload)
                with self.session_factory() as session:
                    row = session.query(OzonAccountingReportFile).filter_by(report_id=report_id).one_or_none()
                    if row is None:
                        row = OzonAccountingReportFile(report_id=report_id)
                        session.add(row)
                    row.local_path = stored.relative_path
                    row.file_name = stored.file_name
                    row.file_extension = stored.extension
                    row.content_type = stored.content_type
                    row.file_size = stored.size
                    row.file_sha256 = stored.sha256
                    row.downloaded_at = datetime.now(timezone.utc)
                    session.commit()
                downloaded += 1
            except Exception as exc:
                error = f"{code}: {type(exc).__name__}: {exc}"
                logger.exception("Ozon accounting file download failed: %s", error)
                errors.append(error)
        return {
            "selected": len(pending),
            "downloaded": downloaded,
            "failed": len(errors),
            "errors": errors,
        }

    def sync_json_snapshots(self) -> dict[str, Any]:
        callbacks: list[tuple[str, date, date, Callable[[], dict[str, Any]]]] = []
        for period_start, period_end in _complete_months(self.history_from, self.today()):
            callbacks.extend((
                ("b2b_sales_json", period_start, period_end, lambda start=period_start: self.api.b2b_sales_json(start)),
                ("realization", period_start, period_end, lambda start=period_start: self.api.realization(start)),
                ("products_buyout", period_start, period_end, lambda start=period_start, end=period_end: self.api.products_buyout(start, end)),
            ))
        for period_start, period_end in _closed_cash_flow_periods(self.history_from, self.today()):
            callbacks.append((
                "cash_flow",
                period_start,
                period_end,
                lambda start=period_start, end=period_end: self.api.cash_flow(start, end),
            ))
        balance_end = self.today()
        balance_start = balance_end - timedelta(days=29)
        callbacks.append((
            "balance",
            balance_start,
            balance_end,
            lambda: self.api.balance(balance_start, balance_end),
        ))

        saved = 0
        skipped = 0
        errors: list[str] = []
        for snapshot_type, period_start, period_end, callback in callbacks:
            with self.session_factory() as session:
                exists = session.query(OzonAccountingSnapshot.id).filter_by(
                    snapshot_type=snapshot_type,
                    period_start=period_start,
                    period_end=period_end,
                ).first()
            if exists:
                skipped += 1
                continue
            try:
                payload = callback()
                with self.session_factory() as session:
                    session.add(OzonAccountingSnapshot(
                        snapshot_type=snapshot_type,
                        period_start=period_start,
                        period_end=period_end,
                        raw_data=payload,
                        fetched_at=datetime.now(timezone.utc),
                    ))
                    session.commit()
                saved += 1
            except Exception as exc:
                if _is_not_found(exc):
                    with self.session_factory() as session:
                        session.add(OzonAccountingSnapshot(
                            snapshot_type=snapshot_type,
                            period_start=period_start,
                            period_end=period_end,
                            raw_data={
                                "available": False,
                                "reason": "Ozon returned HTTP 404 for this completed period",
                            },
                            fetched_at=datetime.now(timezone.utc),
                        ))
                        session.commit()
                    saved += 1
                    continue
                error = (
                    f"{snapshot_type}:{period_start}:{period_end}: "
                    f"{type(exc).__name__}: {exc}"
                )
                logger.exception("Ozon accounting snapshot failed: %s", error)
                errors.append(error)
        return {"saved": saved, "skipped": skipped, "failed": len(errors), "errors": errors}

    def sync_all(self, download_limit: int = OZON_ACCOUNTING_DOWNLOAD_LIMIT) -> dict[str, Any]:
        result: dict[str, Any] = {}
        steps = (
            ("requests", self.request_missing_reports),
            ("registry", self.sync_report_registry),
            ("files", lambda: self.download_ready_files(download_limit)),
            ("snapshots", self.sync_json_snapshots),
        )
        for name, callback in steps:
            try:
                value = callback()
                result[name] = value
                if isinstance(value, dict) and value.get("failed"):
                    result[f"{name}_error"] = "; ".join(value.get("errors") or [f"{name} failed"])
            except Exception as exc:
                logger.exception("Ozon accounting step failed: %s", name)
                result[f"{name}_error"] = f"{type(exc).__name__}: {exc}"
        return result
