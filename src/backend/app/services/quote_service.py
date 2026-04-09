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
import math
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings

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
# Default symbols per data source — loaded from config/default_symbols.yaml
# ---------------------------------------------------------------------------

_SYMBOLS_CONFIG_FILE = Path(__file__).resolve().parents[2] / "config" / "default_symbols.yaml"


def _load_symbols_config() -> dict[str, Any]:
    """Load default symbols config from YAML file. Returns empty dict on error."""
    if not _SYMBOLS_CONFIG_FILE.is_file():
        logger.warning("Default symbols config not found: %s", _SYMBOLS_CONFIG_FILE)
        return {}
    try:
        import yaml

        with _SYMBOLS_CONFIG_FILE.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Failed to load %s: %s", _SYMBOLS_CONFIG_FILE, exc)
        return {}


def _build_symbols_from_config() -> (
    tuple[
        dict[str, list[dict[str, str]]],
        dict[str, str],
        dict[tuple[str, str], list[dict[str, str]]],
    ]
):
    cfg = _load_symbols_config()
    symbols: dict[str, list[dict[str, str]]] = cfg.get("symbols", {})
    asset_types: dict[str, str] = cfg.get("default_asset_types", {})
    symbols_by_asset: dict[tuple[str, str], list[dict[str, str]]] = {}

    # Build symbols_by_asset from the nested structure in YAML
    for source, asset_map in cfg.get("symbols_by_asset", {}).items():
        if isinstance(asset_map, dict):
            for asset_type, sym_list in asset_map.items():
                if isinstance(sym_list, list):
                    symbols_by_asset[(source, asset_type)] = sym_list

    # Auto-populate symbols_by_asset with default asset type mappings
    for source, default_at in asset_types.items():
        key = (source, default_at)
        if key not in symbols_by_asset and source in symbols:
            symbols_by_asset[key] = symbols[source]

    # Also map BINANCE SPOT → BINANCE symbols, OKX SPOT → OKX symbols (if not overridden)
    for source in symbols:
        if (source, "SPOT") not in symbols_by_asset:
            symbols_by_asset[(source, "SPOT")] = symbols[source]

    return symbols, asset_types, symbols_by_asset


_DEFAULT_SYMBOLS, _DEFAULT_ASSET_TYPES, _DEFAULT_SYMBOLS_BY_ASSET = (
    _build_symbols_from_config()
)

_QUOTE_FIELDS_CONFIG_FILE = Path(__file__).resolve().parents[2] / "config" / "quote_fields.yaml"

_GENERIC_QUOTE_FIELDS: list[dict[str, Any]] = [
    {"prop": "symbol", "label": "代码", "visible": True, "always_show": True},
    {"prop": "name", "label": "名称", "visible": True, "always_show": False},
    {"prop": "category", "label": "分类", "visible": True, "always_show": False},
    {"prop": "last_price", "label": "最新价", "visible": True, "always_show": False},
    {"prop": "change", "label": "涨跌", "visible": True, "always_show": False},
    {"prop": "change_pct", "label": "涨跌幅", "visible": True, "always_show": False},
    {"prop": "bid_price", "label": "买价", "visible": True, "always_show": False},
    {"prop": "ask_price", "label": "卖价", "visible": True, "always_show": False},
    {"prop": "high_price", "label": "最高", "visible": True, "always_show": False},
    {"prop": "low_price", "label": "最低", "visible": True, "always_show": False},
    {"prop": "open_price", "label": "开盘", "visible": True, "always_show": False},
    {"prop": "prev_close", "label": "昨收", "visible": True, "always_show": False},
    {"prop": "volume", "label": "成交量", "visible": True, "always_show": False},
    {"prop": "turnover", "label": "成交额", "visible": True, "always_show": False},
    {"prop": "open_interest", "label": "持仓量", "visible": True, "always_show": False},
    {"prop": "update_time", "label": "更新时间", "visible": True, "always_show": False},
]


