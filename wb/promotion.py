from __future__ import annotations

from datetime import date
import threading
import time
from typing import Any

from app.config import WB_PROMOTION_API_KEY, WB_PROMOTION_BASE_URL
from wb.base import WBAPIBase
from wb.client import WBClient


class PromotionAPI(WBAPIBase):
    """Read-only access to WB Promotion campaigns, costs and statistics."""

    def __init__(
        self,
        client: WBClient | None = None,
        *,
        stats_interval_seconds: float = 20.0,
        clock: Any = time.monotonic,
        sleeper: Any = time.sleep,
    ):
        super().__init__(client or WBClient(api_key=WB_PROMOTION_API_KEY, base_url=WB_PROMOTION_BASE_URL))
        self.stats_interval_seconds = stats_interval_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._stats_lock = threading.Lock()
        self._last_stats_request: float | None = None

    def list(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.campaigns()

    def campaigns(self) -> list[dict[str, Any]]:
        payload = self.client.get("/adv/v1/promotion/count", retries=8)
        result = []
        for group in payload.get("adverts", []) if isinstance(payload, dict) else []:
            for item in group.get("advert_list", []):
                result.append({**item, "type": group.get("type"), "status": group.get("status")})
        return result

    def campaign_details(self, advert_ids: list[int]) -> list[dict[str, Any]]:
        if not 1 <= len(advert_ids) <= 50:
            raise ValueError("advert_ids must contain from 1 to 50 IDs")
        payload = self.client.get("/api/advert/v2/adverts", params={"ids": ",".join(map(str, advert_ids))}, retries=8)
        if isinstance(payload, dict):
            payload = payload.get("adverts", payload.get("data", []))
        return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []

    def balance(self) -> dict[str, Any]:
        payload = self.client.get("/adv/v1/balance", retries=8)
        return payload if isinstance(payload, dict) else {}

    def campaign_budget(self, advert_id: int) -> dict[str, Any]:
        payload = self.client.get("/adv/v1/budget", params={"id": advert_id}, retries=8)
        return payload if isinstance(payload, dict) else {}

    def payments(self, date_from: date, date_to: date) -> list[dict[str, Any]]:
        if date_from > date_to:
            raise ValueError("date_from must not be later than date_to")
        if (date_to - date_from).days > 30:
            raise ValueError("WB payment request period cannot exceed 31 calendar days")
        payload = self.client.get("/adv/v1/payments", params={"from": date_from.isoformat(), "to": date_to.isoformat()}, retries=8)
        return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []

    def expenses(self, date_from: date, date_to: date) -> list[dict[str, Any]]:
        if date_from > date_to:
            raise ValueError("date_from must not be later than date_to")
        if (date_to - date_from).days > 30:
            raise ValueError("WB expense request period cannot exceed 31 calendar days")
        payload = self.client.get("/adv/v1/upd", params={"from": date_from.isoformat(), "to": date_to.isoformat()}, retries=8)
        return [x for x in payload if isinstance(x, dict)] if isinstance(payload, list) else []

    def full_stats(self, advert_ids: list[int], date_from: date, date_to: date) -> list[dict[str, Any]]:
        if not 1 <= len(advert_ids) <= 50:
            raise ValueError("advert_ids must contain from 1 to 50 IDs")
        if date_from > date_to:
            raise ValueError("date_from must not be later than date_to")
        if (date_to - date_from).days > 30:
            raise ValueError("WB statistics request period cannot exceed 31 calendar days")
        with self._stats_lock:
            now = self._clock()
            if self._last_stats_request is not None:
                delay = self.stats_interval_seconds - (now - self._last_stats_request)
                if delay > 0:
                    self._sleeper(delay)
            self._last_stats_request = self._clock()
            payload = self.client.get("/adv/v3/fullstats", params={"ids": ",".join(map(str, advert_ids)), "beginDate": date_from.isoformat(), "endDate": date_to.isoformat()}, retries=8)
        return [x for x in payload if isinstance(x, dict)] if isinstance(payload, list) else []
