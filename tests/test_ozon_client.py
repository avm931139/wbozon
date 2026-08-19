import requests
import pytest

from ozon.client import OzonClient
from ozon.exceptions import OzonAuthError, OzonHTTPError, OzonParseError, OzonRateLimitError


class StubResponse:
    def __init__(self, status_code=200, payload=None, text="", content=b"json"):
        self.status_code = status_code
        self.payload = payload
        self.text = text
        self.content = content

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def test_client_uses_ozon_auth_headers():
    calls = []
    session = type("Session", (), {"post": lambda self, *args, **kwargs: calls.append((args, kwargs)) or StubResponse(payload={"ok": True})})()
    client = OzonClient("client", "secret", session=session)
    assert client.post("/test") == {"ok": True}
    assert calls[0][1]["headers"]["Client-Id"] == "client"
    assert calls[0][1]["headers"]["Api-Key"] == "secret"


def test_client_requires_both_credentials(monkeypatch):
    monkeypatch.setattr("ozon.client.OZON_CLIENT_ID", None)
    monkeypatch.setattr("ozon.client.OZON_API_KEY", None)
    with pytest.raises(OzonAuthError):
        OzonClient(client_id="", api_key="", base_url="https://example.test").post("/test")


@pytest.mark.parametrize("status,error", [(401, OzonAuthError), (403, OzonAuthError), (429, OzonRateLimitError)])
def test_client_maps_http_errors(status, error, monkeypatch):
    session = type("Session", (), {"post": lambda self, *args, **kwargs: StubResponse(status_code=status)})()
    monkeypatch.setattr("ozon.client.time.sleep", lambda value: None)
    with pytest.raises(error):
        OzonClient("client", "secret", session=session).post("/test", retries=1)


def test_client_retries_network_errors(monkeypatch):
    attempts = 0
    class Session:
        def post(self, *args, **kwargs):
            nonlocal attempts
            attempts += 1
            raise requests.ConnectionError("offline")
    monkeypatch.setattr("ozon.client.time.sleep", lambda value: None)
    with pytest.raises(OzonHTTPError):
        OzonClient("client", "secret", session=Session()).post("/test", retries=3)
    assert attempts == 3


def test_client_rejects_invalid_json():
    session = type("Session", (), {"post": lambda self, *args, **kwargs: StubResponse(payload=ValueError("bad"))})()
    with pytest.raises(OzonParseError):
        OzonClient("client", "secret", session=session).post("/test")
