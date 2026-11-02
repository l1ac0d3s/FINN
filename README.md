# FINN

A mobile-first investor filter. Push shows what changed in your portfolio and why it
matters. Pull answers questions about one company, using only its annual reports and
concall transcripts.

**Live:** https://finn-wq09.onrender.com  
**Repository:** https://github.com/l1ac0d3s/FINN

## Layout

```
ingest/    runs on your laptop: prices, announcements, classification, alerts, publish
server/    runs on Render: receives synced rows, serves the digest and alerts
shared/    schema used by both sides
web/       mobile-first web app (single-page, dark/light themes, installable)
tests/     pytest (98 tests)
seed/      seed.sqlite — committed snapshot so the hosted app is never blank
```

## Setup (laptop)

```powershell
# Windows
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # fill in values
pytest                    # 98 pure-logic tests, no network needed
```

```bash
# macOS / Linux
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in values, then: export $(grep -v '^#' .env | xargs)
pytest
```

Edit `ingest/config.py` to set the portfolio, ad-hoc tickers, and alert thresholds.

## Run

```bash
python -m ingest.run_daily --dry        # list the tickers
python -m ingest.run_daily              # ingest into data/ingest.db
python -m ingest.run_daily --publish    # ingest and sync to the server
```

Run from the repo root. Schedule the ingest daily after 18:00 IST.

## Server

```bash
FINN_SYNC_TOKEN=... uvicorn server.app:app --reload
curl localhost:8000/api/health
```

Render: start command `uvicorn server.app:app --host 0.0.0.0 --port $PORT`,
environment variables `FINN_SYNC_TOKEN` and `FINN_SERVER_DB`.

## Status

| Piece | State |
|---|---|
| Schema, sync, digest API | Built, tested offline and over HTTP |
| Classifier (18 categories) | Built, tested on 31 labelled subjects; live NSE subjects not yet checked |
| Price ingest and alerts (volume, price move) | Built and run live: 22/22 tickers return bars |
| NSE announcements (last 7 days) | Built and run live: field names confirmed |
| Screener quarterly financials | Built and run live: 13 quarters for 21 of 22 tickers; PAGEIND still failing |
| Screener document links | Built and run live: links stored; PDFs not downloaded |
| Results card (QoQ, YoY) | Built and tested; endpoint `/api/company/{ticker}/results` |
| Web app (digest, alerts, results cards) | Built: one page at `web/index.html`, served at `/` |

## Not built (in order of priority)

1. **Pull outputs beyond narrative vs numbers.** Guidance, cash quality, balance sheet, business snapshot, trajectory and bull vs bear.
2. **Management-change bio** for the push card — needs a reliable professional-data source.
3. **BSE fallback** for announcements.
4. **Background push notifications** when the app is closed. Notifications work while the app is open.
5. **PAGEIND quarters table** — screener layout not yet recognised for this ticker.

## Deploy (Render)

1. Create a Render web service from this repository. `render.yaml` sets the build and start commands.
2. In the Render dashboard, set the secrets `FINN_SYNC_TOKEN` (any long random string) and `HF_TOKEN` (your Hugging Face token).
3. Once the service is live, publish from your machine:

```powershell
$env:FINN_SYNC_TOKEN = "the same value as on Render"
$env:FINN_SERVER_URL = "https://your-service.onrender.com"
python -m ingest.run_daily --publish
```

Render's free tier may not keep the server's database across restarts. If the digest is empty after a restart, publish again.

## Design

The interface is built for an investment team's daily routine, with ENAM Holdings as the intended user:

- **Today's brief** gives the count of items needing attention, alerts and routine items in one line, so an investor sees what matters before scrolling.
- **Priority first:** High-tier filings come first, Medium next, and Routine is collapsed. Nothing is hidden silently, because the number of hidden items is always shown.
- **Every filing links to its primary source,** and the market line shows how the stock moved after each filing.
- **Dark and light themes** follow the phone's setting, and the layout is designed for a phone-sized screen.
- **Nothing is invented.** Figures come from exchange filings, screener.in and end-of-day prices, and each figure is shown with its source.

## Alerts, settings and notifications

- **Alert settings** are changed in the app (open *Alert settings*). They are stored on the server and applied at once. The server recalculates alerts from the synced prices, so no re-publish is needed.
- **Custom period:** type any number of hours (1 to 720) next to the 24h / 3 days / 7 days buttons.
- **Notifications:** press *Turn on notifications*. While the app is open, new high-priority filings trigger a notification. The list of seen filings is kept in this browser only.
- **Install on a phone:** open the app in the phone's browser, then use *Add to Home Screen*. It opens full-screen like an app.

## Always on

The hosted app is designed to run without anyone maintaining it:

- **Seed data.** `seed/seed.sqlite` is a copy of the recent data. When the hosted app starts on an empty disk, it copies this file, so it is never blank. Rebuild it with `python -m ingest.make_seed` and commit it to refresh the data.
- **No sleep.** A free uptime monitor (for example UptimeRobot) checks `/api/health` every 5 minutes, which keeps the free hosting plan awake. This is a one-time setup.
