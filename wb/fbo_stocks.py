from typing import Any

from app.config import WB_ANALYTICS_BASE_URL
from wb.base import WBAPIBase
from wb.client import WBClient
from wb.endpoints import WBEndpoints


class FBOStocksAPI(WBAPIBase):
    """Current inventory by product size and WB (FBO) warehouse."""

    def __init__(self, client: WBClient | None = None):
        super().__init__(client or WBClient(base_url=WB_ANALYTICS_BASE_URL))

    def list(self, **kwargs: Any) -> list[dict[str, Any]]:
        limit = int(kwargs.get("limit", 250000))
        offset = int(kwargs.get("offset", 0))
        nm_ids = kwargs.get("nm_ids", [])
        chrt_ids = kwargs.get("chrt_ids", [])
        result: list[dict[str, Any]] = []

        while True:
            payload = self.client.post(
                WBEndpoints.FBO_STOCKS_LIST,
                json_body={
                    "nmIds": nm_ids,
                    "chrtIds": chrt_ids,
                    "limit": limit,
                    "offset": offset,
                },
            )
            items = payload.get("data", {}).get("items", []) if isinstance(payload, dict) else []
            if not isinstance(items, list):
                break
            page = [item for item in items if isinstance(item, dict)]
            result.extend(page)
            if len(page) < limit:
                break
            offset += len(page)

        return result
