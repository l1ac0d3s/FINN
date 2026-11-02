import pytest

from server.results import build_results_card, growth_pct


def q(period_end, period, revenue, pat=None):
    return {"period": period, "period_end": period_end, "revenue": revenue,
            "ebitda": None, "pbt": None, "pat": pat, "source": "screener"}


SERIES = [
    q("2024-09-30", "Sep 2024", 1000, pat=110),
    q("2024-12-31", "Dec 2024", 1100, pat=118),
    q("2025-03-31", "Mar 2025", 1050, pat=104),
    q("2025-06-30", "Jun 2025", 1200, pat=125),
    q("2025-09-30", "Sep 2025", 1320, pat=None),
]


def test_growth_handles_missing_and_zero_base():
    assert growth_pct(110, 100) == pytest.approx(10.0)
    assert growth_pct(None, 100) is None
    assert growth_pct(100, 0) is None


def test_card_uses_latest_quarter_with_qoq_and_yoy():
    card = build_results_card(SERIES)
    revenue = card["metrics"]["revenue"]
    assert card["period"] == "Sep 2025"
    assert revenue["value"] == 1320
    assert revenue["qoq_pct"] == pytest.approx((1320 / 1200 - 1) * 100)
    assert revenue["yoy_pct"] == pytest.approx((1320 / 1000 - 1) * 100)
    assert card["has_yoy"] is True


def test_missing_latest_value_is_reported_as_none():
    assert build_results_card(SERIES)["metrics"]["pat"]["value"] is None


def test_no_year_ago_quarter_is_flagged():
    card = build_results_card(SERIES[1:])  # the year-ago quarter is gone
    assert card["has_yoy"] is False
    assert card["metrics"]["revenue"]["yoy_pct"] is None


def test_empty_series_returns_none():
    assert build_results_card([]) is None
