from btc_agent.agents.schemas import PortfolioDecision, TraderProposal
from btc_agent.agents.utils.rating import extract_rating, parse_rating


def test_ambiguous_prose_fails_closed_to_hold():
    text = "Not Buy; the evidence instead favors Sell."
    assert extract_rating(text) is None
    assert parse_rating(text) == "Hold"


def test_non_labelled_rating_phrase_fails_closed():
    assert parse_rating("The previous rating: Buy, but evidence changed.") == "Hold"


def test_explicit_rating_is_still_parsed():
    assert extract_rating("**Rating**: Sell\nReasoning") == "Sell"


def test_llm_decision_schemas_cannot_request_trade_numbers():
    forbidden = {
        "entry_price",
        "stop_loss",
        "position_sizing",
        "price_target",
        "time_horizon",
    }
    assert forbidden.isdisjoint(TraderProposal.model_fields)
    assert forbidden.isdisjoint(PortfolioDecision.model_fields)
