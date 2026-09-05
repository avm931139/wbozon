from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    HealthcheckRun,
    InventorySyncRun,
    OperationsEventDelivery,
    OperationsMonitorState,
    OzonSyncRun,
    WBSyncRun,
    WBTelegramDelivery,
    WBDocumentSyncRun,
    YandexMarketSyncRun,
)
from operations_bot.service import OperationsNotificationService, OperationsSettings
from operations_bot.__main__ import private_chats


class RecordingTelegramClient:
    chat_id = "123456"

    def __init__(self, *, error: Exception | None = None):
        self.error = error
        self.messages = []

    def send_text(self, message):
        self.messages.append(message)
        if self.error:
            raise self.error
        return [1000 + len(self.messages)]


@pytest.fixture
def operations_db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


def settings(**kwargs):
    return OperationsSettings(
        startup_lookback_seconds=3600,
        discovery_overlap_seconds=60,
        batch_size=25,
        **kwargs,
    )


def test_operations_digest_reports_successes_and_explains_failures(operations_db):
    now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    with operations_db() as session:
        session.add_all([
            WBSyncRun(
                id="wb-run",
                status="completed",
                started_at=now - timedelta(minutes=10),
                finished_at=now - timedelta(minutes=9),
                duration_seconds=60,
                tasks_total=12,
                tasks_succeeded=12,
                tasks_failed=0,
                results={},
            ),
            OzonSyncRun(
                id="ozon-run",
                task="communications",
                started_at=now - timedelta(minutes=8),
                finished_at=now - timedelta(minutes=7),
                status="partial",
                result={"questions": 10, "reviews_error": "HTTP 403"},
                error="reviews_error=HTTP 403 Forbidden",
            ),
            InventorySyncRun(
                id="inventory-run",
                marketplace="yandex_market",
                run_type="periodic",
                started_at=now - timedelta(minutes=6),
                finished_at=now - timedelta(minutes=5),
                status="completed",
                yandex_market_rows=158,
            ),
            YandexMarketSyncRun(
                id="yandex-orders",
                task="orders",
                started_at=now - timedelta(minutes=6),
                finished_at=now - timedelta(minutes=5),
                status="completed",
                result={"received": 10, "saved": 10},
            ),
            WBTelegramDelivery(
                id=99,
                report_key="stock_excel:wb:2026-08-31",
                report_type="stock_excel_wb",
                chat_id="-1001",
                status="error",
                telegram_message_ids=[],
                error_text="connection timeout through proxy",
                created_at=now - timedelta(minutes=4),
            ),
        ])
        session.commit()

    client = RecordingTelegramClient()
    result = OperationsNotificationService(
        client=client,
        settings=settings(),
        session_factory=operations_db,
    ).run(now=now)

    assert result["discovered"] == 5
    assert result["sent_events"] == 5
    assert len(client.messages) == 1
    message = client.messages[0]
    assert "Wildberries · полный цикл" in message
    assert "Ozon · вопросы и отзывы" in message
    assert "у API-ключа нет нужного разрешения" in message
    assert "Остатки · Яндекс Маркет" in message
    assert "Яндекс Маркет · заказы" in message
    assert "строк=158" in message
    assert "Telegram · stock_excel_wb" in message
    assert "сеть, внешний API или proxy" in message
    with operations_db() as session:
        assert session.query(OperationsEventDelivery).filter_by(status="sent").count() == 5
        assert session.get(OperationsMonitorState, "main") is not None

    second = OperationsNotificationService(
        client=client,
        settings=settings(),
        session_factory=operations_db,
    ).run(now=now + timedelta(minutes=1))
    assert second == {"discovered": 0, "sent_events": 0, "message_ids": []}
    assert len(client.messages) == 1


def test_failed_private_delivery_stays_queued_and_is_retried(operations_db):
    now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    with operations_db() as session:
        session.add(OzonSyncRun(
            id="orders-run",
            task="orders",
            started_at=now - timedelta(minutes=2),
            finished_at=now - timedelta(minutes=1),
            status="completed",
            result={"fbs": 0, "fbo": 1931},
        ))
        session.commit()

    failing_client = RecordingTelegramClient(error=RuntimeError("proxy unavailable"))
    with pytest.raises(RuntimeError, match="proxy unavailable"):
        OperationsNotificationService(
            client=failing_client,
            settings=settings(),
            session_factory=operations_db,
        ).run(now=now)

    with operations_db() as session:
        queued = session.query(OperationsEventDelivery).one()
        assert queued.status == "error"
        assert queued.attempts == 1
        assert "proxy unavailable" in queued.error_text

    recovered_client = RecordingTelegramClient()
    result = OperationsNotificationService(
        client=recovered_client,
        settings=settings(),
        session_factory=operations_db,
    ).run(now=now + timedelta(minutes=1))

    assert result["discovered"] == 0
    assert result["sent_events"] == 1
    assert "Ozon · заказы FBS/FBO" in recovered_client.messages[0]
    with operations_db() as session:
        queued = session.query(OperationsEventDelivery).one()
        assert queued.status == "sent"
        assert queued.attempts == 2
        assert queued.telegram_message_ids == [1001]


