from types import SimpleNamespace

from app.services.quote_service import QuoteService


def test_get_default_symbols_for_mt5_prefers_major_fx_and_avoids_indices_and_oil(monkeypatch):
    QuoteService._instance = None
    service = QuoteService()

    monkeypatch.setattr(service, "_get_live_trading_manager", lambda: None)

    symbols = [item["symbol"] for item in service._get_default_symbols_for_source("MT5")]

    assert "EURUSD" in symbols
    assert "GBPUSD" in symbols
    assert "USDJPY" in symbols
    assert "XAUUSD" in symbols
    assert "US30" not in symbols
    assert "NAS100" not in symbols
    assert "USOIL" not in symbols


def test_match_cached_tick_returns_exact_symbol_match():
    payload = {"symbol": "EURUSD", "bid_price": 1.1}
    cached = {"EURUSD": payload}

    result = QuoteService._match_cached_tick(cached, "EURUSD")

    assert result == payload


def test_subscribe_symbols_on_gateway_tracks_only_mt5_accepted_symbols(monkeypatch):
    QuoteService._instance = None
    service = QuoteService()
    service._subscribed_symbols = {}

    manager = SimpleNamespace()
    config = SimpleNamespace(command_endpoint="tcp://127.0.0.1:5555")

    monkeypatch.setattr(service, "_get_live_trading_manager", lambda: manager)
    monkeypatch.setattr(service, "_find_gateway_config", lambda mgr, source: config)
    monkeypatch.setattr(
        service,
        "_send_gateway_command",
        lambda *args, **kwargs: {
            "accepted": ["EURUSD", "XAUUSD"],
            "skipped_symbols": ["NAS100"],
        },
    )

    service._subscribe_symbols_on_gateway("MT5", ["EURUSD", "NAS100", "XAUUSD"])

    assert service._subscribed_symbols["MT5"] == {"EURUSD", "XAUUSD"}


class _DummyReceiver:
    def __init__(self) -> None:
        self.is_alive = False
        self.seeded: dict[str, dict] = {}

    def seed_tick(self, symbol: str, payload: dict) -> None:
        self.seeded[symbol] = dict(payload)


def test_get_quotes_uses_ib_web_snapshot_fallback_when_stream_cache_is_empty(monkeypatch):
    QuoteService._instance = None
    service = QuoteService()
    receiver = _DummyReceiver()
    service._receivers = {"IB_WEB": receiver}
    service._subscribed_symbols = {}

    class _FakeFeed:
        def get_tick(self, symbol: str):
            assert symbol == "AAPL"
            return {
                "31": "212.34",
                "84": "212.30",
                "86": "212.38",
                "87": "100",
                "conid": "265598",
                "listingExchange": "NASDAQ",
            }

    manager = SimpleNamespace()
    runtime = SimpleNamespace(adapter=SimpleNamespace(feed=_FakeFeed()))

    monkeypatch.setattr(service, "_get_live_trading_manager", lambda: manager)
    monkeypatch.setattr(service, "_ensure_receiver", lambda source, mgr: None)
    monkeypatch.setattr(service, "_subscribe_symbols_on_gateway", lambda source, symbols: None)
    monkeypatch.setattr(
        service,
        "_get_default_symbols_for_source",
        lambda source: [{"symbol": "AAPL", "name": "Apple", "exchange": "NASDAQ", "category": "科技"}],
    )
    monkeypatch.setattr(service, "_find_gateway_state", lambda mgr, source: {"runtime": runtime})

    result = service.get_quotes("IB_WEB", user_id="u1")

    assert result["total"] == 1
    tick = result["ticks"][0]
    assert tick["symbol"] == "AAPL"
    assert tick["last_price"] == 212.34
    assert tick["bid_price"] == 212.3
    assert tick["ask_price"] == 212.38
    assert tick["volume"] == 100.0
    assert tick["status"] == "normal"
    assert receiver.seeded["AAPL"]["instrument_id"] == "265598"


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
