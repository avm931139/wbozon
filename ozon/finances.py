from __future__ import annotations

from datetime import date
from typing import Any
from ozon.client import OzonClient


class OzonFinancesAPI:
    def __init__(self, client: OzonClient | None = None) -> None:
        self.client = client or OzonClient()

    def accruals_by_day(self, date_from: date, date_to: date) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        current = date_from
        while current <= date_to:
            last_id = ""
            while True:
                body = {"date": current.isoformat(), **({"last_id": last_id} if last_id else {})}
                payload = self.client.post("/v1/finance/accrual/by-day", json_body=body)
                page = payload.get("accruals", []) if isinstance(payload, dict) else []
                rows.extend(x for x in page if isinstance(x, dict))
                next_id = str(payload.get("last_id") or "") if isinstance(payload, dict) else ""
                if not page or not next_id or next_id == last_id:
                    break
                last_id = next_id
            current = date.fromordinal(current.toordinal() + 1)
        return rows
