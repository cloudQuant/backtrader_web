import json
from typing import Any
from urllib.parse import urlparse

_TCP_TRANSPORT_GATEWAY_TYPES = {"CTP", "IB_WEB"}


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
    if exchange_type in {"BINANCE", "OKX"}:
        if text in {"", "SWAP", "PERP", "PERPETUAL", "FUT", "FUTURE"}:
            return "SWAP"
        if text in {"SPOT", "CASH"}:
            return "SPOT"
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


def resolve_gateway_transport(
    exchange_type: str,
    requested_transport: Any,
    default_transport: str,
) -> str:
    transport = str(requested_transport or "").strip().lower()
    if transport:
        return transport
    if exchange_type in _TCP_TRANSPORT_GATEWAY_TYPES:
        return "tcp"
    return str(default_transport or "tcp").strip().lower() or "tcp"


def _normalize_session_value(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_session_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "https").lower()
    host = (parsed.hostname or "").lower()
    port = f":{parsed.port}" if parsed.port is not None else ""
    path = (parsed.path or "").rstrip("/")
    return f"{scheme}://{host}{port}{path}"


def build_gateway_session_key(
    exchange_type: Any,
    account_id: Any,
    *,
    asset_type: Any = "",
    broker_id: Any = "",
    td_address: Any = "",
    md_address: Any = "",
    base_url: Any = "",
    login_mode: Any = "",
    testnet: Any = None,
    server: Any = "",
    ws_uri: Any = "",
) -> str:
    normalized_exchange = normalize_gateway_exchange_type(exchange_type)
    normalized_account_id = _normalize_session_value(account_id)
    normalized_asset_type = normalize_gateway_asset_type(
        normalized_exchange,
        asset_type,
    )
    parts = [
        f"exchange={normalized_exchange.lower()}",
        f"asset={normalized_asset_type.lower()}",
        f"account={normalized_account_id}",
    ]
    if normalized_exchange == "CTP":
        parts.extend(
            [
                f"broker={_normalize_session_value(broker_id)}",
                f"td={_normalize_session_url(td_address)}",
                f"md={_normalize_session_url(md_address)}",
            ]
        )
    elif normalized_exchange == "IB_WEB":
        parts.extend(
            [
                f"mode={_normalize_session_value(login_mode or 'paper')}",
                f"base={_normalize_session_url(base_url)}",
            ]
        )
    elif normalized_exchange in {"BINANCE", "OKX"}:
        parts.extend(
            [
                f"env={'testnet' if coerce_bool(testnet) else 'live'}",
                f"base={_normalize_session_url(base_url)}",
            ]
        )
    elif normalized_exchange == "MT5":
        parts.extend(
            [
                f"server={_normalize_session_value(server)}",
                f"ws={_normalize_session_url(ws_uri)}",
            ]
        )
    return "|".join(parts)


