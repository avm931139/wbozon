from wb.client import WBClient
import requests

import pytest

from wb.exceptions import WBAuthError, WBHTTPError, WBParseError, WBRateLimitError


class StubResponse:
    def __init__(self, status_code=200, payload=None, text="", content=b"json", headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.content = content
        self.headers = headers or {}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def test_client_requires_api_key(monkeypatch):
    monkeypatch.setattr("wb.client.WB_API_KEY", None)
    client = WBClient(api_key=None)
    try:
        client.get("/test")
    except WBAuthError:
        assert True
    else:
        assert False, "Expected authentication error"


def test_client_maps_401_to_auth_error():
    client = WBClient(api_key="test-key")
    client.session.request = lambda **kwargs: StubResponse(status_code=401)

    with pytest.raises(WBAuthError):
        client.get("/test", retries=1)


def test_client_retries_429_and_raises_rate_limit(monkeypatch):
    client = WBClient(api_key="test-key")
    attempts = 0

    def request(**kwargs):
        nonlocal attempts
        attempts += 1
        return StubResponse(status_code=429)

    client.session.request = request
    monkeypatch.setattr("wb.client.time.sleep", lambda seconds: None)

    with pytest.raises(WBRateLimitError):
        client.get("/test", retries=3)

    assert attempts == 3


def test_client_respects_retry_after_header(monkeypatch):
    client = WBClient(api_key="test-key")
    responses = iter([
        StubResponse(status_code=429, headers={"Retry-After": "7"}),
        StubResponse(status_code=200, payload={"ok": True}),
    ])
    waits = []
    client.session.request = lambda **kwargs: next(responses)
    monkeypatch.setattr("wb.client.time.sleep", waits.append)

    assert client.get("/test") == {"ok": True}
    assert waits == [7.0]


def test_client_retries_5xx(monkeypatch):
    client = WBClient(api_key="test-key")
    responses = iter(
        [
            StubResponse(status_code=503, text="unavailable"),
            StubResponse(status_code=200, payload={"data": []}),
        ]
    )
    client.session.request = lambda **kwargs: next(responses)
    monkeypatch.setattr("wb.client.time.sleep", lambda seconds: None)

    assert client.get("/test") == {"data": []}


def test_client_raises_after_network_retries(monkeypatch):
    client = WBClient(api_key="test-key")
    attempts = 0

    def request(**kwargs):
        nonlocal attempts
        attempts += 1
        raise requests.ConnectionError("offline")

    client.session.request = request
    monkeypatch.setattr("wb.client.time.sleep", lambda seconds: None)

    with pytest.raises(WBHTTPError):
        client.get("/test", retries=3)

    assert attempts == 3


def test_client_maps_invalid_json_to_parse_error():
    client = WBClient(api_key="test-key")
    client.session.request = lambda **kwargs: StubResponse(
        status_code=200,
        payload=ValueError("invalid json"),
    )

    with pytest.raises(WBParseError):
        client.get("/test", retries=1)


def test_client_returns_none_for_204_no_content():
    client = WBClient(api_key="test-key")
    client.session.request = lambda **kwargs: StubResponse(status_code=204, content=b"")

    assert client.get("/test", retries=1) is None
