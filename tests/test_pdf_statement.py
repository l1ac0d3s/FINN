"""The income-statement reader, tested on the ITC standalone page as it was printed by the probe.

Only the lines the reader uses are copied here, exactly as printed. A page that doesn't match is refused.
"""

import pytest

from ingest.pdf_statement import parse_statement

ITC_LINES = """
ITC Limited
Statement of Unaudited Standalone Financial _Results for the Quarter and Nine Months ended 31st December, 2024
(f In Crores)
Particulars 3 Months 3 Months 3 Months 9 Months 9 Months Months
31,12.2024 31.12.2023 30.09.2024 31.12.2024 31.12.2023 31.03.2024
REVENUE FROM OPERATIONS [(i)+(ii)l 1 18290.24 16864.34 19858.75 55742.01 50385.42 67292.60
PROFIT BEFORE EXCEPTIONAL ITEMS AND TAX (3-4) 5 6545.61 6520.21 6616.79 19584.01 19344.55 25632.12
PROFIT BEFORE TAX (5+6) 7 7073.57 6520.21 6616.79 20111.97 19344.55 25632.12
PROFIT FOR THE PERIOD FROM CONTINUING OPERATIONS (7-8) 9 5421.36 5418.79 4975.85 15217.14 15072.77 19910.23
PROFIT FOR THE PERIOD FROM DISCONTINUED OPERATIONS (10+11-12) (Refer Note 7) 13 216.89 153.28 102.49 416.90 329.00 511.74
PROFIT FOR THE PERIOD (9+13) 14 5638.25 5572.07 5078.34 15634.04 15401.77 20421.97
f) Finance costs 7.57 9.53 11.94 27.84 25.10 34.39
g) Depreciation and amortization expense 361.82 343.17 368.26 1085.45 1015.96 1357.20
""".strip()


def test_itc_current_quarter_is_read_with_its_period():
    figures = parse_statement(ITC_LINES)
    assert figures["period_end"] == "2024-12-31"
    assert figures["revenue"] == pytest.approx(18290.2)
    assert figures["pbt"] == pytest.approx(7073.6)
    assert figures["pat"] == pytest.approx(5638.2)   # the total for the period, not the continuing-operations line


def test_ebitda_follows_the_brief_formula():
    figures = parse_statement(ITC_LINES)
    assert figures["ebitda"] == pytest.approx(7443.0)   # 7073.57 + 7.57 + 361.82


def test_a_page_without_the_crore_unit_is_refused():
    assert parse_statement(ITC_LINES.replace("In Crores", "In Lakhs").replace("crore", "lakh")) is None


def test_a_page_missing_a_key_line_is_refused():
    without_pat = "\n".join(
        line for line in ITC_LINES.splitlines() if not line.startswith("PROFIT FOR THE PERIOD (9+13)"))
    assert parse_statement(without_pat) is None


def test_brackets_mean_a_negative_figure():
    line = "REVENUE FROM OPERATIONS 1 (100.50) 5.00 6.00 7.00 8.00 9.00"
    text = "\n".join(["(f In Crores)", "31,12.2024", "PROFIT BEFORE TAX 7 1 2 3 4 5 6",
                       "PROFIT FOR THE PERIOD (9+13) 14 1 2 3 4 5 6", line])
    assert parse_statement(text)["revenue"] == pytest.approx(-100.5)
