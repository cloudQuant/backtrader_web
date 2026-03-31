import logging
import threading
from typing import Any

_logger = logging.getLogger(__name__)


def connect_gateway(
    gateways: dict[str, dict[str, Any]],
    exchange_type: str,
    credentials: dict[str, Any],
    normalize_exchange_type,
    coerce_bool,
    coerce_float,
    import_gateway_runtime_classes,
    default_transport: str,
    logger,
) -> dict[str, Any]:
    exchange_type = normalize_exchange_type(exchange_type)
    account_id = credentials.get("account_id") or credentials.get("user_id") or ""
    key = f"manual:{exchange_type}:{account_id}"
    if key in gateways:
        return {"gateway_key": key, "status": "connected", "message": "Gateway already active"}
    if exchange_type == "CTP":
        return connect_ctp_gateway(
            gateways,
            key,
            credentials,
            import_gateway_runtime_classes,
            default_transport,
            logger,
        )
    if exchange_type == "IB_WEB":
        return connect_ib_web_gateway(
            gateways,
            key,
            credentials,
            coerce_bool,
            coerce_float,
            import_gateway_runtime_classes,
            default_transport,
            logger,
        )
    if exchange_type == "MT5":
        return connect_mt5_gateway(
            gateways,
            key,
            credentials,
            import_gateway_runtime_classes,
            logger,
        )
    gateways[key] = {
        "config": None,
        "runtime": None,
        "instances": set(),
        "ref_count": 0,
        "lock": threading.Lock(),
        "manual": True,
        "exchange_type": exchange_type,
        "account_id": account_id,
    }
    return {
        "gateway_key": key,
        "status": "connected",
        "message": f"{exchange_type} gateway registered (no runtime)",
    }


def connect_ctp_gateway(
    gateways: dict[str, dict[str, Any]],
    key: str,
    credentials: dict[str, Any],
    import_gateway_runtime_classes,
    default_transport: str,
    logger,
) -> dict[str, Any]:
    required = ["broker_id", "user_id", "password", "td_front", "md_front"]
    missing = [field for field in required if not credentials.get(field)]
    if missing:
        return {
            "gateway_key": key,
            "status": "error",
            "message": f"Missing required fields: {', '.join(missing)}",
        }
    try:
        gateway_config_cls, gateway_runtime_cls = import_gateway_runtime_classes()
        kwargs = {
            "exchange_type": "CTP",
            "asset_type": "FUTURE",
            "account_id": credentials.get("account_id") or credentials["user_id"],
            "transport": default_transport,
            "md_address": credentials["md_front"],
            "td_address": credentials["td_front"],
            "broker_id": credentials["broker_id"],
            "investor_id": credentials["user_id"],
            "user_id": credentials["user_id"],
            "password": credentials["password"],
            "app_id": credentials.get("app_id", "simnow_client_test"),
            "auth_code": credentials.get("auth_code", "0000000000000000"),
        }
        config = gateway_config_cls.from_kwargs(**kwargs)
        runtime = gateway_runtime_cls(config, **kwargs)
        runtime.start_in_thread()
        gateways[key] = {
            "config": config,
            "runtime": runtime,
            "instances": set(),
            "ref_count": 0,
            "lock": threading.Lock(),
            "manual": True,
            "exchange_type": "CTP",
            "account_id": kwargs["account_id"],
        }
        return {
            "gateway_key": key,
            "status": "connected",
            "message": "CTP gateway started successfully",
        }
    except Exception as exc:
        logger.exception("Failed to connect CTP gateway %s", key)
        return {
            "gateway_key": key,
            "status": "error",
            "message": f"CTP连接失败: {type(exc).__name__}: {exc}",
        }


def connect_ib_web_gateway(
    gateways: dict[str, dict[str, Any]],
    key: str,
    credentials: dict[str, Any],
    coerce_bool,
    coerce_float,
    import_gateway_runtime_classes,
    default_transport: str,
    logger,
) -> dict[str, Any]:
    account_id = credentials.get("account_id", "")
    if not account_id:
        return {
            "gateway_key": key,
            "status": "error",
            "message": "Missing required field: account_id",
        }
    try:
        gateway_config_cls, gateway_runtime_cls = import_gateway_runtime_classes()
        kwargs = {
            "exchange_type": "IB_WEB",
            "asset_type": credentials.get("asset_type", "STK"),
            "account_id": account_id,
            "transport": default_transport,
            "base_url": credentials.get("base_url", "https://localhost:5000"),
            "verify_ssl": coerce_bool(credentials.get("verify_ssl"), default=False),
            "timeout": coerce_float(credentials.get("timeout"), default=10.0),
        }
        if credentials.get("access_token"):
            kwargs["access_token"] = credentials["access_token"]
        config = gateway_config_cls.from_kwargs(**kwargs)
        runtime = gateway_runtime_cls(config, **kwargs)
        runtime.start_in_thread()
        gateways[key] = {
            "config": config,
            "runtime": runtime,
            "instances": set(),
            "ref_count": 0,
            "lock": threading.Lock(),
            "manual": True,
            "exchange_type": "IB_WEB",
            "account_id": account_id,
        }
        return {
            "gateway_key": key,
            "status": "connected",
            "message": "IB Web gateway started successfully",
        }
    except Exception as exc:
        logger.exception("Failed to connect IB Web gateway %s", key)
        return {
            "gateway_key": key,
            "status": "error",
            "message": f"IB Web连接失败: {type(exc).__name__}: {exc}",
        }