def test_operations_monitor_can_send_only_problems(operations_db):
    now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    with operations_db() as session:
        session.add_all([
            OzonSyncRun(
                id="success",
                task="orders",
                started_at=now - timedelta(minutes=3),
                finished_at=now - timedelta(minutes=2),
                status="completed",
                result={"fbo": 10},
            ),
            OzonSyncRun(
                id="failure",
                task="ads",
                started_at=now - timedelta(minutes=2),
                finished_at=now - timedelta(minutes=1),
                status="failed",
                error="HTTP 429 rate limit",
            ),
        ])
        session.commit()

    client = RecordingTelegramClient()
    result = OperationsNotificationService(
        client=client,
        settings=settings(include_successes=False),
        session_factory=operations_db,
    ).run(now=now)

    assert result["discovered"] == 1
    assert "Ozon · реклама" in client.messages[0]
    assert "превышен лимит запросов" in client.messages[0]
    assert "заказы FBS/FBO" not in client.messages[0]


def test_digest_stays_in_one_telegram_message(operations_db):
    now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    with operations_db() as session:
        for number in range(25):
            session.add(OzonSyncRun(
                id=f"failed-{number}",
                task="orders",
                started_at=now - timedelta(minutes=2),
                finished_at=now - timedelta(minutes=1),
                status="failed",
                error="connection timeout " + "x" * 2000,
            ))
        session.commit()

    client = RecordingTelegramClient()
    OperationsNotificationService(
        client=client,
        settings=settings(),
        session_factory=operations_db,
    ).run(now=now)

    assert len(client.messages) == 1
    assert len(client.messages[0]) <= 3800
    assert client.messages[0].count("❌ Ozon · заказы FBS/FBO") == 25


def test_private_chats_extracts_unique_private_conversations():
    updates = [
        {"message": {"chat": {"id": 123, "type": "private", "first_name": "Ivan"}}},
        {"message": {"chat": {"id": -1001, "type": "supergroup", "title": "Reports"}}},
        {"my_chat_member": {"chat": {"id": 123, "type": "private", "first_name": "Ivan", "username": "ivan"}}},
    ]

    assert private_chats(updates) == [
        {"chat_id": "123", "first_name": "Ivan", "username": "ivan"}
    ]


def test_operations_digest_includes_health_failure_and_recovery_only(operations_db):
    now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    with operations_db() as session:
        session.add_all([
            HealthcheckRun(
                id="failed-health",
                checked_at=now - timedelta(minutes=3),
                status="failed",
                checks_total=16,
                checks_failed=1,
                failure_signature="abc",
                checks=[{"ok": False, "name": "Yandex inventory service", "detail": "inactive"}],
            ),
            HealthcheckRun(
                id="unchanged-health",
                checked_at=now - timedelta(minutes=2),
                status="unchanged",
                checks_total=16,
                checks_failed=1,
                failure_signature="abc",
                checks=[{"ok": False, "name": "Yandex inventory service", "detail": "inactive"}],
            ),
            HealthcheckRun(
                id="recovered-health",
                checked_at=now - timedelta(minutes=1),
                status="recovered",
                checks_total=16,
                checks_failed=0,
                checks=[],
            ),
        ])
        session.commit()

    client = RecordingTelegramClient()
    result = OperationsNotificationService(
        client=client,
        settings=settings(),
        session_factory=operations_db,
    ).run(now=now)

    assert result["discovered"] == 2
    assert "Контроль состояния · обнаружена проблема" in client.messages[0]
    assert "Yandex inventory service: inactive" in client.messages[0]
    assert "Контроль состояния · восстановление" in client.messages[0]


def test_operations_digest_explains_wb_document_failure(operations_db):
    now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    with operations_db() as session:
        session.add(WBDocumentSyncRun(
            id="documents-failed",
            started_at=now - timedelta(minutes=2),
            finished_at=now - timedelta(minutes=1),
            status="partial",
            result={"documents": {"status": "completed", "result": 12}},
            error="balance: HTTP 403 Forbidden",
        ))
        session.commit()

    client = RecordingTelegramClient()
    OperationsNotificationService(
        client=client,
        settings=settings(),
        session_factory=operations_db,
    ).run(now=now)

    assert "Wildberries · документы и бухгалтерия" in client.messages[0]
    assert "HTTP 403 Forbidden" in client.messages[0]
    assert "нет нужного разрешения" in client.messages[0]
