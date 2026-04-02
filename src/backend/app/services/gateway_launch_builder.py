import json
from typing import Any
from urllib.parse import urlparse


def _is_local_ib_base_url(base_url: str) -> bool:
    parsed = urlparse(base_url or "https://localhost:5000")
    host = (parsed.hostname or "localhost").lower()
    return host in {"localhost", "127.0.0.1"}


def normalize_gateway_exchange_type(value: Any, provider: str = "") -> str:
    text = str(value or "").strip().upper()
    provider_text = str(provider or "").strip().lower()
    if text in {"IB", "IB_WEB", "IBWEB"} or provider_text.startswith("ib_web"):
        return "IB_WEB"
    if text == "MT5" or provider_text.startswith("mt5"):
        return "MT5"
    if text in {"CTP", ""}:
        return "CTP"
    return text


def normalize_gateway_asset_type(exchange_type: str, value: Any) -> str:
    text = str(value or "").strip().upper()
    if exchange_type == "IB_WEB":
        if text in {"", "STOCK", "STK", "EQUITY"}:
            return "STK"
        if text in {"FUT", "FUTURE"}:
            return "FUT"
    if exchange_type == "CTP":
        if text in {"", "FUT", "FUTURE"}:
            return "FUTURE"
    if exchange_type == "MT5":
        return text or "OTC"
    return text or "FUTURE"


def coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off", ""}


def coerce_float(value: Any, default: float = 0.0) -> float:
    if value in {None, ""}:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_json_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not value:
        return None
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def get_gateway_params(instance: dict[str, Any], default_transport: str) -> dict[str, Any]:
    params = instance.get("params") or {}
    if not isinstance(params, dict):
        return {"enabled": False}
    gateway = params.get("gateway") or {}
    if not isinstance(gateway, dict):
        gateway = {}
    provider = str(gateway.get("provider") or params.get("provider") or "").strip().lower()
    exchange_type = normalize_gateway_exchange_type(
        gateway.get("exchange_type")
        or gateway.get("exchange")
        or params.get("exchange_type")
        or params.get("exchange"),
        provider,
    )
    enabled = (
        bool(gateway.get("enabled"))
        or provider in {"ctp_gateway", "gateway"}
        or provider.endswith("_gateway")
    )
    return {
        "enabled": enabled,
        "provider": provider or "ctp",
        "exchange_type": exchange_type,
        "transport": str(gateway.get("transport") or default_transport),
        "asset_type": normalize_gateway_asset_type(
            exchange_type, gateway.get("asset_type") or params.get("asset_type")
        ),
        "account_id": str(gateway.get("account_id") or ""),
        "base_dir": str(gateway.get("base_dir") or ""),
        "base_url": str(gateway.get("base_url") or ""),
        "access_token": str(gateway.get("access_token") or ""),
        "verify_ssl": gateway.get("verify_ssl"),
        "cookie_source": str(gateway.get("cookie_source") or ""),
        "cookie_browser": str(gateway.get("cookie_browser") or ""),
        "cookie_path": str(gateway.get("cookie_path") or ""),
        "cookies": gateway.get("cookies"),
    }


