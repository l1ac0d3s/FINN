"""Guidance statements from transcripts, found without a language model.

A transcript sentence is kept only if it:
  - states a percentage,
  - is about revenue (or sales) growth,
  - looks forward-looking (expects, guidance, outlook, or a future FY or quarter),
  - does not describe a reported result (was, were, grew, delivered) or a sequential change.

Each kept sentence is an exact sentence from a page, so the word-for-word check in server/pull.py
still applies. Precision is favoured over recall: a missed statement is better than a wrong one.
"""

import re
from collections import Counter

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
PERCENT = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:%|per\s?cent\b)", re.I)
RANGE = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*(?:%|per\s?cent)?\s*(?:to|-|–)\s*(-?\d+(?:\.\d+)?)\s*(?:%|per\s?cent\b)", re.I
)
REVENUE = re.compile(r"\b(?:revenues?|sales|top\s?line)\b", re.I)
GROWTH = re.compile(r"\b(?:growth|grow|growing|increase|expand)\w*", re.I)
FORWARD = re.compile(
    r"\b(?:expect\w*|guid\w*|outlook|anticipat\w*|target\w*|we see|going forward|should|will|likely)\b"
    r"|\bFY\s?\d{2}\b|\bnext (?:year|quarter)\b",
    re.I,
)
REPORTED = re.compile(
    r"\b(?:was|were|grew|came in|delivered|reported|stood at|achieved|been able to|maintained)\b", re.I
)
SEQUENTIAL = re.compile(r"sequential|quarter-on-quarter|\bQoQ\b", re.I)
PERIOD_Q = re.compile(r"\bQ([1-4])\s*FY\s?(\d{2})\b", re.I)
PERIOD_FY = re.compile(r"\bFY\s?(\d{2})\b", re.I)


def growth_number(sentence):
    """The growth figure. A range gives its lower end, the conservative reading. Otherwise it is the
    first percentage after the word 'growth', or the first percentage in the sentence."""
    rng = RANGE.search(sentence)
    if rng:
        return float(rng.group(1))
    word = GROWTH.search(sentence)
    match = (PERCENT.search(sentence, word.end()) if word else None) or PERCENT.search(sentence)
    return float(match.group(1)) if match else None


def range_upper(sentence):
    """The upper end of a stated range such as '1% to 2%', or None when the sentence gives a single figure."""
    rng = RANGE.search(sentence)
    return float(rng.group(2)) if rng else None


def period_label(sentence):
    quarter = PERIOD_Q.search(sentence)
    if quarter:
        return f"Q{quarter.group(1)} FY{quarter.group(2)}"
    year = PERIOD_FY.search(sentence)
    return f"FY{year.group(1)}" if year else None


MARGIN_OR_CAPEX = re.compile(
    r"\b(?:operating\s+margins?|ebitda\s+margins?|margins?|capex|capital\s+expenditure)\b", re.I
)


def margin_or_capex(sentence):
    """'margin' or 'capex' when the sentence is about one of them, otherwise None."""
    found = MARGIN_OR_CAPEX.search(sentence)
    if not found:
        return None
    return "capex" if re.search(r"capex|capital\s+expenditure", found.group(0), re.I) else "margin"


def statement_from(sentence):
    """The fields for one forward-looking guidance statement with a number, or None.

    Revenue growth is the metric the verdicts check. Margin and capex guidance are listed with their
    stated figure, but the verdict is 'not checked' for them, because they are not compared with reported figures.
    """
    if not (PERCENT.search(sentence) or RANGE.search(sentence)):
        return None
    if not FORWARD.search(sentence) or REPORTED.search(sentence) or SEQUENTIAL.search(sentence):
        return None
    if REVENUE.search(sentence) and GROWTH.search(sentence):
        return {"metric": "revenue", "period": period_label(sentence), "growth_pct": growth_number(sentence),
                "upper": range_upper(sentence)}
    metric = margin_or_capex(sentence)
    if metric:
        return {"metric": metric, "period": period_label(sentence), "growth_pct": growth_number(sentence),
                "upper": range_upper(sentence)}
    return None


CALL_REFERENCE = re.compile(r"\b(Q[1-4]|H[12])\s*(?:of\s*)?FY\s?(\d{2})\b", re.I)
RELATIVE_THIS = re.compile(
    r"\b(?:for the (?:full )?(?:financial )?year|rest of the year|this (?:financial )?year|"
    r"current (?:financial )?year|full[- ]year)\b", re.I)
RELATIVE_NEXT = re.compile(r"\b(?:coming|next) (?:financial )?year\b", re.I)


def call_context(chunks):
    """{document: (fiscal year, quarter)} for each call: the year and quarter named most often in its text,
    such as 'H1 of FY27'. A call with no such reference has no entry."""
    found = {}
    for chunk in chunks:
        document = chunk.get("document_id") or chunk["label"]
        for match in CALL_REFERENCE.finditer(chunk["text"]):
            found.setdefault(document, []).append((int(match.group(2)), match.group(1).upper()))
    context = {}
    for document, references in found.items():
        year = Counter(y for y, _ in references).most_common(1)[0][0]
        quarter = Counter(q for y, q in references if y == year).most_common(1)[0][0]
        context[document] = (year, quarter)
    return context


def inferred_period(sentence, context):
    """The fiscal year a sentence means when it names none, worked out from the call it was said on.

    'for the year' and 'rest of the year' mean the call's own year, and 'the coming year' means the next.
    On a year-end call (Q4 or H2) 'the year' could mean either, so nothing is inferred.
    """
    if context is None:
        return None
    year, quarter = context
    if RELATIVE_NEXT.search(sentence):
        return f"FY{year + 1}"
    if RELATIVE_THIS.search(sentence):
        return None if quarter in ("Q4", "H2") else f"FY{year}"
    return None


def guidance_statements(chunks):
    """Candidate statements from every chunk, in document order. Each one carries its exact quote,
    page and document label. A sentence appears once even if it is stored twice. When a sentence names
    no year, the year is worked out from the call (see inferred_period)."""
    contexts = call_context(chunks)
    seen, found = set(), []
    for chunk in chunks:
        document = chunk.get("document_id") or chunk["label"]
        for sentence in SENTENCE_END.split(chunk["text"]):
            sentence = sentence.strip()
            fields = statement_from(sentence)
            if fields is None:
                continue
            if fields["period"] is None:
                fields["period"] = inferred_period(sentence, contexts.get(document))
            key = (" ".join(sentence.lower().split()), chunk["page"])
            if key in seen:
                continue
            seen.add(key)
            found.append({**fields, "quote": sentence, "page": chunk["page"], "label": chunk["label"]})
    return found
