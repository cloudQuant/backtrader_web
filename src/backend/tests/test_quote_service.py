import threading
from types import SimpleNamespace

from app.services.quote.cache import match_cached_tick
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


def test_get_source_categories_uses_full_configured_catalog_not_live_tick_subset():
    QuoteService._instance = None
    service = QuoteService()

    categories = service.get_source_categories("CTP")

    assert {"股指期货", "贵金属", "有色金属", "黑色系", "农产品"}.issubset(categories)


def test_match_cached_tick_returns_exact_symbol_match():
    payload = {"symbol": "EURUSD", "bid_price": 1.1}
    cached = {"EURUSD": payload}

    result = match_cached_tick(cached, "EURUSD")

    assert result == payload


def test_remove_subscription_hides_default_and_add_restores_it(monkeypatch):
    QuoteService._instance = None
    service = QuoteService()
    service._custom_symbols = {"user-1": {"MT5": ["EURUSD"]}}
    service._hidden_subscriptions = {}

    monkeypatch.setattr("app.services.quote_service.save_custom_symbols", lambda data: None)
    monkeypatch.setattr("app.services.quote_service.save_hidden_subscriptions", lambda data: None)

    remaining = service.remove_subscriptions("mt5", "user-1", ["EURUSD", "GBPUSD"])

    assert remaining == []
    assert service._hidden_symbol_set("MT5", "user-1") == {"EURUSD", "GBPUSD"}

    service.add_custom_symbols("MT5", "user-1", ["EURUSD"])

    assert service._hidden_symbol_set("MT5", "user-1") == {"GBPUSD"}


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


def test_mt5_native_bid_and_ask_are_exposed_in_quote_ticks(monkeypatch):
    QuoteService._instance = None
    service = QuoteService()
    receiver = _DummyReceiver()
    service._receivers = {"MT5": receiver}
    service._subscribed_symbols = {}

    class _FakeTick:
        def get_all_data(self):
            return {"symbol": "EURUSD", "bid": 1.0842, "ask": 1.0844, "last": 1.0843}

    class _FakeSnapshot:
        def get_data(self):
            return [_FakeTick()]

    class _FakeFeed:
        def get_tick(self, symbol: str):
            assert symbol == "EURUSD"
            return _FakeSnapshot()

    manager = SimpleNamespace()
    runtime = SimpleNamespace(adapter=SimpleNamespace(feed=_FakeFeed()))
    monkeypatch.setattr(service, "_get_live_trading_manager", lambda: manager)
    monkeypatch.setattr(service, "_ensure_mt5_gateway_connected", lambda mgr: None)
    monkeypatch.setattr(service, "_get_running_workspace_context", lambda *args, **kwargs: {})
    monkeypatch.setattr(service, "_ensure_receiver", lambda source, mgr: None)
    monkeypatch.setattr(service, "_subscribe_symbols_on_gateway", lambda source, symbols: None)
    monkeypatch.setattr(
        service,
        "_get_default_symbols_for_source",
        lambda source: [{"symbol": "EURUSD", "name": "Euro", "exchange": "MT5", "category": "FX"}],
    )
    monkeypatch.setattr(service, "_find_gateway_state", lambda mgr, source: {"runtime": runtime})

    result = service.get_quotes("MT5", user_id="u1")

    assert result["ticks"][0]["bid_price"] == 1.0842
    assert result["ticks"][0]["ask_price"] == 1.0844
    assert result["ticks"][0]["last_price"] == 1.0843


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
        lambda source: [
            {"symbol": "AAPL", "name": "Apple", "exchange": "NASDAQ", "category": "科技"}
        ],
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


