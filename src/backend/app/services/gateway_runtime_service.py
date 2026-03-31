import os
import threading
from pathlib import Path
from typing import Any


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
    state = gateways.get(key)
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
        }
        gateways[key] = state
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
    runtime = state.get("runtime")
    if runtime is not None:
        try:
            runtime.stop()
        except (RuntimeError, OSError):
            logger.debug("Gateway runtime stop error for %s (ignored)", key, exc_info=True)
    gateways.pop(key, None)
