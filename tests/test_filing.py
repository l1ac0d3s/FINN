"""Results read from an XBRL file: the right periods, units, EBITDA, source choice and cross-check.

The sample below follows the XBRL structure. It is not a copy of a real NSE filing, which is checked on the
first live run.
"""

import io
import zipfile

import pytest

from ingest.filing import financial_rows, parse_xbrl, unpack
from server.results import choose_source, cross_check

SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
            xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
            xmlns:ind-as="http://www.example.test/ind-as">
  <xbrli:context id="Q2">
    <xbrli:entity><xbrli:identifier scheme="nse">INFY</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:startDate>2025-07-01</xbrli:startDate><xbrli:endDate>2025-09-30</xbrli:endDate></xbrli:period>
  </xbrli:context>
  <xbrli:context id="Q2Segment">
    <xbrli:entity><xbrli:identifier scheme="nse">INFY</xbrli:identifier>
      <xbrli:segment><xbrldi:explicitMember dimension="ind-as:SegmentAxis">ind-as:TelecomMember</xbrldi:explicitMember></xbrli:segment>
    </xbrli:entity>
    <xbrli:period><xbrli:startDate>2025-07-01</xbrli:startDate><xbrli:endDate>2025-09-30</xbrli:endDate></xbrli:period>
  </xbrli:context>
  <xbrli:context id="FY">
    <xbrli:entity><xbrli:identifier scheme="nse">INFY</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:startDate>2024-04-01</xbrli:startDate><xbrli:endDate>2025-03-31</xbrli:endDate></xbrli:period>
  </xbrli:context>
  <ind-as:RevenueFromOperations contextRef="Q2" unitRef="INR" decimals="-6">45000000000</ind-as:RevenueFromOperations>
  <ind-as:ProfitLossBeforeTax contextRef="Q2" unitRef="INR" decimals="-6">6000000000</ind-as:ProfitLossBeforeTax>
  <ind-as:ProfitLoss contextRef="Q2" unitRef="INR" decimals="-6">4500000000</ind-as:ProfitLoss>
  <ind-as:FinanceCosts contextRef="Q2" unitRef="INR" decimals="-6">300000000</ind-as:FinanceCosts>
  <ind-as:DepreciationDepletionAndAmortisationExpense contextRef="Q2" unitRef="INR" decimals="-6">500000000</ind-as:DepreciationDepletionAndAmortisationExpense>
  <ind-as:RevenueFromOperations contextRef="Q2Segment" unitRef="INR" decimals="-6">9999000000</ind-as:RevenueFromOperations>
  <ind-as:RevenueFromOperations contextRef="FY" unitRef="INR" decimals="-6">180000000000</ind-as:RevenueFromOperations>
</xbrli:xbrl>
""".encode()


def test_only_three_month_plain_totals_are_read_and_converted_to_crore():
    periods = parse_xbrl(SAMPLE)
    assert list(periods) == ["2025-09-30"]          # the full year and the segment are ignored
    assert periods["2025-09-30"] == {
        "revenue": 4500.0, "pbt": 600.0, "pat": 450.0, "finance_costs": 30.0, "depreciation": 50.0,
    }


def test_ebitda_follows_the_brief_formula():
    rows = financial_rows("INFY", parse_xbrl(SAMPLE), "2026-11-03T06:00:00+00:00")
    assert len(rows) == 1
    row = rows[0]
    assert row["period"] == "Sep 2025"
    assert row["source"] == "filing"
    assert row["ebitda"] == pytest.approx(680.0)    # 600 + 30 + 50
    assert row["revenue"] == pytest.approx(4500.0)


def test_missing_depreciation_leaves_ebitda_empty_rather_than_guessing():
    without_depreciation = SAMPLE.replace(
        b"<ind-as:DepreciationDepletionAndAmortisationExpense contextRef=\"Q2\" unitRef=\"INR\" decimals=\"-6\">500000000</ind-as:DepreciationDepletionAndAmortisationExpense>",
        b"")
    row = financial_rows("INFY", parse_xbrl(without_depreciation), "t")[0]
    assert row["ebitda"] is None
    assert row["revenue"] == pytest.approx(4500.0)


def test_unpack_reads_xml_from_a_zip_and_passes_bare_xml_through():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("infy-results.xml", SAMPLE)
    assert unpack(buffer.getvalue()) == SAMPLE
    assert unpack(SAMPLE) == SAMPLE


def test_filing_figures_win_over_screener_for_the_same_quarter():
    rows = [
        {"period": "Sep 2025", "period_end": "2025-09-30", "revenue": 4400.0, "source": "screener"},
        {"period": "Sep 2025", "period_end": "2025-09-30", "revenue": 4500.0, "source": "filing"},
    ]
    chosen = choose_source(rows)
    assert len(chosen) == 1
    assert chosen[0]["source"] == "filing"


def test_disagreement_above_one_percent_is_flagged():
    rows = [
        {"period": "Sep 2025", "period_end": "2025-09-30", "revenue": 4400.0, "pbt": 600.0, "pat": 450.0,
         "source": "screener"},
        {"period": "Sep 2025", "period_end": "2025-09-30", "revenue": 4500.0, "pbt": 600.0, "pat": 450.0,
         "source": "filing"},
    ]
    flags = cross_check(rows)
    assert [f["metric"] for f in flags] == ["revenue"]     # +2.3% flagged; PBT and PAT agree
    assert flags[0]["diff_pct"] == pytest.approx(2.3)


def test_an_older_database_gains_the_xbrl_column(tmp_path):
    import sqlite3
    from shared.schema import connect

    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE announcements (id TEXT PRIMARY KEY, ticker TEXT, published_at TEXT, subject TEXT, "
                "attachment_url TEXT, category TEXT, tier TEXT, updated_at TEXT)")
    old.commit()
    old.close()

    conn = connect(path)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(announcements)").fetchall()}
    assert "xbrl_url" in columns
