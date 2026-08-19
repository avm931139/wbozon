from datetime import datetime
from zoneinfo import ZoneInfo

from telegram_bot.client import TelegramClient, split_text
from telegram_bot.reports import TelegramReportService
from telegram_bot.scheduler import TelegramReportScheduler


class FakeResponse:
    def __init__(self, message_id): self.message_id = message_id
    def raise_for_status(self): return None
    def json(self): return {"ok": True, "result": {"message_id": self.message_id}}


class FakeHTTPSession:
    def __init__(self): self.calls = []
    def post(self, url, **kwargs):
        self.calls.append((url, kwargs)); return FakeResponse(len(self.calls))


def sales_data():
    return {
        "orders_placed": 14, "orders_amount": "70010.25", "orders_from_period_now_cancelled": 2,
        "cancellations_registered": 6, "buyouts": 14, "buyouts_amount": "40227", "returns": 1,
        "returns_amount": "1000", "net_buyouts": 13, "net_buyouts_amount": "39227",
        "unknown_operations": 0, "operations_without_order_row": 1,
        "fulfillment": {"orders": {"fbs": 5, "fbo": 9}, "buyouts": {"fbs": 4, "fbo": 10}},
        "accounting_covers_period": False, "accounting_report_through": "2026-08-02",
    }


def test_split_text_and_client_send_every_chunk():
    assert all(len(chunk) <= 10 for chunk in split_text("first\n" + "x" * 30, limit=10))
    session = FakeHTTPSession(); client = TelegramClient("secret", "-1001", session=session)
    assert client.send_text("a" * 4000) == [1, 2]
    assert all(call[1]["json"]["chat_id"] == "-1001" for call in session.calls)
    assert all("secret" not in str(call[1]) for call in session.calls)


def test_sales_block_keeps_event_definitions_separate():
    block = TelegramReportService._sales_block("ПРОШЛЫЙ ДЕНЬ", sales_data())
    for text in ("Заказы: 14", "сейчас отменено: 2", "Отмен зарегистрировано в периоде: 6", "Выкупы: 14", "Возвраты: 1", "оперативный"):
        assert text in block


class FakeDispatcher:
    def __init__(self): self.calls = []
    def send(self, report_type, report_key, **kwargs):
        self.calls.append((report_type, report_key)); return {"status": "sent"}


def test_scheduler_builds_daily_and_interval_keys():
    dispatcher = FakeDispatcher()
    scheduler = TelegramReportScheduler(dispatcher, timezone_name="Europe/Moscow", morning_time="09:00", operational_interval_seconds=10800)
    scheduler.run_pending(datetime(2026, 8, 9, 9, 30, tzinfo=ZoneInfo("Europe/Moscow")))
    assert dispatcher.calls[0] == ("morning", "morning:2026-08-09")
    assert dispatcher.calls[1][0] == "operational"


def test_scheduler_before_morning_sends_only_operational():
    dispatcher = FakeDispatcher()
    scheduler = TelegramReportScheduler(dispatcher, timezone_name="Europe/Moscow", morning_time="09:00", operational_interval_seconds=10800)
    scheduler.run_pending(datetime(2026, 8, 9, 8, 59, tzinfo=ZoneInfo("Europe/Moscow")))
    assert [call[0] for call in dispatcher.calls] == ["operational"]
