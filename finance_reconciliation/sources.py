from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Callable

from app.config import FINANCE_RECONCILIATION_YANDEX_API_DIR
from app.models import OzonFinanceAccrual, WBFinancialSalesRow
from finance_reconciliation.parsing import ParsedRow, _row_key, as_date, money


def _in_period(value: date | None, start: date | None, end: date | None) -> bool:
    if value is None:
        return start is None and end is None
    return (start is None or value >= start) and (end is None or value <= end)


def wb_api_rows(session: Any, start: date | None, end: date | None) -> list[ParsedRow]:
    query = session.query(WBFinancialSalesRow)
    if start:
        query = query.filter(WBFinancialSalesRow.rr_date >= start)
    if end:
        query = query.filter(WBFinancialSalesRow.rr_date < date.fromordinal(end.toordinal() + 1))
    result = []
    for item in query.all():
        raw = dict(item.raw_data or {})
        raw.update({"rrdId": item.rrd_id, "forPay": item.for_pay, "rrDate": item.rr_date, "sellerOperName": item.seller_operation_name})
        result.append(ParsedRow(str(item.rrd_id), money(item.for_pay) or 0, item.rr_date.date() if item.rr_date else None, "API", item.id, raw))
    return result


def ozon_api_rows(session: Any, start: date | None, end: date | None) -> list[ParsedRow]:
    query = session.query(OzonFinanceAccrual)
    if start:
        query = query.filter(OzonFinanceAccrual.accrual_date >= start)
    if end:
        query = query.filter(OzonFinanceAccrual.accrual_date <= end)
    result = []
    for item in query.all():
        raw = dict(item.raw_data or {})
        raw.update({"operationId": item.operation_id, "accrualType": item.accrual_type, "accrualDate": item.accrual_date, "amount": item.amount})
        key = _row_key(raw, "ozon")
        if key:
            result.append(ParsedRow(key, money(item.amount) or 0, item.accrual_date, "API", item.id, raw))
    return result


def _walk_dict_lists(value: Any):
    if isinstance(value, list):
        if value and all(isinstance(item, dict) for item in value):
            yield from value
        else:
            for item in value:
                yield from _walk_dict_lists(item)
    elif isinstance(value, dict):
        files = value.get("files")
        if isinstance(files, list):
            for file_item in files:
                if isinstance(file_item, (list, tuple)) and len(file_item) >= 2:
                    yield from _walk_dict_lists(file_item[1])
        for key, item in value.items():
            if key != "files":
                yield from _walk_dict_lists(item)


def yandex_api_rows(_session: Any, start: date | None, end: date | None) -> list[ParsedRow]:
    root = Path(FINANCE_RECONCILIATION_YANDEX_API_DIR)
    result: list[ParsedRow] = []
    seen: set[tuple[str, str]] = set()
    if not root.exists():
        return result
    for path in root.rglob("*.json"):
        if path.name == "state.json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for number, raw in enumerate(_walk_dict_lists(payload), 1):
            amount = money(raw.get("transactionSum"))
            key = _row_key(raw, "yandex_market")
            row_date = as_date(raw.get("transactionDate"))
            if key and amount is not None and _in_period(row_date, start, end):
                fingerprint = (key, str(amount))
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                result.append(ParsedRow(key, amount, row_date, str(path), number, raw))
    return result


SOURCE_LOADERS: dict[str, Callable[[Any, date | None, date | None], list[ParsedRow]]] = {
    "wb": wb_api_rows,
    "ozon": ozon_api_rows,
    "yandex_market": yandex_api_rows,
}
