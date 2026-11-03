"""Finding the XBRL link in an NSE announcement, whatever its field is called."""

from ingest.announcements import find_xbrl, normalise_nse


def test_finds_a_field_whose_name_contains_xbrl():
    item = {"desc": "Outcome of Board Meeting", "xbrl": "https://nsearchives.example/x/q2.xml"}
    assert find_xbrl(item) == "https://nsearchives.example/x/q2.xml"


def test_finds_a_link_ending_in_xml_under_any_field_name():
    item = {"desc": "Financial Results", "attchmntFile": "https://nsearchives.example/a.pdf",
            "other": "https://nsearchives.example/data/q2-results.xml"}
    assert find_xbrl(item) == "https://nsearchives.example/data/q2-results.xml"


def test_no_link_gives_none_and_the_pdf_is_not_mistaken_for_xbrl():
    assert find_xbrl({"desc": "Press release", "attchmntFile": "https://nsearchives.example/a.pdf"}) is None


def test_normalise_nse_stores_the_xbrl_link():
    row = normalise_nse({"desc": "Financial Results", "seq_id": "1", "an_dt": "29-Oct-2026 16:00:00",
                         "xbrl": "https://nsearchives.example/q2.xml"}, "INFY")
    assert row["xbrl_url"] == "https://nsearchives.example/q2.xml"
