"""SQLite schema shared by the ingest job (laptop) and the server (Render).

Only SYNCED tables travel from the laptop to the server. Everything else
stays local to the ingest job.
"""

import sqlite3
from pathlib import Path

DDL = """
CREATE TABLE IF NOT EXISTS companies (
    ticker        TEXT PRIMARY KEY,           -- NSE symbol, e.g. RELIANCE
    name          TEXT,
    in_portfolio  INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prices_eod (
    id            TEXT PRIMARY KEY,           -- ticker|YYYY-MM-DD
    ticker        TEXT NOT NULL,
    date          TEXT NOT NULL,
    close         REAL,
    adj_close     REAL,
    volume        REAL,
    vol_baseline  REAL,                       -- median of prior comparable sessions
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prices_ticker_date ON prices_eod (ticker, date);

CREATE TABLE IF NOT EXISTS announcements (
    id              TEXT PRIMARY KEY,
    ticker          TEXT NOT NULL,
    published_at    TEXT NOT NULL,            -- ISO 8601, UTC
    subject         TEXT NOT NULL,
    attachment_url  TEXT,
    xbrl_url        TEXT,                     -- structured results file, when the exchange gives one
    category        TEXT NOT NULL,
    tier            TEXT NOT NULL,            -- high | medium | low | hidden
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ann_published ON announcements (published_at);

CREATE TABLE IF NOT EXISTS alerts (
    id          TEXT PRIMARY KEY,
    ticker      TEXT NOT NULL,
    date        TEXT NOT NULL,
    kind        TEXT NOT NULL,                -- volume_spike | price_move
    detail      TEXT,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS financials_q (
    id          TEXT PRIMARY KEY,             -- ticker|period_end
    ticker      TEXT NOT NULL,
    period      TEXT NOT NULL,                -- as shown by screener, e.g. 'Sep 2025'
    period_end  TEXT NOT NULL,                -- ISO date, used for ordering and YoY
    revenue     REAL,
    ebitda      REAL,
    pbt         REAL,
    pat         REAL,
    source      TEXT NOT NULL,                -- 'screener' or 'filing'
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fin_ticker ON financials_q (ticker, period_end);

CREATE TABLE IF NOT EXISTS documents (
    id          TEXT PRIMARY KEY,             -- sha1 of the URL
    ticker      TEXT NOT NULL,
    doc_type    TEXT NOT NULL,                -- annual_report | transcript | investor_presentation
    period      TEXT,
    url         TEXT NOT NULL,
    label       TEXT,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id           TEXT PRIMARY KEY,            -- document_id|page|index
    document_id  TEXT NOT NULL,
    ticker       TEXT NOT NULL,
    doc_type     TEXT NOT NULL,
    page         INTEGER NOT NULL,
    text         TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_ticker ON chunks (ticker, doc_type);

-- Management-change filings, with the profile read from the filing itself.
CREATE TABLE IF NOT EXISTS management_bios (
    id            TEXT PRIMARY KEY,           -- the announcement id
    ticker        TEXT NOT NULL,
    name          TEXT,
    role          TEXT,
    bio           TEXT,                       -- NULL when the filing has no profile
    source_url    TEXT,
    origin        TEXT NOT NULL DEFAULT 'filing',   -- 'filing' or 'manual' (entered by hand, with a source)
    published_at  TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

-- Yearly balance sheet and operating cash flow, from screener.in's company page.
CREATE TABLE IF NOT EXISTS annual_figures (
    id            TEXT PRIMARY KEY,           -- ticker|year
    ticker        TEXT NOT NULL,
    year          TEXT NOT NULL,              -- the financial year that ends in March, e.g. '2025'
    net_worth     REAL,
    borrowings    REAL,
    total_assets  REAL,
    cfo           REAL,                       -- cash from operating activity
    pat           REAL,                       -- net profit
    updated_at    TEXT NOT NULL
);

-- Plain-English notes on promise verdicts, written on the laptop by a small model.
CREATE TABLE IF NOT EXISTS claim_notes (
    id          TEXT PRIMARY KEY,           -- claim id from server/pull.py
    ticker      TEXT NOT NULL,
    text        TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- Server only: phones that asked for notifications, and the filings already sent.
CREATE TABLE IF NOT EXISTS push_subscriptions (
    endpoint          TEXT PRIMARY KEY,
    subscription_json TEXT NOT NULL,
    created_at        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS push_sent (
    id       TEXT PRIMARY KEY,
    sent_at  TEXT NOT NULL
);

-- Server only: tickers looked up in the app that have no data yet. The laptop collects and clears them.
CREATE TABLE IF NOT EXISTS ticker_requests (
    ticker        TEXT PRIMARY KEY,
    requested_at  TEXT NOT NULL
);

-- Server only: user settings, such as alert thresholds.
CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

-- Server only: cached pull outputs, keyed by ticker and source chunks.
CREATE TABLE IF NOT EXISTS pull_cache (
    key          TEXT PRIMARY KEY,
    output_json  TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

-- Ingest only.
CREATE TABLE IF NOT EXISTS classify_cache (
    subject_hash  TEXT PRIMARY KEY,
    category      TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

-- Ingest only.
CREATE TABLE IF NOT EXISTS sync_state (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
"""

