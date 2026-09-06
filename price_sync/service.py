from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable

from app.db import SessionLocal
from app.models import (
    MarketplaceCurrentPrice,
    MarketplaceProductLink,
    MarketplacePriceSnapshot,
    OzonProduct,
    WBProduct,
    YandexMarketOffer,
)
from price_sync.types import PriceRecord


PRICE_FIELDS = (
    "account_id",
    "offer_id",
    "product_id",
    "variant_id",
    "product_name",
    "currency",
    "list_price",
    "seller_price",
    "customer_price",
    "club_price",
    "min_price",
    "discount_percent",
    "club_discount_percent",
    "in_promotion",
    "auto_action_enabled",
    "promotion_names",
    "source_updated_at",
    "raw_data",
)


class MarketplacePriceService:
    MARKETPLACES = ("wb", "ozon", "yandex_market")

    def __init__(
        self,
        *,
        session_factory: Callable[..., Any] = SessionLocal,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def sync(self, marketplace: str, run_id: str) -> dict[str, Any]:
        records = self._source(marketplace).records()
        captured_at = self.clock()
        names = self._product_names(marketplace, records)
        master_ids = self._master_product_ids(marketplace, records)
        with self.session_factory() as session:
            existing = {
                row.source_key: row
                for row in session.query(MarketplaceCurrentPrice).filter_by(
                    marketplace=marketplace
                ).all()
            }
            seen: set[str] = set()
            for record in records:
                seen.add(record.source_key)
                values = asdict(record)
                if not values.get("product_name"):
                    values["product_name"] = names.get(record.product_id or record.offer_id or "")
                current = existing.get(record.source_key)
                if current is None:
                    current = MarketplaceCurrentPrice(
                        marketplace=marketplace,
                        source_key=record.source_key,
                    )
                    session.add(current)
                for field in PRICE_FIELDS:
                    setattr(current, field, values[field])
                identity = self._record_identity(marketplace, record)
                current.master_product_id = master_ids.get(identity)
                current.captured_at = captured_at
                current.active = True
                session.add(MarketplacePriceSnapshot(
                    run_id=run_id,
                    marketplace=marketplace,
                    source_key=record.source_key,
                    master_product_id=master_ids.get(identity),
                    captured_at=captured_at,
                    **{field: values[field] for field in PRICE_FIELDS},
                ))
            for source_key, current in existing.items():
                if source_key not in seen:
                    current.active = False
                    current.captured_at = captured_at
            session.commit()
        return {
            "marketplace": marketplace,
            "received": len(records),
            "current_saved": len(records),
            "snapshots_saved": len(records),
            "captured_at": captured_at.isoformat(),
            "deactivated": len(set(existing) - seen),
        }

    @staticmethod
    def _record_identity(marketplace: str, record: PriceRecord) -> tuple[str, str]:
        external_id = record.offer_id if marketplace == "yandex_market" else record.product_id
        return record.account_id, str(external_id or "")

    def _master_product_ids(
        self, marketplace: str, records: list[PriceRecord]
    ) -> dict[tuple[str, str], int]:
        if not records:
            return {}
        identities = {self._record_identity(marketplace, record) for record in records}
        with self.session_factory() as session:
            rows = session.query(MarketplaceProductLink).filter_by(
                marketplace=marketplace, active=True
            ).all()
        return {
            (row.account_id, row.external_product_id): int(row.master_product_id)
            for row in rows
            if (row.account_id, row.external_product_id) in identities
        }

    def _source(self, marketplace: str):
        if marketplace == "wb":
            from wb.prices import WBPricesAPI

            return WBPricesAPI()
        if marketplace == "ozon":
            from ozon.prices import OzonPricesAPI

            return OzonPricesAPI()
        if marketplace == "yandex_market":
            from yandex_market.prices import YandexMarketPricesAPI

            return YandexMarketPricesAPI(session_factory=self.session_factory)
        raise ValueError(f"unknown price marketplace: {marketplace}")

    def _product_names(
        self, marketplace: str, records: list[PriceRecord]
    ) -> dict[str, str | None]:
        keys = {record.product_id or record.offer_id for record in records}
        keys.discard(None)
        if not keys:
            return {}
        with self.session_factory() as session:
            if marketplace == "wb":
                rows = session.query(WBProduct.nm_id, WBProduct.title).filter(
                    WBProduct.nm_id.in_([int(key) for key in keys])
                ).all()
                return {str(key): value for key, value in rows}
            if marketplace == "ozon":
                rows = session.query(OzonProduct.product_id, OzonProduct.name).filter(
                    OzonProduct.product_id.in_([int(key) for key in keys])
                ).all()
                return {str(key): value for key, value in rows}
            rows = session.query(YandexMarketOffer.offer_id, YandexMarketOffer.name).filter(
                YandexMarketOffer.offer_id.in_([str(key) for key in keys])
            ).all()
            return {str(key): value for key, value in rows}
