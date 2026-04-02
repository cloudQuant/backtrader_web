from typing import Any
import time


def _resolve_ref_count(state: dict[str, Any]) -> int:
    instances = state.get("instances", set()) or set()
    ref_count = max(int(state.get("ref_count", 0) or 0), len(instances))
    if state.get("manual") and state.get("runtime") is not None and ref_count == 0:
        return 1
    return ref_count


def _populate_heartbeat_age(snap: dict[str, Any]) -> None:
    if snap.get("heartbeat_age_sec") is not None:
        return
    last_heartbeat = snap.get("last_heartbeat")
    if last_heartbeat is None:
        return
    try:
        snap["heartbeat_age_sec"] = max(0, int(time.time() - float(last_heartbeat)))
    except (TypeError, ValueError, OSError):
        return


def get_gateway_health(
    gateways: dict[str, dict[str, Any]],
    load_instances,
    is_pid_alive,
    resolve_strategy_dir,
    load_strategy_config,
    load_strategy_env,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    gateway_instance_ids: set[str] = set()

    for key, state in gateways.items():
        runtime = state.get("runtime")
        if runtime is None:
            if state.get("manual"):
                results.append(
                    {
                        "gateway_key": key,
                        "state": "registered",
                        "is_healthy": False,
                        "exchange": state.get("exchange_type", ""),
                        "asset_type": state.get("asset_type", ""),
                        "account_id": state.get("account_id", ""),
                        "market_connection": "not_started",
                        "trade_connection": "not_started",
                        "uptime_sec": 0,
                        "strategy_count": 0,
                        "symbol_count": 0,
                        "tick_count": 0,
                        "order_count": 0,
                        "heartbeat_age_sec": None,
                        "ref_count": _resolve_ref_count(state),
                        "instances": sorted(state.get("instances", set())),
                        "recent_errors": [],
                    }
                )
            continue
        health = getattr(runtime, "health", None)
        snap: dict[str, Any] = health.snapshot() if health is not None else {}
        _populate_heartbeat_age(snap)
        if (
            snap.get("state") == "running"
            and snap.get("market_connection") == "connected"
            and snap.get("trade_connection") in {None, "", "disconnected"}
        ):
            snap["trade_connection"] = "connected"
        snap["gateway_key"] = key
        snap["ref_count"] = _resolve_ref_count(state)
        snap["instances"] = sorted(state.get("instances", set()))
        results.append(snap)
        gateway_instance_ids.update(state.get("instances", set()))

    instances = load_instances()
    for instance_id, inst in instances.items():
        if instance_id in gateway_instance_ids:
            continue
        if inst.get("status") != "running":
            continue
        pid = inst.get("pid")
        if not pid or not is_pid_alive(pid):
            continue
        strategy_id = inst.get("strategy_id", "")
        exchange = "CTP"
        asset_type = "FUTURE"
        account_id = ""
        try:
            strategy_dir = resolve_strategy_dir(strategy_id)
            config_data = load_strategy_config(strategy_dir)
            env_data = load_strategy_env(strategy_dir)
            ctp = config_data.get("ctp", {}) or {}
            account_id = (
                env_data.get("CTP_INVESTOR_ID")
                or env_data.get("CTP_USER_ID")
                or ctp.get("investor_id", "")
            )
        except Exception as e:
            # Strategy config load failed; use empty account_id
            import logging
            logging.getLogger(__name__).debug(
                "Failed to load strategy config for %s: %s", strategy_id, e
            )
        name = inst.get("strategy_name") or strategy_id
        results.append(
            {
                "gateway_key": f"direct:{strategy_id}",
                "state": "running",
                "is_healthy": True,
                "exchange": exchange,
                "asset_type": asset_type,
                "account_id": account_id,
                "market_connection": "connected",
                "trade_connection": "connected",
                "uptime_sec": 0,
                "strategy_count": 1,
                "symbol_count": 0,
                "tick_count": 0,
                "order_count": 0,
                "heartbeat_age_sec": None,
                "ref_count": 1,
                "instances": [instance_id],
                "recent_errors": [],
                "strategy_name": name,
            }
        )
    return results
