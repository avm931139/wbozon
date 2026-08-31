from __future__ import annotations

from datetime import date
from typing import Any

from app.config import WB_FINANCE_BASE_URL
from wb.base import WBAPIBase
from wb.client import WBClient
from wb.endpoints import WBFinanceEndpoints
from wb.exceptions import WBParseError


class FinancesAPI(WBAPIBase):
    def __init__(self, client: WBClient | None = None):
        super().__init__(client or WBClient(base_url=WB_FINANCE_BASE_URL))

    def list(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self.sales_reports(**kwargs)

    def balance(self) -> dict[str, Any]:
        payload = self.client.get(WBFinanceEndpoints.BALANCE, retries=8)
        data = payload.get("data", payload) if isinstance(payload, dict) else {}
        if not isinstance(data, dict) or not any(
            key in data for key in ("currency", "current", "for_withdraw")
        ):
            raise WBParseError("WB balance response has an unexpected shape")
        return data

    def sales_reports(self, date_from: date, date_to: date, period: str = "weekly", limit: int = 100) -> list[dict[str, Any]]:
        return self._offset_pages("/api/finance/v1/sales-reports/list", {
            "dateFrom": date_from.isoformat(), "dateTo": date_to.isoformat(), "period": period
        }, limit)

    def sales_details(self, date_from: date, date_to: date, period: str = "weekly", limit: int = 100000, fields: list[str] | None = None) -> list[dict[str, Any]]:
        return self._rrd_pages("/api/finance/v1/sales-reports/detailed", {
            "dateFrom": date_from.isoformat(), "dateTo": date_to.isoformat(), "period": period
        }, limit, fields)

    def sales_details_by_report(self, report_id: int, limit: int = 100000, fields: list[str] | None = None) -> list[dict[str, Any]]:
        return self._rrd_pages(f"/api/finance/v1/sales-reports/detailed/{report_id}", {}, limit, fields)

    def acquiring_reports(self, date_from: date, date_to: date, limit: int = 100) -> list[dict[str, Any]]:
        return self._offset_pages("/api/finance/v1/acquiring/list", {
            "dateFrom": date_from.isoformat(), "dateTo": date_to.isoformat()
        }, limit)

    def acquiring_details(self, date_from: date, date_to: date, limit: int = 100000, fields: list[str] | None = None) -> list[dict[str, Any]]:
        return self._rrd_pages("/api/finance/v1/acquiring/detailed", {
            "dateFrom": date_from.isoformat(), "dateTo": date_to.isoformat()
        }, limit, fields)

    def acquiring_details_by_report(self, report_id: int, limit: int = 100000, fields: list[str] | None = None) -> list[dict[str, Any]]:
        return self._rrd_pages(f"/api/finance/v1/acquiring/detailed/{report_id}", {}, limit, fields)

    def _offset_pages(self, path: str, body: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        offset = 0
        while True:
            payload = self.client.post(path, json_body={**body, "limit": limit, "offset": offset}, retries=8)
            page = payload if isinstance(payload, list) else []
            result.extend(x for x in page if isinstance(x, dict))
            if len(page) < limit:
                return result
            offset += len(page)

    def _rrd_pages(self, path: str, body: dict[str, Any], limit: int, fields: list[str] | None) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        rrd_id = 0
        while True:
            request = {**body, "limit": limit, "rrdId": rrd_id}
            if fields:
                request["fields"] = fields
            payload = self.client.post(path, json_body=request, retries=8)
            page = payload if isinstance(payload, list) else []
            rows = [x for x in page if isinstance(x, dict)]
            result.extend(rows)
            if len(page) < limit or not rows:
                return result
            next_rrd_id = int(rows[-1].get("rrdId") or 0)
            if next_rrd_id <= rrd_id:
                return result
            rrd_id = next_rrd_id
