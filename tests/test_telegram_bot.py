from datetime import date, datetime
from io import BytesIO

from openpyxl import load_workbook
import pytest
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from zoneinfo import ZoneInfo

from app.db import Base
from app.models import OzonPosting, OzonSyncRun, WBSyncRun, YandexMarketOrder, YandexMarketStockSnapshot
from telegram_bot.client import TelegramClient, TelegramError, split_text
from telegram_bot.__main__ import send_stock_files
from telegram_bot.dispatcher import TelegramReportDispatcher
from telegram_bot.reports import TelegramReportService
from telegram_bot.scheduler import TelegramReportScheduler
from telegram_bot.stock_reports import (
    StockExcelReportService,
    StockSnapshotNotFound,
    build_workbook,
)


class FakeResponse:
    def __init__(self, message_id): self.message_id = message_id
    def raise_for_status(self): return None
    def json(self): return {"ok": True, "result": {"message_id": self.message_id}}


class FakeHTTPSession:
    def __init__(self): self.calls = []; self.proxies = {}
    def post(self, url, **kwargs):
        self.calls.append((url, kwargs)); return FakeResponse(len(self.calls))


class FakeUpdatesResponse(FakeResponse):
    def json(self): return {"ok": True, "result": [{"update_id": 1}]}


class FakeUpdatesSession(FakeHTTPSession):
    def post(self, url, **kwargs):
        self.calls.append((url, kwargs)); return FakeUpdatesResponse(len(self.calls))


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


def test_report_metrics_are_rounded_for_telegram():
    from telegram_bot.reports import _metric

    assert _metric("8.969671361839999712", "%") == "8.97%"
    assert _metric(None) == "—"


def test_client_sends_document_as_multipart_without_disk_file():
    session = FakeHTTPSession(); client = TelegramClient("secret", "-1001", session=session)
    assert client.send_document("stocks.xlsx", b"xlsx", caption="Stocks") == 1
    url, kwargs = session.calls[0]
    assert url.endswith("/sendDocument")
    assert kwargs["data"] == {"chat_id": "-1001", "caption": "Stocks"}
    assert kwargs["files"]["document"][0:2] == ("stocks.xlsx", b"xlsx")


def test_client_get_updates_for_chat_id_discovery():
    session = FakeUpdatesSession(); client = TelegramClient("secret", "0", session=session)
    assert client.get_updates() == [{"update_id": 1}]
    url, kwargs = session.calls[0]
    assert url.endswith("/getUpdates")
    assert kwargs["json"] == {"limit": 100, "timeout": 0}


def test_client_applies_proxy_only_to_its_session():
    session = FakeHTTPSession()
    proxy_url = "socks5h://127.0.0.1:1080"
    TelegramClient("secret", "-1001", proxy_url=proxy_url, session=session)
    assert session.proxies == {"http": proxy_url, "https": proxy_url}


def test_client_rejects_invalid_proxy_url():
    with pytest.raises(ValueError, match="WB_TG_PROXY_URL"):
        TelegramClient("secret", "-1001", proxy_url="ftp://proxy.example", session=FakeHTTPSession())


def test_transport_error_redacts_bot_token():
    token = "123456:very-secret-token"

    class FailingSession(FakeHTTPSession):
        def post(self, url, **kwargs):
            raise requests.ConnectionError(f"connection failed for {url}")

    client = TelegramClient(token, "-1001", session=FailingSession())
    with pytest.raises(TelegramError) as error:
        client.send_text("hello")
    assert token not in str(error.value)
    assert "<redacted>" in str(error.value)


def test_build_workbook_returns_in_memory_xlsx():
    payload = build_workbook([("Остатки", ("Дата", "SKU", "Количество"), [(date(2026, 8, 19), "sku-1", 7)])])
    workbook = load_workbook(BytesIO(payload), read_only=True)
    sheet = workbook["Остатки"]
    assert list(sheet.values) == [("Дата", "SKU", "Количество"), (datetime(2026, 8, 19), "sku-1", 7)]
    workbook.close()


class FakeStockDispatcher:
    def __init__(self): self.documents = []; self.warnings = []
    def send_document(self, report_type, report_key, factory, **kwargs):
        document = factory(); self.documents.append((report_type, report_key, document)); return {"status": "sent"}
    def send_text_content(self, report_type, report_key, factory, **kwargs):
        text = factory(); self.warnings.append((report_type, report_key, text)); return {"status": "sent"}


class PartiallyMissingStockReports:
    def wb(self, snapshot_date):
        raise StockSnapshotNotFound("missing WB")
    def ozon(self, snapshot_date):
        return "ozon.xlsx", b"xlsx", "Ozon"
    def yandex_market(self, snapshot_date):
        raise StockSnapshotNotFound("missing Yandex Market")


