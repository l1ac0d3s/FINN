"""Digest assembly: window filter, tier grouping, and the Routine collapse.

Pure functions only, so they can be tested without a database or network.
"""

from datetime import datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
MARKET_CLOSE = time(15, 30)


def parse_ts(value):
    """Parse an ISO 8601 timestamp. Timestamps must carry a timezone."""
    ts = datetime.fromisoformat(value)
    if ts.tzinfo is None:
        raise ValueError(f"timestamp has no timezone: {value!r}")
    return ts


def market_reaction(bars, published_at):
    """How the stock moved after a filing.

    bars: daily dicts with date, adj_close, volume and vol_baseline, oldest first.
    A filing made after the close (15:30 IST) is measured from the next session.
    Returns None when there is no bar for that session yet.
    """
    ts = parse_ts(published_at).astimezone(IST)
    after_close = ts.time() >= MARKET_CLOSE
    session = (ts.date() + timedelta(days=1)) if after_close else ts.date()
    for i, bar in enumerate(bars):
        if bar["date"] < session.isoformat():
            continue
        previous = bars[i - 1] if i > 0 else None
        if not previous or not previous["adj_close"] or not bar["adj_close"]:
            return None
        move = (bar["adj_close"] / previous["adj_close"] - 1) * 100
        volume_x = None
        if bar.get("vol_baseline") and bar.get("volume"):
            volume_x = round(bar["volume"] / bar["vol_baseline"], 1)
        return {
            "session": bar["date"],
            "move_pct": round(move, 1),
            "volume_x": volume_x,
            "after_close": after_close,
        }
    return None


def collapse_same_filing(rows):
    """One row per filing. Rows from the same company, at the same time, in the same category
    are one filing.

    The exchange lists one filing under several subject lines (for example a board
    outcome that covers a retirement and two appointments), often with different
    attachment links. The subjects are joined into one line.
    """
    merged, by_filing = [], {}
    for r in rows:
        key = (r["ticker"], r["published_at"], r.get("category"))
        if key not in by_filing:
            by_filing[key] = {**r, "subjects": [r["subject"]]}
            merged.append(by_filing[key])
            continue
        row = by_filing[key]
        if r["subject"] not in row["subjects"]:
            row["subjects"].append(r["subject"])
        if r["published_at"] > row["published_at"]:
            row["published_at"] = r["published_at"]
    for row in merged:
        row["subject"] = " · ".join(row.pop("subjects"))
    return merged


def build_digest(rows, now, hours, prices=None):
    """Group announcements in the window by tier.

    rows: dicts with published_at, tier, and display fields.
    prices: optional dict of ticker -> daily bars, used to add each filing's market reaction.
    high and medium are shown in full. low is collapsed under Routine.
    hidden is only counted, never listed.
    """
    cutoff = now - timedelta(hours=hours)
    in_window = [r for r in rows if parse_ts(r["published_at"]) >= cutoff]
    in_window = collapse_same_filing(in_window)
    if prices is not None:
        for r in in_window:
            r["reaction"] = market_reaction(prices.get(r["ticker"], []), r["published_at"])
    in_window.sort(key=lambda r: r["published_at"], reverse=True)

    groups = {"high": [], "medium": [], "low": [], "hidden": []}
    for r in in_window:
        groups.get(r["tier"], groups["low"]).append(r)

    return {
        "window_hours": hours,
        "generated_at": now.isoformat(timespec="seconds"),
        "high": groups["high"],
        "medium": groups["medium"],
        "routine": groups["low"],
        "hidden_count": len(groups["hidden"]),
        "counts": {k: len(v) for k, v in groups.items()},
    }
