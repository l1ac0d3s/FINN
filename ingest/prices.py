"""End-of-day prices from yfinance, with corporate-action-aware baselines.

Corporate actions (splits, bonus issues) change the share count and the raw
price without any real move. Two safeguards:
  - moves are measured on adjusted close, so a split is not a price move;
  - the volume baseline uses only prior sessions whose adjustment factor
    matches today's, so pre-split volumes on the old share count are dropped.
"""

from statistics import median

ADJ_TOLERANCE = 0.01  # factors within 1% are treated as the same adjustment basis


def daily_returns_pct(adj_closes):
    """Percent change between consecutive adjusted closes (oldest first)."""
    return [(b / a - 1) * 100 for a, b in zip(adj_closes, adj_closes[1:]) if a]


def volume_baseline(volumes, factors, window=20, min_sessions=5):
    """Median volume of up to `window` prior sessions on today's share basis.

    volumes and factors run oldest to newest, and the last item is today.
    factor = adj_close / close. Returns None when fewer than `min_sessions`
    comparable sessions exist, so no alert fires on thin data.
    """
    if len(volumes) < 2 or not factors[-1]:
        return None
    today_factor = factors[-1]
    prior = list(zip(volumes[:-1], factors[:-1]))[-window:]
    comparable = [v for v, f in prior if v and abs(f / today_factor - 1) <= ADJ_TOLERANCE]
    if len(comparable) < min_sessions:
        return None
    return median(comparable)


def unusual_moves(ticker, date, volume, vol_baseline, adj_close, prev_adj_close,
                  volume_multiple, price_move_pct):
    """Alert rows for one day, using the user's thresholds."""
    alerts = []
    if vol_baseline and volume and volume / vol_baseline >= volume_multiple:
        alerts.append({
            "id": f"{ticker}|{date}|volume_spike",
            "ticker": ticker,
            "date": date,
            "kind": "volume_spike",
            "detail": f"Volume {volume / vol_baseline:.1f}x the 20-session median",
        })
    if prev_adj_close and adj_close:
        move = (adj_close / prev_adj_close - 1) * 100
        if abs(move) >= price_move_pct:
            alerts.append({
                "id": f"{ticker}|{date}|price_move",
                "ticker": ticker,
                "date": date,
                "kind": "price_move",
                "detail": f"Adjusted close {move:+.1f}% on the day",
            })
    return alerts


def fetch_eod(symbol, days=60):
    """Daily bars for an NSE symbol, falling back to BSE. Returns oldest-first dicts.

    The yfinance column names ('Adj Close') are standard, but the exact
    behaviour of Ticker.history(auto_adjust=False) is unverified until it runs
    on the user's machine.
    """
    import yfinance as yf

    for suffix in (".NS", ".BO"):
        hist = yf.Ticker(symbol + suffix).history(period=f"{days}d", auto_adjust=False)
        if hist.empty:
            continue
        rows = []
        for idx, r in hist.iterrows():
            close = float(r["Close"])
            rows.append({
                "date": idx.date().isoformat(),
                "close": close,
                "adj_close": float(r.get("Adj Close", close)),
                "volume": float(r["Volume"]),
            })
        return rows
    return []


def with_baselines(rows):
    """Attach a volume baseline to each row (None where history is too thin)."""
    volumes = [r["volume"] for r in rows]
    factors = [r["adj_close"] / r["close"] if r["close"] else 0.0 for r in rows]
    for i, r in enumerate(rows):
        r["vol_baseline"] = volume_baseline(volumes[: i + 1], factors[: i + 1])
    return rows
