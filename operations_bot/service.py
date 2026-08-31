from __future__ import annotations

import json
import re
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import or_, text

from app.config import (
    OPERATIONS_TG_BATCH_SIZE,
    OPERATIONS_TG_BOT_TOKEN,
    OPERATIONS_TG_CHAT_ID,
    OPERATIONS_TG_DISCOVERY_OVERLAP_SECONDS,
    OPERATIONS_TG_INCLUDE_SUCCESSES,
    OPERATIONS_TG_PROXY_URL,
    OPERATIONS_TG_STARTUP_LOOKBACK_SECONDS,
    WB_TG_REQUEST_TIMEOUT_SECONDS,
    WB_TG_TIMEZONE,
)
from app.db import SessionLocal
from app.models import (
    HealthcheckRun,
    InventorySyncRun,
    OperationsEventDelivery,
    OperationsMonitorState,
    OzonSyncRun,
    WBDocumentSyncRun,
    WBSyncRun,
    WBTelegramDelivery,
)
from telegram_bot.client import TelegramClient


STATE_ID = "main"
LOCK_ID = zlib.crc32(b"wbozon:operations-notifications")
MAX_DIGEST_CHARS = 3800


@dataclass(frozen=True)
class OperationsSettings:
    timezone_name: str = WB_TG_TIMEZONE
    startup_lookback_seconds: int = OPERATIONS_TG_STARTUP_LOOKBACK_SECONDS
    discovery_overlap_seconds: int = OPERATIONS_TG_DISCOVERY_OVERLAP_SECONDS
    batch_size: int = OPERATIONS_TG_BATCH_SIZE
    include_successes: bool = OPERATIONS_TG_INCLUDE_SUCCESSES

    def __post_init__(self) -> None:
        ZoneInfo(self.timezone_name)
        if self.startup_lookback_seconds < 0:
            raise ValueError("OPERATIONS_TG_STARTUP_LOOKBACK_SECONDS must not be negative")
        if self.discovery_overlap_seconds < 0:
            raise ValueError("OPERATIONS_TG_DISCOVERY_OVERLAP_SECONDS must not be negative")
        if self.batch_size < 1:
            raise ValueError("OPERATIONS_TG_BATCH_SIZE must be positive")


@dataclass(frozen=True)
class OperationEvent:
    key: str
    source_type: str
    source_id: str
    occurred_at: datetime
    severity: str
    title: str
    detail: str


class OperationsNotificationAlreadyRunning(RuntimeError):
    pass


