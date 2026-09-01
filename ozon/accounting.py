from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any

from ozon.client import OzonClient
from ozon.endpoints import OzonAccountingEndpoints
from ozon.exceptions import OzonParseError


ASYNC_FINANCE_REPORTS = {
    "COMPENSATION_REPORT": OzonAccountingEndpoints.COMPENSATION,
    "DECOMPENSATION_REPORT": OzonAccountingEndpoints.DECOMPENSATION,
    "DOCUMENT_B2B_SALES": OzonAccountingEndpoints.DOCUMENT_B2B_SALES,
    "MUTUAL_SETTLEMENT": OzonAccountingEndpoints.MUTUAL_SETTLEMENT,
}


def _month(value: date) -> str:
    return value.strftime("%Y-%m")


def _iso(value: date) -> str:
    return datetime.combine(value, time.min, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


class OzonAccountingAPI:
    """Current Ozon Finance/Report methods used by the accounting worker."""

    def __init__(self, client: OzonClient | None = None) -> None:
        self.client = client or OzonClient()

    def create_monthly_report(self, report_type: str, period_start: date) -> dict[str, Any]:
        if report_type == "REALIZATION_POSTING_REPORT":
            payload = self.client.post(
                OzonAccountingEndpoints.REALIZATION_POSTING_REPORT,
                json_body={"year": period_start.year, "month": period_start.month},
                retries=6,
            )
            if not isinstance(payload, dict) or not isinstance(payload.get("code"), str) or not payload["code"]:
                raise OzonParseError("Ozon realization posting report response does not contain code")
            return payload
        try:
            path = ASYNC_FINANCE_REPORTS[report_type]
        except KeyError as exc:
            raise ValueError(f"unsupported Ozon finance report type: {report_type}") from exc
        payload = self.client.post(
            path,
            json_body={"date": _month(period_start), "language": "RU"},
            retries=6,
        )
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict) or not isinstance(result.get("code"), str) or not result["code"]:
            raise OzonParseError("Ozon finance report response does not contain result.code")
        return payload

    def reports(self, report_type: str = "ALL", page_size: int = 1000) -> list[dict[str, Any]]:
        if not 1 <= page_size <= 1000:
            raise ValueError("page_size must be between 1 and 1000")
        rows: list[dict[str, Any]] = []
        page = 1
        seen_pages: set[tuple[str, ...]] = set()
        while True:
            payload = self.client.post(
                OzonAccountingEndpoints.REPORT_LIST,
                json_body={"page": page, "page_size": page_size, "report_type": report_type},
                retries=6,
            )
            result = payload.get("result") if isinstance(payload, dict) else None
            current = result.get("reports") if isinstance(result, dict) else None
            if not isinstance(current, list) or any(not isinstance(item, dict) for item in current):
                raise OzonParseError("Ozon report list response has an invalid result.reports")
            signature = tuple(str(item.get("code") or "") for item in current)
            if current and signature in seen_pages:
                raise OzonParseError("Ozon report list pagination repeated the same page")
            seen_pages.add(signature)
            rows.extend(current)
            total = result.get("total")
            if len(current) < page_size or (isinstance(total, int) and len(rows) >= total):
                return rows
            page += 1

    def report_info(self, code: str) -> dict[str, Any]:
        if not isinstance(code, str) or not code.strip():
            raise ValueError("report code is required")
        payload = self.client.post(
            OzonAccountingEndpoints.REPORT_INFO,
            json_body={"code": code.strip()},
            retries=6,
        )
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict) or not result.get("code"):
            raise OzonParseError("Ozon report info response has an invalid result")
        return result

    def b2b_sales_json(self, period_start: date) -> dict[str, Any]:
        return self._dict(
            OzonAccountingEndpoints.DOCUMENT_B2B_SALES_JSON,
            {"date": _month(period_start)},
            "B2B sales JSON",
        )

    def realization(self, period_start: date) -> dict[str, Any]:
        return self._dict(
            OzonAccountingEndpoints.REALIZATION,
            {"year": period_start.year, "month": period_start.month},
            "realization",
        )

    def realization_posting(self, period_start: date) -> dict[str, Any]:
        return self._dict(
            OzonAccountingEndpoints.REALIZATION_POSTING,
            {"year": period_start.year, "month": period_start.month},
            "realization posting",
        )

    def products_buyout(self, date_from: date, date_to: date) -> dict[str, Any]:
        # Ozon counts both boundary dates, so a 31-day report has a 30-day delta.
        self._validate_period(date_from, date_to, 30)
        return self._dict(
            OzonAccountingEndpoints.PRODUCTS_BUYOUT,
            {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
            "products buyout",
        )

    def balance(self, date_from: date, date_to: date) -> dict[str, Any]:
        self._validate_period(date_from, date_to, 30)
        return self._dict(
            OzonAccountingEndpoints.BALANCE,
            {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
            "balance",
        )

    def cash_flow(self, date_from: date, date_to: date, page_size: int = 100) -> dict[str, Any]:
        if date_from > date_to:
            raise ValueError("date_from must not be after date_to")
        if page_size < 1:
            raise ValueError("page_size must be positive")
        cash_flows: list[Any] = []
        details: list[Any] = []
        page = 1
        while True:
            payload = self._dict(
                OzonAccountingEndpoints.CASH_FLOW,
                {
                    "date": {"from": _iso(date_from), "to": _iso(date_to)},
                    "with_details": True,
                    "page": page,
                    "page_size": page_size,
                },
                "cash flow",
            )
            result = payload.get("result")
            if not isinstance(result, dict):
                raise OzonParseError("Ozon cash flow response has an invalid result")
            current = result.get("cash_flows") or []
            if not isinstance(current, list):
                raise OzonParseError("Ozon cash flow response has invalid cash_flows")
            cash_flows.extend(current)
            if result.get("details") is not None:
                details.append(result["details"])
            page_count = payload.get("page_count", result.get("page_count"))
            if not current or (isinstance(page_count, int) and page >= page_count) or len(current) < page_size:
                return {"result": {"cash_flows": cash_flows, "details": details}}
            page += 1

    def _dict(self, path: str, body: dict[str, Any], name: str) -> dict[str, Any]:
        payload = self.client.post(path, json_body=body, retries=6)
        if not isinstance(payload, dict):
            raise OzonParseError(f"Ozon {name} response is not an object")
        return payload

    @staticmethod
    def _validate_period(date_from: date, date_to: date, max_days: int) -> None:
        if date_from > date_to:
            raise ValueError("date_from must not be after date_to")
        if (date_to - date_from).days > max_days:
            raise ValueError(f"period must not exceed {max_days} days")
