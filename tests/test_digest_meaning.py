from datetime import datetime, timezone

from server.digest import CATEGORY_MEANING, build_digest

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def test_every_category_has_a_one_line_meaning():
    from server.alerts import ALL_CATEGORIES
    assert set(ALL_CATEGORIES) <= set(CATEGORY_MEANING)


def test_rows_carry_summary_and_alert_flag_from_the_chosen_categories():
    rows = [
        {"id": "a", "ticker": "TRENT", "published_at": "2026-11-02T06:00:00+00:00", "subject": "Dividend",
         "attachment_url": None, "category": "dividend", "tier": "medium"},
        {"id": "b", "ticker": "INFY", "published_at": "2026-11-02T07:00:00+00:00", "subject": "Results",
         "attachment_url": None, "category": "results", "tier": "high"},
    ]
    d = build_digest(rows, NOW, hours=24, alert_categories={"dividend"})
    by_id = {r["id"]: r for r in d["high"] + d["medium"] + d["routine"]}
    assert by_id["a"]["alert"] is True and by_id["b"]["alert"] is False
    assert by_id["b"]["summary"].startswith("Quarterly or annual results")
