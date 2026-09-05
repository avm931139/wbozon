from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from app.config import YANDEX_MARKET_BUSINESS_ID, YANDEX_MARKET_CAMPAIGN_IDS
from app.db import SessionLocal
from app.models import YandexMarketCampaignOffer, YandexMarketOffer
from yandex_market.catalog import YandexMarketCatalogAPI
from yandex_market.identity import YandexMarketIdentityAPI


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, dict):
        value = value.get("value")
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


class YandexMarketCatalogService:
    def __init__(
        self,
        api: YandexMarketCatalogAPI | None = None,
        identity_api: YandexMarketIdentityAPI | None = None,
        *,
        session_factory: Callable[..., Any] = SessionLocal,
    ) -> None:
        self.api = api or YandexMarketCatalogAPI()
        self.identity_api = identity_api or YandexMarketIdentityAPI()
        self.session_factory = session_factory

    def sync(self) -> dict[str, int]:
        campaigns, discovered_business_ids = self.identity_api.contexts()
        business_ids = {YANDEX_MARKET_BUSINESS_ID} if YANDEX_MARKET_BUSINESS_ID else discovered_business_ids
        configured = set(YANDEX_MARKET_CAMPAIGN_IDS)
        campaign_ids = {
            int(item["id"])
            for item in campaigns
            if item.get("id") and (not configured or int(item["id"]) in configured)
        }
        mappings_count = 0
        campaign_offers_count = 0
        for business_id in sorted(business_ids):
            mappings = self.api.offer_mappings(business_id=business_id)
            self._save_mappings(business_id, mappings)
            mappings_count += len(mappings)
        for campaign_id in sorted(campaign_ids):
            offers = self.api.campaign_offers(campaign_id=campaign_id)
            self._save_campaign_offers(campaign_id, offers)
            campaign_offers_count += len(offers)
        return {
            "businesses": len(business_ids),
            "campaigns": len(campaign_ids),
            "offer_mappings": mappings_count,
            "campaign_offers": campaign_offers_count,
        }

    def _save_mappings(self, business_id: int, mappings: list[dict[str, Any]]) -> None:
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            for item in mappings:
                offer = item.get("offer") if isinstance(item.get("offer"), dict) else item
                mapping = item.get("mapping") if isinstance(item.get("mapping"), dict) else {}
                offer_id = offer.get("offerId") or item.get("offerId")
                if not offer_id:
                    continue
                row = session.query(YandexMarketOffer).filter_by(
                    business_id=business_id, offer_id=str(offer_id)
                ).one_or_none()
                if row is None:
                    row = YandexMarketOffer(business_id=business_id, offer_id=str(offer_id))
                    session.add(row)
                row.market_sku = mapping.get("marketSku") or item.get("marketSku")
                row.name = offer.get("name") or mapping.get("marketSkuName")
                row.vendor = offer.get("vendor")
                row.category_name = (
                    mapping.get("marketCategoryName")
                    or offer.get("category")
                    or offer.get("categoryName")
                )
                row.barcodes = offer.get("barcodes") or []
                row.pictures = offer.get("pictures") or []
                row.status = offer.get("cardStatus") or item.get("status") or mapping.get("status")
                row.raw_data = item
                row.fetched_at = now
            session.commit()

    def _save_campaign_offers(self, campaign_id: int, offers: list[dict[str, Any]]) -> None:
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            for item in offers:
                offer_id = item.get("offerId") or item.get("shopSku")
                if not offer_id:
                    continue
                row = session.query(YandexMarketCampaignOffer).filter_by(
                    campaign_id=campaign_id, offer_id=str(offer_id)
                ).one_or_none()
                if row is None:
                    row = YandexMarketCampaignOffer(campaign_id=campaign_id, offer_id=str(offer_id))
                    session.add(row)
                price = item.get("campaignPrice") or item.get("price") or {}
                row.status = item.get("status")
                row.availability = item.get("available")
                row.price = _decimal(price)
                row.old_price = _decimal(
                    price.get("discountBase") if isinstance(price, dict) else item.get("oldPrice")
                )
                row.raw_data = item
                row.fetched_at = now
            session.commit()
