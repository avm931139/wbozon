from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app.config import (
    YANDEX_MARKET_AD_POLL_ATTEMPTS,
    YANDEX_MARKET_AD_POLL_SECONDS,
    YANDEX_MARKET_BUSINESS_ID,
    YANDEX_MARKET_HISTORY_FROM,
    YANDEX_MARKET_TIMEZONE,
)
from app.db import SessionLocal
from app.models import YandexMarketBusiness, YandexMarketFinanceTransaction
from yandex_market.finance import YandexMarketFinanceAPI


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%d.%m.%Y %H:%M").replace(
            tzinfo=ZoneInfo(YANDEX_MARKET_TIMEZONE)
        )
    except ValueError:
        return None


class YandexMarketFinanceService:
    OVERLAP_DAYS = 7
    CHUNK_DAYS = 90

    def __init__(
        self,
        api: YandexMarketFinanceAPI | None = None,
        *,
        session_factory: Callable[..., Any] = SessionLocal,
        business_id: int | None = YANDEX_MARKET_BUSINESS_ID,
    ) -> None:
        self.api = api or YandexMarketFinanceAPI()
        self.session_factory = session_factory
        self.business_id = business_id

    def sync(self) -> dict[str, Any]:
        business_id = self._business_id()
        today = datetime.now(ZoneInfo(YANDEX_MARKET_TIMEZONE)).date()
        begin = self._begin(today)
        generated = rows_received = rows_saved = 0
        cursor = begin
        while cursor <= today:
            chunk_end = min(cursor + timedelta(days=self.CHUNK_DAYS - 1), today)
            report_id = self.api.generate_payments(
                business_id=business_id, date_from=cursor, date_to=chunk_end
            )
            generated += 1
            report = self.api.wait(
                report_id,
                attempts=YANDEX_MARKET_AD_POLL_ATTEMPTS,
                pause_seconds=YANDEX_MARKET_AD_POLL_SECONDS,
            )
            rows = [row for _, file_rows in report["rows"] for row in file_rows]
            rows_received += len(rows)
            rows_saved += self._replace(rows, cursor, chunk_end, business_id)
            cursor = chunk_end + timedelta(days=1)
        return {
            "date_from": begin.isoformat(),
            "date_to": today.isoformat(),
            "reports": generated,
            "rows_received": rows_received,
            "rows_saved": rows_saved,
        }

    def _business_id(self) -> int:
        if self.business_id:
            return self.business_id
        with self.session_factory() as session:
            values = [value for value, in session.query(YandexMarketBusiness.business_id).all()]
        if len(values) != 1:
            raise ValueError("configure YANDEX_MARKET_BUSINESS_ID or synchronize one business")
        return int(values[0])

    def _begin(self, today: date) -> date:
        with self.session_factory() as session:
            latest = session.query(YandexMarketFinanceTransaction.transaction_at).order_by(
                YandexMarketFinanceTransaction.transaction_at.desc()
            ).first()
        if latest and latest[0]:
            return max(latest[0].date() - timedelta(days=self.OVERLAP_DAYS), date.fromisoformat(YANDEX_MARKET_HISTORY_FROM))
        return date.fromisoformat(YANDEX_MARKET_HISTORY_FROM)

    def _replace(self, rows: list[dict[str, Any]], begin: date, finish: date, business_id: int) -> int:
        parsed = []
        occurrences: dict[str, int] = {}
        for raw in rows:
            transaction_at = _datetime(raw.get("transactionDate"))
            if transaction_at is None or not begin <= transaction_at.date() <= finish:
                continue
            transaction_type = str(raw.get("transactionType") or "").strip()
            amount = abs(_decimal(raw.get("transactionSum")))
            signed = -amount if transaction_type.casefold() in {"удержание", "retention"} else amount
            canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
            occurrence = occurrences.get(canonical, 0)
            occurrences[canonical] = occurrence + 1
            parsed.append({
                "source_hash": hashlib.sha256(
                    f"{canonical}:{occurrence}".encode()
                ).hexdigest(),
                "business_id": int(raw.get("businessId") or business_id),
                "partner_id": int(raw["partnerId"]) if raw.get("partnerId") is not None else None,
                "transaction_at": transaction_at,
                "transaction_id": str(raw["transactionId"]) if raw.get("transactionId") is not None else None,
                "transaction_type": transaction_type or "unknown",
                "transaction_source": raw.get("transactionSource"),
                "order_id": int(raw["orderId"]) if raw.get("orderId") is not None else None,
                "offer_id": raw.get("shopSku"),
                "product_or_service": raw.get("offerOrServiceName"),
                "quantity": int(raw.get("count") or 0),
                "amount": signed,
                "raw_data": raw,
            })
        start_at = datetime.combine(begin, datetime.min.time(), tzinfo=ZoneInfo(YANDEX_MARKET_TIMEZONE))
        end_at = datetime.combine(finish + timedelta(days=1), datetime.min.time(), tzinfo=ZoneInfo(YANDEX_MARKET_TIMEZONE))
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            session.query(YandexMarketFinanceTransaction).filter(
                YandexMarketFinanceTransaction.transaction_at >= start_at,
                YandexMarketFinanceTransaction.transaction_at < end_at,
            ).delete(synchronize_session=False)
            for values in parsed:
                session.add(YandexMarketFinanceTransaction(**values, fetched_at=now))
            session.commit()
        return len(parsed)
