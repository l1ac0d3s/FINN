"""End-to-end ingest on synthetic data: no network, real database.

The fetchers are replaced with fixtures, so this checks everything after the
download: storage, classification, tiering, and the alerts the user will see.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from ingest import config, run_daily
from shared.schema import connect


def fake_bars(_symbol, _days):
    """25 sessions at volume 100 and close 100, then a last session at volume 300 and +6%."""
    start = date(2026, 9, 1)
    bars = []
    for i in range(25):
        last = i == 24
        bars.append({
            "date": (start + timedelta(days=i)).isoformat(),
            "close": 106.0 if last else 100.0,
            "adj_close": 106.0 if last else 100.0,
            "volume": 300.0 if last else 100.0,
        })
    return bars


RECENT_UTC = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(second=0, microsecond=0)


def ist_text(utc_dt):
    """NSE publishes IST wall-clock time, so format the UTC instant as IST."""
    return (utc_dt + timedelta(hours=5, minutes=30)).strftime("%d-%b-%Y %H:%M:%S")


def fake_nse(_session, _symbol):
    return [
        {"desc": "Outcome of Board Meeting - approval of financial results",
         "an_dt": ist_text(RECENT_UTC), "seq_id": "101", "attchmntFile": "a.pdf"},
        {"desc": "Clarification on news article",
         "an_dt": ist_text(RECENT_UTC + timedelta(minutes=30)), "seq_id": "102", "attchmntFile": None},
        # Older than the window: must be skipped, not stored.
        {"desc": "Outcome of Board Meeting - approval of financial results",
         "an_dt": "10-Jan-2020 10:00:00", "seq_id": "099", "attchmntFile": None},
    ]


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INGEST_DB", tmp_path / "ingest.db")
    monkeypatch.setattr(config, "PORTFOLIO", ["INFY"])
    monkeypatch.setattr(config, "ADHOC", [])
    monkeypatch.setattr(run_daily, "fetch_eod", fake_bars)
    monkeypatch.setattr(run_daily, "fetch_nse", fake_nse)
    monkeypatch.setattr(run_daily, "store_screener", lambda conn, ticker, session: (0, 0))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return tmp_path / "ingest.db"


def test_run_stores_prices_alerts_and_tiered_announcements(isolated):
    run_daily.run(do_publish=False)
    conn = connect(isolated)

    assert conn.execute("SELECT COUNT(*) FROM prices_eod").fetchone()[0] == 25

    kinds = sorted(r["kind"] for r in conn.execute("SELECT kind FROM alerts WHERE ticker='INFY'"))
    assert kinds == ["price_move", "volume_spike"]

    stored = conn.execute("SELECT * FROM announcements").fetchall()
    assert len(stored) == 2, "the 2020 item must be skipped by the window"
    rows = {r["subject"]: dict(r) for r in stored}
    results = rows["Outcome of Board Meeting - approval of financial results"]
    news = rows["Clarification on news article"]
    assert (results["category"], results["tier"]) == ("results", "high")
    assert (news["category"], news["tier"]) == ("press_release", "low")
    # NSE gives IST; the stored value must be the same instant in UTC.
    assert results["published_at"] == RECENT_UTC.isoformat(timespec="seconds")


def test_empty_run_exits_nonzero_and_does_not_publish(isolated, monkeypatch):
    monkeypatch.setattr(run_daily, "fetch_eod", lambda s, d: [])

    def boom(_session, _symbol):
        raise ConnectionError("blocked")

    monkeypatch.setattr(run_daily, "fetch_nse", boom)
    published = []
    monkeypatch.setattr(run_daily, "publish", lambda conn: published.append(True))

    with pytest.raises(SystemExit):
        run_daily.run(do_publish=True)
    assert published == []
