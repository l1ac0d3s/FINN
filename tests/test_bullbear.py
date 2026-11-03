"""Bull and bear selection: sides, ordering, verbatim quotes and the empty case."""

from server.bullbear import bull_and_bear, stance

CHUNKS = [
    {"page": 3, "label": "Transcript Q2 FY26", "text": (
        "We won 19 large deals in the quarter with strong growth in every region. "
        "Demand remains robust and we are confident about the year ahead. "
        "Revenue was affected by headwinds and softer volumes across two large clients. "
        "Margins may come under pressure from competitive intensity and slower decisions. "
        "Thanks everyone.")},
]


def test_a_sentence_leans_to_the_side_with_more_words():
    assert stance("We won 19 large deals with strong growth in every region this quarter.")[0] == "bull"
    assert stance("Margins may come under pressure from competitive intensity and slower decisions.")[0] == "bear"


def test_short_fragments_and_questions_are_not_points():
    assert stance("Strong growth.") is None
    assert stance("Is the growth strong enough for next year and beyond the current plan?") is None


def test_points_are_verbatim_with_page_and_source():
    result = bull_and_bear(CHUNKS)
    quotes = [p["quote"] for p in result["bull"]] + [p["quote"] for p in result["bear"]]
    for quote in quotes:
        assert quote in CHUNKS[0]["text"]
    assert result["bull"][0]["page"] == 3
    assert result["bull"][0]["doc"] == "Transcript Q2 FY26"


def test_each_side_is_capped_and_ordered_by_decisiveness():
    many = [{"page": 1, "label": "x", "text": " ".join(
        f"Strong growth and record wins in region {i} with robust demand and higher margins." for i in range(9))}]
    result = bull_and_bear(many)
    assert len(result["bull"]) == 4
    assert result["bear"] == []


def test_no_transcripts_gives_empty_sides_not_an_error():
    result = bull_and_bear([])
    assert result["bull"] == [] and result["bear"] == []
    assert "not analysis" in result["method"] or "selection" in result["method"]
