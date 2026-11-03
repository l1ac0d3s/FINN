"""Quarterly results read from the text of a results PDF, for layouts we have checked.

The income statement is read line by line. Each figure line starts with its label and ends with six
numbers: the current quarter, the same quarter a year earlier, the previous quarter, nine months this
year, nine months last year, and the full year before. We take the first of those six. The period is the
first date in the header, such as 31.12.2024, and the unit must say crores.

A PDF is used only when every figure is found and the unit is crores. Anything else returns None, and the
card keeps using the other sources. Layouts are checked one at a time, against real pages, and a figure
that disagrees with screener.in by more than 1% is flagged on the card, not hidden.
"""

import re
from datetime import datetime, timezone

from shared.schema import upsert

NUMBER = re.compile(r"\(?-?\d[\d,]*\.?\d*\)?")
DATE = re.compile(r"(\d{2})[.,](\d{2})[.,](\d{4})")
FIELDS = [
    ("revenue", re.compile(r"^REVENUE FROM OPERATIONS", re.I)),
    ("pbt", re.compile(r"^PROFIT BEFORE TAX\b", re.I)),
    ("pat", re.compile(r"^PROFIT FOR THE PERIOD\b(?!.*(FROM|REFER|DISCONTINUED))", re.I)),
    ("finance_costs", re.compile(r"^(?:[a-z]\)\s*)?FINANCE COSTS\b", re.I)),
    ("depreciation", re.compile(r"^(?:[a-z]\)\s*)?DEPRECIATION\b", re.I)),
]


def to_number(token):
    negative = token.startswith("(") and token.endswith(")")
    value = float(token.strip("()").replace(",", ""))
    return -value if negative else value


def line_values(line):
    """The six figures at the end of a line, as numbers, or None if there are fewer than six."""
    tokens = NUMBER.findall(line)
    if len(tokens) < 6:
        return None
    return [to_number(t) for t in tokens[-6:]]


def parse_statement(text):
    """The current quarter's figures from an income statement, or None if the page isn't one we can read."""
    if "crore" not in text.lower():
        return None
    date = DATE.search(text)
    if not date:
        return None
    period_end = f"{date.group(3)}-{date.group(2)}-{date.group(1)}"

    found = {}
    for line in text.splitlines():
        line = line.strip()
        for name, pattern in FIELDS:
            if name in found or not pattern.search(line):
                continue
            values = line_values(line)
            if values is not None:
                found[name] = values[0]
    if not {"revenue", "pbt", "pat"} <= set(found):
        return None

    finance, depreciation = found.get("finance_costs"), found.get("depreciation")
    ebitda = None
    if finance is not None and depreciation is not None:
        ebitda = round(found["pbt"] + finance + depreciation, 1)
    return {
        "period_end": period_end,
        "revenue": round(found["revenue"], 1),
        "pbt": round(found["pbt"], 1),
        "pat": round(found["pat"], 1),
        "ebitda": ebitda,
    }


def store_pdf_results(conn, ticker, session):
    """Read the most recent results PDFs for a company. Returns the number of quarters stored."""
    from ingest.texts import download_pdf, extract_pages
    import time
    from ingest import config

    rows = conn.execute(
        "SELECT id, published_at, attachment_url FROM announcements WHERE ticker = ? AND category = 'results' "
        "AND attachment_url LIKE '%.pdf' ORDER BY published_at DESC LIMIT 4",
        (ticker,),
    ).fetchall()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    stored = 0
    for row in rows:
        time.sleep(config.REQUEST_DELAY_S)
        try:
            text = " ".join(t for _, t in extract_pages(download_pdf(session, row["attachment_url"])))
        except Exception:
            continue
        figures = parse_statement(text)
        if figures is None:
            continue
        end = figures["period_end"]
        upsert(conn, "financials_q", {
            "id": f"{ticker}|{end}|filing",
            "ticker": ticker,
            "period": datetime.fromisoformat(end).strftime("%b %Y"),
            "period_end": end,
            "revenue": figures["revenue"],
            "ebitda": figures["ebitda"],
            "pbt": figures["pbt"],
            "pat": figures["pat"],
            "source": "filing",
            "updated_at": stamp,
        })
        stored += 1
    return stored
