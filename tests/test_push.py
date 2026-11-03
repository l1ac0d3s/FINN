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
VALID_PUBLIC = "B" + "A" * 86   # the right shape for a browser key: 87 URL-safe characters


def filing(id_, tier="high", hours_ago=1, category="results"):
    return {"id": id_, "ticker": "INFY", "category": category, "tier": tier,
            "subject": "Outcome of Board Meeting", "published_at": (NOW - timedelta(hours=hours_ago)).isoformat()}


def subscription(name):
    return {"endpoint": f"https://push.example/{name}", "keys": {"p256dh": "k1", "auth": "a1"}}


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(push, "PUBLIC", VALID_PUBLIC)
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


def test_a_test_notification_goes_to_every_subscriber(conn):
    push.save_subscription(conn, subscription("phone1"))
    seen = []

    def sender(sub, payload, pem, subject):
        seen.append(json.loads(payload)["title"])
        return "sent"

    assert push.send_test(conn, sender=sender) == (1, 0)
    assert seen == ["FINN test"]


def test_a_test_notification_is_not_sent_without_keys(conn, monkeypatch):
    monkeypatch.setattr(push, "PUBLIC", "")
    assert push.send_test(conn, sender=lambda *a: "sent") == (0, 0)


def test_the_test_endpoint_needs_the_token(client):
    assert client.post("/api/push/test").status_code == 401
    body = client.post("/api/push/test", headers={"Authorization": "Bearer test-token"}).json()
    assert body["sent"] == 0 and body["removed"] == 0
    assert body["subscribers"] == 0
    assert body["configured"] is False          # no keys in the test environment


def test_the_default_sender_records_why_a_send_failed(monkeypatch):
    import types
    fake = types.SimpleNamespace()

    class FakeError(Exception):
        def __init__(self):
            self.response = types.SimpleNamespace(status_code=403, text="BadJwtToken")

    def failing_webpush(**kwargs):
        raise FakeError()

    fake.WebPushException = FakeError
    fake.webpush = failing_webpush
    monkeypatch.setitem(__import__("sys").modules, "pywebpush", fake)
    monkeypatch.setattr(push, "_raw_private_key", lambda pem: "raw-key")
    assert push._default_sender({"endpoint": "e"}, "{}", "pem", "mailto:x@y.z") == "failed"
    assert push.LAST_ERROR["text"].startswith("403 BadJwtToken")


def test_the_private_key_is_given_to_the_library_in_the_form_it_reads():
    pytest.importorskip("py_vapid")
    from py_vapid import Vapid
    from cryptography.hazmat.primitives import serialization
    from server.push_keys import make_keys

    public, private_b64 = make_keys()
    raw = push._raw_private_key(base64.b64decode(private_b64).decode())
    vapid = Vapid.from_string(private_key=raw)         # PEM text here raises "Could not deserialize key data"
    point = vapid.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    assert base64.urlsafe_b64encode(point).decode().rstrip("=") == public


def test_a_pasted_key_with_whitespace_is_cleaned_and_a_malformed_one_is_refused(monkeypatch):
    assert push._clean(" BAA\nBB \r\n") == "BAABB"
    monkeypatch.setattr(push, "PRIVATE_B64", "abc")
    monkeypatch.setattr(push, "PUBLIC", VALID_PUBLIC)
    assert push.configured() is True
    monkeypatch.setattr(push, "PUBLIC", VALID_PUBLIC + "\nVAPID_PRIVATE_B64=x")   # the mistake seen in practice
    assert push.configured() is False
