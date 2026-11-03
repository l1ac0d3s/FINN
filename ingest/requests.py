"""Tickers that were looked up in the app but have no data yet.

The server keeps the queue. At the start of each daily run the laptop collects it, adds those tickers to
the run, and clears them once the run has finished. Any problem reaching the server just means no extra
tickers that day; the portfolio run is never stopped by it.
"""

import requests

from ingest import config


def fetch_queued(session):
    """Queued tickers from the server, or an empty list if the server can't be reached."""
    if not config.SYNC_TOKEN:
        return []
    try:
        resp = session.get(
            config.SERVER_URL.rstrip("/") + "/api/requests",
            headers={"Authorization": f"Bearer {config.SYNC_TOKEN}"}, timeout=20,
        )
        resp.raise_for_status()
        return [t for t in resp.json().get("tickers", []) if isinstance(t, str)]
    except (requests.RequestException, ValueError):
        return []


def clear_queued(session, tickers):
    """Remove tickers the run has finished with. Failures are ignored; they are cleared on the next run."""
    if not tickers or not config.SYNC_TOKEN:
        return
    try:
        session.post(
            config.SERVER_URL.rstrip("/") + "/api/requests/clear",
            json={"tickers": tickers},
            headers={"Authorization": f"Bearer {config.SYNC_TOKEN}"}, timeout=20,
        ).raise_for_status()
    except requests.RequestException:
        pass
