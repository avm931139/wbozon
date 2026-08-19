from __future__ import annotations

import time
from datetime import date, datetime
from typing import Any

from app.config import WB_MARKETPLACE_BASE_URL, WB_STATISTICS_BASE_URL
from wb.base import WBAPIBase
from wb.client import WBClient
from wb.endpoints import WBEndpoints


class FBSOrdersAPI(WBAPIBase):
    def __init__(self, client: WBClient | None = None):
        super().__init__(client or WBClient(base_url=WB_MARKETPLACE_BASE_URL))

    def list(self, date_from: datetime, date_to: datetime, limit: int = 1000) -> list[dict[str, Any]]:
        next_value = 0
        result: list[dict[str, Any]] = []
        while True:
            payload = self.client.get(
                WBEndpoints.FBS_ORDERS_LIST,
                params={"limit": limit, "next": next_value, "dateFrom": int(date_from.timestamp()), "dateTo": int(date_to.timestamp())},
            )
            page = payload.get("orders", []) if isinstance(payload, dict) else []
            result.extend(item for item in page if isinstance(item, dict))
            new_next = payload.get("next", 0) if isinstance(payload, dict) else 0
            if not page or not new_next or new_next == next_value:
                break
            next_value = int(new_next)
            time.sleep(0.21)
        return result

    def statuses(self, order_ids: list[int]) -> dict[int, dict[str, Any]]:
        result: dict[int, dict[str, Any]] = {}
        for offset in range(0, len(order_ids), 1000):
            payload = self.client.post(
                WBEndpoints.FBS_ORDERS_STATUS,
                json_body={"orders": order_ids[offset : offset + 1000]},
            )
            for item in payload.get("orders", []) if isinstance(payload, dict) else []:
                order_id = item.get("id") or item.get("orderId")
                if order_id is not None:
                    result[int(order_id)] = item
            time.sleep(0.21)
        return result


class OrdersHistoryAPI(WBAPIBase):
    def __init__(self, client: WBClient | None = None):
        super().__init__(client or WBClient(base_url=WB_STATISTICS_BASE_URL))

    def list(self, date_from: date | str = "2019-01-01") -> list[dict[str, Any]]:
        value = date_from.isoformat() if isinstance(date_from, date) else date_from
        payload = self.client.get(WBEndpoints.ORDERS_HISTORY, params={"dateFrom": value, "flag": 0}, retries=1)
        return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []
