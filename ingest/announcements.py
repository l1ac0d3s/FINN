"""Exchange announcements from NSE, with BSE as the fallback (not yet implemented).

NSE needs a browser-like session: it sets cookies on the homepage, and the API
rejects requests without them. The endpoint and field names below are from
memory and are NOT verified. Check them on the first live run and adjust the
field mapping in normalise_nse() if needed.
"""

import hashlib
import time
from datetime import datetime, timedelta, timezone

from ingest.classify import classify_rules, classify_with_llm, tier_for
from ingest.config import HAIKU_MODEL, REQUEST_DELAY_S

NSE_HOME = "https://www.nseindia.com"
NSE_API = NSE_HOME + "/api/corporate-announcements"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (FINN research prototype)",
    "Accept": "application/json",
    "Referer": NSE_HOME + "/",
}
TIME_FORMATS = ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M")
IST_OFFSET = timedelta(hours=5, minutes=30)


def parse_nse_time(raw):
    """Parse NSE's timestamp into UTC ISO 8601. NSE publishes IST, so subtract 5:30."""
    for fmt in TIME_FORMATS:
        try:
            wall = datetime.strptime(raw, fmt)
        except (TypeError, ValueError):
            continue
        return (wall - IST_OFFSET).replace(tzinfo=timezone.utc).isoformat(timespec="seconds")
    raise ValueError(f"unrecognised NSE timestamp: {raw!r}")


def find_xbrl(item):
    """The XBRL file link for an announcement, whatever NSE calls the field.

    Looks first for a field whose name contains 'xbrl', then for any web link ending in .xml or .zip.
    Returns None when there is none. Field names are unverified until the first live run.
    """
    for key, value in item.items():
        if "xbrl" in str(key).lower() and isinstance(value, str) and value.startswith("http"):
            return value
    for value in item.values():
        if isinstance(value, str) and value.startswith("http") and value.lower().endswith((".xml", ".zip")):
            return value
    return None


def normalise_nse(item, symbol):
    """Map one NSE record to our announcement fields. Field names are unverified."""
    subject = (item.get("desc") or item.get("subject") or "").strip()
    seq = item.get("seq_id") or item.get("seqId")
    raw_time = item.get("an_dt") or item.get("exchdisstime")
    attachment = item.get("attchmntFile") or item.get("attachment")
    key = seq or hashlib.sha1(f"{symbol}|{raw_time}|{subject}".encode()).hexdigest()
    return {
        "id": f"nse|{key}",
        "ticker": symbol,
        "published_at": parse_nse_time(raw_time),
        "subject": subject,
        "attachment_url": attachment,
        "xbrl_url": find_xbrl(item),
    }


def fetch_nse(session, symbol):
    """Raw NSE records for one symbol. Primes the session cookies first."""
    session.get(NSE_HOME, headers=HEADERS, timeout=15)
    time.sleep(REQUEST_DELAY_S)
    resp = session.get(
        NSE_API, params={"index": "equities", "symbol": symbol},
        headers=HEADERS, timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def categorise(subject, conn, llm_client=None):
    """Return (category, tier) for a subject, using rules, then cache, then Haiku.

    A subject no rule or model can place is kept as a low-tier item, so it stays
    visible under Routine rather than disappearing.
    """
    key = hashlib.sha1(subject.lower().encode()).hexdigest()
    category = classify_rules(subject)
    if category is None:
        row = conn.execute(
            "SELECT category FROM classify_cache WHERE subject_hash = ?", (key,)
        ).fetchone()
        category = row["category"] if row else None
    if category is None and llm_client is not None:
        category = classify_with_llm(subject, llm_client, HAIKU_MODEL)
        conn.execute(
            "INSERT OR REPLACE INTO classify_cache (subject_hash, category, updated_at) "
            "VALUES (?, ?, ?)",
            (key, category, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
    if category is None:
        return "press_release", "low"
    return category, tier_for(category, subject)
