from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    WBAdvertCampaign,
    WBAdvertDailyStat,
    WBAdvertExpense,
    WBAdvertProductDailyStat,
    WBProduct,
    WBPromotionAccountSnapshot,
    WBPromotionPayment,
)


class PromotionRepository:
    """Persistence operations for WB Promotion data within one transaction."""

    def __init__(self, session: Session):
        self.session = session

    def campaigns_by_wb_id(self) -> dict[int, WBAdvertCampaign]:
        return {row.advert_wb_id: row for row in self.session.query(WBAdvertCampaign).all()}

    def campaign_ids(self, statuses: tuple[int, ...] | None = None) -> list[int]:
        query = self.session.query(WBAdvertCampaign.advert_wb_id)
        if statuses:
            query = query.filter(WBAdvertCampaign.status.in_(statuses))
        rows = query.order_by(WBAdvertCampaign.advert_wb_id).all()
        return [int(row[0]) for row in rows]

    def get_or_create_campaign(
        self,
        advert_id: int,
        campaigns: dict[int, WBAdvertCampaign],
        **values: Any,
    ) -> WBAdvertCampaign:
        campaign = campaigns.get(advert_id)
        if campaign is None:
            campaign = WBAdvertCampaign(advert_wb_id=advert_id, raw_data=values.pop("raw_data", {}))
            self.session.add(campaign)
            self.session.flush()
            campaigns[advert_id] = campaign
        for field, value in values.items():
            if value is not None:
                setattr(campaign, field, value)
        return campaign

    def existing_expenses(self) -> list[tuple[str, dict[str, Any]]]:
        return [
            (row.source_hash, row.raw_data or {})
            for row in self.session.query(WBAdvertExpense.source_hash, WBAdvertExpense.raw_data).all()
        ]

    def add_expense(self, **values: Any) -> None:
        self.session.add(WBAdvertExpense(**values))

    def product_ids_by_nm_id(self) -> dict[int, int]:
        return {int(row[0]): int(row[1]) for row in self.session.query(WBProduct.nm_id, WBProduct.id).all()}

    def get_or_create_daily_stat(self, campaign: WBAdvertCampaign, stat_date: datetime) -> WBAdvertDailyStat:
        row = self.session.query(WBAdvertDailyStat).filter_by(campaign_id=campaign.id, stat_date=stat_date).first()
        if row is None:
            row = WBAdvertDailyStat(campaign=campaign, stat_date=stat_date, raw_data={})
            self.session.add(row)
            self.session.flush()
        return row

    def product_stats_by_key(self, daily_stat_id: int) -> dict[tuple[int, int], WBAdvertProductDailyStat]:
        rows = self.session.query(WBAdvertProductDailyStat).filter_by(daily_stat_id=daily_stat_id).all()
        return {(row.app_type, row.nm_id): row for row in rows}

    def remove_product_stats(self, rows: list[WBAdvertProductDailyStat]) -> None:
        for row in rows:
            self.session.delete(row)

    def add_account_snapshot(self, **values: Any) -> None:
        self.session.add(WBPromotionAccountSnapshot(**values))

    def existing_payment_hashes(self) -> set[str]:
        return {row[0] for row in self.session.query(WBPromotionPayment.source_hash).all()}

    def add_payment(self, **values: Any) -> None:
        self.session.add(WBPromotionPayment(**values))
