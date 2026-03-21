from app.services.quote_service import QuoteService


def test_match_cached_tick_returns_exact_symbol_match():
    payload = {"symbol": "EURUSD", "bid_price": 1.1}
    cached = {"EURUSD": payload}

    result = QuoteService._match_cached_tick(cached, "EURUSD")

    assert result == payload


def test_match_cached_tick_matches_mt5_broker_symbol_via_instrument_id_prefix():
    payload = {
        "symbol": "EURUSD",
        "instrument_id": "EURUSDm",
        "bid_price": 1.205,
        "ask_price": 1.2052,
    }
    cached = {"EURUSDm": payload}

    result = QuoteService._match_cached_tick(cached, "EURUSD")

    assert result == payload
