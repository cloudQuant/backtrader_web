from typing import Any


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
            continue
        health = getattr(runtime, "health", None)
        snap: dict[str, Any] = health.snapshot() if health is not None else {}
        snap["gateway_key"] = key
        snap["ref_count"] = state.get("ref_count", 0)
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