def test_stock_files_warn_when_daily_snapshot_is_missing_but_send_available_file():
    dispatcher = FakeStockDispatcher()
    results = send_stock_files(
        dispatcher,
        date(2026, 8, 20),
        reports=PartiallyMissingStockReports(),
    )
    assert len(results) == 2
    assert len(dispatcher.documents) == 1
    assert dispatcher.documents[0][0] == "stock_excel_ozon"
    assert dispatcher.warnings[0][1] == "stock_warning:2026-08-20"
    assert "Wildberries" in dispatcher.warnings[0][2]
    assert "Яндекс Маркет" in dispatcher.warnings[0][2]
    assert "20.08.2026" in dispatcher.warnings[0][2]


def test_yandex_market_stock_report_contains_summary_and_warehouse_rows():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    snapshot_date = date(2026, 8, 30)
    with session_factory() as session:
        session.add_all([
            YandexMarketStockSnapshot(
                snapshot_date=snapshot_date,
                captured_at=datetime(2026, 8, 30, 0, 1, tzinfo=ZoneInfo("UTC")),
                campaign_id=149007825,
                warehouse_id=10,
                offer_id="sku-1",
                stock_type="AVAILABLE",
                count=12,
                source_updated_at=datetime(2026, 8, 29, 23, 59, tzinfo=ZoneInfo("UTC")),
                raw_data={},
            ),
            YandexMarketStockSnapshot(
                snapshot_date=snapshot_date,
                captured_at=datetime(2026, 8, 30, 0, 1, tzinfo=ZoneInfo("UTC")),
                campaign_id=149007825,
                warehouse_id=10,
                offer_id="sku-zero",
                stock_type="AVAILABLE",
                count=0,
                source_updated_at=None,
                raw_data={},
            ),
        ])
        session.commit()

    filename, payload, caption = StockExcelReportService(
        session_factory=session_factory
    ).yandex_market(snapshot_date)

    assert filename == "yandex_market_stocks_2026-08-30.xlsx"
    assert "Яндекс Маркета" in caption
    workbook = load_workbook(BytesIO(payload), read_only=True)
    assert workbook.sheetnames == ["Сводка", "По складам"]
    assert list(workbook["Сводка"].values)[1] == (
        datetime(2026, 8, 30),
        149007825,
        "AVAILABLE",
        1,
        12,
    )
    warehouse_rows = list(workbook["По складам"].values)
    assert len(warehouse_rows) == 2
    assert warehouse_rows[1][4:7] == ("sku-1", "AVAILABLE", 12)
    workbook.close()


def test_sales_block_keeps_event_definitions_separate():
    block = TelegramReportService._sales_block("ПРОШЛЫЙ ДЕНЬ", sales_data())
    for text in ("Заказы: 14", "сейчас отменено: 2", "Отмен зарегистрировано в периоде: 6", "Выкупы: 14", "Возвраты: 1", "оперативный"):
        assert text in block


def test_sales_block_identifies_realtime_order_source():
    data = sales_data()
    data["orders_source"] = "order_feed"
    data["orders_last_updated_at"] = "2026-09-04T12:50:00+03:00"

    block = TelegramReportService._sales_block("СЕГОДНЯ", data)

    assert "WB Order Feed (реальное время)" in block
    assert "2026-09-04T12:50:00+03:00" in block


def test_yandex_market_orders_block_uses_saved_orders():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    with session_factory() as session:
        session.add(YandexMarketOrder(
            business_id=777,
            order_id=123,
            campaign_id=149010920,
            program_type="FBS",
            status="PROCESSING",
            created_at=datetime(2026, 9, 5, 8, 30, tzinfo=ZoneInfo("Europe/Moscow")),
            items_count=2,
            total_amount="1990",
            items=[],
            raw_data={},
            fetched_at=datetime(2026, 9, 5, 5, 31, tzinfo=ZoneInfo("UTC")),
        ))
        session.commit()

    report = TelegramReportService(session_factory=session_factory)
    block = report._yandex_market_orders_block(
        datetime(2026, 9, 5, 12, 0, tzinfo=ZoneInfo("Europe/Moscow"))
    )
    assert "Заказы: 1" in block
    assert "товаров: 2" in block
    assert "FBS 2" in block
    assert "1 990.00" in block


