from __future__ import annotations

from datetime import date, datetime, time
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill


MARKET_NAMES = {"wb": "Wildberries", "ozon": "Ozon", "yandex_market": "Яндекс Маркет"}


def _cell_value(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return value


def _finish(workbook: Workbook) -> bytes:
    for sheet in workbook.worksheets:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="315B8A")
        for column in sheet.columns:
            letter = column[0].column_letter
            width = min(55, max(12, max(len(str(cell.value or "")) for cell in column) + 2))
            sheet.column_dimensions[letter].width = width
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def operational_excel(data: dict[str, Any]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Показатели"
    sheet.append(["Площадка", "Заказы, шт.", "Заказы, ₽", "Отмены, шт.",
                  "Выкупы, шт.", "Выкупы, ₽", "Реклама, ₽", "Остаток, шт.",
                  "Остаток в себестоимости, ₽"])
    for key, values in data["marketplaces"].items():
        ads = data.get("ads", {}).get(key, {})
        stocks = data.get("stocks", {}).get(key, {})
        sheet.append([MARKET_NAMES[key], values.get("orders"), values.get("orders_amount"),
                      values.get("cancelled"), values.get("buyouts"), values.get("buyouts_amount"),
                      ads.get("spend"), stocks.get("units"), stocks.get("cost_value")])
    cabinet = workbook.create_sheet("Кабинетная аналитика")
    cabinet.append(["Площадка", "Покрытие полное", "Дней с данными", "Ожидалось дней",
                    "Заказано, шт.", "Заказано, ₽", "Выкуплено, шт.", "Выкуплено, ₽",
                    "Отменено, шт.", "Отменено, ₽", "Источник"])
    for key, values in data.get("cabinet_analytics", {}).items():
        cabinet.append([MARKET_NAMES[key], bool(values.get("complete")), values.get("coverage_days"),
                        values.get("expected_days"), values.get("ordered_items"), values.get("ordered_amount"),
                        values.get("purchased_items"), values.get("purchased_amount"),
                        values.get("cancelled_items"), values.get("cancelled_amount"), values.get("source")])
    series = workbook.create_sheet("Заказы по дням")
    series.append(["Дата", "Площадка", "Заказы, шт.", "Сумма, ₽"])
    for row in data.get("series", []):
        series.append([row.get("day"), MARKET_NAMES.get(row.get("marketplace"), row.get("marketplace")),
                       row.get("orders"), row.get("revenue")])
    return _finish(workbook)


def pnl_excel(data: dict[str, Any]) -> bytes:
    workbook = Workbook()
    summary = workbook.active
    summary.title = "P&L"
    summary.append(["Площадка", "Период с", "Период по", "Продажи, ₽", "Компенсации, ₽", "Выручка, ₽",
                    "Расходы МП, ₽", "К выплате, ₽", "Себестоимость, ₽", "Прибыль, ₽"])
    total = data["total"]
    period = data.get("period", {})
    summary.append(["ИТОГО", period.get("from"), period.get("to"), total.get("sales_revenue"), total.get("compensation"),
                    total.get("revenue"), total.get("expenses"), total.get("net_payout"),
                    total.get("cost_of_goods"), total.get("profit")])
    for key, values in data["marketplaces"].items():
        if not values.get("available"):
            summary.append([MARKET_NAMES[key], period.get("from"), period.get("to"), "Нет полного финансового отчёта"])
            continue
        summary.append([MARKET_NAMES[key], period.get("from"), period.get("to"), values.get("sales_revenue"), values.get("compensation"),
                        values.get("revenue"), values.get("expenses"), values.get("net_payout"),
                        values.get("cost_of_goods"), values.get("profit")])
    expenses = workbook.create_sheet("Расходы")
    expenses.append(["Площадка", "Статья", "Категория", "Сумма, ₽", "% выручки", "Источник"])
    for key, values in data["marketplaces"].items():
        for row in values.get("expense_lines", []):
            expenses.append([MARKET_NAMES[key], row.get("label"), row.get("category_label"),
                             row.get("amount"), row.get("share_percent"), row.get("source")])
    return _finish(workbook)


def stocks_excel(data: dict[str, Any]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Остатки"
    sheet.append(["Артикул", "Наименование", "Себестоимость, ₽", "Дата себестоимости",
                  "WB, шт.", "WB обновлено", "Ozon, шт.", "Ozon обновлено",
                  "Яндекс, шт.", "Яндекс обновлено"])
    for row in data.get("rows", []):
        sheet.append([_cell_value(value) for value in (
            row.get("article"), row.get("name"), row.get("unit_cost"),
            row.get("cost_updated_at"), row["wb"].get("quantity"),
            row["wb"].get("updated_at"), row["ozon"].get("quantity"),
            row["ozon"].get("updated_at"), row["yandex_market"].get("quantity"),
            row["yandex_market"].get("updated_at"),
        )])
    return _finish(workbook)


def abc_excel(data: dict[str, Any]) -> bytes:
    workbook = Workbook()
    matrix = workbook.active
    matrix.title = "ABC-матрица"
    scopes = (("total", "Итого"), ("wb", "Wildberries"), ("ozon", "Ozon"),
              ("yandex_market", "Яндекс Маркет"))
    header = ["Артикул", "Наименование", "Нераспределённая строка"]
    for _, name in scopes:
        header.extend([
            f"{name}: выручка, ₽", f"{name}: ABC выручки", f"{name}: доля выручки, %",
            f"{name}: прибыль, ₽", f"{name}: ABC прибыли", f"{name}: маржа, %",
            f"{name}: реклама, ₽", f"{name}: ДРР, %",
            f"{name}: логистика, ₽", f"{name}: логистика, %", f"{name}: логистика на шт., ₽",
        ])
    matrix.append(header)
    for row in data.get("rows", []):
        values: list[Any] = [row.get("article"), row.get("name"), bool(row.get("is_unallocated"))]
        for key, _ in scopes:
            metric = row.get(key) or {}
            if not metric.get("available"):
                values.extend([None] * 11)
                continue
            values.extend([
                metric.get("revenue_kopecks", 0) / 100, metric.get("revenue_category"),
                metric.get("revenue_share_percent"), metric.get("profit_kopecks", 0) / 100,
                metric.get("profit_category"), metric.get("profit_margin_percent"),
                metric.get("advertising_kopecks", 0) / 100, metric.get("advertising_drr_percent"),
                metric.get("logistics_kopecks", 0) / 100, metric.get("logistics_share_percent"),
                (metric["logistics_per_unit_kopecks"] / 100
                 if metric.get("logistics_per_unit_kopecks") is not None else None),
            ])
        matrix.append(values)

    calculation = workbook.create_sheet("Расчёт по SKU")
    calculation.append(["Площадка", "Артикул", "Наименование", "Количество",
                        "Выручка, коп.", "Расходы МП, коп.", "Себестоимость, коп.",
                        "Прибыль, коп.", "Реклама, коп.", "Логистика, коп.",
                        "Метод расходов", "Метод рекламы", "Строк без себестоимости"])
    for row in data.get("rows", []):
        for key, name in scopes[1:]:
            metric = row.get(key)
            if not metric:
                continue
            calculation.append([name, row.get("article"), row.get("name"), metric.get("units"),
                                metric.get("revenue_kopecks"), metric.get("expense_kopecks"),
                                metric.get("cost_kopecks"), metric.get("profit_kopecks"),
                                metric.get("advertising_kopecks"), metric.get("logistics_kopecks"),
                                metric.get("expense_allocation_method"),
                                metric.get("advertising_allocation_method"),
                                metric.get("missing_cost_rows")])

    control = workbook.create_sheet("Контроль")
    control.append(["Площадка", "Покрытие", "Дней", "Ожидалось", "Выручка слоя, коп.",
                    "Выручка строк, коп.", "Разница, коп.", "Прибыль слоя, коп.",
                    "Прибыль строк, коп.", "Разница, коп.", "Нераспределённая реклама, коп."])
    for key, name in scopes[1:]:
        item = data.get("controls", {}).get(key, {})
        control.append([name, bool(item.get("available")), item.get("coverage_days"),
                        item.get("expected_days"), item.get("revenue_kopecks"),
                        item.get("revenue_actual_kopecks"), item.get("revenue_delta_kopecks"),
                        item.get("profit_kopecks"), item.get("profit_actual_kopecks"),
                        item.get("profit_delta_kopecks"), item.get("advertising_unallocated_kopecks")])

    methodology = workbook.create_sheet("Методика")
    methodology.append(["Параметр", "Значение"])
    methodology.append(["Период", f"{data['period']['from']} — {data['period']['to']}"])
    for key, value in data.get("methodology", {}).items():
        methodology.append([key, value])
    return _finish(workbook)
