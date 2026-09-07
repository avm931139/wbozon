from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from sqlalchemy import func, select

from app.config import (
    OZON_FINANCE_POSTING_BATCH_LIMIT,
    OZON_FINANCE_POSTING_REQUEST_PAUSE_SECONDS,
    OZON_HISTORY_FROM,
    OZON_SYNC_OVERLAP_DAYS,
)
from app.db import SessionLocal
from app.models import (
    OzonFinanceAccrual,
    OzonFinanceAccrualType,
    OzonFinancePostingAccrual,
)
from ozon.business_time import ozon_today
from ozon.finances import OzonFinancesAPI


logger = logging.getLogger(__name__)


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _decimal(value: Any) -> Decimal:
    if isinstance(value, dict):
        value = value.get("amount")
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


def _source_hash(posting_number: str, row: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"posting_number": posting_number, "accrual": row},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _operation_id(item: dict[str, Any]) -> str:
    identifier = item.get("operation_id") or item.get("accrual_id")
    if identifier not in (None, ""):
        return str(identifier)
    canonical = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return f"generated:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


class OzonFinanceSyncService:
    """Persist the daily accrual ledger and its per-posting drill-down."""

    def __init__(
        self,
        *,
        api: OzonFinancesAPI | None = None,
        session_factory: Callable[..., Any] = SessionLocal,
        history_from: date | None = None,
        today: Callable[[], date] = ozon_today,
        posting_batch_limit: int = OZON_FINANCE_POSTING_BATCH_LIMIT,
        request_pause_seconds: float = OZON_FINANCE_POSTING_REQUEST_PAUSE_SECONDS,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if posting_batch_limit < 1 or request_pause_seconds < 0:
            raise ValueError("invalid Ozon finance posting synchronization settings")
        self.api = api or OzonFinancesAPI()
        self.session_factory = session_factory
        self.history_from = history_from or date.fromisoformat(OZON_HISTORY_FROM)
        self.today = today
        self.posting_batch_limit = posting_batch_limit
        self.request_pause_seconds = request_pause_seconds
        self.sleeper = sleeper

    def sync_types(self) -> int:
        rows = self.api.accrual_types()
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            for item in rows:
                type_id = item.get("id")
                if type_id is None:
                    continue
                row = session.get(OzonFinanceAccrualType, int(type_id))
                if row is None:
                    row = OzonFinanceAccrualType(type_id=int(type_id), name="", raw_data={}, fetched_at=now)
                    session.add(row)
                row.name = str(item.get("name") or f"type_{type_id}")
                row.description = item.get("description") or None
                row.raw_data = item
                row.fetched_at = now
            session.commit()
        return len(rows)

    def sync_daily(self) -> tuple[int, set[str]]:
        with self.session_factory() as session:
            latest = session.query(func.max(OzonFinanceAccrual.accrual_date)).scalar()
        start = max(self.history_from, latest - timedelta(days=OZON_SYNC_OVERLAP_DAYS)) if latest else self.history_from
        end = self.today()
        rows = self.api.accruals_by_day(start, end)
        now = datetime.now(timezone.utc)
        posting_numbers: set[str] = set()
        saved = 0
        with self.session_factory() as session:
            for item in rows:
                day = _date(item.get("date") or item.get("accrual_date"))
                if day is None:
                    continue
                operation_id = _operation_id(item)
                category = str(item.get("accrued_category") or item.get("accrual_type") or item.get("type") or "unknown")
                row = session.query(OzonFinanceAccrual).filter_by(
                    accrual_date=day,
                    operation_id=operation_id,
                    accrual_type=category,
                ).one_or_none()
                if row is None:
                    row = OzonFinanceAccrual(
                        accrual_date=day,
                        operation_id=operation_id,
                        accrual_type=category,
                        raw_data=item,
                        fetched_at=now,
                    )
                    session.add(row)
                total = item.get("total_amount", item.get("amount", 0))
                unit_number = str(item.get("unit_number") or item.get("posting_number") or "").strip()
                row.accrual_name = item.get("accrual_name") or item.get("type_name")
                row.posting_number = unit_number or None
                row.amount = _decimal(total)
                row.currency = total.get("currency") if isinstance(total, dict) else item.get("currency")
                row.raw_data = item
                row.fetched_at = now
                if category == "POSTING" and unit_number:
                    posting_numbers.add(unit_number)
                saved += 1
            session.commit()
        return saved, posting_numbers

    def _missing_postings(self, limit: int) -> list[str]:
        with self.session_factory() as session:
            known = select(OzonFinancePostingAccrual.posting_number).distinct()
            rows = session.query(OzonFinanceAccrual.posting_number).filter(
                OzonFinanceAccrual.posting_number.is_not(None),
                ~OzonFinanceAccrual.posting_number.in_(known),
            ).distinct().limit(limit).all()
        return [str(row[0]) for row in rows if row[0]]

    def sync_postings(self, current: set[str]) -> dict[str, int]:
        capacity = self.posting_batch_limit * 200
        candidates = list(sorted(current))[:capacity]
        if len(candidates) < capacity:
            seen = set(candidates)
            candidates.extend(
                value for value in self._missing_postings(capacity - len(candidates))
                if value not in seen
            )
        batches = [candidates[index:index + 200] for index in range(0, len(candidates), 200)]
        saved = 0
        returned_postings = 0
        for index, batch in enumerate(batches):
            if index and self.request_pause_seconds:
                self.sleeper(self.request_pause_seconds)
            groups = self.api.accruals_by_postings(batch)
            now = datetime.now(timezone.utc)
            with self.session_factory() as session:
                for group in groups:
                    posting_number = str(group.get("posting_number") or "").strip()
                    accruals = group.get("accruals")
                    if not posting_number or not isinstance(accruals, list):
                        continue
                    returned_postings += 1
                    session.query(OzonFinancePostingAccrual).filter_by(
                        posting_number=posting_number
                    ).delete(synchronize_session=False)
                    for item in accruals:
                        if not isinstance(item, dict) or item.get("type_id") is None:
                            continue
                        type_id = int(item["type_id"])
                        if session.get(OzonFinanceAccrualType, type_id) is None:
                            session.add(OzonFinanceAccrualType(
                                type_id=type_id,
                                name=f"type_{type_id}",
                                description="Type was returned before it appeared in the Ozon dictionary",
                                raw_data={"id": type_id},
                                fetched_at=now,
                            ))
                            session.flush()
                        accrued = item.get("accrued") or {}
                        seller_price = item.get("seller_price")
                        session.add(OzonFinancePostingAccrual(
                            source_hash=_source_hash(posting_number, item),
                            posting_number=posting_number,
                            accrual_date=_date(item.get("accrual_date")),
                            type_id=type_id,
                            sku=int(item["sku"]) if item.get("sku") is not None else None,
                            quantity=int(item["quantity"]) if item.get("quantity") is not None else None,
                            seller_price=_decimal(seller_price) if seller_price is not None else None,
                            accrued=_decimal(accrued),
                            currency=accrued.get("currency") if isinstance(accrued, dict) else None,
                            raw_data=item,
                            fetched_at=now,
                        ))
                        saved += 1
                session.commit()
        return {"requested": len(candidates), "returned": returned_postings, "rows": saved, "batches": len(batches)}

    def sync_all(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        try:
            result["types"] = self.sync_types()
        except Exception as exc:
            logger.exception("Ozon finance accrual type sync failed")
            result["types_error"] = f"{type(exc).__name__}: {exc}"
        try:
            daily, current = self.sync_daily()
            result["daily"] = daily
        except Exception as exc:
            logger.exception("Ozon finance daily accrual sync failed")
            result["daily_error"] = f"{type(exc).__name__}: {exc}"
            return result
        try:
            result["postings"] = self.sync_postings(current)
        except Exception as exc:
            logger.exception("Ozon finance posting accrual sync failed")
            result["postings_error"] = f"{type(exc).__name__}: {exc}"
        return result
