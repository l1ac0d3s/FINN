from datetime import datetime, timedelta, timezone

from server.digest import build_digest, market_reaction

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)


def row(hours_ago, tier, name="x"):
    ts = (NOW - timedelta(hours=hours_ago)).isoformat(timespec="seconds")
    return {"id": f"{name}-{hours_ago}", "ticker": "INFY", "published_at": ts,
            "subject": "s", "category": "c", "tier": tier}


def test_window_excludes_old_items():
    rows = [row(2, "high"), row(30, "high")]
    d = build_digest(rows, NOW, hours=24)
    assert len(d["high"]) == 1


def test_longer_window_includes_older_items():
    rows = [row(2, "high"), row(30, "high")]
    d = build_digest(rows, NOW, hours=24 * 7)
    assert len(d["high"]) == 2


def test_tiers_are_grouped_and_hidden_only_counted():
    rows = [row(1, "high"), row(2, "medium"), row(3, "low"), row(4, "hidden")]
    d = build_digest(rows, NOW, hours=24)
    assert [r["tier"] for r in d["high"]] == ["high"]
    assert [r["tier"] for r in d["medium"]] == ["medium"]
    assert [r["tier"] for r in d["routine"]] == ["low"]
    assert d["hidden_count"] == 1
    assert "hidden" not in d


BARS = [
    {"date": "2026-10-28", "adj_close": 100.0, "volume": 100.0, "vol_baseline": 100.0},
    {"date": "2026-10-29", "adj_close": 104.0, "volume": 300.0, "vol_baseline": 100.0},
    {"date": "2026-10-30", "adj_close": 101.0, "volume": 90.0, "vol_baseline": 100.0},
]


def test_filing_before_the_close_is_measured_on_the_same_session():
    r = market_reaction(BARS, "2026-10-29T05:00:00+00:00")  # 10:30 IST
    assert r == {"session": "2026-10-29", "move_pct": 4.0, "volume_x": 3.0, "after_close": False}


def test_filing_after_the_close_is_measured_on_the_next_session():
    r = market_reaction(BARS, "2026-10-29T11:30:00+00:00")  # 17:00 IST
    assert r["session"] == "2026-10-30"
    assert r["move_pct"] == -2.9
    assert r["after_close"] is True


def test_no_bar_for_the_session_gives_no_reaction():
    assert market_reaction([], "2026-10-29T05:00:00+00:00") is None


def test_digest_attaches_reaction_when_prices_are_given():
    rows = [{"id": "p", "ticker": "TRENT", "published_at": "2026-10-29T05:00:00+00:00",
             "subject": "Appointment", "attachment_url": None, "tier": "high"}]
    d = build_digest(rows, datetime(2026, 10, 30, tzinfo=timezone.utc), hours=168, prices={"TRENT": BARS})
    assert d["high"][0]["reaction"]["move_pct"] == 4.0


def test_same_filing_under_several_subjects_is_one_card():
    filing = "https://www.nseindia.com/corporate/TRENT-board-outcome.pdf"
    rows = [
        {"id": "a", "ticker": "TRENT", "published_at": (NOW - timedelta(hours=2)).isoformat(),
         "subject": "Retirement", "attachment_url": filing, "tier": "high"},
        {"id": "b", "ticker": "TRENT", "published_at": (NOW - timedelta(hours=2)).isoformat(),
         "subject": "Appointment", "attachment_url": filing, "tier": "high"},
        {"id": "c", "ticker": "TRENT", "published_at": (NOW - timedelta(hours=2)).isoformat(),
         "subject": "Appointment", "attachment_url": filing, "tier": "high"},
    ]
    d = build_digest(rows, NOW, hours=24)
    assert len(d["high"]) == 1
    assert d["high"][0]["subject"] == "Retirement · Appointment"


def test_filings_at_different_times_are_not_merged():
    rows = [
        {"id": "x", "ticker": "INFY", "published_at": (NOW - timedelta(hours=1)).isoformat(),
         "subject": "Clarification", "category": "press_release", "tier": "low"},
        {"id": "y", "ticker": "INFY", "published_at": (NOW - timedelta(hours=2)).isoformat(),
         "subject": "Clarification", "category": "press_release", "tier": "low"},
    ]
    assert len(build_digest(rows, NOW, hours=24)["routine"]) == 2


def test_newest_first_within_a_tier():
    rows = [row(5, "high", "old"), row(1, "high", "new")]
    d = build_digest(rows, NOW, hours=24)
    assert [r["id"] for r in d["high"]] == ["new-1", "old-5"]