def connect_mt5_gateway(
    gateways: dict[str, dict[str, Any]],
    key: str,
    credentials: dict[str, Any],
    import_gateway_runtime_classes,
    logger,
) -> dict[str, Any]:
    login = credentials.get("login")
    password = credentials.get("password")
    if not login or not password:
        return {
            "gateway_key": key,
            "status": "error",
            "message": "Missing required fields: login, password",
        }
    try:
        gateway_config_cls, gateway_runtime_cls = import_gateway_runtime_classes()
        account_id = credentials.get("account_id") or str(login)
        kwargs = {
            "exchange_type": "MT5",
            "asset_type": "OTC",
            "account_id": account_id,
            "transport": "tcp",
            "login": int(login),
            "password": str(password),
            "ws_uri": credentials.get("ws_uri", ""),
            "symbol_suffix": credentials.get("symbol_suffix", ""),
            "auto_reconnect": True,
        }
        if credentials.get("symbol_map"):
            kwargs["symbol_map"] = credentials["symbol_map"]
        config = gateway_config_cls.from_kwargs(**kwargs)
        runtime = gateway_runtime_cls(config, **kwargs)
        runtime.start_in_thread()
        gateways[key] = {
            "config": config,
            "runtime": runtime,
            "instances": set(),
            "ref_count": 0,
            "lock": threading.Lock(),
            "manual": True,
            "exchange_type": "MT5",
            "account_id": account_id,
        }
        return {
            "gateway_key": key,
            "status": "connected",
            "message": "MT5 gateway started successfully",
        }
    except Exception as exc:
        logger.exception("Failed to connect MT5 gateway %s", key)
        return {
            "gateway_key": key,
            "status": "error",
            "message": f"MT5连接失败: {type(exc).__name__}: {exc}",
        }


def query_gateway_account(
    gateways: dict[str, dict[str, Any]], gateway_key: str
) -> dict[str, Any] | None:
    state = gateways.get(gateway_key)
    if state is None:
        return None
    runtime = state.get("runtime")
    if runtime is None:
        return None
    try:
        health = getattr(runtime, "health", None)
        if health is not None:
            snap = health.snapshot()
            return {
                "gateway_key": gateway_key,
                "exchange": state.get("exchange_type", snap.get("exchange", "")),
                "account_id": state.get("account_id", snap.get("account_id", "")),
                "state": snap.get("state", "unknown"),
                "market_connection": snap.get("market_connection", "unknown"),
                "trade_connection": snap.get("trade_connection", "unknown"),
            }
        return {"gateway_key": gateway_key, "state": "connected"}
    except (AttributeError, KeyError, RuntimeError):
        return {"gateway_key": gateway_key, "state": "error"}


def query_gateway_positions(
    gateways: dict[str, dict[str, Any]], gateway_key: str
) -> list[dict[str, Any]]:
    state = gateways.get(gateway_key)
    if state is None:
        return []
    runtime = state.get("runtime")
    if runtime is None:
        return []
    try:
        positions = getattr(runtime, "positions", None)
        if positions is not None and callable(positions):
            return list(positions())
        pos_dict = getattr(runtime, "_positions", None)
        if isinstance(pos_dict, dict):
            return list(pos_dict.values())
        return []
    except (AttributeError, KeyError, TypeError):
        return []


def list_connected_gateways(gateways: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for key, state in gateways.items():
        if not state.get("manual"):
            continue
        results.append(
            {
                "gateway_key": key,
                "exchange_type": state.get("exchange_type", ""),
                "account_id": state.get("account_id", ""),
                "has_runtime": state.get("runtime") is not None,
            }
        )
    return results


def disconnect_gateway(
    gateways: dict[str, dict[str, Any]], gateway_key: str
) -> dict[str, Any]:
    state = gateways.get(gateway_key)
    if state is None:
        return {
            "gateway_key": gateway_key,
            "status": "error",
            "message": "Gateway not found",
        }
    if not state.get("manual"):
        return {
            "gateway_key": gateway_key,
            "status": "error",
            "message": "Cannot disconnect a strategy-owned gateway",
        }
    runtime = state.get("runtime")
    if runtime is not None:
        try:
            runtime.stop()
        except Exception as e:
            _logger.warning(f"Error stopping gateway {gateway_key}: {e}")
    gateways.pop(gateway_key, None)
    return {
        "gateway_key": gateway_key,
        "status": "disconnected",
        "message": "Gateway disconnected",
    }
