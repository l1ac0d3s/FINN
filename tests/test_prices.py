import pytest

from ingest.prices import daily_returns_pct, unusual_moves, volume_baseline, with_baselines


def test_returns_use_adjusted_closes():
    assert daily_returns_pct([100, 110, 99]) == pytest.approx([10.0, -10.0])


def test_baseline_is_median_of_prior_sessions():
    volumes = [100, 200, 300, 400, 500, 600]
    factors = [1.0] * 6
    assert volume_baseline(volumes, factors) == 300  # median of 100..500


def test_split_sessions_are_excluded_from_baseline():
    # Five pre-split sessions at factor 0.5, then today at factor 1.0.
    volumes = [1000, 1000, 1000, 1000, 1000, 300]
    factors = [0.5, 0.5, 0.5, 0.5, 0.5, 1.0]
    assert volume_baseline(volumes, factors) is None


def test_thin_history_gives_no_baseline():
    assert volume_baseline([100, 200, 300], [1.0, 1.0, 1.0]) is None


def test_volume_spike_alert():
    alerts = unusual_moves("INFY", "2026-10-29", volume=300, vol_baseline=100,
                           adj_close=100, prev_adj_close=100,
                           volume_multiple=2.0, price_move_pct=5.0)
    assert [a["kind"] for a in alerts] == ["volume_spike"]


def test_price_move_alert_both_directions():
    down = unusual_moves("INFY", "2026-10-29", 0, None, 94, 100, 2.0, 5.0)
    up = unusual_moves("INFY", "2026-10-29", 0, None, 106, 100, 2.0, 5.0)
    assert [a["kind"] for a in down] == ["price_move"]
    assert [a["kind"] for a in up] == ["price_move"]


def test_no_alert_on_ordinary_day():
    assert unusual_moves("INFY", "2026-10-29", 120, 100, 101, 100, 2.0, 5.0) == []


def test_with_baselines_attaches_none_when_history_thin():
    rows = [{"date": f"2026-10-{i:02d}", "close": 100.0, "adj_close": 100.0, "volume": 100.0}
            for i in range(1, 4)]
    out = with_baselines(rows)
    assert all(r["vol_baseline"] is None for r in out)
