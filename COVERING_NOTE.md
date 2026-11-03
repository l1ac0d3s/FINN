# FINN: covering note

**Subject:** ENAM - IIT screening - 2027

## Links

- App (mobile-friendly): https://finn-wq09.onrender.com
- Repository: https://github.com/l1ac0d3s/FINN
- AI build history: https://claude.ai/code/session_01A1LVKziQJcCEW5rvXbFFn9

The free hosting plan sleeps when idle. The first visit can take up to a minute.

## What I built

FINN is a mobile-first investor filter. Push tells an investor what changed. Pull answers a question about one company.

**Push: the digest (Today)**
- A portfolio of 18 NSE companies across sectors and sizes, plus 4 ad-hoc tickers. The list is in `ingest/config.py`.
- A digest for 24 hours, 3 days, 7 days, or any custom period from 1 to 720 hours.
- Every filing is classified into one of the 18 categories in the reference document and placed in High, Medium, Routine or Hidden. Hidden items are counted, never listed.
- High-tier filings come first. Routine is collapsed. A filing listed under several subject lines appears as one card.
- Each card has a one-line meaning for its category, and a market line showing how the stock moved after the filing. A filing made after 15:30 IST is measured from the next session.
- A morning brief at the top of Today: the counts, and the three most important high-tier filings in one line each.
- Management-change cards show the person's name, role and profile, read from the appointment filing itself. If the filing has no profile, the card says so. Where I have entered a background by hand, it is labelled "entered by hand", and it links to the source I used.
- Results cards show revenue, EBITDA, PBT and PAT, with QoQ and YoY change. They also show a profit view: EBITDA growth against PBT growth, the gap between them, and a blended figure whose weight is stated.

**Push: alerts**
- Price alerts use each stock's own history. A move alerts when it is an outlier against that stock's last 30 sessions (z score of 2 or more by default), and at least 2% in size. A fixed percentage would treat a utility and a volatile small cap alike.
- Volume alerts fire when volume is at least 2 times the 20-session median and, where the stock has enough history, also an outlier against its own last 30 sessions. A stock whose volume is routinely noisy does not alert every other day.
- You set the thresholds in the app, and choose which announcement types raise an alert. Changes apply at once, without a re-run.

