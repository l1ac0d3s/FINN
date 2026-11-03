"""The credit scorecard route, over HTTP, with figures synced from the laptop."""

import importlib

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FINN_SERVER_DB", str(tmp_path / "server.db"))
    monkeypatch.setenv("FINN_SYNC_TOKEN", "test-token")
    import server.app as app_module
    importlib.reload(app_module)
    return fastapi_testclient.TestClient(app_module.app)


QUARTER_ENDS = ["2024-06-30", "2024-09-30", "2024-12-31", "2025-03-31",
                "2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31"]


def sync_quarters(client, count):
    rows = [{"id": f"INFY|{end}", "ticker": "INFY", "period": end, "period_end": end,
             "revenue": 1000 + 10 * i, "ebitda": 300 + i, "pbt": 280 + i, "pat": 150 + i,
             "source": "screener", "updated_at": "2026-10-29T06:00:00+00:00"}
            for i, end in enumerate(QUARTER_ENDS[:count])]
    return client.post("/api/sync", json={"financials_q": rows}, headers=HEADERS)


def test_credit_route_scores_and_returns_the_sensitivity_grid(client):
    assert sync_quarters(client, 8).status_code == 200
    resp = client.get("/api/company/infy/credit", params={"debt": 400, "cash": 100, "interest": 30})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "INFY"
    assert body["rating"] in {"Strong", "Adequate", "Weak", "Stressed"}
    assert len(body["sensitivity"]["series"]) == 3
    assert body["inputs"] == {"debt": 400, "cash": 100, "interest": 30}


def test_credit_route_needs_four_quarters(client):
    sync_quarters(client, 2)
    resp = client.get("/api/company/infy/credit", params={"debt": 400})
    assert resp.status_code == 404


def test_credit_route_rejects_negative_debt(client):
    sync_quarters(client, 8)
    assert client.get("/api/company/infy/credit", params={"debt": -1}).status_code == 422
