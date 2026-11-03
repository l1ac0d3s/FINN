"""Guidance extraction without a model, and the fiscal-year and no-model paths of the narrative check."""

import pytest

from server.guidance import guidance_statements, statement_from
from server.pull import run_narrative, verdict_for

EIGHT_QUARTERS = [
    {"period": "Jun 2024", "period_end": "2024-06-30", "revenue": 100},
    {"period": "Sep 2024", "period_end": "2024-09-30", "revenue": 110},
    {"period": "Dec 2024", "period_end": "2024-12-31", "revenue": 120},
    {"period": "Mar 2025", "period_end": "2025-03-31", "revenue": 130},
    {"period": "Jun 2025", "period_end": "2025-06-30", "revenue": 120},
    {"period": "Sep 2025", "period_end": "2025-09-30", "revenue": 132},
    {"period": "Dec 2025", "period_end": "2025-12-31", "revenue": 144},
    {"period": "Mar 2026", "period_end": "2026-03-31", "revenue": 150},
]


def test_forward_range_takes_the_lower_end_and_the_fiscal_year():
    got = statement_from("For FY27 we expect revenue growth in constant currency of 2% to 4%.")
    assert got == {"metric": "revenue", "period": "FY27", "growth_pct": 2.0}


def test_reported_and_sequential_sentences_are_not_guidance():
    assert statement_from("Q2 revenues were $5,145 mn, an increase of 1.2% sequentially and 1.5% on YoY.") is None
    assert statement_from("Revenue growth was at 1.9% in constant currency terms.") is None


def test_sentence_is_quoted_verbatim_with_its_page_and_quarter():
    chunks = [{"page": 7, "label": "Transcript Q2 FY26",
               "text": "Margins held steady. We expect revenue growth of 12 percent in Q3 FY26. Thanks everyone."}]
    assert guidance_statements(chunks) == [{
        "metric": "revenue", "period": "Q3 FY26", "growth_pct": 12.0,
        "quote": "We expect revenue growth of 12 percent in Q3 FY26.",
        "page": 7, "label": "Transcript Q2 FY26",
    }]


def test_fiscal_year_verdict_sums_four_quarters_each_way():
    # FY26 = 2025-06..2026-03 = 546; FY25 = 2024-06..2025-03 = 460; growth 18.7%
    assert verdict_for({"metric": "revenue", "growth_pct": 15, "period": "FY26"}, EIGHT_QUARTERS) == (18.7, "met")
    assert verdict_for({"metric": "revenue", "growth_pct": 20, "period": "FY26"}, EIGHT_QUARTERS) == (18.7, "nearly met")


def test_future_fiscal_year_is_pending():
    assert verdict_for({"metric": "revenue", "growth_pct": 3, "period": "FY27"}, EIGHT_QUARTERS) == (None, "pending")


def test_narrative_runs_without_any_model():
    chunks = [{"id": "c1", "page": 4, "label": "Transcript Q2 FY26",
               "text": "We expect revenue growth of 12 percent in Q3 FY26."}]
    result = run_narrative("INFY", chunks, EIGHT_QUARTERS)
    assert result["dropped"] == 0
    claim = result["claims"][0]
    assert claim["doc"] == "Transcript Q2 FY26"
    assert claim["verdict"] == "met"          # Dec 2025: 144 vs 120 = +20%, promised 12%
    assert claim["actual_yoy_pct"] == pytest.approx(20.0)


def test_narrative_with_no_statements_says_not_found():
    result = run_narrative("INFY", [{"id": "c", "page": 1, "label": "x", "text": "Nothing about numbers here."}],
                           EIGHT_QUARTERS)
    assert result["claims"] == []
    assert "no forward-looking" in result["note"]
