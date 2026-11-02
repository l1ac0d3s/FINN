import pytest

from server.snapshot import financial_snapshot, trajectory


def q(period_end, period, revenue, pat):
    return {"period": period, "period_end": period_end, "revenue": revenue, "ebitda": revenue * 0.2,
            "pbt": None, "pat": pat, "source": "screener"}


SERIES = [
    q("2024-09-30", "Sep 2024", 100, 10), q("2024-12-31", "Dec 2024", 105, 10),
    q("2025-03-31", "Mar 2025", 110, 11), q("2025-06-30", "Jun 2025", 120, 12),
    q("2025-09-30", "Sep 2025", 130, 13), q("2025-12-31", "Dec 2025", 150, 16),
    q("2026-03-31", "Mar 2026", 165, 18), q("2026-06-30", "Jun 2026", 190, 22),
]


def test_snapshot_gives_latest_numbers_and_margins():
    f = financial_snapshot(SERIES)
    assert f["period"] == "Jun 2026"
    assert f["revenue"] == 190
    assert f["ebitda_margin_pct"] == 20.0
    assert f["pat_margin_pct"] == pytest.approx(11.6)


LONG = [q("2023-06-30", "Jun 2023", 60, 6), q("2023-09-30", "Sep 2023", 70, 7),
        q("2023-12-31", "Dec 2023", 75, 7), q("2024-03-31", "Mar 2024", 80, 8)] + SERIES


def test_trajectory_gives_year_on_year_growth_per_quarter():
    t = trajectory(LONG)
    assert t["points"][8]["revenue_yoy_pct"] == pytest.approx(30.0)   # Sep 2025 vs Sep 2024
    assert t["points"][0]["revenue_yoy_pct"] is None                  # no year-ago quarter
    assert t["direction"] == "accelerating"


def test_short_history_says_so():
    assert trajectory(SERIES[:3])["direction"] == "not enough history"
    assert financial_snapshot([]) is None
