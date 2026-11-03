"""Daily ingest: prices, announcements, classification, alerts. Run from the repo root.

    python -m ingest.run_daily            # ingest only
    python -m ingest.run_daily --publish  # ingest, then sync to the server
    python -m ingest.run_daily --dry      # print the ticker list and exit
"""

import argparse
import hashlib
import os
import time
import warnings
from datetime import datetime, timedelta, timezone

import requests

from ingest import config
from ingest.announcements import categorise, fetch_nse, normalise_nse
from ingest.prices import fetch_eod, unusual_moves, with_baselines
from ingest.publish import publish
from shared.schema import connect, upsert



def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def tickers(extra=()):
    base = config.PORTFOLIO + [t for t in config.ADHOC if t not in config.PORTFOLIO]
    return base + [t for t in extra if t not in base]


def register_companies(conn, ticker_list):
    for ticker in ticker_list:
        upsert(conn, "companies", {
            "ticker": ticker,
            "name": ticker,  # real names come from the NSE listing later
            "in_portfolio": int(ticker in config.PORTFOLIO),
            "updated_at": now_iso(),
        })


def store_prices(conn, ticker, rows):
    """Store the bars and return any unusual-move alerts for the latest bar."""
    if not rows:
        return []
    rows = with_baselines(rows)
    stamp = now_iso()
    for r in rows:
        upsert(conn, "prices_eod", {
            "id": f"{ticker}|{r['date']}",
            "ticker": ticker,
            "date": r["date"],
            "close": r["close"],
            "adj_close": r["adj_close"],
            "volume": r["volume"],
            "vol_baseline": r["vol_baseline"],
            "updated_at": stamp,
        })
    today, prev = rows[-1], rows[-2] if len(rows) > 1 else None
    alerts = unusual_moves(
        ticker, today["date"], today["volume"], today["vol_baseline"],
        today["adj_close"], prev["adj_close"] if prev else None,
        config.VOLUME_MULTIPLE, config.PRICE_MOVE_PCT,
    )
    for a in alerts:
        upsert(conn, "alerts", {**a, "updated_at": stamp})
    return alerts


def store_announcements(conn, ticker, items, llm_client, days=config.ANNOUNCEMENT_DAYS):
    """Store announcements from the last `days` days. Returns the number stored.

    NSE returns the full history for a symbol, so older items are skipped before
    any classification or model call is made.
    """
    stamp = now_iso()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    count = 0
    for item in items:
        row = normalise_nse(item, ticker)
        if row["published_at"] < cutoff:
            continue
        category, tier = categorise(row["subject"], conn, llm_client)
        upsert(conn, "announcements", {**row, "category": category, "tier": tier, "updated_at": stamp})
        count += 1
    return count


def store_screener(conn, ticker, session):
    """Store quarterly figures and document links. Returns (quarters, documents) counts."""
    from ingest.screener import fetch_page, parse_documents, parse_quarters

    html, url = fetch_page(session, ticker)
    quarters = parse_quarters(html)
    docs = parse_documents(html, url)
    stamp = now_iso()
    for q in quarters:
        upsert(conn, "financials_q", {
            "id": f"{ticker}|{q['period_end']}",
            "ticker": ticker,
            "period": q["period"],
            "period_end": q["period_end"],
            "revenue": q["revenue"],
            "ebitda": q["ebitda"],
            "pbt": q["pbt"],
            "pat": q["pat"],
            "source": "screener",
            "updated_at": stamp,
        })
    for d in docs:
        upsert(conn, "documents", {
            "id": hashlib.sha1(d["url"].encode()).hexdigest(),
            "ticker": ticker,
            "doc_type": d["doc_type"],
            "period": d["period"],
            "url": d["url"],
            "label": d["label"],
            "updated_at": stamp,
        })
    from ingest.annual import store_annual
    store_annual(conn, ticker, html)   # balance sheet and cash flow; never stops the run
    return len(quarters), len(docs)


def store_texts(conn, ticker, session):
    """Download, extract and store text for the selected documents not yet done.

    Returns (chunks stored, documents that failed). Failures are counted, not hidden.
    """
    from ingest.texts import chunk_pages, download_pdf, extract_pages, select_documents

    docs = conn.execute(
        "SELECT id, url, doc_type, period FROM documents WHERE ticker = ?", (ticker,)
    ).fetchall()
    stamp = now_iso()
    stored, failed = 0, 0
    for doc in select_documents([dict(d) for d in docs]):
        if conn.execute("SELECT 1 FROM chunks WHERE document_id = ? LIMIT 1", (doc["id"],)).fetchone():
            continue
        time.sleep(config.REQUEST_DELAY_S)
        try:
            pages = extract_pages(download_pdf(session, doc["url"]))
        except Exception:
            failed += 1
            continue
        for index, (page, text) in enumerate(chunk_pages(pages)):
            upsert(conn, "chunks", {
                "id": f"{doc['id']}|{page}|{index}",
                "document_id": doc["id"],
                "ticker": ticker,
                "doc_type": doc["doc_type"],
                "page": page,
                "text": text,
                "updated_at": stamp,
            })
            stored += 1
    return stored, failed


