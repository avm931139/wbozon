from __future__ import annotations

import json
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.config import OPERATIONS_TG_BOT_TOKEN, OPERATIONS_TG_CHAT_ID, OPERATIONS_TG_PROXY_URL
from app.db import SessionLocal
from supply_movement_report.collectors import (
    ozon_returns, ozon_supplies, wb_returns, wb_supplies, yandex_movements,
)
from telegram_bot.client import TelegramClient


DEFAULT_PATH = Path("data/supply_movement_reports/marketplace_supplies_and_returns_all.xlsx")
MOSCOW = ZoneInfo("Europe/Moscow")


def _cell(value: Any) -> Any:
    if isinstance(value, datetime) and value.tzinfo:
        value = value.astimezone(MOSCOW).replace(tzinfo=None)
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        value = "'" + value
    return value[:32760] if isinstance(value, str) else value


class SupplyMovementReportService:
    def __init__(self, *, session_factory: Callable[..., Any] = SessionLocal) -> None:
        self.session_factory = session_factory

    @staticmethod
    def _cached_rows(path: Path, sheet_name: str) -> list[dict[str, Any]]:
        if not path.exists(): return []
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            if sheet_name not in workbook.sheetnames: return []
            values = workbook[sheet_name].iter_rows(values_only=True)
            headers = next(values, None)
            if not headers or headers[0] == "Данных нет": return []
            return [dict(zip(headers, row)) for row in values if any(value is not None for value in row)]
        finally:
            workbook.close()

    @staticmethod
    def _add_sheet(workbook: Workbook, title: str, rows: list[dict[str, Any]]) -> None:
        ws = workbook.create_sheet(title)
        if not rows:
            ws.append(["Данных нет"])
            return
        columns = []
        for row in rows:
            for key in row:
                if key not in columns: columns.append(key)
        ws.append(columns)
        for cell in ws[1]:
            cell.fill = PatternFill("solid", fgColor="1F4E78")
            cell.font = Font(color="FFFFFF", bold=True)
            cell.alignment = Alignment(wrap_text=True)
        for row in rows:
            ws.append([_cell(row.get(key)) for key in columns])
        ws.freeze_panes = "A2"; ws.auto_filter.ref = ws.dimensions
        for index, key in enumerate(columns, 1):
            width = 18 if len(key) < 18 else min(42, len(key) + 2)
            ws.column_dimensions[get_column_letter(index)].width = width

    def build(self, *, include_live_returns: bool = True) -> tuple[bytes, dict[str, Any]]:
        today = date.today(); errors = {}; warnings = {}; data = {}
        with self.session_factory() as session:
            for key, callback in (("WB · Поставки", lambda: wb_supplies(session)), ("Ozon · Поставки", lambda: ozon_supplies(session))):
                try: data[key] = callback()
                except Exception as exc: errors[key] = f"{type(exc).__name__}: {exc}"; data[key] = []
            try:
                ym_supply, ym_return, ym_warnings = yandex_movements(session, today)
                data["Яндекс · Поставки"] = ym_supply; data["Яндекс · Возвраты"] = ym_return
                if ym_warnings:
                    warnings["Яндекс · Заявки"] = "; ".join(ym_warnings)
            except Exception as exc:
                errors["Яндекс · Заявки"] = f"{type(exc).__name__}: {exc}"
                data["Яндекс · Поставки"] = []; data["Яндекс · Возвраты"] = []
            if include_live_returns:
                cached_wb = self._cached_rows(DEFAULT_PATH.resolve(), "WB · Возвраты")
                try:
                    refresh_from = today.replace(day=1) if cached_wb else None
                    fresh_wb = wb_returns(session, today, refresh_from)
                    merged = {(row.get("Возврат/заказ"), row.get("ШК единицы")): row for row in cached_wb}
                    merged.update({(row.get("Возврат/заказ"), row.get("ШК единицы")): row for row in fresh_wb})
                    data["WB · Возвраты"] = list(merged.values())
                except Exception as exc:
                    if cached_wb:
                        data["WB · Возвраты"] = cached_wb
                        warnings["WB · Возвраты"] = f"Использован локальный кэш; обновление текущего месяца: {type(exc).__name__}: {exc}"
                    else:
                        errors["WB · Возвраты"] = f"{type(exc).__name__}: {exc}"; data["WB · Возвраты"] = []
                try: data["Ozon · Возвраты"] = ozon_returns(session, today)
                except Exception as exc: errors["Ozon · Возвраты"] = f"{type(exc).__name__}: {exc}"; data["Ozon · Возвраты"] = []
            else:
                data["WB · Возвраты"] = []; data["Ozon · Возвраты"] = []

        workbook = Workbook(); summary = workbook.active; summary.title = "Итог"
        summary.append(["Отчёт", "Поставки товаров и обратные движения за весь доступный период"])
        summary.append(["Сформирован", datetime.now(MOSCOW).replace(tzinfo=None)])
        summary.append(["Источник", "Поставки WB/Ozon — PostgreSQL; возвраты WB/Ozon и заявки Яндекса — актуальный API"])
        summary.append([]); summary.append(["Лист", "Строк", "Отправлено/план", "Принято/факт", "Статус источника"])
        for cell in summary[5]: cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="1F4E78")
        order = ("WB · Поставки", "WB · Возвраты", "Ozon · Поставки", "Ozon · Возвраты", "Яндекс · Поставки", "Яндекс · Возвраты")
        for key in order:
            rows = data.get(key, [])
            planned = sum((row.get("Отправлено, шт.") or row.get("Отправлено/план, шт.") or row.get("К возврату, шт.") or row.get("Количество, шт.") or 0) for row in rows)
            actual = sum((row.get("Принято, шт.") or row.get("Принято/факт, шт.") or row.get("Фактически, шт.") or 0) for row in rows)
            source_status = errors.get(key) or warnings.get(key)
            if not source_status and key.startswith("Яндекс"):
                source_status = errors.get("Яндекс · Заявки") or warnings.get("Яндекс · Заявки")
            summary.append([key, len(rows), planned, actual, source_status or "OK"])
            self._add_sheet(workbook, key, rows)
        if errors:
            self._add_sheet(workbook, "Ошибки источников", [{"Источник": key, "Ошибка": value} for key, value in errors.items()])
        if warnings:
            self._add_sheet(workbook, "Ограничения API", [{"Источник": key, "Ограничение": value} for key, value in warnings.items()])
        summary.column_dimensions["A"].width = 26; summary.column_dimensions["B"].width = 85
        stream = BytesIO(); workbook.save(stream); workbook.close()
        return stream.getvalue(), {"sheets": {key: len(data.get(key, [])) for key in order}, "errors": errors, "warnings": warnings}

    def save(self, destination: str | Path = DEFAULT_PATH, *, include_live_returns: bool = True) -> dict[str, Any]:
        path = Path(destination).resolve(); path.parent.mkdir(parents=True, exist_ok=True)
        content, result = self.build(include_live_returns=include_live_returns)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_bytes(content); temporary.replace(path)
        return {"path": str(path), "bytes": len(content), **result}

    def send_telegram(self, destination: str | Path = DEFAULT_PATH) -> dict[str, Any]:
        result = self.save(destination)
        if not OPERATIONS_TG_BOT_TOKEN or not OPERATIONS_TG_CHAT_ID:
            raise RuntimeError("operations Telegram bot/chat is not configured")
        path = Path(result["path"])
        client = TelegramClient(OPERATIONS_TG_BOT_TOKEN, OPERATIONS_TG_CHAT_ID, proxy_url=OPERATIONS_TG_PROXY_URL)
        result["telegram_message_id"] = client.send_document(path.name, path.read_bytes(), caption="Поставки и возвраты по WB, Ozon и Яндекс Маркету за весь доступный период")
        return result
