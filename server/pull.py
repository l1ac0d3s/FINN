"""Narrative vs numbers: check management's quantified revenue claims against reported growth.

Steps:
1. Pick the transcript passages most likely to hold guidance (keyword scoring).
2. Ask the model for claims as JSON, each with a verbatim quote and a page number.
3. Keep only claims whose quote appears word for word on that page of the source.
4. For claims about revenue growth in a named quarter, compare with reported YoY growth.

Claims that fail step 3 are dropped and counted, never shown. The model never
supplies a number that the verdict depends on: verdicts come from the figures.
"""

import re
from calendar import monthrange

from server.llm import parse_json_list
from server.results import growth_pct, year_ago

GUIDANCE_WORDS = re.compile(
    r"guidance|expect|outlook|anticipat|target|aim|we see|grow|margin|capex|capital expenditure|"
    r"FY\s?\d{2}|Q[1-4]", re.I,
)
PERIOD = re.compile(r"\bQ([1-4])\s*FY\s?(\d{2})\b", re.I)
MONTH_PERIOD = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{4})\b", re.I)
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MET_TOLERANCE_PCT = 1.0     # reported growth within 1 percentage point of the promise counts as met
MAX_PASSAGES = 6            # fewer passages means a faster model call on a laptop CPU

SYSTEM_PROMPT = (
    "You extract management's quantified statements from earnings-call transcript passages. "
    "Use only the passages you are given. Reply with a JSON list and nothing else. "
    "Each item must have: quote (one sentence copied exactly, word for word, from a passage), "
    "page (the page number in that passage's header), metric (one of revenue, ebitda, pat, "
    "margin, capex, other), growth_pct (the growth percentage stated, as a plain number, or null), "
    "period (for example 'Q3 FY26' or 'FY27', or null). "
    "Include only statements about current or future performance that state a number. "
    "If there are none, reply with []."
)


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


def pick_passages(chunks, limit=MAX_PASSAGES):
    """Chunks with the most guidance-type words, most relevant first."""
    scored = [(len(GUIDANCE_WORDS.findall(c["text"])), c) for c in chunks]
    scored = [item for item in scored if item[0] > 0]
    scored.sort(key=lambda item: -item[0])
    return [c for _, c in scored[:limit]]


def build_prompt(passages):
    lines = [f"[{p['label']} | page {p['page']}] {p['text']}" for p in passages]
    return "Passages:\n" + "\n".join(lines)


def ground(claims, passages):
    """Keep claims whose quote appears verbatim on the stated page. Returns (kept, dropped count)."""
    kept, dropped = [], 0
    for claim in claims:
        quote = normalise(str(claim.get("quote", "")))
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
        kept.append({**claim, "doc": source["label"], "page": source["page"]})
    return kept, dropped


def verdict_for(claim, quarters):
    """(actual YoY revenue growth, verdict) for a claim about revenue growth in a named quarter."""
    if claim.get("metric") != "revenue" or claim.get("growth_pct") is None:
        return None, "not checked"
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
    promised = float(claim["growth_pct"])
    return round(actual, 1), ("met" if actual >= promised - MET_TOLERANCE_PCT else "missed")


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


def run_narrative(ticker, chunks, quarters, llm):
    """The narrative-vs-numbers output for one company. `llm(system, user)` returns text."""
    passages = pick_passages(chunks)
    if not passages:
        return {"ticker": ticker, "claims": [], "dropped": 0, "quarters": quarter_table(quarters),
                "note": "no guidance passages found in the stored transcripts"}

    kept, dropped = ground(parse_json_list(llm(SYSTEM_PROMPT, build_prompt(passages))), passages)
    claims = []
    for claim in kept:
        actual, verdict = verdict_for(claim, quarters)
        claims.append({
            "quote": claim["quote"],
            "doc": claim["doc"],
            "page": claim["page"],
            "metric": claim.get("metric"),
            "period": claim.get("period"),
            "promised_growth_pct": claim.get("growth_pct"),
            "actual_yoy_pct": actual,
            "verdict": verdict,
        })
    return {"ticker": ticker, "claims": claims, "dropped": dropped, "quarters": quarter_table(quarters)}