def _normalize_quote_fields_config(fields: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    if not isinstance(fields, list):
        return normalized
    for item in fields:
        if not isinstance(item, dict):
            continue
        prop = str(item.get("prop") or "").strip()
        if not prop:
            continue
        normalized.append(
            {
                "prop": prop,
                "label": str(item.get("label") or prop),
                "visible": bool(item.get("visible", True)),
                "always_show": bool(item.get("always_show", False)),
            }
        )
    return normalized


def _load_quote_fields_by_source() -> dict[str, list[dict[str, Any]]]:
    if not _QUOTE_FIELDS_CONFIG_FILE.is_file():
        logger.warning("Quote fields config not found: %s", _QUOTE_FIELDS_CONFIG_FILE)
        return {}
    try:
        import yaml

        with _QUOTE_FIELDS_CONFIG_FILE.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception as exc:
        logger.warning("Failed to load %s: %s", _QUOTE_FIELDS_CONFIG_FILE, exc)
        return {}
    if not isinstance(data, dict):
        return {}
    raw_sources = data.get("sources", {})
    if not isinstance(raw_sources, dict):
        return {}
    normalized_sources: dict[str, list[dict[str, Any]]] = {}
    for source, fields in raw_sources.items():
        normalized_fields = _normalize_quote_fields_config(fields)
        if normalized_fields:
            normalized_sources[str(source).strip().upper()] = normalized_fields
    return normalized_sources


def _has_quote_field_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    return True


def _first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def _resolve_quote_fields(source: str, ticks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    configured_fields = _QUOTE_FIELDS_BY_SOURCE.get(source, _GENERIC_QUOTE_FIELDS)
    resolved: list[dict[str, Any]] = []
    for field in configured_fields:
        prop = str(field.get("prop") or "").strip()
        if not prop:
            continue
        if field.get("always_show") or any(_has_quote_field_value(tick.get(prop)) for tick in ticks):
            resolved.append(dict(field))
    return resolved


_QUOTE_FIELDS_BY_SOURCE = _load_quote_fields_by_source()


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

    def seed_tick(self, symbol: str, payload: dict[str, Any]) -> None:
        normalized = dict(payload)
        if symbol:
            normalized["symbol"] = normalized.get("symbol") or symbol
        key = str(normalized.get("symbol") or symbol or "").strip()
        if not key:
            return
        with self._lock:
            self._tick_cache[key] = normalized
            instrument_id = str(normalized.get("instrument_id") or "").strip()
            if instrument_id and instrument_id != key:
                self._tick_cache[instrument_id] = normalized

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
        # Sources explicitly disconnected by the user; auto-connect should stay paused
        self._auto_connect_suppressed_sources: set[str] = set()

    def suppress_auto_connect(self, source: str) -> None:
        normalized = str(source or "").strip().upper()
        if not normalized:
            return
        self._auto_connect_suppressed_sources.add(normalized)

    def resume_auto_connect(self, source: str) -> None:
        normalized = str(source or "").strip().upper()
        if not normalized:
            return
        self._auto_connect_suppressed_sources.discard(normalized)

    def get_cached_tick_metrics(self, source: str) -> dict[str, Any]:
        normalized = str(source or "").strip().upper()
        if not normalized:
            return {"tick_count": 0, "last_tick_time": None}
        receiver = self._receivers.get(normalized)
        if receiver is None:
            return {"tick_count": 0, "last_tick_time": None}
        cached_ticks = receiver.get_all_ticks()
        last_tick_time: int | None = None
        for payload in cached_ticks.values():
            if not isinstance(payload, dict):
                continue
            raw_timestamp = payload.get("timestamp")
            if raw_timestamp in (None, ""):
                continue
            try:
                timestamp = float(raw_timestamp)
            except (TypeError, ValueError, OverflowError):
                continue
            if math.isnan(timestamp) or math.isinf(timestamp):
                continue
            normalized_timestamp = int(timestamp / 1000.0) if timestamp > 1e12 else int(timestamp)
            if last_tick_time is None or normalized_timestamp > last_tick_time:
                last_tick_time = normalized_timestamp
        return {
            "tick_count": len(cached_ticks),
            "last_tick_time": last_tick_time,
        }

    # ------------------------------------------------------------------
    # Data-source status
    # ------------------------------------------------------------------

    def get_data_sources(self) -> list[dict[str, Any]]:
        """Return all data sources with their current status."""
        manager = self._get_live_trading_manager()
        self._ensure_mt5_gateway_connected(manager)
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
        if source == "MT5":
            self._ensure_mt5_gateway_connected(manager)

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
        if source in {"IB_WEB", "BINANCE", "OKX"}:
            cached_ticks = self._hydrate_snapshot_ticks(
                manager,
                source,
                receiver,
                all_syms,
                cached_ticks,
            )
        has_receiver = receiver is not None and receiver.is_alive

        now = datetime.now(timezone.utc).isoformat()
        ticks: list[dict[str, Any]] = []

        for sym in all_syms:
            meta = defaults_map.get(sym, {"symbol": sym, "name": "", "exchange": "", "category": ""})
            raw = self._match_cached_tick(cached_ticks, sym)
            tick = self._build_tick(source, label, sym, meta, raw, now)
            ticks.append(tick)
        fields = _resolve_quote_fields(source, ticks)

        return {
            "source": source,
            "source_label": label,
            "total": len(ticks),
            "ticks": ticks,
            "fields": fields,
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
            recv_timeout_ms = 12000 if source == "IB_WEB" else 3000
            result = self._send_gateway_command(
                command_endpoint,
                "subscribe",
                {
                    "symbols": new_syms,
                    "strategy_id": "quote_page",
                },
                send_timeout_ms=3000,
                recv_timeout_ms=recv_timeout_ms,
            )
            if result is not None:
                accepted_symbols = list(new_syms)
                skipped_symbols: list[str] = []
                if isinstance(result, dict):
                    accepted_candidate = (
                        result.get("accepted")
                        or result.get("symbols")
                        or result.get("subscribed")
                    )
                    if isinstance(accepted_candidate, list):
                        accepted_symbols = [str(symbol) for symbol in accepted_candidate if str(symbol)]
                    skipped_candidate = result.get("skipped") or result.get("skipped_symbols")
                    if isinstance(skipped_candidate, list):
                        skipped_symbols = [str(symbol) for symbol in skipped_candidate if str(symbol)]
                if accepted_symbols:
                    self._subscribed_symbols[source].update(accepted_symbols)
                    logger.info(
                        "Subscribed %d symbols on %s: %s",
                        len(accepted_symbols), source, accepted_symbols[:5],
                    )
                if skipped_symbols:
                    logger.warning(
                        "Skipped %d symbols on %s due to gateway rejection: %s",
                        len(skipped_symbols), source, skipped_symbols[:5],
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

    def _ensure_mt5_gateway_connected(self, manager: Any) -> None:
        if manager is None:
            return
        if "MT5" in self._auto_connect_suppressed_sources:
            return
        if self._find_gateway_state(manager, "MT5") is not None:
            return
        settings = get_settings()
        login = str(settings.MT5_LOGIN or "").strip()
        password = str(settings.MT5_PASSWORD or "").strip()
        if not login or not password:
            return
        credentials = {
            "login": login,
            "password": password,
            "ws_uri": str(settings.MT5_WS_URI or "").strip(),
            "symbol_suffix": str(settings.MT5_SYMBOL_SUFFIX or "").strip(),
        }
        try:
            result = manager.connect_gateway("MT5", credentials)
        except Exception as exc:
            logger.warning(
                "Auto-connect MT5 gateway failed: %s: %s",
                type(exc).__name__,
                exc,
            )
            return
        if result.get("status") == "error":
            logger.warning(
                "Auto-connect MT5 gateway failed: %s",
                result.get("message", "unknown error"),
            )
            return
        logger.info("Auto-connected MT5 gateway for quote service")

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

    def _hydrate_snapshot_ticks(
        self,
        manager: Any,
        source: str,
        receiver: _ZmqTickReceiver | None,
        symbols: list[str],
        cached_ticks: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        if not symbols:
            return cached_ticks
        runtime = self._get_gateway_runtime(manager, "IB_WEB")
        if source != "IB_WEB":
            runtime = self._get_gateway_runtime(manager, source)
        adapter = getattr(runtime, "adapter", None)
        feed = getattr(adapter, "feed", None)
        if feed is None or not hasattr(feed, "get_tick"):
            return cached_ticks
        hydrated = dict(cached_ticks)
        for symbol in symbols:
            if self._match_cached_tick(hydrated, symbol) is not None:
                continue
            raw = self._fetch_gateway_snapshot_tick(source, feed, symbol)
            if raw is None:
                continue
            hydrated[symbol] = raw
            if receiver is not None:
                receiver.seed_tick(symbol, raw)
        return hydrated

    @staticmethod
    def _fetch_gateway_snapshot_tick(source: str, feed: Any, symbol: str) -> dict[str, Any] | None:
        if source == "IB_WEB":
            return QuoteService._fetch_ib_web_snapshot_tick(feed, symbol)
        return QuoteService._fetch_standard_snapshot_tick(source, feed, symbol)

    def _get_gateway_runtime(self, manager: Any, source: str) -> Any | None:
        state = self._find_gateway_state(manager, source)
        if state is None:
            return None
        return state.get("runtime")

    @staticmethod
    def _fetch_ib_web_snapshot_tick(feed: Any, symbol: str) -> dict[str, Any] | None:
        try:
            snapshot = feed.get_tick(symbol)
        except Exception as exc:
            logger.warning(
                "Failed to fetch IB_WEB snapshot for %s: %s: %s",
                symbol,
                type(exc).__name__,
                exc,
            )
            return None
        if not isinstance(snapshot, dict) or not snapshot:
            return None

        price = _opt_float(snapshot.get("31") or snapshot.get("last") or snapshot.get("lastPrice"))
        bid_price = _opt_float(snapshot.get("84") or snapshot.get("bid") or snapshot.get("bidPrice"))
        ask_price = _opt_float(snapshot.get("86") or snapshot.get("ask") or snapshot.get("askPrice"))
        volume = _opt_float(snapshot.get("87") or snapshot.get("volume") or snapshot.get("lastSize"))
        if price is None and bid_price is None and ask_price is None and volume is None:
            return None

        raw: dict[str, Any] = {
            "timestamp": time.time(),
            "symbol": symbol,
            "exchange": "IB_WEB",
            "instrument_id": str(snapshot.get("conid") or snapshot.get("conidEx") or ""),
            "exchange_id": str(snapshot.get("listingExchange") or snapshot.get("exchange") or ""),
        }
        if price is not None:
            raw["price"] = price
        if bid_price is not None:
            raw["bid_price"] = bid_price
        if ask_price is not None:
            raw["ask_price"] = ask_price
        if volume is not None:
            raw["volume"] = volume
        return raw

    @staticmethod
    def _fetch_standard_snapshot_tick(source: str, feed: Any, symbol: str) -> dict[str, Any] | None:
        try:
            snapshot = feed.get_tick(symbol)
        except Exception as exc:
            logger.warning(
                "Failed to fetch %s snapshot for %s: %s: %s",
                source,
                symbol,
                type(exc).__name__,
                exc,
            )
            return None

        data = snapshot.get_data() if hasattr(snapshot, "get_data") else snapshot
        if isinstance(data, list):
            item = data[0] if data else None
        elif isinstance(data, dict):
            item = data
        else:
            item = None
        if item is None:
            return None

        payload = item.get_all_data() if hasattr(item, "get_all_data") else item
        if not isinstance(payload, dict) or not payload:
            return None

        bid_price = _opt_float(_first_present(payload, "bid_price"))
        ask_price = _opt_float(_first_present(payload, "ask_price"))
        price = _opt_float(_first_present(payload, "last_price", "price"))
        if price is None and bid_price is not None and ask_price is not None:
            price = (bid_price + ask_price) / 2.0
        volume = _opt_float(_first_present(payload, "volume_24h", "vol_24h", "volume"))
        turnover = _opt_float(_first_present(payload, "turnover_24h", "vol_ccy_24h", "turnover"))
        high_price = _opt_float(_first_present(payload, "high_price", "high_24h"))
        low_price = _opt_float(_first_present(payload, "low_price", "low_24h"))
        open_price = _opt_float(_first_present(payload, "open_price", "open_24h"))
        prev_close = _opt_float(_first_present(payload, "prev_close"))
        bid_volume = _opt_float(_first_present(payload, "bid_volume"))
        ask_volume = _opt_float(_first_present(payload, "ask_volume"))
        if all(
            value is None
            for value in (
                price,
                bid_price,
                ask_price,
                volume,
                turnover,
                high_price,
                low_price,
                open_price,
                prev_close,
            )
        ):
            return None

        server_time = _opt_float(_first_present(payload, "server_time"))
        if server_time is None:
            timestamp = time.time()
        else:
            timestamp = server_time / 1000.0 if server_time > 1e12 else server_time

        raw: dict[str, Any] = {
            "timestamp": timestamp,
            "symbol": str(_first_present(payload, "ticker_symbol_name", "symbol_name") or symbol),
            "exchange": source,
        }
        if price is not None:
            raw["price"] = price
        if bid_price is not None:
            raw["bid_price"] = bid_price
        if ask_price is not None:
            raw["ask_price"] = ask_price
        if bid_volume is not None:
            raw["bid_volume"] = bid_volume
        if ask_volume is not None:
            raw["ask_volume"] = ask_volume
        if volume is not None:
            raw["volume"] = volume
        if turnover is not None:
            raw["turnover"] = turnover
        if high_price is not None:
            raw["high_price"] = high_price
        if low_price is not None:
            raw["low_price"] = low_price
        if open_price is not None:
            raw["open_price"] = open_price
        if prev_close is not None:
            raw["prev_close"] = prev_close
        return raw

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

        if raw.get("update_time"):
            tick["update_time"] = _normalize_tick_update_time(raw.get("update_time"), raw, now)
        elif raw.get("datetime"):
            tick["update_time"] = _normalize_tick_update_time(raw.get("datetime"), raw, now)
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


def _normalize_tick_date_part(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return text
    return None


def _normalize_tick_update_time(value: Any, raw: dict[str, Any], now: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.isoformat()
    except ValueError:
        pass

    time_part = text
    if text.count(":") >= 2:
        date_part = (
            _normalize_tick_date_part(raw.get("trading_day"))
            or _normalize_tick_date_part(raw.get("action_day"))
            or _normalize_tick_date_part(raw.get("date"))
            or now.split("T", 1)[0]
        )
        return f"{date_part}T{time_part}"

    return text


def _opt_float(v: Any) -> float | None:
    """Convert a value to float, returning None only for missing values."""
    if v is None:
        return None
    try:
        number = float(v)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(number) or abs(number) >= 1e308:
        return None
    return number


def get_quote_service() -> QuoteService:
    """Dependency-injection helper."""
    return QuoteService()
