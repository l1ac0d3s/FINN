"""Results card: latest quarter's headline figures with QoQ and YoY change.

Pure functions. Input is the quarterly series, oldest first, as stored in financials_q.
"""

from server.risk import pct_change, profit_view

METRICS = ["revenue", "ebitda", "pbt", "pat"]


def growth_pct(current, previous):
    """Percent change from previous to current, divided by |previous| so a negative base reads correctly.
    None when either value is missing or the base is zero."""
    return pct_change(previous, current)


def year_ago(quarters, latest):
    """The quarter with the same month one year earlier, if it is in the series."""
    target = (latest["period_end"][:4], latest["period_end"][5:7])
    for q in quarters:
        if q["period_end"][5:7] == target[1] and int(q["period_end"][:4]) == int(target[0]) - 1:
            return q
    return None


def build_results_card(quarters):
    """Latest quarter with QoQ and YoY for each metric, or None if no data."""
    if not quarters:
        return None
    latest = quarters[-1]
    prev = quarters[-2] if len(quarters) >= 2 else None
    ya = year_ago(quarters, latest)

    metrics = {}
    for m in METRICS:
        metrics[m] = {
            "value": latest.get(m),
            "qoq_pct": growth_pct(latest.get(m), prev.get(m) if prev else None),
            "yoy_pct": growth_pct(latest.get(m), ya.get(m) if ya else None),
        }
    return {
        "period": latest["period"],
        "period_end": latest["period_end"],
        "unit": "Rs crore",
        "source": latest.get("source"),
        "metrics": metrics,
        "has_yoy": ya is not None,
        "profit_view": profit_view(
            metrics["ebitda"]["yoy_pct"], metrics["pbt"]["yoy_pct"],
            pbt=latest.get("pbt"), ebitda=latest.get("ebitda"),
        ),
    }
