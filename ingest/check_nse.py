"""Check what NSE sends for one company: its field names, and whether a results filing has an XBRL link.

    python -m ingest.check_nse RELIANCE

Run it from the repository root on the laptop, which can reach NSE. Paste the whole output back.
"""

import sys

import requests

from ingest.announcements import fetch_nse, find_xbrl


def main(symbol):
    items = fetch_nse(requests.Session(), symbol)
    print(f"{len(items)} announcements for {symbol}")
    if items:
        print("field names in the first announcement:")
        print(sorted(items[0].keys()))
    results = [i for i in items if "result" in str(i.get("desc", "")).lower()]
    print(f"{len(results)} results announcements")
    for item in results[:5]:
        print("-", item.get("desc"), "| xbrl found:", find_xbrl(item))
        print("   link-like fields:", {k: v for k, v in item.items()
                                       if isinstance(v, str) and v.startswith("http")})


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "RELIANCE")
