from ingest import config
from ingest.publish import batches, publish
from shared.schema import connect, upsert


class FakeResponse:
    def raise_for_status(self):
        pass


def test_batches_split_rows_without_losing_any():
    rows = list(range(1234))
    parts = list(batches(rows, size=500))
    assert [len(p) for p in parts] == [500, 500, 234]
    assert [x for p in parts for x in p] == rows


def test_publish_sends_bounded_batches_and_all_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SYNC_TOKEN", "t")
    conn = connect(tmp_path / "ingest.db")
    for i in range(1200):
        upsert(conn, "prices_eod", {
            "id": f"T|{i}", "ticker": "T", "date": f"2026-01-{i:04d}", "close": 1.0,
            "adj_close": 1.0, "volume": 1.0, "vol_baseline": None,
            "updated_at": "2026-10-29T06:00:00+00:00",
        })
    conn.commit()

    sent_batches = []

    def fake_post(url, json, headers, timeout):
        sent_batches.append(json)
        assert timeout > 0
        return FakeResponse()

    publish(conn, post=fake_post)
    prices = [row for b in sent_batches for row in b.get("prices_eod", [])]
    assert len(prices) == 1200
    assert max(len(b.get("prices_eod", [])) for b in sent_batches) <= 500
    assert all(len(b) == 1 for b in sent_batches)  # one table per request


def test_full_publish_ignores_the_last_sync_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SYNC_TOKEN", "t")
    conn = connect(tmp_path / "ingest.db")
    upsert(conn, "companies", {"ticker": "INFY", "name": "INFY", "in_portfolio": 1,
                               "updated_at": "2026-10-29T06:00:00+00:00"})
    conn.execute("INSERT INTO sync_state (key, value) VALUES ('last_sync', '2099-01-01T00:00:00+00:00')")
    conn.commit()

    sent = []
    publish(conn, post=lambda url, json, headers, timeout: sent.append(json) or FakeResponse(), full=True)
    assert [row["ticker"] for b in sent for row in b.get("companies", [])] == ["INFY"]
