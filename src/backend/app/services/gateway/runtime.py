import contextlib
import os
import threading
import time
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.services.gateway.launch_builder import build_gateway_session_key_from_runtime_kwargs

_LIVE_SUBPROCESS_THREAD_DEFAULTS = {
    "BACKTRADER_LIGHT_IMPORT": "1",
    "BT_API_PY_LIGHT_IMPORT": "1",
    "BT_FEED_ENABLE_LIGHT_COLUMNS": "1",
    "BT_STORE_LOCAL_TIMEZONE": "Asia/Shanghai",
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "BLIS_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
}
_GATEWAY_STDIO_REDIRECT_LOCK = threading.RLock()
_GATEWAY_STDOUT_LOG = "gateway.stdout.log"
_GATEWAY_STDERR_LOG = "gateway.stderr.log"
_MT5_ADAPTER_STARTUP_ATTEMPTS = 3
_MT5_ADAPTER_STARTUP_RETRY_SEC = 2.0
_IB_WEB_SESSION_FIELDS = (
    "account_id",
    "asset_type",
    "base_url",
    "access_token",
    "verify_ssl",
    "timeout",
    "cookie_source",
    "cookie_browser",
    "cookie_path",
    "cookie_output",
    "cookies",
    "username",
    "password",
    "login_mode",
    "login_browser",
    "login_headless",
    "login_timeout",
)


@contextlib.contextmanager
def _redirect_gateway_native_stdio(strategy_dir: Path) -> Generator[None, None, None]:
    """Capture native gateway stdout/stderr during startup probes."""
    stdout_copy = None
    stderr_copy = None
    stdout_handle = None
    stderr_handle = None
    with _GATEWAY_STDIO_REDIRECT_LOCK:
        try:
            logs_dir = strategy_dir / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            stdout_handle = (logs_dir / _GATEWAY_STDOUT_LOG).open("ab", buffering=0)
            stderr_handle = (logs_dir / _GATEWAY_STDERR_LOG).open("ab", buffering=0)
            stdout_copy = os.dup(1)
            stderr_copy = os.dup(2)
            os.dup2(stdout_handle.fileno(), 1)
            os.dup2(stderr_handle.fileno(), 2)
        except OSError:
            if stdout_copy is not None:
                with contextlib.suppress(OSError):
                    os.dup2(stdout_copy, 1)
            if stderr_copy is not None:
                with contextlib.suppress(OSError):
                    os.dup2(stderr_copy, 2)
            for handle in (stdout_handle, stderr_handle):
                if handle is not None:
                    with contextlib.suppress(OSError):
                        handle.close()
            yield
            return

        try:
            yield
        finally:
            if stdout_copy is not None:
                with contextlib.suppress(OSError):
                    os.dup2(stdout_copy, 1)
            if stderr_copy is not None:
                with contextlib.suppress(OSError):
                    os.dup2(stderr_copy, 2)
            for fd in (stdout_copy, stderr_copy):
                if fd is not None:
                    with contextlib.suppress(OSError):
                        os.close(fd)
            for handle in (stdout_handle, stderr_handle):
                if handle is not None:
                    with contextlib.suppress(OSError):
                        handle.close()


def _resolve_gateway_state_session_key(state: dict[str, Any]) -> str:
    session_key = str(state.get("session_key") or "").strip()
    if session_key:
        return session_key
    config = state.get("config")
    if config is None:
        return ""
    runtime_kwargs = {
        "exchange_type": getattr(config, "exchange_type", "")
        if not isinstance(config, dict)
        else config.get("exchange_type", ""),
        "asset_type": getattr(config, "asset_type", "")
        if not isinstance(config, dict)
        else config.get("asset_type", ""),
        "account_id": getattr(config, "account_id", "")
        if not isinstance(config, dict)
        else config.get("account_id", ""),
        "broker_id": getattr(config, "broker_id", "")
        if not isinstance(config, dict)
        else config.get("broker_id", ""),
        "td_address": getattr(config, "td_address", "")
        if not isinstance(config, dict)
        else config.get("td_address", ""),
        "md_address": getattr(config, "md_address", "")
        if not isinstance(config, dict)
        else config.get("md_address", ""),
        "base_url": getattr(config, "base_url", "")
        if not isinstance(config, dict)
        else config.get("base_url", ""),
        "login_mode": getattr(config, "login_mode", "")
        if not isinstance(config, dict)
        else config.get("login_mode", ""),
        "testnet": getattr(config, "testnet", None)
        if not isinstance(config, dict)
        else config.get("testnet"),
        "server": getattr(config, "server", "")
        if not isinstance(config, dict)
        else config.get("server", ""),
        "ws_uri": getattr(config, "ws_uri", "")
        if not isinstance(config, dict)
        else config.get("ws_uri", ""),
    }
    resolved = build_gateway_session_key_from_runtime_kwargs(runtime_kwargs)
    if resolved:
        state["session_key"] = resolved
    return resolved


