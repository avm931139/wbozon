from datetime import datetime
from decimal import Decimal

from openpyxl import Workbook

from product_costs.importer import ProductCostImporter


def test_read_skips_blank_cost_and_preserves_quantity(tmp_path):
    path = tmp_path / "costs.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Себестоимость"
    headers = [None] * 17
    headers[0] = "ID товара (не менять)"
    headers[1] = "Базовый артикул (не менять)"
    headers[3] = "Себестоимость 1 шт., ₽"
    headers[4] = "Количество на текущий момент, шт."
    headers[16] = "Дата фиксации остатков"
    sheet.append(headers)
    sheet.append([1, "SKU-1", "One", 123.4567894, 8] + [None] * 11 + [datetime(2026, 9, 6)])
    sheet.append([2, "SKU-2", "Two", None, 9] + [None] * 11 + [datetime(2026, 9, 6)])
    workbook.save(path)
    workbook.close()

    rows, total, skipped = ProductCostImporter._read(path)

    assert total == 2
    assert skipped == 1
    assert len(rows) == 1
    assert rows[0]["unit_cost"] == Decimal("123.456789")
    assert rows[0]["quantity"] == 8
