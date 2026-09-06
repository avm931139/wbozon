from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import func

from app.db import SessionLocal
from app.models import (
    OzonAdDailyStat,
    OzonPosting,
    OzonStock,
    OzonSyncRun,
    WBFBSStock,
    WBFboStock,
    WBSyncRun,
    YandexMarketOrder,
    YandexMarketStock,
    YandexMarketSyncRun,
)
from wb.services.customer_communication_service import CustomerCommunicationService
from wb.services.promotion_service import PromotionService
from wb.services.sales_service import SalesService


def _money(value: Any) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    return f"{amount:,.2f}".replace(",", " ") + " ₽"


def _metric(value: Any, suffix: str = "") -> str:
    return "—" if value is None else f"{value}{suffix}"


def _ozon_order_amount(products: Any) -> Decimal:
    total = Decimal("0")
    for product in products if isinstance(products, list) else []:
        if not isinstance(product, dict):
            continue
        try:
            raw_price = product.get("price") or 0
            if isinstance(raw_price, dict):
                raw_price = raw_price.get("amount") or raw_price.get("value") or 0
            price = Decimal(str(raw_price))
            quantity = int(product.get("quantity") or 0)
        except (ArithmeticError, TypeError, ValueError):
            continue
        total += price * quantity
    return total


class TelegramReportService:
    def __init__(
        self,
        *,
        timezone_name: str = "Europe/Moscow",
        low_stock_threshold: int = 5,
        session_factory: Callable[..., Any] = SessionLocal,
        sales_summary: Callable[[date, date], dict[str, Any]] = SalesService.summary,
        promotion_service: PromotionService | None = None,
        quality_summary: Callable[[], dict[str, Any]] = CustomerCommunicationService.quality_summary,
    ) -> None:
        self.timezone = ZoneInfo(timezone_name)
        self.low_stock_threshold = low_stock_threshold
        self.session_factory = session_factory
        self.sales_summary = sales_summary
        self.promotion = promotion_service or PromotionService(session_factory=session_factory)
        self.quality_summary = quality_summary

    def morning(self, now: datetime | None = None) -> str:
        now = self._local(now)
        yesterday = now.date() - timedelta(days=1)
        month_start = now.date().replace(day=1)
        parts = [f"WB — утренний отчёт {now:%d.%m.%Y %H:%M}", self._sales_block("ПРОШЛЫЙ ДЕНЬ", self.sales_summary(yesterday, yesterday))]
        if month_start <= yesterday:
            parts.append(self._sales_block("ТЕКУЩИЙ МЕСЯЦ ПО ВЧЕРА", self.sales_summary(month_start, yesterday)))
            parts.append(self._ads_block("РЕКЛАМА: МЕСЯЦ ПО ВЧЕРА", month_start, yesterday))
        else:
            parts.append("ТЕКУЩИЙ МЕСЯЦ ПО ВЧЕРА\nПериод ещё не начался.")
        parts.extend([self._ads_block("РЕКЛАМА: ПРОШЛЫЙ ДЕНЬ", yesterday, yesterday), self._stock_block(), self._communication_block(), self._sync_block()])
        return "\n\n".join(parts)

    def operational(self, now: datetime | None = None) -> str:
        """Return the complete report as text for backwards-compatible callers."""
        return "\n\n".join(text for _, text in self.operational_messages(now))

    def operational_messages(self, now: datetime | None = None) -> list[tuple[str, str]]:
        now = self._local(now)
        today = now.date()
        wb_sales = self.sales_summary(today, today)
        wb_ads = self.promotion.efficiency_summary(date_from=today, date_to=today)
        wb_stock = self._wb_stock_data()
        ozon_orders = self._ozon_orders_data(now)
        ozon_ads = self._ozon_ads_data(today)
        ozon_stock = self._ozon_stock_data()
        yandex_orders = self._yandex_market_orders_data(now)
        yandex_stock = self._yandex_market_stock_data()
        timestamp = f"{now:%d.%m.%Y %H:%M} МСК"
        return [
            (
                "wildberries",
                "\n\n".join([
                    f"🟣 WILDBERRIES · {timestamp}",
                    self._sales_block("ЗАКАЗЫ И ПРОДАЖИ · СЕГОДНЯ", wb_sales),
                    self._ads_data_block("РЕКЛАМА · СЕГОДНЯ", wb_ads),
                    self._stock_block(wb_stock),
                    self._communication_block(),
                    self._sync_block(),
                ]),
            ),
            (
                "ozon",
                "\n\n".join([
                    f"🔵 OZON · {timestamp}",
                    self._ozon_orders_block(now, ozon_orders),
                    self._ozon_ads_block(ozon_ads),
                    self._ozon_stock_block(ozon_stock),
                ]),
            ),
            (
                "yandex_market",
                "\n\n".join([
                    f"🟡 ЯНДЕКС МАРКЕТ · {timestamp}",
                    self._yandex_market_orders_block(now, yandex_orders),
                    "РЕКЛАМА\nСтатистика рекламы ещё не подключена к Partner API.",
                    self._yandex_market_stock_block(yandex_stock),
                ]),
            ),
            (
                "summary",
                self._marketplaces_summary(
                    now,
                    wb_sales=wb_sales,
                    wb_ads=wb_ads,
                    wb_stock=wb_stock,
                    ozon_orders=ozon_orders,
                    ozon_ads=ozon_ads,
                    ozon_stock=ozon_stock,
                    yandex_orders=yandex_orders,
                    yandex_stock=yandex_stock,
                ),
            ),
        ]

    def _ozon_orders_data(self, now: datetime) -> dict[str, Any]:
        start_local, end_local = self._day_bounds(now)
        with self.session_factory() as session:
            rows = session.query(OzonPosting).filter(
                OzonPosting.in_process_at >= start_local,
                OzonPosting.in_process_at < end_local,
            ).all()
            run = session.query(OzonSyncRun).filter_by(task="orders").order_by(
                OzonSyncRun.started_at.desc()
            ).first()
        units = sum(
            int(product.get("quantity") or 0)
            for row in rows
            for product in (row.products if isinstance(row.products, list) else [])
            if isinstance(product, dict)
        )
        amount = sum((_ozon_order_amount(row.products) for row in rows), Decimal("0"))
        order_key = lambda row: row.order_id or row.order_number or f"{row.scheme}:{row.posting_number}"
        order_count = len({order_key(row) for row in rows})
        fbo = sum((row.scheme or "").lower() == "fbo" for row in rows)
        fbs = sum((row.scheme or "").lower() == "fbs" for row in rows)
        cancelled = sum((row.status or "").lower() in {"cancelled", "canceled"} for row in rows)
        cancelled_amount = sum(
            (_ozon_order_amount(row.products) for row in rows if (row.status or "").lower() in {"cancelled", "canceled"}),
            Decimal("0"),
        )
        delivered = sum((row.status or "").lower() == "delivered" for row in rows)
        return {
            "orders": order_count,
            "postings": len(rows),
            "units": units,
            "amount": amount,
            "fbo": fbo,
            "fbs": fbs,
            "cancelled": cancelled,
            "cancelled_amount": cancelled_amount,
            "delivered": delivered,
            "run": run,
        }

    def _ozon_orders_block(self, now: datetime, data: dict[str, Any] | None = None) -> str:
        data = data or self._ozon_orders_data(now)
        return "\n".join([
            "ЗАКАЗЫ · СЕГОДНЯ",
            f"Заказы: {data['orders']}; отправления: {data['postings']}; товаров: {data['units']}.",
            f"Сумма товаров: {_money(data['amount'])}.",
            f"Отправления по схеме: FBO {data['fbo']} / FBS {data['fbs']}.",
            f"Статусы: доставлено {data['delivered']}, отменено {data['cancelled']} на {_money(data['cancelled_amount'])}.",
            self._task_run_line(data["run"]),
        ])

    def _yandex_market_orders_data(self, now: datetime) -> dict[str, Any]:
        start_local, end_local = self._day_bounds(now)
        with self.session_factory() as session:
            rows = session.query(YandexMarketOrder).filter(
                YandexMarketOrder.created_at >= start_local,
                YandexMarketOrder.created_at < end_local,
            ).all()
            run = session.query(YandexMarketSyncRun).filter_by(task="orders").order_by(
                YandexMarketSyncRun.started_at.desc()
            ).first()
        cancelled = sum(row.status == "CANCELLED" for row in rows)
        delivered = sum(row.status == "DELIVERED" for row in rows)
        returned = sum(row.status in {"RETURNED", "PARTIALLY_RETURNED"} for row in rows)
        fby = sum(row.items_count or 0 for row in rows if row.program_type == "FBY")
        fbs = sum(row.items_count or 0 for row in rows if row.program_type == "FBS")
        units = sum(row.items_count or 0 for row in rows)
        amount = sum((Decimal(row.total_amount or 0) for row in rows), Decimal("0"))
        return {
            "orders": len(rows),
            "units": units,
            "amount": amount,
            "fby": fby,
            "fbs": fbs,
            "cancelled": cancelled,
            "delivered": delivered,
            "returned": returned,
            "run": run,
        }

    def _yandex_market_orders_block(self, now: datetime, data: dict[str, Any] | None = None) -> str:
        data = data or self._yandex_market_orders_data(now)
        return "\n".join([
            "ЗАКАЗЫ · СЕГОДНЯ",
            f"Заказы: {data['orders']}; товаров: {data['units']}; товарная сумма до комиссий: {_money(data['amount'])}.",
            f"Товары по модели: FBY {data['fby']} / FBS {data['fbs']}.",
            f"Статусы: доставлено {data['delivered']}, отменено {data['cancelled']}, возвратов {data['returned']}.",
            self._task_run_line(data["run"]),
        ])

    def _day_bounds(self, now: datetime) -> tuple[datetime, datetime]:
        start = datetime.combine(now.date(), datetime.min.time(), tzinfo=self.timezone)
        return start, start + timedelta(days=1)

    def _task_run_line(self, run: Any) -> str:
        if run is None:
            return "Загрузка заказов: ещё не запускалась."
        timestamp = run.finished_at or run.started_at
        if timestamp is not None:
            timestamp = timestamp.replace(tzinfo=self.timezone) if timestamp.tzinfo is None else timestamp.astimezone(self.timezone)
            finished = timestamp.strftime("%d.%m %H:%M")
        else:
            finished = "время неизвестно"
        line = f"Загрузка заказов: {run.status}, {finished}."
        if run.error:
            error = " ".join(str(run.error).split())
            line += f" Ошибка: {error[:180]}{'…' if len(error) > 180 else ''}"
        return line

    def _local(self, value: datetime | None) -> datetime:
        value = value or datetime.now(self.timezone)
        return value.replace(tzinfo=self.timezone) if value.tzinfo is None else value.astimezone(self.timezone)

    @staticmethod
    def _sales_block(title: str, data: dict[str, Any]) -> str:
        fulfillment = data.get("fulfillment", {})
        orders = fulfillment.get("orders", {})
        buyouts = fulfillment.get("buyouts", {})
        accounting = "подтверждён фин. отчётом" if data.get("accounting_covers_period") else f"оперативный, фин. отчёт по {data.get('accounting_report_through') or 'ещё не загружен'}"
        warning = data.get("operations_without_order_row", 0) + data.get("unknown_operations", 0)
        order_source = data.get("orders_source")
        source_text = (
            "WB Order Feed (реальное время)"
            if order_source == "order_feed"
            else "Statistics API — резервный источник"
        )
        updated_at = data.get("orders_last_updated_at")
        lines = [
            title,
            f"Заказы: {data['orders_placed']} на {_money(data['orders_amount'])} (FBS {orders.get('fbs', 0)} / FBO {orders.get('fbo', 0)})",
            f"Источник заказов: {source_text}; обновлено {updated_at or 'нет данных'}.",
            f"Из заказов периода сейчас отменено: {data['orders_from_period_now_cancelled']}",
            f"Отмен зарегистрировано в периоде: {data['cancellations_registered']}",
            f"Выкупы: {data['buyouts']} на {_money(data['buyouts_amount'])} (FBS {buyouts.get('fbs', 0)} / FBO {buyouts.get('fbo', 0)})",
            f"Возвраты: {data['returns']} на {_money(data['returns_amount'])}",
            f"Чистые выкупы: {data['net_buyouts']} на {_money(data['net_buyouts_amount'])}",
            f"Статус: {accounting}.",
        ]
        if warning:
            lines.append(f"Контроль качества: {warning} несвязанных/нераспознанных операций.")
        return "\n".join(lines)

    def _ads_block(self, title: str, date_from: date, date_to: date) -> str:
        data = self.promotion.efficiency_summary(date_from=date_from, date_to=date_to)
        return self._ads_data_block(title, data)

    @staticmethod
    def _ads_data_block(title: str, data: dict[str, Any]) -> str:
        return "\n".join([
            title,
            f"Расход: {_money(data['spend'])}; рекламных заказов: {data['orders']}; атрибутированная выручка: {_money(data['attributed_revenue'])}",
            f"ДРР: {_metric(data['drr_percent'], '%')}; ROAS: {_metric(data['roas'])}; CPO: {_money(data['cpo']) if data['cpo'] is not None else '—'}",
        ])

    def _ozon_ads_data(self, report_date: date) -> dict[str, Any]:
        with self.session_factory() as session:
            stats_date = session.query(func.max(OzonAdDailyStat.stat_date)).filter(
                OzonAdDailyStat.stat_date <= report_date
            ).scalar()
            rows = (
                session.query(OzonAdDailyStat).filter_by(stat_date=stats_date).all()
                if stats_date is not None
                else []
            )
        spend = sum((Decimal(row.spend or 0) for row in rows), Decimal("0"))
        revenue = sum((Decimal(row.orders_money or 0) for row in rows), Decimal("0"))
        orders = sum(int(row.orders or 0) for row in rows)
        return {
            "date": stats_date,
            "is_today": stats_date == report_date,
            "views": sum(int(row.views or 0) for row in rows),
            "clicks": sum(int(row.clicks or 0) for row in rows),
            "orders": orders,
            "spend": spend,
            "attributed_revenue": revenue,
            "drr_percent": spend / revenue * 100 if revenue else None,
            "roas": revenue / spend if spend else None,
            "cpo": spend / orders if orders else None,
        }

    def _ozon_ads_block(self, data: dict[str, Any]) -> str:
        if data["date"] is None:
            return "РЕКЛАМА\nСтатистика ещё не загружена."
        period = "сегодня" if data["is_today"] else f"последние данные за {data['date']:%d.%m.%Y}"
        return "\n".join([
            f"РЕКЛАМА · {period.upper()}",
            f"Расход: {_money(data['spend'])}; заказы: {data['orders']}; выручка: {_money(data['attributed_revenue'])}.",
            f"Показы: {data['views']}; клики: {data['clicks']}; ДРР: {_metric(data['drr_percent'], '%')}; ROAS: {_metric(data['roas'])}; CPO: {_money(data['cpo']) if data['cpo'] is not None else '—'}.",
        ])

    def _wb_stock_data(self) -> dict[str, int]:
        with self.session_factory() as session:
            fbs_units = session.query(func.coalesce(func.sum(WBFBSStock.quantity), 0)).scalar()
            fbo_units = session.query(func.coalesce(func.sum(WBFboStock.quantity), 0)).scalar()
            to_client = session.query(func.coalesce(func.sum(WBFboStock.in_way_to_client), 0)).scalar()
            from_client = session.query(func.coalesce(func.sum(WBFboStock.in_way_from_client), 0)).scalar()
            low_fbs = session.query(func.count(WBFBSStock.id)).filter(WBFBSStock.quantity.between(1, self.low_stock_threshold)).scalar()
            low_fbo = session.query(func.count(WBFboStock.id)).filter(WBFboStock.quantity.between(1, self.low_stock_threshold)).scalar()
        return {
            "fbs": int(fbs_units or 0),
            "fbo": int(fbo_units or 0),
            "to_client": int(to_client or 0),
            "from_client": int(from_client or 0),
            "low_fbs": int(low_fbs or 0),
            "low_fbo": int(low_fbo or 0),
        }

    def _stock_block(self, data: dict[str, int] | None = None) -> str:
        data = data or self._wb_stock_data()
        return f"ОСТАТКИ СЕЙЧАС\nFBS: {data['fbs']} шт.; FBO: {data['fbo']} шт.; к клиенту: {data['to_client']}; от клиента: {data['from_client']}.\nПозиций с остатком 1–{self.low_stock_threshold}: FBS {data['low_fbs']}, FBO {data['low_fbo']}."

    def _ozon_stock_data(self) -> dict[str, dict[str, int]]:
        with self.session_factory() as session:
            rows = session.query(
                OzonStock.stock_type,
                func.coalesce(func.sum(OzonStock.present), 0),
                func.coalesce(func.sum(OzonStock.reserved), 0),
            ).group_by(OzonStock.stock_type).all()
            low_rows = session.query(
                OzonStock.stock_type,
                func.count(OzonStock.id),
            ).filter(
                (OzonStock.present - OzonStock.reserved).between(1, self.low_stock_threshold)
            ).group_by(OzonStock.stock_type).all()
        low = {str(stock_type).lower(): int(count or 0) for stock_type, count in low_rows}
        result: dict[str, dict[str, int]] = {}
        for stock_type, present, reserved in rows:
            key = str(stock_type).lower()
            result[key] = {
                "present": int(present or 0),
                "reserved": int(reserved or 0),
                "available": max(int(present or 0) - int(reserved or 0), 0),
                "low": low.get(key, 0),
            }
        return result

    def _ozon_stock_block(self, data: dict[str, dict[str, int]]) -> str:
        lines = ["ОСТАТКИ СЕЙЧАС"]
        for stock_type in ("fbo", "fbs"):
            values = data.get(stock_type, {"present": 0, "reserved": 0, "available": 0, "low": 0})
            lines.append(
                f"{stock_type.upper()}: доступно {values['available']} шт.; всего {values['present']}; в резерве {values['reserved']}; позиций 1–{self.low_stock_threshold}: {values['low']}."
            )
        return "\n".join(lines)

    def _yandex_market_stock_data(self) -> dict[str, dict[str, int]]:
        with self.session_factory() as session:
            rows = session.query(
                YandexMarketStock.stock_type,
                func.coalesce(func.sum(YandexMarketStock.count), 0),
                func.count(YandexMarketStock.id),
            ).group_by(YandexMarketStock.stock_type).all()
            low_available = session.query(func.count(YandexMarketStock.id)).filter(
                YandexMarketStock.stock_type == "AVAILABLE",
                YandexMarketStock.count.between(1, self.low_stock_threshold),
            ).scalar()
        result = {
            str(stock_type).upper(): {"units": int(units or 0), "positions": int(positions or 0)}
            for stock_type, units, positions in rows
        }
        result.setdefault("AVAILABLE", {"units": 0, "positions": 0})["low"] = int(low_available or 0)
        return result

    def _yandex_market_stock_block(self, data: dict[str, dict[str, int]]) -> str:
        available = data.get("AVAILABLE", {"units": 0, "positions": 0, "low": 0})
        fit = data.get("FIT", {"units": 0, "positions": 0})
        unavailable = sum(
            values["units"]
            for key, values in data.items()
            if key not in {"AVAILABLE", "FIT"}
        )
        return "\n".join([
            "ОСТАТКИ СЕЙЧАС",
            f"Доступно: {available['units']} шт. в {available['positions']} позициях; позиций 1–{self.low_stock_threshold}: {available.get('low', 0)}.",
            f"Годных (FIT): {fit['units']} шт.; карантин/резерв/брак: {unavailable} шт.",
        ])

    def _marketplaces_summary(
        self,
        now: datetime,
        *,
        wb_sales: dict[str, Any],
        wb_ads: dict[str, Any],
        wb_stock: dict[str, int],
        ozon_orders: dict[str, Any],
        ozon_ads: dict[str, Any],
        ozon_stock: dict[str, dict[str, int]],
        yandex_orders: dict[str, Any],
        yandex_stock: dict[str, dict[str, int]],
    ) -> str:
        total_orders = int(wb_sales.get("orders_placed") or 0) + ozon_orders["orders"] + yandex_orders["orders"]
        total_units = int(wb_sales.get("orders_placed") or 0) + ozon_orders["units"] + yandex_orders["units"]
        total_amount = (
            Decimal(str(wb_sales.get("orders_amount") or 0))
            + Decimal(ozon_orders["amount"])
            + Decimal(yandex_orders["amount"])
        )
        total_cancelled = (
            int(wb_sales.get("orders_from_period_now_cancelled") or 0)
            + int(ozon_orders["cancelled"])
            + int(yandex_orders["cancelled"])
        )
        advertising_spend = Decimal(str(wb_ads.get("spend") or 0))
        advertising_revenue = Decimal(str(wb_ads.get("attributed_revenue") or 0))
        advertising_sources = ["WB"]
        if ozon_ads["is_today"]:
            advertising_spend += Decimal(ozon_ads["spend"])
            advertising_revenue += Decimal(ozon_ads["attributed_revenue"])
            advertising_sources.append("Ozon")
        ozon_available = sum(values["available"] for values in ozon_stock.values())
        yandex_available = yandex_stock.get("AVAILABLE", {}).get("units", 0)
        total_available = wb_stock["fbs"] + wb_stock["fbo"] + ozon_available + yandex_available
        ozon_status = ozon_orders["run"].status if ozon_orders["run"] is not None else "нет запуска"
        yandex_status = yandex_orders["run"].status if yandex_orders["run"] is not None else "нет запуска"
        return "\n".join([
            f"📊 ИТОГО ПО МАРКЕТПЛЕЙСАМ · {now:%d.%m.%Y %H:%M} МСК",
            f"Заказы: {total_orders}; товаров: {total_units}; сумма: {_money(total_amount)}.",
            f"Сейчас отменено: {total_cancelled}.",
            f"Реклама ({' + '.join(advertising_sources)}): расход {_money(advertising_spend)}; атрибутированная выручка {_money(advertising_revenue)}.",
            "Реклама Яндекс Маркета в итог не включена: источник ещё не подключён.",
            f"Доступные остатки: {total_available} шт. — WB {wb_stock['fbs'] + wb_stock['fbo']}, Ozon {ozon_available}, Яндекс Маркет {yandex_available}.",
            f"Загрузка заказов: Ozon {ozon_status}; Яндекс Маркет {yandex_status}. Статус WB указан в сообщении площадки.",
        ])

    def _communication_block(self) -> str:
        data = self.quality_summary()
        q, f = data["questions"], data["feedbacks"]
        return f"ОБРАЩЕНИЯ\nВопросы: без ответа {q['total'] - q['answered']}, просрочено {q['overdue']}.\nОтзывы: без ответа {f['total'] - f['answered']}, просрочено {f['overdue']}."

    def _sync_block(self) -> str:
        with self.session_factory() as session:
            run = session.query(WBSyncRun).order_by(WBSyncRun.started_at.desc()).first()
        if not run:
            return "ЗАГРУЗКА ДАННЫХ\nЦиклы синхронизации ещё не записаны."
        finished = run.finished_at.astimezone(self.timezone).strftime("%d.%m %H:%M") if run.finished_at else "выполняется"
        lines = [
            "ЗАГРУЗКА ДАННЫХ",
            f"Последний цикл: {run.status}, завершён {finished}; успешно {run.tasks_succeeded}/{run.tasks_total}, ошибок {run.tasks_failed}.",
        ]
        for task, result in (run.results or {}).items():
            if not isinstance(result, dict) or result.get("status") != "error":
                continue
            error = " ".join(str(result.get("error") or "причина не записана").split())
            lines.append(f"Ошибка {task}: {error[:180]}{'…' if len(error) > 180 else ''}")
        return "\n".join(lines)
