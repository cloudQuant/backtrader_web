"""
Quote service for the unified quote display page.

Architecture
~~~~~~~~~~~~
bt_api_py  GatewayRuntime  (per exchange)
   ├─ market_socket  (ZMQ PUB) → publishes GatewayTick as JSON
   ├─ event_socket   (ZMQ PUB)
   └─ command_socket (ZMQ ROUTER) → accepts subscribe / health / …

backtrader_web  QuoteService
   ├─ discovers active gateways via LiveTradingManager._gateways
   ├─ connects ZMQ SUB to each gateway's market_endpoint
   ├─ sends "subscribe" commands via ZMQ DEALER to command_endpoint
   ├─ caches latest GatewayTick per (source, symbol) in memory
   └─ serves cached ticks to the frontend via REST API
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistent storage for custom symbols
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).resolve().parents[4] / "data"
_CUSTOM_SYMBOLS_FILE = _DATA_DIR / "quote_custom_symbols.json"


def _load_custom_symbols() -> dict[str, dict[str, list[str]]]:
    """Load custom symbols from disk. Returns {user_id: {source: [symbols]}}."""
    try:
        if _CUSTOM_SYMBOLS_FILE.exists():
            data = json.loads(_CUSTOM_SYMBOLS_FILE.read_text("utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        logger.exception("Failed to load custom symbols from %s", _CUSTOM_SYMBOLS_FILE)
    return {}


def _save_custom_symbols(data: dict[str, dict[str, list[str]]]) -> None:
    """Persist custom symbols to disk."""
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        _CUSTOM_SYMBOLS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), "utf-8",
        )
    except Exception:
        logger.exception("Failed to save custom symbols to %s", _CUSTOM_SYMBOLS_FILE)

# ---------------------------------------------------------------------------
# Data-source registry:  source_id -> { label, capabilities }
# ---------------------------------------------------------------------------

_SOURCE_REGISTRY: list[dict[str, Any]] = [
    {
        "source": "CTP",
        "source_label": "CTP",
        "capabilities": ["quote", "search", "chart"],
    },
    {
        "source": "IB_WEB",
        "source_label": "IB",
        "capabilities": ["quote", "search", "chart"],
    },
    {
        "source": "MT5",
        "source_label": "MT5",
        "capabilities": ["quote", "search", "chart"],
    },
    {
        "source": "BINANCE",
        "source_label": "Binance",
        "capabilities": ["quote", "search"],
    },
    {
        "source": "OKX",
        "source_label": "OKX",
        "capabilities": ["quote", "search"],
    },
]

_SOURCE_TO_LABEL: dict[str, str] = {s["source"]: s["source_label"] for s in _SOURCE_REGISTRY}

# ---------------------------------------------------------------------------
# Default symbols per data source
# ---------------------------------------------------------------------------

_DEFAULT_SYMBOLS: dict[str, list[dict[str, str]]] = {
    "CTP": [
        {"symbol": "IF2406", "name": "沪深300主力", "exchange": "CFFEX", "category": "股指期货"},
        {"symbol": "IC2406", "name": "中证500主力", "exchange": "CFFEX", "category": "股指期货"},
        {"symbol": "IH2406", "name": "上证50主力", "exchange": "CFFEX", "category": "股指期货"},
        {"symbol": "IM2406", "name": "中证1000主力", "exchange": "CFFEX", "category": "股指期货"},
        {"symbol": "au2406", "name": "黄金主力", "exchange": "SHFE", "category": "贵金属"},
        {"symbol": "ag2406", "name": "白银主力", "exchange": "SHFE", "category": "贵金属"},
        {"symbol": "cu2406", "name": "铜主力", "exchange": "SHFE", "category": "有色金属"},
        {"symbol": "rb2410", "name": "螺纹钢主力", "exchange": "SHFE", "category": "黑色系"},
        {"symbol": "i2409", "name": "铁矿石主力", "exchange": "DCE", "category": "黑色系"},
        {"symbol": "m2409", "name": "豆粕主力", "exchange": "DCE", "category": "农产品"},
    ],
    "IB_WEB": [
        {"symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "category": "科技"},
        {"symbol": "MSFT", "name": "Microsoft Corp.", "exchange": "NASDAQ", "category": "科技"},
        {"symbol": "GOOGL", "name": "Alphabet Inc.", "exchange": "NASDAQ", "category": "科技"},
        {"symbol": "AMZN", "name": "Amazon.com Inc.", "exchange": "NASDAQ", "category": "科技"},
        {"symbol": "TSLA", "name": "Tesla Inc.", "exchange": "NASDAQ", "category": "汽车"},
        {"symbol": "NVDA", "name": "NVIDIA Corp.", "exchange": "NASDAQ", "category": "半导体"},
        {"symbol": "META", "name": "Meta Platforms", "exchange": "NASDAQ", "category": "科技"},
        {"symbol": "SPY", "name": "S&P 500 ETF", "exchange": "NYSE", "category": "ETF"},
        {"symbol": "QQQ", "name": "Nasdaq 100 ETF", "exchange": "NASDAQ", "category": "ETF"},
        {"symbol": "ES", "name": "E-mini S&P 500", "exchange": "CME", "category": "股指期货"},
    ],
    "MT5": [
        {"symbol": "XAUUSD", "name": "黄金/美元", "exchange": "FOREX", "category": "贵金属"},
        {"symbol": "EURUSD", "name": "欧元/美元", "exchange": "FOREX", "category": "外汇"},
        {"symbol": "GBPUSD", "name": "英镑/美元", "exchange": "FOREX", "category": "外汇"},
        {"symbol": "USDJPY", "name": "美元/日元", "exchange": "FOREX", "category": "外汇"},
        {"symbol": "AUDUSD", "name": "澳元/美元", "exchange": "FOREX", "category": "外汇"},
        {"symbol": "USDCAD", "name": "美元/加元", "exchange": "FOREX", "category": "外汇"},
        {"symbol": "XAGUSD", "name": "白银/美元", "exchange": "FOREX", "category": "贵金属"},
        {"symbol": "US30", "name": "道琼斯30", "exchange": "INDEX", "category": "指数"},
        {"symbol": "NAS100", "name": "纳斯达克100", "exchange": "INDEX", "category": "指数"},
        {"symbol": "USOIL", "name": "美原油", "exchange": "COMMODITY", "category": "能源"},
    ],
    "BINANCE": [
        {"symbol": "BTCUSDT", "name": "比特币/USDT", "exchange": "BINANCE", "category": "加密货币"},
        {"symbol": "ETHUSDT", "name": "以太坊/USDT", "exchange": "BINANCE", "category": "加密货币"},
        {"symbol": "BNBUSDT", "name": "BNB/USDT", "exchange": "BINANCE", "category": "加密货币"},
        {"symbol": "SOLUSDT", "name": "Solana/USDT", "exchange": "BINANCE", "category": "加密货币"},
        {"symbol": "XRPUSDT", "name": "XRP/USDT", "exchange": "BINANCE", "category": "加密货币"},
    ],
    "OKX": [
        {"symbol": "BTC-USDT", "name": "比特币/USDT", "exchange": "OKX", "category": "加密货币"},
        {"symbol": "ETH-USDT", "name": "以太坊/USDT", "exchange": "OKX", "category": "加密货币"},
        {"symbol": "OKB-USDT", "name": "OKB/USDT", "exchange": "OKX", "category": "加密货币"},
        {"symbol": "SOL-USDT", "name": "Solana/USDT", "exchange": "OKX", "category": "加密货币"},
        {"symbol": "DOGE-USDT", "name": "狗狗币/USDT", "exchange": "OKX", "category": "加密货币"},
    ],
}

_DEFAULT_ASSET_TYPES: dict[str, str] = {
    "CTP": "FUTURE",
    "IB_WEB": "STK",
    "MT5": "OTC",
    "BINANCE": "SWAP",
    "OKX": "SWAP",
}

_DEFAULT_SYMBOLS_BY_ASSET: dict[tuple[str, str], list[dict[str, str]]] = {
    ("CTP", "FUTURE"): _DEFAULT_SYMBOLS["CTP"],
    ("IB_WEB", "STK"): _DEFAULT_SYMBOLS["IB_WEB"],
    ("IB_WEB", "FUT"): [
        {"symbol": "ES", "name": "E-mini S&P 500", "exchange": "CME", "category": "股指期货"},
        {"symbol": "NQ", "name": "E-mini Nasdaq 100", "exchange": "CME", "category": "股指期货"},
        {"symbol": "YM", "name": "E-mini Dow Jones", "exchange": "CBOT", "category": "股指期货"},
        {"symbol": "RTY", "name": "E-mini Russell 2000", "exchange": "CME", "category": "股指期货"},
        {"symbol": "CL", "name": "WTI 原油", "exchange": "NYMEX", "category": "能源"},
    ],
    ("MT5", "OTC"): _DEFAULT_SYMBOLS["MT5"],
    ("BINANCE", "SPOT"): _DEFAULT_SYMBOLS["BINANCE"],
    ("BINANCE", "SWAP"): [
        {"symbol": "BTCUSDT", "name": "BTC 永续", "exchange": "BINANCE", "category": "加密货币"},
        {"symbol": "ETHUSDT", "name": "ETH 永续", "exchange": "BINANCE", "category": "加密货币"},
        {"symbol": "BNBUSDT", "name": "BNB 永续", "exchange": "BINANCE", "category": "加密货币"},
        {"symbol": "SOLUSDT", "name": "SOL 永续", "exchange": "BINANCE", "category": "加密货币"},
        {"symbol": "XRPUSDT", "name": "XRP 永续", "exchange": "BINANCE", "category": "加密货币"},
    ],
    ("OKX", "SPOT"): _DEFAULT_SYMBOLS["OKX"],
    ("OKX", "SWAP"): [
        {"symbol": "BTC-USDT-SWAP", "name": "BTC 永续", "exchange": "OKX", "category": "加密货币"},
        {"symbol": "ETH-USDT-SWAP", "name": "ETH 永续", "exchange": "OKX", "category": "加密货币"},
        {"symbol": "SOL-USDT-SWAP", "name": "SOL 永续", "exchange": "OKX", "category": "加密货币"},
        {"symbol": "DOGE-USDT-SWAP", "name": "DOGE 永续", "exchange": "OKX", "category": "加密货币"},
        {"symbol": "LTC-USDT-SWAP", "name": "LTC 永续", "exchange": "OKX", "category": "加密货币"},
    ],
}


# ===================================================================
# ZMQ tick receiver — one per gateway
# ===================================================================

class _ZmqTickReceiver:
    """Background thread that SUBscribes to a GatewayRuntime's market_endpoint
    and caches the latest GatewayTick per symbol."""

    def __init__(self, source: str, market_endpoint: str) -> None:
        self.source = source
        self.market_endpoint = market_endpoint
        self._tick_cache: dict[str, dict[str, Any]] = {}  # symbol -> raw tick dict
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    # -- lifecycle --

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._recv_loop, daemon=True,
            name=f"quote-zmq-{self.source}",
        )
        self._thread.start()
        logger.info("ZMQ tick receiver started for %s @ %s", self.source, self.market_endpoint)

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("ZMQ tick receiver stopped for %s", self.source)

    @property
    def is_alive(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    # -- data access --

    def get_tick(self, symbol: str) -> dict[str, Any] | None:
        with self._lock:
            return self._tick_cache.get(symbol)

    def get_all_ticks(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return dict(self._tick_cache)

    # -- internal --

    def _recv_loop(self) -> None:
        """Connect ZMQ SUB and drain ticks into cache."""
        try:
            import zmq
        except ImportError:
            logger.warning("pyzmq not installed; ZMQ tick receiver disabled for %s", self.source)
            self._running = False
            return

        ctx = zmq.Context.instance()
        sock = ctx.socket(zmq.SUB)
        sock.setsockopt(zmq.SUBSCRIBE, b"")
        sock.setsockopt(zmq.RCVTIMEO, 500)  # 500 ms timeout so we can check _running
        try:
            sock.connect(self.market_endpoint)
        except zmq.ZMQError as exc:
            logger.error("Cannot connect ZMQ SUB to %s: %s", self.market_endpoint, exc)
            self._running = False
            sock.close()
            return

        logger.info("ZMQ SUB connected to %s for %s", self.market_endpoint, self.source)
        try:
            while self._running:
                try:
                    raw = sock.recv()
                except zmq.Again:
                    continue
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                symbol = payload.get("symbol") or payload.get("instrument_id") or ""
                if not symbol:
                    continue
                with self._lock:
                    self._tick_cache[symbol] = payload
        finally:
            sock.close()
            self._running = False


# ===================================================================
# QuoteService
# ===================================================================

class QuoteService:
    """Singleton service for quote page operations.

    Discovers active bt_api_py gateways via ``LiveTradingManager``,
    attaches ZMQ SUB receivers to their ``market_endpoint``, caches
    incoming ``GatewayTick`` payloads, and serves them to the frontend.
    """

    _instance: QuoteService | None = None
    _lock = threading.Lock()

    def __new__(cls) -> QuoteService:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._init_state()
                    cls._instance = inst
        return cls._instance

    def _init_state(self) -> None:
        # custom symbols: {user_id: {source: [symbol, ...]}}
        self._custom_symbols: dict[str, dict[str, list[str]]] = _load_custom_symbols()
        # ZMQ receivers: {source: _ZmqTickReceiver}
        self._receivers: dict[str, _ZmqTickReceiver] = {}
        # Symbols we have already asked gateways to subscribe
        self._subscribed_symbols: dict[str, set[str]] = {}

    # ------------------------------------------------------------------
    # Data-source status
    # ------------------------------------------------------------------

    def get_data_sources(self) -> list[dict[str, Any]]:
        """Return all data sources with their current status."""
        manager = self._get_live_trading_manager()
        connected_gateways = self._get_connected_gateway_exchanges(manager)

        results = []
        for reg in _SOURCE_REGISTRY:
            source = reg["source"]
            label = reg["source_label"]
            caps = reg["capabilities"]

            if not caps:
                status = "unavailable"
                msg = "接入中，暂不可用"
            elif source in connected_gateways and self._is_source_ready(manager, source):
                status = "available"
                msg = None
                self._ensure_receiver(source, manager)
            elif source in connected_gateways:
                status = "not_connected"
                msg = "网关已启动，但行情通道尚未就绪"
            else:
                status = "not_connected"
                msg = "网关未连接，请前往 Gateway 状态页连接"

            results.append({
                "source": source,
                "source_label": label,
                "status": status,
                "status_message": msg,
                "capabilities": caps,
            })
        return results

    # ------------------------------------------------------------------
    # Symbols
    # ------------------------------------------------------------------

    def get_symbols(self, source: str, user_id: str) -> dict[str, Any]:
        """Return default + custom symbols for a data source."""
        defaults = self._get_default_symbols_for_source(source)
        customs = self._custom_symbols.get(user_id, {}).get(source, [])
        return {
            "source": source,
            "default_symbols": defaults,
            "custom_symbols": customs,
        }

    def add_custom_symbols(
        self, source: str, user_id: str, symbols: list[str]
    ) -> list[str]:
        """Add custom symbols for a user+source. Returns updated list."""
        if user_id not in self._custom_symbols:
            self._custom_symbols[user_id] = {}
        if source not in self._custom_symbols[user_id]:
            self._custom_symbols[user_id][source] = []

        existing = set(self._custom_symbols[user_id][source])
        for s in symbols:
            if s not in existing:
                self._custom_symbols[user_id][source].append(s)
                existing.add(s)

        # Subscribe newly added symbols on the gateway
        self._subscribe_symbols_on_gateway(source, symbols)
        _save_custom_symbols(self._custom_symbols)
        return self._custom_symbols[user_id][source]

    def remove_custom_symbols(
        self, source: str, user_id: str, symbols: list[str]
    ) -> list[str]:
        """Remove custom symbols. Returns updated list."""
        if user_id not in self._custom_symbols:
            return []
        if source not in self._custom_symbols[user_id]:
            return []

        remove_set = set(symbols)
        self._custom_symbols[user_id][source] = [
            s for s in self._custom_symbols[user_id][source] if s not in remove_set
        ]
        _save_custom_symbols(self._custom_symbols)
        return self._custom_symbols[user_id][source]

    def search_symbols(self, source: str, keyword: str) -> list[dict[str, str]]:
        """Search symbols within a data source by keyword."""
        keyword_lower = keyword.lower()
        defaults = self._get_default_symbols_for_source(source)
        results = []
        for item in defaults:
            if (
                keyword_lower in item["symbol"].lower()
                or keyword_lower in item.get("name", "").lower()
            ):
                results.append(item)
        return results

    # ------------------------------------------------------------------
    # Quote data
    # ------------------------------------------------------------------

    def get_quotes(
        self, source: str, user_id: str, symbols: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch quote ticks for the given source and symbol list.

        If *symbols* is ``None``, returns quotes for default + custom symbols.
        """
        label = _SOURCE_TO_LABEL.get(source, source)
        manager = self._get_live_trading_manager()

        if symbols is None:
            sym_info = self.get_symbols(source, user_id)
            all_syms = [s["symbol"] for s in sym_info["default_symbols"]]
            all_syms.extend(sym_info["custom_symbols"])
        else:
            all_syms = symbols
        all_syms = list(dict.fromkeys(str(sym).strip() for sym in all_syms if str(sym).strip()))

        self._ensure_receiver(source, manager)
        self._subscribe_symbols_on_gateway(source, all_syms)

        defaults_map: dict[str, dict[str, str]] = {}
        for item in self._get_default_symbols_for_source(source):
            defaults_map[item["symbol"]] = item

        receiver = self._receivers.get(source)
        cached_ticks = self._wait_for_initial_ticks(receiver, all_syms)
        has_receiver = receiver is not None and receiver.is_alive

        now = datetime.now(timezone.utc).isoformat()
        ticks: list[dict[str, Any]] = []

        for sym in all_syms:
            meta = defaults_map.get(sym, {"symbol": sym, "name": "", "exchange": "", "category": ""})
            raw = self._match_cached_tick(cached_ticks, sym)
            tick = self._build_tick(source, label, sym, meta, raw, now)
            ticks.append(tick)

        return {
            "source": source,
            "source_label": label,
            "total": len(ticks),
            "ticks": ticks,
            "update_time": now,
            "refresh_mode": "push" if has_receiver else "polling",
        }

    # ------------------------------------------------------------------
    # Chart data (P1)
    # ------------------------------------------------------------------

    def get_chart_data(
        self,
        source: str,
        symbol: str,
        timeframe: str = "M1",
        count: int = 200,
    ) -> dict[str, Any]:
        """Fetch OHLCV bars from gateway via ZMQ command channel.

        Sends a ``get_bars`` command to the gateway runtime's command socket
        and returns the bar data for chart rendering.
        """
        manager = self._get_live_trading_manager()
        config = self._find_gateway_config(manager, source)
        if config is None:
            return {
                "source": source,
                "symbol": symbol,
                "timeframe": timeframe,
                "bars": [],
                "total": 0,
            }

        command_endpoint = getattr(config, "command_endpoint", None)
        if not command_endpoint:
            return {
                "source": source,
                "symbol": symbol,
                "timeframe": timeframe,
                "bars": [],
                "total": 0,
            }

        bars = self._send_gateway_command(
            command_endpoint,
            "get_bars",
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "count": count,
            },
            send_timeout_ms=5000,
            recv_timeout_ms=10000,
        ) or []

        normalized: list[dict[str, Any]] = []
        for bar in bars:
            normalized.append({
                "date": bar.get("datetime") or bar.get("date") or bar.get("time") or "",
                "open": float(bar.get("open") or 0),
                "high": float(bar.get("high") or 0),
                "low": float(bar.get("low") or 0),
                "close": float(bar.get("close") or 0),
                "volume": float(bar.get("volume") or bar.get("tick_volume") or 0),
            })

        return {
            "source": source,
            "symbol": symbol,
            "timeframe": timeframe,
            "bars": normalized,
            "total": len(normalized),
        }

    # ------------------------------------------------------------------
    # ZMQ receiver management
    # ------------------------------------------------------------------

    def _ensure_receiver(self, source: str, manager: Any) -> None:
        """Start a ZMQ tick receiver for *source* if not already running."""
        existing = self._receivers.get(source)
        if existing is not None and existing.is_alive:
            return

        # Find the gateway config to get market_endpoint
        config = self._find_gateway_config(manager, source)
        if config is None:
            return

        market_endpoint = getattr(config, "market_endpoint", None)
        if not market_endpoint:
            return

        receiver = _ZmqTickReceiver(source, market_endpoint)
        receiver.start()
        self._receivers[source] = receiver
        logger.info("Started ZMQ receiver for %s at %s", source, market_endpoint)

    def _subscribe_symbols_on_gateway(self, source: str, symbols: list[str]) -> None:
        """Send a 'subscribe' command to the gateway for any not-yet-subscribed symbols."""
        if not symbols:
            return

        if source not in self._subscribed_symbols:
            self._subscribed_symbols[source] = set()

        new_syms = [s for s in symbols if s not in self._subscribed_symbols[source]]
        if not new_syms:
            return

        manager = self._get_live_trading_manager()
        config = self._find_gateway_config(manager, source)
        if config is None:
            return

        command_endpoint = getattr(config, "command_endpoint", None)
        if not command_endpoint:
            return

        try:
            import zmq

            ctx = zmq.Context.instance()
            result = self._send_gateway_command(
                command_endpoint,
                "subscribe",
                {
                    "symbols": new_syms,
                    "strategy_id": "quote_page",
                },
                send_timeout_ms=3000,
                recv_timeout_ms=3000,
            )
            if result is not None:
                self._subscribed_symbols[source].update(new_syms)
                logger.info(
                    "Subscribed %d symbols on %s: %s",
                    len(new_syms), source, new_syms[:5],
                )
        except ImportError:
            logger.warning("pyzmq not installed; cannot subscribe symbols on %s", source)
        except Exception:
            logger.exception("Failed to subscribe symbols on %s", source)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_live_trading_manager():
        """Lazily import LiveTradingManager to avoid circular imports."""
        try:
            from app.services.live_trading_manager import get_live_trading_manager
            return get_live_trading_manager()
        except Exception:
            return None

    @staticmethod
    def _get_connected_gateway_exchanges(manager) -> set[str]:
        """Return set of exchange types that have connected gateways."""
        if manager is None:
            return set()
        try:
            gateways = manager.list_connected_gateways()
            return {g.get("exchange_type", "") for g in gateways}
        except Exception:
            return set()

    def _get_default_symbols_for_source(self, source: str) -> list[dict[str, str]]:
        manager = self._get_live_trading_manager()
        state = self._find_gateway_state(manager, source)
        asset_type = self._get_source_asset_type(source, state)
        return list(_DEFAULT_SYMBOLS_BY_ASSET.get((source, asset_type), _DEFAULT_SYMBOLS.get(source, [])))

    @staticmethod
    def _get_source_asset_type(source: str, state: dict[str, Any] | None) -> str:
        if state is None:
            return _DEFAULT_ASSET_TYPES.get(source, "")
        asset_type = str(
            state.get("asset_type")
            or getattr(state.get("config"), "asset_type", "")
            or ""
        ).strip().upper()
        if asset_type:
            return asset_type
        return _DEFAULT_ASSET_TYPES.get(source, "")

    def _is_source_ready(self, manager, source: str) -> bool:
        state = self._find_gateway_state(manager, source)
        if state is None:
            return False
        config = state.get("config")
        command_endpoint = getattr(config, "command_endpoint", None)
        if not command_endpoint:
            return False
        result = self._send_gateway_command(
            command_endpoint,
            "ping",
            {},
            send_timeout_ms=1500,
            recv_timeout_ms=1500,
        )
        if isinstance(result, dict):
            return bool(result.get("ready"))
        return False

    def _find_gateway_config(self, manager, source: str):
        state = self._find_gateway_state(manager, source)
        if state is None:
            return None
        return state.get("config")

    def _find_gateway_state(self, manager, source: str) -> dict[str, Any] | None:
        """Find the most relevant gateway state for the given source.

        Preference order:
        1. Manual gateways for the source
        2. Among them, gateways whose ping says ready=true
        3. Fallback to any gateway of the source
        """
        if manager is None:
            return None
        try:
            candidates: list[dict[str, Any]] = []
            manual_candidates: list[dict[str, Any]] = []
            for _key, state in manager._gateways.items():
                if state.get("exchange_type") != source:
                    continue
                if state.get("config") is None:
                    continue
                candidates.append(state)
                if state.get("manual"):
                    manual_candidates.append(state)
            preferred = manual_candidates or candidates
            for state in preferred:
                config = state.get("config")
                command_endpoint = getattr(config, "command_endpoint", None)
                if not command_endpoint:
                    continue
                result = self._send_gateway_command(
                    command_endpoint,
                    "ping",
                    {},
                    send_timeout_ms=1000,
                    recv_timeout_ms=1000,
                )
                if isinstance(result, dict) and result.get("ready") is True:
                    return state
            if preferred:
                return preferred[0]
        except Exception:
            pass
        return None

    @staticmethod
    def _wait_for_initial_ticks(
        receiver: _ZmqTickReceiver | None,
        symbols: list[str],
        timeout_sec: float = 1.5,
    ) -> dict[str, dict[str, Any]]:
        if receiver is None or not receiver.is_alive:
            return {}
        cached = receiver.get_all_ticks()
        if not symbols or any(sym in cached for sym in symbols):
            return cached
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            time.sleep(0.2)
            cached = receiver.get_all_ticks()
            if any(sym in cached for sym in symbols):
                return cached
        return cached

    @staticmethod
    def _match_cached_tick(
        cached_ticks: dict[str, dict[str, Any]],
        symbol: str,
    ) -> dict[str, Any] | None:
        raw = cached_ticks.get(symbol)
        if raw is not None:
            return raw
        target = symbol.upper()
        for key, payload in cached_ticks.items():
            candidates = [
                str(key or ""),
                str(payload.get("symbol") or ""),
                str(payload.get("instrument_id") or ""),
            ]
            normalized = [candidate.upper() for candidate in candidates if candidate]
            if target in normalized:
                return payload
            if any(value.startswith(target) for value in normalized):
                return payload
        return None

    @staticmethod
    def _send_gateway_command(
        command_endpoint: str,
        command: str,
        payload: dict[str, Any],
        send_timeout_ms: int = 3000,
        recv_timeout_ms: int = 3000,
    ) -> Any | None:
        try:
            import zmq
        except ImportError:
            logger.warning("pyzmq not installed; cannot execute %s on %s", command, command_endpoint)
            return None
        ctx = zmq.Context.instance()
        sock = ctx.socket(zmq.DEALER)
        sock.setsockopt(zmq.IDENTITY, uuid.uuid4().hex.encode("utf-8"))
        sock.setsockopt(zmq.SNDTIMEO, send_timeout_ms)
        sock.setsockopt(zmq.RCVTIMEO, recv_timeout_ms)
        try:
            sock.connect(command_endpoint)
            request = {
                "request_id": uuid.uuid4().hex,
                "command": command,
                "payload": payload,
            }
            sock.send(json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            resp_raw = sock.recv()
            resp = json.loads(resp_raw.decode("utf-8"))
            if isinstance(resp, dict) and resp.get("status") == "ok":
                return resp.get("data")
            if isinstance(resp, dict):
                logger.warning("%s failed for %s: %s", command, command_endpoint, resp.get("error"))
            else:
                logger.warning("%s returned invalid response for %s", command, command_endpoint)
        except zmq.Again:
            logger.warning("%s timed out for %s", command, command_endpoint)
        except Exception:
            logger.exception("Failed to execute %s for %s", command, command_endpoint)
        finally:
            sock.close()
        return None

    @staticmethod
    def _build_tick(
        source: str,
        label: str,
        symbol: str,
        meta: dict[str, str],
        raw: dict[str, Any] | None,
        now: str,
    ) -> dict[str, Any]:
        """Build a QuoteTick dict.

        *raw* is a cached GatewayTick payload (dict) from the ZMQ receiver,
        or None if no data has been received yet.

        GatewayTick fields (from bt_api_py/gateway/models.py):
            timestamp, symbol, exchange, price, volume, bid_price, ask_price,
            bid_volume, ask_volume, openinterest, turnover, update_time, ...
        """
        tick: dict[str, Any] = {
            "source": source,
            "source_label": label,
            "symbol": symbol,
            "name": meta.get("name", ""),
            "exchange": meta.get("exchange", ""),
            "category": meta.get("category", ""),
            "last_price": None,
            "change": None,
            "change_pct": None,
            "bid_price": None,
            "ask_price": None,
            "high_price": None,
            "low_price": None,
            "open_price": None,
            "prev_close": None,
            "volume": None,
            "turnover": None,
            "open_interest": None,
            "update_time": None,
            "status": "normal",
            "error_message": None,
        }

        if raw is None:
            tick["status"] = "missing"
            return tick

        # Map GatewayTick fields → QuoteTick fields
        price = raw.get("price")
        bid_price = _opt_float(raw.get("bid_price"))
        ask_price = _opt_float(raw.get("ask_price"))
        if price is not None and price != 0:
            tick["last_price"] = float(price)
        elif bid_price is not None and ask_price is not None:
            tick["last_price"] = (bid_price + ask_price) / 2.0
        elif bid_price is not None:
            tick["last_price"] = bid_price
        elif ask_price is not None:
            tick["last_price"] = ask_price
        tick["bid_price"] = bid_price
        tick["ask_price"] = ask_price
        tick["volume"] = _opt_float(raw.get("volume"))
        tick["turnover"] = _opt_float(raw.get("turnover"))
        tick["open_interest"] = _opt_float(raw.get("openinterest"))

        # OHLC fields from enriched GatewayTick (24h ticker data)
        tick["high_price"] = _opt_float(raw.get("high_price"))
        tick["low_price"] = _opt_float(raw.get("low_price"))
        tick["open_price"] = _opt_float(raw.get("open_price"))
        tick["prev_close"] = _opt_float(raw.get("prev_close"))

        # Compute change / change_pct from last_price and open_price or prev_close
        last = tick["last_price"]
        if last is not None:
            ref = tick["prev_close"] or tick["open_price"]
            if ref is not None and ref != 0:
                tick["change"] = last - ref
                tick["change_pct"] = (last - ref) / ref * 100.0

        # Exchange from tick overrides metadata if present
        if raw.get("exchange"):
            tick["exchange"] = raw["exchange"]

        # Update time — prefer the tick's own update_time, else use timestamp
        if raw.get("update_time"):
            tick["update_time"] = raw["update_time"]
        elif raw.get("datetime"):
            tick["update_time"] = raw["datetime"]
        elif raw.get("timestamp"):
            try:
                tick["update_time"] = datetime.fromtimestamp(
                    float(raw["timestamp"]), tz=timezone.utc
                ).isoformat()
            except (ValueError, TypeError, OSError):
                tick["update_time"] = now

        return tick

    def shutdown(self) -> None:
        """Stop all ZMQ receivers (called on app shutdown)."""
        for source, receiver in self._receivers.items():
            try:
                receiver.stop()
            except Exception:
                logger.exception("Error stopping receiver for %s", source)
        self._receivers.clear()


def _opt_float(v: Any) -> float | None:
    """Convert a value to float, returning None only for missing values."""
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def get_quote_service() -> QuoteService:
    """Dependency-injection helper."""
    return QuoteService()
