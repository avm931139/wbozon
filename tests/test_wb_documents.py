from datetime import date
import base64
from io import BytesIO
import zipfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import WBDocument, WBDocumentFile, WBFinanceBalanceSnapshot
from wb.documents import DocumentsAPI
from wb.document_storage import DocumentStorage
from wb.exceptions import WBParseError
from wb.finances import FinancesAPI
from wb.services.document_service import DocumentService
from wb.document_sync import WBDocumentSyncRunner, WBDocumentSyncSettings


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses if isinstance(responses, list) else [responses])
        self.calls = []

    def get(self, path, *, params=None, retries=3):
        self.calls.append(("GET", path, params, None))
        return next(self.responses)

    def post(self, path, *, json_body=None, retries=3):
        self.calls.append(("POST", path, None, json_body))
        return next(self.responses)


def test_document_categories_extract_rows():
    client = FakeClient({"data": {"categories": [{"name": "upd", "title": "УПД"}]}})
    assert DocumentsAPI(client).categories() == [{"name": "upd", "title": "УПД"}]
    assert client.calls == [("GET", "/api/v1/documents/categories", {"locale": "ru"}, None)]


def test_documents_list_paginates_and_uses_official_parameters():
    client = FakeClient([
        {"data": {"documents": [{"serviceName": str(i)} for i in range(2)]}},
        {"data": {"documents": []}},
    ])
    result = DocumentsAPI(client).list(
        date(2026, 8, 1), date(2026, 8, 31), sort="date", order="desc", limit=2
    )
    assert len(result) == 2
    assert client.calls[0] == ("GET", "/api/v1/documents/list", {
        "locale": "ru", "limit": 2, "beginTime": "2026-08-01", "endTime": "2026-08-31",
        "sort": "date", "order": "desc", "offset": 0,
    }, None)
    assert client.calls[1][2]["offset"] == 2


def test_document_downloads_extract_data_and_validate_batch():
    single = FakeClient({"data": {"fileName": "one.zip", "document": "abc", "extension": "zip"}})
    assert DocumentsAPI(single).download("doc-1", "zip")["document"] == "abc"
    assert single.calls[0] == ("GET", "/api/v1/documents/download", {
        "serviceName": "doc-1", "extension": "zip",
    }, None)

    batch = FakeClient({
        "data": {"fileName": "documents.zip", "extension": "zip", "document": "xyz"}
    })
    refs = [{"serviceName": "doc-1", "extension": "zip"}]
    assert DocumentsAPI(batch).download_all(refs)["document"] == "xyz"
    assert batch.calls[0] == ("POST", "/api/v1/documents/download/all", None, {"params": refs})

    with pytest.raises(ValueError, match="between 1 and 50"):
        DocumentsAPI(batch).download_all([])


def test_document_list_requires_parameter_pairs():
    api = DocumentsAPI(FakeClient({}))
    with pytest.raises(ValueError, match="begin_time and end_time"):
        api.list(begin_time=date(2026, 8, 1))
    with pytest.raises(ValueError, match="sort and order"):
        api.list(sort="date")
    with pytest.raises(ValueError, match="only for locale='ru'"):
        api.list(locale="en", sort="category", order="asc")


def test_document_list_rejects_repeated_page():
    page = {"data": {"documents": [{"serviceName": "same"}]}}
    api = DocumentsAPI(FakeClient([page, page]))
    with pytest.raises(WBParseError, match="repeated the same page"):
        api.list(limit=1)


def test_finance_balance_uses_current_endpoint():
    client = FakeClient({"currency": "RUB", "current": 1200, "for_withdraw": 900})
    assert FinancesAPI(client).balance() == {
        "currency": "RUB", "current": 1200, "for_withdraw": 900,
    }
    assert client.calls == [("GET", "/api/v1/account/balance", None, None)]


def test_document_storage_decodes_base64_and_confines_file_to_root(tmp_path):
    content = b"%PDF-1.7\naccounting document"
    stored = DocumentStorage(tmp_path).save("../doc:1", {
        "fileName": "../../UPD 1.exe",
        "extension": "pdf",
        "document": base64.b64encode(content).decode("ascii"),
    })

    assert stored.path.read_bytes() == content
    assert stored.path.is_relative_to(tmp_path)
    assert stored.file_name == "UPD 1.pdf"
    assert stored.relative_path == "_doc_1/UPD 1.pdf"
    assert stored.size == len(content)
    assert len(stored.sha256) == 64
    assert DocumentStorage(tmp_path).verify(
        stored.relative_path,
        size=stored.size,
        sha256=stored.sha256,
    )


def test_document_storage_rejects_invalid_base64(tmp_path):
    with pytest.raises(ValueError, match="invalid base64"):
        DocumentStorage(tmp_path).save("doc-1", {
            "fileName": "one.zip", "extension": "zip", "document": "not base64!",
        })


def test_document_storage_rejects_unsafe_or_unexpected_extension(tmp_path):
    encoded = base64.b64encode(b"binary data").decode("ascii")
    with pytest.raises(ValueError, match="invalid extension"):
        DocumentStorage(tmp_path).save("doc-1", {
            "fileName": "one.bin", "extension": "../bin", "document": encoded,
        })
    with pytest.raises(ValueError, match="extension mismatch"):
        DocumentStorage(tmp_path).save(
            "doc-1",
            {"fileName": "one.zip", "extension": "zip", "document": encoded},
            expected_extension="pdf",
        )


