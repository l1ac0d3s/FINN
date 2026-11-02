"""FINN server: receives synced rows from the laptop, serves the digest and alerts.

Run from the repo root:
    FINN_SYNC_TOKEN=... uvicorn server.app:app --reload
"""

import os
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Body, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from server.alerts import DEFAULTS, compute_alerts, thresholds, valid_thresholds
from server.digest import build_digest
from server.llm import complete
from server.pull import run_narrative
from server.results import build_results_card
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
    price_rows = conn.execute(
        "SELECT ticker, date, adj_close, volume, vol_baseline FROM prices_eod "
        "WHERE date >= ? ORDER BY ticker, date",
        ((datetime.now(timezone.utc) - timedelta(days=14)).date().isoformat(),),
    ).fetchall()
    conn.close()
    prices = {}
    for p in price_rows:
        prices.setdefault(p["ticker"], []).append(dict(p))
    return build_digest([dict(r) for r in rows], datetime.now(timezone.utc), hours, prices=prices)


@app.get("/api/company/{ticker}/results")
def company_results(ticker: str):
    conn = db()
    rows = conn.execute(
        "SELECT period, period_end, revenue, ebitda, pbt, pat, source FROM financials_q "
        "WHERE ticker = ? ORDER BY period_end",
        (ticker.upper(),),
    ).fetchall()
    conn.close()
    card = build_results_card([dict(r) for r in rows])
    if card is None:
        raise HTTPException(status_code=404, detail=f"no quarterly figures for {ticker}")
    return card


def quarter_rows(conn, ticker):
    return [dict(r) for r in conn.execute(
        "SELECT period, period_end, revenue, ebitda, pbt, pat, source FROM financials_q "
        "WHERE ticker = ? ORDER BY period_end",
        (ticker,),
    ).fetchall()]


@app.post("/api/pull/{ticker}/narrative")
def pull_narrative(ticker: str):
    ticker = ticker.upper()
    conn = db()
    try:
        chunks = [dict(r) for r in conn.execute(
            "SELECT c.id, c.page, c.text, d.label FROM chunks c "
            "JOIN documents d ON d.id = c.document_id "
            "WHERE c.ticker = ? AND c.doc_type = 'transcript'",
            (ticker,),
        ).fetchall()]
        if not chunks:
            raise HTTPException(status_code=404, detail=f"no transcripts stored for {ticker}")
        quarters = quarter_rows(conn, ticker)

        key = hashlib.sha1("|".join([ticker] + sorted(c["id"] for c in chunks)).encode()).hexdigest()
        cached = conn.execute("SELECT output_json FROM pull_cache WHERE key = ?", (key,)).fetchone()
        if cached:
            return {**json.loads(cached["output_json"]), "cached": True}

        try:
            result = run_narrative(ticker, chunks, quarters, complete)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"model call failed: {exc}")

        conn.execute(
            "INSERT OR REPLACE INTO pull_cache (key, output_json, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps(result), datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        conn.commit()
        return {**result, "cached": False}
    finally:
        conn.close()


def load_settings(conn):
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings").fetchall()}


@app.get("/api/settings")
def get_settings():
    conn = db()
    try:
        return thresholds(load_settings(conn))
    finally:
        conn.close()


@app.put("/api/settings")
def put_settings(body: dict = Body(...)):
    try:
        values = {key: float(body[key]) for key in DEFAULTS}
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="volume_multiple and price_move_pct must be numbers")
    if not valid_thresholds(values):
        raise HTTPException(status_code=400, detail="volume must be 1 to 10 times; price move must be 1 to 20 percent")
    conn = db()
    try:
        with conn:
            for key, value in values.items():
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    finally:
        conn.close()
    return values


@app.get("/api/alerts")
def alerts(hours: int = Query(24, ge=1, le=24 * 30)):
    """Alerts for the window, recalculated with the saved thresholds.

    Prices are read from a little before the window, so the first day's move can be measured.
    """
    today = datetime.now(timezone.utc).date()
    since = (today - timedelta(days=max(1, hours // 24))).isoformat()
    conn = db()
    try:
        rows = conn.execute(
            "SELECT ticker, date, adj_close, volume, vol_baseline FROM prices_eod "
            "WHERE date >= ? ORDER BY ticker, date",
            ((today - timedelta(days=hours // 24 + 10)).isoformat(),),
        ).fetchall()
        settings = load_settings(conn)
    finally:
        conn.close()
    found = compute_alerts([dict(r) for r in rows], settings, since)
    return {"alerts": found, "thresholds": thresholds(settings)}


if (WEB_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
