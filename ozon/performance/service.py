from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable
from app.db import SessionLocal
from app.models import OzonAdCampaign, OzonAdDailyStat
from app.config import OZON_HISTORY_FROM, OZON_SYNC_OVERLAP_DAYS
from ozon.performance.api import OzonPerformanceAPI
from ozon.business_time import ozon_today

def _money(value: Any) -> Decimal:
    try:
        normalized = str(value or 0).replace("\u00a0", "").replace(" ", "").replace(",", ".")
        return Decimal(normalized)
    except Exception: return Decimal(0)
def _date(value: Any) -> date | None:
    try: return date.fromisoformat(str(value)[:10])
    except ValueError: return None

class OzonPerformanceService:
    def __init__(
        self,
        api: OzonPerformanceAPI | None = None,
        *,
        today: Callable[[], date] = ozon_today,
    ) -> None:
        self.api = api or OzonPerformanceAPI()
        self.today = today
    def sync_campaigns(self) -> list[dict[str, Any]]:
        items = self.api.campaigns(); now = datetime.now(timezone.utc)
        with SessionLocal() as session:
            for item in items:
                cid = int(item["id"]); row = session.query(OzonAdCampaign).filter_by(campaign_id=cid).one_or_none()
                if row is None: row = OzonAdCampaign(campaign_id=cid, raw_data=item, fetched_at=now); session.add(row)
                row.title=item.get("title"); row.state=item.get("state"); row.campaign_type=item.get("advObjectType"); row.payment_type=item.get("PaymentType")
                row.budget=_money(item.get("budget")); row.daily_budget=_money(item.get("dailyBudget")); row.from_date=_date(item.get("fromDate")); row.to_date=_date(item.get("toDate")); row.raw_data=item; row.fetched_at=now
            session.commit()
        return items

    def sync_daily_stats(self) -> int:
        with SessionLocal() as session:
            latest = session.query(OzonAdDailyStat.stat_date).order_by(OzonAdDailyStat.stat_date.desc()).first()
        history_from = date.fromisoformat(OZON_HISTORY_FROM)
        start = max(history_from, latest[0] - timedelta(days=OZON_SYNC_OVERLAP_DAYS)) if latest else history_from
        end = self.today() - timedelta(days=1)
        if start > end: return 0
        rows: list[dict[str, Any]] = []; cursor = start
        while cursor <= end:
            chunk_end = min(end, cursor + timedelta(days=30))
            rows.extend(self.api.daily_statistics(cursor, chunk_end)); cursor = chunk_end + timedelta(days=1)
        now = datetime.now(timezone.utc)
        with SessionLocal() as session:
            for item in rows:
                day = _date(item.get("date")); cid = item.get("id")
                if day is None or cid in (None, ""): continue
                row = session.query(OzonAdDailyStat).filter_by(stat_date=day, campaign_id=int(cid), sku=0).one_or_none()
                if row is None: row = OzonAdDailyStat(stat_date=day,campaign_id=int(cid),sku=0,raw_data=item,fetched_at=now); session.add(row)
                row.views=int(item.get("views") or 0); row.clicks=int(item.get("clicks") or 0); row.orders=int(item.get("orders") or 0)
                row.orders_money=_money(item.get("ordersMoney")); row.spend=_money(item.get("moneySpent")); row.raw_data=item; row.fetched_at=now
            session.commit()
        return len(rows)

    def sync_all(self) -> dict[str, int]:
        return {"campaigns": len(self.sync_campaigns()), "daily_stats": self.sync_daily_stats()}

    @staticmethod
    def summary(date_from: date, date_to: date) -> dict[str, Any]:
        with SessionLocal() as session: rows=session.query(OzonAdDailyStat).filter(OzonAdDailyStat.stat_date.between(date_from,date_to)).all()
        spend=sum((x.spend for x in rows),Decimal(0)); revenue=sum((x.orders_money for x in rows),Decimal(0)); orders=sum(x.orders for x in rows)
        return {"spend":str(spend),"orders":orders,"attributed_revenue":str(revenue),"drr_percent":str(spend/revenue*100) if revenue else None,"roas":str(revenue/spend) if spend else None,"cpo":str(spend/orders) if orders else None}
