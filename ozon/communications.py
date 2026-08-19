from __future__ import annotations

from typing import Any
from ozon.client import OzonClient


class OzonCommunicationsAPI:
    def __init__(self, client: OzonClient | None = None) -> None:
        self.client = client or OzonClient()

    def reviews(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._cursor("/v1/review/list", "reviews", {"limit": limit, "sort_dir": "DESC"})

    def questions(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._cursor("/v1/question/list", "questions", {"limit": limit, "sort_dir": "DESC"})

    def _cursor(self, path: str, key: str, body: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        last_id = ""
        while True:
            payload = self.client.post(path, json_body={**body, **({"last_id": last_id} if last_id else {})})
            result = payload.get("result", payload) if isinstance(payload, dict) else {}
            page = result.get(key, []) if isinstance(result, dict) else []
            rows.extend(x for x in page if isinstance(x, dict))
            next_id = str(result.get("last_id") or "") if isinstance(result, dict) else ""
            if not page or not next_id or next_id == last_id:
                return rows
            last_id = next_id
