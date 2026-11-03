"""Quarterly results read from the results filing's XBRL file, not from screener.in.

Listed companies file results with an XBRL file: the same figures as the filing, tagged so that a
program can read them. We read five tagged values for each quarter:
    revenue from operations, profit before tax, profit after tax, finance costs, depreciation.
EBITDA follows the brief's formula: PBT + finance costs + depreciation.

Only three-month periods are kept, so full-year and half-year figures are ignored. Segment figures
are ignored unless they are the consolidated total. Element names follow the Indian Accounting
Standards taxonomy and are matched by local name, so the namespace prefix does not matter.
Values are read as rupees and converted to crore (1 crore = 10 million rupees).

The element names and the file layout are from the standard taxonomy, not from a live NSE file.
That is checked on the first live run, and a filing that does not parse is skipped, not guessed.
"""

import io
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import date

from ingest.config import REQUEST_DELAY_S
from shared.schema import upsert
from datetime import datetime, timezone

WANTED = {
    "RevenueFromOperations": "revenue",
    "ProfitLossBeforeTax": "pbt",
    "ProfitLoss": "pat",
    "FinanceCosts": "finance_costs",
    "DepreciationDepletionAndAmortisationExpense": "depreciation",
}
RUPEES_PER_CRORE = 1e7
QUARTER_DAYS = (80, 100)   # a three-month period is 89 to 92 days; the margin allows for leap years and rounding


def local(tag):
    return tag.rsplit("}", 1)[-1]


def read_contexts(root):
    """Each context's start date, end date, and dimension members (empty for the plain total)."""
    contexts = {}
    for el in root.iter():
        if local(el.tag) != "context":
            continue
        start = end = None
        members = []
        for sub in el.iter():
            name = local(sub.tag)
            if name == "startDate":
                start = (sub.text or "").strip()
            elif name == "endDate":
                end = (sub.text or "").strip()
            elif name in ("explicitMember", "typedMember"):
                members.append((sub.text or "").strip())
        contexts[el.get("id")] = {"start": start, "end": end, "members": members}
    return contexts


def member_rank(members):
    """0 for the plain total, 1 for the consolidated total, None for any other breakdown (not used)."""
    if not members:
        return 0
    if all("consolidated" in m.lower() and "non" not in m.lower() and "standalone" not in m.lower()
           and "separate" not in m.lower() for m in members):
        return 1
    return None


def parse_xbrl(xml_bytes):
    """{period_end ISO date: {field: crore}} for three-month periods. Empty if nothing is recognised."""
    root = ET.fromstring(xml_bytes)
    contexts = read_contexts(root)
    best = {}   # (period_end, field) -> (rank, value)
    for el in root.iter():
        field = WANTED.get(local(el.tag))
        if field is None or el.get("contextRef") is None or not el.text:
            continue
        ctx = contexts.get(el.get("contextRef"))
        if not ctx or not ctx["start"] or not ctx["end"]:
            continue
        days = (date.fromisoformat(ctx["end"]) - date.fromisoformat(ctx["start"])).days
        if not QUARTER_DAYS[0] <= days <= QUARTER_DAYS[1]:
            continue
        rank = member_rank(ctx["members"])
        if rank is None or "INR" not in (el.get("unitRef") or "INR").upper():
            continue
        try:
            value = float(el.text.strip().replace(",", ""))
        except ValueError:
            continue
        key = (ctx["end"], field)
        if key not in best or rank < best[key][0]:
            best[key] = (rank, value / RUPEES_PER_CRORE)

    periods = {}
    for (end, field), (_, value) in best.items():
        periods.setdefault(end, {})[field] = value
    return periods


def financial_rows(ticker, periods, stamp):
    """financials_q rows for each quarter that has revenue. EBITDA is PBT + finance costs + depreciation,
    and is left empty when any of those three is missing."""
    rows = []
    for end in sorted(periods):
        vals = periods[end]
        if "revenue" not in vals:
            continue
        ebitda = None
        if all(k in vals for k in ("pbt", "finance_costs", "depreciation")):
            ebitda = round(vals["pbt"] + vals["finance_costs"] + vals["depreciation"], 1)
        rows.append({
            "id": f"{ticker}|{end}|filing",
            "ticker": ticker,
            "period": date.fromisoformat(end).strftime("%b %Y"),
            "period_end": end,
            "revenue": round(vals["revenue"], 1),
            "ebitda": ebitda,
            "pbt": round(vals["pbt"], 1) if "pbt" in vals else None,
            "pat": round(vals["pat"], 1) if "pat" in vals else None,
            "source": "filing",
            "updated_at": stamp,
        })
    return rows


def unpack(content):
    """The XBRL XML, whether the exchange sent it bare or inside a zip file."""
    if content[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith(".xml")]
            if not names:
                raise ValueError("zip file has no XML inside")
            return archive.read(names[0])
    return content


def store_filing_results(conn, ticker, session):
    """Read each results filing that has an XBRL file. Returns (quarters stored, filings that failed)."""
    rows = conn.execute(
        "SELECT id, xbrl_url FROM announcements WHERE ticker = ? AND category = 'results' "
        "AND xbrl_url IS NOT NULL", (ticker,),
    ).fetchall()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    stored = failed = 0
    for row in rows:
        time.sleep(REQUEST_DELAY_S)
        try:
            resp = session.get(row["xbrl_url"], timeout=60)
            resp.raise_for_status()
            periods = parse_xbrl(unpack(resp.content))
        except Exception:
            failed += 1
            continue
        for item in financial_rows(ticker, periods, stamp):
            upsert(conn, "financials_q", item)
            stored += 1
    return stored, failed
