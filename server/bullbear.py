"""Bull and bear points, selected from the earnings-call transcripts and quoted word for word.

This is a selection, not an argument. A sentence is a bull point when it has more positive words than
negative ones, and a bear point when it has more negative words. Each point is a sentence management
actually said, with its page, so a reader can check it against the source. Read the transcript before
relying on a point. No language model is used.
"""

import re

from server.guidance import SENTENCE_END

BULL_WORDS = re.compile(
    r"\b(?:record|strong\w*|growth|grew|increas\w*|improv\w*|expansion|expand\w*|wins?|won|robust|healthy|"
    r"ahead of|above (?:our )?expectations|higher|upgrad\w*|momentum|accelerat\w*|confident|opportunit\w*)\b",
    re.I,
)
BEAR_WORDS = re.compile(
    r"\b(?:declin\w*|headwind\w*|pressure\w*|below (?:our )?expectations|lower than|softer|weak\w*|slowdown|"
    r"slow\w*|delay\w*|churn\w*|attrition|competitive intensity|challeng\w*|risks?|uncertain\w*|decelerat\w*|"
    r"fell|fall\w*|drop\w*|lower)\b",
    re.I,
)
MIN_CHARS, MAX_CHARS = 60, 320   # short fragments and long run-on passages make poor points
MAX_POINTS = 4
METHOD = ("Selected by keyword from the stored transcripts. Each point is a sentence management said, quoted "
          "word for word with its page. This is a selection, not an analysis; read the transcript before relying on it.")


def stance(sentence):
    """('bull' or 'bear', strength) for a sentence, or None if it leans neither way."""
    if not MIN_CHARS <= len(sentence) <= MAX_CHARS or sentence.endswith("?"):
        return None
    bull = len(BULL_WORDS.findall(sentence))
    bear = len(BEAR_WORDS.findall(sentence))
    if bull > bear:
        return "bull", bull - bear
    if bear > bull:
        return "bear", bear - bull
    return None


def bull_and_bear(chunks, limit=MAX_POINTS):
    """The strongest bull and bear sentences from the transcript chunks, most decisive first."""
    scored = {"bull": [], "bear": []}
    seen = set()
    for chunk in chunks:
        for sentence in SENTENCE_END.split(chunk["text"]):
            text = sentence.strip()
            key = " ".join(text.lower().split())
            if key in seen:
                continue
            found = stance(text)
            if found is None:
                continue
            seen.add(key)
            side, strength = found
            scored[side].append((strength, {"quote": text, "page": chunk["page"], "doc": chunk["label"]}))
    return {
        side: [point for _, point in sorted(scored[side], key=lambda item: -item[0])[:limit]]
        for side in ("bull", "bear")
    } | {"method": METHOD}
