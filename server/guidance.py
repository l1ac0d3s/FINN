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
REPORTED = re.compile(r"\b(?:was|were|grew|came in|delivered|reported|stood at|achieved)\b", re.I)
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


def period_label(sentence):
    quarter = PERIOD_Q.search(sentence)
    if quarter:
        return f"Q{quarter.group(1)} FY{quarter.group(2)}"
    year = PERIOD_FY.search(sentence)
    return f"FY{year.group(1)}" if year else None


def statement_from(sentence):
    """The fields for one forward-looking revenue growth statement, or None."""
    if not (PERCENT.search(sentence) or RANGE.search(sentence)):
        return None
    if not REVENUE.search(sentence) or not GROWTH.search(sentence):
        return None
    if not FORWARD.search(sentence) or REPORTED.search(sentence) or SEQUENTIAL.search(sentence):
        return None
    return {"metric": "revenue", "period": period_label(sentence), "growth_pct": growth_number(sentence)}


def guidance_statements(chunks):
    """Candidate statements from every chunk, in document order. Each one carries its exact quote,
    page and document label. A sentence appears once even if it is stored twice."""
    seen, found = set(), []
    for chunk in chunks:
        for sentence in SENTENCE_END.split(chunk["text"]):
            sentence = sentence.strip()
            fields = statement_from(sentence)
            if fields is None:
                continue
            key = (" ".join(sentence.lower().split()), chunk["page"])
            if key in seen:
                continue
            seen.add(key)
            found.append({**fields, "quote": sentence, "page": chunk["page"], "label": chunk["label"]})
    return found
