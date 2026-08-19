from typing import Any

from app.config import WB_MARKETPLACE_BASE_URL
from wb.base import WBAPIBase
from wb.client import WBClient
from wb.endpoints import WBEndpoints


class WarehousesAPI(WBAPIBase):
    """API для складов Wildberries."""

    def __init__(self, client: WBClient | None = None):
        super().__init__(client or WBClient(base_url=WB_MARKETPLACE_BASE_URL))

    def list(self, **kwargs: Any) -> list[dict[str, Any]]:
        payload = self.client.get(WBEndpoints.WAREHOUSES_LIST, params=kwargs)
        return payload if isinstance(payload, list) else []
