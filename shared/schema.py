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
}

SYNCED = ["companies", "prices_eod", "announcements", "alerts", "financials_q", "documents", "chunks"]

COLUMNS = {
    "companies": ["ticker", "name", "in_portfolio", "updated_at"],
    "prices_eod": ["id", "ticker", "date", "close", "adj_close", "volume", "vol_baseline", "updated_at"],
    "announcements": ["id", "ticker", "published_at", "subject", "attachment_url", "category", "tier", "updated_at"],
    "alerts": ["id", "ticker", "date", "kind", "detail", "updated_at"],
    "financials_q": ["id", "ticker", "period", "period_end", "revenue", "ebitda", "pbt", "pat", "source", "updated_at"],
    "documents": ["id", "ticker", "doc_type", "period", "url", "label", "updated_at"],
    "chunks": ["id", "document_id", "ticker", "doc_type", "page", "text", "updated_at"],
}


def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(DDL)
    return conn


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