PRIMARY_KEY = {
    "companies": "ticker",
    "prices_eod": "id",
    "announcements": "id",
    "alerts": "id",
    "financials_q": "id",
    "documents": "id",
    "chunks": "id",
    "classify_cache": "subject_hash",
    "management_bios": "id",
    "claim_notes": "id",
    "annual_figures": "id",
}

SYNCED = ["companies", "prices_eod", "announcements", "alerts", "financials_q", "documents", "chunks",
          "management_bios", "claim_notes", "annual_figures"]

COLUMNS = {
    "companies": ["ticker", "name", "in_portfolio", "updated_at"],
    "prices_eod": ["id", "ticker", "date", "close", "adj_close", "volume", "vol_baseline", "updated_at"],
    "announcements": ["id", "ticker", "published_at", "subject", "attachment_url", "xbrl_url", "category", "tier", "updated_at"],
    "alerts": ["id", "ticker", "date", "kind", "detail", "updated_at"],
    "financials_q": ["id", "ticker", "period", "period_end", "revenue", "ebitda", "pbt", "pat", "source", "updated_at"],
    "documents": ["id", "ticker", "doc_type", "period", "url", "label", "updated_at"],
    "chunks": ["id", "document_id", "ticker", "doc_type", "page", "text", "updated_at"],
    "management_bios": ["id", "ticker", "name", "role", "bio", "source_url", "origin", "published_at", "updated_at"],
    "claim_notes": ["id", "ticker", "text", "updated_at"],
    "annual_figures": ["id", "ticker", "year", "net_worth", "borrowings", "total_assets", "cfo", "pat", "updated_at"],
}


def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(DDL)
    _migrate(conn)
    return conn


def _migrate(conn):
    """Add columns that were introduced after a database was first created. CREATE TABLE IF NOT EXISTS
    does not add columns to an existing table, so this is needed for older files."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(announcements)").fetchall()}
    if "xbrl_url" not in columns:
        conn.execute("ALTER TABLE announcements ADD COLUMN xbrl_url TEXT")
        conn.commit()
    bios = {row["name"] for row in conn.execute("PRAGMA table_info(management_bios)").fetchall()}
    if "origin" not in bios:
        conn.execute("ALTER TABLE management_bios ADD COLUMN origin TEXT NOT NULL DEFAULT 'filing'")
        conn.commit()


def upsert(conn, table, row):
    """Insert or update one row. An incoming row only replaces a stored one
    if its updated_at is at least as new, so re-syncing is safe."""
    if table not in COLUMNS:
        raise ValueError(f"table not syncable: {table}")
    cols = [c for c in COLUMNS[table] if c in row]
    pk = PRIMARY_KEY[table]
    updates = ", ".join(f"{c} = excluded.{c}" for c in cols if c != pk)
    sql = (
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
        f"ON CONFLICT({pk}) DO UPDATE SET {updates} "
        f"WHERE excluded.updated_at >= {table}.updated_at"
    )
    conn.execute(sql, [row[c] for c in cols])
