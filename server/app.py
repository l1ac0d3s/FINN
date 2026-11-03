"""FINN server: receives synced rows from the laptop, serves the digest and alerts.

Run from the repo root:
    FINN_SYNC_TOKEN=... uvicorn server.app:app --reload
"""

import os
import re
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Body, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from server.alerts import ALL_CATEGORIES, DEFAULTS, alert_categories, compute_alerts, thresholds, valid_thresholds
from server.digest import build_digest
from server.pull import run_narrative, with_notes
from server.results import build_results_card, choose_source, cross_check
from server.risk import credit_model, sensitivity, ttm_from_quarters
from server.snapshot import financial_snapshot, trajectory
from shared.schema import SYNCED, connect, upsert

DB_PATH = os.environ.get("FINN_SERVER_DB", "data/server.db")
SYNC_TOKEN = os.environ.get("FINN_SYNC_TOKEN", "")
WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="FINN")


SEED_PATH = Path(os.environ.get("FINN_SEED", Path(__file__).resolve().parent.parent / "seed" / "seed.sqlite"))


def ensure_seeded(db_path, seed_path):
    """On an empty disk, start from the committed seed so the app is never blank.

    An existing database is never overwritten.
    """
    db_path, seed_path = Path(db_path), Path(seed_path)
    if not db_path.exists() and seed_path.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(seed_path, db_path)


def db():
    ensure_seeded(DB_PATH, SEED_PATH)
    return connect(DB_PATH)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/sync")
def sync(payload: dict = Body(...), authorization: str | None = Header(default=None)):
    if not SYNC_TOKEN or authorization != f"Bearer {SYNC_TOKEN}":
        raise HTTPException(status_code=401, detail="bad token")
    conn = db()
    counts = {}
    try:
        with conn:
            for table in SYNCED:
                rows = payload.get(table, [])
                for row in rows:
                    upsert(conn, table, row)
                counts[table] = len(rows)
            try:
                from server.push import notify_new
                notify_new(conn, payload.get("announcements", []))
            except Exception:
                pass   # a push problem must never fail the sync
    except (KeyError, ValueError, sqlite3.Error) as exc:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})
    finally:
        conn.close()
    return {"ok": True, "counts": counts}


@app.get("/api/digest")
def digest(hours: int = Query(24, ge=1, le=24 * 30)):
    conn = db()
    rows = conn.execute(
        """
        SELECT a.id, a.ticker, a.published_at, a.subject, a.attachment_url,
               a.category, a.tier, c.name
        FROM announcements a
        JOIN companies c ON c.ticker = a.ticker
        WHERE c.in_portfolio = 1
        """
    ).fetchall()
    alert_cats = alert_categories(load_settings(conn))
    price_rows = conn.execute(
        "SELECT ticker, date, adj_close, volume, vol_baseline FROM prices_eod "
        "WHERE date >= ? ORDER BY ticker, date",
        ((datetime.now(timezone.utc) - timedelta(days=14)).date().isoformat(),),
    ).fetchall()
    conn.close()
    prices = {}
    for p in price_rows:
        prices.setdefault(p["ticker"], []).append(dict(p))
    result = build_digest([dict(r) for r in rows], data_now(), hours, prices=prices, alert_categories=alert_cats)
    bios = management_bios()
    for group in ("high", "medium", "routine"):
        for item in result[group]:
            if item["id"] in bios:
                item["bio"] = bios[item["id"]]
    return result


def management_bios():
    """Management-change profiles keyed by announcement id."""
    conn = db()
    try:
        return {r["id"]: dict(r) for r in conn.execute("SELECT * FROM management_bios").fetchall()}
    finally:
        conn.close()


@app.get("/api/company/{ticker}/results")
def company_results(ticker: str):
    conn = db()
    rows = conn.execute(
        "SELECT period, period_end, revenue, ebitda, pbt, pat, source FROM financials_q "
        "WHERE ticker = ? ORDER BY period_end",
        (ticker.upper(),),
    ).fetchall()
    conn.close()
    raw = [dict(r) for r in rows]
    card = build_results_card(choose_source(raw))
    if card is not None:
        card["cross_check"] = cross_check(raw)
    if card is None:
        raise HTTPException(status_code=404, detail=f"no quarterly figures for {ticker}")
    return card


def claim_notes_for(conn, ticker):
    """Stored plain-English notes for a company's promise verdicts, keyed by claim id."""
    return {r["id"]: r["text"] for r in conn.execute(
        "SELECT id, text FROM claim_notes WHERE ticker = ?", (ticker,)).fetchall()}


def quarter_rows(conn, ticker):
    """One figure per quarter: the filing's where it exists, screener's otherwise. Used by every calculation,
    so a quarter is never counted twice."""
    rows = [dict(r) for r in conn.execute(
        "SELECT period, period_end, revenue, ebitda, pbt, pat, source FROM financials_q "
        "WHERE ticker = ? ORDER BY period_end",
        (ticker,),
    ).fetchall()]
    return choose_source(rows)


