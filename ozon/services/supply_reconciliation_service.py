from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from typing import Any, Callable

from app.config import OZON_SUPPLY_RECONCILIATION_FROM, OZON_SUPPLY_REQUEST_PAUSE_SECONDS
from app.db import SessionLocal
from app.models import (
    OzonFBOSupplyAct,
    OzonFBOSupplyActItem,
    OzonFBOSupplyDeclaredItem,
)
from ozon.exceptions import OzonHTTPError
from ozon.supplies import OzonSuppliesAPI


logger = logging.getLogger(__name__)

SENT_SUPPLY_STATES = {
    "ACCEPTED_AT_SUPPLY_WAREHOUSE",
    "IN_TRANSIT",
    "ACCEPTANCE_AT_STORAGE_WAREHOUSE",
    "REPORTS_CONFIRMATION_AWAITING",
    "REPORT_REJECTED",
    "COMPLETED",
    "REJECTED_AT_SUPPLY_WAREHOUSE",
}


def _datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
    except ValueError:
        return None


def _date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10].strip())
    except ValueError:
        return None


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _act_is_absent(exc: Exception) -> bool:
    return isinstance(exc, OzonHTTPError) and "HTTP 404" in str(exc)


class OzonSupplyReconciliationService:
    """Persist sent FBO quantities and Ozon acceptance acts by supply and SKU."""

    def __init__(
        self,
        *,
        api: OzonSuppliesAPI | None = None,
        session_factory: Callable[..., Any] = SessionLocal,
        history_from: date | None = None,
        request_pause_seconds: float = OZON_SUPPLY_REQUEST_PAUSE_SECONDS,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if request_pause_seconds < 0:
            raise ValueError("request_pause_seconds must not be negative")
        self.api = api or OzonSuppliesAPI()
        self.session_factory = session_factory
        self.history_from = history_from or date.fromisoformat(OZON_SUPPLY_RECONCILIATION_FROM)
        self.request_pause_seconds = request_pause_seconds
        self.sleeper = sleeper

    def sync_all(self) -> dict[str, Any]:
        order_refs = self.api.list()
        orders_scanned = 0
        orders_in_period = 0
        supplies_sent = 0
        declared_items = 0
        acts = 0
        act_items = 0
        acts_unavailable = 0
        errors: list[str] = []

        for index, reference in enumerate(order_refs):
            order_id = _integer(reference.get("supply_order_id"))
            if not order_id:
                continue
            if index and self.request_pause_seconds:
                self.sleeper(self.request_pause_seconds)
            orders_scanned += 1
            try:
                order = self.api.get(order_id)
            except Exception as exc:
                errors.append(self._error("order", order_id, exc))
                continue
            created_at = _datetime(order.get("created_date") or order.get("created_at"))
            if created_at is not None and created_at.date() < self.history_from:
                continue
            orders_in_period += 1

            sent_supplies = []
            for supply in order.get("supplies") or []:
                if not isinstance(supply, dict):
                    continue
                state = str(supply.get("state") or order.get("state") or "UNSPECIFIED")
                if state in SENT_SUPPLY_STATES and _integer(supply.get("supply_id")):
                    sent_supplies.append((supply, state))
            supplies_sent += len(sent_supplies)
            if not sent_supplies:
                continue

            summary: dict[str, Any] = {}
            try:
                self._pause()
                summary = self.api.act_summary(order_id)
            except Exception as exc:
                if _act_is_absent(exc):
                    acts_unavailable += len(sent_supplies)
                else:
                    errors.append(self._error("act-summary", order_id, exc))
            summary_by_supply = {
                _integer(group.get("supply_id")): group
                for group in summary.get("supplies_acts") or []
                if isinstance(group, dict) and _integer(group.get("supply_id"))
            }

            for supply, state in sent_supplies:
                supply_id = _integer(supply.get("supply_id"))
                bundle_id = str(supply.get("bundle_id") or "").strip()
                if not bundle_id:
                    errors.append(f"bundle:{order_id}:{supply_id}: bundle_id is missing")
                    continue
                try:
                    self._pause()
                    bundle_items = self.api.bundle(bundle_id)
                    declared_items += self._save_declared(
                        order_id,
                        supply,
                        state,
                        bundle_id,
                        bundle_items,
                    )
                except Exception as exc:
                    errors.append(self._error("bundle", f"{order_id}:{supply_id}", exc))

                group = summary_by_supply.get(supply_id)
                if not group:
                    continue
                acts += self._save_act_summaries(order_id, supply_id, group)
                try:
                    self._pause()
                    products = self.api.act_products(supply_id)
                    product_result = self._save_act_products(order_id, supply_id, products)
                    acts += product_result["new_acts"]
                    act_items += product_result["items"]
                except Exception as exc:
                    if _act_is_absent(exc):
                        acts_unavailable += 1
                    else:
                        errors.append(self._error("act-products", f"{order_id}:{supply_id}", exc))

        return {
            "history_from": self.history_from.isoformat(),
            "orders_scanned": orders_scanned,
            "orders_in_period": orders_in_period,
            "supplies_sent": supplies_sent,
            "declared_items": declared_items,
            "acts": acts,
            "act_items": act_items,
            "acts_unavailable": acts_unavailable,
            "failed": len(errors),
            "errors": errors,
            **({"reconciliation_error": "; ".join(errors)} if errors else {}),
        }

    def _save_declared(
        self,
        order_id: int,
        supply: dict[str, Any],
        state: str,
        bundle_id: str,
        items: list[dict[str, Any]],
    ) -> int:
        supply_id = _integer(supply.get("supply_id"))
        warehouse = supply.get("storage_warehouse") or {}
        now = datetime.now(timezone.utc)
        saved = 0
        with self.session_factory() as session:
            for item in items:
                sku = _integer(item.get("sku"))
                if not sku:
                    continue
                row = session.query(OzonFBOSupplyDeclaredItem).filter_by(
                    supply_id=supply_id,
                    sku=sku,
                ).one_or_none()
                if row is None:
                    row = OzonFBOSupplyDeclaredItem(
                        supply_id=supply_id,
                        sku=sku,
                        first_seen_at=now,
                    )
                    session.add(row)
                row.supply_order_id = order_id
                row.bundle_id = bundle_id
                row.supply_state = state
                row.storage_warehouse_id = warehouse.get("warehouse_id")
                row.storage_warehouse_name = warehouse.get("name")
                row.product_id = item.get("product_id")
                row.offer_id = item.get("offer_id")
                row.name = item.get("name")
                row.barcode = item.get("barcode")
                row.declared_quantity = _integer(item.get("quantity"))
                row.pack_quantity = item.get("quant")
                row.shipment_type = item.get("shipment_type")
                row.placement_zone = item.get("placement_zone")
                row.tags = item.get("tags") if isinstance(item.get("tags"), list) else []
                row.raw_data = item
                row.fetched_at = now
                saved += 1
            session.commit()
        return saved

    def _save_act_summaries(self, order_id: int, supply_id: int, group: dict[str, Any]) -> int:
        now = datetime.now(timezone.utc)
        saved = 0
        with self.session_factory() as session:
            for item in group.get("supply_acts") or []:
                if not isinstance(item, dict):
                    continue
                act_id = _integer(item.get("act_id"))
                if not act_id:
                    continue
                row = session.query(OzonFBOSupplyAct).filter_by(act_id=act_id).one_or_none()
                if row is None:
                    row = OzonFBOSupplyAct(act_id=act_id)
                    session.add(row)
                summary = item.get("summary") or {}
                row.supply_order_id = order_id
                row.supply_id = supply_id
                row.act_number = item.get("act_number")
                row.act_type = str(item.get("type") or "UNSPECIFIED")
                row.act_state = item.get("act_state")
                row.act_created_date = _date(item.get("created_date"))
                row.deadline_at = _datetime(item.get("deadline_utc"))
                row.is_agreement_completed = bool(group.get("is_agreement_completed"))
                row.declared_quantity = _integer(summary.get("declared_quantity"))
                row.fact_quantity = _integer(summary.get("fact_quantity"))
                row.approved_quantity = _integer(summary.get("approved_quantity"))
                row.sku_quantity = _integer(summary.get("sku_quantity"))
                row.unidentified_quantity = _integer(summary.get("unidentified_quantity"))
                row.declared_amount = summary.get("declared_amount")
                row.fact_amount = summary.get("fact_amount")
                row.approved_amount = summary.get("approved_amount")
                row.raw_data = item
                row.fetched_at = now
                saved += 1
            session.commit()
        return saved

    def _save_act_products(
        self,
        order_id: int,
        supply_id: int,
        payload: dict[str, Any],
    ) -> dict[str, int]:
        defect_reasons = {
            _integer(item.get("sku")): item.get("defect_reasons") or []
            for item in payload.get("skus_defects") or []
            if isinstance(item, dict) and _integer(item.get("sku"))
        }
        now = datetime.now(timezone.utc)
        new_acts = 0
        saved_items = 0
        with self.session_factory() as session:
            for act in payload.get("supply_acts") or []:
                if not isinstance(act, dict):
                    continue
                act_id = _integer(act.get("act_id"))
                if not act_id:
                    continue
                act_type = str(act.get("type") or "UNSPECIFIED")
                act_row = session.query(OzonFBOSupplyAct).filter_by(act_id=act_id).one_or_none()
                if act_row is None:
                    act_row = OzonFBOSupplyAct(
                        act_id=act_id,
                        supply_order_id=order_id,
                        supply_id=supply_id,
                        act_type=act_type,
                        act_state=None,
                        is_agreement_completed=False,
                        declared_quantity=0,
                        fact_quantity=0,
                        approved_quantity=0,
                        sku_quantity=0,
                        unidentified_quantity=_integer(act.get("unidentified_quantity")),
                        raw_data=act,
                        fetched_at=now,
                    )
                    session.add(act_row)
                    new_acts += 1
                else:
                    act_row.act_type = act_type
                    act_row.unidentified_quantity = _integer(act.get("unidentified_quantity"))
                    act_row.raw_data = {
                        **(act_row.raw_data or {}),
                        "product_details": act,
                    }
                    act_row.fetched_at = now
                for item in act.get("items") or []:
                    if not isinstance(item, dict):
                        continue
                    sku_info = item.get("sku_info") or {}
                    sku = _integer(sku_info.get("sku"))
                    if not sku:
                        continue
                    row = session.query(OzonFBOSupplyActItem).filter_by(
                        act_id=act_id,
                        sku=sku,
                    ).one_or_none()
                    if row is None:
                        row = OzonFBOSupplyActItem(act_id=act_id, sku=sku)
                        session.add(row)
                    row.supply_order_id = order_id
                    row.supply_id = supply_id
                    row.act_type = act_type
                    row.offer_id = sku_info.get("offer_id")
                    row.name = sku_info.get("name")
                    row.barcode = sku_info.get("barcode")
                    row.declared_quantity = _integer(item.get("declared_quantity"))
                    row.fact_quantity = _integer(item.get("fact_quantity"))
                    row.approved_quantity = _integer(item.get("approved_quantity"))
                    row.price_without_vat = sku_info.get("price_without_vat")
                    row.fact_amount = item.get("fact_amount")
                    row.approved_amount = item.get("approved_amount")
                    row.defect_reasons = defect_reasons.get(sku, [])
                    row.raw_data = item
                    row.fetched_at = now
                    saved_items += 1
            session.commit()
        return {"new_acts": new_acts, "items": saved_items}

    def _pause(self) -> None:
        if self.request_pause_seconds:
            self.sleeper(self.request_pause_seconds)

    @staticmethod
    def _error(stage: str, identifier: Any, exc: Exception) -> str:
        message = f"{stage}:{identifier}: {type(exc).__name__}: {exc}"
        logger.exception("Ozon FBO supply reconciliation failed: %s", message)
        return message
