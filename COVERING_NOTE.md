# FINN: covering note

**Subject:** ENAM - IIT screening - 2027

## Links

- App (mobile-friendly): https://finn-wq09.onrender.com
- Repository: https://github.com/l1ac0d3s/FINN
- AI build history: https://claude.ai/code/session_01A1LVKziQJcCEW5rvXbFFn9

## What I built

FINN is a mobile-first investor filter with a push view and a pull view.

**Push**
- A portfolio of 18 companies across sectors and sizes, plus 4 ad-hoc tickers.
- A digest for 24 hours, 3 days, 7 days, or any number of hours from 1 to 720.
- Each announcement is classified using the 18 categories in the reference document, and sorted into High, Medium, Routine and Hidden.
- Every filing has a one-line meaning for its type, and a market line showing how the stock moved after the filing.
- Filings listed under several subject lines appear as one card.
- Price and volume alerts, with thresholds you can change in the app.
- You choose which announcement types raise an alert.
- Results cards with revenue, EBITDA, PBT and PAT, and QoQ and YoY growth.
- You can look up any ticker that has data on the server.

**Pull**
- Narrative vs numbers: management's quantified revenue claims are taken from earnings-call transcripts, and each one must be quoted word for word from the cited page. Claims that fail this check are dropped. Each claim is then compared with reported growth.

## Key decisions and trade-offs

- The data is gathered on a computer and sent to the hosted app. Financial sites block the cloud host, so this was the reliable route.
- A nightly job on GitHub Actions refreshes the data each weekday at 18:30 IST, so no computer needs to stay on. Its first run is a test, and I haven't confirmed it yet.
- Results and market figures come from data, not from a language model.
- EBITDA is screener.in's "Operating Profit", which is an approximation.
- Every filing's one-line meaning describes its category, not its content. Reading the actual document would need downloads I haven't built.
- The page shows "Data as of" with the newest filing date, and the time windows are measured from that date.

## What is not finished

- **The claims check has not produced output from a real model.** It needs a language model. The free hosted models I tried had no credits or refused access, and a local model on my laptop was too slow to finish. The code is complete and tested with a stand-in model.
- **Only one pull output is built.** Guidance, cash quality, balance sheet, business snapshot, trajectory and bull vs bear are not built.
- **Management-change bio.** I found no reliable source for a person's background, so it is not built.
- **Results figures come from screener.in,** not from the results filing the brief names.
- **Alerts are not sent to the phone when the app is closed.** The app shows notifications while it is open, and it can be added to a phone's home screen.
- **BSE is not used.** NSE covers every demo company.

## Where I'd take it next

1. Get the claims check running on a hosted model, and run it across all 22 companies.
2. Build the other pull outputs, starting with guidance and cash quality from screener.in's tables.
3. Read the results figures from the filing itself.
4. Add a source for management-change backgrounds, for example the disclosure in the appointment filing.
5. Send push notifications when the app is closed.

Thank you for the opportunity. I'm happy to walk through any part of it.

Regards,
[YOUR NAME]
[YOUR PHONE]
