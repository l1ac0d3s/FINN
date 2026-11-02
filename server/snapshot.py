"""Financial snapshot and trajectory, computed from the stored quarterly figures only."""

from statistics import mean

from server.results import growth_pct, year_ago


def margin_pct(part, whole):
    if part is None or not whole:
        return None
    return round(part / whole * 100, 1)


def financial_snapshot(quarters):
    """The latest quarter's headline numbers, with margins. None if there is no data."""
    if not quarters:
        return None
    q = quarters[-1]
    return {
        "period": q["period"],
        "unit": "Rs crore",
        "revenue": q.get("revenue"),
        "ebitda": q.get("ebitda"),
        "pat": q.get("pat"),
        "ebitda_margin_pct": margin_pct(q.get("ebitda"), q.get("revenue")),
        "pat_margin_pct": margin_pct(q.get("pat"), q.get("revenue")),
        "source": q.get("source"),
    }


def trajectory(quarters):
    """Year-on-year growth for every quarter, and whether growth is speeding up or slowing."""
    points = []
    for q in quarters:
        prior = year_ago(quarters, q)
        points.append({
            "period": q["period"],
            "revenue_yoy_pct": growth_pct(q.get("revenue"), prior.get("revenue") if prior else None),
            "pat_yoy_pct": growth_pct(q.get("pat"), prior.get("pat") if prior else None),
        })

    valid = [p["revenue_yoy_pct"] for p in points if p["revenue_yoy_pct"] is not None]
    recent, earlier = valid[-4:], valid[-8:-4]
    if len(recent) < 2 or len(earlier) < 2:
        direction = "not enough history"
    else:
        change = mean(recent) - mean(earlier)
        direction = "accelerating" if change > 2 else "slowing" if change < -2 else "steady"
    return {"points": points, "direction": direction}
