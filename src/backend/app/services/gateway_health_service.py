import logging
import math
import time
from datetime import date, datetime
from typing import Any

logger = logging.getLogger(__name__)


def _resolve_ref_count(state: dict[str, Any]) -> int:
    instances = state.get("instances", set()) or set()
    ref_count = max(int(state.get("ref_count", 0) or 0), len(instances))
    if state.get("manual") and state.get("runtime") is not None and ref_count == 0:
        return 1
    return ref_count


def _coerce_string(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _coerce_int(value: Any, default: int = 0) -> int:
    if value in (None, "") or isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    return int(number)


def _coerce_optional_int(value: Any) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return int(number)


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _coerce_timestamp(value: Any) -> int | None:
    if isinstance(value, datetime):
        return int(value.timestamp())
    if isinstance(value, date):
        return int(datetime.combine(value, datetime.min.time()).timestamp())
    return _coerce_optional_int(value)


def _normalize_instances(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return sorted(str(item) for item in value if item is not None)
    if value in (None, ""):
        return []
    return [str(value)]


def _normalize_recent_errors(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    results: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            entry = {
                "source": _coerce_string(item.get("source"), ""),
                "message": _coerce_string(item.get("message"), ""),
            }
            timestamp = _coerce_timestamp(item.get("timestamp"))
            if timestamp is not None:
                entry["timestamp"] = timestamp
            results.append(entry)
            continue
        if item is not None:
            results.append({"source": "gateway", "message": _coerce_string(item)})
    return results


def _build_default_snapshot(
    key: str,
    state: dict[str, Any],
    *,
    gateway_state: str = "unknown",
    is_healthy: bool = False,
    market_connection: str = "unknown",
    trade_connection: str = "unknown",
) -> dict[str, Any]:
    return {
        "gateway_key": key,
        "state": gateway_state,
        "is_healthy": is_healthy,
        "exchange": _coerce_string(state.get("exchange_type"), ""),
        "asset_type": _coerce_string(state.get("asset_type"), ""),
        "account_id": _coerce_string(state.get("account_id"), ""),
        "market_connection": market_connection,
        "trade_connection": trade_connection,
        "uptime_sec": 0,
        "last_heartbeat": None,
        "heartbeat_age_sec": None,
        "last_tick_time": None,
        "last_order_time": None,
        "strategy_count": 0,
        "symbol_count": 0,
        "tick_count": 0,
        "order_count": 0,
        "ref_count": _resolve_ref_count(state),
        "instances": _normalize_instances(state.get("instances", set())),
        "recent_errors": [],
    }


def _build_error_snapshot(key: str, state: dict[str, Any], exc: Exception) -> dict[str, Any]:
    snap = _build_default_snapshot(
        key,
        state,
        gateway_state="error",
        is_healthy=False,
        market_connection="error",
        trade_connection="error",
    )
    message = str(exc).strip()
    snap["recent_errors"] = [
        {
            "source": "health_snapshot",
            "message": (
                f"{type(exc).__name__}: {message}" if message else type(exc).__name__
            ),
        }
    ]
    return snap


def _normalize_runtime_snapshot(
    key: str,
    state: dict[str, Any],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    snap = _build_default_snapshot(key, state)
    snap["state"] = _coerce_string(snapshot.get("state"), snap["state"])
    snap["exchange"] = _coerce_string(snapshot.get("exchange"), snap["exchange"])
    snap["asset_type"] = _coerce_string(snapshot.get("asset_type"), snap["asset_type"])
    snap["account_id"] = _coerce_string(snapshot.get("account_id"), snap["account_id"])
    snap["market_connection"] = _coerce_string(
        snapshot.get("market_connection"), snap["market_connection"]
    )
    snap["trade_connection"] = _coerce_string(
        snapshot.get("trade_connection"), snap["trade_connection"]
    )
    if (
        snap["state"] == "running"
        and snap["market_connection"] == "connected"
        and snap["trade_connection"] in {"", "disconnected"}
    ):
        snap["trade_connection"] = "connected"
    snap["uptime_sec"] = _coerce_int(snapshot.get("uptime_sec"), 0)
    snap["last_heartbeat"] = _coerce_timestamp(snapshot.get("last_heartbeat"))
    snap["heartbeat_age_sec"] = _coerce_optional_int(snapshot.get("heartbeat_age_sec"))
    snap["last_tick_time"] = _coerce_timestamp(snapshot.get("last_tick_time"))
    snap["last_order_time"] = _coerce_timestamp(snapshot.get("last_order_time"))
    snap["strategy_count"] = _coerce_int(snapshot.get("strategy_count"), 0)
    snap["symbol_count"] = _coerce_int(snapshot.get("symbol_count"), 0)
    snap["tick_count"] = _coerce_int(snapshot.get("tick_count"), 0)
    snap["order_count"] = _coerce_int(snapshot.get("order_count"), 0)
    snap["ref_count"] = max(_resolve_ref_count(state), _coerce_int(snapshot.get("ref_count"), 0))
    snap["instances"] = _normalize_instances(snapshot.get("instances", state.get("instances", set())))
    snap["recent_errors"] = _normalize_recent_errors(snapshot.get("recent_errors"))
    if snapshot.get("strategy_name") not in (None, ""):
        snap["strategy_name"] = _coerce_string(snapshot.get("strategy_name"))
    is_healthy = snapshot.get("is_healthy")
    if is_healthy is None:
        snap["is_healthy"] = (
            snap["state"] == "running"
            and snap["market_connection"] == "connected"
            and snap["trade_connection"] == "connected"
        )
    else:
        snap["is_healthy"] = _coerce_bool(is_healthy)
    return snap


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


def _augment_snapshot_from_quote_cache(snap: dict[str, Any]) -> None:
    exchange = _coerce_string(snap.get("exchange"), "").upper()
    if exchange != "IB_WEB":
        return
    if _coerce_int(snap.get("tick_count"), 0) > 0:
        return
    try:
        from app.services.quote_service import QuoteService

        cached_metrics = QuoteService().get_cached_tick_metrics(exchange)
    except Exception:
        logger.debug("Failed to read cached quote metrics for %s", exchange, exc_info=True)
        return

    cached_tick_count = _coerce_int(cached_metrics.get("tick_count"), 0)
    if cached_tick_count <= 0:
        return
    snap["tick_count"] = cached_tick_count
    snap["symbol_count"] = max(_coerce_int(snap.get("symbol_count"), 0), cached_tick_count)
    if snap.get("last_tick_time") is None:
        snap["last_tick_time"] = _coerce_timestamp(cached_metrics.get("last_tick_time"))


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
        if not isinstance(state, dict):
            logger.warning(
                "Skipping malformed gateway state for %s: expected dict, got %s",
                key,
                type(state).__name__,
            )
            continue
        runtime = state.get("runtime")
        if runtime is None:
            if state.get("manual"):
                results.append(
                    _build_default_snapshot(
                        key,
                        state,
                        gateway_state="registered",
                        is_healthy=False,
                        market_connection="not_started",
                        trade_connection="not_started",
                    )
                )
            continue
        try:
            health = getattr(runtime, "health", None)
            raw_snapshot = health.snapshot() if health is not None else {}
            if not isinstance(raw_snapshot, dict):
                raise TypeError(
                    f"health.snapshot() returned {type(raw_snapshot).__name__}, expected dict"
                )
            snap = _normalize_runtime_snapshot(key, state, raw_snapshot)
        except Exception as exc:
            logger.warning("Failed to build gateway health snapshot for %s: %s", key, exc)
            snap = _build_error_snapshot(key, state, exc)
        _augment_snapshot_from_quote_cache(snap)
        _populate_heartbeat_age(snap)
        results.append(snap)
        gateway_instance_ids.update(_normalize_instances(snap.get("instances")))

    try:
        instances = load_instances()
    except Exception as exc:
        logger.warning("Failed to load live trading instances for gateway health: %s", exc)
        return results
    if not isinstance(instances, dict):
        logger.warning(
            "Skipping direct gateway health reconciliation: expected dict instances payload, got %s",
            type(instances).__name__,
        )
        return results
    for instance_id, inst in instances.items():
        if not isinstance(inst, dict):
            logger.warning(
                "Skipping malformed live trading instance %s: expected dict, got %s",
                instance_id,
                type(inst).__name__,
            )
            continue
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
