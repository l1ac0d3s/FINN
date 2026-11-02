To: assessment@enam.com
Subject: ENAM - IIT screening - 2027

Dear ENAM team,

Please find my submission for the FINN build challenge.

Live prototype (mobile-friendly web app): https://finn-wq09.onrender.com
Repository: https://github.com/l1ac0d3s/FINN
AI build history: https://claude.ai/code/session_01A1LVKziQJcCEW5rvXbFFn9

---

## What I built

FINN is a mobile-first web app with two modes. Push shows what changed in an 18-company portfolio plus 4 ad-hoc tickers: a time-windowed digest, announcements sorted into priority tiers, price and volume alerts with configurable thresholds, and results cards with QoQ and YoY growth. Every filing card shows how the stock moved on the next session. Pull runs a narrative-vs-numbers analysis on one company, grounded in earnings-call transcripts.

## Key decisions and trade-offs

- **Rules before models:** classification uses the 18 reference categories from your companion document. A model is called only for unmatched subjects, keeping cost near zero.
- **Verdicts from figures, not the model:** the model extracts verbatim quotes; claims that fail the quote check are dropped. Verdicts compare against reported financials.
- **Ingest on my machine, serve from the cloud:** the financial data sites are reachable from a normal network but not from cloud sandboxes, so the laptop does the ingest and the server only stores and serves.
- **Free tier throughout:** Hugging Face free model for the pull feature, Render free plan for hosting, no spend required.

## What I left out

Management-change bios (no reliable source), BSE fallback, and the other pull outputs (guidance, cash quality, balance sheet, trajectory, bull vs bear). The narrative-vs-numbers is the worked example the brief asks for.

## Where I'd take it next

1. Run the claims check on all 22 companies and tune the prompt.
2. Add the other pull outputs, starting with guidance and cash quality.
3. Move ingest to a scheduled job (no laptop dependency).
4. Background push notifications for high-priority filings.

---

The full covering note is in the repository at COVERING_NOTE.md.

Thank you for the opportunity. Please reply if you would like anything clarified.

Regards,
[YOUR NAME]
[YOUR PHONE]
