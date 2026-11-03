"""Plain-English notes on promise verdicts, written on the laptop by a small model.

The model is given one verdict and its numbers, and writes one sentence. The sentence is kept only if
it is short, on one line, and uses no number that was not in the prompt. Anything else is discarded
and tried again on the next run. Each note is cached by claim id, so a verdict is never sent twice.

The hosted app makes no model calls. It only shows the notes stored here.

    python -m ingest.notes --check      # one test call, to confirm the key and model access
"""

import argparse
import os
import re
from datetime import datetime, timezone

from ingest.config import HAIKU_MODEL
from server.pull import GRADED, run_narrative
from server.risk import achievement_pct
from shared.schema import upsert

NUMBER = re.compile(r"\d+(?:\.\d+)?")
MAX_WORDS = 40

SYSTEM = (
    "You explain one verdict on a company's promise to an investment analyst. "
    "Write one plain sentence of at most 30 words. Use only the numbers given to you, and do not "
    "introduce any other number. Reply with the sentence only."
)


def build_prompt(ticker, claim):
    achieved = achievement_pct(claim["promised_growth_pct"], claim["actual_yoy_pct"])
    return (
        f"Company: {ticker}. Management said: \"{claim['quote']}\" "
        f"Period: {claim.get('period') or 'not stated'}. "
        f"Promised growth: {claim['promised_growth_pct']}%. "
        f"Reported year-on-year growth: {claim['actual_yoy_pct']}%. "
        f"Share of the promise delivered: {round(achieved, 1)}%. "
        f"Verdict: {claim['verdict']}."
    )


def accept_note(prompt, reply):
    """The note if it passes the checks, otherwise None."""
    text = (reply or "").strip()
    if not text or "\n" in text or len(text.split()) > MAX_WORDS:
        return None
    allowed = {float(n) for n in NUMBER.findall(prompt)}   # compare by value: "12" and "12.0" are the same
    if any(float(n) not in allowed for n in NUMBER.findall(text)):
        return None
    return text


def ask_model(client, prompt):
    message = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=80,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def transcript_chunks(conn, ticker):
    return [dict(r) for r in conn.execute(
        "SELECT c.id, c.page, c.text, d.label FROM chunks c "
        "JOIN documents d ON d.id = c.document_id "
        "WHERE c.ticker = ? AND c.doc_type = 'transcript'",
        (ticker,),
    ).fetchall()]


def quarter_rows(conn, ticker):
    return [dict(r) for r in conn.execute(
        "SELECT period, period_end, revenue FROM financials_q WHERE ticker = ? ORDER BY period_end",
        (ticker,),
    ).fetchall()]


def store_claim_notes(conn, ticker, client):
    """Write notes for graded verdicts that have none yet. Returns (written, rejected), or None without a client."""
    if client is None:
        return None
    chunks = transcript_chunks(conn, ticker)
    if not chunks:
        return 0, 0
    result = run_narrative(ticker, chunks, quarter_rows(conn, ticker))
    have = {r["id"] for r in conn.execute("SELECT id FROM claim_notes WHERE ticker = ?", (ticker,)).fetchall()}
    written = rejected = 0
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for claim in result["claims"]:
        if claim["verdict"] not in GRADED or claim["id"] in have:
            continue
        prompt = build_prompt(ticker, claim)
        note = accept_note(prompt, ask_model(client, prompt))
        if note is None:
            rejected += 1
            continue
        upsert(conn, "claim_notes", {"id": claim["id"], "ticker": ticker, "text": note, "updated_at": stamp})
        written += 1
    return written, rejected


def check_key():
    """One real call to the model, on a subject whose label is known. Prints what came back."""
    import anthropic
    from ingest.classify import classify_with_llm

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set. Set it in this window, then run the check again.")
        return 1
    label = classify_with_llm(
        "Resignation of Mr. A B as Chief Financial Officer", anthropic.Anthropic(), HAIKU_MODEL)
    print(f"model {HAIKU_MODEL} returned: {label}")
    print("OK" if label == "management_change" else "Unexpected label. Check the model name and the key's access.")
    return 0 if label == "management_change" else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="make one test call to the model")
    args = parser.parse_args()
    if args.check:
        raise SystemExit(check_key())
    parser.print_help()


if __name__ == "__main__":
    main()
