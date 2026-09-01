from __future__ import annotations

from datetime import date
from io import BytesIO
import zipfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    OzonAccountingReport,
    OzonAccountingReportFile,
    OzonAccountingReportRequest,
    OzonAccountingSnapshot,
)
from ozon.accounting import OzonAccountingAPI
from ozon.accounting_storage import (
    DownloadedReport,
    OzonAccountingStorage,
    OzonReportDownloader,
)
from ozon.exceptions import OzonHTTPError
from ozon.services.accounting_service import OzonAccountingService
from ozon.services.sync_service import OzonSyncService


class QueueClient:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.calls = []

    def post(self, path, *, json_body=None, retries=3):
        self.calls.append((path, json_body, retries))
        return next(self.payloads)


def _xlsx_bytes() -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", "types")
        archive.writestr("xl/workbook.xml", "workbook")
    return output.getvalue()


def test_accounting_api_creates_reports_and_paginates_registry():
    create_client = QueueClient([
        {"result": {"code": "mutual-code"}},
        {"code": "posting-code"},
    ])
    api = OzonAccountingAPI(create_client)
    assert api.create_monthly_report("MUTUAL_SETTLEMENT", date(2026, 7, 1))["result"]["code"] == "mutual-code"
    assert api.create_monthly_report("REALIZATION_POSTING_REPORT", date(2026, 7, 1))["code"] == "posting-code"
    assert create_client.calls[0][0] == "/v1/finance/mutual-settlement"
    assert create_client.calls[0][1] == {"date": "2026-07", "language": "RU"}
    assert create_client.calls[1][0] == "/v1/report/realization/posting/create"

    list_client = QueueClient([
        {"result": {"reports": [{"code": "1"}], "total": 2}},
        {"result": {"reports": [{"code": "2"}], "total": 2}},
    ])
    rows = OzonAccountingAPI(list_client).reports(page_size=1)
    assert [row["code"] for row in rows] == ["1", "2"]
    assert list_client.calls[1][1]["page"] == 2


def test_accounting_api_uses_current_period_contracts():
    client = QueueClient([
        {"date_from": "2026-07-01", "date_to": "2026-07-31", "invoices": []},
        {"result": {"rows": []}},
        {"products": []},
        {"cashflows": [], "total": {}},
        {"result": {"cash_flows": [], "details": {}}, "page_count": 1},
    ])
    api = OzonAccountingAPI(client)
    api.b2b_sales_json(date(2026, 7, 1))
    api.realization(date(2026, 7, 1))
    api.products_buyout(date(2026, 7, 1), date(2026, 7, 31))
    api.balance(date(2026, 7, 2), date(2026, 7, 31))
    api.cash_flow(date(2026, 7, 1), date(2026, 7, 15))
    assert [call[0] for call in client.calls] == [
        "/v1/finance/document-b2b-sales/json",
        "/v2/finance/realization",
        "/v1/finance/products/buyout",
        "/v1/finance/balance",
        "/v1/finance/cash-flow-statement/list",
    ]
    with pytest.raises(ValueError, match="30 days"):
        api.balance(date(2026, 7, 1), date(2026, 8, 1))
    with pytest.raises(ValueError, match="30 days"):
        api.products_buyout(date(2026, 7, 1), date(2026, 8, 1))


class FakeResponse:
    def __init__(self, url="https://files.ozone.ru/report.xlsx"):
        self.url = url
        self.status_code = 200
        self.content = _xlsx_bytes()
        self.headers = {
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "Content-Disposition": "attachment; filename=finance.xlsx",
        }

    def raise_for_status(self):
        return None


class FakeDownloadSession:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(url)


def test_report_downloader_does_not_forward_credentials_and_checks_host():
    session = FakeDownloadSession()
    downloader = OzonReportDownloader(
        session=session,
        allowed_host_suffixes=("ozone.ru",),
    )
    report = downloader.download("https://files.ozone.ru/signed/report.xlsx")
    assert report.file_name == "finance.xlsx"
    assert session.calls[0][1]["headers"] == {"Accept": "application/octet-stream,*/*"}
    assert session.calls[0][1]["allow_redirects"] is False
    with pytest.raises(ValueError, match="not allowed"):
        downloader.download("https://example.org/report.xlsx")
    with pytest.raises(ValueError, match="HTTPS"):
        downloader.download("http://files.ozone.ru/report.xlsx")


def test_report_downloader_validates_redirect_before_following_it():
    class RedirectResponse:
        status_code = 302
        url = "https://files.ozone.ru/report.xlsx"
        headers = {"Location": "https://internal.example.org/secret"}

    class RedirectSession:
        def __init__(self):
            self.calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            return RedirectResponse()

    session = RedirectSession()
    downloader = OzonReportDownloader(
        session=session,
        allowed_host_suffixes=("ozone.ru",),
    )
    with pytest.raises(ValueError, match="not allowed"):
        downloader.download("https://files.ozone.ru/report.xlsx")
    assert session.calls == 1


