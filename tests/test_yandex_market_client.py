import requests
import pytest

from yandex_market.client import YandexMarketClient
from yandex_market.exceptions import (
    YandexMarketAuthError,
    YandexMarketHTTPError,
    YandexMarketParseError,
    YandexMarketRateLimitError,
)


class StubResponse:
    def __init__(self, status_code=200, payload=None, text="", headers=None):
        self.status_code = status_code
        self.payload = payload
        self.text = text
        self.headers = headers or {}

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def test_client_uses_api_key_and_closes_connection():
    calls = []
    session = type(
        "Session",
        (),
        {"post": lambda self, *args, **kwargs: calls.append((args, kwargs)) or StubResponse(payload={"status": "OK"})},
    )()

    result = YandexMarketClient("secret", session=session).post(
        "/v2/test",
        params={"limit": 100},
        json_body={"withTurnover": False},
    )

    assert result == {"status": "OK"}
    assert calls[0][1]["headers"]["Api-Key"] == "secret"
    assert calls[0][1]["headers"]["Connection"] == "close"
    assert calls[0][1]["params"] == {"limit": 100}


def test_client_get_does_not_send_json_body():
    calls = []
    session = type(
        "Session",
        (),
        {"get": lambda self, *args, **kwargs: calls.append((args, kwargs)) or StubResponse(payload={"campaigns": []})},
    )()

    result = YandexMarketClient("secret", session=session).get(
        "/v2/campaigns", params={"limit": 100}
    )

    assert result == {"campaigns": []}
    assert "json" not in calls[0][1]


def test_client_requires_api_key(monkeypatch):
    monkeypatch.setattr("yandex_market.client.YANDEX_MARKET_API_KEY", None)
    with pytest.raises(YandexMarketAuthError):
        YandexMarketClient(api_key="", base_url="https://example.test").post("/test")


@pytest.mark.parametrize(
    "status,error",
    [(401, YandexMarketAuthError), (403, YandexMarketAuthError), (420, YandexMarketRateLimitError)],
)
def test_client_maps_http_errors(status, error):
    session = type(
        "Session",
        (),
        {"post": lambda self, *args, **kwargs: StubResponse(status_code=status)},
    )()
    with pytest.raises(error):
        YandexMarketClient("secret", session=session, sleeper=lambda value: None).post(
            "/test", retries=1
        )


def test_client_retries_network_errors():
    attempts = 0

    class Session:
        def post(self, *args, **kwargs):
            nonlocal attempts
            attempts += 1
            raise requests.ConnectionError("offline")

    with pytest.raises(YandexMarketHTTPError, match="request failed"):
        YandexMarketClient("secret", session=Session(), sleeper=lambda value: None).post(
            "/test", retries=3
        )
    assert attempts == 3


def test_client_rejects_invalid_json_and_error_payload():
    invalid = type(
        "Session",
        (),
        {"post": lambda self, *args, **kwargs: StubResponse(payload=ValueError("bad"))},
    )()
    with pytest.raises(YandexMarketParseError):
        YandexMarketClient("secret", session=invalid).post("/test")

    rejected = type(
        "Session",
        (),
        {"post": lambda self, *args, **kwargs: StubResponse(payload={"status": "ERROR", "errors": [{"code": "BAD", "message": "invalid"}]})},
    )()
    with pytest.raises(YandexMarketHTTPError, match="BAD: invalid"):
        YandexMarketClient("secret", session=rejected).post("/test")
