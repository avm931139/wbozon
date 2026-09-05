from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app.config import (
    YANDEX_MARKET_BUSINESS_ID,
    YANDEX_MARKET_CAMPAIGN_IDS,
    YANDEX_MARKET_HISTORY_FROM,
    YANDEX_MARKET_ORDER_LOOKBACK_DAYS,
    YANDEX_MARKET_TIMEZONE,
)
from app.db import SessionLocal
from app.models import YandexMarketOrder, YandexMarketOrderItem
from yandex_market.identity import YandexMarketIdentityAPI
from yandex_market.orders import YandexMarketOrdersAPI


def _datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    for pattern in ("%d-%m-%Y %H:%M:%S", "%d-%m-%Y"):
        try:
            parsed = datetime.strptime(value, pattern)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _decimal(value: Any) -> Decimal:
    if isinstance(value, dict):
        value = value.get("value") or value.get("amount")
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _order_total(prices: dict[str, Any], fallback: Any = None) -> Decimal:
    explicit = prices.get("buyerTotal") or prices.get("buyerItemsTotal") or fallback
    if explicit is not None:
        return _decimal(explicit)
    return _decimal(prices.get("payment")) + _decimal(prices.get("cashback"))


class YandexMarketOrderService:
    def __init__(
        self,
        api: YandexMarketOrdersAPI | None = None,
        identity_api: YandexMarketIdentityAPI | None = None,
        *,
        session_factory: Callable[..., Any] = SessionLocal,
    ) -> None:
        self.api = api or YandexMarketOrdersAPI()
        self.identity_api = identity_api or YandexMarketIdentityAPI()
        self.session_factory = session_factory

    def sync(self, *, today: date | None = None) -> dict[str, int]:
        today = today or datetime.now(ZoneInfo(YANDEX_MARKET_TIMEZONE)).date()
        campaigns, discovered_business_ids = self.identity_api.contexts()
        business_ids = {YANDEX_MARKET_BUSINESS_ID} if YANDEX_MARKET_BUSINESS_ID else discovered_business_ids
        configured = set(YANDEX_MARKET_CAMPAIGN_IDS)
        campaigns_by_business: dict[int, list[int]] = {}
        for item in campaigns:
            business = item.get("business") or {}
            campaign_id = item.get("id")
            if not isinstance(business, dict) or not business.get("id") or not campaign_id:
                continue
            if configured and int(campaign_id) not in configured:
                continue
            campaigns_by_business.setdefault(int(business["id"]), []).append(int(campaign_id))

        received = 0
        saved = 0
        for business_id in sorted(business_ids):
            start = self._start_date(business_id, today)
            for date_from, date_to in self._ranges(start, today):
                orders = self.api.list(
                    business_id=business_id,
                    date_from=date_from,
                    date_to=date_to,
                    campaign_ids=campaigns_by_business.get(business_id),
                )
                received += len(orders)
                saved += self._save(business_id, orders)
        return {"businesses": len(business_ids), "received": received, "saved": saved}

    def _start_date(self, business_id: int, today: date) -> date:
        with self.session_factory() as session:
            has_orders = session.query(YandexMarketOrder.id).filter_by(business_id=business_id).first()
        if has_orders:
            return today - timedelta(days=max(YANDEX_MARKET_ORDER_LOOKBACK_DAYS - 1, 0))
        configured = date.fromisoformat(YANDEX_MARKET_HISTORY_FROM)
        return min(configured, today)

    @staticmethod
    def _ranges(start: date, end: date):
        cursor = start
        while cursor <= end:
            chunk_end = min(cursor + timedelta(days=30), end)
            yield cursor, chunk_end
            cursor = chunk_end + timedelta(days=1)

    def _save(self, business_id: int, orders: list[dict[str, Any]]) -> int:
        now = datetime.now(timezone.utc)
        saved = 0
        with self.session_factory() as session:
            for item in orders:
                order_id = item.get("id") or item.get("orderId")
                if order_id is None:
                    continue
                order_id = int(order_id)
                row = session.query(YandexMarketOrder).filter_by(
                    business_id=business_id, order_id=order_id
                ).one_or_none()
                if row is None:
                    row = YandexMarketOrder(business_id=business_id, order_id=order_id)
                    session.add(row)
                delivery = item.get("delivery") if isinstance(item.get("delivery"), dict) else {}
                dates = item.get("dates") if isinstance(item.get("dates"), dict) else {}
                prices = item.get("prices") if isinstance(item.get("prices"), dict) else {}
                order_items = item.get("items") if isinstance(item.get("items"), list) else []
                row.external_order_id = item.get("externalOrderId")
                row.campaign_id = item.get("campaignId")
                row.program_type = item.get("programType") or item.get("placementType")
                row.status = item.get("status")
                row.substatus = item.get("substatus")
                row.created_at = _datetime(item.get("creationDate") or dates.get("creationDate"))
                row.updated_at = _datetime(item.get("updateDate") or dates.get("updateDate"))
                shipment = delivery.get("shipment") if isinstance(delivery.get("shipment"), dict) else {}
                delivery_dates = delivery.get("dates") if isinstance(delivery.get("dates"), dict) else {}
                row.shipment_date = _datetime(
                    item.get("shipmentDate") or delivery.get("shipmentDate") or shipment.get("shipmentDate")
                )
                row.delivery_date = _datetime(
                    item.get("deliveryDate")
                    or delivery.get("deliveryDate")
                    or delivery_dates.get("realDeliveryDate")
                    or delivery_dates.get("toDate")
                )
                row.payment_type = item.get("paymentType")
                row.payment_method = item.get("paymentMethod")
                row.items_count = sum(int(product.get("count") or 0) for product in order_items if isinstance(product, dict))
                total = prices.get("buyerTotal") or prices.get("buyerItemsTotal") or prices.get("payment") or item.get("total")
                row.total_amount = _order_total(prices, item.get("total"))
                row.currency = (
                    total.get("currencyId") or total.get("currency")
                    if isinstance(total, dict)
                    else item.get("currency")
                )
                row.items = order_items
                row.raw_data = item
                row.fetched_at = now
                session.flush()
                session.query(YandexMarketOrderItem).filter_by(
                    business_id=business_id, order_id=order_id
                ).delete(synchronize_session=False)
                for index, product in enumerate(order_items):
                    if not isinstance(product, dict):
                        continue
                    item_prices = product.get("prices") if isinstance(product.get("prices"), dict) else {}
                    offer_id = product.get("offerId") or product.get("shopSku")
                    market_sku = product.get("marketSku") or product.get("sku")
                    item_key = str(product.get("id") or f"{offer_id or ''}:{market_sku or ''}:{index}")
                    session.add(YandexMarketOrderItem(
                        business_id=business_id,
                        order_id=order_id,
                        item_key=item_key,
                        offer_id=str(offer_id) if offer_id is not None else None,
                        market_sku=market_sku,
                        name=product.get("offerName") or product.get("name"),
                        count=int(product.get("count") or 0),
                        price=_decimal(item_prices.get("buyerPrice") or item_prices.get("payment") or product.get("price")),
                        subsidy=_decimal(item_prices.get("subsidy")),
                        statuses=product.get("itemStatuses") or [],
                        raw_data=product,
                        fetched_at=now,
                    ))
                saved += 1
            session.commit()
        return saved
