"""Alerts computed on the server from synced prices and the user's saved thresholds.

Price alerts are judged against each stock's own recent behaviour. A move alerts when it is
an outlier (|z| at or above the saved threshold) against that stock's last 30 sessions, and it
is at least a minimum size. A fixed percentage treats a utility and a volatile small cap alike;
the z-score does not. Volume alerts compare with the 20-session median, as before.

Thresholds are stored on the server, so changing them in the app takes effect at once.
"""

from server.risk import Z_MIN_POINTS, z_score

Z_WINDOW = 30  # sessions of history each price move is judged against

DEFAULTS = {"volume_multiple": 2.0, "price_move_pct": 2.0, "z_threshold": 2.0}

ALL_CATEGORIES = [
    "results", "M&A", "fund_raise", "management_change", "litigation", "insider_trading",
    "earnings_call", "investor_meetings", "credit_rating", "dividend", "bonus_split", "capex",
    "press_release", "postal_ballot", "agm_egm", "pledging", "unclassified",
]
DEFAULT_ALERT_CATEGORIES = ["results", "M&A", "management_change", "litigation", "fund_raise", "pledging"]


def alert_categories(settings):
    """The announcement types that raise an alert. Defaults to the material types."""
    raw = settings.get("alert_categories")
    if raw is None:
        return set(DEFAULT_ALERT_CATEGORIES)
    return {c for c in raw.split(",") if c in ALL_CATEGORIES}


LIMITS = {
    "volume_multiple": (1.0, 10.0),
    "price_move_pct": (0.5, 20.0),   # minimum size of a move, so stable stocks don't alert on noise
    "z_threshold": (1.0, 4.0),       # how many standard deviations out a move must be
}


def thresholds(settings):
    """The saved thresholds, falling back to the defaults for anything missing."""
    return {key: float(settings.get(key, default)) for key, default in DEFAULTS.items()}


def valid_thresholds(values):
    """True if every threshold is a number inside its allowed range."""
    for key, (low, high) in LIMITS.items():
        if not low <= values[key] <= high:
            return False
    return True


def _volume_alert(ticker, bar, multiple):
    volume, baseline = bar["volume"], bar["vol_baseline"]
    if not (baseline and volume and volume / baseline >= multiple):
        return []
    return [{
        "id": f"{ticker}|{bar['date']}|volume_spike",
        "ticker": ticker,
        "date": bar["date"],
        "kind": "volume_spike",
        "detail": f"Volume {volume / baseline:.1f}x the 20-session median",
    }]


def _price_alert(ticker, date, move, history, limits):
    if move is None or abs(move) < limits["price_move_pct"]:
        return []
    z, flagged = z_score(history, move, threshold=limits["z_threshold"], min_points=Z_MIN_POINTS)
    if not flagged:
        return []
    return [{
        "id": f"{ticker}|{date}|price_move",
        "ticker": ticker,
        "date": date,
        "kind": "price_move",
        "detail": (f"Move {move:+.1f}% is {z:+.1f} standard deviations from its last "
                   f"{len(history)} sessions"),
    }]


def compute_alerts(price_rows, settings, since_date):
    """Alerts for trading days on or after `since_date`.

    price_rows: dicts with ticker, date, adj_close, volume and vol_baseline, oldest first
    within each ticker. Earlier bars are used only as history, so the first day in the window
    still has a full comparison.
    """
    limits = thresholds(settings)
    by_ticker = {}
    for row in price_rows:
        by_ticker.setdefault(row["ticker"], []).append(row)

    alerts = []
    for ticker, bars in by_ticker.items():
        moves = []  # every earlier daily % move for this ticker, oldest first
        for i, bar in enumerate(bars):
            previous = bars[i - 1] if i > 0 else None
            move = None
            if previous and previous["adj_close"] and bar["adj_close"]:
                move = (bar["adj_close"] / previous["adj_close"] - 1) * 100
            if bar["date"] >= since_date:
                alerts += _volume_alert(ticker, bar, limits["volume_multiple"])
                alerts += _price_alert(ticker, bar["date"], move, moves[-Z_WINDOW:], limits)
            if move is not None:
                moves.append(move)
    alerts.sort(key=lambda a: (a["date"], a["ticker"]), reverse=True)
    return alerts
