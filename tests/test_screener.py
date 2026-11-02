"""Screener parser tests on a saved sample. The sample imitates the layout as I
understand it, so these tests show the parser works on that layout, not that it
matches the live site."""

from pathlib import Path

import pytest

from ingest.screener import parse_documents, parse_number, parse_quarters, period_end

SAMPLE = (Path(__file__).parent / "fixtures" / "screener_sample.html").read_text()
BASE = "https://www.screener.in/company/INFY/consolidated/"


def test_parse_number_handles_commas_percent_and_dash():
    assert parse_number("1,234.5") == 1234.5
    assert parse_number("20%") == 20.0
    assert parse_number("-") is None
    assert parse_number("") is None


def test_period_end_is_last_day_of_month():
    assert period_end("Sep 2025").isoformat() == "2025-09-30"
    assert period_end("Mar 2025").isoformat() == "2025-03-31"


def test_quarters_are_parsed_oldest_first():
    quarters = parse_quarters(SAMPLE)
    assert [q["period"] for q in quarters] == ["Sep 2024", "Dec 2024", "Mar 2025", "Jun 2025", "Sep 2025"]
    latest = quarters[-1]
    assert latest["revenue"] == 1320
    assert latest["ebitda"] == 264
    assert latest["pbt"] == 190


def test_table_without_period_headers_raises_with_detail():
    html = '<section id="quarters"><table><tr><th></th><th>Quarterly</th></tr><tr><td>Sales</td><td>1</td></tr></table></section>'
    with pytest.raises(ValueError, match="no period headers"):
        parse_quarters(html)


def test_empty_first_row_does_not_hide_the_header():
    # PAGEIND's table starts with an empty row before the period headers.
    html = SAMPLE.replace("<table>", "<table><tr></tr>", 1)
    quarters = parse_quarters(html)
    assert quarters[-1]["period"] == "Sep 2025"
    assert quarters[-1]["revenue"] == 1320


def test_blank_cell_becomes_none_not_zero():
    latest = parse_quarters(SAMPLE)[-1]
    assert latest["pat"] is None


def test_documents_are_classified_resolved_and_deduplicated():
    docs = parse_documents(SAMPLE, BASE)
    types = [d["doc_type"] for d in docs]
    assert types == ["annual_report", "transcript", "investor_presentation"]
    assert docs[0]["url"] == "https://www.screener.in/company/INFY/annual-report/2025.pdf"
    assert docs[0]["period"] == "FY2025"
    assert docs[1]["period"] == "2025"