def _find_gateway_key_by_session_key(
    gateways: dict[str, dict[str, Any]],
    session_key: str,
) -> str | None:
    if not session_key:
        return None
    for key, state in gateways.items():
        if not isinstance(state, dict):
            continue
        if _resolve_gateway_state_session_key(state) != session_key:
            continue
        if state.get("runtime") is None:
            continue
        return key
    return None


def _refresh_ib_web_session_for_launch(launch: dict[str, Any], logger: Any) -> None:
    """Ensure an IB Client Portal session is valid before starting a runtime.

    Strategy startup used to only launch Client Portal.  That left an expired
    browser-cookie session untouched, so the gateway started with stale
    credentials and failed later with an opaque 401.  Reuse the manual gateway
    login flow here: it validates existing cookies, opens/reuses the configured
    login flow when necessary, and injects the refreshed session into the
    runtime that is about to start.
    """
    from app.services.gateway import manual as manual_gateway_service

    runtime_kwargs = launch["runtime_kwargs"]
    credentials = {
        key: runtime_kwargs[key]
        for key in _IB_WEB_SESSION_FIELDS
        if key in runtime_kwargs and runtime_kwargs[key] is not None and runtime_kwargs[key] != ""
    }
    base_url = manual_gateway_service._normalize_ib_web_base_url(
        str(credentials.get("base_url") or "https://localhost:5000")
    )
    verify_ssl = bool(credentials.get("verify_ssl", False))
    timeout = float(credentials.get("timeout") or 10.0)
    manual_gateway_service._ensure_ib_clientportal_running(
        base_url,
        logger,
        startup_wait_sec=float(runtime_kwargs.get("gateway_startup_timeout_sec") or 30.0),
    )
    base_url = manual_gateway_service._resolve_ib_web_base_url(
        base_url,
        verify_ssl,
        timeout,
        logger,
    )
    credentials["base_url"] = base_url
    runtime_kwargs["base_url"] = base_url

    session = manual_gateway_service._bootstrap_ib_web_session(
        credentials,
        base_url,
        verify_ssl,
        timeout,
        allow_interactive_login=True,
    )
    if session is None:
        has_session_login_config = any(
            credentials.get(key)
            for key in ("cookies", "cookie_source", "cookie_output", "username", "password")
        )
        if has_session_login_config and not credentials.get("access_token"):
            raise RuntimeError(
                "IB Client Portal 会话已失效且自动登录未完成；"
                "请在打开的 Client Portal 窗口完成登录后重试"
            )
        logger.warning(
            "IB Client Portal did not return a browser session; continuing with configured token auth"
        )
        return

    resolved_account_id = str(
        session.get("account_id") or credentials.get("account_id") or ""
    ).strip()
    if resolved_account_id:
        credentials["account_id"] = resolved_account_id
        runtime_kwargs["account_id"] = resolved_account_id
    cookie_output = str(session.get("cookie_output") or "").strip()
    if cookie_output:
        cookie_output = manual_gateway_service._to_backend_env_relative_path(cookie_output)
        credentials["cookie_output"] = cookie_output
        credentials["cookie_source"] = f"file:{cookie_output}"
        runtime_kwargs["cookie_output"] = cookie_output
        runtime_kwargs["cookie_source"] = f"file:{cookie_output}"
    elif session.get("cookie_source"):
        cookie_source = str(session["cookie_source"])
        credentials["cookie_source"] = cookie_source
        runtime_kwargs["cookie_source"] = cookie_source
    if isinstance(session.get("cookies"), dict) and session["cookies"]:
        runtime_kwargs["cookies"] = session["cookies"]

    manual_gateway_service._persist_ib_web_env_updates(
        manual_gateway_service._build_ib_web_env_updates(
            credentials,
            base_url,
            verify_ssl,
            timeout,
            session,
        )
    )

    config_factory = getattr(type(launch["config"]), "from_kwargs", None)
    if callable(config_factory):
        launch["config"] = config_factory(**runtime_kwargs)


