from ingest.texts import chunk_pages, select_documents


def test_chunks_never_split_a_sentence():
    sentence_a = "Revenue growth guidance is twelve percent for the year."
    sentence_b = "We expect margins to hold steady."
    pages = [(3, f"{sentence_a} {sentence_b}")]
    chunks = chunk_pages(pages, max_chars=60)
    assert [c[1] for c in chunks] == [sentence_a, sentence_b]
    assert all(c[0] == 3 for c in chunks)


def test_long_sentence_stays_whole():
    long_sentence = "x" * 500 + "."
    chunks = chunk_pages([(1, long_sentence)], max_chars=100)
    assert chunks == [(1, long_sentence)]


def test_select_documents_takes_newest_transcripts_and_one_report():
    rows = [
        {"id": "t1", "url": "u", "doc_type": "transcript", "period": "2024"},
        {"id": "t2", "url": "u", "doc_type": "transcript", "period": "2026"},
        {"id": "t3", "url": "u", "doc_type": "transcript", "period": "2025"},
        {"id": "t4", "url": "u", "doc_type": "transcript", "period": "2023"},
        {"id": "t5", "url": "u", "doc_type": "transcript", "period": "2022"},
        {"id": "a1", "url": "u", "doc_type": "annual_report", "period": "FY2024"},
        {"id": "a2", "url": "u", "doc_type": "annual_report", "period": "FY2025"},
        {"id": "p1", "url": "u", "doc_type": "investor_presentation", "period": "2026"},
    ]
    chosen = [d["id"] for d in select_documents(rows)]
    assert chosen == ["t2", "t3", "t1", "t4"]  # annual reports are off, see ANNUAL_REPORTS_PER_TICKER
