"""Narrative vs numbers: check management's forward-looking revenue growth statements against reported growth.

Steps:
1. Find forward-looking revenue growth sentences in the transcripts (server/guidance.py).
   No language model is used here, so the same transcripts always give the same answer.
2. Keep only statements whose quote appears word for word on the stated page of the source.
   A growth figure is kept only if it appears in the quote, and never for sequential figures.
3. Compare each statement with reported growth: a quarter with its year-ago quarter, or a full
   fiscal year (April to March) with the year before, summed from four quarters each.

Statements that fail step 2 are dropped and counted, never shown. Verdicts come from the figures.
Plain-English notes on each verdict are written on the laptop (ingest/notes.py) and attached here.
"""

import hashlib
import re
from calendar import monthrange

from server.guidance import SEQUENTIAL, guidance_statements
from server.results import growth_pct, year_ago
from server.risk import achievement_pct, grade

PERIOD = re.compile(r"\bQ([1-4])\s*FY\s?(\d{2})\b", re.I)
FY_PERIOD = re.compile(r"^\s*FY\s?(\d{2})\s*$", re.I)
MONTH_PERIOD = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{4})\b", re.I)
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
GRADED = ("met", "nearly met", "partly met", "missed")   # verdicts that have numbers behind them


def normalise(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def quarter_end(label):
    """'Q3 FY26' -> '2025-12-31'; 'Dec 2025' -> '2025-12-31'. Indian financial years run April to March."""
    text = label or ""
    match = PERIOD.search(text)
    if match:
        quarter, fy = int(match.group(1)), 2000 + int(match.group(2))
        year, month, day = {1: (fy - 1, 6, 30), 2: (fy - 1, 9, 30), 3: (fy - 1, 12, 31), 4: (fy, 3, 31)}[quarter]
        return f"{year:04d}-{month:02d}-{day:02d}"
    month_match = MONTH_PERIOD.search(text)
    if month_match:
        year = int(month_match.group(2))
        month = MONTHS.index(month_match.group(1).title()) + 1
        return f"{year:04d}-{month:02d}-{monthrange(year, month)[1]:02d}"
    return None


def number_in_quote(value, quote):
    return any(abs(float(token) - value) < 1e-9 for token in re.findall(r"\d+(?:\.\d+)?", quote))


def growth_from_quote(quote):
    """The growth percentage stated in a quote, or None. Only quotes that say 'growth' count, and never
    quotes about sequential change, so a share such as '10.5% of our revenues' is never read as growth."""
    if "growth" not in quote.lower() or SEQUENTIAL.search(quote):
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", quote)
    return float(match.group(1)) if match else None


def ground(claims, passages):
    """Keep claims whose quote appears verbatim on the stated page. Returns (kept, dropped count)."""
    kept, dropped = [], 0
    for claim in claims:
        raw = str(claim.get("quote", ""))
        quote = normalise(raw)
        try:
            page = int(claim.get("page"))
        except (TypeError, ValueError):
            page = None
        source = next(
            (p for p in passages if p["page"] == page and quote and quote in normalise(p["text"])),
            None,
        )
        if source is None:
            dropped += 1
            continue
        growth = None if SEQUENTIAL.search(raw) else claim.get("growth_pct")
        if growth is not None and not number_in_quote(growth, raw):
            growth = None
        if growth is None:
            growth = growth_from_quote(raw)
        kept.append({**claim, "growth_pct": growth, "doc": source["label"], "page": source["page"]})
    return kept, dropped


def judge(actual, promised):
    """Verdict from the share of the promise delivered: met, nearly met, partly met or missed."""
    return grade(achievement_pct(promised, actual)) or "not checked"


def fiscal_year_growth(quarters, fy):
    """Actual revenue growth for a full fiscal year (April to March) over the year before, summed from
    four quarters each. `fy` is the calendar year the year ends in, so FY26 is 2026. None if any quarter is missing."""
    def ends(year):
        return {f"{year - 1}-06-30", f"{year - 1}-09-30", f"{year - 1}-12-31", f"{year}-03-31"}

    current = [q for q in quarters if q["period_end"] in ends(fy)]
    prior = [q for q in quarters if q["period_end"] in ends(fy - 1)]
    if len(current) < 4 or len(prior) < 4 or any(q.get("revenue") is None for q in current + prior):
        return None
    total_now = sum(q["revenue"] for q in current)
    total_before = sum(q["revenue"] for q in prior)
    return round((total_now / total_before - 1) * 100, 1)


def verdict_for(claim, quarters):
    """(actual YoY revenue growth, verdict) for a claim about revenue growth in a named quarter or fiscal year."""
    if claim.get("metric") != "revenue" or claim.get("growth_pct") is None:
        return None, "not checked"
    promised = float(claim["growth_pct"])
    fy = FY_PERIOD.match(claim.get("period") or "")
    if fy:
        actual = fiscal_year_growth(quarters, 2000 + int(fy.group(1)))
        if actual is None:
            return None, "pending"
        return actual, judge(actual, promised)
    target = quarter_end(claim.get("period"))
    if target is None:
        return None, "not checked"
    quarter = next((q for q in quarters if q["period_end"] == target), None)
    if quarter is None:
        return None, "pending"
    prior = year_ago(quarters, quarter)
    actual = growth_pct(quarter.get("revenue"), prior.get("revenue") if prior else None)
    if actual is None:
        return None, "not available"
    return round(actual, 1), judge(actual, promised)


def quarter_table(quarters, count=4):
    """The last `count` quarters with revenue and its QoQ and YoY growth."""
    rows = []
    for i in range(max(0, len(quarters) - count), len(quarters)):
        quarter = quarters[i]
        previous = quarters[i - 1] if i > 0 else None
        prior = year_ago(quarters, quarter)
        rows.append({
            "period": quarter["period"],
            "revenue": quarter.get("revenue"),
            "qoq_pct": growth_pct(quarter.get("revenue"), previous.get("revenue") if previous else None),
            "yoy_pct": growth_pct(quarter.get("revenue"), prior.get("revenue") if prior else None),
        })
    return rows


def claim_id(ticker, claim):
    """A stable id for a verdict. The same statement with the same verdict always gets the same id,
    so a note written once is reused, and a changed verdict gets a fresh note."""
    parts = [ticker, normalise(claim["quote"]), str(claim["page"]), str(claim["verdict"]),
             str(claim["promised_growth_pct"]), str(claim["actual_yoy_pct"])]
    return hashlib.sha1("|".join(parts).encode()).hexdigest()


def with_notes(result, notes):
    """Attach the stored plain-English note to each claim. `notes` maps claim id to text."""
    return {**result, "claims": [{**c, "explanation": notes.get(c.get("id"))} for c in result["claims"]]}


def run_narrative(ticker, chunks, quarters):
    """The narrative-vs-numbers output for one company, from the stored transcripts and quarterly figures."""
    found = guidance_statements(chunks)
    if not found:
        return {"ticker": ticker, "claims": [], "dropped": 0, "quarters": quarter_table(quarters),
                "note": "no forward-looking revenue growth statement with a number was found in the stored transcripts"}

    kept, dropped = ground(found, chunks)
    claims, seen = [], set()
    for claim in kept:
        key = (normalise(claim["quote"]), claim["page"])
        if key in seen:
            continue
        seen.add(key)
        actual, verdict = verdict_for(claim, quarters)
        row = {
            "quote": claim["quote"],
            "doc": claim["doc"],
            "page": claim["page"],
            "metric": claim.get("metric"),
            "period": claim.get("period"),
            "promised_growth_pct": claim.get("growth_pct"),
            "actual_yoy_pct": actual,
            "verdict": verdict,
        }
        claims.append({**row, "id": claim_id(ticker, row)})
    return {"ticker": ticker, "claims": claims, "dropped": dropped, "quarters": quarter_table(quarters)}
