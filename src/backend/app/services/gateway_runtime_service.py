import os
import threading
from pathlib import Path
from typing import Any

from app.services.gateway_launch_builder import build_gateway_session_key_from_runtime_kwargs


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


def build_subprocess_env(
    instance_id: str,
    instance: dict[str, Any],
    strategy_dir: Path,
    acquire_gateway_for_instance,
    os_environ: dict[str, str],
    bt_api_py_dir: Path,
) -> dict[str, str]:
    env = dict(os_environ)
    python_paths = [str(bt_api_py_dir)] if bt_api_py_dir.is_dir() else []
    if python_paths:
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join(python_paths + ([existing] if existing else []))
    gateway = acquire_gateway_for_instance(instance_id, instance, strategy_dir)
    if gateway is None:
        return env
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


def acquire_gateway_for_instance(
    instance_id: str,
    instance: dict[str, Any],
    strategy_dir: Path,
    get_gateway_params,
    build_gateway_launch,
    gateways: dict[str, dict[str, Any]],
    instance_gateways: dict[str, str],
    logger,
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
            runtime.start_in_thread()
        except (KeyError, TypeError, OSError, RuntimeError) as exc:
            logger.warning(
                "Gateway runtime failed to start for {}, falling back to direct mode: {}",
                instance_id,
                exc,
            )
            return None
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
    logger,
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
