"""End to end: load realistic data into the server, then call every endpoint the pages depend on.

If this passes, the digest, alerts, results, snapshot, balance sheet, bull and bear, promise check, credit
scorecard, settings, push, ticker queue and both pages all work together on one set of data.
"""

import importlib
from datetime import datetime, timedelta, timezone

import pytest

from server import push

fastapi_testclient = pytest.importorskip("fastapi.testclient")
HEADERS = {"Authorization": "Bearer test-token"}
NOW = datetime.now(timezone.utc)
STAMP = (NOW - timedelta(hours=1)).isoformat(timespec="seconds")

TRANSCRIPT = (
    "We delivered strong Q1 FY27 results and H1 of FY27 is on plan. "
    "Our operating margin guidance remains at 20% to 22% for the year. "
    "Based on our outlook, our revenue growth guidance is 1% to 2% YoY in constant currency terms. "
    "Demand remains robust and we are confident about the year ahead. "
    "Headwinds and softer volumes pressured two large clients during the second quarter."
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FINN_SERVER_DB", str(tmp_path / "server.db"))
    monkeypatch.setenv("FINN_SYNC_TOKEN", "test-token")
    monkeypatch.setattr(push, "PUBLIC", "")
    monkeypatch.setattr(push, "PRIVATE_B64", "")
    import server.app as app_module
    importlib.reload(app_module)
    return fastapi_testclient.TestClient(app_module.app)


def announcement(id_, category, tier, hours_ago, subject):
    published = (NOW - timedelta(hours=hours_ago)).isoformat(timespec="seconds")
    return {"id": id_, "ticker": "INFY", "published_at": published, "subject": subject,
            "attachment_url": "https://example.com/filing.pdf", "xbrl_url": None,
            "category": category, "tier": tier, "updated_at": STAMP}


def quarter_ends():
    ends = []
    for year in (2023, 2024, 2025):
        ends += [f"{year}-06-30", f"{year}-09-30", f"{year}-12-31", f"{year + 1}-03-31"]
    return ends + ["2026-06-30"]            # 13 quarters, ending in June 2026


def payload():
    end_day = (NOW - timedelta(hours=1)).date()
    bars, price = [], 100.0
    for i in range(40):
        day = (end_day - timedelta(days=39 - i)).isoformat()
        last = i == 39
        price *= 1.04 if last else (1.001 if i % 2 == 0 else 0.999)
        bars.append({"id": f"INFY|{day}", "ticker": "INFY", "date": day, "close": price, "adj_close": price,
                     "volume": 300.0 if last else 100.0, "vol_baseline": 100.0, "updated_at": STAMP})
    quarters = []
    for i, end in enumerate(quarter_ends()):
        revenue = 1000.0 + 25 * i
        quarters.append({"id": f"INFY|{end}", "ticker": "INFY",
                         "period": datetime.fromisoformat(end).strftime("%b %Y"), "period_end": end,
                         "revenue": revenue, "ebitda": round(revenue * 0.21, 1), "pbt": round(revenue * 0.19, 1),
                         "pat": round(revenue * 0.14, 1), "source": "screener", "updated_at": STAMP})
    return {
        "companies": [{"ticker": "INFY", "name": "Infosys", "in_portfolio": 1, "updated_at": STAMP}],
        "announcements": [
            announcement("nse|r1", "results", "high", 2, "Financial Results for the quarter"),
            announcement("nse|m1", "management_change", "high", 3, "Appointment of Mr. A. Sharma as CFO"),
            announcement("nse|p1", "press_release", "low", 1, "Press release"),
        ],
        "management_bios": [{
            "id": "nse|m1", "ticker": "INFY", "name": "A. Sharma", "role": "Chief Financial Officer",
            "bio": "Chartered accountant with twenty years in finance, most recently at a large retailer.",
            "source_url": "https://example.com/profile", "origin": "manual",
            "published_at": (NOW - timedelta(hours=3)).isoformat(timespec="seconds"), "updated_at": STAMP}],
        "prices_eod": bars,
        "financials_q": quarters,
        "documents": [{"id": "d1", "ticker": "INFY", "doc_type": "transcript", "period": "2026",
                       "url": "https://example.com/t.pdf", "label": "Earnings Call Transcript 28 Oct",
                       "updated_at": STAMP}],
        "chunks": [{"id": "d1|4|0", "document_id": "d1", "ticker": "INFY", "doc_type": "transcript",
                    "page": 4, "text": TRANSCRIPT, "updated_at": STAMP}],
        "annual_figures": [
            {"id": f"INFY|{y}", "ticker": "INFY", "year": str(y), "net_worth": 1000.0, "borrowings": 400.0,
             "total_assets": 2000.0, "cfo": 250.0, "pat": 200.0, "updated_at": STAMP} for y in (2024, 2025)],
    }


@pytest.fixture
def loaded(client):
    resp = client.post("/api/sync", json=payload(), headers=HEADERS)
    assert resp.status_code == 200, resp.text
    return client


def test_the_digest_prioritises_and_attaches_the_management_profile(loaded):
    digest = loaded.get("/api/digest?hours=720").json()
    assert digest["counts"]["high"] == 2
    assert [a["category"] for a in digest["routine"]] == ["press_release"]
    management = next(a for a in digest["high"] if a["category"] == "management_change")
    assert management["bio"]["name"] == "A. Sharma"
    assert management["bio"]["origin"] == "manual"


def test_an_unusual_day_raises_both_alerts_for_that_stock(loaded):
    kinds = {a["kind"] for a in loaded.get("/api/alerts?hours=24").json()["alerts"]}
    assert kinds == {"volume_spike", "price_move"}


def test_the_results_card_has_figures_and_the_profit_view(loaded):
    card = loaded.get("/api/company/INFY/results").json()
    assert card["period"] == "Jun 2026"
    assert card["metrics"]["revenue"]["yoy_pct"] is not None
    assert card["profit_view"]["gap_pts"] is not None


def test_snapshot_balance_sheet_and_bull_and_bear_answer(loaded):
    assert loaded.get("/api/company/INFY/snapshot").json()["trajectory"]["points"]
    years = loaded.get("/api/company/INFY/annual").json()["years"]
    assert years[-1]["debt_to_equity_x"] == pytest.approx(0.4)
    assert years[-1]["cash_quality_pct"] == pytest.approx(125.0)
    sides = loaded.get("/api/company/INFY/bullbear").json()
    assert sides["bull"] and sides["bull"][0]["page"] == 4
    assert sides["bear"]


def test_the_promise_check_gives_each_kind_of_statement_its_honest_verdict(loaded):
    result = loaded.post("/api/pull/INFY/narrative").json()
    by_metric = {c["metric"]: c for c in result["claims"]}
    assert by_metric["margin"]["period"] == "FY27"           # worked out from "H1 of FY27"
    assert by_metric["margin"]["verdict"] == "on track"      # 21% so far against a guided 20% to 22%
    assert by_metric["revenue"]["verdict"] == "not comparable"   # guided in constant currency
    assert result["dropped"] == 0
    assert len(result["quarters"]) == 4


def test_the_credit_scorecard_scores_the_company(loaded):
    body = loaded.get("/api/company/INFY/credit", params={"debt": 400, "cash": 100, "interest": 30}).json()
    assert body["rating"] in {"Strong", "Adequate", "Weak", "Stressed"}
    assert len(body["sensitivity"]["series"]) == 3


def test_alert_settings_can_be_read_and_changed(loaded):
    assert loaded.get("/api/settings").json()["z_threshold"] == 2.0
    resp = loaded.put("/api/settings", json={"volume_multiple": 2.5, "price_move_pct": 3.0, "z_threshold": 3.0})
    assert resp.status_code == 200
    assert loaded.get("/api/settings").json()["z_threshold"] == 3.0


def test_push_says_it_is_not_set_up_and_the_ticker_queue_works(loaded):
    assert loaded.get("/api/push/key").json() == {"key": None}
    assert loaded.post("/api/request/ZOMATO").json()["status"] == "queued"
    assert loaded.get("/api/requests", headers=HEADERS).json() == {"tickers": ["ZOMATO"]}


def test_both_pages_and_the_service_worker_are_served(loaded):
    home = loaded.get("/")
    assert home.status_code == 200
    assert "Today's brief" in home.text and "credit.html" in home.text
    assert loaded.get("/credit.html").status_code == 200
    assert "push" in loaded.get("/sw.js").text


def test_ask_answers_from_the_transcripts_and_admits_when_it_cannot(loaded):
    found = loaded.get("/api/company/INFY/ask", params={"q": "What is the operating margin guidance?"}).json()
    assert found["found"] is True and found["answers"][0]["page"] == 4
    missing = loaded.get("/api/company/INFY/ask", params={"q": "Who won the cricket world cup final?"}).json()
    assert missing["found"] is False and "Not found in source" in missing["note"]
    assert loaded.get("/api/company/NOPE/ask", params={"q": "margin guidance"}).status_code == 404
