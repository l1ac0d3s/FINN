"""Build the seed database that the hosted app starts from.

Run on your computer after the daily ingest:
    python -m ingest.make_seed

Commit the result as seed/seed.sqlite. The hosted app copies it whenever it starts
on an empty disk, so it always has data, even after a redeploy or a restart of the free
server. Transcript text is included, because the promise checker and the bull-and-bear
card read it, and a restarted server would show neither without it.

The nightly job runs on GitHub with an empty database and skips transcripts, and it has no
model key for the promise notes. So for those two tables, when the new run has no rows, the
previous seed's rows are kept instead of being thrown away.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from ingest import config
from shared.schema import connect, upsert

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"
SEED_PATH = SEED_DIR / "seed.sqlite"
PRICE_DAYS = 30
CARRY_FORWARD = ("chunks", "claim_notes")   # tables the nightly job cannot produce


def build(source_db, target_db, now=None):
    """Copy the recent rows the app needs from the ingest database. Returns row counts."""
    now = now or datetime.now(timezone.utc)
    target_db = Path(target_db)

    previous = {}
    if target_db.exists():
        old = connect(target_db)
        for table in CARRY_FORWARD:
            previous[table] = [dict(r) for r in old.execute(f"SELECT * FROM {table}").fetchall()]
        old.close()
        target_db.unlink()

    source = connect(source_db)
    target = connect(target_db)
    price_cut = (now - timedelta(days=PRICE_DAYS)).date().isoformat()
    announcement_cut = (now - timedelta(days=config.ANNOUNCEMENT_DAYS)).isoformat(timespec="seconds")
    queries = {
        "companies": ("SELECT * FROM companies", []),
        "prices_eod": ("SELECT * FROM prices_eod WHERE date >= ?", [price_cut]),
        "announcements": ("SELECT * FROM announcements WHERE published_at >= ?", [announcement_cut]),
        "alerts": ("SELECT * FROM alerts WHERE date >= ?", [price_cut]),
        "financials_q": ("SELECT * FROM financials_q", []),
        "documents": ("SELECT * FROM documents", []),
        "chunks": ("SELECT * FROM chunks", []),
        "management_bios": ("SELECT * FROM management_bios", []),
        "claim_notes": ("SELECT * FROM claim_notes", []),
        "annual_figures": ("SELECT * FROM annual_figures", []),
    }
    counts = {}
    with target:
        for table, (sql, args) in queries.items():
            rows = [dict(r) for r in source.execute(sql, args).fetchall()]
            if not rows and table in CARRY_FORWARD:
                rows = previous.get(table, [])   # keep the last seed's rows rather than losing them
            for row in rows:
                upsert(target, table, row)
            counts[table] = len(rows)
    source.close()
    target.close()
    return counts


if __name__ == "__main__":
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    print("seed written to", SEED_PATH)
    print(build(config.INGEST_DB, SEED_PATH))
