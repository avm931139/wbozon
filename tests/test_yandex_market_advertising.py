import io
import json
import zipfile
from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import YandexMarketAdDailyStat, YandexMarketBusiness
from yandex_market.advertising import YandexMarketAdvertisingAPI
from yandex_market.services.advertising_service import YandexMarketAdvertisingService


def _archive(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, rows in files.items():
            archive.writestr(name, json.dumps(rows))
    return output.getvalue()


class FakeClient:
    timeout = 10

    def __init__(self):
        self.calls = []

    def post(self, path, **kwargs):
        self.calls.append(("post", path, kwargs))
        return {"status": "OK", "result": {"reportId": "report-1"}}

    def get(self, path, **kwargs):
        self.calls.append(("get", path, kwargs))
        return {"status": "OK", "result": {"status": "DONE", "file": "https://storage.yandexcloud.net/report.zip"}}


class Response:
    status_code = 200
    headers = {}

    def __init__(self, content):
        self.content = content


class DownloadSession:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return Response(self.content)


def test_advertising_api_generates_waits_and_reads_json_archive():
    client = FakeClient()
    download = DownloadSession(_archive({"business_boost_consolidated.json": [{"billedAmount": 12}]}))
    api = YandexMarketAdvertisingAPI(client, download_session=download, sleeper=lambda _: None)

    report_id = api.generate("sales_boost", business_id=777, stat_date=date(2026, 9, 6))
    result = api.wait(report_id, attempts=1, pause_seconds=0)

    assert result["rows"][0][1] == [{"billedAmount": 12}]
    assert client.calls[0][2]["params"] == {"format": "JSON", "sourceType": "SELLER"}
    assert client.calls[0][2]["json_body"]["dateFrom"] == "2026-09-06"
    assert download.calls[0][1]["allow_redirects"] is False


def test_shelves_report_uses_click_attribution():
    client = FakeClient()
    api = YandexMarketAdvertisingAPI(client, download_session=object())

    api.generate("shelves", business_id=777, stat_date=date(2026, 9, 6))

    assert client.calls[0][1] == "/v2/reports/shelf-statistics/generate"
    assert client.calls[0][2]["json_body"]["attributionType"] == "CLICKS"


def test_advertising_service_persists_four_sources(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True)

    class API:
        source = None

        def generate(self, source, **kwargs):
            self.source = source
            return source

        def wait(self, report_id, **kwargs):
            names = {
                "sales_boost": "business_boost_consolidated.json",
                "shows_boost": "business_shows_boost_consolidated_campaigns.json",
                "shelves": "shelfs_statistics_summary.json",
                "banners": "banners_statistics_report_consolidated.json",
            }
            rows = {
                "sales_boost": [{
                    "showsWithFee": 10, "clicksVendorWithFee": 4,
                    "orderItemsDeliveredWithFee": 2, "billedAmount": 100,
                    "ordersGvmDeliveredWithFee": 1000,
                }],
                "shows_boost": [{
                    "date": "2026-09-06", "saleCampaignId": 20,
                    "shows": 30, "clicks": 5, "orderedCount": 3,
                    "realCost": 200, "orderedAmount": 2000,
                }],
                "shelves": [{
                    "campaignId": 30, "shows": 5, "clicks": 1,
                    "orderedCount": 1, "realCost": 50, "orderedAmount": 400,
                }],
                "banners": [],
            }
            return {"status": "DONE", "rows": [(names[report_id], rows[report_id])]}

    service = YandexMarketAdvertisingService(
        api=API(), session_factory=factory, business_id=777
    )
    result = service.sync(stat_date=date(2026, 9, 6))

    assert set(result["sources"]) == {"sales_boost", "shows_boost", "shelves", "banners"}
    with factory() as session:
        rows = session.query(YandexMarketAdDailyStat).all()
        assert len(rows) == 4
        assert sum(row.views for row in rows) == 45
        assert sum(row.clicks for row in rows) == 10
        assert sum(row.orders for row in rows) == 6
        assert sum(row.spend for row in rows) == 350
        assert sum(row.attributed_revenue for row in rows) == 3400


def test_no_data_report_is_saved_as_zero_day():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True)

    service = YandexMarketAdvertisingService(
        api=object(), session_factory=factory, business_id=777
    )
    assert service._replace("banners", date(2026, 9, 6), []) == 1
    with factory() as session:
        row = session.query(YandexMarketAdDailyStat).one()
        assert row.source == "banners"
        assert row.spend == 0


def test_business_id_is_discovered_from_identity_data():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        session.add(YandexMarketBusiness(
            business_id=216673578,
            name="Cabinet",
            raw_data={},
            fetched_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
        ))
        session.commit()

    service = YandexMarketAdvertisingService(
        api=object(), session_factory=factory, business_id=None
    )
    assert service._business_id() == 216673578


def test_automatic_advertising_sync_backfills_newest_missing_day(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        for source in YandexMarketAdvertisingService.SOURCES:
            session.add(YandexMarketAdDailyStat(
                stat_date=date(2026, 9, 6),
                source=source,
                business_id=777,
                campaign_id="total",
                fetched_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
            ))
        session.commit()

    monkeypatch.setattr(
        "yandex_market.services.advertising_service.YANDEX_MARKET_HISTORY_FROM",
        "2026-09-01",
    )
    monkeypatch.setattr(
        "yandex_market.services.advertising_service.YANDEX_MARKET_AD_HISTORY_DAYS", 90
    )
    service = YandexMarketAdvertisingService(
        api=object(), session_factory=factory, business_id=777
    )

    assert service._target_date(date(2026, 9, 6)) == date(2026, 9, 5)


def test_advertising_backfill_requests_only_missing_sources():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        for source in ("sales_boost", "shows_boost", "banners"):
            session.add(YandexMarketAdDailyStat(
                stat_date=date(2026, 9, 5), source=source, business_id=777,
                campaign_id=0, fetched_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
            ))
        session.commit()

    service = YandexMarketAdvertisingService(
        api=object(), session_factory=factory, business_id=777
    )

    assert service._sources_for_date(date(2026, 9, 5)) == ("shelves",)
    assert service._sources_for_date(date(2026, 9, 4)) == service.SOURCES
