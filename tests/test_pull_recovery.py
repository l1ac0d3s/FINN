from server.pull import growth_from_quote


def test_growth_is_read_only_from_quotes_that_talk_about_growth():
    assert growth_from_quote("Revenue growth was at 1.9% in constant currency") == 1.9
    assert growth_from_quote("AI revenue now accounts for 10.5% of our revenues") is None


def test_sequential_figures_are_never_read_as_year_on_year_growth():
    assert growth_from_quote("Revenue growth was 1.2% sequentially") is None
