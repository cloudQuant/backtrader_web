"""
Quote service for the unified quote display page.

Architecture
~~~~~~~~~~~~
bt_api_py  GatewayRuntime  (per exchange)
   ├─ market_socket  (ZMQ PUB) → publishes GatewayTick as JSON
   ├─ event_socket   (ZMQ PUB)
   └─ command_socket (ZMQ ROUTER) → accepts subscribe / health / …

AI for Investor QuoteService
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
    load_hidden_subscriptions,
    match_cached_tick,
    save_custom_symbols,
    save_hidden_subscriptions,
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

_MAX_SNAPSHOT_HYDRATION_PER_GATEWAY = 10

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
        # Persistently hidden regular subscriptions. Running-workspace rows
        # never enter this collection because their dismissal is UI-local.
        self._hidden_subscriptions: dict[str, dict[str, list[str]]] = (
            load_hidden_subscriptions()
        )
        # ZMQ receivers: {gateway_key: _ZmqTickReceiver}.  A source may have
        # several running gateways (for example, two IB workspaces), so the
        # gateway key is the only safe cache boundary.
        self._receivers: dict[str, _ZmqTickReceiver] = {}
        # Symbols we have already asked each gateway to subscribe.  This is
        # deliberately keyed by gateway rather than exchange: two workspaces
        # on the same exchange may use independent sessions, while a shared
        # gateway must never receive the same subscription twice.
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

    def get_data_sources(
        self,
        user_id: str = "",
        workspace_names: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return all data sources with their current status."""
        manager = self._get_live_trading_manager()
        self._ensure_mt5_gateway_connected(manager)
        workspace_context = self._get_running_workspace_context(
            manager,
            user_id,
            workspace_names,
        )

        results = []
        for reg in _SOURCE_REGISTRY:
            source = reg["source"]
            label = reg["source_label"]
            caps = reg["capabilities"]
            source_context = workspace_context.get(source, {})
            gateway_states = self._get_source_gateway_states(
                manager,
                source,
                source_context,
            )
            ready_gateways = [
                (gateway_key, state)
                for gateway_key, state in gateway_states.items()
                if self._is_gateway_state_ready(state)
            ]
            for gateway_key, state in ready_gateways:
                self._ensure_receiver_for_gateway(source, gateway_key, state)
                workspace_gateway = source_context.get(gateway_key, {})
                workspace_symbols = [
                    metadata["symbol"]
                    for metadata in workspace_gateway.get("symbols", {}).values()
                ]
                self._subscribe_symbols_on_gateway_state(
                    source,
                    gateway_key,
                    state,
                    workspace_symbols,
                )
            workspace_runs = self._build_workspace_runs(source_context)
            running_symbol_count = len(
                {
                    symbol_key
                    for gateway in source_context.values()
                    for symbol_key in gateway["symbols"]
                }
            )

            if not caps:
                status = "unavailable"
                msg = "接入中，暂不可用"
            elif ready_gateways:
                status = "available"
                msg = None
            elif gateway_states:
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
                    "gateway_count": len(gateway_states),
                    "workspace_count": len(workspace_runs),
                    "running_symbol_count": running_symbol_count,
                    "workspaces": workspace_runs,
                }
            )
        return results

    # ------------------------------------------------------------------
    # Symbols
    # ------------------------------------------------------------------

    def get_symbols(self, source: str, user_id: str) -> dict[str, Any]:
        """Return symbols plus the complete configured category catalog for a source."""
        source = str(source or "").strip().upper()
        hidden = self._hidden_symbol_set(source, user_id)
        defaults = [
            item for item in self._get_default_symbols_for_source(source) if item["symbol"] not in hidden
        ]
        customs = self._custom_symbols.get(user_id, {}).get(source, [])
        context = self._get_running_workspace_context(
            self._get_live_trading_manager(),
            user_id,
        ).get(source, {})
        default_map = {item["symbol"]: item for item in defaults}
        running_symbols: list[dict[str, str]] = []
        seen: set[str] = set()
        for gateway in context.values():
            for symbol_key, metadata in gateway["symbols"].items():
                if symbol_key in seen:
                    continue
                seen.add(symbol_key)
                symbol = metadata["symbol"]
                running_symbols.append(
                    dict(
                        default_map.get(
                            symbol,
                            {
                                "symbol": symbol,
                                "name": "",
                                "exchange": "",
                                "category": "",
                            },
                        )
                    )
                )
        return {
            "source": source,
            "default_symbols": defaults,
            "custom_symbols": customs,
            "running_symbols": running_symbols,
            "categories": self.get_source_categories(source),
        }

    @staticmethod
    def get_source_categories(source: str) -> list[str]:
        """Return every configured category for a data source.

        Quote snapshots may contain only the instruments currently subscribed
        by a gateway.  Deriving the filter menu from those rows hides valid
        categories whenever a market is inactive or a workspace uses a small
        symbol subset, so build the catalog from both base and asset-specific
        symbol configuration instead.
        """
        normalized_source = str(source or "").strip().upper()
        configured_symbols = list(_DEFAULT_SYMBOLS.get(normalized_source, []))
        for (configured_source, _asset_type), symbols in _DEFAULT_SYMBOLS_BY_ASSET.items():
            if str(configured_source).strip().upper() == normalized_source:
                configured_symbols.extend(symbols)

        categories = {
            str(item.get("category") or "").strip()
            for item in configured_symbols
            if isinstance(item, dict) and str(item.get("category") or "").strip()
        }
        return sorted(categories)

    def _hidden_symbol_set(self, source: str, user_id: str) -> set[str]:
        normalized_source = str(source or "").strip().upper()
        return {
            str(symbol).strip()
            for symbol in self._hidden_subscriptions.get(user_id, {}).get(normalized_source, [])
            if str(symbol).strip()
        }

    def _unhide_subscription_symbols(self, source: str, user_id: str, symbols: list[str]) -> None:
        normalized_source = str(source or "").strip().upper()
        restore_set = {str(symbol).strip() for symbol in symbols if str(symbol).strip()}
        if not restore_set:
            return
        by_source = self._hidden_subscriptions.get(user_id)
        if not by_source or normalized_source not in by_source:
            return
        by_source[normalized_source] = [
            symbol for symbol in by_source[normalized_source] if symbol not in restore_set
        ]
        if not by_source[normalized_source]:
            by_source.pop(normalized_source, None)
        if not by_source:
            self._hidden_subscriptions.pop(user_id, None)
        save_hidden_subscriptions(self._hidden_subscriptions)

    def add_custom_symbols(self, source: str, user_id: str, symbols: list[str]) -> list[str]:
        """Add custom symbols for a user+source. Returns updated list."""
        source = str(source or "").strip().upper()
        if user_id not in self._custom_symbols:
            self._custom_symbols[user_id] = {}
        if source not in self._custom_symbols[user_id]:
            self._custom_symbols[user_id][source] = []

        existing = set(self._custom_symbols[user_id][source])
        for s in symbols:
            if s not in existing:
                self._custom_symbols[user_id][source].append(s)
                existing.add(s)

        self._unhide_subscription_symbols(source, user_id, symbols)

        # Subscribe newly added symbols on the gateway
        self._subscribe_symbols_on_gateway(source, symbols)
        save_custom_symbols(self._custom_symbols)
        return self._custom_symbols[user_id][source]

    def remove_custom_symbols(self, source: str, user_id: str, symbols: list[str]) -> list[str]:
        """Remove custom symbols. Returns updated list."""
        source = str(source or "").strip().upper()
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

    def remove_subscriptions(self, source: str, user_id: str, symbols: list[str]) -> list[str]:
        """Permanently remove saved/default subscriptions for a user.

        This intentionally excludes workspace-driven rows: the frontend hides
        those only for its current session so a refresh or service restart
        restores the strategy's live instrument monitoring.
        """
        source = str(source or "").strip().upper()
        remove_set = {str(symbol).strip() for symbol in symbols if str(symbol).strip()}
        if not source or not remove_set:
            return self._custom_symbols.get(user_id, {}).get(source, [])

        user_custom = self._custom_symbols.setdefault(user_id, {})
        if source in user_custom:
            user_custom[source] = [
                symbol for symbol in user_custom[source] if symbol not in remove_set
            ]
        hidden_by_source = self._hidden_subscriptions.setdefault(user_id, {})
        current_hidden = set(hidden_by_source.get(source, []))
        current_hidden.update(remove_set)
        hidden_by_source[source] = sorted(current_hidden)
        save_custom_symbols(self._custom_symbols)
        save_hidden_subscriptions(self._hidden_subscriptions)
        return user_custom.get(source, [])

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
        workspace_names: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Fetch quote ticks for the given source and symbol list.

        If *symbols* is ``None``, returns quotes for default + custom symbols.
        """
        source = str(source or "").strip().upper()
        label = _SOURCE_TO_LABEL.get(source, source)
        manager = self._get_live_trading_manager()
        if source == "MT5":
            self._ensure_mt5_gateway_connected(manager)

        if symbols is None:
            hidden = self._hidden_symbol_set(source, user_id)
            subscription_symbols = [
                item["symbol"]
                for item in self._get_default_symbols_for_source(source)
                if item["symbol"] not in hidden
            ]
            subscription_symbols.extend(self._custom_symbols.get(user_id, {}).get(source, []))
        else:
            subscription_symbols = symbols
        subscription_symbols = list(
            dict.fromkeys(str(sym).strip() for sym in subscription_symbols if str(sym).strip())
        )

        workspace_context = self._get_running_workspace_context(
            manager,
            user_id,
            workspace_names,
        ).get(source, {})

        # Keep the original source-level calls for a manual subscription.  In
        # normal operation these resolve to the selected gateway key; retaining
        # this path also lets a source with no active workspace show its saved
        # subscriptions as missing rather than silently disappearing.
        self._ensure_receiver(source, manager)
        self._subscribe_symbols_on_gateway(source, subscription_symbols)

        defaults_map: dict[str, dict[str, str]] = {}
        for item in self._get_default_symbols_for_source(source):
            defaults_map[item["symbol"]] = item

        now = datetime.now(timezone.utc).isoformat()
        ticks: list[dict[str, Any]] = []
        has_receiver = False

        plans = self._build_quote_plans(
            manager,
            source,
            subscription_symbols,
            workspace_context,
        )
        for gateway_key, plan in plans.items():
            state = plan.get("state")
            plan_symbols = list(plan["symbols"].values())
            symbols_for_gateway = [item["symbol"] for item in plan_symbols]

            receiver = self._get_receiver_for_plan(source, gateway_key, state)
            if state is not None and gateway_key != source:
                self._ensure_receiver_for_gateway(source, gateway_key, state)
                receiver = self._receivers.get(gateway_key)
                self._subscribe_symbols_on_gateway_state(
                    source,
                    gateway_key,
                    state,
                    symbols_for_gateway,
                )

            cached_ticks = wait_for_initial_ticks(receiver, symbols_for_gateway)
            if source in {"IB_WEB", "MT5", "BINANCE", "OKX"}:
                cached_ticks = self._hydrate_snapshot_ticks(
                    manager,
                    source,
                    receiver,
                    symbols_for_gateway,
                    cached_ticks,
                    state=state,
                    max_snapshots=_MAX_SNAPSHOT_HYDRATION_PER_GATEWAY,
                )
            has_receiver = has_receiver or bool(receiver is not None and receiver.is_alive)

            for item in plan_symbols:
                sym = item["symbol"]
                meta = defaults_map.get(
                    sym,
                    {"symbol": sym, "name": "", "exchange": "", "category": ""},
                )
                raw = match_cached_tick(cached_ticks, sym)
                tick = self._build_tick(source, label, sym, meta, raw, now)
                tick["quote_key"] = f"{gateway_key}:{sym}"
                tick["gateway_key"] = "" if gateway_key == source else gateway_key
                tick["origins"] = sorted(item["origins"])
                tick["workspace_ids"] = sorted(item["workspace_ids"])
                tick["workspace_names"] = sorted(item["workspace_names"])
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
        """Start a receiver for the preferred concrete gateway of *source*."""
        gateway_key, state = self._find_gateway_state_with_key(manager, source)
        if state is None:
            return
        self._ensure_receiver_for_gateway(source, gateway_key or source, state)

    def _ensure_receiver_for_gateway(
        self,
        source: str,
        gateway_key: str,
        state: dict[str, Any],
    ) -> None:
        """Start one receiver for a concrete gateway, if needed."""
        existing = self._receivers.get(gateway_key)
        if existing is not None and existing.is_alive:
            return

        config = state.get("config")
        market_endpoint = getattr(config, "market_endpoint", None)
        if not market_endpoint:
            return

        receiver = _ZmqTickReceiver(source, market_endpoint)
        receiver.start()
        self._receivers[gateway_key] = receiver
        logger.info("Started ZMQ receiver for %s gateway %s", source, gateway_key)

    def _subscribe_symbols_on_gateway(self, source: str, symbols: list[str]) -> None:
        """Subscribe source-level symbols on the preferred concrete gateway."""
        manager = self._get_live_trading_manager()
        gateway_key, state = self._find_gateway_state_with_key(manager, source)
        if state is None:
            # Preserve the source-key fallback for integrations that expose a
            # config lookup but do not expose gateway state.
            config = self._find_gateway_config(manager, source)
            state = {"config": config} if config is not None else None
            gateway_key = source
        if state is None:
            return
        self._subscribe_symbols_on_gateway_state(source, gateway_key or source, state, symbols)

    def _subscribe_symbols_on_gateway_state(
        self,
        source: str,
        gateway_key: str,
        state: dict[str, Any],
        symbols: list[str],
    ) -> None:
        """Subscribe symbols once for a given gateway session."""
        if not symbols:
            return

        subscription_key = gateway_key or source
        subscribed = self._subscribed_symbols.setdefault(subscription_key, set())
        new_syms = [s for s in symbols if s not in subscribed]
        if not new_syms:
            return

        config = state.get("config")
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
                    subscribed.update(accepted_symbols)
                    logger.info(
                        "Subscribed %d symbols on %s gateway %s: %s",
                        len(accepted_symbols),
                        source,
                        subscription_key,
                        accepted_symbols[:5],
                    )
                if skipped_symbols:
                    logger.warning(
                        "Skipped %d symbols on %s gateway %s due to rejection: %s",
                        len(skipped_symbols),
                        source,
                        subscription_key,
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
    def _snapshot_gateway_states(manager: Any) -> dict[str, dict[str, Any]]:
        """Safely snapshot the manager's in-memory gateway registry."""
        if manager is None:
            return {}
        try:
            lock = getattr(manager, "_gateway_lock", None)
            if lock is None:
                states = dict(getattr(manager, "_gateways", {}))
            else:
                with lock:
                    states = dict(getattr(manager, "_gateways", {}))
            return {
                str(gateway_key): state
                for gateway_key, state in states.items()
                if isinstance(state, dict) and state.get("config") is not None
            }
        except Exception:
            logger.debug("Unable to snapshot gateway states for quote monitoring", exc_info=True)
            return {}

    def _get_running_workspace_context(
        self,
        manager: Any,
        user_id: str,
        workspace_names: dict[str, str] | None = None,
    ) -> dict[str, dict[str, dict[str, Any]]]:
        """Group running workspace instruments by source and gateway.

        Only instances belonging to the current user are included.  The
        result is intentionally keyed by concrete gateway session, which
        prevents duplicate subscriptions when many strategy units share one
        gateway while still preserving separate sessions of the same exchange.
        """
        if manager is None or not user_id:
            return {}
        try:
            instances = manager.list_instances(user_id=user_id)
        except Exception:
            logger.debug("Unable to list running workspace instances", exc_info=True)
            return {}

        states = self._snapshot_gateway_states(manager)
        instance_gateways: dict[str, str] = {}
        try:
            lock = getattr(manager, "_gateway_lock", None)
            if lock is None:
                instance_gateways = {
                    str(instance_id): str(gateway_key)
                    for instance_id, gateway_key in getattr(manager, "_instance_gateways", {}).items()
                }
            else:
                with lock:
                    instance_gateways = {
                        str(instance_id): str(gateway_key)
                        for instance_id, gateway_key in getattr(manager, "_instance_gateways", {}).items()
                    }
        except Exception:
            logger.debug("Unable to read instance gateway assignments", exc_info=True)

        names = workspace_names or {}
        context: dict[str, dict[str, dict[str, Any]]] = {}
        for instance in instances:
            if str(instance.get("status") or "").lower() != "running":
                continue
            params = instance.get("params")
            if not isinstance(params, dict):
                continue
            workspace_unit = params.get("workspace_unit")
            if not isinstance(workspace_unit, dict):
                # Regular live-trading instances remain available as manual
                # subscriptions but are not presented as a trading workspace.
                continue
            workspace_id = str(workspace_unit.get("workspace_id") or "").strip()
            if not workspace_id:
                continue
            symbol = str(params.get("symbol") or "").strip()
            if not symbol:
                continue
            instance_id = str(instance.get("id") or "").strip()
            gateway_key = instance_gateways.get(instance_id, "")
            if not gateway_key:
                for candidate_key, state in states.items():
                    linked_instances = state.get("instances", set()) or set()
                    if instance_id in {str(item) for item in linked_instances}:
                        gateway_key = candidate_key
                        break
            state = states.get(gateway_key)
            if state is None:
                continue
            source = str(state.get("exchange_type") or "").strip().upper()
            if not source:
                continue

            source_context = context.setdefault(source, {})
            gateway = source_context.setdefault(
                gateway_key,
                {
                    "state": state,
                    "symbols": {},
                    "workspaces": {},
                },
            )
            symbol_key = symbol.upper()
            workspace_name = str(
                names.get(workspace_id) or workspace_unit.get("workspace_name") or workspace_id
            ).strip()
            gateway["symbols"].setdefault(
                symbol_key,
                {
                    "symbol": symbol,
                    "workspace_ids": set(),
                    "workspace_names": set(),
                },
            )
            gateway["symbols"][symbol_key]["workspace_ids"].add(workspace_id)
            gateway["symbols"][symbol_key]["workspace_names"].add(workspace_name)
            workspace = gateway["workspaces"].setdefault(
                workspace_id,
                {
                    "workspace_id": workspace_id,
                    "workspace_name": workspace_name,
                    "symbols": set(),
                },
            )
            workspace["symbols"].add(symbol)
        return context

    def _get_source_gateway_states(
        self,
        manager: Any,
        source: str,
        workspace_context: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Return visible manual and running-workspace gateways for a source."""
        normalized_source = str(source or "").strip().upper()
        result: dict[str, dict[str, Any]] = {}
        for gateway_key, state in self._snapshot_gateway_states(manager).items():
            if (
                str(state.get("exchange_type") or "").strip().upper() == normalized_source
                and bool(state.get("manual"))
            ):
                result[gateway_key] = state
        for gateway_key, gateway in (workspace_context or {}).items():
            state = gateway.get("state")
            if isinstance(state, dict):
                result[gateway_key] = state
        return result

    @staticmethod
    def _build_workspace_runs(
        workspace_context: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Format workspace monitor metadata for the data-source endpoint."""
        runs: list[dict[str, Any]] = []
        for gateway_key, gateway in workspace_context.items():
            for workspace in gateway["workspaces"].values():
                symbols = sorted(workspace["symbols"])
                runs.append(
                    {
                        "workspace_id": workspace["workspace_id"],
                        "workspace_name": workspace["workspace_name"],
                        "gateway_key": gateway_key,
                        "symbol_count": len(symbols),
                        "symbols": symbols,
                    }
                )
        return sorted(runs, key=lambda item: (item["workspace_name"], item["gateway_key"]))

    def _ensure_mt5_gateway_connected(self, manager: Any) -> None:
        if manager is None:
            return
        restore_in_progress = getattr(manager, "is_gateway_restore_in_progress", None)
        if callable(restore_in_progress) and restore_in_progress():
            logger.info("Deferring MT5 quote auto-connect while gateway recovery is in progress")
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
        return self._is_gateway_state_ready(state)

    def _is_gateway_state_ready(self, state: dict[str, Any] | None) -> bool:
        """Return whether a gateway has an accepting command channel."""
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
        _gateway_key, state = self._find_gateway_state_with_key(manager, source)
        return state

    def _find_gateway_state_with_key(
        self,
        manager: Any,
        source: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Find the preferred gateway session and return both key and state."""
        normalized_source = str(source or "").strip().upper()
        candidates = [
            (gateway_key, state)
            for gateway_key, state in self._snapshot_gateway_states(manager).items()
            if str(state.get("exchange_type") or "").strip().upper() == normalized_source
        ]
        manual = [(key, state) for key, state in candidates if state.get("manual")]
        preferred = manual or candidates
        for gateway_key, state in preferred:
            if self._is_gateway_state_ready(state):
                return gateway_key, state
        if preferred:
            return preferred[0]
        return "", None

    def _build_quote_plans(
        self,
        manager: Any,
        source: str,
        subscription_symbols: list[str],
        workspace_context: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Build deduplicated ``gateway + symbol`` quote requests.

        An instrument can appear in a watchlist and in multiple strategy
        units.  It is requested once for that gateway and its displayed row
        carries every origin.  The same symbol on a different gateway remains
        a separate row because it can represent a different market session.
        """
        plans: dict[str, dict[str, Any]] = {}

        def ensure_plan(gateway_key: str, state: dict[str, Any] | None) -> dict[str, Any]:
            return plans.setdefault(
                gateway_key,
                {"state": state, "symbols": {}},
            )

        def add_symbol(
            plan: dict[str, Any],
            symbol: str,
            *,
            origin: str,
            workspace_ids: set[str] | None = None,
            workspace_names: set[str] | None = None,
        ) -> None:
            normalized = str(symbol or "").strip()
            if not normalized:
                return
            symbol_key = normalized.upper()
            item = plan["symbols"].setdefault(
                symbol_key,
                {
                    "symbol": normalized,
                    "origins": set(),
                    "workspace_ids": set(),
                    "workspace_names": set(),
                },
            )
            item["origins"].add(origin)
            item["workspace_ids"].update(workspace_ids or set())
            item["workspace_names"].update(workspace_names or set())

        source_states = self._get_source_gateway_states(manager, source, workspace_context)
        if source_states:
            ready = [
                (gateway_key, state)
                for gateway_key, state in source_states.items()
                if self._is_gateway_state_ready(state)
            ]
            subscription_key, subscription_state = (ready or list(source_states.items()))[0]
        else:
            subscription_key, subscription_state = self._find_gateway_state_with_key(manager, source)
            subscription_key = subscription_key or source
        subscription_plan = ensure_plan(subscription_key, subscription_state)
        for symbol in subscription_symbols:
            add_symbol(subscription_plan, symbol, origin="subscription")

        for gateway_key, gateway in workspace_context.items():
            plan = ensure_plan(gateway_key, gateway.get("state"))
            for metadata in gateway["symbols"].values():
                add_symbol(
                    plan,
                    metadata["symbol"],
                    origin="workspace",
                    workspace_ids=metadata["workspace_ids"],
                    workspace_names=metadata["workspace_names"],
                )
        return plans

    def _get_receiver_for_plan(
        self,
        source: str,
        gateway_key: str,
        state: dict[str, Any] | None,
    ) -> _ZmqTickReceiver | None:
        """Find the receiver for a concrete quote plan, with legacy fallback."""
        receiver = self._receivers.get(gateway_key)
        if receiver is not None:
            return receiver
        if state is None or gateway_key == source:
            return self._receivers.get(source)
        return None

    def _hydrate_snapshot_ticks(
        self,
        manager: Any,
        source: str,
        receiver: _ZmqTickReceiver | None,
        symbols: list[str],
        cached_ticks: dict[str, dict[str, Any]],
        state: dict[str, Any] | None = None,
        max_snapshots: int | None = None,
    ) -> dict[str, dict[str, Any]]:
        if not symbols:
            return cached_ticks
        runtime = state.get("runtime") if state is not None else None
        if runtime is None:
            runtime = self._get_gateway_runtime(manager, "IB_WEB")
            if source != "IB_WEB":
                runtime = self._get_gateway_runtime(manager, source)
        adapter = getattr(runtime, "adapter", None)
        feed = getattr(adapter, "feed", None)
        if feed is None or not hasattr(feed, "get_tick"):
            return cached_ticks
        hydrated = dict(cached_ticks)
        hydrated_count = 0
        for symbol in symbols:
            if match_cached_tick(hydrated, symbol) is not None:
                continue
            if max_snapshots is not None and hydrated_count >= max_snapshots:
                break
            raw = self._fetch_gateway_snapshot_tick(source, feed, symbol)
            if raw is None:
                continue
            hydrated[symbol] = raw
            hydrated_count += 1
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