def test_get_quotes_uses_binance_snapshot_fallback_when_stream_cache_is_empty(monkeypatch):
    QuoteService._instance = None
    service = QuoteService()
    receiver = _DummyReceiver()
    service._receivers = {"BINANCE": receiver}
    service._subscribed_symbols = {}

    class _FakeTicker:
        def get_all_data(self):
            return {
                "ticker_symbol_name": "BTCUSDT",
                "symbol_name": "BTCUSDT",
                "server_time": 1712678400000,
                "bid_price": 68000.1,
                "ask_price": 68000.3,
                "last_price": 68000.2,
                "bid_volume": 12.0,
                "ask_volume": 10.0,
                "open_price": 67000.0,
                "high_price": 69000.0,
                "low_price": 66000.0,
                "prev_close": 67500.0,
                "volume_24h": 12345.0,
                "turnover_24h": 987654321.0,
            }

    class _FakeSnapshot:
        def get_data(self):
            return [_FakeTicker()]

    class _FakeFeed:
        def get_tick(self, symbol: str):
            assert symbol == "BTCUSDT"
            return _FakeSnapshot()

    manager = SimpleNamespace()
    runtime = SimpleNamespace(adapter=SimpleNamespace(feed=_FakeFeed()))

    monkeypatch.setattr(service, "_get_live_trading_manager", lambda: manager)
    monkeypatch.setattr(service, "_ensure_receiver", lambda source, mgr: None)
    monkeypatch.setattr(service, "_subscribe_symbols_on_gateway", lambda source, symbols: None)
    monkeypatch.setattr(
        service,
        "_get_default_symbols_for_source",
        lambda source: [
            {"symbol": "BTCUSDT", "name": "BTC 永续", "exchange": "BINANCE", "category": "加密货币"}
        ],
    )
    monkeypatch.setattr(service, "_find_gateway_state", lambda mgr, source: {"runtime": runtime})

    result = service.get_quotes("BINANCE", user_id="u1")

    assert result["total"] == 1
    tick = result["ticks"][0]
    assert tick["symbol"] == "BTCUSDT"
    assert tick["last_price"] == 68000.2
    assert tick["bid_price"] == 68000.1
    assert tick["ask_price"] == 68000.3
    assert tick["open_price"] == 67000.0
    assert tick["high_price"] == 69000.0
    assert tick["low_price"] == 66000.0
    assert tick["volume"] == 12345.0
    assert tick["turnover"] == 987654321.0
    assert tick["status"] == "normal"
    assert receiver.seeded["BTCUSDT"]["symbol"] == "BTCUSDT"


def test_snapshot_hydration_limits_gateway_requests(monkeypatch):
    QuoteService._instance = None
    service = QuoteService()
    requested: list[str] = []

    class _FakeFeed:
        def get_tick(self, symbol: str):
            requested.append(symbol)
            return {"symbol": symbol, "price": 1.0}

    monkeypatch.setattr(
        service,
        "_fetch_gateway_snapshot_tick",
        lambda source, feed, symbol: feed.get_tick(symbol),
    )

    hydrated = service._hydrate_snapshot_ticks(
        manager=SimpleNamespace(),
        source="IB_WEB",
        receiver=None,
        symbols=["AAPL", "MSFT", "NVDA"],
        cached_ticks={},
        state={"runtime": SimpleNamespace(adapter=SimpleNamespace(feed=_FakeFeed()))},
        max_snapshots=1,
    )

    assert requested == ["AAPL"]
    assert list(hydrated) == ["AAPL"]


def test_ensure_mt5_gateway_connected_skips_when_auto_connect_is_suppressed(monkeypatch):
    QuoteService._instance = None
    service = QuoteService()
    service.suppress_auto_connect("MT5")
    manager = SimpleNamespace(
        connect_gateway=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("should not connect")
        )
    )

    monkeypatch.setattr(service, "_find_gateway_state", lambda mgr, source: None)

    service._ensure_mt5_gateway_connected(manager)


def test_ensure_mt5_gateway_connected_defers_during_gateway_recovery(monkeypatch):
    QuoteService._instance = None
    service = QuoteService()
    manager = SimpleNamespace(
        is_gateway_restore_in_progress=lambda: True,
        connect_gateway=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("should not connect")
        ),
    )

    monkeypatch.setattr(service, "_find_gateway_state", lambda mgr, source: None)

    service._ensure_mt5_gateway_connected(manager)


def test_ensure_mt5_gateway_connected_resumes_after_resume_auto_connect(monkeypatch):
    QuoteService._instance = None
    service = QuoteService()
    service.suppress_auto_connect("MT5")
    service.resume_auto_connect("MT5")

    calls = []

    class _Manager:
        def connect_gateway(self, exchange_type, credentials):
            calls.append((exchange_type, credentials))
            return {"status": "connected", "gateway_key": "manual:MT5:123456"}

    monkeypatch.setattr(service, "_find_gateway_state", lambda mgr, source: None)
    monkeypatch.setattr(
        "app.services.quote_service.get_settings",
        lambda: SimpleNamespace(
            MT5_LOGIN="123456",
            MT5_PASSWORD="secret",
            MT5_WS_URI="wss://web.metatrader.app/terminal",
            MT5_SYMBOL_SUFFIX="",
        ),
    )

    service._ensure_mt5_gateway_connected(_Manager())

    assert len(calls) == 1
    assert calls[0][0] == "MT5"


