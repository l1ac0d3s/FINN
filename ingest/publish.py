"""Send rows changed since the last sync to the server. Idempotent on the server side.

Rows go in batches so no single request is large. Each batch is one table's rows,
so a failed batch can be retried without resending the rest.
"""

from datetime import datetime, timezone

import requests

from ingest import config
from shared.schema import SYNCED, connect

EPOCH = "1970-01-01T00:00:00+00:00"
BATCH_ROWS = 500
TIMEOUT_S = 120


def get_state(conn, key, default=None):
    row = conn.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_state(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO sync_state (key, value) VALUES (?, ?)", (key, value))
    conn.commit()


def pending_rows(conn, since):
    """Rows changed since `since`, grouped by table."""
    pending = {}
    for table in SYNCED:
        rows = conn.execute(f"SELECT * FROM {table} WHERE updated_at > ?", (since,)).fetchall()
        pending[table] = [dict(r) for r in rows]
    return pending


def batches(rows, size=BATCH_ROWS):
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


def publish(conn=None, post=requests.post, full=False):
    """Send changed rows to the server. full=True sends everything, which fills an empty server."""
    if not config.SYNC_TOKEN:
        raise SystemExit("FINN_SYNC_TOKEN is not set")
    conn = conn or connect(config.INGEST_DB)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    since = EPOCH if full else get_state(conn, "last_sync", EPOCH)
    pending = pending_rows(conn, since)
    url = config.SERVER_URL.rstrip("/") + "/api/sync"
    headers = {"Authorization": f"Bearer {config.SYNC_TOKEN}"}

    sent = {}
    for table, rows in pending.items():
        for batch in batches(rows):
            resp = post(url, json={table: batch}, headers=headers, timeout=TIMEOUT_S)
            resp.raise_for_status()
            sent[table] = sent.get(table, 0) + len(batch)
    set_state(conn, "last_sync", started)
    print("synced:", sent or "nothing new")


if __name__ == "__main__":
    import sys

    publish(full="--full" in sys.argv)
