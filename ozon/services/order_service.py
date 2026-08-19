from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.config import OZON_ORDER_LOOKBACK_DAYS
from app.db import SessionLocal
from app.models import OzonPosting
from ozon.orders import OzonOrdersAPI
from ozon.repositories.order_repository import OzonPostingRepository


def _datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class OzonOrderService:
    def __init__(self, api: OzonOrdersAPI | None = None, *, session_factory: Callable[..., Any] = SessionLocal) -> None:
        self.api = api or OzonOrdersAPI()
        self.session_factory = session_factory

    def sync_recent(self, *, lookback_days: int = OZON_ORDER_LOOKBACK_DAYS) -> dict[str, int]:
        until = datetime.now(timezone.utc)
        since = until - timedelta(days=lookback_days)
        fbs = self.api.fbs_list(since=since, until=until)
        fbo = self.api.fbo_list(since=since, until=until)
        self._save(fbs, "fbs")
        self._save(fbo, "fbo")
        return {"fbs": len(fbs), "fbo": len(fbo)}

    def _save(self, postings: list[dict[str, Any]], scheme: str) -> None:
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            repository = OzonPostingRepository(session)
            for item in postings:
                number = item.get("posting_number")
                if not number:
                    continue
                row = repository.get(str(number), scheme)
                if row is None:
                    row = OzonPosting(posting_number=str(number), scheme=scheme, raw_data=item, products=[], created_at=now, updated_at=now)
                    session.add(row)
                row.order_id = item.get("order_id")
                row.order_number = item.get("order_number")
                row.status = item.get("status")
                row.substatus = item.get("substatus")
                row.in_process_at = _datetime(item.get("in_process_at"))
                row.shipment_date = _datetime(item.get("shipment_date"))
                row.products = item.get("products") or []
                row.analytics_data = item.get("analytics_data")
                row.financial_data = item.get("financial_data")
                row.raw_data = item
                row.updated_at = now
            session.commit()
