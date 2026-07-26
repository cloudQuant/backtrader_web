from __future__ import annotations

from typing import Any


def pick_explicit_or_setting_or_env(
    explicit_value: Any,
    settings: Any,
    setting_names: tuple[str, ...],
    env_names: tuple[str, ...],
    env_values: dict[str, str] | None = None,
    default: Any = "",
) -> Any:
    if explicit_value not in {None, ""}:
        return explicit_value
    for setting_name in setting_names:
        value = getattr(settings, setting_name, None)
        if value not in {None, ""}:
            return value
    if env_values:
        for env_name in env_names:
            value = env_values.get(env_name)
            if value not in {None, ""}:
                return value
    return default


def coerce_bool_like(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in {None, ""}:
        return default
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def coerce_str(value: Any) -> str:
    if value in {None, ""}:
        return ""
    return str(value).strip()


def merge_binance_default_credentials(
    credentials: dict[str, Any],
    settings: Any,
    env_values: dict[str, str],
) -> dict[str, Any]:
    resolved = dict(credentials)
    resolved["api_key"] = coerce_str(
        pick_explicit_or_setting_or_env(
            resolved.get("api_key"),
            settings,
            ("BINANCE_API_KEY",),
            ("BINANCE_API_KEY",),
            env_values,
            default="",
        )
    )
    resolved["secret_key"] = coerce_str(
        pick_explicit_or_setting_or_env(
            resolved.get("secret_key"),
            settings,
            ("BINANCE_SECRET_KEY",),
            ("BINANCE_SECRET_KEY", "BINANCE_PASSWORD", "BINANCE_SECRET"),
            env_values,
            default="",
        )
    )
    resolved["testnet"] = coerce_bool_like(
        pick_explicit_or_setting_or_env(
            resolved.get("testnet"),
            settings,
            ("BINANCE_TESTNET",),
            ("BINANCE_TESTNET",),
            env_values,
            default=False,
        ),
        default=False,
    )
    resolved["base_url"] = coerce_str(
        pick_explicit_or_setting_or_env(
            resolved.get("base_url"),
            settings,
            ("BINANCE_BASE_URL",),
            ("BINANCE_BASE_URL",),
            env_values,
            default="",
        )
    )
    return resolved


def merge_okx_default_credentials(
    credentials: dict[str, Any],
    settings: Any,
    env_values: dict[str, str],
) -> dict[str, Any]:
    resolved = dict(credentials)
    resolved["api_key"] = coerce_str(
        pick_explicit_or_setting_or_env(
            resolved.get("api_key"),
            settings,
            ("OKX_API_KEY",),
            ("OKX_API_KEY",),
            env_values,
            default="",
        )
    )
    resolved["secret_key"] = coerce_str(
        pick_explicit_or_setting_or_env(
            resolved.get("secret_key"),
            settings,
            ("OKX_SECRET_KEY",),
            ("OKX_SECRET_KEY", "OKX_SECRET"),
            env_values,
            default="",
        )
    )
    resolved["passphrase"] = coerce_str(
        pick_explicit_or_setting_or_env(
            resolved.get("passphrase"),
            settings,
            ("OKX_PASSPHRASE",),
            ("OKX_PASSPHRASE", "OKX_PASSWORD"),
            env_values,
            default="",
        )
    )
    resolved["testnet"] = coerce_bool_like(
        pick_explicit_or_setting_or_env(
            resolved.get("testnet"),
            settings,
            ("OKX_TESTNET",),
            ("OKX_TESTNET",),
            env_values,
            default=False,
        ),
        default=False,
    )
    resolved["base_url"] = coerce_str(
        pick_explicit_or_setting_or_env(
            resolved.get("base_url"),
            settings,
            ("OKX_BASE_URL",),
            ("OKX_BASE_URL",),
            env_values,
            default="",
        )
    )
    return resolved


def merge_mt5_default_credentials(
    credentials: dict[str, Any],
    settings: Any,
    env_values: dict[str, str],
) -> dict[str, Any]:
    resolved = dict(credentials)
    resolved["login"] = coerce_str(
        pick_explicit_or_setting_or_env(
            resolved.get("login"),
            settings,
            ("MT5_LOGIN",),
            ("MT5_LOGIN", "MT5_ACCOUNT"),
            env_values,
            default="",
        )
    )
    resolved["password"] = coerce_str(
        pick_explicit_or_setting_or_env(
            resolved.get("password"),
            settings,
            ("MT5_PASSWORD",),
            ("MT5_PASSWORD", "MT5_PASS"),
            env_values,
            default="",
        )
    )
    resolved["server"] = coerce_str(
        pick_explicit_or_setting_or_env(
            resolved.get("server"),
            settings,
            ("MT5_SERVER",),
            ("MT5_SERVER", "MT5_ACCOUNT_SERVER"),
            env_values,
            default="",
        )
    )
    resolved["ws_uri"] = coerce_str(
        pick_explicit_or_setting_or_env(
            resolved.get("ws_uri"),
            settings,
            ("MT5_WS_URI",),
            ("MT5_WS_URI",),
            env_values,
            default="",
        )
    )
    resolved["symbol_suffix"] = coerce_str(
        pick_explicit_or_setting_or_env(
            resolved.get("symbol_suffix"),
            settings,
            ("MT5_SYMBOL_SUFFIX",),
            ("MT5_SYMBOL_SUFFIX",),
            env_values,
            default="",
        )
    )
    return resolved


def pick_explicit_or_setting(
    explicit_value: Any,
    settings: Any,
    *setting_names: str,
    default: Any = "",
) -> Any:
    if explicit_value not in {None, ""}:
        return explicit_value
    for name in setting_names:
        value = getattr(settings, name, None)
        if value not in {None, ""}:
            return value
    return default


def merge_ib_web_default_credentials(credentials: dict[str, Any], settings: Any) -> dict[str, Any]:
    resolved = dict(credentials)
    login_mode = (
        str(
            pick_explicit_or_setting(
                resolved.get("login_mode"),
                settings,
                "IB_WEB_LOGIN_MODE",
                default="paper",
            )
            or "paper"
        )
        .strip()
        .lower()
    )
    if login_mode not in {"paper", "live"}:
        login_mode = "paper"
    mode_prefix = "LIVE" if login_mode == "live" else "PAPER"

    resolved["login_mode"] = login_mode
    resolved["account_id"] = str(
        pick_explicit_or_setting(
            resolved.get("account_id"),
            settings,
            "IB_WEB_ACCOUNT_ID",
            f"IB_{mode_prefix}_ACCOUNT_ID",
            "IB_ACCOUNT_ID",
            default="",
        )
        or ""
    ).strip()
    resolved["asset_type"] = (
        str(
            pick_explicit_or_setting(
                resolved.get("asset_type"),
                settings,
                "IB_WEB_ASSET_TYPE",
                f"IB_{mode_prefix}_ASSET_TYPE",
                "IB_ASSET_TYPE",
                default="STK",
            )
            or "STK"
        ).strip()
        or "STK"
    )
    resolved["base_url"] = str(
        pick_explicit_or_setting(
            resolved.get("base_url"),
            settings,
            "IB_WEB_BASE_URL",
            f"IB_{mode_prefix}_BASE_URL",
            "IB_BASE_URL",
            default="https://localhost:5000",
        )
        or "https://localhost:5000"
    ).strip()
    resolved["access_token"] = str(
        pick_explicit_or_setting(
            resolved.get("access_token"),
            settings,
            "IB_WEB_ACCESS_TOKEN",
            f"IB_{mode_prefix}_ACCESS_TOKEN",
            "IB_ACCESS_TOKEN",
            default="",
        )
        or ""
    ).strip()
    resolved["verify_ssl"] = pick_explicit_or_setting(
        resolved.get("verify_ssl"),
        settings,
        "IB_WEB_VERIFY_SSL",
        f"IB_{mode_prefix}_VERIFY_SSL",
        "IB_VERIFY_SSL",
        default=False,
    )
    resolved["timeout"] = pick_explicit_or_setting(
        resolved.get("timeout"),
        settings,
        "IB_WEB_TIMEOUT",
        f"IB_{mode_prefix}_TIMEOUT",
        "IB_TIMEOUT",
        default=10.0,
    )
    resolved["cookie_browser"] = (
        str(
            pick_explicit_or_setting(
                resolved.get("cookie_browser"),
                settings,
                "IB_WEB_COOKIE_BROWSER",
                f"IB_{mode_prefix}_COOKIE_BROWSER",
                "IB_COOKIE_BROWSER",
                default="chrome",
            )
            or "chrome"
        ).strip()
        or "chrome"
    )
    resolved["cookie_path"] = (
        str(
            pick_explicit_or_setting(
                resolved.get("cookie_path"),
                settings,
                "IB_WEB_COOKIE_PATH",
                f"IB_{mode_prefix}_COOKIE_PATH",
                "IB_COOKIE_PATH",
                default="/sso",
            )
            or "/sso"
        ).strip()
        or "/sso"
    )
    resolved["cookie_output"] = str(
        pick_explicit_or_setting(
            resolved.get("cookie_output"),
            settings,
            "IB_WEB_COOKIE_OUTPUT",
            "IB_COOKIE_OUTPUT",
            default="",
        )
        or ""
    ).strip()
    resolved["cookie_source"] = str(
        pick_explicit_or_setting(
            resolved.get("cookie_source"),
            settings,
            "IB_WEB_COOKIE_SOURCE",
            f"IB_{mode_prefix}_COOKIE_SOURCE",
            "IB_COOKIE_SOURCE",
            default="",
        )
        or ""
    ).strip()
    if not resolved["cookie_source"] and resolved["cookie_output"]:
        resolved["cookie_source"] = f"file:{resolved['cookie_output']}"
    resolved["username"] = str(
        pick_explicit_or_setting(
            resolved.get("username"),
            settings,
            "IB_WEB_USERNAME",
            "IB_USERNAME",
            default="",
        )
        or ""
    ).strip()
    resolved["password"] = str(
        pick_explicit_or_setting(
            resolved.get("password"),
            settings,
            "IB_WEB_PASSWORD",
            "IB_PASSWORD",
            default="",
        )
        or ""
    ).strip()
    resolved["login_browser"] = (
        str(
            pick_explicit_or_setting(
                resolved.get("login_browser"),
                settings,
                "IB_WEB_LOGIN_BROWSER",
                "IB_LOGIN_BROWSER",
                default=resolved["cookie_browser"],
            )
            or resolved["cookie_browser"]
        ).strip()
        or resolved["cookie_browser"]
    )
    resolved["login_headless"] = pick_explicit_or_setting(
        resolved.get("login_headless"),
        settings,
        "IB_WEB_LOGIN_HEADLESS",
        "IB_LOGIN_HEADLESS",
        default=False,
    )
    resolved["login_timeout"] = pick_explicit_or_setting(
        resolved.get("login_timeout"),
        settings,
        "IB_WEB_LOGIN_TIMEOUT",
        "IB_LOGIN_TIMEOUT",
        default=180,
    )
    return resolved
