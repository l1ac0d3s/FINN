"""Push notifications to phones that have subscribed, for new high-priority filings.

Setup, once, on the laptop (see server/push_keys.py): create the keys, then set on Render:
    VAPID_PUBLIC_KEY   the public key (URL-safe base64)
    VAPID_PRIVATE_B64  the private key's PEM text, base64-encoded (one line, so it can be pasted)
    VAPID_SUBJECT      a mailto: address the push service may contact

Rules:
- Only filings published in the last 24 hours are sent. A first full sync can carry a week of filings, and
  a phone should not receive them all at once.
- Each filing is sent once, and recorded in push_sent.
- A subscription the push service reports as gone (404 or 410) is removed.
- If the keys are not set, nothing is sent. The app says so.
"""

import base64
import json
import os
from datetime import datetime, timedelta, timezone

PUBLIC = os.environ.get("VAPID_PUBLIC_KEY", "")
PRIVATE_B64 = os.environ.get("VAPID_PRIVATE_B64", "")
SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:finn@example.com")
RECENT = timedelta(hours=24)


def configured():
    return bool(PUBLIC and PRIVATE_B64)


def private_pem():
    return base64.b64decode(PRIVATE_B64).decode()


def save_subscription(conn, subscription):
    """Store a browser's push subscription. Returns False if it is malformed."""
    endpoint = subscription.get("endpoint")
    keys = subscription.get("keys") or {}
    if not endpoint or not keys.get("p256dh") or not keys.get("auth"):
        return False
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO push_subscriptions (endpoint, subscription_json, created_at) VALUES (?, ?, ?)",
            (endpoint, json.dumps(subscription), datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
    return True


def _raw_private_key(pem):
    """The 32-byte private key as URL-safe base64. This is the form pywebpush reads from a string;
    handing it PEM text fails with 'Could not deserialize key data'."""
    from cryptography.hazmat.primitives import serialization
    key = serialization.load_pem_private_key(pem.encode(), password=None)
    raw = key.private_numbers().private_value.to_bytes(32, "big")
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


LAST_ERROR = {"text": None}   # the most recent failure from the push service, for diagnosis


def _default_sender(subscription, payload, pem, subject):
    from pywebpush import WebPushException, webpush
    try:
        webpush(subscription_info=subscription, data=payload, vapid_private_key=_raw_private_key(pem),
                vapid_claims={"sub": subject})
        LAST_ERROR["text"] = None
        return "sent"
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        body = getattr(exc.response, "text", "") or ""
        LAST_ERROR["text"] = (f"{status} {body[:200]}").strip() or str(exc)[:200]
        return "gone" if status in (404, 410) else "failed"
    except Exception as exc:   # a broken key or a malformed subscription must not crash the request
        LAST_ERROR["text"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        return "failed"


def new_high_filings(rows, now=None):
    """High-priority filings from the last 24 hours, from the rows a sync just received."""
    now = now or datetime.now(timezone.utc)
    recent = []
    for row in rows:
        if row.get("tier") != "high" or not row.get("published_at"):
            continue
        try:
            published = datetime.fromisoformat(row["published_at"])
        except ValueError:
            continue
        if published.tzinfo is None:
            continue
        if now - published <= RECENT:
            recent.append(row)
    return recent


def notify_new(conn, rows, sender=None):
    """Send one notification per new high-priority filing to every subscriber. Returns (sent, removed)."""
    if not configured():
        return 0, 0
    sender = sender or _default_sender
    pem = private_pem()
    sent = removed = 0
    for row in new_high_filings(rows):
        if conn.execute("SELECT 1 FROM push_sent WHERE id = ?", (row["id"],)).fetchone():
            continue
        payload = json.dumps({
            "title": f"{row['ticker']}: {row.get('category', 'filing').replace('_', ' ')}",
            "body": row.get("subject", "")[:140],
            "url": "/",
        })
        for (raw,) in conn.execute("SELECT subscription_json FROM push_subscriptions").fetchall():
            result = sender(json.loads(raw), payload, pem, SUBJECT)
            if result == "sent":
                sent += 1
            elif result == "gone":
                with conn:
                    conn.execute("DELETE FROM push_subscriptions WHERE subscription_json = ?", (raw,))
                removed += 1
        with conn:
            conn.execute("INSERT OR REPLACE INTO push_sent (id, sent_at) VALUES (?, ?)",
                         (row["id"], datetime.now(timezone.utc).isoformat(timespec="seconds")))
    return sent, removed


def send_test(conn, sender=None):
    """Send one clearly labelled test notification to every subscribed phone. Returns (sent, removed)."""
    if not configured():
        return 0, 0
    sender = sender or _default_sender
    pem = private_pem()
    payload = json.dumps({"title": "FINN test", "body": "Notifications are working on this device.", "url": "/"})
    sent = removed = 0
    for (raw,) in conn.execute("SELECT subscription_json FROM push_subscriptions").fetchall():
        result = sender(json.loads(raw), payload, pem, SUBJECT)
        if result == "sent":
            sent += 1
        elif result == "gone":
            with conn:
                conn.execute("DELETE FROM push_subscriptions WHERE subscription_json = ?", (raw,))
            removed += 1
    return sent, removed


def subscriber_count(conn):
    """How many phones are subscribed."""
    return conn.execute("SELECT COUNT(*) FROM push_subscriptions").fetchone()[0]
