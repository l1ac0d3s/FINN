"""The ticker queue: a lookup of an unknown ticker is saved, and the laptop collects and clears it."""

import importlib

import pytest

from ingest import requests as queue

fastapi_testclient = pytest.importorskip("fastapi.testclient")
HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FINN_SERVER_DB", str(tmp_path / "server.db"))
    monkeypatch.setenv("FINN_SYNC_TOKEN", "test-token")
    import server.app as app_module
    importlib.reload(app_module)
    return fastapi_testclient.TestClient(app_module.app)


def test_a_valid_symbol_is_queued_once(client):
    assert client.post("/api/request/zomato").json() == {"ok": True, "ticker": "ZOMATO", "status": "queued"}
    client.post("/api/request/ZOMATO")          # asking twice keeps one entry
    assert client.get("/api/requests", headers=HEADERS).json() == {"tickers": ["ZOMATO"]}


def test_an_invalid_symbol_is_refused(client):
    assert client.post("/api/request/bad;drop").status_code == 400


def test_the_queue_needs_the_token(client):
    client.post("/api/request/ZOMATO")
    assert client.get("/api/requests").status_code == 401
    assert client.post("/api/requests/clear", json={"tickers": ["ZOMATO"]}).status_code == 401


def test_clearing_removes_the_collected_tickers(client):
    client.post("/api/request/ZOMATO")
    client.post("/api/request/PAYTM")
    client.post("/api/requests/clear", json={"tickers": ["ZOMATO"]}, headers=HEADERS)
    assert client.get("/api/requests", headers=HEADERS).json() == {"tickers": ["PAYTM"]}


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class _Session:
    def __init__(self, payload=None, fail=False):
        self.payload, self.fail = payload, fail

    def get(self, *args, **kwargs):
        if self.fail:
            raise queue.requests.ConnectionError("server unreachable")
        return _Response(self.payload)


def test_the_laptop_collects_queued_tickers(monkeypatch):
    monkeypatch.setattr(queue.config, "SYNC_TOKEN", "t")
    assert queue.fetch_queued(_Session({"tickers": ["ZOMATO"]})) == ["ZOMATO"]


def test_an_unreachable_server_means_no_extra_tickers_not_a_failed_run(monkeypatch):
    monkeypatch.setattr(queue.config, "SYNC_TOKEN", "t")
    assert queue.fetch_queued(_Session(fail=True)) == []


def test_no_token_means_nothing_is_collected(monkeypatch):
    monkeypatch.setattr(queue.config, "SYNC_TOKEN", "")
    assert queue.fetch_queued(_Session({"tickers": ["ZOMATO"]})) == []
