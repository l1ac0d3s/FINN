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
    assert got == {"metric": "revenue", "period": "FY27", "growth_pct": 2.0, "upper": 4.0}


def test_margin_and_capex_guidance_is_listed_with_its_figure():
    margin = statement_from("We expect operating margin of 21% to 22% in FY27.")
    assert margin == {"metric": "margin", "period": "FY27", "growth_pct": 21.0, "upper": 22.0}
    capex = statement_from("We expect capex of 5% of revenue in FY27.")
    assert capex["metric"] == "capex"


def test_margin_guidance_for_a_year_with_no_figures_yet_is_pending():
    result = run_narrative("INFY", [{"id": "c", "page": 2, "label": "x",
                                     "text": "We expect operating margin of 21% in FY27."}], EIGHT_QUARTERS)
    assert result["claims"][0]["metric"] == "margin"
    assert result["claims"][0]["verdict"] == "pending"


def test_reported_and_sequential_sentences_are_not_guidance():
    assert statement_from("Q2 revenues were $5,145 mn, an increase of 1.2% sequentially and 1.5% on YoY.") is None
    assert statement_from("Revenue growth was at 1.9% in constant currency terms.") is None


def test_sentence_is_quoted_verbatim_with_its_page_and_quarter():
    chunks = [{"page": 7, "label": "Transcript Q2 FY26",
               "text": "Margins held steady. We expect revenue growth of 12 percent in Q3 FY26. Thanks everyone."}]
    assert guidance_statements(chunks) == [{
        "metric": "revenue", "period": "Q3 FY26", "growth_pct": 12.0, "upper": None,
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


# ---- Real INFY sentences (public transcript text), as the checker found them. Note the stray spaces
# inside words and the ".in" that come from reading the PDF; the sentences are used exactly as stored.
LABEL = "Announcement under Regulation 30 (LODR)-Earnings Call Transcript 28 Oct"
OCT_CALL = [
    {"id": "a", "document_id": "d-oct", "page": 4, "label": LABEL, "text": (
        "Based on our Q2 performance and revised outlook for rest of the year, our revenue growth guidance is "
        "1% to 2% YoY .in constant currency terms. Our operating margin guidance remains at 20% to 22% for the year. "
        "This deal is expected to c ontribute over 1% revenue growth in the coming financial year.")},
    {"id": "b", "document_id": "d-oct", "page": 25, "label": LABEL, "text": (
        "Our operating margin guidance remains at 20% to 22% for the year. "
        "We delivered strong Q2 FY27 results and H1 of FY27 was in line with plan.")},
]
FY27_SO_FAR = EIGHT_QUARTERS + [
    {"period": "Jun 2026", "period_end": "2026-06-30", "revenue": 48211, "ebitda": 10400},
    {"period": "Sep 2026", "period_end": "2026-09-30", "revenue": 49244, "ebitda": 10600},
]


def test_the_year_of_a_call_is_worked_out_from_its_own_text():
    from server.guidance import call_context
    assert call_context(OCT_CALL) == {"d-oct": (27, "Q2")}


def test_for_the_year_means_the_calls_year_and_the_coming_year_means_the_next():
    found = {(c["metric"], c["period"]) for c in guidance_statements(OCT_CALL)}
    assert ("revenue", "FY27") in found      # "rest of the year" on an Oct 2026 call
    assert ("margin", "FY27") in found       # "for the year"
    assert ("revenue", "FY28") in found      # "the coming financial year"


def test_a_year_end_call_does_not_guess_what_the_year_means():
    chunks = [{"id": "q", "document_id": "d-apr", "page": 3, "label": "Apr call",
               "text": "We closed Q4 FY26 and the full year FY26 on plan. Our margin guidance is 20% to 22% for the year."}]
    assert guidance_statements(chunks)[0]["period"] is None


def test_constant_currency_guidance_is_never_compared_with_rupee_revenue():
    result = run_narrative("INFY", OCT_CALL, FY27_SO_FAR)
    revenue = [c for c in result["claims"] if c["metric"] == "revenue" and c["period"] == "FY27"][0]
    assert revenue["verdict"] == "not comparable"
    assert revenue["actual_yoy_pct"] is None


def test_margin_guidance_for_a_year_in_progress_uses_the_quarters_so_far():
    result = run_narrative("INFY", OCT_CALL, FY27_SO_FAR)
    margin = [c for c in result["claims"] if c["metric"] == "margin"][0]
    assert margin["verdict"] == "on track"
    assert margin["actual_yoy_pct"] == pytest.approx(21.5, abs=0.1)   # 21,000 / 97,455
    assert margin["promised_upper_pct"] == 22.0


def test_a_completed_year_gives_met_or_missed_for_margin():
    quarters = [
        {"period": "Jun 2025", "period_end": "2025-06-30", "revenue": 100, "ebitda": 19},
        {"period": "Sep 2025", "period_end": "2025-09-30", "revenue": 100, "ebitda": 19},
        {"period": "Dec 2025", "period_end": "2025-12-31", "revenue": 100, "ebitda": 19},
        {"period": "Mar 2026", "period_end": "2026-03-31", "revenue": 100, "ebitda": 19},
    ]
    claim = {"metric": "margin", "growth_pct": 20.0, "period": "FY26"}
    assert verdict_for(claim, quarters) == (19.0, "missed")


def test_the_same_sentence_on_two_pages_of_one_call_is_one_row():
    result = run_narrative("INFY", OCT_CALL, FY27_SO_FAR)
    margin_rows = [c for c in result["claims"] if c["quote"].startswith("Our operating margin guidance")]
    assert len(margin_rows) == 1


def test_a_sentence_about_maintaining_margins_is_not_guidance():
    assert statement_from("In FY26 we have been able to maintain the margins at 21% despite investing in business.") is None


def test_the_four_quarter_table_carries_margin_and_the_year_each_quarter_belongs_to():
    quarters = run_narrative("INFY", OCT_CALL, FY27_SO_FAR)["quarters"]
    assert [q["fy"] for q in quarters] == ["FY26", "FY26", "FY27", "FY27"]
    assert quarters[0]["margin_pct"] is None                      # no operating profit stored for that quarter
    assert quarters[2]["margin_pct"] == pytest.approx(21.6, abs=0.1)   # 10,400 / 48,211


def test_the_guidance_in_force_is_listed_for_its_fiscal_year():
    guidance = run_narrative("INFY", OCT_CALL, FY27_SO_FAR)["guidance_by_year"]
    assert "operating margin 20.0% to 22.0%" in guidance["FY27"]
    assert "revenue growth 1.0% to 2.0% (constant currency)" in guidance["FY27"]


# ---- Sentences from the live check that were wrongly treated as promises (public transcript text).
def test_reported_results_in_other_words_are_not_guidance():
    assert statement_from("And lastly, on the overall top line growth guidance, we had suggested for high "
                          "single-digit growth versus this quarter, we have done almost 11% kind of a growth.") is None
    assert statement_from("During the 3rd Quarter of FY 2026, we recorded sales of Rs.1,54,691 million, registering "
                          "a growth of 15.1% vis- a -vis Q3 FY 2025.") is None


def test_an_analysts_question_is_not_a_statement_by_management():
    assert statement_from("How do we think about the margin commitment we had made around exiting FY27, "
                          "at 25% plus EBIT margin range?") is None


def test_a_bare_fiscal_year_does_not_make_a_result_sound_like_a_promise():
    assert statement_from("Nitin, we are exiting FY26 at a four-year high on annual margins at 25%.") is None


def test_fiscal_years_written_in_full_are_understood():
    from server.guidance import period_label
    assert period_label("In Q3 FY 2026 we expect margin of 21%.") == "Q3 FY26"
    assert period_label("For FY2027 we expect growth.") == "FY27"


def test_a_statement_about_a_year_that_has_already_ended_is_a_result_not_a_promise():
    call = ("We reported Q2 FY27 results today. H1 of FY27 went to plan. Q2 FY27 demand was strong. "
            "We expect operating margin of 21% in FY25. We expect operating margin of 22% in FY28.")
    found = guidance_statements([{"id": "a", "document_id": "d", "page": 1, "label": "call", "text": call}])
    assert [c["period"] for c in found] == ["FY28"]


def test_a_call_with_too_few_references_is_not_used_to_discard_statements():
    one_reference = "We expect revenue growth of 12 percent in Q3 FY26."
    found = guidance_statements([{"id": "a", "document_id": "d", "page": 1, "label": "call", "text": one_reference}])
    assert len(found) == 1       # a single mention is not enough to know which quarter the call is about
