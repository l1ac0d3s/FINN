"""Round-trip test: rows written by ingest are accepted by the server and
an older update does not overwrite a newer row."""

import importlib
from datetime import datetime, timedelta, timezone

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FINN_SERVER_DB", str(tmp_path / "server.db"))
    monkeypatch.setenv("FINN_SYNC_TOKEN", "test-token")
    import server.app as app_module
    importlib.reload(app_module)
    return fastapi_testclient.TestClient(app_module.app)


NOW = datetime.now(timezone.utc)
RECENT = (NOW - timedelta(hours=1)).isoformat(timespec="seconds")
EARLIER = (NOW - timedelta(hours=3)).isoformat(timespec="seconds")
HEADERS = {"Authorization": "Bearer test-token"}


def ann(updated_at, tier="high"):
    return {"id": "nse|1", "ticker": "INFY", "published_at": RECENT,
            "subject": "Outcome of Board Meeting", "attachment_url": None,
            "category": "results", "tier": tier, "updated_at": updated_at}


def test_rejects_bad_token(client):
    resp = client.post("/api/sync", json={}, headers={"Authorization": "Bearer nope"})
    assert resp.status_code == 401


def test_alerts_are_calculated_from_prices_with_saved_thresholds(client):
    today = NOW.date()
    yesterday = (today - timedelta(days=1)).isoformat()
    client.post("/api/sync", json={"prices_eod": [
        {"id": f"INFY|{yesterday}", "ticker": "INFY", "date": yesterday, "close": 100.0,
         "adj_close": 100.0, "volume": 100.0, "vol_baseline": 100.0, "updated_at": RECENT},
        {"id": f"INFY|{today.isoformat()}", "ticker": "INFY", "date": today.isoformat(), "close": 100.0,
         "adj_close": 100.0, "volume": 300.0, "vol_baseline": 100.0, "updated_at": RECENT},
    ]}, headers=HEADERS)

    resp = client.get("/api/alerts?hours=24")
    assert [a["kind"] for a in resp.json()["alerts"]] == ["volume_spike"]

    # Raising the volume threshold above 3x must remove the alert, with no re-sync needed.
    assert client.put("/api/settings", json={"volume_multiple": 4, "price_move_pct": 5}).status_code == 200
    assert client.get("/api/alerts?hours=24").json()["alerts"] == []


def test_settings_round_trip_and_reject_bad_values(client):
    s = client.get("/api/settings").json()
    assert (s["volume_multiple"], s["price_move_pct"], s["z_threshold"]) == (2.0, 2.0, 2.0)
    assert "results" in s["alert_categories"] and "dividend" not in s["alert_categories"]
    assert client.put("/api/settings", json={"volume_multiple": 3, "price_move_pct": 7}).status_code == 200
    assert client.get("/api/settings").json()["volume_multiple"] == 3.0
    assert client.put("/api/settings", json={"volume_multiple": 3, "price_move_pct": 7,
                                             "alert_categories": ["dividend", "pledging"]}).status_code == 200
    assert sorted(client.get("/api/settings").json()["alert_categories"]) == ["dividend", "pledging"]
    assert client.put("/api/settings", json={"volume_multiple": 3, "price_move_pct": 7,
                                             "alert_categories": ["not-a-category"]}).status_code == 400
    assert client.put("/api/settings", json={"volume_multiple": 99, "price_move_pct": 7}).status_code == 400
    assert client.put("/api/settings", json={"volume_multiple": "abc", "price_move_pct": 7}).status_code == 400


def test_newer_row_wins_and_older_is_ignored(client):
    client.post("/api/sync", json={"companies": [
        {"ticker": "INFY", "name": "Infosys", "in_portfolio": 1, "updated_at": EARLIER}
    ], "announcements": [ann(EARLIER, tier="high")]}, headers=HEADERS)
    client.post("/api/sync", json={"announcements": [ann("2000-01-01T00:00:00+00:00", tier="low")]},
                headers=HEADERS)
    resp = client.get("/api/digest?hours=24")
    assert resp.status_code == 200
    assert resp.json()["counts"]["high"] == 1
    assert resp.json()["counts"]["low"] == 0
