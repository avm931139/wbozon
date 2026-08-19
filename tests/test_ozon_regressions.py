import requests
import pytest

from ozon.exceptions import OzonHTTPError, OzonParseError, OzonRateLimitError
from ozon.performance.client import OzonPerformanceClient
from ozon.services.overview_service import _finance_operation_id
from ozon.services.sync_service import OzonSyncService
from ozon.supplies import OzonSuppliesAPI


class Response:
    def __init__(self, status_code=200, payload=None, *, content=b"json", headers=None, text=""):
        self.status_code = status_code
        self.payload = payload
        self.content = content
        self.headers = headers or {}
        self.text = text

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def test_finance_fallback_identifier_is_stable_and_distinct():
    first = {"date": "2026-08-10", "type": "fee", "amount": "10"}
    reordered = {"amount": "10", "type": "fee", "date": "2026-08-10"}
    second = {"date": "2026-08-10", "type": "fee", "amount": "20"}

    assert _finance_operation_id(first) == _finance_operation_id(reordered)
    assert _finance_operation_id(first) != _finance_operation_id(second)
    assert _finance_operation_id({"operation_id": 42}) == "42"


def test_supply_list_does_not_claim_to_send_unsupported_date_filter():
    calls = []

    class Client:
        def post(self, path, *, json_body=None):
            calls.append((path, json_body))
            return {"order_ids": [1], "last_id": ""}

    assert OzonSuppliesAPI(Client()).list() == [{"supply_order_id": 1}]
    assert calls[0][1] == {"filter": {"states": list(range(1, 11))}, "limit": 100, "last_id": "", "sort_by": 1}


def test_periodic_ads_sync_is_skipped_without_credentials(monkeypatch):
    monkeypatch.setattr("ozon.services.sync_service.OZON_PERFORMANCE_CLIENT_ID", None)
    monkeypatch.setattr("ozon.services.sync_service.OZON_PERFORMANCE_CLIENT_SECRET", None)

    result = OzonSyncService.__new__(OzonSyncService).sync_ads()

    assert result["skipped"] is True


def test_performance_client_retries_network_errors(monkeypatch):
    attempts = 0

    class Session:
        def request(self, *args, **kwargs):
            nonlocal attempts
            attempts += 1
            raise requests.ConnectionError("offline")

    client = OzonPerformanceClient("client", "secret", session=Session())
    client.token = "token"
    monkeypatch.setattr("ozon.performance.client.time.sleep", lambda value: None)
    with pytest.raises(OzonHTTPError):
        client.request("GET", "/test", retries=3)
    assert attempts == 3


def test_performance_client_maps_rate_limit(monkeypatch):
    session = type("Session", (), {"request": lambda self, *args, **kwargs: Response(429)})()
    client = OzonPerformanceClient("client", "secret", session=session)
    client.token = "token"
    monkeypatch.setattr("ozon.performance.client.time.sleep", lambda value: None)
    with pytest.raises(OzonRateLimitError):
        client.request("GET", "/test", retries=1)


def test_performance_client_rejects_invalid_json():
    session = type("Session", (), {"request": lambda self, *args, **kwargs: Response(payload=ValueError("bad"))})()
    client = OzonPerformanceClient("client", "secret", session=session)
    client.token = "token"
    with pytest.raises(OzonParseError):
        client.request("GET", "/test")