def test_accounting_storage_is_atomic_confined_and_verified(tmp_path):
    storage = OzonAccountingStorage(tmp_path)
    stored = storage.save(
        "../MUTUAL_SETTLEMENT",
        "../../code",
        DownloadedReport(
            content=_xlsx_bytes(),
            file_name="../../finance.exe.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            source_url="https://files.ozone.ru/report.xlsx",
        ),
    )
    assert stored.relative_path == "_MUTUAL_SETTLEMENT/_.._code/finance.exe.xlsx"
    assert storage.verify(stored.relative_path, size=stored.size, sha256=stored.sha256)
    (tmp_path / stored.relative_path).write_bytes(b"damaged")
    assert not storage.verify(stored.relative_path, size=stored.size, sha256=stored.sha256)


class FakeAccountingAPI:
    def __init__(self):
        self.created = []

    def create_monthly_report(self, report_type, period_start):
        code = f"{report_type}:{period_start:%Y-%m}"
        self.created.append(code)
        if report_type == "REALIZATION_POSTING_REPORT":
            return {"code": code}
        return {"result": {"code": code}}

    def reports(self, report_type="ALL"):
        return [
            {
                "code": code,
                "report_type": code.split(":", 1)[0],
                "status": "success",
                "file": f"https://files.ozone.ru/{index}.xlsx",
                "params": {},
                "created_at": "2026-02-01T00:00:00Z",
                "expires_at": "2026-02-04T00:00:00Z",
            }
            for index, code in enumerate(self.created)
        ]

    def report_info(self, code):
        raise AssertionError(f"unexpected report_info call for {code}")

    def b2b_sales_json(self, period_start):
        return {"invoices": [], "period": str(period_start)}

    def realization(self, period_start):
        return {"result": {"rows": []}, "period": str(period_start)}

    def products_buyout(self, date_from, date_to):
        return {"products": [], "from": str(date_from), "to": str(date_to)}

    def cash_flow(self, date_from, date_to):
        return {"result": {"cash_flows": []}, "from": str(date_from), "to": str(date_to)}

    def balance(self, date_from, date_to):
        return {"cashflows": [], "total": {"available": 100}}


class FakeDownloader:
    def download(self, url):
        return DownloadedReport(
            content=_xlsx_bytes(),
            file_name=PathFromUrl(url),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            source_url=url,
        )


def PathFromUrl(url):
    return f"{url.rsplit('/', 1)[-1]}"


def test_accounting_service_backfills_once_and_keeps_files_idempotent(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    api = FakeAccountingAPI()
    service = OzonAccountingService(
        api=api,
        downloader=FakeDownloader(),
        storage=OzonAccountingStorage(tmp_path),
        session_factory=session_factory,
        history_from=date(2026, 1, 1),
        today=lambda: date(2026, 2, 1),
    )

    result = service.sync_all(download_limit=5)
    assert result["requests"] == {
        "requested": 5,
        "unavailable": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
    }
    assert result["registry"] == 5
    assert result["files"] == {"selected": 5, "downloaded": 5, "failed": 0, "errors": []}
    assert result["snapshots"] == {"saved": 6, "skipped": 0, "failed": 0, "errors": []}
    assert not [key for key in result if key.endswith("_error")]

    with session_factory() as session:
        assert session.query(OzonAccountingReportRequest).count() == 5
        assert session.query(OzonAccountingReport).count() == 5
        assert session.query(OzonAccountingReportFile).count() == 5
        assert session.query(OzonAccountingSnapshot).count() == 6

    repeated = service.sync_all(download_limit=5)
    assert repeated["requests"]["requested"] == 0
    assert repeated["requests"]["skipped"] == 5
    assert repeated["files"]["selected"] == 0
    assert repeated["snapshots"]["skipped"] == 6


def test_missing_monthly_documents_are_persisted_as_normal_absence(tmp_path):
    class MissingDocumentAPI(FakeAccountingAPI):
        def create_monthly_report(self, report_type, period_start):
            if report_type in {"COMPENSATION_REPORT", "DECOMPENSATION_REPORT"}:
                raise OzonHTTPError(
                    "Ozon API returned HTTP 404: document not found"
                )
            return super().create_monthly_report(report_type, period_start)

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    api = MissingDocumentAPI()
    service = OzonAccountingService(
        api=api,
        downloader=FakeDownloader(),
        storage=OzonAccountingStorage(tmp_path),
        session_factory=session_factory,
        history_from=date(2026, 1, 1),
        today=lambda: date(2026, 2, 1),
    )

    first = service.request_missing_reports()
    assert first == {
        "requested": 3,
        "unavailable": 2,
        "skipped": 0,
        "failed": 0,
        "errors": [],
    }
    with session_factory() as session:
        missing = session.query(OzonAccountingReportRequest).filter_by(
            status="not_found"
        ).all()
        assert {row.report_type for row in missing} == {
            "COMPENSATION_REPORT",
            "DECOMPENSATION_REPORT",
        }

    repeated = service.request_missing_reports()
    assert repeated == {
        "requested": 0,
        "unavailable": 0,
        "skipped": 5,
        "failed": 0,
        "errors": [],
    }


def test_documents_are_an_independent_ozon_task():
    assert "documents" in OzonSyncService.task_names()
