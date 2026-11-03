"""The checks on a model's note: one line, short, and no number that was not in the prompt."""

from ingest.notes import accept_note, build_prompt

CLAIM = {
    "quote": "We expect revenue growth of 12 percent in Q3 FY26.",
    "period": "Dec 2025", "promised_growth_pct": 12.0, "actual_yoy_pct": 9.1, "verdict": "partly met",
}


def test_note_using_only_given_numbers_is_accepted():
    prompt = build_prompt("INFY", CLAIM)
    reply = "Revenue grew 9.1% against a promised 12%, so the company delivered about three-quarters of its promise."
    assert accept_note(prompt, reply) == reply


def test_note_with_an_invented_number_is_rejected():
    prompt = build_prompt("INFY", CLAIM)
    assert accept_note(prompt, "Revenue grew 15% against a promise of 12%.") is None


def test_multi_line_or_long_replies_are_rejected():
    prompt = build_prompt("INFY", CLAIM)
    assert accept_note(prompt, "First line.\nSecond line.") is None
    assert accept_note(prompt, " ".join(["word"] * 60)) is None
    assert accept_note(prompt, "") is None
    assert accept_note(prompt, None) is None


def test_numbers_are_compared_by_value_not_spelling():
    prompt = build_prompt("INFY", CLAIM)              # the prompt says 12.0%
    assert accept_note(prompt, "The promise was for 12% growth.") is not None


class _Block:
    def __init__(self, text):
        self.text = text


class _Message:
    def __init__(self, text):
        self.content = [_Block(text)]


class _Messages:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _Message(self.reply)


class _Client:
    def __init__(self, reply):
        self.messages = _Messages(reply)


def test_store_claim_notes_writes_each_note_once(tmp_path):
    from ingest.notes import store_claim_notes
    from shared.schema import connect

    conn = connect(tmp_path / "ingest.db")
    stamp = "2026-11-01T06:00:00+00:00"
    conn.execute("INSERT INTO documents (id, ticker, doc_type, period, url, label, updated_at) "
                 "VALUES ('d1', 'INFY', 'transcript', '2026', 'https://example.com/t.pdf', 'Transcript Q2 FY26', ?)",
                 (stamp,))
    conn.execute("INSERT INTO chunks (id, document_id, ticker, doc_type, page, text, updated_at) "
                 "VALUES ('d1|4|0', 'd1', 'INFY', 'transcript', 4, ?, ?)",
                 ("We expect revenue growth of 12 percent in Q3 FY26. Margins should hold steady this year.", stamp))
    quarters = [("Sep 2024", "2024-09-30", 1000), ("Dec 2024", "2024-12-31", 1100),
                ("Mar 2025", "2025-03-31", 1050), ("Jun 2025", "2025-06-30", 1200),
                ("Sep 2025", "2025-09-30", 1320), ("Dec 2025", "2025-12-31", 1200)]
    for period, end, revenue in quarters:
        conn.execute("INSERT INTO financials_q (id, ticker, period, period_end, revenue, source, updated_at) "
                     "VALUES (?, 'INFY', ?, ?, ?, 'screener', ?)", (f"INFY|{end}", period, end, revenue, stamp))
    conn.commit()

    client = _Client("Revenue grew 9.1% against a promise of 12%, so most of the promise was delivered.")
    assert store_claim_notes(conn, "INFY", client) == (1, 0)
    assert store_claim_notes(conn, "INFY", client) == (0, 0)   # already written, so no second call
    assert len(client.messages.calls) == 1
    assert conn.execute("SELECT text FROM claim_notes").fetchone()["text"].startswith("Revenue grew 9.1%")


def test_store_claim_notes_without_a_key_does_nothing(tmp_path):
    from ingest.notes import store_claim_notes
    from shared.schema import connect

    conn = connect(tmp_path / "ingest.db")
    assert store_claim_notes(conn, "INFY", None) is None


def test_prompt_carries_the_verdict_and_the_numbers():
    prompt = build_prompt("INFY", CLAIM)
    assert "9.1%" in prompt and "12.0%" in prompt and "partly met" in prompt
