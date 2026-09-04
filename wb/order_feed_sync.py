from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app.config import WB_LOG_DIR, WB_LOG_LEVEL, WB_ORDER_FEED_LOOKBACK_DAYS, WB_TG_TIMEZONE
from app.db import SessionLocal
from app.models import WBOrderFeedOrder, WBOrderFeedSyncRun, WBProduct
from wb.exceptions import WBParseError
from wb.order_feed import OrderFeedAPI
from wb.sync_logging import configure_wb_logging, install_context_filter


logger = logging.getLogger(__name__)


def _datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


class OrderFeedSyncService:
    def __init__(
        self,
        *,
        api: OrderFeedAPI | None = None,
        session_factory: Callable[..., Any] = SessionLocal,
        timezone_name: str = WB_TG_TIMEZONE,
        lookback_days: int = WB_ORDER_FEED_LOOKBACK_DAYS,
    ) -> None:
        if not 1 <= lookback_days <= 31:
            raise ValueError("WB_ORDER_FEED_LOOKBACK_DAYS must be between 1 and 31")
        self.api = api or OrderFeedAPI()
        self.session_factory = session_factory
        self.timezone = ZoneInfo(timezone_name)
        self.lookback_days = lookback_days

    def sync(self, now: datetime | None = None) -> dict[str, Any]:
        current = now or datetime.now(self.timezone)
        current = current.replace(tzinfo=self.timezone) if current.tzinfo is None else current.astimezone(self.timezone)
        date_from = (current - timedelta(days=self.lookback_days - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        run_id = uuid.uuid4().hex
        with self.session_factory() as session:
            session.add(WBOrderFeedSyncRun(id=run_id, started_at=current, status="running"))
            session.commit()
        try:
            rows = self.api.list(date_from, current)
            upserted = self._persist(rows, current)
            result = {
                "run_id": run_id,
                "status": "completed",
                "period_from": date_from.isoformat(),
                "period_to": current.isoformat(),
                "rows_received": len(rows),
                "rows_upserted": upserted,
            }
            self._finish(run_id, "completed", len(rows), upserted, None, current)
            return result
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            self._finish(run_id, "failed", 0, 0, error, datetime.now(self.timezone))
            logger.exception("WB Order Feed synchronization failed")
            raise

    def _persist(self, rows: list[dict[str, Any]], fetched_at: datetime) -> int:
        valid = []
        for index, item in enumerate(rows):
            srid = str(item.get("srid") or "")
            created_at = _datetime(item.get("createdAt"))
            updated_at = _datetime(item.get("updatedAt"))
            status = item.get("status")
            if not srid or created_at is None or updated_at is None or not status:
                raise WBParseError(
                    f"WB Order Feed row {index} has no srid, createdAt, updatedAt or status"
                )
            if not isinstance(item.get("isMp"), bool):
                raise WBParseError(f"WB Order Feed row {index} has invalid isMp")
            valid.append((item, srid, created_at, updated_at))
        if not valid:
            return 0
        with self.session_factory() as session:
            srids = [item[1] for item in valid]
            existing = {
                row.srid: row
                for row in session.query(WBOrderFeedOrder).filter(WBOrderFeedOrder.srid.in_(srids)).all()
            }
            product_ids = {
                int(nm_id): product_id
                for nm_id, product_id in session.query(WBProduct.nm_id, WBProduct.id).all()
            }
            for item, srid, created_at, updated_at in valid:
                row = existing.get(srid)
                if row is None:
                    row = WBOrderFeedOrder(srid=srid)
                    session.add(row)
                    existing[srid] = row
                nm_id = int(item.get("nmId") or 0)
                row.product_id = product_ids.get(nm_id)
                row.nm_id = nm_id or None
                row.chrt_id = item.get("chrtId")
                row.order_date = created_at
                row.status_updated_at = updated_at
                row.status = str(item.get("status") or "unknown")
                row.cancel_type = item.get("cancelType")
                row.is_b2b = bool(item.get("isB2b"))
                row.is_mp = bool(item.get("isMp"))
                row.seller_price = _money(item.get("sellerPrice"))
                row.warehouse_name = item.get("warehouseName")
                row.warehouse_region = item.get("warehouseRegion")
                row.destination_city = item.get("destinationCity")
                row.destination_district = item.get("destinationDistrict")
                row.raw_data = item
                row.fetched_at = fetched_at
            session.commit()
        return len(valid)

    def _finish(
        self,
        run_id: str,
        status: str,
        rows_received: int,
        rows_upserted: int,
        error: str | None,
        finished_at: datetime,
    ) -> None:
        with self.session_factory() as session:
            run = session.get(WBOrderFeedSyncRun, run_id)
            if run is not None:
                run.finished_at = finished_at
                run.status = status
                run.rows_received = rows_received
                run.rows_upserted = rows_upserted
                run.error = error
                session.commit()


def main() -> None:
    configure_wb_logging(log_dir=WB_LOG_DIR, file_prefix="wb_order_feed")
    install_context_filter()
    logging.basicConfig(
        level=getattr(logging, WB_LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = OrderFeedSyncService().sync()
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
