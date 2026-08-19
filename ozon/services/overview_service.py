from __future__ import annotations

import hashlib
import json
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from sqlalchemy import func

from app.config import OZON_HISTORY_FROM, OZON_SUPPLY_REQUEST_PAUSE_SECONDS, OZON_SYNC_OVERLAP_DAYS
from app.db import SessionLocal
from app.models import OzonDailySale, OzonFinanceAccrual, OzonQuestion, OzonReview, OzonSupply
from ozon.analytics import OzonAnalyticsAPI
from ozon.communications import OzonCommunicationsAPI
from ozon.finances import OzonFinancesAPI
from ozon.supplies import OzonSuppliesAPI
from ozon.business_time import ozon_today


def _dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _date(value: Any) -> date | None:
    parsed = _dt(value)
    if parsed:
        return parsed.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _decimal(value: Any) -> Decimal:
    try:
        if isinstance(value, dict):
            value = value.get("amount", 0)
        return Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        return Decimal(0)


def _metric(row: dict[str, Any], name: str) -> Any:
    metrics = row.get("metrics", [])
    names = row.get("metric_names", [])
    if isinstance(metrics, dict):
        return metrics.get(name, 0)
    if isinstance(names, list) and name in names and isinstance(metrics, list):
        return metrics[names.index(name)]
    return row.get(name, 0)


def _dimension(row: dict[str, Any], name: str) -> dict[str, Any]:
    for item in row.get("dimensions") or []:
        if isinstance(item, dict) and (item.get("id") == name or item.get("name") == name):
            return item
    return {}


def _finance_operation_id(item: dict[str, Any]) -> str:
    """Return the API identifier or a stable fallback for legacy responses."""
    identifier = item.get("operation_id") or item.get("accrual_id")
    if identifier not in (None, ""):
        return str(identifier)
    canonical = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return f"generated:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


