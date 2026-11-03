"""Management backgrounds entered by hand, each with a source link.

Use this when a company's appointment filing has no profile. Add an entry to ingest/manual/management.json:

    {
      "ticker": "TRENT",
      "date": "2026-10-29",           the date of the management-change filing, YYYY-MM-DD
      "name": "Full name",
      "role": "Chief Financial Officer",
      "profile": "One or two factual sentences, from the source.",
      "source_url": "https://...",    where the background was read, starting with https://
      "entered_by": "your initials"
    }

An entry is used only if a management-change filing for that ticker exists on that date. Entries are shown
on the card labelled "entered by hand", with the source link, never as the exchange filing's own text.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from shared.schema import upsert

SOURCE = Path(__file__).parent / "manual" / "management.json"
REQUIRED = ("ticker", "date", "name", "profile", "source_url")


def load_entries(path=SOURCE):
    """The valid entries in the file. Entries missing a required field, or without an https source, are skipped."""
    if not Path(path).exists():
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = data.get("entries", []) if isinstance(data, dict) else []
    return [e for e in entries
            if isinstance(e, dict) and all(e.get(k) for k in REQUIRED)
            and str(e["source_url"]).startswith("https://")]


def store_manual_bios(conn, path=SOURCE):
    """Attach each valid entry to its management-change filing. Returns the number stored."""
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    stored = 0
    for entry in load_entries(path):
        match = conn.execute(
            "SELECT id, published_at FROM announcements WHERE ticker = ? AND category = 'management_change' "
            "AND substr(published_at, 1, 10) = ? ORDER BY published_at LIMIT 1",
            (entry["ticker"].upper(), entry["date"]),
        ).fetchone()
        if match is None:
            continue
        upsert(conn, "management_bios", {
            "id": match["id"],
            "ticker": entry["ticker"].upper(),
            "name": entry["name"],
            "role": entry.get("role"),
            "bio": entry["profile"],
            "source_url": entry["source_url"],
            "origin": "manual",
            "published_at": match["published_at"],
            "updated_at": stamp,
        })
        stored += 1
    return stored
