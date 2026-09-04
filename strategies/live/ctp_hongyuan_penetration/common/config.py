"""宏源期货仿真环境配置与凭证管理."""
from __future__ import annotations

import os
from pathlib import Path


_SUITE_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SUITE_DIR.parents[2]
_CREDENTIAL_FILE_ENV = "HONGYUAN_CREDENTIALS_FILE"
_REFERENCE_ROOT_ENV = "BACKTRADER_REFERENCE_ROOT"

HONGYUAN_ENVIRONMENTS = {
    "telecom": {
        "name": "宏源期货仿真（电信）",
        "td_address": "tcp://101.230.79.235:32205",
        "md_address": "tcp://101.230.79.235:32213",
        "description": "上海唐银机房，电信线路，BrokerID=3070，v6.7.10_20250422 API",
    },
    "unicom": {
        "name": "宏源期货仿真（联通）",
        "td_address": "tcp://112.65.19.116:32205",
        "md_address": "tcp://112.65.19.116:32213",
        "description": "上海唐银机房，联通线路，BrokerID=3070，v6.7.10_20250422 API",
    },
}

DEFAULT_ENV = "telecom"
DEFAULT_BROKER_ID = "3070"
DEFAULT_APP_ID = "client_wtyj_1.0.9.9"
DEFAULT_AUTH_CODE = "VCSX4A2S43I4RN25"
# Verified through a read-only CTP instrument query on 2026-09-04.  Operators
# can and should override these through the environment as contracts roll.
DEFAULT_ORDER_SYMBOL = "rb2610"
DEFAULT_TICK_SYMBOL = "rb2610"


def _credential_file_candidates() -> tuple[Path, ...]:
    """Return credential files in explicit-to-compatible precedence order.

    The strategy workspace intentionally does not copy a developer's private
    ``.env`` file.  An operator can point ``HONGYUAN_CREDENTIALS_FILE`` at an
    approved file, while the default reference root preserves the requested
    migration path from the backtrader CTP certification example.
    """
    explicit_file = os.getenv(_CREDENTIAL_FILE_ENV, "").strip()
    reference_root = Path(
        os.getenv(
            _REFERENCE_ROOT_ENV,
            str(Path.home() / "Documents/new_projects/backtrader"),
        )
    ).expanduser()
    candidates = (
        Path(explicit_file).expanduser() if explicit_file else None,
        _SUITE_DIR / ".env",
        _REPO_ROOT / ".env",
        reference_root / "examples/007_ctp/live_certification/hongyuan_penetration/.env",
        reference_root / ".env",
    )
    return tuple(path for path in candidates if path is not None)


def _environment_credentials() -> tuple[str | None, str | None]:
    """Return a complete credential pair supplied directly by the environment."""
    return (
        os.getenv("HONGYUAN_USER_ID") or os.getenv("hongyuan_user_id"),
        os.getenv("HONGYUAN_PASSWORD") or os.getenv("hongyuan_password"),
    )


def _credentials_from_available_files() -> tuple[str, str] | None:
    """Read the first approved file that contains one complete credential pair.

    The values are returned directly rather than copied into ``os.environ``.
    That prevents a partial shell configuration or one incomplete file from
    being combined with a different source's credential field.
    """
    try:
        from dotenv import dotenv_values
    except ImportError:
        return None

    for credential_file in _credential_file_candidates():
        if credential_file.is_file():
            values = dotenv_values(credential_file)
            investor_id = values.get("HONGYUAN_USER_ID") or values.get("hongyuan_user_id")
            password = values.get("HONGYUAN_PASSWORD") or values.get("hongyuan_password")
            if investor_id and password:
                return str(investor_id), str(password)
    return None


def get_credentials():
    """Get Hongyuan credentials from environment variables."""
    investor_id, password = _environment_credentials()
    if investor_id and password:
        return investor_id, password

    file_credentials = _credentials_from_available_files()
    if file_credentials is not None:
        return file_credentials

    raise RuntimeError(
        "宏源期货凭证未找到。"
        "请在环境变量、HONGYUAN_CREDENTIALS_FILE，或允许的 .env 文件中设置 "
        "HONGYUAN_USER_ID 和 HONGYUAN_PASSWORD。"
    )


def get_env_key():
    """Get the Hongyuan environment key from env var or default."""
    return os.getenv("HONGYUAN_ENV", DEFAULT_ENV)


def get_order_symbol():
    """Get the symbol to use for order tests."""
    return os.getenv(
        "HONGYUAN_ORDER_SYMBOL",
        os.getenv("HONGYUAN_TICK_SYMBOL", DEFAULT_ORDER_SYMBOL),
    )


def get_tick_symbol():
    """Get the symbol to use for tick / market-data tests."""
    return os.getenv("HONGYUAN_TICK_SYMBOL", DEFAULT_TICK_SYMBOL)


def create_config(env_key=None):
    """Create Hongyuan connection configuration dict."""
    env_key = env_key or get_env_key()
    if env_key not in HONGYUAN_ENVIRONMENTS:
        raise ValueError(
            f"Invalid environment key: {env_key}. "
            f"Valid keys: {', '.join(HONGYUAN_ENVIRONMENTS)}"
        )
    env = HONGYUAN_ENVIRONMENTS[env_key]
    investor_id, password = get_credentials()
    return {
        "td_address": env["td_address"],
        "md_address": env["md_address"],
        "broker_id": DEFAULT_BROKER_ID,
        "investor_id": investor_id,
        "password": password,
        "app_id": DEFAULT_APP_ID,
        "auth_code": DEFAULT_AUTH_CODE,
    }