def _discard_idle_ib_gateway_with_auth_failure(
    key: str,
    state: dict[str, Any] | None,
    gateways: dict[str, dict[str, Any]],
    logger: Any,
) -> dict[str, Any] | None:
    """Drop an idle IB runtime whose recorded auth error requires a fresh login."""
    if not isinstance(state, dict) or int(state.get("ref_count") or 0) > 0:
        return state
    runtime = state.get("runtime")
    if runtime is None or not _is_non_retriable_gateway_error(_latest_runtime_error(runtime)):
        return state
    try:
        runtime.stop()
    except (AttributeError, OSError, RuntimeError):
        logger.debug("Failed to stop expired IB gateway %s", key, exc_info=True)
    gateways.pop(key, None)
    logger.info("Discarded expired idle IB gateway %s before re-authentication", key)
    return None


def _prepend_python_paths(env: dict[str, str], paths: list[Path | None]) -> None:
    entries: list[str] = []
    seen: set[str] = set()

    for path in paths:
        if path is None or not path.is_dir():
            continue
        entry = str(path)
        if entry in seen:
            continue
        entries.append(entry)
        seen.add(entry)

    existing = env.get("PYTHONPATH", "")
    if existing:
        for entry in existing.split(os.pathsep):
            if entry in seen:
                continue
            entries.append(entry)
            seen.add(entry)

    if entries:
        env["PYTHONPATH"] = os.pathsep.join(entries)


_CONTRACT_SPEC_KEYS = (
    "multiplier",
    "contract_multiplier",
    "contract_size",
    "contract_notional_value",
    "okx_contract_value",
    "ctVal",
    "VolumeMultiple",
)
_MARGIN_SPEC_KEYS = (
    "margin",
    "margin_rate",
    "long_margin_rate",
    "short_margin_rate",
    "margin_ratio",
    "margin_initial",
    "initial_margin",
    "margin_amount",
    "initial_margin_per_lot",
    "margin_initial_per_lot",
    "margin_value",
    "use_margin",
    "imr",
    "mmr",
    "positionIM",
    "positionIMByMp",
    "MARGIN_PER_LOT",
    "LONG_MARGIN_AMOUNT",
    "SHORT_MARGIN_AMOUNT",
    "LongMarginRatioByMoney",
    "ShortMarginRatioByMoney",
    "LongMarginRatioByVolume",
    "ShortMarginRatioByVolume",
    "longMarginRatioByMoney",
    "shortMarginRatioByMoney",
    "leverage",
    "lever",
    "max_leverage",
    "maxLeverage",
)
_FEE_SPEC_KEYS = (
    "commission_rate",
    "open_commission_rate",
    "close_commission_rate",
    "close_today_commission_rate",
    "close_yesterday_commission_rate",
    "maker_commission_rate",
    "taker_commission_rate",
    "commission_amount",
    "open_commission_amount",
    "close_commission_amount",
    "close_today_commission_amount",
    "close_yesterday_commission_amount",
    "OpenRatioByMoney",
    "CloseRatioByMoney",
    "CloseTodayRatioByMoney",
    "CloseYesterdayRatioByMoney",
    "OpenRatioByVolume",
    "CloseRatioByVolume",
    "CloseTodayRatioByVolume",
    "CloseYesterdayRatioByVolume",
    "COMMISSION_OPEN_RATIO",
    "COMMISSION_CLOSE_RATIO",
    "COMMISSION_CLOSE_TODAY_RATIO",
    "COMMISSION_CLOSE_YESTERDAY_RATIO",
    "COMMISSION_OPEN_AMOUNT",
    "COMMISSION_CLOSE_AMOUNT",
    "COMMISSION_CLOSE_TODAY_AMOUNT",
    "COMMISSION_CLOSE_YESTERDAY_AMOUNT",
)
_CONTRACT_ASSET_TYPES = {
    "CFD",
    "COIN-M",
    "COIN_M",
    "FOP",
    "FOREX",
    "FUTURE",
    "FUTURES",
    "OPTION",
    "PERP",
    "PERPETUAL",
    "SWAP",
}


