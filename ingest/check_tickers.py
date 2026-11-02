"""Check that every configured ticker resolves on Yahoo Finance and report its size.

Run on your machine before the first ingest:
    python -m ingest.check_tickers

Exit code 1 if any ticker returns no price data, so a typo is caught early.
Ad-hoc tickers are checked the same way, which is how the engine stays general.
"""

import sys
import warnings

from ingest.config import PORTFOLIO
from ingest.prices import fetch_eod
from ingest.run_daily import tickers

# yfinance triggers a pandas deprecation warning on every call. It is harmless here.
warnings.filterwarnings("ignore", message=".*inplace keyword.*")


def market_cap_crore(symbol):
    """Market cap in Rs crore, or None if Yahoo does not report it.

    Tries fast_info first, then the full info record, because either one can be
    empty depending on what Yahoo returns for the symbol.
    """
    import yfinance as yf

    for suffix in (".NS", ".BO"):
        ticker = yf.Ticker(symbol + suffix)
        lookups = (
            lambda: ticker.fast_info["market_cap"],
            lambda: ticker.info["marketCap"],
        )
        for lookup in lookups:
            try:
                cap = lookup()
            except Exception:
                continue
            if cap:
                return cap / 1e7
    return None


def main():
    missing = []
    print(f"{'ticker':<12}{'group':<11}{'bars':>5}{'last close':>12}{'mcap Rs cr':>14}")
    for ticker in tickers():
        bars = fetch_eod(ticker, days=10)
        group = "portfolio" if ticker in PORTFOLIO else "ad-hoc"
        if not bars:
            missing.append(ticker)
            print(f"{ticker:<12}{group:<11}{0:>5}{'-':>12}{'-':>14}")
            continue
        cap = market_cap_crore(ticker)
        cap_text = f"{cap:,.0f}" if cap else "n/a"
        print(f"{ticker:<12}{group:<11}{len(bars):>5}{bars[-1]['close']:>12,.1f}{cap_text:>14}")

    if missing:
        print(f"\nNo price data for: {', '.join(missing)}. Check the symbol on NSE.")
        sys.exit(1)
    print("\nAll tickers resolve.")


if __name__ == "__main__":
    main()
