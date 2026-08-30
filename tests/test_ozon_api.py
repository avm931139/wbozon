from datetime import datetime, timezone

from ozon.communications import OzonCommunicationsAPI
from ozon.orders import OzonOrdersAPI
from ozon.products import OzonProductsAPI
from ozon.stocks import OzonStocksAPI


class QueueClient:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.calls = []

    def post(self, path, *, json_body=None, retries=3):
        self.calls.append((path, json_body))
        return next(self.payloads)


def test_products_follow_last_id_cursor():
    client = QueueClient([
        {"result": {"items": [{"product_id": 1}], "last_id": "next"}},
        {"result": {"items": [{"product_id": 2}], "last_id": ""}},
    ])
    assert [row["product_id"] for row in OzonProductsAPI(client).list(limit=1)] == [1, 2]
    assert client.calls[1][1]["last_id"] == "next"


def test_stocks_follow_cursor():
    client = QueueClient([
        {"items": [{"product_id": 1}], "cursor": "next"},
        {"items": [], "cursor": ""},
    ])
    assert OzonStocksAPI(client).list(limit=1) == [{"product_id": 1}]
    assert client.calls[1][1]["cursor"] == "next"


def test_fbs_postings_follow_cursor():
    client = QueueClient([
        {"postings": [{"posting_number": "1"}], "has_next": True, "cursor": "next"},
        {"postings": [{"posting_number": "2"}], "has_next": False, "cursor": ""},
    ])
    now = datetime(2026, 8, 9, tzinfo=timezone.utc)
    rows = OzonOrdersAPI(client).fbs_list(since=now, until=now, limit=1)
    assert [row["posting_number"] for row in rows] == ["1", "2"]
    assert client.calls[0][0] == "/v4/posting/fbs/list"
    assert client.calls[0][1]["sort_dir"] == "ASC"
    assert "offset" not in client.calls[0][1]
    assert "cursor" not in client.calls[0][1]
    assert client.calls[1][1]["cursor"] == "next"


def test_fbo_postings_use_v3_cursor_endpoint():
    client = QueueClient([
        {"postings": [{"posting_number": "1"}], "has_next": False, "cursor": ""},
    ])
    now = datetime(2026, 8, 9, tzinfo=timezone.utc)
    rows = OzonOrdersAPI(client).fbo_list(since=now, until=now)
    assert rows == [{"posting_number": "1"}]
    assert client.calls[0][0] == "/v3/posting/fbo/list"


def test_postings_reject_limit_above_new_api_maximum():
    now = datetime(2026, 8, 9, tzinfo=timezone.utc)
    try:
        OzonOrdersAPI(QueueClient([])).fbs_list(since=now, until=now, limit=101)
    except ValueError as exc:
        assert str(exc) == "Ozon postings page limit must be between 1 and 100"
    else:
        raise AssertionError("ValueError was not raised")


def test_reviews_use_v2_endpoint_and_follow_last_id():
    client = QueueClient([
        {"reviews": [{"id": "1"}], "has_next": True, "last_id": "next"},
        {"reviews": [{"id": "2"}], "has_next": False, "last_id": ""},
    ])
    rows = OzonCommunicationsAPI(client).reviews(limit=20)
    assert [row["id"] for row in rows] == ["1", "2"]
    assert client.calls[0][0] == "/v2/review/list"
    assert client.calls[0][1] == {"limit": 20, "sort_dir": "DESC"}
    assert client.calls[1][1]["last_id"] == "next"
