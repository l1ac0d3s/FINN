"""Hand-entered management backgrounds: validation, matching to a filing, and the label they carry."""

import json

from ingest.manual_management import load_entries, store_manual_bios
from shared.schema import connect, upsert

GOOD = {"ticker": "TRENT", "date": "2026-10-29", "name": "A. Sharma", "role": "Chief Financial Officer",
        "profile": "Chartered accountant; formerly finance head at a retailer.",
        "source_url": "https://example.com/profile", "entered_by": "ab"}


def write(tmp_path, entries):
    path = tmp_path / "management.json"
    path.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return path


def test_entries_without_a_source_link_or_a_required_field_are_skipped(tmp_path):
    path = write(tmp_path, [
        GOOD,
        {**GOOD, "source_url": "http://insecure.example"},
        {**GOOD, "profile": ""},
        {k: v for k, v in GOOD.items() if k != "name"},
    ])
    assert len(load_entries(path)) == 1


def test_an_entry_attaches_to_the_filing_on_its_date_and_is_marked_by_hand(tmp_path):
    conn = connect(tmp_path / "ingest.db")
    upsert(conn, "announcements", {
        "id": "nse|77", "ticker": "TRENT", "published_at": "2026-10-29T10:30:00+00:00",
        "subject": "Appointment of Mr. A. Sharma as CFO", "attachment_url": None, "xbrl_url": None,
        "category": "management_change", "tier": "high", "updated_at": "2026-10-29T11:00:00+00:00"})
    conn.commit()
    assert store_manual_bios(conn, write(tmp_path, [GOOD])) == 1
    row = conn.execute("SELECT * FROM management_bios WHERE id = 'nse|77'").fetchone()
    assert row["origin"] == "manual"
    assert row["bio"].startswith("Chartered accountant")


def test_an_entry_with_no_matching_filing_is_not_stored(tmp_path):
    conn = connect(tmp_path / "ingest.db")
    assert store_manual_bios(conn, write(tmp_path, [GOOD])) == 0


def test_the_shipped_file_is_valid_and_empty():
    assert load_entries() == []
