from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from app.config import YANDEX_MARKET_BUSINESS_ID
from app.db import SessionLocal
from app.models import YandexMarketBusiness
from price_sync.types import PriceRecord
from yandex_market.client import YandexMarketClient
from yandex_market.endpoints import business_prices
from yandex_market.exceptions import YandexMarketParseError


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value not in (None, "") else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def _datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class YandexMarketPricesAPI:
    def __init__(
        self,
        client: YandexMarketClient | None = None,
        *,
        session_factory: Callable[..., Any] = SessionLocal,
        business_id: int | None = YANDEX_MARKET_BUSINESS_ID,
    ) -> None:
        self.client = client or YandexMarketClient()
        self.session_factory = session_factory
        self.business_id = business_id

    def resolve_business_id(self) -> int:
        if self.business_id:
            return self.business_id
        with self.session_factory() as session:
            ids = [value for value, in session.query(YandexMarketBusiness.business_id).all()]
        if len(ids) == 1:
            return int(ids[0])
        if not ids:
            raise ValueError("run Yandex Market identity before price synchronization")
        raise ValueError("configure YANDEX_MARKET_BUSINESS_ID for multiple businesses")

    def list_all(self, *, business_id: int, limit: int = 500) -> list[dict[str, Any]]:
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        rows: list[dict[str, Any]] = []
        page_token = ""
        seen: set[str] = set()
        while True:
            params: dict[str, Any] = {"limit": limit}
            if page_token:
                params["pageToken"] = page_token
            payload = self.client.post(
                business_prices(business_id),
                params=params,
                json_body={"archived": False},
            )
            result = payload.get("result") if isinstance(payload.get("result"), dict) else None
            offers = result.get("offers") if isinstance(result, dict) else None
            if not isinstance(offers, list):
                raise YandexMarketParseError("Yandex Market prices response has no result.offers")
            rows.extend(item for item in offers if isinstance(item, dict))
            paging = result.get("paging") if isinstance(result.get("paging"), dict) else {}
            next_token = str(paging.get("nextPageToken") or "")
            if not next_token:
                return rows
            if next_token == page_token or next_token in seen:
                raise YandexMarketParseError("Yandex Market prices token did not advance")
            seen.add(next_token)
            page_token = next_token

    def records(self) -> list[PriceRecord]:
        business_id = self.resolve_business_id()
        records: list[PriceRecord] = []
        for item in self.list_all(business_id=business_id):
            offer_id = item.get("offerId")
            if not offer_id:
                continue
            price = item.get("price") if isinstance(item.get("price"), dict) else {}
            value = _decimal(price.get("value"))
            records.append(PriceRecord(
                source_key=f"{business_id}:{offer_id}",
                account_id=str(business_id),
                offer_id=str(offer_id),
                currency=price.get("currencyId"),
                list_price=_decimal(price.get("discountBase")),
                seller_price=value,
                min_price=_decimal(price.get("minimumForBestseller")),
                source_updated_at=_datetime(price.get("updatedAt")),
                raw_data=item,
            ))
        return records
