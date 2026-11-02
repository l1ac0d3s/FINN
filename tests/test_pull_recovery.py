from server.llm import parse_json_list
from server.pull import growth_from_quote


def test_claims_are_kept_when_the_reply_is_cut_off_mid_list():
    reply = ('```json\n[{"quote": "Revenue growth was at 1.9%.", "page": 28, "period": "H1 FY26"},\n'
             '{"quote": "Revenue growth was 1.3% in constant currency", "page": 28, "pe')
    claims = parse_json_list(reply)
    assert [c["page"] for c in claims] == [28]


def test_growth_is_read_only_from_quotes_that_talk_about_growth():
    assert growth_from_quote("Revenue growth was at 1.9% in constant currency") == 1.9
    assert growth_from_quote("AI revenue now accounts for 10.5% of our revenues") is None
