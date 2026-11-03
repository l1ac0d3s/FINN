"""Narrative-vs-numbers logic: grounding, period mapping, verdicts, and the notes attached to them."""

import importlib
from datetime import datetime, timedelta, timezone

import pytest

from server.pull import claim_id, ground, quarter_end, run_narrative, verdict_for, with_notes

PASSAGE = {
    "label": "Transcript Q2 FY26",
    "page": 4,
    "text": "We expect revenue growth of 12 percent in Q3 FY26. Margins should hold steady this year.",
}
QUARTERS = [
    {"period": "Sep 2024", "period_end": "2024-09-30", "revenue": 1000},
    {"period": "Dec 2024", "period_end": "2024-12-31", "revenue": 1100},
    {"period": "Mar 2025", "period_end": "2025-03-31", "revenue": 1050},
    {"period": "Jun 2025", "period_end": "2025-06-30", "revenue": 1200},
    {"period": "Sep 2025", "period_end": "2025-09-30", "revenue": 1320},
    {"period": "Dec 2025", "period_end": "2025-12-31", "revenue": 1200},
]


def test_indian_quarter_labels_map_to_calendar_quarter_ends():
    assert quarter_end("Q3 FY26") == "2025-12-31"
    assert quarter_end("Q1 FY27") == "2026-06-30"
    assert quarter_end("Q4 FY26") == "2026-03-31"
    assert quarter_end("Dec 2025") == "2025-12-31"
    assert quarter_end("FY27") is None


def test_grounded_quote_is_kept_with_its_source():
    claim = {"quote": "We expect revenue growth of 12 percent in Q3 FY26.", "page": 4}
    kept, dropped = ground([claim], [PASSAGE])
    assert dropped == 0
    assert kept[0]["doc"] == "Transcript Q2 FY26"
    assert kept[0]["page"] == 4


def test_paraphrase_is_dropped():
    claim = {"quote": "Management expects twelve percent revenue growth.", "page": 4}
    kept, dropped = ground([claim], [PASSAGE])
    assert kept == [] and dropped == 1


def test_quote_on_wrong_page_is_dropped():
    claim = {"quote": "Margins should hold steady this year.", "page": 9}
    kept, dropped = ground([claim], [PASSAGE])
    assert kept == [] and dropped == 1


def test_non_numeric_page_is_dropped_not_crashed():
    claim = {"quote": "Margins should hold steady this year.", "page": "four"}
    kept, dropped = ground([claim], [PASSAGE])
    assert kept == [] and dropped == 1


def test_met_missed_and_pending_verdicts():
    met = verdict_for({"metric": "revenue", "growth_pct": 10, "period": "Sep 2025"}, QUARTERS)
    partly = verdict_for({"metric": "revenue", "growth_pct": 40, "period": "Sep 2025"}, QUARTERS)
    pending = verdict_for({"metric": "revenue", "growth_pct": 10, "period": "Mar 2026 Q4 FY26"}, QUARTERS)
    assert met == (32.0, "met")                 # 1320 vs 1000 a year earlier = +32%
    assert partly == (32.0, "partly met")       # 32 delivered of 40 promised = 80%
    assert pending == (None, "pending")         # no figures for that quarter yet


def test_non_revenue_claims_are_not_checked():
    assert verdict_for({"metric": "margin", "growth_pct": 20, "period": "Q3 FY26"}, QUARTERS) == (None, "not checked")


def test_run_narrative_finds_statements_and_grades_them_without_a_model():
    chunks = [{"id": "c1", "page": 4, "text": PASSAGE["text"], "label": PASSAGE["label"]}]
    result = run_narrative("INFY", chunks, QUARTERS)
    assert result["dropped"] == 0
    claim = result["claims"][0]
    assert claim["verdict"] == "partly met"      # Dec 2025 is +9.1%, 12% promised = 76% of target
    assert claim["actual_yoy_pct"] == pytest.approx(9.1)
    assert claim["id"]                           # every claim carries its id for the note
    assert [q["period"] for q in result["quarters"]] == ["Mar 2025", "Jun 2025", "Sep 2025", "Dec 2025"]


def test_no_statements_returns_a_note():
    result = run_narrative("INFY", [{"id": "c", "page": 1, "text": "Nothing relevant.", "label": "x"}], QUARTERS)
    assert result["claims"] == []
    assert "no forward-looking" in result["note"]


def test_claim_id_is_stable_and_changes_with_the_verdict():
    base = {"quote": "We expect revenue growth of 12 percent in Q3 FY26.", "page": 4,
            "verdict": "partly met", "promised_growth_pct": 12.0, "actual_yoy_pct": 9.1}
    assert claim_id("INFY", base) == claim_id("INFY", dict(base))
    assert claim_id("INFY", base) != claim_id("INFY", {**base, "verdict": "met"})


def test_with_notes_attaches_text_by_id_and_leaves_others_empty():
    result = {"claims": [{"id": "a"}, {"id": "b"}]}
    out = with_notes(result, {"a": "The company delivered most of its promise."})
    assert out["claims"][0]["explanation"] == "The company delivered most of its promise."
    assert out["claims"][1]["explanation"] is None


@pytest.fixture
def client(tmp_path, monkeypatch):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    monkeypatch.setenv("FINN_SERVER_DB", str(tmp_path / "server.db"))
    monkeypatch.setenv("FINN_SYNC_TOKEN", "test-token")
    import server.app as app_module
    importlib.reload(app_module)
    return fastapi_testclient.TestClient(app_module.app)


def test_endpoint_404_when_no_transcripts(client):
    assert client.post("/api/pull/INFY/narrative").status_code == 404


def test_endpoint_finds_statements_without_any_model_key(client):
    stamp = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
    client.post("/api/sync", json={
        "documents": [{"id": "d1", "ticker": "INFY", "doc_type": "transcript", "period": "2026",
                       "url": "https://example.com/t.pdf", "label": "Transcript", "updated_at": stamp}],
        "chunks": [{"id": "d1|4|0", "document_id": "d1", "ticker": "INFY", "doc_type": "transcript",
                    "page": 4, "text": PASSAGE["text"], "updated_at": stamp}],
    }, headers={"Authorization": "Bearer test-token"})
    resp = client.post("/api/pull/INFY/narrative")
    assert resp.status_code == 200
    claims = resp.json()["claims"]
    assert claims[0]["quote"] == "We expect revenue growth of 12 percent in Q3 FY26."
    assert claims[0]["page"] == 4
    assert "explanation" in claims[0]