def _gateway_config_value(gateway: dict[str, Any] | None, field: str) -> Any:
    if not isinstance(gateway, dict):
        return None
    config = gateway.get("config")
    if isinstance(config, dict):
        value = config.get(field)
    else:
        value = getattr(config, field, None)
    if value not in (None, ""):
        return value
    return gateway.get(field)


def _positive_spec_number(spec: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        value = spec.get(key)
        if value in (None, ""):
            continue
        try:
            if float(value) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _has_spec_value(spec: dict[str, Any], *keys: str) -> bool:
    return any(spec.get(key) not in (None, "") for key in keys)


def _asset_type_requires_contract_spec(
    gateway: dict[str, Any] | None, spec: dict[str, Any]
) -> bool:
    values = (
        spec.get("asset_type"),
        spec.get("instType"),
        _gateway_config_value(gateway, "asset_type"),
        _gateway_config_value(gateway, "exchange_type"),
    )
    text = " ".join(str(value or "").upper().replace("-", "_") for value in values)
    return any(token in text for token in _CONTRACT_ASSET_TYPES)


def _runtime_spec_for_symbol(
    specs: dict[str, dict[str, Any]],
    symbol: str,
    symbol_aliases: Callable[[str], list[str]],
) -> dict[str, Any]:
    aliases = [symbol]
    try:
        aliases.extend(symbol_aliases(symbol))
    except Exception:
        pass
    aliases = [str(alias or "").strip() for alias in aliases if str(alias or "").strip()]
    compact_aliases = {"".join(ch for ch in alias if ch.isalnum()).upper() for alias in aliases}
    for alias in aliases:
        item = specs.get(alias)
        if isinstance(item, dict) and item:
            return item
    for key, item in specs.items():
        if not isinstance(item, dict) or not item:
            continue
        key_text = str(key or "").strip()
        if key_text in aliases:
            return item
        compact_key = "".join(ch for ch in key_text if ch.isalnum()).upper()
        if compact_key and compact_key in compact_aliases:
            return item
    return {}


def _validate_runtime_asset_specs(
    instance: dict[str, Any],
    strategy_dir: Path,
    gateway: dict[str, Any] | None,
    specs: dict[str, dict[str, Any]],
    symbols_for_instance: Callable[[dict[str, Any], Path], list[str]],
    symbol_aliases: Callable[[str], list[str]],
    runtime_symbols: list[str] | None = None,
) -> None:
    if gateway is None:
        return

    symbols: list[str] = []
    seen_symbols: set[str] = set()
    for symbol in (
        runtime_symbols
        if runtime_symbols is not None
        else symbols_for_instance(instance, strategy_dir)
    ):
        text = str(symbol or "").strip()
        key = text.upper()
        if not text or key in seen_symbols:
            continue
        symbols.append(text)
        seen_symbols.add(key)
    if not symbols:
        return

    missing: list[str] = []
    incomplete: list[str] = []
    for symbol in symbols:
        spec = _runtime_spec_for_symbol(specs, symbol, symbol_aliases)
        if not spec:
            missing.append(symbol)
            continue
        if _asset_type_requires_contract_spec(gateway, spec):
            if not _positive_spec_number(spec, *_CONTRACT_SPEC_KEYS):
                incomplete.append(f"{symbol}: missing contract multiplier/value")
            if not _positive_spec_number(spec, *_MARGIN_SPEC_KEYS):
                incomplete.append(f"{symbol}: missing margin/leverage metadata")
            if not _has_spec_value(spec, *_FEE_SPEC_KEYS):
                incomplete.append(f"{symbol}: missing commission/fee metadata")

    if missing:
        raise RuntimeError("实盘策略启动前未获取到交易资产规格: " + ", ".join(sorted(set(missing))))
    if incomplete:
        raise RuntimeError(
            "实盘策略启动前交易资产规格不完整: " + "; ".join(sorted(set(incomplete)))
        )


def build_subprocess_env(
    instance_id: str,
    instance: dict[str, Any],
    strategy_dir: Path,
    acquire_gateway_for_instance: Callable[..., Any],
    os_environ: dict[str, str],
    bt_api_py_dir: Path | None,
    backtrader_dir: Path | None = None,
) -> dict[str, str]:
    env = dict(os_environ)
    # Strategy runners execute from generated workspace directories, where the
    # relative ``.env`` resolution can differ from the API process.  Propagate
    # the API's resolved mode so a development server is not treated as
    # production merely because a different dotenv file is discovered.
    env["DEBUG"] = "true" if get_settings().DEBUG else "false"
    for key, value in _LIVE_SUBPROCESS_THREAD_DEFAULTS.items():
        env.setdefault(key, value)
    env["BT_TRADING_INSTANCE_ID"] = str(instance_id)
    _prepend_python_paths(env, [backtrader_dir, bt_api_py_dir])
    gateway = acquire_gateway_for_instance(instance_id, instance, strategy_dir)
    if gateway is None:
        _refresh_runtime_asset_specs(instance, strategy_dir, None)
        return env
    with _redirect_gateway_native_stdio(strategy_dir):
        wait_gateway_runtime_ready(gateway)
    _refresh_runtime_asset_specs(instance, strategy_dir, gateway)
    config = gateway["config"]
    env["BT_STORE_PROVIDER"] = "mt5_gateway" if config.exchange_type == "MT5" else "ctp_gateway"
    env["BT_GATEWAY_START_LOCAL_RUNTIME"] = "0"
    env["BT_GATEWAY_COMMAND_ENDPOINT"] = config.command_endpoint
    env["BT_GATEWAY_EVENT_ENDPOINT"] = config.event_endpoint
    env["BT_GATEWAY_MARKET_ENDPOINT"] = config.market_endpoint
    env["BT_GATEWAY_ACCOUNT_ID"] = config.account_id
    env["BT_GATEWAY_EXCHANGE_TYPE"] = config.exchange_type
    env["BT_GATEWAY_ASSET_TYPE"] = config.asset_type
    env["BT_GATEWAY_STARTUP_TIMEOUT_SEC"] = str(config.startup_timeout_sec)
    env["BT_GATEWAY_COMMAND_TIMEOUT_SEC"] = str(config.command_timeout_sec)
    return env


def _refresh_runtime_asset_specs(
    instance: dict[str, Any],
    strategy_dir: Path,
    gateway: dict[str, Any] | None,
) -> None:
    try:
        from app.services.trading_asset_info_service import (
            refresh_instance_asset_specs,
            symbol_aliases,
            symbols_for_instance,
        )
    except Exception as exc:
        if gateway is not None:
            raise RuntimeError(f"实盘策略启动前加载资产信息服务失败: {exc}") from exc
        return
    try:
        runtime_symbols = (
            symbols_for_instance(instance, strategy_dir) if gateway is not None else None
        )
        specs = refresh_instance_asset_specs(instance, strategy_dir, gateway)
        _validate_runtime_asset_specs(
            instance,
            strategy_dir,
            gateway,
            specs,
            symbols_for_instance,
            symbol_aliases,
            runtime_symbols=runtime_symbols,
        )
    except Exception as exc:
        if gateway is not None:
            raise RuntimeError(f"实盘策略启动前刷新交易资产信息失败: {exc}") from exc
        return


def restore_gateway_subscription(
    instance_id: str,
    instance: dict[str, Any],
    strategy_dir: Path,
    gateway: dict[str, Any],
) -> list[str]:
    """Restore a surviving strategy's market subscription after API restart."""
    from app.services.trading_asset_info_service import symbols_for_instance

    symbols = list(dict.fromkeys(symbols_for_instance(instance, strategy_dir)))
    if not symbols:
        return []
    runtime = gateway.get("runtime")
    dispatch = getattr(runtime, "_dispatch", None)
    if not callable(dispatch):
        raise RuntimeError("gateway runtime cannot restore strategy subscriptions")
    result = dispatch(
        "register_strategy",
        {"strategy_id": instance_id, "symbols": symbols},
    )
    if not isinstance(result, dict):
        raise RuntimeError("gateway returned an invalid subscription result")
    accepted = [str(symbol) for symbol in result.get("accepted") or [] if str(symbol)]
    if not accepted:
        raise RuntimeError(f"gateway did not accept market subscription for {instance_id}")
    return accepted


def _latest_runtime_error(runtime: Any) -> str:
    health = getattr(runtime, "health", None)
    snapshot = _gateway_health_snapshot(health)
    recent_errors = snapshot.get("recent_errors") or getattr(health, "recent_errors", None) or []
    if not isinstance(recent_errors, (list, tuple)):
        return ""
    if not recent_errors:
        return ""
    latest = recent_errors[-1]
    if isinstance(latest, dict):
        source = str(latest.get("source") or "runtime").strip()
        message = str(latest.get("message") or "").strip()
        return f"{source}: {message}" if message else source
    return str(latest)


def _is_non_retriable_gateway_error(message: str) -> bool:
    """Return whether a runtime error cannot be fixed by waiting for another poll."""
    normalized = str(message or "").strip().lower()
    return any(
        marker in normalized
        for marker in (
            "invalid_api_key",
            "invalid api key",
            "http 401",
            "unauthorized",
            "auth error",
            "authentication failed",
            "invalid token",
            "invalid password",
            "invalid credentials",
            "login failed",
            "access denied",
        )
    )


def _connect_mt5_adapter_with_retry(
    runtime: Any,
    logger: Any,
    *,
    attempts: int = _MT5_ADAPTER_STARTUP_ATTEMPTS,
    retry_delay_sec: float = _MT5_ADAPTER_STARTUP_RETRY_SEC,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Connect an MT5 adapter and verify its account transport before launch.

    A WebSocket reset during ``Mt5GatewayAdapter.connect`` leaves some adapter
    versions with their internal ``_running`` flag set.  Their next
    ``connect`` then becomes a no-op, while the transport is still unusable.
    Resetting the adapter before retrying prevents a strategy subprocess from
    being launched against that stale transport.
    """
    adapter = getattr(runtime, "adapter", None)
    connect = getattr(adapter, "connect", None)
    get_balance = getattr(adapter, "get_balance", None)
    disconnect = getattr(adapter, "disconnect", None)
    if not callable(connect) or not callable(get_balance):
        raise RuntimeError("MT5 gateway adapter does not support startup readiness checks")

    total_attempts = max(int(attempts), 1)
    last_error: Exception | None = None
    for attempt in range(1, total_attempts + 1):
        try:
            connect()
            # A successful socket/login handshake alone is insufficient for
            # pymt5: its transport can still be resetting.  This read-only
            # command is the same first command issued by BtApiStore.
            get_balance()
            return
        except Exception as exc:
            last_error = exc
            if callable(disconnect):
                try:
                    disconnect()
                except Exception:
                    logger.debug(
                        "MT5 adapter cleanup after failed startup was unsuccessful", exc_info=True
                    )
            if _is_non_retriable_gateway_error(str(exc)) or attempt >= total_attempts:
                break
            logger.warning(
                "MT5 gateway startup attempt {}/{} failed; reconnecting: {}: {}",
                attempt,
                total_attempts,
                type(exc).__name__,
                exc,
            )
            sleep(max(float(retry_delay_sec), 0.0))

    detail = str(last_error or "unknown MT5 adapter error")
    raise RuntimeError(f"MT5 gateway transport did not become ready: {detail}")


def _gateway_health_snapshot(health: Any) -> dict[str, Any]:
    """Return a normalized health view for current and legacy runtime implementations."""
    snapshot_method = getattr(health, "snapshot", None)
    if callable(snapshot_method):
        try:
            snapshot = snapshot_method()
        except Exception:
            snapshot = None
        if isinstance(snapshot, dict):
            return snapshot
    return {
        "state": getattr(health, "state", ""),
        "market_connection": getattr(health, "market_connection", ""),
        "trade_connection": getattr(health, "trade_connection", ""),
        "recent_errors": getattr(health, "recent_errors", []),
    }


def wait_gateway_runtime_ready(
    gateway: dict[str, Any],
    *,
    timeout_sec: float | None = None,
    poll_interval_sec: float = 0.2,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Wait until an in-process gateway runtime is ready for strategy commands."""
    runtime = gateway.get("runtime")
    if runtime is None:
        return
    health = getattr(runtime, "health", None)
    if health is None:
        return
    config = gateway.get("config")
    if timeout_sec is None:
        timeout_sec = float(getattr(config, "startup_timeout_sec", 0.0) or 0.0)
    if timeout_sec <= 0:
        return

    deadline = monotonic() + timeout_sec
    while True:
        health_snapshot = _gateway_health_snapshot(health)
        state = str(health_snapshot.get("state") or "")
        market_connection = str(health_snapshot.get("market_connection") or "")
        trade_connection = str(health_snapshot.get("trade_connection") or "")
        # GatewayRuntime marks a successful adapter connection as market-ready.
        # Adapters such as CTP authenticate both market and trade streams inside
        # that single connection step, but do not separately mutate
        # ``health.trade_connection``.  Requiring both fields here therefore
        # turns healthy gateways into false startup timeouts.
        if state == "running" and market_connection == "connected":
            return

        latest_error = _latest_runtime_error(runtime)
        if _is_non_retriable_gateway_error(latest_error):
            raise RuntimeError(f"Gateway runtime failed to become ready: {latest_error}")

        runtime_running = bool(getattr(runtime, "running", False))
        if state == "error" or (
            state and state not in {"created", "connecting"} and not runtime_running
        ):
            detail = latest_error or state
            raise RuntimeError(f"Gateway runtime failed to become ready: {detail}")

        now = monotonic()
        if now >= deadline:
            thread = getattr(runtime, "thread", None)
            if thread is not None:
                try:
                    if thread.is_alive():
                        thread.join(timeout=min(max(poll_interval_sec, 0.1), 1.0))
                except RuntimeError:
                    pass
            health_snapshot = _gateway_health_snapshot(health)
            state = str(health_snapshot.get("state") or "")
            market_connection = str(health_snapshot.get("market_connection") or "")
            trade_connection = str(health_snapshot.get("trade_connection") or "")
            if state == "error":
                detail = _latest_runtime_error(runtime) or state
                raise RuntimeError(f"Gateway runtime failed to become ready: {detail}")
            detail = (
                f"state={state or 'unknown'}, "
                f"market={market_connection or 'unknown'}, "
                f"trade={trade_connection or 'unknown'}"
            )
            latest_error = _latest_runtime_error(runtime)
            if latest_error:
                detail = f"{detail}, recent_error={latest_error}"
            raise TimeoutError(
                f"Gateway runtime did not become ready within {timeout_sec:.1f}s: {detail}"
            )

        sleep(min(poll_interval_sec, max(deadline - now, 0.0)))


def acquire_gateway_for_instance(
    instance_id: str,
    instance: dict[str, Any],
    strategy_dir: Path,
    get_gateway_params: Callable[..., Any],
    build_gateway_launch: Callable[..., Any],
    gateways: dict[str, dict[str, Any]],
    instance_gateways: dict[str, str],
    logger: Any,
) -> dict[str, Any] | None:
    gateway_params = get_gateway_params(instance)
    if not gateway_params.get("enabled"):
        return None
    try:
        launch = build_gateway_launch(instance, strategy_dir, gateway_params)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        logger.warning(
            "Gateway launch config failed for {}, falling back to direct mode: {}",
            instance_id,
            exc,
        )
        return None
    runtime_kwargs = launch["runtime_kwargs"]
    key = launch["config"].runtime_name
    session_key = build_gateway_session_key_from_runtime_kwargs(runtime_kwargs)
    state = gateways.get(key)
    if state is None:
        matched_key = _find_gateway_key_by_session_key(gateways, session_key)
        if matched_key:
            key = matched_key
            state = gateways.get(matched_key)
    if state is not None and str(runtime_kwargs.get("exchange_type") or "").upper() == "IB_WEB":
        state = _discard_idle_ib_gateway_with_auth_failure(key, state, gateways, logger)
    if state is None and str(runtime_kwargs.get("exchange_type") or "").upper() == "IB_WEB":
        _refresh_ib_web_session_for_launch(launch, logger)
        runtime_kwargs = launch["runtime_kwargs"]
        key = launch["config"].runtime_name
        session_key = build_gateway_session_key_from_runtime_kwargs(runtime_kwargs)
        state = gateways.get(key)
        if state is None:
            matched_key = _find_gateway_key_by_session_key(gateways, session_key)
            if matched_key:
                key = matched_key
                state = gateways.get(matched_key)
    logger.info(
        "Gateway acquire for {}: key={}, existing={}, endpoints={}/{}/{}",
        instance_id,
        key,
        state is not None,
        launch["config"].command_endpoint,
        launch["config"].event_endpoint,
        launch["config"].market_endpoint,
    )
    if state is None:
        try:
            runtime = launch["runtime_cls"](launch["config"], **launch["runtime_kwargs"])
            with _redirect_gateway_native_stdio(strategy_dir):
                # The native CTP SDK completes its login callbacks only when
                # connect() is invoked by the calling thread.  GatewayRuntime
                # normally invokes adapters from a daemon thread, which leaves
                # CTP stuck in ``connecting`` even though the same credentials
                # work through the adapter directly.  Pre-connect CTP here;
                # GatewayRuntime's background attempt then becomes a no-op and
                # records the usual healthy runtime state.
                if str(runtime_kwargs.get("exchange_type") or "").upper() == "CTP":
                    adapter = getattr(runtime, "adapter", None)
                    adapter_connect = getattr(adapter, "connect", None)
                    if callable(adapter_connect):
                        adapter_connect()
                    # CTP reports the socket session before the trading client
                    # can always answer commands.  Verify the read-only account
                    # path before a strategy is allowed to issue its own first
                    # balance query; this prevents a false ``running`` state.
                    adapter_get_balance = getattr(adapter, "get_balance", None)
                    if callable(adapter_get_balance):
                        adapter_get_balance()
                elif str(runtime_kwargs.get("exchange_type") or "").upper() == "MT5":
                    _connect_mt5_adapter_with_retry(runtime, logger)
                runtime.start_in_thread()
        except (KeyError, TypeError, OSError, RuntimeError) as exc:
            logger.warning(
                "Gateway runtime failed to start for {}: {}",
                instance_id,
                exc,
            )
            raise
        state = {
            "config": launch["config"],
            "runtime": runtime,
            "instances": set(),
            "ref_count": 0,
            "lock": threading.Lock(),
            "manual": False,
            "exchange_type": launch["runtime_kwargs"].get("exchange_type", ""),
            "asset_type": launch["runtime_kwargs"].get("asset_type", ""),
            "account_id": launch["runtime_kwargs"].get("account_id", ""),
            "selected_ctp_env": launch["runtime_kwargs"].get("selected_ctp_env", ""),
            "td_front": launch["runtime_kwargs"].get("td_front")
            or launch["runtime_kwargs"].get("td_address", ""),
            "md_front": launch["runtime_kwargs"].get("md_front")
            or launch["runtime_kwargs"].get("md_address", ""),
            "selection_reason": launch["runtime_kwargs"].get("selection_reason", ""),
            "auth_state": launch["runtime_kwargs"].get("auth_state", "unknown"),
            "login_state": launch["runtime_kwargs"].get("login_state", "unknown"),
            "session_key": session_key,
        }
        gateways[key] = state
    elif session_key and not state.get("session_key"):
        state["session_key"] = session_key
    state["instances"].add(instance_id)
    state["ref_count"] += 1
    instance_gateways[instance_id] = key
    return state


def release_gateway_for_instance(
    instance_id: str,
    gateways: dict[str, dict[str, Any]],
    instance_gateways: dict[str, str],
    logger: Any,
) -> None:
    key = instance_gateways.pop(instance_id, None)
    if not key:
        return
    state = gateways.get(key)
    if state is None:
        return
    state["instances"].discard(instance_id)
    state["ref_count"] = max(int(state.get("ref_count", 0)) - 1, 0)
    if state["ref_count"] > 0:
        return
    if state.get("manual"):
        return
    exchange_type = str(state.get("exchange_type") or "").strip().upper()
    if exchange_type == "CTP":
        # The native CTP SDK owns callback threads beyond the Python adapter
        # lifecycle.  Tearing the last in-process runtime down can terminate
        # the API process once those callbacks race with native cleanup.  Keep
        # the authenticated session warm at ref_count=0 instead; a later unit
        # reuses it, and the process owner performs final native cleanup.
        logger.info("Keeping idle CTP gateway %s connected for safe reuse", key)
        return
    runtime = state.get("runtime")
    if runtime is not None:
        try:
            runtime.stop()
        except (RuntimeError, OSError):
            logger.debug("Gateway runtime stop error for %s (ignored)", key, exc_info=True)
    gateways.pop(key, None)