def build_gateway_session_key_from_runtime_kwargs(runtime_kwargs: dict[str, Any]) -> str:
    exchange_type = runtime_kwargs.get("exchange_type", "")
    return build_gateway_session_key(
        exchange_type,
        runtime_kwargs.get("account_id", ""),
        asset_type=runtime_kwargs.get("asset_type", ""),
        broker_id=runtime_kwargs.get("broker_id", ""),
        td_address=runtime_kwargs.get("td_address", ""),
        md_address=runtime_kwargs.get("md_address", ""),
        base_url=runtime_kwargs.get("base_url", ""),
        login_mode=runtime_kwargs.get("login_mode", ""),
        testnet=runtime_kwargs.get("testnet"),
        server=runtime_kwargs.get("server", ""),
        ws_uri=runtime_kwargs.get("ws_uri", ""),
    )


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
        "transport": resolve_gateway_transport(
            exchange_type,
            gateway.get("transport"),
            default_transport,
        ),
        "asset_type": normalize_gateway_asset_type(
            exchange_type, gateway.get("asset_type") or params.get("asset_type")
        ),
        "account_id": str(gateway.get("account_id") or ""),
        "base_dir": str(gateway.get("base_dir") or ""),
        "base_url": str(gateway.get("base_url") or ""),
        "access_token": str(gateway.get("access_token") or ""),
        "verify_ssl": gateway.get("verify_ssl"),
        "broker_id": str(gateway.get("broker_id") or ""),
        "investor_id": str(gateway.get("investor_id") or ""),
        "user_id": str(gateway.get("user_id") or ""),
        "password": str(gateway.get("password") or ""),
        "app_id": str(gateway.get("app_id") or ""),
        "auth_code": str(gateway.get("auth_code") or ""),
        "td_front": str(gateway.get("td_front") or gateway.get("td_address") or ""),
        "md_front": str(gateway.get("md_front") or gateway.get("md_address") or ""),
        "cookie_source": str(gateway.get("cookie_source") or ""),
        "cookie_browser": str(gateway.get("cookie_browser") or ""),
        "cookie_path": str(gateway.get("cookie_path") or ""),
        "cookie_output": str(gateway.get("cookie_output") or ""),
        "cookies": gateway.get("cookies"),
        "username": str(gateway.get("username") or ""),
        "login_mode": str(gateway.get("login_mode") or ""),
        "login_browser": str(gateway.get("login_browser") or ""),
        "login_headless": gateway.get("login_headless"),
        "login_timeout": gateway.get("login_timeout"),
        "api_key": str(gateway.get("api_key") or ""),
        "secret_key": str(gateway.get("secret_key") or ""),
        "passphrase": str(gateway.get("passphrase") or ""),
        "testnet": gateway.get("testnet"),
        "startup_timeout_sec": gateway.get("startup_timeout_sec"),
        "command_timeout_sec": gateway.get("command_timeout_sec"),
        "login": gateway.get("login"),
        "server": str(gateway.get("server") or ""),
        "ws_uri": str(gateway.get("ws_uri") or ""),
        "symbol_suffix": str(gateway.get("symbol_suffix") or ""),
        "symbol_map": gateway.get("symbol_map"),
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
        gateway_params.get("investor_id")
        or gateway_params.get("user_id")
        or env_data.get("CTP_INVESTOR_ID")
        or env_data.get("CTP_USER_ID")
        or ctp.get("investor_id", "")
        or ctp.get("user_id", "")
    )
    broker_id = gateway_params.get("broker_id") or env_data.get("CTP_BROKER_ID") or ctp.get("broker_id", "")
    password = gateway_params.get("password") or env_data.get("CTP_PASSWORD") or ctp.get("password", "")
    app_id = gateway_params.get("app_id") or env_data.get("CTP_APP_ID") or ctp.get("app_id", "simnow_client_test")
    auth_code = gateway_params.get("auth_code") or env_data.get("CTP_AUTH_CODE") or ctp.get("auth_code", "0000000000000000")
    td_address = (
        gateway_params.get("td_front")
        or gateway_params.get("td_address")
        or env_data.get("CTP_TD_ADDRESS")
        or front.get("td_address", "")
    )
    md_address = (
        gateway_params.get("md_front")
        or gateway_params.get("md_address")
        or env_data.get("CTP_MD_ADDRESS")
        or front.get("md_address", "")
    )
    account_id = gateway_params.get("account_id") or investor_id
    if not all([account_id, investor_id, broker_id, password, td_address, md_address]):
        raise ValueError("CTP gateway requires complete CTP credentials and front addresses")
    return {
        "exchange_type": "CTP",
        "asset_type": normalize_gateway_asset_type("CTP", gateway_params.get("asset_type")),
        "account_id": account_id,
        "transport": resolve_gateway_transport(
            "CTP",
            gateway_params.get("transport"),
            default_transport,
        ),
        "gateway_base_dir": gateway_params.get("base_dir") or "",
        "md_address": md_address,
        "td_address": td_address,
        "broker_id": broker_id,
        "investor_id": investor_id,
        "user_id": investor_id,
        "password": password,
        "app_id": app_id,
        "auth_code": auth_code,
        "gateway_startup_timeout_sec": coerce_float(
            gateway_params.get("startup_timeout_sec")
            or env_data.get("CTP_STARTUP_TIMEOUT_SEC")
            or ctp.get("startup_timeout_sec"),
            default=60.0,
        ),
        "gateway_command_timeout_sec": coerce_float(
            gateway_params.get("command_timeout_sec")
            or env_data.get("CTP_COMMAND_TIMEOUT_SEC")
            or ctp.get("command_timeout_sec"),
            default=20.0,
        ),
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
    cookie_output = (
        gateway_params.get("cookie_output")
        or env_data.get("IB_WEB_COOKIE_OUTPUT")
        or ib_web.get("cookie_output", "")
    )
    if not cookie_source and cookie_output:
        cookie_source = f"file:{cookie_output}"
    username = (
        gateway_params.get("username")
        or env_data.get("IB_WEB_USERNAME")
        or ib_web.get("username", "")
    )
    password = (
        gateway_params.get("password")
        or env_data.get("IB_WEB_PASSWORD")
        or ib_web.get("password", "")
    )
    login_mode = (
        gateway_params.get("login_mode")
        or env_data.get("IB_WEB_LOGIN_MODE")
        or ib_web.get("login_mode", "")
    )
    login_browser = (
        gateway_params.get("login_browser")
        or env_data.get("IB_WEB_LOGIN_BROWSER")
        or ib_web.get("login_browser", "")
    )
    if not login_browser:
        login_browser = cookie_browser
    login_headless_value = gateway_params.get("login_headless")
    if login_headless_value is None:
        login_headless_value = env_data.get("IB_WEB_LOGIN_HEADLESS", ib_web.get("login_headless"))
    login_timeout = coerce_float(
        gateway_params.get("login_timeout")
        or env_data.get("IB_WEB_LOGIN_TIMEOUT")
        or ib_web.get("login_timeout"),
        default=180.0,
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
        "transport": resolve_gateway_transport(
            "IB_WEB",
            gateway_params.get("transport"),
            default_transport,
        ),
        "gateway_base_dir": gateway_params.get("base_dir") or "",
        "base_url": base_url,
        "verify_ssl": verify_ssl,
        "timeout": timeout,
        "cookie_base_dir": gateway_params.get("base_dir") or "",
        "gateway_startup_timeout_sec": coerce_float(
            gateway_params.get("startup_timeout_sec")
            or env_data.get("IB_WEB_STARTUP_TIMEOUT_SEC")
            or ib_web.get("startup_timeout_sec"),
            default=30.0,
        ),
        "gateway_command_timeout_sec": coerce_float(
            gateway_params.get("command_timeout_sec")
            or env_data.get("IB_WEB_COMMAND_TIMEOUT_SEC")
            or ib_web.get("command_timeout_sec"),
            default=10.0,
        ),
    }
    if access_token:
        runtime_kwargs["access_token"] = access_token
    if cookie_source:
        runtime_kwargs["cookie_source"] = cookie_source
    if cookie_browser:
        runtime_kwargs["cookie_browser"] = cookie_browser
    if cookie_path:
        runtime_kwargs["cookie_path"] = cookie_path
    if cookie_output:
        runtime_kwargs["cookie_output"] = cookie_output
    if cookies:
        runtime_kwargs["cookies"] = cookies
    if username:
        runtime_kwargs["username"] = username
    if password:
        runtime_kwargs["password"] = password
    if login_mode:
        runtime_kwargs["login_mode"] = login_mode
    if login_browser:
        runtime_kwargs["login_browser"] = login_browser
    if login_headless_value is not None:
        runtime_kwargs["login_headless"] = coerce_bool(login_headless_value, default=False)
    if login_timeout > 0:
        runtime_kwargs["login_timeout"] = int(login_timeout)
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


def build_binance_gateway_runtime_kwargs(
    config_data: dict[str, Any],
    env_data: dict[str, str],
    gateway_params: dict[str, Any],
    default_transport: str,
) -> dict[str, Any]:
    binance = dict(config_data.get("binance", {}) or {})
    api_key = (
        gateway_params.get("api_key")
        or env_data.get("BINANCE_API_KEY")
        or binance.get("api_key", "")
    )
    secret_key = (
        gateway_params.get("secret_key")
        or env_data.get("BINANCE_SECRET_KEY")
        or binance.get("secret_key", "")
    )
    if not api_key or not secret_key:
        raise ValueError("BINANCE gateway requires api_key and secret_key")
    account_id = (
        gateway_params.get("account_id")
        or env_data.get("BINANCE_ACCOUNT_ID")
        or binance.get("account_id")
        or f"binance-{str(api_key)[-6:]}"
    )
    runtime_kwargs: dict[str, Any] = {
        "exchange_type": "BINANCE",
        "asset_type": normalize_gateway_asset_type(
            "BINANCE",
            gateway_params.get("asset_type")
            or env_data.get("BINANCE_ASSET_TYPE")
            or binance.get("asset_type"),
        ),
        "account_id": account_id,
        "transport": resolve_gateway_transport(
            "BINANCE",
            gateway_params.get("transport"),
            default_transport,
        ),
        "api_key": api_key,
        "secret_key": secret_key,
        "testnet": coerce_bool(
            gateway_params.get("testnet")
            if gateway_params.get("testnet") is not None
            else env_data.get("BINANCE_TESTNET", binance.get("testnet")),
            default=False,
        ),
    }
    base_url = (
        gateway_params.get("base_url")
        or env_data.get("BINANCE_BASE_URL")
        or binance.get("base_url", "")
    )
    if base_url:
        runtime_kwargs["base_url"] = str(base_url)
    return runtime_kwargs


def build_okx_gateway_runtime_kwargs(
    config_data: dict[str, Any],
    env_data: dict[str, str],
    gateway_params: dict[str, Any],
    default_transport: str,
) -> dict[str, Any]:
    okx = dict(config_data.get("okx", {}) or {})
    api_key = (
        gateway_params.get("api_key")
        or env_data.get("OKX_API_KEY")
        or okx.get("api_key", "")
    )
    secret_key = (
        gateway_params.get("secret_key")
        or env_data.get("OKX_SECRET_KEY")
        or okx.get("secret_key", "")
    )
    passphrase = (
        gateway_params.get("passphrase")
        or env_data.get("OKX_PASSPHRASE")
        or okx.get("passphrase", "")
    )
    if not api_key or not secret_key or not passphrase:
        raise ValueError("OKX gateway requires api_key, secret_key and passphrase")
    account_id = (
        gateway_params.get("account_id")
        or env_data.get("OKX_ACCOUNT_ID")
        or okx.get("account_id")
        or f"okx-{str(api_key)[-6:]}"
    )
    runtime_kwargs: dict[str, Any] = {
        "exchange_type": "OKX",
        "asset_type": normalize_gateway_asset_type(
            "OKX",
            gateway_params.get("asset_type")
            or env_data.get("OKX_ASSET_TYPE")
            or okx.get("asset_type"),
        ),
        "account_id": account_id,
        "transport": resolve_gateway_transport(
            "OKX",
            gateway_params.get("transport"),
            default_transport,
        ),
        "api_key": api_key,
        "secret_key": secret_key,
        "passphrase": passphrase,
        "testnet": coerce_bool(
            gateway_params.get("testnet")
            if gateway_params.get("testnet") is not None
            else env_data.get("OKX_TESTNET", okx.get("testnet")),
            default=False,
        ),
    }
    base_url = (
        gateway_params.get("base_url")
        or env_data.get("OKX_BASE_URL")
        or okx.get("base_url", "")
    )
    if base_url:
        runtime_kwargs["base_url"] = str(base_url)
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
    elif exchange_type == "BINANCE":
        runtime_kwargs = build_binance_gateway_runtime_kwargs(
            config_data=config_data,
            env_data=env_data,
            gateway_params=gateway_params,
            default_transport=default_transport,
        )
    elif exchange_type == "OKX":
        runtime_kwargs = build_okx_gateway_runtime_kwargs(
            config_data=config_data,
            env_data=env_data,
            gateway_params=gateway_params,
            default_transport=default_transport,
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
