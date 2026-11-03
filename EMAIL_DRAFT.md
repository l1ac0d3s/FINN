To: assessment@enam.com
Subject: ENAM - IIT screening - 2027

Dear ENAM team,

Please find my submission for the FINN build challenge.

Links
- Live prototype (mobile-friendly): https://finn-wq09.onrender.com
  The app runs on a free hosting plan, so the first visit can take up to a minute.
- Repository: https://github.com/l1ac0d3s/FINN
- AI build history: https://claude.ai/code/session_01A1LVKziQJcCEW5rvXbFFn9

What it does
FINN is a mobile-first investor filter with a push view and a pull view.
Push: a digest for 24 hours, 3 days, 7 days or a custom period, with filings prioritised into High, Medium,
Routine and Hidden, and a morning brief that asks one question per important filing. Management changes show the
person's profile from the appointment filing, or an entry I made by hand with its source link. Results cards show
revenue, EBITDA, PBT and PAT with QoQ and YoY, and compare operating profit with PBT. Price alerts use a z-score
against each stock's own last 30 sessions, so a utility and a volatile small cap are judged on their own behaviour.
Notifications reach a subscribed phone, including when the app is closed.
Pull: promised versus delivered. Forward-looking statements are taken from the earnings-call transcripts, each
checked word for word against its page. Revenue guidance is compared with reported growth, margin guidance with the
reported operating margin, and each is graded by the share of the promise delivered. A balance sheet and cash
quality view, bull and bear points quoted from the transcripts, and a credit scorecard with a sensitivity chart.

Key decisions
- The hosted app makes no model calls. Growth, verdicts, alerts and the credit score are code, and every threshold
  is written in the repository. Small local models could not follow the output format, so I used rules and kept the
  word-for-word check. Optional Claude Haiku steps on the laptop (plain-English notes, labels) are not enabled in the
  submitted data.
- Guidance in constant currency, such as Infosys's, is marked "not comparable" with rupee revenue, instead of showing
  a misleading "met".
- EBITDA is PBT + finance costs + depreciation where a results filing gives them, otherwise screener.in's operating
  profit, and the app says which.

Not built
- Results figures mostly come from screener.in. Results PDFs are read only for the layouts I have checked.
- Management backgrounds beyond the appointment filing and my hand entries. I did not scrape LinkedIn.
- Business snapshot, free cash flow and working-capital days, and BSE data.
- On the free hosting plan, saved phones and changed alert settings are lost when the server redeploys.

The full write-up, including the limits, is in the attached COVERING_NOTE.md. The README explains how to run and
deploy it.

Thank you for the opportunity. I'm happy to walk through any part of it.

Regards,
[YOUR NAME]
[YOUR PHONE]
