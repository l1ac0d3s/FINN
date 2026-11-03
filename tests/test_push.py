"""Push notifications: which filings are sent, once each, to whom, and what happens when a phone is gone.

The sender is a fake, so nothing is sent to a real push service here.
"""

import base64
import importlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from server import push
from shared.schema import connect

NOW = datetime.now(timezone.utc)


def filing(id_, tier="high", hours_ago=1, category="results"):
    return {"id": id_, "ticker": "INFY", "category": category, "tier": tier,
            "subject": "Outcome of Board Meeting", "published_at": (NOW - timedelta(hours=hours_ago)).isoformat()}


def subscription(name):
    return {"endpoint": f"https://push.example/{name}", "keys": {"p256dh": "k1", "auth": "a1"}}


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(push, "PUBLIC", "public-key")
    monkeypatch.setattr(push, "PRIVATE_B64", base64.b64encode(b"pem-text").decode())
    return connect(tmp_path / "server.db")


def test_only_recent_high_filings_are_sent():
    rows = [filing("a"), filing("b", tier="medium"), filing("c", hours_ago=30)]
    assert [r["id"] for r in push.new_high_filings(rows, now=NOW)] == ["a"]


def test_each_filing_goes_to_every_subscriber_once(conn):
    push.save_subscription(conn, subscription("phone1"))
    push.save_subscription(conn, subscription("phone2"))
    sent = []

    def sender(sub, payload, pem, subject):
        sent.append((sub["endpoint"], json.loads(payload)["title"]))
        return "sent"

    assert push.notify_new(conn, [filing("a")], sender=sender) == (2, 0)
    assert push.notify_new(conn, [filing("a")], sender=sender) == (0, 0)   # already sent
    assert len(sent) == 2
    assert sent[0][1] == "INFY: results"


def test_a_subscription_the_service_reports_gone_is_removed(conn):
    push.save_subscription(conn, subscription("old-phone"))
    assert push.notify_new(conn, [filing("a")], sender=lambda *a: "gone") == (0, 1)
    assert conn.execute("SELECT COUNT(*) FROM push_subscriptions").fetchone()[0] == 0


def test_nothing_is_sent_when_the_keys_are_not_set(conn, monkeypatch):
    monkeypatch.setattr(push, "PUBLIC", "")
    push.save_subscription(conn, subscription("phone1"))
    called = []
    assert push.notify_new(conn, [filing("a")], sender=lambda *a: called.append(a)) == (0, 0)
    assert called == []


def test_an_incomplete_subscription_is_refused(conn):
    assert push.save_subscription(conn, {"endpoint": "https://x"}) is False


def test_keys_have_the_expected_shape():
    pytest.importorskip("cryptography")
    from server.push_keys import make_keys
    public, private = make_keys()
    assert len(base64.urlsafe_b64decode(public + "==")) == 65   # an uncompressed P-256 point
    assert base64.b64decode(private).startswith(b"-----BEGIN PRIVATE KEY-----")


@pytest.fixture
def client(tmp_path, monkeypatch):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    monkeypatch.setenv("FINN_SERVER_DB", str(tmp_path / "server.db"))
    monkeypatch.setenv("FINN_SYNC_TOKEN", "test-token")
    import server.app as app_module
    importlib.reload(app_module)
    return fastapi_testclient.TestClient(app_module.app)


def test_without_keys_the_server_says_so(client, monkeypatch):
    monkeypatch.setattr(push, "PUBLIC", "")
    monkeypatch.setattr(push, "PRIVATE_B64", "")
    assert client.get("/api/push/key").json() == {"key": None}
    assert client.post("/api/push/subscribe", json=subscription("phone1")).status_code == 503
