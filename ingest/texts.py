"""Annual reports and transcripts: pick the documents, download the PDFs, extract text, split into chunks.

Chunks break only at sentence boundaries, so a sentence is never split across
two chunks. That lets the pull side check each quoted sentence against the source.
"""

import io
import logging
import re

from pypdf import PdfReader

# pypdf logs a warning for every embedded font on every page. The text is still
# extracted, so these messages are noise here. Errors still show.
logging.getLogger("pypdf").setLevel(logging.ERROR)

HEADERS = {"User-Agent": "Mozilla/5.0 (FINN research prototype)"}
TRANSCRIPTS_PER_TICKER = 4      # the last four quarters' calls
ANNUAL_REPORTS_PER_TICKER = 0   # off for now: the pull side reads transcripts only. Set to 1 when pull uses reports.
MAX_PAGES = 300                 # caps very long annual reports
MAX_CHUNK_CHARS = 1200
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def select_documents(rows):
    """Newest transcripts and annual reports, capped per type.

    rows are dicts with id, url, doc_type and period. Screener periods are
    labels such as '2025' or 'FY2025', so the newest is the largest string.
    """
    def newest(doc_type, limit):
        matches = [r for r in rows if r["doc_type"] == doc_type]
        matches.sort(key=lambda r: r["period"] or "", reverse=True)
        return matches[:limit]

    return newest("transcript", TRANSCRIPTS_PER_TICKER) + newest("annual_report", ANNUAL_REPORTS_PER_TICKER)


def download_pdf(session, url):
    resp = session.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    if not resp.content.startswith(b"%PDF"):
        raise ValueError("link did not return a PDF")
    return resp.content


def extract_pages(pdf_bytes):
    """(page number, text) for each non-empty page, pages counted from 1."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for number, page in enumerate(reader.pages[:MAX_PAGES], start=1):
        text = re.sub(r"\s+", " ", page.extract_text() or "").strip()
        if text:
            pages.append((number, text))
    return pages


def chunk_pages(pages, max_chars=MAX_CHUNK_CHARS):
    """(page number, chunk text) pairs. A single long sentence stays whole."""
    chunks = []
    for number, text in pages:
        current = ""
        for sentence in SENTENCE_END.split(text):
            if current and len(current) + len(sentence) + 1 > max_chars:
                chunks.append((number, current))
                current = sentence
            else:
                current = f"{current} {sentence}".strip()
        if current:
            chunks.append((number, current))
    return chunks
