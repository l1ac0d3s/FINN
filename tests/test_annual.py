"""Balance sheet and cash quality, read from a company page's sections.

The HTML below is a sample written to match screener's usual section layout. It is NOT a saved screener
page. The parser is checked on real pages during the live run.
"""

import pytest

from ingest.annual import clean_label, metrics, parse_annual, store_annual, view
from shared.schema import connect

SAMPLE = """
<html><body>
<section id="balance-sheet"><table>
  <thead><tr><th></th><th>Mar 2024</th><th>Mar 2025</th></tr></thead>
  <tbody>
    <tr><td>Equity Capital +</td><td>100</td><td>100</td></tr>
    <tr><td>Reserves</td><td>800</td><td>900</td></tr>
    <tr><td>Borrowings +</td><td>450</td><td>400</td></tr>
    <tr><td>Total Assets</td><td>1,900</td><td>2,000</td></tr>
  </tbody></table></section>
<section id="cash-flow"><table>
  <thead><tr><th></th><th>Mar 2024</th><th>Mar 2025</th></tr></thead>
  <tbody>
    <tr><td>Cash from Operating Activity +</td><td>180</td><td>250</td></tr>
  </tbody></table></section>
<section id="profit-loss"><table>
  <thead><tr><th></th><th>Mar 2024</th><th>Mar 2025</th></tr></thead>
  <tbody>
    <tr><td>Net Profit +</td><td>150</td><td>200</td></tr>
  </tbody></table></section>
</body></html>
"""


def test_labels_are_cleaned_of_plus_and_minus_signs():
    assert clean_label("Cash from Operating Activity +") == "cash from operating activity"
    assert clean_label("Borrowings +") == "borrowings"


def test_parses_each_year_from_the_three_sections():
    years = parse_annual(SAMPLE)
    assert years["2025"] == {"equity": 100, "reserves": 900, "borrowings": 400,
                             "total_assets": 2000, "cfo": 250, "pat": 200}
    assert years["2024"]["cfo"] == 180


def test_metrics_compute_net_worth_debt_to_equity_and_cash_quality():
    m = metrics(parse_annual(SAMPLE)["2025"])
    assert m["net_worth"] == 1000
    assert m["debt_to_equity_x"] == pytest.approx(0.4)
    assert m["cash_quality_pct"] == pytest.approx(125.0)   # 250 / 200


def test_a_page_without_these_sections_gives_no_figures_and_no_error():
    assert parse_annual("<html><body><p>nothing here</p></body></html>") == {}


def test_store_annual_writes_rows_and_view_reads_them_back(tmp_path):
    conn = connect(tmp_path / "ingest.db")
    assert store_annual(conn, "INFY", SAMPLE) == 2
    rows = [dict(r) for r in conn.execute("SELECT * FROM annual_figures WHERE ticker = 'INFY'").fetchall()]
    years = view(rows)
    assert [y["year"] for y in years] == ["2024", "2025"]
    assert years[1]["net_worth"] == 1000


def test_store_annual_never_raises_on_broken_input(tmp_path):
    conn = connect(tmp_path / "ingest.db")
    assert store_annual(conn, "INFY", None) == 0
