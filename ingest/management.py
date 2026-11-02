"""Management-change profiles, read from the appointment filing itself.

Appointment filings often include a short profile of the person (education, past roles).
We keep the profile only when it is in the filing text, and store the filing link with it.
If a filing has no profile, the card says so. No web search and no social-media scraping is done.
"""

import re
import time
from datetime import datetime, timezone

from ingest.config import REQUEST_DELAY_S
from ingest.texts import download_pdf, extract_pages
from shared.schema import upsert

PROFILE_HEADING = re.compile(
    r"(?:brief\s+profile|profile\s+of\s+(?:the\s+)?(?:appointee|director|person|incoming\s+\w+)"
    r"|details\s+of\s+(?:the\s+)?(?:appointee|director)|background)\s*[:\-–.]?\s*",
    re.I,
)
NAME = re.compile(r"(?:Mr\.?|Ms\.?|Mrs\.?|Dr\.?|Shri|Smt\.?)\s+([A-Z][A-Za-z.]*(?:\s+[A-Z][A-Za-z.]*){0,4})")
ROLE = re.compile(
    r"\bas\s+((?:Chief|Managing|Whole[- ]?time|Executive|Non[- ]?Executive|Independent|Additional|Joint|"
    r"Company|Chairman|Director|Manager|Head)[^.;,]{0,80})",
    re.I,
)
MIN_BIO_CHARS = 60
MAX_BIO_CHARS = 700


def parse_filing(subject, text):
    """Name, role and profile from one appointment filing. A part the filing does not contain is None."""
    name = NAME.search(f"{subject}. {text}")
    role = ROLE.search(f"{subject}. {text}")
    bio = None
    heading = PROFILE_HEADING.search(text)
    if heading:
        body = text[heading.end():heading.end() + MAX_BIO_CHARS]
        cut = body.rfind(".")
        if cut >= MIN_BIO_CHARS:
            body = body[:cut + 1]
        bio = body.strip() if len(body.strip()) >= MIN_BIO_CHARS else None
    return {
        "name": name.group(1).strip() if name else None,
        "role": role.group(1).strip() if role else None,
        "bio": bio,
    }


def store_management_bios(conn, ticker, session):
    """Read the filing for each management-change announcement not yet read. Returns the number read.

    A filing that cannot be downloaded is not stored, so the next run tries it again.
    """
    rows = conn.execute(
        "SELECT id, subject, attachment_url, published_at FROM announcements "
        "WHERE ticker = ? AND category = 'management_change' AND attachment_url IS NOT NULL "
        "AND id NOT IN (SELECT id FROM management_bios)",
        (ticker,),
    ).fetchall()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    read = 0
    for row in rows:
        time.sleep(REQUEST_DELAY_S)
        try:
            text = " ".join(page_text for _, page_text in extract_pages(download_pdf(session, row["attachment_url"])))
        except Exception:
            continue
        fields = parse_filing(row["subject"], text)
        upsert(conn, "management_bios", {
            "id": row["id"],
            "ticker": ticker,
            "name": fields["name"],
            "role": fields["role"],
            "bio": fields["bio"],
            "source_url": row["attachment_url"],
            "published_at": row["published_at"],
            "updated_at": stamp,
        })
        read += 1
    return read