def test_match_cached_tick_matches_mt5_broker_symbol_via_instrument_id_prefix():
    payload = {
        "symbol": "EURUSD",
        "instrument_id": "EURUSDm",
        "bid_price": 1.205,
        "ask_price": 1.2052,
    }
    cached = {"EURUSDm": payload}

    result = match_cached_tick(cached, "EURUSD")

    assert result == payload


def test_running_workspace_symbols_are_grouped_by_gateway_and_deduplicated(monkeypatch):
    QuoteService._instance = None
    service = QuoteService()
    state = {
        "config": SimpleNamespace(command_endpoint="tcp://127.0.0.1:5555"),
        "exchange_type": "IB_WEB",
        "instances": {"instance-a", "instance-b"},
        "manual": False,
    }
    manager = SimpleNamespace(
        _gateway_lock=threading.RLock(),
        _gateways={"ib-workspace-gateway": state},
        _instance_gateways={
            "instance-a": "ib-workspace-gateway",
            "instance-b": "ib-workspace-gateway",
        },
        list_instances=lambda user_id: [
            {
                "id": "instance-a",
                "status": "running",
                "params": {
                    "symbol": "AAPL",
                    "workspace_unit": {"workspace_id": "workspace-1"},
                },
            },
            {
                "id": "instance-b",
                "status": "running",
                "params": {
                    "symbol": "AAPL",
                    "workspace_unit": {"workspace_id": "workspace-1"},
                },
            },
        ],
    )
    monkeypatch.setattr(service, "_is_gateway_state_ready", lambda value: True)

    context = service._get_running_workspace_context(
        manager,
        "user-1",
        {"workspace-1": "IB 工作区"},
    )
    plans = service._build_quote_plans(
        manager,
        "IB_WEB",
        ["AAPL"],
        context["IB_WEB"],
    )

    assert list(plans) == ["ib-workspace-gateway"]
    assert list(plans["ib-workspace-gateway"]["symbols"]) == ["AAPL"]
    item = plans["ib-workspace-gateway"]["symbols"]["AAPL"]
    assert item["origins"] == {"subscription", "workspace"}
    assert item["workspace_names"] == {"IB 工作区"}


def test_workspace_gateway_marks_quote_source_available(monkeypatch):
    QuoteService._instance = None
    service = QuoteService()
    state = {
        "config": SimpleNamespace(command_endpoint="tcp://127.0.0.1:5555"),
        "exchange_type": "CTP",
        "instances": {"instance-ctp"},
        "manual": False,
    }
    manager = SimpleNamespace(
        _gateway_lock=threading.RLock(),
        _gateways={"ctp-workspace-gateway": state},
        _instance_gateways={"instance-ctp": "ctp-workspace-gateway"},
        list_instances=lambda user_id: [
            {
                "id": "instance-ctp",
                "status": "running",
                "params": {
                    "symbol": "RB2510",
                    "workspace_unit": {"workspace_id": "workspace-ctp"},
                },
            },
        ],
    )
    monkeypatch.setattr(service, "_get_live_trading_manager", lambda: manager)
    monkeypatch.setattr(service, "_ensure_mt5_gateway_connected", lambda value: None)
    monkeypatch.setattr(service, "_is_gateway_state_ready", lambda value: True)
    monkeypatch.setattr(service, "_ensure_receiver_for_gateway", lambda *args: None)
    subscriptions: list[tuple[str, str, list[str]]] = []
    monkeypatch.setattr(
        service,
        "_subscribe_symbols_on_gateway_state",
        lambda source, gateway_key, state, symbols: subscriptions.append(
            (source, gateway_key, symbols)
        ),
    )

    sources = service.get_data_sources("user-1", {"workspace-ctp": "CTP 工作区"})
    ctp = next(item for item in sources if item["source"] == "CTP")

    assert ctp["status"] == "available"
    assert ctp["gateway_count"] == 1
    assert ctp["workspace_count"] == 1
    assert ctp["running_symbol_count"] == 1
    assert ctp["workspaces"][0]["symbols"] == ["RB2510"]
    assert subscriptions == [("CTP", "ctp-workspace-gateway", ["RB2510"])]
