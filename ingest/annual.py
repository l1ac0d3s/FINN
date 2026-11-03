"""Balance sheet and operating cash flow by year, read from screener.in's company page.

The company page has a balance sheet, a cash-flow summary and a profit and loss table, each in its own
section. We read the rows we need, by label, for each year:
    net worth (equity capital + reserves), borrowings, total assets, cash from operating activity, net profit.

From these we compute:
    cash quality = cash from operations / net profit x 100
    debt to equity = borrowings / net worth

NOT built, because screener's summary tables do not carry them: capital expenditure (so no free cash
flow) and receivables or inventory (so no working-capital days). Those need the full cash-flow statement
and the balance sheet notes from the filing.

If a section or row is missing, the year simply has no figure for it. The daily run continues.
"""

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from ingest.screener import parse_number
from shared.schema import upsert

SECTIONS = {"balance-sheet": "balance", "cash-flow": "cashflow", "profit-loss": "profit"}
ROWS = {
    ("balance", "equity capital"): "equity",
    ("balance", "reserves"): "reserves",
    ("balance", "borrowings"): "borrowings",
    ("balance", "total assets"): "total_assets",
    ("cashflow", "cash from operating activity"): "cfo",
    ("profit", "net profit"): "pat",
}
YEAR = re.compile(r"(\d{4})")


def clean_label(text):
    """'Cash from Operating Activity +' -> 'cash from operating activity'."""
    return re.sub(r"[\s+\-]+$", "", text.strip()).lower()


def parse_section(section):
    """{year: {key: value}} for the rows we know, from one screener section table."""
    table = section.find("table")
    if table is None:
        return {}
    header = None
    for row in table.find_all("tr"):
        cells = row.find_all("th")
        if cells and any(YEAR.search(c.get_text(" ", strip=True)) for c in cells):
            header = [c.get_text(" ", strip=True) for c in cells]
            break
    if header is None:
        return {}
    years = [YEAR.search(h).group(1) if YEAR.search(h) else None for h in header]

    found = {}
    kind = SECTIONS[section.get("id")]
    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        key = ROWS.get((kind, clean_label(cells[0].get_text(" ", strip=True))))
        if key is None:
            continue
        values = [parse_number(c.get_text(" ", strip=True)) for c in cells[1:]]
        for index, value in enumerate(values, start=1):
            year = years[index] if index < len(years) else None
            if year and value is not None:
                found.setdefault(year, {})[key] = value
    return found


def parse_annual(html):
    """{year: {equity, reserves, borrowings, total_assets, cfo, pat}} for the years screener shows."""
    soup = BeautifulSoup(html, "html.parser")
    merged = {}
    for section_id in SECTIONS:
        section = soup.find(id=section_id)
        if section is None:
            continue
        for year, values in parse_section(section).items():
            merged.setdefault(year, {}).update(values)
    return merged


def metrics(values):
    """Net worth, debt to equity and cash quality for one year. None where an input is missing."""
    equity, reserves = values.get("equity"), values.get("reserves")
    net_worth = values.get("net_worth")
    if net_worth is None and equity is not None and reserves is not None:
        net_worth = equity + reserves
    borrowings = values.get("borrowings")
    cfo, pat = values.get("cfo"), values.get("pat")
    return {
        "net_worth": net_worth,
        "borrowings": borrowings,
        "total_assets": values.get("total_assets"),
        "cfo": cfo,
        "pat": pat,
        "debt_to_equity_x": round(borrowings / net_worth, 2) if borrowings is not None and net_worth else None,
        "cash_quality_pct": round(cfo / pat * 100, 1) if cfo is not None and pat else None,
    }


def store_annual(conn, ticker, html):
    """Store one row per year. Returns the number of years stored; never raises, so the daily run goes on."""
    try:
        years = parse_annual(html)
    except Exception:
        return 0
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    stored = 0
    for year, values in sorted(years.items()):
        m = metrics(values)
        if all(m[k] is None for k in ("net_worth", "borrowings", "cfo", "pat")):
            continue
        upsert(conn, "annual_figures", {
            "id": f"{ticker}|{year}",
            "ticker": ticker,
            "year": year,
            "net_worth": m["net_worth"],
            "borrowings": m["borrowings"],
            "total_assets": m["total_assets"],
            "cfo": m["cfo"],
            "pat": m["pat"],
            "updated_at": stamp,
        })
        stored += 1
    return stored


def view(rows):
    """Rows from annual_figures, oldest first, with the derived metrics added."""
    out = []
    for row in sorted(rows, key=lambda r: r["year"]):
        out.append({"year": row["year"], **metrics(row)})
    return out