def test_ozon_orders_block_uses_saved_postings_and_shows_sync_status():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    with session_factory() as session:
        session.add_all([
            OzonPosting(
                posting_number="100-1",
                scheme="fbo",
                status="delivered",
                in_process_at=datetime(2026, 9, 5, 8, 30, tzinfo=ZoneInfo("Europe/Moscow")),
                products=[{"price": {"amount": "995", "currency": "RUB"}, "quantity": 2}],
                raw_data={},
                created_at=datetime(2026, 9, 5, 5, 31, tzinfo=ZoneInfo("UTC")),
                updated_at=datetime(2026, 9, 5, 5, 31, tzinfo=ZoneInfo("UTC")),
            ),
            OzonSyncRun(
                id="run-1",
                task="orders",
                started_at=datetime(2026, 9, 5, 9, 0, tzinfo=ZoneInfo("Europe/Moscow")),
                finished_at=datetime(2026, 9, 5, 9, 1, tzinfo=ZoneInfo("Europe/Moscow")),
                status="completed",
                result={"fbo": 1, "fbs": 0},
            ),
        ])
        session.commit()

    block = TelegramReportService(session_factory=session_factory)._ozon_orders_block(
        datetime(2026, 9, 5, 12, 0, tzinfo=ZoneInfo("Europe/Moscow"))
    )

    assert "ЗАКАЗЫ · СЕГОДНЯ" in block
    assert "Заказы: 1" in block
    assert "товаров: 2" in block
    assert "1 990.00" in block
    assert "FBO 1 / FBS 0" in block
    assert "Загрузка заказов: completed" in block


class EmptyPromotionService:
    def efficiency_summary(self, **kwargs):
        return {
            "spend": "0",
            "orders": 0,
            "attributed_revenue": "0",
            "drr_percent": None,
            "roas": None,
            "cpo": None,
        }


def test_operational_report_is_four_ordered_marketplace_messages():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    report = TelegramReportService(
        session_factory=session_factory,
        sales_summary=lambda date_from, date_to: sales_data(),
        promotion_service=EmptyPromotionService(),
        quality_summary=lambda: {
            "questions": {"total": 0, "answered": 0, "overdue": 0},
            "feedbacks": {"total": 0, "answered": 0, "overdue": 0},
        },
    )

    messages = report.operational_messages(
        datetime(2026, 9, 5, 12, 0, tzinfo=ZoneInfo("Europe/Moscow"))
    )

    assert [key for key, _ in messages] == ["wildberries", "ozon", "yandex_market", "summary"]
    assert "РЕКЛАМА · СЕГОДНЯ" in messages[0][1]
    assert "РЕКЛАМА" in messages[1][1]
    assert "РЕКЛАМА" in messages[2][1]
    assert "ИТОГО ПО МАРКЕТПЛЕЙСАМ" in messages[3][1]


def test_dispatcher_sends_operational_sections_separately_with_delay():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)

    class Client:
        chat_id = "-1001"

        def __init__(self):
            self.texts = []

        def send_text(self, content):
            self.texts.append(content)
            return [len(self.texts)]

    class Reports:
        def operational_messages(self, now):
            return [("wb", "WB"), ("ozon", "Ozon"), ("yandex", "Yandex"), ("summary", "Total")]

    client = Client()
    delays = []
    dispatcher = TelegramReportDispatcher(
        client,
        Reports(),
        session_factory=session_factory,
        message_delay_seconds=3,
        sleeper=delays.append,
    )
    delivery_keys = []

    def send_text_content(report_type, report_key, factory, **kwargs):
        delivery_keys.append(report_key)
        message_ids = client.send_text(factory())
        return {"status": "sent", "report_key": report_key, "message_ids": message_ids}

    dispatcher.send_text_content = send_text_content

    result = dispatcher.send("operational", "operational:1")

    assert client.texts == ["WB", "Ozon", "Yandex", "Total"]
    assert delays == [3, 3, 3]
    assert result["message_ids"] == [1, 2, 3, 4]
    assert delivery_keys == [
        "operational:1:wb",
        "operational:1:ozon",
        "operational:1:yandex",
        "operational:1:summary",
    ]


def test_sync_block_explains_failed_wb_task():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    with session_factory() as session:
        session.add(WBSyncRun(
            id="wb-run",
            status="partial",
            started_at=datetime(2026, 9, 5, 7, 0, tzinfo=ZoneInfo("UTC")),
            finished_at=datetime(2026, 9, 5, 7, 1, tzinfo=ZoneInfo("UTC")),
            tasks_total=2,
            tasks_succeeded=1,
            tasks_failed=1,
            results={
                "products": {"status": "ok"},
                "documents": {"status": "error", "error": "HTTP 429 rate limit"},
            },
        ))
        session.commit()

    block = TelegramReportService(session_factory=session_factory)._sync_block()

    assert "ошибок 1" in block
    assert "Ошибка documents: HTTP 429 rate limit" in block


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


def test_hourly_scheduler_uses_a_new_delivery_key_each_hour():
    dispatcher = FakeDispatcher()
    scheduler = TelegramReportScheduler(
        dispatcher,
        timezone_name="Europe/Moscow",
        morning_time="09:00",
        operational_interval_seconds=3600,
    )
    scheduler.run_pending(datetime(2026, 9, 4, 10, 5, tzinfo=ZoneInfo("Europe/Moscow")))
    scheduler.run_pending(datetime(2026, 9, 4, 11, 5, tzinfo=ZoneInfo("Europe/Moscow")))

    operational_keys = [key for report_type, key in dispatcher.calls if report_type == "operational"]
    assert len(operational_keys) == 2
    assert operational_keys[0] != operational_keys[1]
