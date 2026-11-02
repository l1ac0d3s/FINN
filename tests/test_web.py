"""The web app is served by the server, and the company results endpoint works over HTTP."""

import importlib
from datetime import datetime, timedelta, timezone

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

NOW = datetime.now(timezone.utc)
HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FINN_SERVER_DB", str(tmp_path / "server.db"))
    monkeypatch.setenv("FINN_SYNC_TOKEN", "test-token")
    import server.app as app_module
    importlib.reload(app_module)
    return fastapi_testclient.TestClient(app_module.app)


def test_home_page_is_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "<title>FINN</title>" in resp.text
    assert "/api/digest" in resp.text


def test_results_endpoint_returns_card_after_sync(client):
    quarters = [
        {"id": f"INFY|{end}", "ticker": "INFY", "period": period, "period_end": end,
         "revenue": revenue, "ebitda": None, "pbt": None, "pat": None,
         "source": "screener", "updated_at": "2026-10-29T06:00:00+00:00"}
        for period, end, revenue in [
            ("Sep 2024", "2024-09-30", 1000), ("Dec 2024", "2024-12-31", 1100),
            ("Mar 2025", "2025-03-31", 1050), ("Jun 2025", "2025-06-30", 1200),
            ("Sep 2025", "2025-09-30", 1320),
        ]
    ]
    resp = client.post("/api/sync", json={"financials_q": quarters}, headers=HEADERS)
    assert resp.status_code == 200

    card = client.get("/api/company/infy/results").json()
    assert card["period"] == "Sep 2025"
    assert card["metrics"]["revenue"]["yoy_pct"] == pytest.approx(32.0)


def test_results_endpoint_404_for_unknown_company(client):
    assert client.get("/api/company/NOPE/results").status_code == 404


def test_digest_includes_recent_high_announcement(client):
    ts = (NOW - timedelta(hours=1)).isoformat(timespec="seconds")
    client.post("/api/sync", json={
        "companies": [{"ticker": "INFY", "name": "INFY", "in_portfolio": 1, "updated_at": ts}],
        "announcements": [{"id": "nse|1", "ticker": "INFY", "published_at": ts,
                           "subject": "Outcome of Board Meeting", "attachment_url": None,
                           "category": "results", "tier": "high", "updated_at": ts}],
    }, headers=HEADERS)
    digest = client.get("/api/digest?hours=24").json()
    assert [a["ticker"] for a in digest["high"]] == ["INFY"]