def build_ctp_gateway_runtime_kwargs(
    config_data: dict[str, Any],
    env_data: dict[str, str],
    gateway_params: dict[str, Any],
    default_transport: str,
) -> dict[str, Any]:
    ctp = dict(config_data.get("ctp", {}) or {})
    live = dict(config_data.get("live", {}) or {})
    fronts = dict(ctp.get("fronts", {}) or {})
    network = str(live.get("network") or "simnow")
    front = dict(
        fronts.get(network) or fronts.get("telecom") or fronts.get("simnow") or {}
    )
    investor_id = (
        env_data.get("CTP_INVESTOR_ID")
        or env_data.get("CTP_USER_ID")
        or ctp.get("investor_id", "")
        or ctp.get("user_id", "")
    )
    broker_id = env_data.get("CTP_BROKER_ID") or ctp.get("broker_id", "")
    password = env_data.get("CTP_PASSWORD") or ctp.get("password", "")
    app_id = env_data.get("CTP_APP_ID") or ctp.get("app_id", "simnow_client_test")
    auth_code = env_data.get("CTP_AUTH_CODE") or ctp.get("auth_code", "0000000000000000")
    td_address = front.get("td_address", "")
    md_address = front.get("md_address", "")
    account_id = gateway_params.get("account_id") or investor_id
    if not all([account_id, investor_id, broker_id, password, td_address, md_address]):
        raise ValueError("CTP gateway requires complete CTP credentials and front addresses")
    return {
        "exchange_type": "CTP",
        "asset_type": normalize_gateway_asset_type("CTP", gateway_params.get("asset_type")),
        "account_id": account_id,
        "transport": gateway_params.get("transport") or default_transport,
        "gateway_base_dir": gateway_params.get("base_dir") or "",
        "md_address": md_address,
        "td_address": td_address,
        "broker_id": broker_id,
        "investor_id": investor_id,
        "user_id": investor_id,
        "password": password,
        "app_id": app_id,
        "auth_code": auth_code,
    }


def build_ib_web_gateway_runtime_kwargs(
    config_data: dict[str, Any],
    env_data: dict[str, str],
    gateway_params: dict[str, Any],
    default_transport: str,
) -> dict[str, Any]:
    ib_web = dict(config_data.get("ib_web", {}) or {})
    account_id = (
        gateway_params.get("account_id")
        or env_data.get("IB_WEB_ACCOUNT_ID")
        or ib_web.get("account_id", "")
    )
    if not account_id:
        raise ValueError("IB_WEB gateway requires account_id")
    base_url = (
        gateway_params.get("base_url")
        or env_data.get("IB_WEB_BASE_URL")
        or ib_web.get("base_url")
        or "https://localhost:5000"
    )
    access_token = (
        gateway_params.get("access_token")
        or env_data.get("IB_WEB_ACCESS_TOKEN")
        or ib_web.get("access_token", "")
    )
    verify_ssl_value = gateway_params.get("verify_ssl")
    if verify_ssl_value is None:
        verify_ssl_value = env_data.get("IB_WEB_VERIFY_SSL", ib_web.get("verify_ssl"))
    verify_ssl = coerce_bool(verify_ssl_value, default=False)
    timeout = coerce_float(
        env_data.get("IB_WEB_TIMEOUT", ib_web.get("timeout")),
        default=10.0,
    )
    cookie_source = (
        gateway_params.get("cookie_source")
        or env_data.get("IB_WEB_COOKIE_SOURCE")
        or ib_web.get("cookie_source", "")
    )
    cookie_browser = (
        gateway_params.get("cookie_browser")
        or env_data.get("IB_WEB_COOKIE_BROWSER")
        or ib_web.get("cookie_browser")
        or "chrome"
    )
    cookie_path = (
        gateway_params.get("cookie_path")
        or env_data.get("IB_WEB_COOKIE_PATH")
        or ib_web.get("cookie_path")
        or "/sso"
    )
    cookies = gateway_params.get("cookies") or parse_json_dict(
        env_data.get("IB_WEB_COOKIES_JSON")
    )
    if cookies is None and isinstance(ib_web.get("cookies"), dict):
        cookies = ib_web.get("cookies")
    runtime_kwargs = {
        "exchange_type": "IB_WEB",
        "asset_type": normalize_gateway_asset_type(
            "IB_WEB", gateway_params.get("asset_type") or ib_web.get("asset_type")
        ),
        "account_id": account_id,
        "transport": gateway_params.get("transport") or default_transport,
        "gateway_base_dir": gateway_params.get("base_dir") or "",
        "base_url": base_url,
        "verify_ssl": verify_ssl,
        "timeout": timeout,
    }
    if access_token:
        runtime_kwargs["access_token"] = access_token
    if cookie_source:
        runtime_kwargs["cookie_source"] = cookie_source
    if cookie_browser:
        runtime_kwargs["cookie_browser"] = cookie_browser
    if cookie_path:
        runtime_kwargs["cookie_path"] = cookie_path
    if cookies:
        runtime_kwargs["cookies"] = cookies
    if _is_local_ib_base_url(base_url):
        runtime_kwargs["proxies"] = {}
        runtime_kwargs["async_proxy"] = ""
    return runtime_kwargs


