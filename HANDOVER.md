# FINN handover

What runs where, and how to operate it. The covering note says what is and is not built.

## Where things run
- **Laptop (`ingest/`)** fetches prices (yfinance), announcements (NSE), quarterly figures and balance sheets (screener.in),
  transcripts, and management-change filings. Run `python -m ingest.run_daily --skip-text --publish`, or
  `.\refresh_finn.ps1` to rebuild the seed and send everything to the server.
- **Server (`server/`, on Render, free plan)** stores what the laptop sends and serves the pages and the API.
  It makes no model calls. Its disk is temporary, so it starts from `seed/seed.sqlite` after a deploy or restart.
- **GitHub Actions** (`.github/workflows/nightly.yml`) refreshes data on weekdays and commits a new seed.

## Environment variables
- Laptop: `FINN_SERVER_URL`, `FINN_SYNC_TOKEN`; optional `ANTHROPIC_API_KEY` (promise notes, labels for unmatched subjects).
- Render: `FINN_SYNC_TOKEN`, `FINN_SERVER_DB`, and for push: `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_B64`, `VAPID_SUBJECT`
  (create with `python -m server.push_keys`; each value goes in its own field, one line, no label).

## Checks
- `python -m pytest -q` runs every test, including `tests/test_smoke.py`, which loads sample data and calls every endpoint.
- `python -m ingest.check_nse TICKER` shows what NSE returns for a company.
- `python -m ingest.notes --check` tests the Anthropic key.
- `POST /api/push/test` (with the sync token) sends a labelled test notification and reports subscribers and any error.

## Known limits
- Results come mostly from screener.in. Results PDFs are read for layouts checked so far (ITC standalone).
- Constant-currency revenue guidance is marked "not comparable" with rupee revenue.
- Saved phones and changed alert settings are lost when the free server redeploys or restarts.
- Not built: business snapshot, free cash flow and working-capital days, BSE data, management backgrounds beyond the
  filing and hand entries.

## Security
- Never paste the sync token or the VAPID private key into chat, tickets or commits. If one is exposed, replace it on
  Render and on the laptop.