@app.post("/api/pull/{ticker}/narrative")
def pull_narrative(ticker: str):
    ticker = ticker.upper()
    conn = db()
    try:
        chunks = [dict(r) for r in conn.execute(
            "SELECT c.id, c.document_id, c.page, c.text, d.label FROM chunks c "
            "JOIN documents d ON d.id = c.document_id "
            "WHERE c.ticker = ? AND c.doc_type = 'transcript'",
            (ticker,),
        ).fetchall()]
        if not chunks:
            raise HTTPException(status_code=404, detail=f"no transcripts stored for {ticker}")
        quarters = quarter_rows(conn, ticker)

        key = hashlib.sha1("|".join(["v4", ticker] + sorted(c["id"] for c in chunks)).encode()).hexdigest()
        cached = conn.execute("SELECT output_json FROM pull_cache WHERE key = ?", (key,)).fetchone()
        if cached:
            return {**with_notes(json.loads(cached["output_json"]), claim_notes_for(conn, ticker)), "cached": True}

        result = run_narrative(ticker, chunks, quarters)

        conn.execute(
            "INSERT OR REPLACE INTO pull_cache (key, output_json, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps(result), datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        conn.commit()
        return {**with_notes(result, claim_notes_for(conn, ticker)), "cached": False}
    finally:
        conn.close()


def data_now():
    """The time the page is 'as of': the newest filing in the data, or the current time if
    there is none. The time windows are measured from here, so a snapshot of the data
    still shows its latest filings instead of going blank."""
    conn = db()
    try:
        latest = conn.execute("SELECT MAX(published_at) AS m FROM announcements").fetchone()["m"]
    finally:
        conn.close()
    return datetime.fromisoformat(latest) if latest else datetime.now(timezone.utc)


def load_settings(conn):
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings").fetchall()}


@app.get("/api/settings")
def get_settings():
    conn = db()
    try:
        settings = load_settings(conn)
        return {**thresholds(settings),
                "alert_categories": sorted(alert_categories(settings)),
                "all_categories": ALL_CATEGORIES}
    finally:
        conn.close()


@app.put("/api/settings")
def put_settings(body: dict = Body(...)):
    try:
        values = {key: float(body.get(key, DEFAULTS[key])) for key in DEFAULTS}
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="volume_multiple and price_move_pct must be numbers")
    if not valid_thresholds(values):
        raise HTTPException(status_code=400, detail="volume must be 1 to 10 times; price move must be 1 to 20 percent")
    cats = body.get("alert_categories")
    if cats is not None and (not isinstance(cats, list) or any(c not in ALL_CATEGORIES for c in cats)):
        raise HTTPException(status_code=400, detail="alert_categories must be a list of known categories")
    conn = db()
    try:
        with conn:
            for key, value in values.items():
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
            if cats is not None:
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                             ("alert_categories", ",".join(sorted(set(cats)))))
    finally:
        conn.close()
    return {**values, "alert_categories": sorted(set(cats)) if cats is not None else None}


@app.get("/api/company/{ticker}/snapshot")
def company_snapshot(ticker: str):
    conn = db()
    try:
        quarters = quarter_rows(conn, ticker.upper())
    finally:
        conn.close()
    if not quarters:
        raise HTTPException(status_code=404, detail=f"no quarterly figures for {ticker}")
    return {"financial": financial_snapshot(quarters), "trajectory": trajectory(quarters)}


@app.get("/api/company/{ticker}/credit")
def company_credit(ticker: str, debt: float = Query(..., ge=0), interest: float = Query(0.0, ge=0),
                   cash: float = Query(0.0, ge=0)):
    """Credit scorecard for one company. Debt, cash and interest are entered by the user, in Rs crore."""
    conn = db()
    try:
        quarters = quarter_rows(conn, ticker.upper())
    finally:
        conn.close()
    ttm = ttm_from_quarters(quarters)
    if ttm is None:
        raise HTTPException(status_code=404, detail=f"need at least four quarters of figures for {ticker}")
    return {
        "ticker": ticker.upper(),
        "ttm": ttm,
        "inputs": {"debt": debt, "cash": cash, "interest": interest},
        **credit_model(ttm, debt, cash, interest),
        "sensitivity": sensitivity(ttm, debt, cash, interest),
    }


TICKER_PATTERN = re.compile(r"^[A-Z0-9&-]{1,20}$")


def require_token(authorization):
    if not SYNC_TOKEN or authorization != f"Bearer {SYNC_TOKEN}":
        raise HTTPException(status_code=401, detail="bad token")


