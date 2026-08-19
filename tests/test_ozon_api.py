from datetime import datetime, timezone

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


def test_fbs_postings_follow_offset():
    client = QueueClient([
        {"result": {"postings": [{"posting_number": "1"}], "has_next": True}},
        {"result": {"postings": [{"posting_number": "2"}], "has_next": False}},
    ])
    now = datetime(2026, 8, 9, tzinfo=timezone.utc)
    rows = OzonOrdersAPI(client).fbs_list(since=now, until=now, limit=1)
    assert [row["posting_number"] for row in rows] == ["1", "2"]
    assert client.calls[1][1]["offset"] == 1
