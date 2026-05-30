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

import logging
import threading
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.services.quote.cache import (
    get_cached_tick_metrics,
    load_custom_symbols,
    match_cached_tick,
    save_custom_symbols,
    wait_for_initial_ticks,
)
from app.services.quote.registry import (
    DEFAULT_ASSET_TYPES as _DEFAULT_ASSET_TYPES,
)
from app.services.quote.registry import (
    DEFAULT_SYMBOLS as _DEFAULT_SYMBOLS,
)
from app.services.quote.registry import (
    DEFAULT_SYMBOLS_BY_ASSET as _DEFAULT_SYMBOLS_BY_ASSET,
)
from app.services.quote.registry import (
    SOURCE_REGISTRY as _SOURCE_REGISTRY,
)
from app.services.quote.registry import (
    SOURCE_TO_LABEL as _SOURCE_TO_LABEL,
)
from app.services.quote.registry import (
    resolve_quote_fields as _resolve_quote_fields,
)
from app.services.quote.runtime import (
    send_gateway_command as _send_gateway_command_impl,
)
from app.services.quote.snapshots import (
    fetch_gateway_snapshot_tick as _fetch_gateway_snapshot_tick,
)
from app.services.quote.snapshots import (
    fetch_ib_web_snapshot_tick as _fetch_ib_web_snapshot_tick,
)
from app.services.quote.snapshots import (
    fetch_standard_snapshot_tick as _fetch_standard_snapshot_tick,
)
from app.services.quote.tick import (
    build_tick as _build_tick,
)
from app.services.quote.zmq_receiver import ZmqTickReceiver

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistent storage for custom symbols
# ---------------------------------------------------------------------------


# ===================================================================
# ZMQ tick receiver — one per gateway
# ===================================================================


# ZMQ tick receiver moved to quote.zmq_receiver in iteration 174 C4.
# Keep the legacy private name as an alias for backward compatibility.
_ZmqTickReceiver = ZmqTickReceiver


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
        self._custom_symbols: dict[str, dict[str, list[str]]] = load_custom_symbols()
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
        return get_cached_tick_metrics(self._receivers, source)

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

            results.append(
                {
                    "source": source,
                    "source_label": label,
                    "status": status,
                    "status_message": msg,
                    "capabilities": caps,
                }
            )
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

    def add_custom_symbols(self, source: str, user_id: str, symbols: list[str]) -> list[str]:
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
        save_custom_symbols(self._custom_symbols)
        return self._custom_symbols[user_id][source]

    def remove_custom_symbols(self, source: str, user_id: str, symbols: list[str]) -> list[str]:
        """Remove custom symbols. Returns updated list."""
        if user_id not in self._custom_symbols:
            return []
        if source not in self._custom_symbols[user_id]:
            return []

        remove_set = set(symbols)
        self._custom_symbols[user_id][source] = [
            s for s in self._custom_symbols[user_id][source] if s not in remove_set
        ]
        save_custom_symbols(self._custom_symbols)
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
        self,
        source: str,
        user_id: str,
        symbols: list[str] | None = None,
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
        cached_ticks = wait_for_initial_ticks(receiver, all_syms)
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
            meta = defaults_map.get(
                sym, {"symbol": sym, "name": "", "exchange": "", "category": ""}
            )
            raw = match_cached_tick(cached_ticks, sym)
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

        bars = (
            self._send_gateway_command(
                command_endpoint,
                "get_bars",
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "count": count,
                },
                send_timeout_ms=5000,
                recv_timeout_ms=10000,
            )
            or []
        )

        normalized: list[dict[str, Any]] = []
        for bar in bars:
            normalized.append(
                {
                    "date": bar.get("datetime") or bar.get("date") or bar.get("time") or "",
                    "open": float(bar.get("open") or 0),
                    "high": float(bar.get("high") or 0),
                    "low": float(bar.get("low") or 0),
                    "close": float(bar.get("close") or 0),
                    "volume": float(bar.get("volume") or bar.get("tick_volume") or 0),
                }
            )

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
                        result.get("accepted") or result.get("symbols") or result.get("subscribed")
                    )
                    if isinstance(accepted_candidate, list):
                        accepted_symbols = [
                            str(symbol) for symbol in accepted_candidate if str(symbol)
                        ]
                    skipped_candidate = result.get("skipped") or result.get("skipped_symbols")
                    if isinstance(skipped_candidate, list):
                        skipped_symbols = [
                            str(symbol) for symbol in skipped_candidate if str(symbol)
                        ]
                if accepted_symbols:
                    self._subscribed_symbols[source].update(accepted_symbols)
                    logger.info(
                        "Subscribed %d symbols on %s: %s",
                        len(accepted_symbols),
                        source,
                        accepted_symbols[:5],
                    )
                if skipped_symbols:
                    logger.warning(
                        "Skipped %d symbols on %s due to gateway rejection: %s",
                        len(skipped_symbols),
                        source,
                        skipped_symbols[:5],
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
        return list(
            _DEFAULT_SYMBOLS_BY_ASSET.get((source, asset_type), _DEFAULT_SYMBOLS.get(source, []))
        )

    @staticmethod
    def _get_source_asset_type(source: str, state: dict[str, Any] | None) -> str:
        if state is None:
            return _DEFAULT_ASSET_TYPES.get(source, "")
        asset_type = (
            str(state.get("asset_type") or getattr(state.get("config"), "asset_type", "") or "")
            .strip()
            .upper()
        )
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
            if match_cached_tick(hydrated, symbol) is not None:
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
        return _fetch_gateway_snapshot_tick(source, feed, symbol)

    def _get_gateway_runtime(self, manager: Any, source: str) -> Any | None:
        state = self._find_gateway_state(manager, source)
        if state is None:
            return None
        return state.get("runtime")

    @staticmethod
    def _fetch_ib_web_snapshot_tick(feed: Any, symbol: str) -> dict[str, Any] | None:
        return _fetch_ib_web_snapshot_tick(feed, symbol)

    @staticmethod
    def _fetch_standard_snapshot_tick(source: str, feed: Any, symbol: str) -> dict[str, Any] | None:
        return _fetch_standard_snapshot_tick(source, feed, symbol)

    @staticmethod
    def _send_gateway_command(
        command_endpoint: str,
        command: str,
        payload: dict[str, Any],
        send_timeout_ms: int = 3000,
        recv_timeout_ms: int = 3000,
    ) -> Any | None:
        return _send_gateway_command_impl(
            command_endpoint,
            command,
            payload,
            send_timeout_ms=send_timeout_ms,
            recv_timeout_ms=recv_timeout_ms,
        )

    @staticmethod
    def _build_tick(
        source: str,
        label: str,
        symbol: str,
        meta: dict[str, str],
        raw: dict[str, Any] | None,
        now: str,
    ) -> dict[str, Any]:
        """Build a QuoteTick dict from a raw GatewayTick payload."""
        return _build_tick(source, label, symbol, meta, raw, now)

    def shutdown(self) -> None:
        """Stop all ZMQ receivers (called on app shutdown)."""
        for source, receiver in self._receivers.items():
            try:
                receiver.stop()
            except Exception:
                logger.exception("Error stopping receiver for %s", source)
        self._receivers.clear()


def get_quote_service() -> QuoteService:
    """Dependency-injection helper."""
    return QuoteService()
