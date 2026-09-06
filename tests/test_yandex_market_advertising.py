import io
import json
import zipfile
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import YandexMarketAdDailyStat
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


def test_advertising_service_persists_three_sources(monkeypatch):
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
                "banners": [],
            }
            return {"status": "DONE", "rows": [(names[report_id], rows[report_id])]}

    service = YandexMarketAdvertisingService(
        api=API(), session_factory=factory, business_id=777
    )
    result = service.sync(stat_date=date(2026, 9, 6))

    assert set(result["sources"]) == {"sales_boost", "shows_boost", "banners"}
    with factory() as session:
        rows = session.query(YandexMarketAdDailyStat).all()
        assert len(rows) == 3
        assert sum(row.views for row in rows) == 40
        assert sum(row.clicks for row in rows) == 9
        assert sum(row.orders for row in rows) == 5
        assert sum(row.spend for row in rows) == 300
        assert sum(row.attributed_revenue for row in rows) == 3000


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
