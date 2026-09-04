from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import func

from app.db import SessionLocal
from app.models import WBFBSStock, WBFboStock, WBSyncRun
from wb.services.customer_communication_service import CustomerCommunicationService
from wb.services.promotion_service import PromotionService
from wb.services.sales_service import SalesService


def _money(value: Any) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    return f"{amount:,.2f}".replace(",", " ") + " ₽"


def _metric(value: Any, suffix: str = "") -> str:
    return "—" if value is None else f"{value}{suffix}"


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
        now = self._local(now)
        today = now.date()
        return "\n\n".join([
            f"WB — текущая обстановка {now:%d.%m.%Y %H:%M}",
            self._sales_block("СЕГОДНЯ", self.sales_summary(today, today)),
            self._ads_block("РЕКЛАМА: СЕГОДНЯ", today, today),
            self._stock_block(),
            self._sync_block(),
        ])

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
        return "\n".join([
            title,
            f"Расход: {_money(data['spend'])}; рекламных заказов: {data['orders']}; атрибутированная выручка: {_money(data['attributed_revenue'])}",
            f"ДРР: {_metric(data['drr_percent'], '%')}; ROAS: {_metric(data['roas'])}; CPO: {_money(data['cpo']) if data['cpo'] is not None else '—'}",
        ])

    def _stock_block(self) -> str:
        with self.session_factory() as session:
            fbs_units = session.query(func.coalesce(func.sum(WBFBSStock.quantity), 0)).scalar()
            fbo_units = session.query(func.coalesce(func.sum(WBFboStock.quantity), 0)).scalar()
            to_client = session.query(func.coalesce(func.sum(WBFboStock.in_way_to_client), 0)).scalar()
            from_client = session.query(func.coalesce(func.sum(WBFboStock.in_way_from_client), 0)).scalar()
            low_fbs = session.query(func.count(WBFBSStock.id)).filter(WBFBSStock.quantity.between(1, self.low_stock_threshold)).scalar()
            low_fbo = session.query(func.count(WBFboStock.id)).filter(WBFboStock.quantity.between(1, self.low_stock_threshold)).scalar()
        return f"ОСТАТКИ СЕЙЧАС\nFBS: {fbs_units} шт.; FBO: {fbo_units} шт.; к клиенту: {to_client}; от клиента: {from_client}.\nПозиций с остатком 1–{self.low_stock_threshold}: FBS {low_fbs}, FBO {low_fbo}."

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
        return f"ЗАГРУЗКА ДАННЫХ\nПоследний цикл: {run.status}, завершён {finished}; успешно {run.tasks_succeeded}/{run.tasks_total}, ошибок {run.tasks_failed}."
