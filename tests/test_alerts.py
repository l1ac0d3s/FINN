from server.alerts import DEFAULTS, compute_alerts, thresholds, valid_thresholds

BARS = [
    {"ticker": "TRENT", "date": "2026-10-28", "adj_close": 100.0, "volume": 100.0, "vol_baseline": 100.0},
    {"ticker": "TRENT", "date": "2026-10-29", "adj_close": 106.0, "volume": 300.0, "vol_baseline": 100.0},
    {"ticker": "INFY", "date": "2026-10-29", "adj_close": 101.0, "volume": 110.0, "vol_baseline": 100.0},
]


def test_default_thresholds_when_nothing_is_saved():
    assert thresholds({}) == {"volume_multiple": 2.0, "price_move_pct": 5.0}


def test_saved_threshold_changes_which_alerts_fire():
    loose = compute_alerts(BARS, {"volume_multiple": "2", "price_move_pct": "5"}, "2026-10-29")
    strict = compute_alerts(BARS, {"volume_multiple": "4", "price_move_pct": "10"}, "2026-10-29")
    assert {a["kind"] for a in loose} == {"volume_spike", "price_move"}
    assert strict == []


def test_window_start_excludes_older_days_but_uses_them_for_the_first_move():
    alerts = compute_alerts(BARS, {}, "2026-10-29")
    assert all(a["date"] == "2026-10-29" for a in alerts)
    assert any(a["kind"] == "price_move" for a in alerts)  # 100 -> 106 on the 29th


def test_out_of_range_thresholds_are_rejected():
    assert valid_thresholds({"volume_multiple": 2.0, "price_move_pct": 5.0})
    assert not valid_thresholds({"volume_multiple": 0.5, "price_move_pct": 5.0})
    assert not valid_thresholds({"volume_multiple": 2.0, "price_move_pct": 50.0})


def test_defaults_match_the_brief_examples():
    assert DEFAULTS == {"volume_multiple": 2.0, "price_move_pct": 5.0}
