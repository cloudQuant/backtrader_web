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
    _prepend_python_paths(env, [backtrader_dir, bt_api_py_dir])
    gateway = acquire_gateway_for_instance(instance_id, instance, strategy_dir)
    if gateway is None:
        return env
    with _redirect_gateway_native_stdio(strategy_dir):
        wait_gateway_runtime_ready(gateway)
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
        if state == "error" or (state and state not in {"created", "connecting"} and not runtime_running):
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
    key = launch["config"].runtime_name
    session_key = build_gateway_session_key_from_runtime_kwargs(launch["runtime_kwargs"])
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
