"""screener.in: company documents and the quarterly results table.

Unverified against the live site. The parser is tested on a saved HTML sample
that I wrote to match screener's layout as I understand it. Run check_screener
on your machine and adjust the label map or link patterns if a field is empty.

Screener shows figures in Rs crore. Its 'Operating Profit' row is used as EBITDA.
It is close to EBITDA but not identical, so every EBITDA figure is labelled
source='screener' in the database.
"""

import re
import time
from calendar import monthrange
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ingest.config import REQUEST_DELAY_S

SCREENER = "https://www.screener.in"
HEADERS = {"User-Agent": "Mozilla/5.0 (FINN research prototype)"}

# Screener row label (after stripping the trailing '+' it adds) -> our metric.
QUARTER_ROWS = {
    "Sales": "revenue",
    "Operating Profit": "ebitda",
    "Profit before tax": "pbt",
    "Net Profit": "pat",
}

DOC_PATTERNS = [
    ("annual_report", re.compile(r"annual report", re.I)),
    ("transcript", re.compile(r"transcript|concall", re.I)),
    ("investor_presentation", re.compile(r"presentation|\bppt\b", re.I)),
]


def company_urls(symbol):
    """Consolidated figures first, then standalone."""
    return [f"{SCREENER}/company/{symbol}/consolidated/", f"{SCREENER}/company/{symbol}/"]


def fetch_page(session, symbol):
    """Return (html, url) for the first screener page that has a quarters table."""
    for url in company_urls(symbol):
        time.sleep(REQUEST_DELAY_S)
        resp = session.get(url, headers=HEADERS, timeout=20)
        if resp.status_code == 200 and 'id="quarters"' in resp.text:
            return resp.text, url
    raise LookupError(f"no screener page with a quarters table for {symbol}")


def parse_number(text):
    """'1,234.5%' -> 1234.5. Blank or dash -> None."""
    cleaned = text.replace(",", "").replace("%", "").strip()
    if cleaned in ("", "-", "--"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def period_end(label):
    """'Sep 2025' -> date(2025, 9, 30). Used to sort periods and find year-ago quarters."""
    month_name, year = label.split()[:2]
    month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"].index(month_name[:3]) + 1
    year = int(year)
    return date(year, month, monthrange(year, month)[1])


def parse_quarters(html):
    """Quarterly figures, oldest first: [{'period', 'period_end', 'revenue', ...}]."""
    soup = BeautifulSoup(html, "html.parser")
    section = soup.find(id="quarters")
    if section is None or section.find("table") is None:
        raise ValueError("no quarters table found")
    table = section.find("table")

    rows = table.find_all("tr")
    header_index, header = None, []
    for i, tr in enumerate(rows):
        cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
        if any(re.match(r"[A-Za-z]{3} \d{4}", c) for c in cells):
            header_index, header = i, cells[1:]
            break
    if header_index is None:
        # Fail loudly with the first rows we actually saw, so the layout can be fixed.
        seen = [[c.get_text(strip=True) for c in tr.find_all(["th", "td"])][:4] for tr in rows[:3]]
        raise ValueError(f"no period headers in quarters table; first rows were {seen}")
    periods = [p for p in header if re.match(r"[A-Za-z]{3} \d{4}", p)]

    by_metric = {}
    for tr in rows[header_index + 1:]:
        cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
        if not cells:
            continue
        label = cells[0].rstrip("+ ").strip()
        if label in QUARTER_ROWS:
            by_metric[QUARTER_ROWS[label]] = [parse_number(v) for v in cells[1:]]

    quarters = []
    for i, period in enumerate(periods):
        q = {"period": period, "period_end": period_end(period).isoformat()}
        for metric in QUARTER_ROWS.values():
            values = by_metric.get(metric, [])
            q[metric] = values[i] if i < len(values) else None
        quarters.append(q)
    quarters.sort(key=lambda q: q["period_end"])
    return quarters


def classify_doc(text):
    for doc_type, pattern in DOC_PATTERNS:
        if pattern.search(text):
            return doc_type
    return None


def parse_documents(html, base_url):
    """Annual reports, transcripts and presentations linked from the page.

    Matches on the link text. Duplicate URLs are dropped.
    """
    soup = BeautifulSoup(html, "html.parser")
    seen, docs = set(), []
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        doc_type = classify_doc(text)
        if doc_type is None:
            continue
        url = urljoin(base_url, a["href"])
        if url in seen:
            continue
        seen.add(url)
        year = re.search(r"FY\s?\d{2,4}|20\d{2}", text)
        docs.append({
            "doc_type": doc_type,
            "period": year.group(0) if year else None,
            "url": url,
            "label": text,
        })
    return docs
