# FINN: covering note

**Subject:** ENAM - IIT screening - 2027

## What I built

FINN is a mobile-first web app with two modes. **Push** shows what changed in an 18-company portfolio plus 4 ad-hoc tickers: a time-windowed digest, announcements sorted into priority tiers, price and volume alerts with configurable thresholds, and results cards with QoQ and YoY growth. Every filing card shows the market reaction — how the stock moved on the session after the filing, and whether volume was unusual. **Pull** runs a narrative-vs-numbers check on one company: it reads earnings-call transcripts, lists management's quantified revenue claims with a verbatim quote and page, and compares each claim with the reported growth.

## Key decisions and trade-offs

- **Ingest runs on my own machine; the server only serves data.** Yahoo, NSE and screener.in block cloud-sandbox traffic, but are reachable from a normal network. The trade-off is that the data is as fresh as the last run, not live. The app shows a "Data as of" line so the investor always knows.
- **Classification by rules first, from the reference document's 18 categories.** A model is called only when no rule matches. This keeps cost near zero. Unmatched subjects go to low priority rather than being hidden.
- **Verdicts come from the figures, not the model.** The model writes quotes and states the growth it was told about. A claim is kept only if its quote appears word for word on the stated page. Claims that fail are dropped and counted, never shown. This is the "narrative vs numbers" analysis the brief values most.
- **Free-tier model.** The pull feature calls a free Hugging Face model, so the cost is zero. The trade-off is that free-tier availability and quality vary.
- **Sentence-aligned chunks.** Text is split at sentence boundaries so a quote is never cut in half, which makes the verbatim check reliable.
- **Batch sync.** Rows go to the server in batches of 500, so a deployed server doesn't receive one very large request.
- **Alert thresholds are configurable in the app.** Volume spike multiple (1–10×) and price move percentage (1–20%) can be edited directly in the UI and saved on the server.
- **Time windows follow the newest data.** A snapshot stays useful instead of going blank when the data isn't live.

## What I deliberately left out

- The management-change bio (the brief's example). It needs a source for the person's background, and I didn't want to scrape a professional network.
- The BSE fallback. NSE alone covers the demo tickers.
- Pull outputs other than narrative-vs-numbers. Guidance, cash quality, balance sheet, business snapshot, trajectory and bull-vs-bear are not built. The narrative-vs-numbers is the worked example the brief asks for.
- Real-time push notifications when the app is closed. Notifications work while the app is open.
- Annual reports in the pull feature. The download logic exists but is switched off to keep the seed small.

## Status, stated plainly

- Prices, announcements, quarterly figures and document links ran live for all 22 tickers.
- Transcript text extraction is present.
- The claims check code is complete and tested. The deployed link shows the digest, alerts, results cards and market reactions. The claims-check button appears on results cards but requires model access to produce output.
- Each filing card shows how the stock moved on the session after the filing, and whether volume was unusual.

## Where I'd take it next

1. Run the claims check on all 22 companies and tune the prompt against the verdicts.
2. Add the other pull outputs, starting with guidance and cash quality.
3. Move ingest to a scheduled job so the data refreshes without a laptop.
4. Add push notifications for the High tier (background sync via web push).
5. Add the management-change bio enrichment with a reliable professional-data source.

## Build history

The Claude Code session used to build this: https://claude.ai/code/session_01A1LVKziQJcCEW5rvXbFFn9

## Links

- App: https://finn-wq09.onrender.com
- Repository: https://github.com/l1ac0d3s/FINN
