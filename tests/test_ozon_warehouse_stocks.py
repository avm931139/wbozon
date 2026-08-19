import pytest

from ozon.endpoints import OzonEndpoints
from ozon.exceptions import OzonParseError
from ozon.warehouse_stocks import OzonWarehouseStocksAPI


class QueueClient:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.calls = []

    def post(self, path, *, json_body=None, retries=3):
        self.calls.append((path, json_body))
        return next(self.payloads)


def test_fbo_warehouse_stocks_follow_cursor_and_use_verified_body():
    client = QueueClient([
        {"products": [{"sku": 1, "warehouse_id": 10}], "has_next": True, "cursor": "next"},
        {"products": [{"sku": 1, "warehouse_id": 20}], "has_next": False, "cursor": ""},
    ])

    rows = OzonWarehouseStocksAPI(client).list_fbo(skus=[1, 1], limit=1000)

    assert [row["warehouse_id"] for row in rows] == [10, 20]
    assert client.calls == [
        (OzonEndpoints.FBO_STOCKS_BY_WAREHOUSE, {"limit": 1000, "skus": [1], "cursor": ""}),
        (OzonEndpoints.FBO_STOCKS_BY_WAREHOUSE, {"limit": 1000, "skus": [1], "cursor": "next"}),
    ]


def test_fbs_warehouse_stocks_use_current_v2_contract():
    client = QueueClient([
        {"products": [{"sku": 1, "warehouse_id": 30}], "has_next": False, "cursor": ""},
    ])

    rows = OzonWarehouseStocksAPI(client).list_fbs(skus=[1], limit=500)

    assert rows == [{"sku": 1, "warehouse_id": 30}]
    assert client.calls == [
        (OzonEndpoints.FBS_STOCKS_BY_WAREHOUSE, {"sku": [1], "limit": 500, "cursor": ""}),
    ]


def test_analytics_stocks_are_batched_at_verified_maximum():
    client = QueueClient([
        {"items": [{"sku": 1, "warehouse_id": 10}]},
        {"items": [{"sku": 101, "warehouse_id": 20}]},
    ])

    rows = OzonWarehouseStocksAPI(client).list_analytics(skus=list(range(1, 102)))

    assert len(rows) == 2
    assert len(client.calls[0][1]["skus"]) == 100
    assert client.calls[1][1]["skus"] == [101]
    assert all(path == OzonEndpoints.ANALYTICS_STOCKS for path, _ in client.calls)


@pytest.mark.parametrize("limit", [0, 1001])
def test_warehouse_stock_limit_is_validated(limit):
    with pytest.raises(ValueError, match="limit"):
        OzonWarehouseStocksAPI(QueueClient([])).list_fbo(skus=[1], limit=limit)


def test_warehouse_stock_filters_are_required():
    api = OzonWarehouseStocksAPI(QueueClient([]))
    with pytest.raises(ValueError, match="skus or offer_ids"):
        api.list_fbo()
    with pytest.raises(ValueError, match="skus"):
        api.list_fbs(skus=[])


def test_cursor_must_advance_when_more_rows_are_declared():
    client = QueueClient([
        {"products": [], "has_next": True, "cursor": ""},
    ])

    with pytest.raises(OzonParseError, match="cursor"):
        OzonWarehouseStocksAPI(client).list_fbo(skus=[1])