class OzonOverviewService:
    def __init__(
        self,
        *,
        history_from: date | None = None,
        today: Callable[[], date] = ozon_today,
        supply_request_pause_seconds: float = OZON_SUPPLY_REQUEST_PAUSE_SECONDS,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if supply_request_pause_seconds < 0:
            raise ValueError("OZON_SUPPLY_REQUEST_PAUSE_SECONDS must not be negative")
        self.history_from = history_from or date.fromisoformat(OZON_HISTORY_FROM)
        self.today = today
        self.supply_request_pause_seconds = supply_request_pause_seconds
        self.sleeper = sleeper
        self.analytics = OzonAnalyticsAPI()
        self.communications = OzonCommunicationsAPI()
        self.finances = OzonFinancesAPI()
        self.supplies = OzonSuppliesAPI()

    def sync_supplies(self) -> int:
        rows = self.supplies.list()
        now = datetime.now(timezone.utc)
        saved = 0
        with SessionLocal() as session:
            for index, item in enumerate(rows):
                identifier = item.get("supply_order_id")
                if identifier is None:
                    continue
                if index and self.supply_request_pause_seconds:
                    self.sleeper(self.supply_request_pause_seconds)
                detail = self.supplies.get(int(identifier))
                data = {**item, **detail}
                created = _dt(data.get("created_date") or data.get("created_at"))
                if created is not None and created.date() < self.history_from:
                    continue
                row = session.query(OzonSupply).filter_by(supply_order_id=int(identifier)).one_or_none()
                if row is None:
                    row = OzonSupply(supply_order_id=int(identifier), raw_data=data, fetched_at=now)
                    session.add(row)
                supplies = data.get("supplies") or []
                first_supply = supplies[0] if supplies and isinstance(supplies[0], dict) else {}
                warehouse = data.get("supply_warehouse") or first_supply.get("storage_warehouse") or data.get("drop_off_warehouse") or {}
                slot = data.get("local_timeslot") or data.get("timeslot") or {}
                row.supply_order_number = data.get("supply_order_number") or data.get("order_number")
                row.state = data.get("state") or data.get("status")
                row.created_at = created
                row.supply_date_from = _dt(slot.get("from") or data.get("preferred_supply_date_from"))
                row.supply_date_to = _dt(slot.get("to") or data.get("preferred_supply_date_to"))
                row.warehouse_id = warehouse.get("warehouse_id")
                row.warehouse_name = warehouse.get("name")
                row.total_items_count = int(data.get("total_items_count") or len(supplies))
                row.total_quantity = int(data.get("total_quantity") or 0)
                row.items = data.get("items") or data.get("bundle") or supplies
                row.raw_data = data; row.fetched_at = now
                saved += 1
            session.commit()
        return saved

    def sync_communications(self) -> dict[str, int]:
        reviews_error = questions_error = None
        try: reviews = self.communications.reviews()
        except Exception as exc: reviews, reviews_error = [], f"{type(exc).__name__}: {exc}"
        try: questions = self.communications.questions()
        except Exception as exc: questions, questions_error = [], f"{type(exc).__name__}: {exc}"
        now = datetime.now(timezone.utc)
        with SessionLocal() as session:
            for item in reviews:
                identifier = str(item.get("id") or item.get("review_id") or "")
                if not identifier: continue
                row = session.query(OzonReview).filter_by(review_id=identifier).one_or_none()
                if row is None: row = OzonReview(review_id=identifier, raw_data=item, fetched_at=now); session.add(row)
                row.sku = item.get("sku"); row.text = item.get("text") or item.get("content") or ""
                row.rating = item.get("rating") or item.get("score"); row.status = item.get("status")
                row.is_answered = bool(item.get("is_answered") or item.get("comments_count"))
                row.created_at = _dt(item.get("published_at") or item.get("created_at")); row.comments = item.get("comments") or []
                row.raw_data = item; row.fetched_at = now
            for item in questions:
                identifier = str(item.get("id") or item.get("question_id") or "")
                if not identifier: continue
                row = session.query(OzonQuestion).filter_by(question_id=identifier).one_or_none()
                if row is None: row = OzonQuestion(question_id=identifier, raw_data=item, fetched_at=now); session.add(row)
                row.sku = item.get("sku"); row.text = item.get("text") or ""; row.status = item.get("status")
                row.answers = item.get("answers") or []; row.is_answered = bool(row.answers or item.get("is_answered"))
                row.created_at = _dt(item.get("created_at") or item.get("published_at")); row.raw_data = item; row.fetched_at = now
            session.commit()
        result = {"reviews": len(reviews), "questions": len(questions)}
        if reviews_error: result["reviews_error"] = reviews_error
        if questions_error: result["questions_error"] = questions_error
        return result

    def sync_daily_sales(self) -> int:
        start = self._incremental_start(OzonDailySale.sale_date)
        end = self.today() - timedelta(days=1)
        if start > end: return 0
        rows = self.analytics.daily_sales(start, end)
        now = datetime.now(timezone.utc)
        with SessionLocal() as session:
            for item in rows:
                dimensions = item.get("dimensions") or []
                day_dim = dimensions[0] if len(dimensions) > 0 and isinstance(dimensions[0], dict) else {}
                sku_dim = dimensions[1] if len(dimensions) > 1 and isinstance(dimensions[1], dict) else {}
                day = _date(day_dim.get("id") or day_dim.get("name") or item.get("date"))
                sku_value = sku_dim.get("id") or item.get("sku")
                if day is None or sku_value in (None, ""): continue
                sku = int(sku_value)
                row = session.query(OzonDailySale).filter_by(sale_date=day, sku=sku).one_or_none()
                if row is None: row = OzonDailySale(sale_date=day, sku=sku, raw_data=item, fetched_at=now); session.add(row)
                row.product_name = sku_dim.get("name") or item.get("product_name"); row.offer_id = item.get("offer_id")
                row.revenue = _decimal(_metric(item, "revenue")); row.ordered_units = int(_metric(item, "ordered_units") or 0)
                row.delivered_units = int(_metric(item, "delivered_units") or 0); row.returns = int(_metric(item, "returns") or 0)
                row.cancellations = int(_metric(item, "cancellations") or 0); row.raw_data = item; row.fetched_at = now
            session.commit()
        return len(rows)

    def sync_finances(self) -> int:
        start = self._incremental_start(OzonFinanceAccrual.accrual_date)
        end = self.today()
        count = 0; cursor = start
        now = datetime.now(timezone.utc)
        with SessionLocal() as session:
            while cursor <= end:
                chunk_end = min(end, cursor + timedelta(days=30))
                for item in self.finances.accruals_by_day(cursor, chunk_end):
                    day = _date(item.get("date") or item.get("accrual_date"))
                    if day is None: continue
                    operation_id = _finance_operation_id(item)
                    kind = str(item.get("accrual_type") or item.get("type") or item.get("accrued_category") or "unknown")
                    row = session.query(OzonFinanceAccrual).filter_by(accrual_date=day, operation_id=operation_id, accrual_type=kind).one_or_none()
                    if row is None: row = OzonFinanceAccrual(accrual_date=day, operation_id=operation_id, accrual_type=kind, raw_data=item, fetched_at=now); session.add(row)
                    posting = item.get("posting") or {}; total = item.get("amount", item.get("total_amount", 0))
                    row.accrual_name = item.get("accrual_name") or item.get("type_name"); row.posting_number = posting.get("posting_number") or item.get("posting_number")
                    row.amount = _decimal(total); row.currency = total.get("currency") if isinstance(total, dict) else item.get("currency")
                    row.raw_data = item; row.fetched_at = now; count += 1
                cursor = chunk_end + timedelta(days=1)
            session.commit()
        return count

    def _incremental_start(self, column: Any) -> date:
        with SessionLocal() as session: latest = session.query(func.max(column)).scalar()
        return max(self.history_from, latest - timedelta(days=OZON_SYNC_OVERLAP_DAYS)) if latest else self.history_from

    @staticmethod
    def sales_report(date_from: date, date_to: date) -> dict[str, Any]:
        if date_from > date_to: raise ValueError("date_from must not be later than date_to")
        with SessionLocal() as session:
            rows = session.query(OzonDailySale).filter(OzonDailySale.sale_date.between(date_from, date_to)).all()
        return {"period": {"from": date_from.isoformat(), "to": date_to.isoformat()}, "days": len({x.sale_date for x in rows}),
                "ordered_units": sum(x.ordered_units for x in rows), "delivered_units": sum(x.delivered_units for x in rows),
                "returns": sum(x.returns for x in rows), "cancellations": sum(x.cancellations for x in rows),
                "revenue": str(sum((x.revenue for x in rows), Decimal(0)))}

    @staticmethod
    def finance_report(date_from: date, date_to: date) -> dict[str, Any]:
        with SessionLocal() as session:
            rows = session.query(OzonFinanceAccrual).filter(OzonFinanceAccrual.accrual_date.between(date_from, date_to)).all()
        by_type: dict[str, Decimal] = {}
        for row in rows:
            by_type[row.accrual_type] = by_type.get(row.accrual_type, Decimal(0)) + row.amount
        return {"operations": len(rows), "total": str(sum((x.amount for x in rows), Decimal(0))),
                "by_type": {key: str(value) for key, value in sorted(by_type.items())}}

    @classmethod
    def report(cls, date_from: date, date_to: date) -> dict[str, Any]:
        from ozon.performance.service import OzonPerformanceService
        return {"sales": cls.sales_report(date_from, date_to), "finance": cls.finance_report(date_from, date_to), "advertising": OzonPerformanceService.summary(date_from, date_to)}

    @classmethod
    def month_report(cls, year: int, month: int) -> dict[str, Any]:
        start = date(year, month, 1); end = (date(year + (month == 12), 1 if month == 12 else month + 1, 1) - timedelta(days=1))
        return cls.report(start, min(end, ozon_today() - timedelta(days=1)))