def llm_client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import anthropic
    return anthropic.Anthropic()


def run(do_publish, skip_text=False):
    from ingest.requests import clear_queued, fetch_queued
    conn = connect(config.INGEST_DB)
    session = requests.Session()
    queued = fetch_queued(session)              # tickers looked up in the app since the last run
    ticker_list = tickers(queued)
    register_companies(conn, ticker_list)
    client = llm_client()
    summary = []
    bars_total = 0
    items_total = 0
    fundamentals_total = 0
    text_total = 0

    for ticker in ticker_list:
        bars, alerts = [], []
        try:
            bars = fetch_eod(ticker, config.PRICE_HISTORY_DAYS)
            alerts = store_prices(conn, ticker, bars)
            bars_total += len(bars)
            if not bars:
                summary.append(f"{ticker}: prices empty (no data from yfinance)")
        except Exception as exc:  # one bad ticker must not stop the run
            summary.append(f"{ticker}: prices failed ({exc})")
        try:
            items = fetch_nse(session, ticker)
            n = store_announcements(conn, ticker, items, client)
            items_total += n
            summary.append(f"{ticker}: {len(bars)} bars, {n} announcements, {len(alerts)} alerts")
        except Exception as exc:
            summary.append(f"{ticker}: announcements failed ({exc})")
        try:
            quarters, docs = store_screener(conn, ticker, session)
            fundamentals_total += quarters + docs
            summary.append(f"{ticker}: {quarters} quarters, {docs} documents from screener")
        except Exception as exc:
            summary.append(f"{ticker}: screener failed ({exc})")
        try:
            from ingest.filing import store_filing_results
            filed, bad = store_filing_results(conn, ticker, session)
            from ingest.pdf_statement import store_pdf_results
            from_pdf = store_pdf_results(conn, ticker, session)
            summary.append(f"{ticker}: {filed} quarters from XBRL, {from_pdf} from results PDFs, {bad} filings failed")
        except Exception as exc:
            summary.append(f"{ticker}: results filings failed ({exc})")
        try:
            stored, failed = (0, 0) if skip_text else store_texts(conn, ticker, session)
            text_total += stored
            summary.append(f"{ticker}: {stored} text chunks, {failed} PDFs failed")
        except Exception as exc:
            summary.append(f"{ticker}: text failed ({exc})")
        try:
            from ingest.management import store_management_bios
            read = store_management_bios(conn, ticker, session)
            from ingest.manual_management import store_manual_bios
            by_hand = store_manual_bios(conn)
            summary.append(f"{ticker}: {read} management-change filings read, {by_hand} entered by hand")
        except Exception as exc:
            summary.append(f"{ticker}: management filings failed ({exc})")
        try:
            from ingest.notes import store_claim_notes
            notes = store_claim_notes(conn, ticker, client)
            if notes is None:
                summary.append(f"{ticker}: promise notes skipped (no ANTHROPIC_API_KEY set)")
            else:
                summary.append(f"{ticker}: {notes[0]} promise notes written, {notes[1]} rejected")
        except Exception as exc:
            summary.append(f"{ticker}: promise notes failed ({exc})")
        conn.commit()

    clear_queued(session, queued)
    print("\n".join(summary))
    print(f"\nTotal: {bars_total} price bars, {items_total} announcements, "
          f"{fundamentals_total} screener rows, {text_total} text chunks")

    # Publishing an empty run would only add noise, and a run that fetched nothing
    # is a network or source problem that should be fixed before anything syncs.
    if bars_total == 0 and items_total == 0 and fundamentals_total == 0:
        raise SystemExit("Nothing fetched from any source. Check network access and the messages above.")
    if do_publish:
        publish(conn)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--dry", action="store_true")
    parser.add_argument("--skip-text", action="store_true", help="skip PDF text (not needed for the hosted app)")
    args = parser.parse_args()
    if args.dry:
        print("\n".join(tickers()))
        return
    # yfinance and pandas print deprecation warnings on every call. They don't affect
    # the data, and the context manager restores the warning settings when the run ends.
    # Exceptions still show.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        run(args.publish, skip_text=args.skip_text)


if __name__ == "__main__":
    main()