def _zip_bytes(files=None):
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in (files or {"document.txt": b"data"}).items():
            archive.writestr(name, content)
    return output.getvalue()


def test_document_storage_validates_zip_xlsx_and_size(tmp_path):
    zip_content = _zip_bytes()
    zip_stored = DocumentStorage(tmp_path).save("zip-doc", {
        "fileName": "archive.zip",
        "extension": "zip",
        "document": base64.b64encode(zip_content).decode("ascii"),
    })
    assert zip_stored.path.read_bytes() == zip_content

    xlsx_content = _zip_bytes({
        "[Content_Types].xml": b"types",
        "xl/workbook.xml": b"workbook",
    })
    xlsx_stored = DocumentStorage(tmp_path).save("xlsx-doc", {
        "fileName": "report.xlsx",
        "extension": "xlsx",
        "document": base64.b64encode(xlsx_content).decode("ascii"),
    })
    assert xlsx_stored.extension == "xlsx"

    with pytest.raises(ValueError, match="not a valid ZIP"):
        DocumentStorage(tmp_path).save("bad-zip", {
            "fileName": "bad.zip",
            "extension": "zip",
            "document": base64.b64encode(b"not a zip").decode("ascii"),
        })
    with pytest.raises(ValueError, match="configured limit"):
        DocumentStorage(tmp_path, max_file_bytes=3).save("large", {
            "fileName": "large.bin",
            "extension": "bin",
            "document": base64.b64encode(b"1234").decode("ascii"),
        })


class FakeDocumentsAPI:
    def __init__(self):
        self.download_calls = []

    def categories(self, locale="ru"):
        return [{"name": "redeem-notification", "title": "Уведомление"}]

    def list(self, begin_time=None, end_time=None, *, locale="ru"):
        return [{
            "serviceName": "redeem-notification-1",
            "name": "redeem-notification",
            "category": "Уведомление",
            "extensions": ["pdf", "zip"],
            "creationTime": "2026-08-31T10:15:00Z",
            "viewed": False,
        }]

    def download(self, service_name, extension):
        self.download_calls.append((service_name, extension))
        content = b"%PDF-1.7\ndocument" if extension == "pdf" else _zip_bytes()
        return {
            "fileName": f"{service_name}.{extension}",
            "extension": extension,
            "document": base64.b64encode(content).decode("ascii"),
        }


class FakeFinancesAPI:
    def balance(self):
        return {"currency": "RUB", "current": 1200.25, "for_withdraw": 900.10}


def test_document_service_persists_metadata_balance_and_every_extension(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    documents_api = FakeDocumentsAPI()
    service = DocumentService(
        documents_api=documents_api,
        finances_api=FakeFinancesAPI(),
        storage=DocumentStorage(tmp_path),
        session_factory=session_factory,
    )

    result = service.sync_all(download_limit=5)

    assert result["categories"] == 1
    assert result["documents"] == 1
    assert result["files"] == {
        "selected": 2, "downloaded": 2, "failed": 0, "errors": [],
    }
    assert documents_api.download_calls == [
        ("redeem-notification-1", "pdf"),
        ("redeem-notification-1", "zip"),
    ]
    with session_factory() as session:
        document = session.query(WBDocument).one()
        assert document.category == "redeem-notification"
        assert document.title == "Уведомление"
        assert document.document_created_at is not None
        assert document.viewed is False
        assert session.query(WBDocumentFile).count() == 2
        balance = session.query(WBFinanceBalanceSnapshot).one()
        assert balance.currency == "RUB"
        assert str(balance.current) == "1200.25"

    assert service.sync_missing_files(limit=5)["selected"] == 0
    assert len(documents_api.download_calls) == 2

    pdf_path = tmp_path / "redeem-notification-1" / "redeem-notification-1.pdf"
    pdf_path.write_bytes(b"corrupted")
    retry = service.sync_missing_files(limit=5)
    assert retry["selected"] == 1
    assert retry["downloaded"] == 1
    assert len(documents_api.download_calls) == 3


class RecordingDocumentService:
    def __init__(self, *, fail_balance=False):
        self.calls = []
        self.fail_balance = fail_balance

    def sync_categories(self, locale):
        self.calls.append(("categories", locale))
        return 3

    def sync_documents(self, begin_date, end_date, locale):
        self.calls.append(("documents", begin_date, end_date, locale))
        return 10

    def sync_balance(self):
        self.calls.append(("balance",))
        if self.fail_balance:
            raise RuntimeError("finance token forbidden")
        return {"currency": "RUB", "current": 100, "for_withdraw": 90}

    def sync_missing_files(self, limit):
        self.calls.append(("files", limit))
        return {"selected": 2, "downloaded": 2, "failed": 0, "errors": []}


def test_document_runner_journals_success_and_keeps_steps_independent():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    service = RecordingDocumentService(fail_balance=True)
    runner = WBDocumentSyncRunner(
        service=service,
        settings=WBDocumentSyncSettings(download_limit=4),
        session_factory=session_factory,
    )

    result = runner.run(
        begin_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
    )

    assert result["status"] == "partial"
    assert "finance token forbidden" in result["error"]
    assert service.calls[-1] == ("files", 4)
    with session_factory() as session:
        from app.models import WBDocumentSyncRun

        row = session.query(WBDocumentSyncRun).one()
        assert row.status == "partial"
        assert row.finished_at is not None
        assert row.result["files"]["status"] == "completed"
