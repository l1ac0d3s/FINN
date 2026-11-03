"""Ask: answers are quoted transcript sentences with pages, or an honest 'not found in source'."""

from server.ask import answer, content_words

CHUNKS = [
    {"page": 4, "label": "Transcript 28 Oct", "text": (
        "Our operating margin guidance remains at 20% to 22% for the year. "
        "Demand remains robust across financial services and manufacturing clients. "
        "We won 19 large deals with a total contract value of 5.2 billion dollars in the quarter.")},
    {"page": 9, "label": "Transcript 28 Oct", "text": (
        "Attrition declined to 14 percent over the last twelve months across the company. "
        "Short.")},
]


def test_plural_and_singular_words_match():
    assert content_words("margins") == content_words("margin")


def test_a_question_gets_the_matching_sentence_with_its_page():
    result = answer("What is the margin guidance?", CHUNKS)
    assert result["found"] is True
    assert result["answers"][0]["quote"].startswith("Our operating margin guidance")
    assert result["answers"][0]["page"] == 4


def test_a_question_the_transcripts_do_not_cover_is_not_found_and_nothing_is_invented():
    result = answer("What is the CEO's favourite holiday destination?", CHUNKS)
    assert result["found"] is False
    assert result["answers"] == []
    assert "Not found in source" in result["note"]


def test_one_shared_word_is_not_enough_to_answer_a_longer_question():
    assert answer("What did they say about the margin of the nuclear programme?", CHUNKS)["found"] is False


def test_a_question_with_no_content_words_asks_for_something_specific():
    result = answer("what is the", CHUNKS)
    assert result["found"] is False and "specific" in result["note"]


def test_every_answer_is_word_for_word_from_the_source():
    result = answer("deals contract value quarter", CHUNKS)
    sources = " ".join(c["text"] for c in CHUNKS)
    assert result["found"] and all(a["quote"] in sources for a in result["answers"])
