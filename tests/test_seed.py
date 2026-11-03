from datetime import datetime, timedelta, timezone

from ingest.make_seed import build
from server.app import ensure_seeded
from shared.schema import connect, upsert

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
STAMP = "2026-10-31T12:00:00+00:00"


def make_source(path):
    conn = connect(path)
    upsert(conn, "companies", {"ticker": "INFY", "name": "INFY", "in_portfolio": 1, "updated_at": STAMP})
    old_day = (NOW - timedelta(days=60)).date().isoformat()
    new_day = (NOW - timedelta(days=1)).date().isoformat()
    for day in (old_day, new_day):
        upsert(conn, "prices_eod", {"id": f"INFY|{day}", "ticker": "INFY", "date": day, "close": 1.0,
                                    "adj_close": 1.0, "volume": 1.0, "vol_baseline": 1.0, "updated_at": STAMP})
    upsert(conn, "announcements", {"id": "old", "ticker": "INFY",
                                   "published_at": (NOW - timedelta(days=30)).isoformat(timespec="seconds"),
                                   "subject": "old", "attachment_url": None, "category": "press_release",
                                   "tier": "low", "updated_at": STAMP})
    upsert(conn, "announcements", {"id": "new", "ticker": "INFY",
                                   "published_at": (NOW - timedelta(hours=2)).isoformat(timespec="seconds"),
                                   "subject": "new", "attachment_url": None, "category": "results",
                                   "tier": "high", "updated_at": STAMP})
    conn.execute("INSERT INTO chunks (id, document_id, ticker, doc_type, page, text, updated_at) "
                 "VALUES ('c', 'd', 'INFY', 'transcript', 1, 'long text', ?)", (STAMP,))
    conn.commit()
    conn.close()


def test_seed_keeps_recent_rows_and_carries_the_transcripts(tmp_path):
    source, target = tmp_path / "ingest.db", tmp_path / "seed.sqlite"
    make_source(source)
    counts = build(source, target, now=NOW)

    assert counts["announcements"] == 1          # only the 2-hour-old filing
    assert counts["prices_eod"] == 1             # only yesterday's bar
    conn = connect(target)
    assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 1   # transcripts travel with the seed
    conn.close()


def test_empty_disk_starts_from_the_seed_and_existing_data_is_kept(tmp_path):
    source, seed = tmp_path / "ingest.db", tmp_path / "seed.sqlite"
    make_source(source)
    build(source, seed, now=NOW)

    fresh = tmp_path / "disk" / "server.db"
    ensure_seeded(fresh, seed)
    assert fresh.exists()
    assert connect(fresh).execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 1

    fresh.write_bytes(b"")  # simulate an existing database: it must not be overwritten
    ensure_seeded(fresh, seed)
    assert fresh.read_bytes() == b""


def test_transcripts_and_notes_are_kept_when_the_next_run_has_none(tmp_path):
    """The nightly job skips transcripts, so a rebuilt seed must not lose the ones it already had."""
    source, seed = tmp_path / "ingest.db", tmp_path / "seed.sqlite"
    make_source(source)
    build(source, seed, now=NOW)                      # a seed that has the transcript chunk

    empty_source = tmp_path / "nightly.db"
    conn = connect(empty_source)
    upsert(conn, "companies", {"ticker": "INFY", "name": "INFY", "in_portfolio": 1, "updated_at": STAMP})
    conn.commit()
    conn.close()
    counts = build(empty_source, seed, now=NOW)       # a run with no transcripts

    assert counts["chunks"] == 1
    kept = connect(seed)
    assert kept.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 1
    kept.close()
