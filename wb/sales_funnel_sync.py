from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app.config import WB_LOG_DIR, WB_LOG_LEVEL, WB_SALES_FUNNEL_LOOKBACK_DAYS, WB_TG_TIMEZONE
from app.db import SessionLocal
from app.models import WBProduct, WBSalesFunnelDaily, WBSalesFunnelSyncRun
from wb.exceptions import WBParseError
from wb.sales_funnel import SalesFunnelAPI
from wb.sync_logging import configure_wb_logging, install_context_filter


logger = logging.getLogger(__name__)


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


class SalesFunnelSyncService:
    def __init__(
        self,
        *,
        api: SalesFunnelAPI | None = None,
        session_factory: Callable[..., Any] = SessionLocal,
        timezone_name: str = WB_TG_TIMEZONE,
        lookback_days: int = WB_SALES_FUNNEL_LOOKBACK_DAYS,
    ) -> None:
        if not 1 <= lookback_days <= 7:
            raise ValueError("WB_SALES_FUNNEL_LOOKBACK_DAYS must be between 1 and 7")
        self.api = api or SalesFunnelAPI()
        self.session_factory = session_factory
        self.timezone = ZoneInfo(timezone_name)
        self.lookback_days = lookback_days

    def sync(self, now: datetime | None = None) -> dict[str, Any]:
        current = now or datetime.now(self.timezone)
        current = current.replace(tzinfo=self.timezone) if current.tzinfo is None else current.astimezone(self.timezone)
        period_to = current.date()
        period_from = period_to - timedelta(days=self.lookback_days - 1)
        run_id = uuid.uuid4().hex
        with self.session_factory() as session:
            nm_ids = [int(value) for (value,) in session.query(WBProduct.nm_id).filter(WBProduct.nm_id.isnot(None)).distinct().all()]
            session.add(WBSalesFunnelSyncRun(
                id=run_id, started_at=current, status="running", period_from=period_from, period_to=period_to
            ))
            session.commit()
        try:
            payload = self.api.history(period_from, period_to, nm_ids)
            received, upserted = self._persist(payload, current)
            self._finish(run_id, "completed", received, upserted, None, datetime.now(self.timezone))
            return {"run_id": run_id, "status": "completed", "period_from": period_from,
                    "period_to": period_to, "rows_received": received, "rows_upserted": upserted}
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            self._finish(run_id, "failed", 0, 0, error, datetime.now(self.timezone))
            logger.exception("WB Sales Funnel synchronization failed")
            raise

    def _persist(self, payload: list[dict[str, Any]], fetched_at: datetime) -> tuple[int, int]:
        parsed: list[tuple[date, int, dict[str, Any], dict[str, Any], Any, str | None]] = []
        for product_row in payload:
            product = product_row.get("product")
            history = product_row.get("history")
            if not isinstance(product, dict) or not isinstance(history, list):
                raise WBParseError("WB Sales Funnel item has no product or history")
            nm_id = int(product.get("nmId") or 0)
            if not nm_id:
                raise WBParseError("WB Sales Funnel item has no nmId")
            currency = product_row.get("currency")
            currency_code = currency.get("name") if isinstance(currency, dict) else currency
            for item in history:
                if not isinstance(item, dict) or not item.get("date"):
                    raise WBParseError(f"WB Sales Funnel history for {nm_id} has no date")
                parsed.append((date.fromisoformat(str(item["date"])), nm_id, product, item,
                               product_row.get("currency"), currency_code))
        if not parsed:
            return 0, 0
        with self.session_factory() as session:
            keys = [(day, nm_id) for day, nm_id, *_ in parsed]
            dates = {key[0] for key in keys}
            ids = {key[1] for key in keys}
            existing = {(row.stat_date, row.nm_id): row for row in session.query(WBSalesFunnelDaily).filter(
                WBSalesFunnelDaily.stat_date.in_(dates), WBSalesFunnelDaily.nm_id.in_(ids)
            ).all()}
            for day, nm_id, product, item, raw_currency, currency in parsed:
                row = existing.get((day, nm_id))
                if row is None:
                    row = WBSalesFunnelDaily(stat_date=day, nm_id=nm_id)
                    session.add(row)
                    existing[(day, nm_id)] = row
                row.vendor_code = product.get("vendorCode")
                row.title = product.get("title")
                row.currency = str(currency) if currency else None
                row.open_count = int(item.get("openCount") or 0)
                row.cart_count = int(item.get("cartCount") or 0)
                row.order_count = int(item.get("orderCount") or 0)
                row.order_sum = _money(item.get("orderSum"))
                row.buyout_count = int(item.get("buyoutCount") or 0)
                row.buyout_sum = _money(item.get("buyoutSum"))
                # Daily history has no cancellation fields. Do not mistake pending orders
                # (orders minus purchases) for cancellations.
                row.cancel_count = 0
                row.cancel_sum = Decimal(0)
                row.raw_data = {"product": product, "metrics": item, "currency": raw_currency}
                row.fetched_at = fetched_at
            session.commit()
        return len(parsed), len(parsed)

    def _finish(self, run_id: str, status: str, received: int, upserted: int,
                error: str | None, finished_at: datetime) -> None:
        with self.session_factory() as session:
            run = session.get(WBSalesFunnelSyncRun, run_id)
            if run is not None:
                run.finished_at = finished_at
                run.status = status
                run.rows_received = received
                run.rows_upserted = upserted
                run.error = error
                session.commit()


def main() -> None:
    configure_wb_logging(log_dir=WB_LOG_DIR, file_prefix="wb_sales_funnel")
    install_context_filter()
    logging.basicConfig(level=getattr(logging, WB_LOG_LEVEL, logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(json.dumps(SalesFunnelSyncService().sync(), ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