**Pull: narrative vs numbers (the worked example)**
- Forward-looking revenue growth statements are taken directly from the last four earnings-call transcripts. A sentence qualifies only if it states a percentage, is about revenue or growth, looks forward-looking, and is not a reported or sequential figure. An analyst's question, and a statement about a period that had already ended on the day of the call, are ignored, because they report a result and do not make a promise.
- Each statement must match the source word for word, on the stated page. Anything that doesn't match is dropped and counted.
- When a sentence names no year, the year is worked out from the call it was said on, using references such as "H1 of FY27". "For the year" means the call's own year, and "the coming year" means the next. On a year-end call nothing is guessed.
- Each revenue statement is compared with reported figures. A single quarter is compared with the same quarter a year earlier. A full fiscal year (April to March) is compared with the year before, summed from four quarters each. A year that is still in progress is shown as pending.
- Guidance in constant currency is never compared with the stored rupee revenue. The two are different measures, so the verdict is "not comparable", not a misleading "met". This applies to companies such as Infosys, which guide in dollars.
- Margin guidance is compared with the reported operating margin (screener's operating profit over revenue). A finished year gives met or missed. A year in progress uses the quarters so far and gives on track or behind.
- Each revenue verdict is the share of the promise delivered. The bands are: met at 100% or more, nearly met at 90% or more, partly met at 50% or more, and missed below 50%. A result of 14.95% against a 15% target is 99.7%, which is "nearly met", not a miss.
- No language model is used at run time. The check is deterministic, so the same transcripts always give the same answer.

**Pull: other outputs**
- Financial snapshot and four-quarter trajectory, from the stored quarterly figures.
- An Ask box under each company. A question is answered only with sentences quoted word for word from the stored transcripts, with their pages. If the transcripts don't cover it, the answer is "Not found in source". No model is used.
- A four-quarter table with each quarter's revenue growth and reported operating margin, and the guidance in force for the fiscal year beneath it.
- Balance sheet and cash quality, by year, from screener.in's balance sheet and cash-flow tables: net worth, borrowings, debt to equity, cash from operations, and cash from operations as a share of net profit. Built and tested on a sample page; the first live check against a real screener page is pending.
- A credit scorecard at `/credit.html`. You enter debt, cash and interest expense from the annual report. It scores interest cover, net debt to EBITDA, PAT margin and EBITDA trend, and gives a rating and an underwriting view. A chart shows how the score moves as EBITDA falls or rises, at three debt levels.

## Key decisions and trade-offs

- **Data is gathered on a computer, then published to the hosted app.** Financial sites block cloud hosts from the data sources I could reach. The app keeps working when the laptop is off, because the server holds the last published data.
- **A nightly job on GitHub Actions** is configured to refresh the data each weekday at 18:30 IST. I have not yet confirmed a scheduled run has passed.
- **Models are used only on the laptop, for two small jobs.** The hosted app makes no model calls. See the Models section below.
- **EBITDA is PBT + finance costs + depreciation, as the brief defines it,** where the results filing gives those figures. Where it does not, EBITDA is screener.in's operating profit, an approximation, and the app labels which one it shows. The profit view shows where PBT and operating profit diverge, because profit can move for reasons other than operations, such as other income.
- **Growth is divided by the size of the base,** so a move from a loss to a profit is read as an improvement. A plain percentage gives the opposite sign in that case.
- **Credit thresholds and promise bands are my assumptions,** not an industry or bank standard. They are shown in the app and in the code.
- **The filing's meaning line describes the category,** not the document's content. Reading the document itself would need the full PDF text, which I did not build.

## Models: what runs where, and why

| Step | Model | Where it runs | Why |
|---|---|---|---|
| Label announcement subjects that no rule matches | Claude Haiku (`claude-haiku-5-5`) | Laptop, nightly, cached by subject | One short label per subject is a cheap, bulk task |
| One-sentence note on each promise verdict | Claude Haiku (`claude-haiku-5-5`) | Laptop, nightly, cached by claim | Plain English for an analyst. A note is kept only if every number in it appears in the inputs |
| Finding and checking management's promises | None (code) | Laptop and server | Small local models could not follow the output format (see below). Rules with word-for-word checks give the same answer each time |
| Growth, verdicts, alerts, credit score | None (code) | Server | Arithmetic is not a model's job. Each threshold is written in `server/risk.py` |

**What I tried first.** I ran Qwen 2.5 models locally through Ollama, at 1.5B, 3B and 7B parameters, to extract the promises from transcripts. The 1.5B and 3B models returned prose or tags instead of the requested list, and copied whole paragraphs as "quotes" without page numbers, so the word-for-word check dropped everything. The 7B model took too long on my laptop. I replaced the extraction with rules and kept the word-for-word check. Those experiments are in the build history.

**Status of the note step.** The note step is tested with a stand-in model client. It runs against the live model only once an Anthropic key is set on the laptop and `python -m ingest.notes --check` returns `OK`. Until then the app shows no notes. The label step has the same requirement.

## What is not finished

- **Results come mostly from screener.in.** NSE's feed carries no XBRL links, so the XBRL reader is not used. The results PDFs are read for the layouts I have checked. Only the ITC standalone income statement has been tested, against the page text as printed. The RELIANCE segment page was not usable, and one saved PDF was truncated and skipped. Any quarter read from a PDF is marked "from the results filing", and any figure that differs from screener.in by more than 1% is flagged on the card. Other companies keep screener.in's figures.
- **Management-change background from outside the filing.** The app uses the appointment filing. Where a filing has no profile, backgrounds can be entered by hand, each with a source link, and they are labelled as entered by hand. I did not add a web search, and I did not scrape LinkedIn, because it prohibits scraping.
- **Bull and bear is a selection, not an argument.** Each side shows up to four sentences from the last four transcripts, chosen by keyword and quoted word for word with its page. It does not weigh the evidence, and it does not use any model. A reader still has to judge the points against the source.
- **Not built:** business snapshot, free cash flow (needs capex from the cash-flow statement), and working-capital days (needs receivables and inventory). Screener's summary tables do not carry these figures.
- **Guidance** covers forward-looking statements from transcripts. Revenue growth and margin guidance are compared with reported figures, where the period is known and the measures match. Capex guidance is listed with its stated figure, but not checked. Annual reports are not read.
- **Where the worked example is thin.** For a company that guides in constant currency, the revenue verdicts are "not comparable", so the margin check carries the example. A sentence whose year can't be worked out is shown but not compared.
- **Any NSE ticker, on demand.** Looking up a ticker with no data queues it. The laptop ingests queued tickers at the start of its next daily run, and the page shows the queued message until then. A ticker only appears after that run, not at once.
- **Notifications when the app is closed** are built with web push: a phone that subscribes receives a notification for each new high-priority filing from the last 24 hours. They are switched on with server keys, and they work on an iPhone only after the app is added to the Home Screen. I tested delivery on a real iPhone, using a labelled test notification. A notification for a real filing is sent only when a new high-priority filing from the last 24 hours is synced. On the free hosting plan the server's disk is temporary: a redeploy erases saved phones and any changed alert settings, and an idle restart probably does too. Everything else is restored from the seed file, which carries the transcripts and figures. An uptime monitor reduces idle restarts.
- **BSE is not used.** NSE covers every demo company.
- **The NSE classification has been tested on labelled test subjects,** not on every live subject line. Subjects no rule matches are shown as low-tier press releases, so they stay visible under Routine.
- **One company, PAGEIND, did not return quarterly figures** from screener.in in the last run I checked. Its results card shows no figures. I could not fix this without its screener page.
- **Classification of live announcement subjects** is tested on labelled test subjects only. Subjects no rule matches show as low-tier press releases.

- **The promise check is verified on Infosys and TCS only.** On other companies it can show figures that are not company guidance (Dixon's rows are an example), several companies have no transcripts stored (TITAN is one), and some companies state no numeric guidance at all. Treat it as a working engine that has been checked on two companies, not on all twenty-two.

## Where I'd take it next

1. Read results figures from the results PDFs, one parser per layout, checked against screener.in.
2. Add a source for management-change backgrounds beyond the appointment filing, using a licensed data source.
3. Add free cash flow and working-capital days, using the full cash-flow statement and the balance sheet notes.
4. Check margin and capex guidance against reported figures.
5. Send push notifications when the app is closed.

Thank you for the opportunity. I'm happy to walk through any part of it.

Regards,
Aaliyah Ahmed
