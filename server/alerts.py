"""Alerts computed on the server from synced prices and the user's saved thresholds.

Thresholds are stored on the server, so changing them in the app takes effect at once,
with no re-run of the laptop ingest. The price rules are the same pure functions the
ingest uses.
"""

from ingest.prices import unusual_moves

DEFAULTS = {"volume_multiple": 2.0, "price_move_pct": 5.0}

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


LIMITS = {"volume_multiple": (1.0, 10.0), "price_move_pct": (1.0, 20.0)}


def thresholds(settings):
    """The saved thresholds, falling back to the defaults for anything missing."""
    return {
        key: float(settings.get(key, default))
        for key, default in DEFAULTS.items()
    }


def valid_thresholds(values):
    """True if every threshold is a number inside its allowed range."""
    for key, (low, high) in LIMITS.items():
        if not low <= values[key] <= high:
            return False
    return True


def compute_alerts(price_rows, settings, since_date):
    """Alerts for trading days on or after `since_date`.

    price_rows: dicts with ticker, date, adj_close, volume and vol_baseline, oldest first
    within each ticker. The bar before the window is used only to measure the first move.
    """
    limits = thresholds(settings)
    by_ticker = {}
    for row in price_rows:
        by_ticker.setdefault(row["ticker"], []).append(row)

    alerts = []
    for ticker, bars in by_ticker.items():
        for i, bar in enumerate(bars):
            if bar["date"] < since_date:
                continue
            previous = bars[i - 1] if i > 0 else None
            alerts += unusual_moves(
                ticker, bar["date"], bar["volume"], bar["vol_baseline"],
                bar["adj_close"], previous["adj_close"] if previous else None,
                limits["volume_multiple"], limits["price_move_pct"],
            )
    alerts.sort(key=lambda a: (a["date"], a["ticker"]), reverse=True)
    return alerts
