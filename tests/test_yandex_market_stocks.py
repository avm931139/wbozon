import pytest

from yandex_market.exceptions import YandexMarketParseError
from yandex_market.stocks import YandexMarketStocksAPI


class QueueClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return self.responses.pop(0)


def test_stocks_follow_page_tokens_and_flatten_warehouses():
    client = QueueClient([
        {
            "status": "OK",
            "result": {
                "warehouses": [{
                    "warehouseId": 700,
                    "offers": [{
                        "offerId": "sku-1",
                        "stocks": [{"type": "AVAILABLE", "count": 4}],
                        "updatedAt": "2026-08-30T12:00:00Z",
                    }],
                }],
                "paging": {"nextPageToken": "next"},
            },
        },
        {
            "status": "OK",
            "result": {
                "warehouses": [{
                    "warehouseId": 701,
                    "offers": [{"offerId": "sku-2", "stocks": [{"type": "FIT", "count": 8}]}],
                }],
                "paging": {},
            },
        },
    ])

    rows = YandexMarketStocksAPI(client).list(campaign_id=123)

    assert [(row["campaignId"], row["warehouseId"], row["offerId"]) for row in rows] == [
        (123, 700, "sku-1"),
        (123, 701, "sku-2"),
    ]
    assert client.calls[0][0] == "/v2/campaigns/123/offers/stocks"
    assert client.calls[0][1]["params"] == {"limit": 100}
    assert client.calls[1][1]["params"] == {"limit": 100, "pageToken": "next"}


@pytest.mark.parametrize("limit", [0, 101])
def test_stocks_validate_limit(limit):
    with pytest.raises(ValueError):
        YandexMarketStocksAPI(QueueClient([])).list(campaign_id=1, limit=limit)


def test_stocks_reject_repeated_page_token():
    response = {
        "status": "OK",
        "result": {"warehouses": [], "paging": {"nextPageToken": "same"}},
    }
    client = QueueClient([response, response])
    with pytest.raises(YandexMarketParseError, match="did not advance"):
        YandexMarketStocksAPI(client).list(campaign_id=1)
