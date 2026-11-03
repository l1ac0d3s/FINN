# FINN

A mobile-first investor filter. **Push** shows what changed in a portfolio and why it matters.
**Pull** checks what management promised in earnings calls against the reported figures.

Live app: https://finn-wq09.onrender.com
The covering note, with what is and isn't built, is in `COVERING_NOTE.md`.

## Layout

```
ingest/     runs on the laptop: prices, announcements, screener figures, transcripts, publish
server/     runs on Render: receives synced rows, serves the digest, alerts, pull outputs, credit
  risk.py       growth with a negative base, promise grading, z-scores, profit view, credit scorecard
  guidance.py   forward-looking revenue growth statements from transcripts (no language model)
  pull.py       narrative vs numbers: word-for-word check, quarter and fiscal-year verdicts
  alerts.py     price alerts (z-score per stock) and volume alerts
shared/     schema used by both sides
web/        index.html (Today, lookup, settings) and credit.html (credit scorecard)
tests/      pytest, no network needed
seed/       recent data, so the hosted app is never blank on an empty disk
```

## Setup (laptop)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest -q
```

Set the portfolio, the ad-hoc tickers and the default thresholds in `ingest/config.py`.

## Run the daily ingest

```powershell
python -m ingest.run_daily --dry        # list the tickers
python -m ingest.run_daily              # fetch prices, filings, figures, transcripts and management filings
python -m ingest.run_daily --publish    # the same, then sync to the server
```

Run from the repository root, after 18:00 IST, so that the day's closing prices are available.

## Plain-English notes (optional, needs an Anthropic key on the laptop)

Each promise verdict gets a one-sentence note, written by Claude Haiku on the laptop during the daily run.
A note is kept only if every number in it appears in the inputs. To check that the key and model work:

```powershell
$env:ANTHROPIC_API_KEY = "your key, typed here, never committed"
python -m ingest.notes --check
```

Without a key the daily run skips the notes, and the app shows none. The hosted app makes no model calls.

## Publish to the hosted app

`refresh_finn.ps1` rebuilds the seed file and sends all the data to the server. It asks for the sync token,
which must match the `FINN_SYNC_TOKEN` set on Render.

```powershell
.\refresh_finn.ps1
```

## Deploy (Render)

1. Create a Render web service from this repository. `render.yaml` sets the Python version, build command and start command.
2. Set these environment variables on Render: `FINN_SYNC_TOKEN` (a long random string) and `FINN_SERVER_DB` (`data/server.db`).
3. After any change to the server code, use **Manual Deploy → Deploy latest commit**.

Render's free plan wipes the disk on a redeploy. The seed file fills an empty disk, so the app is never blank, but
the latest figures come only from the last publish.

## Nightly refresh (GitHub Actions)

`.github/workflows/nightly.yml` runs the daily ingest on weekdays at 18:30 IST, rebuilds the seed and commits it.
The repository's Actions settings must allow **Read and write** workflow permissions. Run it once by hand to check.

## Alert settings and the credit page

- **Alerts** are set in the app under *Alert settings*. Price alerts use a z score against each stock's last 30 sessions
  (default 2), with a smallest move of 2%. Volume alerts use 2 times the 20-session median. The server applies changes at once.
- **Credit scorecard** (`/credit.html`) takes debt, cash and interest expense, in Rs crore, from the annual report.
  Those three figures are not in the stored data.

## Status

| Piece | State |
|---|---|
| Digest, tiers, Routine collapse, windows | Built, tested offline and over HTTP |
| Announcement classification (18 categories) | Built, tested on labelled subject lines. Unmatched subjects show as low-tier press releases |
| Market line after each filing | Built |
| Price alerts (z score) and volume alerts | Built, tested |
| Results card (QoQ, YoY) and profit view | Built, from screener.in. NSE's feed carries no XBRL links, so the filing parser is not used |
| Balance sheet and cash quality (by year) | Built from screener.in's tables. Tested on a sample page; live page check pending |
| Management-change profile | Built from the appointment filing, where the filing has a profile |
| Narrative vs numbers (four quarters) | Built. Deterministic, word-for-word checked, quarter and fiscal-year verdicts |
| Guidance list | Built, from transcripts only |
| Financial snapshot and trajectory | Built, from stored quarterly figures |
| Credit scorecard | Built. Debt, cash and interest are entered by the user |
| Lookup of an ingested ticker | Built |
| Lookup of a ticker with no data | Built: queued on the server; the laptop ingests it on its next daily run |
| Bull and bear points | Built as a keyword selection of quoted transcript sentences, with pages. Not a written argument |
| Guidance (revenue, margin, capex) | Built from transcripts. Revenue is checked against reported figures; margin and capex are listed only |

## Not built

- Results figures from the results PDFs (one parser per layout). Results come from screener.in.
- Free cash flow and working-capital days (need capex, receivables and inventory from the full statements).
- Business snapshot.
- Checking margin and capex guidance against reported figures (they are listed, not checked).
- Push notifications when the app is closed.
- BSE data. NSE covers every demo company.
- Management backgrounds beyond the appointment filing. No web search, no LinkedIn scraping.
- Bull vs bear as a written argument. The built version selects quoted transcript sentences by keyword; it does not weigh them.
- BSE fallback.
- Push notifications when the app is closed.
- On-demand research for a ticker that has not been ingested.

## Design

- **Today's brief** counts the items needing attention, the alerts and the routine items in one line.
- **Priority first:** High-tier filings come first, Medium next, and Routine is collapsed. Hidden items are counted, never silent.
- **Every filing links to its primary source,** and the market line shows the move after each filing.
- **Nothing is invented in the app.** Figures come from exchange filings, screener.in, end-of-day prices and the transcripts. Each one is shown with its source, and approximations are labelled.

## Notifications and install

- Notifications: press *Turn on notifications*. While the app is open, new high-priority filings trigger one. The seen list is kept in this browser only.
- On a phone, open the app in the browser and choose *Add to Home Screen*.
- A free uptime monitor (for example UptimeRobot) pinging `/api/health` every 5 minutes keeps the free plan awake.
