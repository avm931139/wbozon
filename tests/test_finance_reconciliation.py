from datetime import date
from decimal import Decimal

from openpyxl import Workbook

from finance_reconciliation.parsing import ParsedRow, parse_export
from finance_reconciliation.report import compare


def test_parse_wb_export_with_header_after_title(tmp_path):
    path = tmp_path / "wb_финансы_2026-08.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Отчёт Wildberries"])
    sheet.append(["rrdId", "rrDate", "forPay", "sellerOperName"])
    sheet.append([101, "2026-08-02", "125,50", "Продажа"])
    workbook.save(path)
    workbook.close()

    parsed = parse_export(path)

    assert parsed.marketplace == "wb"
    assert parsed.period_start == date(2026, 8, 2)
    assert parsed.rows[0].key == "101"
    assert parsed.rows[0].amount == Decimal("125.50")


def test_month_is_taken_from_filename_when_rows_have_no_dates(tmp_path):
    path = tmp_path / "ozon_финансы_2026-08.csv"
    path.write_text("operationId;accrualType;amount\n42;ITEM;10.00\n", encoding="utf-8")

    parsed = parse_export(path)

    assert parsed.period_start == date(2026, 8, 1)
    assert parsed.period_end == date(2026, 8, 31)


def test_compare_detects_both_missing_sides_and_amount_difference():
    cabinet = [
        ParsedRow("same", Decimal("10.02"), None, "cabinet", 2, {}),
        ParsedRow("cabinet-only", Decimal("5"), None, "cabinet", 3, {}),
    ]
    api = [
        ParsedRow("same", Decimal("10.00"), None, "api", 1, {}),
        ParsedRow("api-only", Decimal("7"), None, "api", 2, {}),
    ]

    result = compare(cabinet, api, Decimal("0.01"))

    assert result.status == "mismatch"
    assert len(result.amount_mismatches) == 1
    assert len(result.missing_in_api) == 1
    assert len(result.missing_in_cabinet) == 1


def test_compare_accepts_amount_within_tolerance():
    cabinet = [ParsedRow("same", Decimal("10.005"), None, "cabinet", 2, {})]
    api = [ParsedRow("same", Decimal("10.00"), None, "api", 1, {})]

    assert compare(cabinet, api, Decimal("0.01")).status == "correct"