@app.post("/api/request/{ticker}")
def request_ticker(ticker: str):
    """Queue a ticker that has no data yet. The laptop ingests queued tickers on its next daily run."""
    symbol = ticker.strip().upper()
    if not TICKER_PATTERN.match(symbol):
        raise HTTPException(status_code=400, detail="not a valid NSE symbol")
    conn = db()
    try:
        with conn:
            conn.execute("INSERT OR IGNORE INTO ticker_requests (ticker, requested_at) VALUES (?, ?)",
                         (symbol, datetime.now(timezone.utc).isoformat(timespec="seconds")))
    finally:
        conn.close()
    return {"ok": True, "ticker": symbol, "status": "queued"}


@app.get("/api/requests")
def pending_requests(authorization: str | None = Header(default=None)):
    require_token(authorization)
    conn = db()
    try:
        rows = conn.execute("SELECT ticker FROM ticker_requests ORDER BY requested_at").fetchall()
    finally:
        conn.close()
    return {"tickers": [r["ticker"] for r in rows]}


@app.post("/api/requests/clear")
def clear_requests(body: dict = Body(...), authorization: str | None = Header(default=None)):
    require_token(authorization)
    tickers = [t for t in body.get("tickers", []) if isinstance(t, str)]
    conn = db()
    try:
        with conn:
            for t in tickers:
                conn.execute("DELETE FROM ticker_requests WHERE ticker = ?", (t,))
    finally:
        conn.close()
    return {"ok": True, "cleared": len(tickers)}


@app.get("/api/company/{ticker}/bullbear")
def company_bull_bear(ticker: str):
    """Bull and bear points from the stored transcripts, each quoted with its page."""
    from server.bullbear import bull_and_bear
    conn = db()
    try:
        chunks = [dict(r) for r in conn.execute(
            "SELECT c.id, c.document_id, c.page, c.text, d.label FROM chunks c "
            "JOIN documents d ON d.id = c.document_id "
            "WHERE c.ticker = ? AND c.doc_type = 'transcript'",
            (ticker.upper(),),
        ).fetchall()]
    finally:
        conn.close()
    if not chunks:
        raise HTTPException(status_code=404, detail=f"no transcripts stored for {ticker}")
    return {"ticker": ticker.upper(), **bull_and_bear(chunks)}


@app.post("/api/push/test")
def push_test(authorization: str | None = Header(default=None)):
    """Send a labelled test notification to every subscribed phone. Needs the sync token."""
    require_token(authorization)
    from server.push import LAST_ERROR, configured, send_test, subscriber_count
    conn = db()
    try:
        subscribers = subscriber_count(conn)
        sent, removed = send_test(conn)
    finally:
        conn.close()
    return {"sent": sent, "removed": removed, "subscribers": subscribers,
            "configured": configured(), "last_error": LAST_ERROR["text"]}


@app.get("/api/push/key")
def push_key():
    from server.push import PUBLIC, configured
    return {"key": PUBLIC if configured() else None}


@app.post("/api/push/subscribe")
def push_subscribe(body: dict = Body(...)):
    from server.push import configured, save_subscription
    if not configured():
        raise HTTPException(status_code=503, detail="push notifications are not set up on the server")
    conn = db()
    try:
        if not save_subscription(conn, body):
            raise HTTPException(status_code=400, detail="subscription is incomplete")
    finally:
        conn.close()
    return {"ok": True}


@app.get("/api/company/{ticker}/annual")
def company_annual(ticker: str):
    """Yearly net worth, borrowings, debt to equity, operating cash flow and cash quality."""
    from ingest.annual import view
    conn = db()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT year, net_worth, borrowings, total_assets, cfo, pat FROM annual_figures WHERE ticker = ?",
            (ticker.upper(),),
        ).fetchall()]
    finally:
        conn.close()
    if not rows:
        raise HTTPException(status_code=404, detail=f"no balance sheet figures for {ticker}")
    return {
        "ticker": ticker.upper(),
        "unit": "Rs crore",
        "years": view(rows),
        "not_built": ["free cash flow (needs capex)", "working-capital days (needs receivables and inventory)"],
    }


@app.get("/api/alerts")
def alerts(hours: int = Query(24, ge=1, le=24 * 30)):
    """Alerts for the window, recalculated with the saved thresholds.

    Prices are read from a little before the window, so the first day's move can be measured.
    """
    today = data_now().date()
    since = (today - timedelta(days=max(1, hours // 24))).isoformat()
    conn = db()
    try:
        rows = conn.execute(
            "SELECT ticker, date, adj_close, volume, vol_baseline FROM prices_eod "
            "WHERE date >= ? ORDER BY ticker, date",
            ((today - timedelta(days=hours // 24 + 60)).isoformat(),),
        ).fetchall()
        settings = load_settings(conn)
    finally:
        conn.close()
    found = compute_alerts([dict(r) for r in rows], settings, since)
    return {"alerts": found, "thresholds": thresholds(settings)}


if (WEB_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
