from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from app.db import SessionLocal
from app.models import YandexMarketBusiness, YandexMarketCampaign, YandexMarketWarehouse
from yandex_market.identity import YandexMarketIdentityAPI


class YandexMarketIdentityService:
    def __init__(
        self,
        api: YandexMarketIdentityAPI | None = None,
        *,
        session_factory: Callable[..., Any] = SessionLocal,
    ) -> None:
        self.api = api or YandexMarketIdentityAPI()
        self.session_factory = session_factory

    def sync(self) -> dict[str, Any]:
        campaigns, business_ids = self.api.contexts()
        now = datetime.now(timezone.utc)
        warehouses: list[tuple[int, int | None, str, dict[str, Any]]] = []
        for business_id in business_ids:
            campaign_ids = [
                int(item["id"])
                for item in campaigns
                if item.get("id")
                and isinstance(item.get("business"), dict)
                and int(item["business"].get("id") or 0) == business_id
                and item.get("placementType") in {"FBS", "DBS", "EXPRESS"}
            ]
            if not campaign_ids:
                continue
            for item in self.api.partner_warehouses(
                business_id=business_id,
                campaign_ids=campaign_ids,
            ):
                warehouses.append((business_id, item.get("campaignId"), "PARTNER", item))
        for campaign in campaigns:
            if campaign.get("placementType") not in {"FBY", "LAAS"}:
                continue
            business = campaign.get("business") or {}
            if not isinstance(business, dict) or not business.get("id") or not campaign.get("id"):
                continue
            for item in self.api.fulfillment_warehouses(campaign_id=int(campaign["id"])):
                warehouses.append((int(business["id"]), int(campaign["id"]), "FULFILLMENT", item))
        with self.session_factory() as session:
            for item in campaigns:
                campaign_id = item.get("id")
                business = item.get("business") or {}
                if campaign_id is None or not isinstance(business, dict) or business.get("id") is None:
                    continue
                business_id = int(business["id"])
                business_row = session.get(YandexMarketBusiness, business_id)
                if business_row is None:
                    business_row = YandexMarketBusiness(business_id=business_id)
                    session.add(business_row)
                business_row.name = business.get("name")
                business_row.raw_data = business
                business_row.fetched_at = now

                campaign_row = session.get(YandexMarketCampaign, int(campaign_id))
                if campaign_row is None:
                    campaign_row = YandexMarketCampaign(campaign_id=int(campaign_id))
                    session.add(campaign_row)
                campaign_row.business_id = business_id
                campaign_row.name = item.get("name") or item.get("domain")
                campaign_row.domain = item.get("domain")
                campaign_row.placement_type = item.get("placementType")
                campaign_row.api_availability = item.get("apiAvailability")
                campaign_row.raw_data = item
                campaign_row.fetched_at = now
            for business_id, campaign_id, warehouse_type, item in warehouses:
                warehouse_id = item.get("id")
                if warehouse_id is None:
                    continue
                row = session.query(YandexMarketWarehouse).filter_by(
                    business_id=business_id,
                    warehouse_id=int(warehouse_id),
                    warehouse_type=warehouse_type,
                ).one_or_none()
                if row is None:
                    row = YandexMarketWarehouse(
                        business_id=business_id,
                        warehouse_id=int(warehouse_id),
                        warehouse_type=warehouse_type,
                    )
                    session.add(row)
                row.campaign_id = campaign_id or item.get("campaignId")
                row.name = item.get("name")
                row.models = item.get("models") or []
                row.address = item.get("address") or {}
                row.raw_data = item
                row.fetched_at = now
            session.commit()
        return {
            "businesses": len(business_ids),
            "campaigns": len(campaigns),
            "warehouses": len(warehouses),
        }
