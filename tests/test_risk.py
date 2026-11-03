import pytest

from server.risk import (
    achievement_pct, credit_model, grade, pct_change, profit_view, sensitivity, ttm_from_quarters, z_score,
)


def test_growth_divides_by_the_size_of_the_base():
    assert pct_change(-100, 50) == pytest.approx(150.0)    # loss narrowing to a profit: an improvement
    assert pct_change(-50, -100) == pytest.approx(-100.0)  # loss widening: a decline
    assert pct_change(100, 80) == pytest.approx(-20.0)
    assert pct_change(0, 5) is None
    assert pct_change(None, 5) is None


def test_promise_grid_bands():
    assert grade(achievement_pct(15, 15)) == "met"
    assert grade(achievement_pct(15, 16)) == "met"
    assert grade(achievement_pct(15, 14.95)) == "nearly met"   # 99.7% of target, not a miss
    assert grade(achievement_pct(15, 10)) == "partly met"      # 66.7%
    assert grade(achievement_pct(15, 7)) == "missed"           # 46.7%
    assert grade(90.0) == "nearly met"
    assert grade(89.99) == "partly met"
    assert grade(None) is None


def test_promised_decline_is_compared_with_its_sign():
    assert achievement_pct(-5, -6) == pytest.approx(120.0)
    assert achievement_pct(0, 5) is None


def test_z_matches_a_hand_calculation():
    # history mean 11.6, sample variance 5.2 / 4 = 1.3, standard deviation 1.1402
    z, flagged = z_score([10, 12, 11, 13, 12], 20, threshold=2.5, min_points=2)
    assert z == pytest.approx(7.37, abs=0.01)
    assert flagged
    z, flagged = z_score([10, 12, 11, 13, 12], 12, threshold=2.5, min_points=2)
    assert z == pytest.approx(0.35, abs=0.01)
    assert not flagged


def test_z_gives_no_alert_without_enough_history_or_spread():
    assert z_score([5, 5, 5, 5], 9, min_points=2) == (0.0, False)  # no spread
    assert z_score([1, 2, 3], 9) == (0.0, False)                   # fewer than 10 points by default


def test_profit_gap_is_flagged_and_blended_with_the_stated_weight():
    view = profit_view(ebitda_yoy=12.0, pbt_yoy=30.0, pbt=100, ebitda=80)
    assert view["gap_pts"] == 18.0
    assert view["blended_yoy_pct"] == pytest.approx(21.0)   # 0.5 x 12 + 0.5 x 30
    assert "moving apart" in view["note"]
    assert view["pbt_above_operating_profit_pct"] == pytest.approx(20.0)


def test_profit_moving_together_is_not_flagged():
    assert "together" in profit_view(10.0, 12.0)["note"]


def test_ttm_sums_the_last_four_and_the_four_before():
    quarters = [{"revenue": 100, "ebitda": 20, "pat": 10}] * 4 + [{"revenue": 120, "ebitda": 30, "pat": 12}] * 4
    assert ttm_from_quarters(quarters) == {"revenue": 480, "ebitda": 120, "pat": 48, "ebitda_prior": 80}


def test_ttm_needs_four_quarters():
    assert ttm_from_quarters([{"revenue": 1, "ebitda": 1, "pat": 1}] * 3) is None


STRONG = {"revenue": 1000, "ebitda": 300, "pat": 150, "ebitda_prior": 260}
STRESSED = {"revenue": 500, "ebitda": 20, "pat": -15, "ebitda_prior": 60}


def test_strong_company_scores_strong():
    out = credit_model(STRONG, debt=400, cash=100, interest=30)
    assert out["points"] == {"interest_cover": 3, "leverage": 2, "pat_margin": 3, "ebitda_trend": 3}
    assert out["score"] == pytest.approx(90.0)
    assert out["rating"] == "Strong"


def test_stressed_company_is_declined():
    out = credit_model(STRESSED, debt=400, cash=10, interest=35)
    assert out["score"] == 0
    assert out["rating"] == "Stressed"
    assert out["view"] == "Decline"


def test_no_interest_expense_earns_full_cover_points():
    assert credit_model(STRONG, debt=0, cash=0, interest=0)["points"]["interest_cover"] == 3


def test_sensitivity_grid_shape_and_direction():
    grid = sensitivity(STRONG, debt=400, cash=100, interest=30)
    assert len(grid["series"]) == 3
    assert all(len(s["scores"]) == len(grid["shocks_pct"]) for s in grid["series"])
    base = grid["series"][1]["scores"]                # debt as entered
    assert base[0] <= base[-1]                        # a larger EBITDA fall scores lower
    assert grid["series"][0]["scores"][-1] >= grid["series"][2]["scores"][-1]   # less debt scores higher
