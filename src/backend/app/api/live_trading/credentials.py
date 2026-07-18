"""Build the gateway-credentials response payload for the connect form.

The endpoint surfaces this data so the frontend can pre-fill the
gateway-connection form from values defined in ``.env`` /
``backend_gateway_env``. Iteration 174 (C6) extracted this 290-line
dict-building helper out of ``app.api.live_trading.api`` to keep the
router file focused on routing.
"""

from __future__ import annotations

from typing import Any

from app.services.gateway import manual as manual_gateway_service

_SENSITIVE_CREDENTIAL_FIELDS = frozenset(
    {
        "access_token",
        "api_key",
        "auth_code",
        "cookie_output",
        "cookie_source",
        "passphrase",
        "password",
        "secret_key",
    }
)


def _first_non_empty(*values: Any) -> Any:
    for v in values:
        if v not in (None, "", 0):
            return v
    return values[-1] if values else None


def _env_or_default(value: Any, *fallbacks: Any) -> Any:
    if value not in (None, ""):
        return value
    for fallback in fallbacks:
        if fallback not in (None, ""):
            return fallback
    return ""


def _is_configured(value: Any) -> bool:
    """Return whether a credential value exists without exposing it."""
    return value not in (None, "")


def redact_gateway_credentials(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove credential material from a gateway-form payload.

    The browser only needs public connection defaults.  It must never receive
    a password, broker token, API secret, or cookie location merely to decide
    whether the operator needs to fill a field.  Preserve the existing shape
    for form compatibility and add a boolean status for UI hints.
    """
    result: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, dict):
            result[key] = redact_gateway_credentials(value)
        elif key in _SENSITIVE_CREDENTIAL_FIELDS:
            result[key] = ""
            result[f"{key}_configured"] = _is_configured(value)
        else:
            result[key] = value
    return result


def build_gateway_credentials_payload(env_values: dict[str, str] | None = None) -> dict[str, Any]:
    """Construct a redacted gateway-form payload from configured settings."""
    from app.config import get_settings

    s = get_settings()
    if env_values is None:
        env_values = manual_gateway_service._load_backend_gateway_env_values()
    ib_web_login_mode = str(s.IB_WEB_LOGIN_MODE or "").strip().lower()
    ib_web_default_is_paper = ib_web_login_mode == "paper"
    ib_web_default_is_live = ib_web_login_mode == "live"
    payload = {
        "CTP": {
            "broker_id": s.CTP_BROKER_ID,
            "user_id": s.CTP_USER_ID or s.CTP_INVESTOR_ID,
            "password": s.CTP_PASSWORD,
            "app_id": s.CTP_APP_ID,
            "auth_code": s.CTP_AUTH_CODE,
        },
        "MT5": {
            "login": _env_or_default(
                s.MT5_LOGIN,
                env_values.get("MT5_LOGIN", ""),
                env_values.get("MT5_ACCOUNT", ""),
            ),
            "password": _env_or_default(
                s.MT5_PASSWORD,
                env_values.get("MT5_PASSWORD", ""),
                env_values.get("MT5_PASS", ""),
            ),
            "server": _env_or_default(
                s.MT5_SERVER,
                env_values.get("MT5_SERVER", ""),
            ),
            "ws_uri": _env_or_default(
                s.MT5_WS_URI,
                env_values.get("MT5_WS_URI", ""),
            ),
            "symbol_suffix": _env_or_default(
                s.MT5_SYMBOL_SUFFIX,
                env_values.get("MT5_SYMBOL_SUFFIX", ""),
            ),
            "timeout": s.MT5_TIMEOUT,
            "demo": {
                "login": _env_or_default(
                    s.MT5_DEMO_LOGIN,
                    env_values.get("MT5_DEMO_LOGIN", ""),
                    s.MT5_LOGIN,
                    env_values.get("MT5_LOGIN", ""),
                ),
                "password": _env_or_default(
                    s.MT5_DEMO_PASSWORD,
                    env_values.get("MT5_DEMO_PASSWORD", ""),
                    s.MT5_PASSWORD,
                    env_values.get("MT5_PASSWORD", ""),
                ),
                "server": _env_or_default(
                    s.MT5_DEMO_SERVER,
                    env_values.get("MT5_DEMO_SERVER", ""),
                    s.MT5_SERVER,
                    env_values.get("MT5_SERVER", ""),
                ),
                "ws_uri": _env_or_default(
                    s.MT5_DEMO_WS_URI,
                    env_values.get("MT5_DEMO_WS_URI", ""),
                    s.MT5_WS_URI,
                    env_values.get("MT5_WS_URI", ""),
                ),
                "symbol_suffix": _env_or_default(
                    s.MT5_SYMBOL_SUFFIX,
                    env_values.get("MT5_SYMBOL_SUFFIX", ""),
                ),
                "timeout": s.MT5_TIMEOUT,
            },
            "live": {
                "login": _env_or_default(
                    s.MT5_LIVE_LOGIN,
                    env_values.get("MT5_LIVE_LOGIN", ""),
                    s.MT5_LOGIN,
                    env_values.get("MT5_LOGIN", ""),
                ),
                "password": _env_or_default(
                    s.MT5_LIVE_PASSWORD,
                    env_values.get("MT5_LIVE_PASSWORD", ""),
                    s.MT5_PASSWORD,
                    env_values.get("MT5_PASSWORD", ""),
                ),
                "server": _env_or_default(
                    s.MT5_LIVE_SERVER,
                    env_values.get("MT5_LIVE_SERVER", ""),
                    s.MT5_SERVER,
                    env_values.get("MT5_SERVER", ""),
                ),
                "ws_uri": _env_or_default(
                    s.MT5_LIVE_WS_URI,
                    env_values.get("MT5_LIVE_WS_URI", ""),
                    s.MT5_WS_URI,
                    env_values.get("MT5_WS_URI", ""),
                ),
                "symbol_suffix": _env_or_default(
                    s.MT5_SYMBOL_SUFFIX,
                    env_values.get("MT5_SYMBOL_SUFFIX", ""),
                ),
                "timeout": s.MT5_TIMEOUT,
            },
        },
        "IB_WEB": {
            "account_id": _first_non_empty(s.IB_WEB_ACCOUNT_ID, s.IB_ACCOUNT_ID),
            "asset_type": _first_non_empty(s.IB_WEB_ASSET_TYPE, s.IB_ASSET_TYPE, "STK"),
            "base_url": _first_non_empty(s.IB_WEB_BASE_URL, s.IB_BASE_URL),
            "access_token": _first_non_empty(s.IB_WEB_ACCESS_TOKEN, s.IB_ACCESS_TOKEN),
            "verify_ssl": s.IB_WEB_VERIFY_SSL
            if s.IB_WEB_BASE_URL
            or s.IB_WEB_ACCOUNT_ID
            or s.IB_WEB_COOKIE_SOURCE
            or s.IB_WEB_USERNAME
            else s.IB_VERIFY_SSL,
            "timeout": _first_non_empty(s.IB_WEB_TIMEOUT, s.IB_TIMEOUT, 10),
            "cookie_source": _first_non_empty(s.IB_WEB_COOKIE_SOURCE, s.IB_COOKIE_SOURCE),
            "cookie_browser": _first_non_empty(
                s.IB_WEB_COOKIE_BROWSER, s.IB_COOKIE_BROWSER, "chrome"
            ),
            "cookie_path": _first_non_empty(s.IB_WEB_COOKIE_PATH, s.IB_COOKIE_PATH, "/sso"),
            "username": _first_non_empty(s.IB_WEB_USERNAME, s.IB_USERNAME),
            "password": _first_non_empty(s.IB_WEB_PASSWORD, s.IB_PASSWORD),
            "login_mode": _first_non_empty(s.IB_WEB_LOGIN_MODE, "paper"),
            "login_browser": _first_non_empty(s.IB_WEB_LOGIN_BROWSER, s.IB_LOGIN_BROWSER, "chrome"),
            "login_headless": s.IB_WEB_LOGIN_HEADLESS
            if s.IB_WEB_LOGIN_BROWSER or s.IB_WEB_USERNAME
            else s.IB_LOGIN_HEADLESS,
            "login_timeout": _first_non_empty(s.IB_WEB_LOGIN_TIMEOUT, s.IB_LOGIN_TIMEOUT, 180),
            "cookie_output": _first_non_empty(s.IB_WEB_COOKIE_OUTPUT, s.IB_COOKIE_OUTPUT),
            "paper": {
                "account_id": _first_non_empty(
                    s.IB_PAPER_ACCOUNT_ID,
                    s.IB_WEB_ACCOUNT_ID if ib_web_default_is_paper else "",
                    s.IB_ACCOUNT_ID,
                ),
                "asset_type": _first_non_empty(
                    s.IB_PAPER_ASSET_TYPE,
                    s.IB_WEB_ASSET_TYPE if ib_web_default_is_paper else "",
                    s.IB_ASSET_TYPE,
                    "STK",
                ),
                "base_url": _first_non_empty(
                    s.IB_PAPER_BASE_URL,
                    s.IB_WEB_BASE_URL if ib_web_default_is_paper else "",
                    s.IB_BASE_URL,
                ),
                "access_token": _first_non_empty(
                    s.IB_PAPER_ACCESS_TOKEN,
                    s.IB_WEB_ACCESS_TOKEN if ib_web_default_is_paper else "",
                    s.IB_ACCESS_TOKEN,
                ),
                "verify_ssl": s.IB_PAPER_VERIFY_SSL
                if s.IB_PAPER_BASE_URL or s.IB_PAPER_ACCOUNT_ID or s.IB_PAPER_ACCESS_TOKEN
                else s.IB_VERIFY_SSL,
                "timeout": _first_non_empty(
                    s.IB_PAPER_TIMEOUT,
                    s.IB_WEB_TIMEOUT if ib_web_default_is_paper else 0,
                    s.IB_TIMEOUT,
                    10,
                ),
                "cookie_source": _first_non_empty(
                    s.IB_PAPER_COOKIE_SOURCE,
                    s.IB_WEB_COOKIE_SOURCE if ib_web_default_is_paper else "",
                    s.IB_COOKIE_SOURCE,
                ),
                "cookie_browser": _first_non_empty(
                    s.IB_PAPER_COOKIE_BROWSER,
                    s.IB_WEB_COOKIE_BROWSER if ib_web_default_is_paper else "",
                    s.IB_COOKIE_BROWSER,
                    "chrome",
                ),
                "cookie_path": _first_non_empty(
                    s.IB_PAPER_COOKIE_PATH,
                    s.IB_WEB_COOKIE_PATH if ib_web_default_is_paper else "",
                    s.IB_COOKIE_PATH,
                    "/sso",
                ),
                "username": _first_non_empty(s.IB_WEB_USERNAME, s.IB_USERNAME),
                "password": _first_non_empty(s.IB_WEB_PASSWORD, s.IB_PASSWORD),
                "login_mode": "paper",
                "login_browser": _first_non_empty(
                    s.IB_WEB_LOGIN_BROWSER, s.IB_LOGIN_BROWSER, "chrome"
                ),
                "login_headless": s.IB_WEB_LOGIN_HEADLESS
                if s.IB_WEB_LOGIN_BROWSER or s.IB_WEB_USERNAME
                else s.IB_LOGIN_HEADLESS,
                "login_timeout": _first_non_empty(s.IB_WEB_LOGIN_TIMEOUT, s.IB_LOGIN_TIMEOUT, 180),
                "cookie_output": _first_non_empty(s.IB_WEB_COOKIE_OUTPUT, s.IB_COOKIE_OUTPUT),
            },
            "live": {
                "account_id": _first_non_empty(
                    s.IB_LIVE_ACCOUNT_ID,
                    s.IB_WEB_ACCOUNT_ID if ib_web_default_is_live else "",
                    s.IB_ACCOUNT_ID,
                ),
                "asset_type": _first_non_empty(
                    s.IB_LIVE_ASSET_TYPE,
                    s.IB_WEB_ASSET_TYPE if ib_web_default_is_live else "",
                    s.IB_ASSET_TYPE,
                    "STK",
                ),
                "base_url": _first_non_empty(
                    s.IB_LIVE_BASE_URL,
                    s.IB_WEB_BASE_URL if ib_web_default_is_live else "",
                    s.IB_BASE_URL,
                ),
                "access_token": _first_non_empty(
                    s.IB_LIVE_ACCESS_TOKEN,
                    s.IB_WEB_ACCESS_TOKEN if ib_web_default_is_live else "",
                    s.IB_ACCESS_TOKEN,
                ),
                "verify_ssl": s.IB_LIVE_VERIFY_SSL
                if s.IB_LIVE_BASE_URL or s.IB_LIVE_ACCOUNT_ID or s.IB_LIVE_ACCESS_TOKEN
                else s.IB_VERIFY_SSL,
                "timeout": _first_non_empty(
                    s.IB_LIVE_TIMEOUT,
                    s.IB_WEB_TIMEOUT if ib_web_default_is_live else 0,
                    s.IB_TIMEOUT,
                    10,
                ),
                "cookie_source": _first_non_empty(
                    s.IB_LIVE_COOKIE_SOURCE,
                    s.IB_WEB_COOKIE_SOURCE if ib_web_default_is_live else "",
                    s.IB_COOKIE_SOURCE,
                ),
                "cookie_browser": _first_non_empty(
                    s.IB_LIVE_COOKIE_BROWSER,
                    s.IB_WEB_COOKIE_BROWSER if ib_web_default_is_live else "",
                    s.IB_COOKIE_BROWSER,
                    "chrome",
                ),
                "cookie_path": _first_non_empty(
                    s.IB_LIVE_COOKIE_PATH,
                    s.IB_WEB_COOKIE_PATH if ib_web_default_is_live else "",
                    s.IB_COOKIE_PATH,
                    "/sso",
                ),
                "username": _first_non_empty(s.IB_WEB_USERNAME, s.IB_USERNAME),
                "password": _first_non_empty(s.IB_WEB_PASSWORD, s.IB_PASSWORD),
                "login_mode": "live",
                "login_browser": _first_non_empty(
                    s.IB_WEB_LOGIN_BROWSER, s.IB_LOGIN_BROWSER, "chrome"
                ),
                "login_headless": s.IB_WEB_LOGIN_HEADLESS
                if s.IB_WEB_LOGIN_BROWSER or s.IB_WEB_USERNAME
                else s.IB_LOGIN_HEADLESS,
                "login_timeout": _first_non_empty(s.IB_WEB_LOGIN_TIMEOUT, s.IB_LOGIN_TIMEOUT, 180),
                "cookie_output": _first_non_empty(s.IB_WEB_COOKIE_OUTPUT, s.IB_COOKIE_OUTPUT),
            },
        },
        "BINANCE": {
            "account_id": s.BINANCE_ACCOUNT_ID,
            "asset_type": s.BINANCE_ASSET_TYPE,
            "api_key": _env_or_default(
                s.BINANCE_API_KEY,
                env_values.get("BINANCE_API_KEY", ""),
            ),
            "secret_key": _env_or_default(
                s.BINANCE_SECRET_KEY,
                env_values.get("BINANCE_SECRET_KEY", ""),
                env_values.get("BINANCE_PASSWORD", ""),
                env_values.get("BINANCE_SECRET", ""),
            ),
            "testnet": s.BINANCE_TESTNET,
            "base_url": s.BINANCE_BASE_URL,
        },
        "OKX": {
            "account_id": s.OKX_ACCOUNT_ID,
            "asset_type": s.OKX_ASSET_TYPE,
            "api_key": _env_or_default(
                s.OKX_API_KEY,
                env_values.get("OKX_API_KEY", ""),
            ),
            "secret_key": _env_or_default(
                s.OKX_SECRET_KEY,
                env_values.get("OKX_SECRET_KEY", ""),
                env_values.get("OKX_SECRET", ""),
            ),
            "passphrase": _env_or_default(
                s.OKX_PASSPHRASE,
                env_values.get("OKX_PASSPHRASE", ""),
                env_values.get("OKX_PASSWORD", ""),
            ),
            "testnet": s.OKX_TESTNET,
            "base_url": s.OKX_BASE_URL,
        },
    }
    return redact_gateway_credentials(payload)
