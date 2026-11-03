from datetime import date, timedelta

from server.alerts import DEFAULTS, compute_alerts, thresholds, valid_thresholds


def bars(ticker, moves, volume=100.0, baseline=100.0, start="2026-09-01"):
    """Daily bars whose adjusted close moves by the given percentages, oldest first."""
    price, day, rows = 100.0, date.fromisoformat(start), []
    for i, move in enumerate(moves):
        price *= 1 + move / 100
        rows.append({"ticker": ticker, "date": (day + timedelta(days=i)).isoformat(),
                     "adj_close": price, "volume": volume, "vol_baseline": baseline})
    return rows


def price_alerts(alerts):
    return [a for a in alerts if a["kind"] == "price_move"]


def test_defaults_and_saved_values():
    assert DEFAULTS == {"volume_multiple": 2.0, "price_move_pct": 2.0, "z_threshold": 2.0}
    assert thresholds({}) == {"volume_multiple": 2.0, "price_move_pct": 2.0, "z_threshold": 2.0}
    assert thresholds({"z_threshold": "3"})["z_threshold"] == 3.0


def test_stable_stock_alerts_on_a_move_that_is_large_for_it():
    rows = bars("UTILITY", [0.1, -0.1] * 8 + [3.0])
    alerts = price_alerts(compute_alerts(rows, {}, rows[-1]["date"]))
    assert len(alerts) == 1
    assert "standard deviations" in alerts[0]["detail"]


def test_volatile_stock_does_not_alert_on_a_move_that_is_normal_for_it():
    rows = bars("SMALLCAP", [4.0, -4.0] * 8 + [6.0])  # z is about 1.5, below 2
    assert price_alerts(compute_alerts(rows, {}, rows[-1]["date"])) == []


def test_minimum_move_stops_tiny_outliers_on_very_stable_stocks():
    rows = bars("STEADY", [0.01, -0.01] * 8 + [0.3])  # a huge z, but only a 0.3% move
    assert price_alerts(compute_alerts(rows, {}, rows[-1]["date"])) == []


def test_too_little_history_gives_no_price_alert():
    rows = bars("NEWLISTING", [3.0])
    assert price_alerts(compute_alerts(rows, {}, rows[-1]["date"])) == []


def test_raising_the_z_threshold_removes_the_alert():
    rows = bars("UTILITY", [0.1, -0.1] * 8 + [3.0])
    strict = compute_alerts(rows, {"z_threshold": "1000"}, rows[-1]["date"])
    assert price_alerts(strict) == []


def test_volume_spike_uses_the_median_baseline():
    rows = bars("INFY", [0.0], volume=300.0, baseline=100.0)
    assert [a["kind"] for a in compute_alerts(rows, {}, rows[-1]["date"])] == ["volume_spike"]


def test_window_start_excludes_older_days_but_keeps_them_as_history():
    rows = bars("UTILITY", [0.1, -0.1] * 8 + [3.0, 0.1, 0.1])
    alerts = compute_alerts(rows, {}, rows[-3]["date"])
    assert all(a["date"] >= rows[-3]["date"] for a in alerts)


def test_out_of_range_thresholds_are_rejected():
    assert valid_thresholds({"volume_multiple": 2.0, "price_move_pct": 2.0, "z_threshold": 2.0})
    assert not valid_thresholds({"volume_multiple": 0.5, "price_move_pct": 2.0, "z_threshold": 2.0})
    assert not valid_thresholds({"volume_multiple": 2.0, "price_move_pct": 2.0, "z_threshold": 9.0})
