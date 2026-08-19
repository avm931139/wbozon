from typing import Any

from app.config import WB_CONTENT_BASE_URL
from wb.base import WBAPIBase
from wb.client import WBClient
from wb.endpoints import WBEndpoints


class CategoriesAPI(WBAPIBase):
    """API для групп/категорий/предметов Wildberries."""

    def __init__(self, client: WBClient | None = None):
        super().__init__(client or WBClient(base_url=WB_CONTENT_BASE_URL))

    def list(self, **kwargs: Any) -> list[dict[str, Any]]:
        payload = self.client.get(WBEndpoints.CATEGORIES_LIST, params=kwargs)
        data = payload.get("data", []) if isinstance(payload, dict) else []
        return data if isinstance(data, list) else []
