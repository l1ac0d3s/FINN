"""Ingest configuration. Edit here; nothing in this file is secret."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("FINN_DATA_DIR", ROOT / "data"))
INGEST_DB = DATA_DIR / "ingest.db"

# Portfolio: 18 NSE symbols, 14 large caps and 4 mid caps.
# Sectors: conglomerate, private banks, NBFC, IT (3), FMCG (2), pharma, auto,
# capital goods, telecom, metals, mining, electronics manufacturing, retail, apparel.
# Size is by my understanding of market capitalisation. check_tickers prints
# the live value, so confirm the mid-cap group there before the demo.
PORTFOLIO = [
    "RELIANCE",     # energy, retail and telecom conglomerate
    "HDFCBANK",     # private bank
    "ICICIBANK",    # private bank
    "BAJFINANCE",   # NBFC (lender)
    "INFY",         # IT services
    "TCS",          # IT services
    "PERSISTENT",   # IT products and services, mid cap
    "ITC",          # FMCG and cigarettes
    "HINDUNILVR",   # FMCG
    "SUNPHARMA",    # pharma
    "MARUTI",       # auto
    "LT",           # engineering and capital goods
    "BHARTIARTL",   # telecom
    "TATASTEEL",    # metals
    "COALINDIA",    # mining
    "DIXON",        # electronics manufacturing, mid cap
    "TRENT",        # retail, mid cap
    "PAGEIND",      # apparel, mid cap
]

# Ad-hoc research: outside the portfolio, to demo on-demand research.
# Chosen to contrast with the portfolio: a PSU bank against private banks,
# a defence PSU, a large FMCG name, and a conglomerate with many listed group companies.
ADHOC = [
    "SBIN",         # public-sector bank
    "HAL",          # defence PSU
    "NESTLEIND",    # large FMCG
    "ADANIENT",     # conglomerate with listed group companies
]

# Alert thresholds. The user owns these.
VOLUME_MULTIPLE = 2.0      # alert when volume >= this multiple of the 20-session median
PRICE_MOVE_PCT = 5.0       # alert when the adjusted close moves by at least this percent

PRICE_HISTORY_DAYS = 60
ANNOUNCEMENT_DAYS = 7      # NSE returns the full history per symbol; keep only this many days
REQUEST_DELAY_S = 2.0      # polite delay between requests to NSE and screener.in

HAIKU_MODEL = "claude-haiku-5-5"

SERVER_URL = os.environ.get("FINN_SERVER_URL", "http://localhost:8000")
SYNC_TOKEN = os.environ.get("FINN_SYNC_TOKEN", "")
