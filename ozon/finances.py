from __future__ import annotations

from datetime import date
from typing import Any
from ozon.client import OzonClient
from ozon.endpoints import OzonFinanceEndpoints
from ozon.exceptions import OzonParseError


class OzonFinancesAPI:
    def __init__(self, client: OzonClient | None = None) -> None:
        self.client = client or OzonClient()

    def accruals_by_day(self, date_from: date, date_to: date) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        current = date_from
        while current <= date_to:
            last_id = ""
            while True:
                body = {"date": current.isoformat(), "last_id": last_id}
                payload = self.client.post(OzonFinanceEndpoints.ACCRUAL_BY_DAY, json_body=body)
                page = payload.get("accruals", []) if isinstance(payload, dict) else []
                rows.extend(x for x in page if isinstance(x, dict))
                next_id = str(payload.get("last_id") or "") if isinstance(payload, dict) else ""
                if not page or not next_id or next_id == last_id:
                    break
                last_id = next_id
            current = date.fromordinal(current.toordinal() + 1)
        return rows

    def accrual_types(self) -> list[dict[str, Any]]:
        payload = self.client.post(OzonFinanceEndpoints.ACCRUAL_TYPES, json_body={})
        rows = payload.get("accrual_types") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise OzonParseError("Ozon accrual types response is invalid")
        return rows

    def accruals_by_postings(self, posting_numbers: list[str]) -> list[dict[str, Any]]:
        if not 1 <= len(posting_numbers) <= 200:
            raise ValueError("posting_numbers must contain between 1 and 200 values")
        if any(not isinstance(value, str) or not value.strip() for value in posting_numbers):
            raise ValueError("posting numbers must be non-empty strings")
        payload = self.client.post(
            OzonFinanceEndpoints.ACCRUAL_POSTINGS,
            json_body={"posting_numbers": [value.strip() for value in posting_numbers]},
        )
        rows = payload.get("posting_accruals") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise OzonParseError("Ozon posting accruals response is invalid")
        return rows
