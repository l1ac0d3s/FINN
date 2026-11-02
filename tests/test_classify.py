"""Classification tests on labelled subject lines.

NOTE: these subjects are written to match the reference document's categories.
They are not copied from a live NSE feed. Validate against real subjects once
the ingest runs on your machine, and add the misses here.
"""

import pytest

from ingest.classify import classify_rules, tier_for

LABELLED = [
    ("Financial Results for the quarter and half year ended 30.09.2026", "results", "high"),
    ("Outcome of Board Meeting - approval of unaudited financial results", "results", "high"),
    ("Intimation of Board Meeting to consider financial results", "results", "low"),
    ("Publication of extract of financial results in newspaper", "results", "low"),
    ("Transcript of Earnings Call held on 25.10.2026", "earnings_call", "medium"),
    ("Intimation of Earnings Call", "earnings_call", "low"),
    ("Acquisition of 51% stake in XYZ Pvt Ltd", "M&A", "high"),
    ("Scheme of Amalgamation approved by the board", "M&A", "high"),
    ("Resignation of Chief Financial Officer", "management_change", "high"),
    ("Appointment of Mr. A as Managing Director", "management_change", "high"),
    ("Penalty imposed by SEBI", "litigation", "high"),
    ("Order received from NCLT", "litigation", "high"),
    ("Rights issue of equity shares", "fund_raise", "high"),
    ("Preferential allotment of shares to promoter group", "fund_raise", "high"),
    ("Pledge of shares by promoter", "pledging", "high"),
    ("Credit rating downgraded by CRISIL", "credit_rating", "high"),
    ("Credit rating reaffirmed by ICRA", "credit_rating", "medium"),
    ("Disclosure under Regulation 7(2) of SEBI PIT", "insider_trading", "medium"),
    ("Bonus issue in the ratio of 1:1 record date 10.11.2026", "bonus_split", "medium"),
    ("Recommendation of final dividend, record date", "dividend", "medium"),
    ("Capex of Rs 2,000 crore for new plant", "capex", "medium"),
    ("Postal ballot notice", "postal_ballot", "low"),
    ("Notice of Annual General Meeting", "agm_egm", "low"),
    ("Analyst meet schedule", "investor_meetings", "low"),
    ("Allotment of ESOP shares under ESOP scheme", "unclassified", "hidden"),
    ("Appointment of Secretarial Auditor", "unclassified", "hidden"),
    ("Compliance certificate under Regulation 40(9)", "unclassified", "hidden"),
    ("Shareholding pattern for quarter ended", "unclassified", "hidden"),
    ("Clarification on news article", "press_release", "low"),
    ("Bagged order worth Rs 800 crore", "press_release", "low"),
    ("Partnership with XYZ for launch of product", "press_release", "low"),
]


@pytest.mark.parametrize("subject, category, tier", LABELLED)
def test_rules_and_tier(subject, category, tier):
    got = classify_rules(subject)
    assert got == category, f"{subject!r}: got {got}"
    assert tier_for(got, subject) == tier


def test_unmatched_subject_returns_none():
    assert classify_rules("Miscellaneous update") is None
