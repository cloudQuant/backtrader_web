import contextlib
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

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


@contextlib.contextmanager
def _redirect_gateway_native_stdio(strategy_dir: Path):
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


def _asset_type_requires_contract_spec(gateway: dict[str, Any] | None, spec: dict[str, Any]) -> bool:
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
        runtime_symbols if runtime_symbols is not None else symbols_for_instance(instance, strategy_dir)
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
        raise RuntimeError(
            "实盘策略启动前未获取到交易资产规格: " + ", ".join(sorted(set(missing)))
        )
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
    bt_api_py_dir: Path,
    backtrader_dir: Path | None = None,
) -> dict[str, str]:
    env = dict(os_environ)
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
        runtime_symbols = symbols_for_instance(instance, strategy_dir) if gateway is not None else None
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


def _latest_runtime_error(runtime: Any) -> str:
    health = getattr(runtime, "health", None)
    recent_errors = getattr(health, "recent_errors", None) or []
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
        state = str(getattr(health, "state", "") or "")
        market_connection = str(getattr(health, "market_connection", "") or "")
        trade_connection = str(getattr(health, "trade_connection", "") or "")
        if (
            state == "running"
            and market_connection == "connected"
            and trade_connection == "connected"
        ):
            return

        runtime_running = bool(getattr(runtime, "running", False))
        if state == "error" or (
            state and state not in {"created", "connecting"} and not runtime_running
        ):
            detail = _latest_runtime_error(runtime) or state
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
            state = str(getattr(health, "state", "") or "")
            market_connection = str(getattr(health, "market_connection", "") or "")
            trade_connection = str(getattr(health, "trade_connection", "") or "")
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
    if str(runtime_kwargs.get("exchange_type") or "").upper() == "IB_WEB":
        from app.services.gateway.manual import _ensure_ib_clientportal_running

        _ensure_ib_clientportal_running(
            str(runtime_kwargs.get("base_url") or "https://localhost:5000"),
            logger,
            startup_wait_sec=float(runtime_kwargs.get("gateway_startup_timeout_sec") or 30.0),
        )
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
    runtime = state.get("runtime")
    if runtime is not None:
        try:
            runtime.stop()
        except (RuntimeError, OSError):
            logger.debug("Gateway runtime stop error for %s (ignored)", key, exc_info=True)
    gateways.pop(key, None)