def build_mt5_gateway_runtime_kwargs(
    config_data: dict[str, Any],
    env_data: dict[str, str],
    gateway_params: dict[str, Any],
) -> dict[str, Any]:
    mt5 = dict(config_data.get("mt5", {}) or {})
    login = gateway_params.get("login") or env_data.get("MT5_LOGIN") or mt5.get("login", "")
    password = (
        gateway_params.get("password") or env_data.get("MT5_PASSWORD") or mt5.get("password", "")
    )
    account_id = (
        gateway_params.get("account_id")
        or env_data.get("MT5_ACCOUNT_ID")
        or mt5.get("account_id")
        or str(login)
    )
    ws_uri = (
        gateway_params.get("ws_uri") or env_data.get("MT5_WS_URI") or mt5.get("ws_uri", "")
    )
    symbol_suffix = (
        gateway_params.get("symbol_suffix")
        or env_data.get("MT5_SYMBOL_SUFFIX")
        or mt5.get("symbol_suffix", "")
    )
    if not login or not password:
        raise ValueError("MT5 gateway requires login and password")
    runtime_kwargs: dict[str, Any] = {
        "exchange_type": "MT5",
        "asset_type": normalize_gateway_asset_type(
            "MT5", gateway_params.get("asset_type") or mt5.get("asset_type")
        ),
        "account_id": account_id,
        "transport": gateway_params.get("transport") or "tcp",
        "login": int(login),
        "password": str(password),
        "ws_uri": ws_uri,
        "symbol_suffix": symbol_suffix,
        "auto_reconnect": True,
        "gateway_startup_timeout_sec": 60.0,
        "gateway_command_timeout_sec": 30.0,
    }
    symbol_map = mt5.get("symbol_map")
    if isinstance(symbol_map, dict) and symbol_map:
        runtime_kwargs["symbol_map"] = symbol_map
    return runtime_kwargs


def build_gateway_launch(
    config_data: dict[str, Any],
    env_data: dict[str, str],
    gateway_params: dict[str, Any],
    gateway_config_cls: type,
    gateway_runtime_cls: type,
    default_transport: str,
) -> dict[str, Any]:
    strategy_gateway = dict(config_data.get("gateway", {}) or {})
    exchange_type = normalize_gateway_exchange_type(
        gateway_params.get("exchange_type")
        or strategy_gateway.get("exchange_type")
        or strategy_gateway.get("exchange"),
        str(gateway_params.get("provider") or ""),
    )
    if exchange_type == "IB_WEB":
        runtime_kwargs = build_ib_web_gateway_runtime_kwargs(
            config_data=config_data,
            env_data=env_data,
            gateway_params=gateway_params,
            default_transport=default_transport,
        )
    elif exchange_type == "MT5":
        runtime_kwargs = build_mt5_gateway_runtime_kwargs(
            config_data=config_data,
            env_data=env_data,
            gateway_params=gateway_params,
        )
    else:
        runtime_kwargs = build_ctp_gateway_runtime_kwargs(
            config_data=config_data,
            env_data=env_data,
            gateway_params=gateway_params,
            default_transport=default_transport,
        )
    return {
        "config": gateway_config_cls.from_kwargs(**runtime_kwargs),
        "runtime_cls": gateway_runtime_cls,
        "runtime_kwargs": runtime_kwargs,
    }
