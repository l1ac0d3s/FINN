"""Ask a question about a company and get quotes from its transcripts, or "not found in source".

No language model is used. The question's content words are matched against each transcript sentence, and the
best matches are returned word for word with their page. If no sentence matches well enough, the answer says so
instead of guessing. Nothing outside the stored transcripts is used.
"""

import re

from server.guidance import SENTENCE_END

STOPWORDS = frozenset(
    "a about after again all also an and any are as at be been being but by can could did do does for from had has have "
    "he her his how i if in into is it its just may me more most my no not of on one or our out over she so some than "
    "that the their them then there these they this those to up us very was we were what when where which while who "
    "whom why will with would you your tell give say said does mention company management".split())
WORD = re.compile(r"[a-z0-9%]+")
MIN_CHARS, MAX_CHARS = 40, 400
MAX_ANSWERS = 3
NOT_FOUND = "Not found in source: no sentence in the stored transcripts matches this question."
METHOD = ("Each answer is a sentence quoted word for word from the stored earnings-call transcripts, with its page. "
          "Nothing outside those transcripts is used.")


def content_words(text):
    """The meaningful words of a text, lower-cased, with a plain trailing 's' removed so 'margins' matches 'margin'."""
    words = set()
    for word in WORD.findall(text.lower()):
        if word in STOPWORDS or len(word) < 3 and not word.isdigit():
            continue
        words.add(word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word)
    return words


def answer(question, chunks, limit=MAX_ANSWERS):
    """The best-matching transcript sentences for a question: {"found", "answers", "note"}."""
    wanted = content_words(question)
    if not wanted:
        return {"found": False, "answers": [], "note": "Ask about something specific, such as margin guidance."}
    need = 1 if len(wanted) == 1 else 2        # a single word is too weak to match on, so two must agree
    scored, seen = [], set()
    for order, chunk in enumerate(chunks):
        for sentence in SENTENCE_END.split(chunk["text"]):
            text = sentence.strip()
            key = " ".join(text.lower().split())
            if key in seen or not MIN_CHARS <= len(text) <= MAX_CHARS:
                continue
            overlap = len(wanted & content_words(text))
            if overlap < need:
                continue
            seen.add(key)
            scored.append((-overlap, order, {"quote": text, "page": chunk["page"], "doc": chunk["label"]}))
    scored.sort(key=lambda item: item[:2])
    answers = [item[2] for item in scored[:limit]]
    return {"found": bool(answers), "answers": answers, "note": METHOD if answers else NOT_FOUND}
