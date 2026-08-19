from typing import Any

from app.config import WB_MARKETPLACE_BASE_URL
from wb.base import WBAPIBase
from wb.client import WBClient
from wb.endpoints import WBEndpoints


class StocksAPI(WBAPIBase):
    """API для остатков Wildberries."""

    def __init__(self, client: WBClient | None = None):
        super().__init__(client or WBClient(base_url=WB_MARKETPLACE_BASE_URL))

    def list(self, **kwargs: Any) -> list[dict[str, Any]]:
        warehouse_id = kwargs.get("warehouse_id")
        chrt_ids = kwargs.get("chrt_ids")
        if warehouse_id is None:
            raise ValueError("warehouse_id is required")
        if not isinstance(chrt_ids, list):
            raise ValueError("chrt_ids must be a list")

        path = WBEndpoints.STOCKS_LIST.format(warehouse_id=warehouse_id)
        payload = self.client.post(path, json_body={"chrtIds": chrt_ids})
        stocks = payload.get("stocks", []) if isinstance(payload, dict) else []
        if not isinstance(stocks, list):
            return []
        return [{**item, "warehouseId": warehouse_id} for item in stocks if isinstance(item, dict)]