class OperationsNotificationService:
    """Discover durable worker results and deliver private Telegram digests."""

    def __init__(
        self,
        *,
        client: TelegramClient | None = None,
        settings: OperationsSettings | None = None,
        session_factory: Callable[..., Any] = SessionLocal,
    ) -> None:
        self.settings = settings or OperationsSettings()
        self.timezone = ZoneInfo(self.settings.timezone_name)
        self.session_factory = session_factory
        if client is None:
            if not OPERATIONS_TG_BOT_TOKEN:
                raise RuntimeError("OPERATIONS_TG_BOT_TOKEN or WB_TG_BOT_TOKEN must be configured")
            if not OPERATIONS_TG_CHAT_ID:
                raise RuntimeError("OPERATIONS_TG_CHAT_ID must be configured")
            client = TelegramClient(
                OPERATIONS_TG_BOT_TOKEN,
                OPERATIONS_TG_CHAT_ID,
                timeout=WB_TG_REQUEST_TIMEOUT_SECONDS,
                proxy_url=OPERATIONS_TG_PROXY_URL,
            )
        self.client = client

    def run(self, *, now: datetime | None = None) -> dict[str, Any]:
        current = self._as_utc(now or datetime.now(timezone.utc))
        with self.session_factory() as lock_session:
            if not self._acquire_lock(lock_session):
                raise OperationsNotificationAlreadyRunning(
                    "operations notification cycle is already running"
                )
            try:
                discovered = self._discover(current)
                delivery = self._deliver(current)
                return {"discovered": discovered, **delivery}
            finally:
                self._release_lock(lock_session)

    def _discover(self, current: datetime) -> int:
        with self.session_factory() as session:
            state = session.get(OperationsMonitorState, STATE_ID)
            if state is None:
                since = current - timedelta(seconds=self.settings.startup_lookback_seconds)
            else:
                since = self._as_utc(state.cursor_at) - timedelta(
                    seconds=self.settings.discovery_overlap_seconds
                )

            events = self._collect_events(session, since, current)
            if not self.settings.include_successes:
                events = [event for event in events if event.severity != "success"]
            existing = set()
            if events:
                existing = {
                    row[0]
                    for row in session.query(OperationsEventDelivery.event_key).filter(
                        OperationsEventDelivery.event_key.in_([event.key for event in events])
                    )
                }
            created_at = datetime.now(timezone.utc)
            for event in events:
                if event.key in existing:
                    continue
                session.add(OperationsEventDelivery(
                    event_key=event.key,
                    source_type=event.source_type,
                    source_id=event.source_id,
                    occurred_at=event.occurred_at,
                    severity=event.severity,
                    title=event.title,
                    detail=event.detail,
                    status="pending",
                    attempts=0,
                    telegram_message_ids=[],
                    created_at=created_at,
                ))

            if state is None:
                session.add(OperationsMonitorState(
                    id=STATE_ID,
                    cursor_at=current,
                    updated_at=created_at,
                ))
            else:
                state.cursor_at = current
                state.updated_at = created_at
            session.commit()
            return sum(event.key not in existing for event in events)

    def _deliver(self, current: datetime) -> dict[str, Any]:
        with self.session_factory() as session:
            rows = session.query(OperationsEventDelivery).filter(
                OperationsEventDelivery.status.in_(("pending", "error"))
            ).order_by(
                OperationsEventDelivery.occurred_at,
                OperationsEventDelivery.id,
            ).limit(self.settings.batch_size).all()
            if not rows:
                return {"sent_events": 0, "message_ids": []}
            row_ids = [int(row.id) for row in rows]
            message = self._digest(rows, current)

        try:
            message_ids = self.client.send_text(message)
        except Exception as exc:
            with self.session_factory() as session:
                failed_rows = session.query(OperationsEventDelivery).filter(
                    OperationsEventDelivery.id.in_(row_ids)
                ).all()
                for row in failed_rows:
                    row.status = "error"
                    row.attempts += 1
                    row.error_text = self._trim(f"{type(exc).__name__}: {exc}", 4000)
                session.commit()
            raise

        sent_at = datetime.now(timezone.utc)
        with self.session_factory() as session:
            sent_rows = session.query(OperationsEventDelivery).filter(
                OperationsEventDelivery.id.in_(row_ids)
            ).all()
            for row in sent_rows:
                row.status = "sent"
                row.attempts += 1
                row.telegram_message_ids = message_ids
                row.error_text = None
                row.sent_at = sent_at
            session.commit()
        return {"sent_events": len(row_ids), "message_ids": message_ids}

    def _collect_events(
        self,
        session: Any,
        since: datetime,
        until: datetime,
    ) -> list[OperationEvent]:
        events: list[OperationEvent] = []
        wb_rows = session.query(WBSyncRun).filter(
            WBSyncRun.finished_at.is_not(None),
            WBSyncRun.finished_at >= since,
            WBSyncRun.finished_at <= until,
        ).all()
        events.extend(self._wb_event(row) for row in wb_rows)

        document_rows = session.query(WBDocumentSyncRun).filter(
            WBDocumentSyncRun.finished_at.is_not(None),
            WBDocumentSyncRun.finished_at >= since,
            WBDocumentSyncRun.finished_at <= until,
        ).all()
        events.extend(self._wb_documents_event(row) for row in document_rows)

        ozon_rows = session.query(OzonSyncRun).filter(
            OzonSyncRun.finished_at.is_not(None),
            OzonSyncRun.finished_at >= since,
            OzonSyncRun.finished_at <= until,
        ).all()
        events.extend(self._ozon_event(row) for row in ozon_rows)

        inventory_rows = session.query(InventorySyncRun).filter(
            InventorySyncRun.finished_at.is_not(None),
            InventorySyncRun.finished_at >= since,
            InventorySyncRun.finished_at <= until,
        ).all()
        events.extend(self._inventory_event(row) for row in inventory_rows)

        telegram_rows = session.query(WBTelegramDelivery).filter(
            WBTelegramDelivery.report_type.notlike("operations_%"),
            WBTelegramDelivery.status.in_(("sent", "error")),
            or_(
                WBTelegramDelivery.created_at.between(since, until),
                WBTelegramDelivery.sent_at.between(since, until),
            ),
        ).all()
        events.extend(self._telegram_event(row) for row in telegram_rows)
        health_rows = session.query(HealthcheckRun).filter(
            HealthcheckRun.status.in_(("failed", "recovered")),
            HealthcheckRun.checked_at >= since,
            HealthcheckRun.checked_at <= until,
        ).all()
        events.extend(self._healthcheck_event(row) for row in health_rows)
        return sorted(events, key=lambda event: (event.occurred_at, event.key))

    def _wb_event(self, row: WBSyncRun) -> OperationEvent:
        failed = []
        for task, result in (row.results or {}).items():
            if isinstance(result, dict) and result.get("status") == "error":
                failed.append(f"{task}: {result.get('error') or 'неизвестная ошибка'}")
        if row.status == "completed":
            severity = "success"
            detail = (
                f"Выполнено успешно: {row.tasks_succeeded}/{row.tasks_total} задач. "
                f"Длительность: {row.duration_seconds or 0} с."
            )
        else:
            severity = "error"
            explanation = "; ".join(failed[:4]) or "часть задач завершилась ошибкой"
            detail = (
                f"Ошибок: {row.tasks_failed} из {row.tasks_total}. {explanation}. "
                "Проверить: journalctl -u wbozon-wb.service и logs/wb/wb_errors.jsonl."
            )
        return OperationEvent(
            key=f"wb:{row.id}:{row.status}",
            source_type="wb",
            source_id=str(row.id),
            occurred_at=self._as_utc(row.finished_at),
            severity=severity,
            title="Wildberries · полный цикл",
            detail=self._trim(detail),
        )

    def _ozon_event(self, row: OzonSyncRun) -> OperationEvent:
        titles = {
            "products": "товары",
            "orders": "заказы FBS/FBO",
            "supplies": "поставки",
            "communications": "вопросы и отзывы",
            "daily_sales": "дневные продажи",
            "finances": "финансы",
            "ads": "реклама",
        }
        if row.status == "completed":
            severity = "success"
            detail = f"Выполнено успешно. Результат: {self._compact(row.result)}."
        elif row.status == "skipped":
            severity = "info"
            detail = f"Задание пропущено штатно. Результат: {self._compact(row.result)}."
        else:
            severity = "error"
            error = row.error or "причина не записана"
            detail = (
                f"Статус {row.status}. Ошибка: {error}. "
                f"{self._problem_hint(error)} Проверить: journalctl -u wbozon-ozon@{row.task}.service."
            )
        return OperationEvent(
            key=f"ozon:{row.id}:{row.status}",
            source_type="ozon",
            source_id=str(row.id),
            occurred_at=self._as_utc(row.finished_at),
            severity=severity,
            title=f"Ozon · {titles.get(row.task, row.task)}",
            detail=self._trim(detail),
        )

    def _wb_documents_event(self, row: WBDocumentSyncRun) -> OperationEvent:
        if row.status == "completed":
            severity = "success"
            detail = f"Выполнено успешно. Результат: {self._compact(row.result)}."
        else:
            severity = "error"
            error = row.error or "причина не записана"
            detail = (
                f"Статус {row.status}. Ошибка: {error}. {self._problem_hint(error)} "
                "Проверить: journalctl -u wbozon-wb-documents.service."
            )
        return OperationEvent(
            key=f"wb_documents:{row.id}:{row.status}",
            source_type="wb_documents",
            source_id=str(row.id),
            occurred_at=self._as_utc(row.finished_at),
            severity=severity,
            title="Wildberries · документы и бухгалтерия",
            detail=self._trim(detail),
        )

    def _inventory_event(self, row: InventorySyncRun) -> OperationEvent:
        names = {"wb": "Wildberries", "ozon": "Ozon", "yandex_market": "Яндекс Маркет", "all": "все маркетплейсы"}
        counts = {
            "wb": f"FBS={row.wb_fbs_rows}, FBO={row.wb_fbo_rows}",
            "ozon": f"агрегат={row.ozon_rows}, по складам={row.ozon_warehouse_rows}",
            "yandex_market": f"строк={row.yandex_market_rows}",
            "all": (
                f"WB FBS={row.wb_fbs_rows}, WB FBO={row.wb_fbo_rows}, "
                f"Ozon={row.ozon_rows}/{row.ozon_warehouse_rows}, "
                f"Яндекс={row.yandex_market_rows}"
            ),
        }
        run_name = "дневной срез" if row.run_type == "daily_snapshot" else "текущие остатки"
        if row.status == "completed":
            severity = "success"
            detail = f"Выполнено успешно: {counts.get(row.marketplace, 'данные сохранены')}."
        else:
            severity = "error"
            error = row.error or "причина не записана"
            detail = (
                f"Загрузка не завершена. Ошибка: {error}. {self._problem_hint(error)} "
                f"Проверить: journalctl -u wbozon-inventory@{row.marketplace}.service."
            )
        return OperationEvent(
            key=f"inventory:{row.id}:{row.status}",
            source_type="inventory",
            source_id=str(row.id),
            occurred_at=self._as_utc(row.finished_at),
            severity=severity,
            title=f"Остатки · {names.get(row.marketplace, row.marketplace)} · {run_name}",
            detail=self._trim(detail),
        )

    def _telegram_event(self, row: WBTelegramDelivery) -> OperationEvent:
        if row.status == "sent":
            severity = "success"
            detail = f"Сообщение доставлено, Telegram message IDs: {row.telegram_message_ids or []}."
            occurred_at = row.sent_at or row.created_at
        else:
            severity = "error"
            error = row.error_text or "причина не записана"
            detail = (
                f"Не удалось отправить сообщение. Ошибка: {error}. {self._problem_hint(error)} "
                "Проверить Telegram relay, proxy и journalctl -u wbozon-telegram.service."
            )
            occurred_at = row.created_at
        return OperationEvent(
            key=f"telegram:{row.id}:{row.status}",
            source_type="telegram",
            source_id=str(row.id),
            occurred_at=self._as_utc(occurred_at),
            severity=severity,
            title=f"Telegram · {row.report_type}",
            detail=self._trim(detail),
        )

    def _healthcheck_event(self, row: HealthcheckRun) -> OperationEvent:
        if row.status == "recovered":
            severity = "success"
            detail = f"Все {row.checks_total} проверок снова выполняются успешно."
            title = "Контроль состояния · восстановление"
        else:
            severity = "error"
            failures = [
                f"{check.get('name')}: {check.get('detail')}"
                for check in (row.checks or [])
                if not check.get("ok")
            ]
            error = "; ".join(failures) or "healthcheck не сохранил подробности"
            detail = (
                f"Проблем: {row.checks_failed} из {row.checks_total}. {error}. "
                f"{self._problem_hint(error)} Проверить: journalctl -u wbozon-healthcheck.service."
            )
            title = "Контроль состояния · обнаружена проблема"
        return OperationEvent(
            key=f"healthcheck:{row.id}:{row.status}",
            source_type="healthcheck",
            source_id=str(row.id),
            occurred_at=self._as_utc(row.checked_at),
            severity=severity,
            title=title,
            detail=self._trim(detail),
        )

    def _digest(self, rows: list[OperationsEventDelivery], current: datetime) -> str:
        errors = sum(row.severity == "error" for row in rows)
        successes = sum(row.severity == "success" for row in rows)
        header = [
            "🧭 wbozon · действия программы",
            f"Событий: {len(rows)} · успешно: {successes} · проблем: {errors}",
            "",
        ]
        icons = {"success": "✅", "error": "❌", "info": "ℹ️"}
        entry_headers: list[str] = []
        for row in rows:
            occurred = self._as_utc(row.occurred_at).astimezone(self.timezone)
            title = self._trim(row.title, 90)
            entry_headers.append(
                f"{icons.get(row.severity, '•')} {title} · {occurred:%d.%m %H:%M} МСК"
            )
        footer = f"Сформировано: {current.astimezone(self.timezone):%d.%m.%Y %H:%M:%S} МСК"
        fixed_size = len("\n".join(header + entry_headers + [footer])) + len(rows) * 2
        detail_limit = max(24, (MAX_DIGEST_CHARS - fixed_size) // max(len(rows), 1))
        lines = list(header)
        for row, entry_header in zip(rows, entry_headers):
            lines.extend([entry_header, self._trim(row.detail, detail_limit), ""])
        lines.append(footer)
        return self._trim("\n".join(lines).strip(), MAX_DIGEST_CHARS)

    @staticmethod
    def _problem_hint(error: str) -> str:
        normalized = error.casefold()
        if "403" in normalized or "forbidden" in normalized or "permission" in normalized:
            return "Вероятная причина: у API-ключа нет нужного разрешения или услуга недоступна кабинету."
        if "401" in normalized or "unauthorized" in normalized or "authentication" in normalized:
            return "Вероятная причина: неверный, отозванный или просроченный API-ключ."
        if "429" in normalized or "rate limit" in normalized:
            return "Вероятная причина: превышен лимит запросов; следующий запуск повторит операцию."
        if any(value in normalized for value in ("timeout", "connection", "network", "proxy")):
            return "Вероятная причина: сеть, внешний API или proxy временно недоступны."
        if "campaign_ids" in normalized:
            return "Причина: не настроен список кампаний Яндекс Маркета."
        if any(value in normalized for value in ("database", "postgres", "operationalerror")):
            return "Вероятная причина: недоступна PostgreSQL или нарушена схема БД."
        if any(value in normalized for value in ("duplicate", "parse", "invalid json")):
            return "Вероятная причина: ответ API не соответствует ожидаемому контракту."
        return "Точная причина записана в журнале указанного systemd unit."

    @staticmethod
    def _compact(value: Any) -> str:
        if value is None:
            return "нет дополнительных данных"
        return OperationsNotificationService._trim(
            json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":")),
            700,
        )

    @staticmethod
    def _trim(value: Any, limit: int = 1200) -> str:
        text_value = re.sub(r"\s+", " ", str(value)).strip()
        if limit < 1:
            return ""
        if len(text_value) <= limit:
            return text_value
        if limit == 1:
            return "…"
        return f"{text_value[:limit - 1]}…"

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime:
        if value is None:
            return datetime.now(timezone.utc)
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _acquire_lock(session: Any) -> bool:
        if session.get_bind().dialect.name != "postgresql":
            return True
        return bool(session.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": LOCK_ID},
        ).scalar())

    @staticmethod
    def _release_lock(session: Any) -> None:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": LOCK_ID},
            )
