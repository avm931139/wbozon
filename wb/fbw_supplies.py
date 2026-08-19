from __future__ import annotations

from datetime import date
from typing import Any

from app.config import WB_SUPPLIES_BASE_URL
from wb.base import WBAPIBase
from wb.client import WBClient


class FBWSuppliesAPI(WBAPIBase):
    def __init__(self, client: WBClient | None = None):
        super().__init__(client or WBClient(base_url=WB_SUPPLIES_BASE_URL))

    def warehouses(self) -> list[dict[str, Any]]:
        payload = self.client.get("/api/v1/warehouses")
        return [x for x in payload if isinstance(x, dict)] if isinstance(payload, list) else []

    def supplies(self, date_from: date, date_to: date, limit: int = 1000) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        offset = 0
        body = {"dates": [{"from": date_from.isoformat(), "till": date_to.isoformat(), "type": "createDate"}], "statusIDs": [1, 2, 3, 4, 5, 6]}
        while True:
            payload = self.client.post(f"/api/v1/supplies?limit={limit}&offset={offset}", json_body=body)
            page = [x for x in payload if isinstance(x, dict)] if isinstance(payload, list) else []
            result.extend(page)
            if len(page) < limit:
                break
            offset += len(page)
        return result

    def list(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.supplies(**kwargs)

    def details(self, identifier: int, is_preorder: bool = False) -> dict[str, Any]:
        payload = self.client.get(f"/api/v1/supplies/{identifier}", params={"isPreorderID": str(is_preorder).lower()}, retries=8)
        return payload if isinstance(payload, dict) else {}

    def goods(self, identifier: int, is_preorder: bool = False, limit: int = 1000) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        offset = 0
        while True:
            payload = self.client.get(f"/api/v1/supplies/{identifier}/goods", params={"limit": limit, "offset": offset, "isPreorderID": str(is_preorder).lower()}, retries=8)
            page = [x for x in payload if isinstance(x, dict)] if isinstance(payload, list) else []
            result.extend(page)
            if len(page) < limit:
                break
            offset += len(page)
        return result

    def packages(self, supply_id: int) -> list[dict[str, Any]]:
        payload = self.client.get(f"/api/v1/supplies/{supply_id}/package", retries=8)
        return [x for x in payload if isinstance(x, dict)] if isinstance(payload, list) else []
