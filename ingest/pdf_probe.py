"""Print the lines of a results PDF that carry the figures the parser needs.

    python -m ingest.pdf_probe tests\\fixtures\\results_1.pdf

Read-only. It prints the page count, then each matching line with its page number, so the parser can be
built from real wording and layout. Paste the whole output back.
"""

import re
import sys

from pypdf import PdfReader

KEYWORDS = re.compile(
    r"revenue from operations|total income|profit before tax|profit before exceptional|"
    r"profit after tax|profit for the (period|year)|net profit|finance costs|finance cost|"
    r"depreciation|amortisation|amortization|\bEBITDA\b|ended|quarter",
    re.I,
)
MAX_LINES = 60   # keeps the output readable; the first matches are the ones that matter


def main(path):
    reader = PdfReader(path)
    print(f"{path}: {len(reader.pages)} pages")
    shown = 0
    for number, page in enumerate(reader.pages, start=1):
        for line in (page.extract_text() or "").splitlines():
            line = line.strip()
            if line and KEYWORDS.search(line):
                print(f"p{number}: {line}")
                shown += 1
                if shown >= MAX_LINES:
                    print(f"... stopped after {MAX_LINES} matching lines")
                    return


STATEMENT = re.compile(r"revenue from operations", re.I)
PROFIT = re.compile(r"profit before tax", re.I)


def statement_page(path):
    """Print the whole page that holds the consolidated income statement: the first page that has both
    'revenue from operations' and 'profit before tax'. Values sit on these lines, not the label lines."""
    reader = PdfReader(path)
    for number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if STATEMENT.search(text) and PROFIT.search(text):
            print(f"--- statement page {number} of {len(reader.pages)} ---")
            print(text)
            return
    print("no page has both 'revenue from operations' and 'profit before tax'")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m ingest.pdf_probe <file.pdf> [--statement]")
    if "--statement" in sys.argv:
        statement_page(sys.argv[1])
    else:
        main(sys.argv[1])
