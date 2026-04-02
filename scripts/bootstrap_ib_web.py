#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "src" / "backend"
BT_API_PY_DIR = PROJECT_ROOT.parent / "bt_api_py"
BACKEND_ENV_FILE = BACKEND_DIR / ".env"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(BT_API_PY_DIR) not in sys.path:
    sys.path.insert(0, str(BT_API_PY_DIR))


def load_backend_env_file() -> None:
    if not BACKEND_ENV_FILE.is_file():
        return
    for raw_line in BACKEND_ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


load_backend_env_file()

from app.config import get_settings
from app.services import manual_gateway_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-id", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--verify-ssl", choices=("true", "false"), default="")
    parser.add_argument("--timeout", type=float, default=0.0)
    parser.add_argument("--cookie-source", default="")
    parser.add_argument("--cookie-browser", default="")
    parser.add_argument("--cookie-path", default="")
    parser.add_argument("--cookie-output", default="")
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--login-mode", choices=("paper", "live"), default="")
    parser.add_argument("--login-browser", default="")
    parser.add_argument("--login-headless", choices=("true", "false"), default="")
    parser.add_argument("--login-timeout", type=int, default=0)
    parser.add_argument("--login-settle-timeout", type=int, default=0)
    parser.add_argument("--allow-browser-login", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def pick_bool(cli_value: str, config_value: bool) -> bool:
    if not cli_value:
        return bool(config_value)
    return cli_value.strip().lower() == "true"


def build_credentials(args: argparse.Namespace) -> dict[str, Any]:
    s = get_settings()
    return {
        "account_id": args.account_id or s.IB_WEB_ACCOUNT_ID or s.IB_ACCOUNT_ID,
        "base_url": args.base_url or s.IB_WEB_BASE_URL or s.IB_BASE_URL or "https://localhost:5000/v1/api",
        "verify_ssl": pick_bool(args.verify_ssl, s.IB_WEB_VERIFY_SSL if s.IB_WEB_BASE_URL else s.IB_VERIFY_SSL),
        "timeout": args.timeout or s.IB_WEB_TIMEOUT or s.IB_TIMEOUT or 10.0,
        "cookie_source": args.cookie_source or s.IB_WEB_COOKIE_SOURCE or s.IB_COOKIE_SOURCE,
        "cookie_browser": args.cookie_browser or s.IB_WEB_COOKIE_BROWSER or s.IB_COOKIE_BROWSER or "chrome",
        "cookie_path": args.cookie_path or s.IB_WEB_COOKIE_PATH or s.IB_COOKIE_PATH or "/sso",
        "cookie_output": args.cookie_output or s.IB_WEB_COOKIE_OUTPUT or s.IB_COOKIE_OUTPUT,
        "username": args.username or s.IB_WEB_USERNAME or s.IB_USERNAME,
        "password": args.password or s.IB_WEB_PASSWORD or s.IB_PASSWORD,
        "login_mode": args.login_mode or s.IB_WEB_LOGIN_MODE or "paper",
        "login_browser": args.login_browser or s.IB_WEB_LOGIN_BROWSER or s.IB_LOGIN_BROWSER or "chrome",
        "login_headless": pick_bool(
            args.login_headless,
            s.IB_WEB_LOGIN_HEADLESS if s.IB_WEB_LOGIN_BROWSER or s.IB_WEB_USERNAME else s.IB_LOGIN_HEADLESS,
        ),
        "login_timeout": args.login_timeout or s.IB_WEB_LOGIN_TIMEOUT or s.IB_LOGIN_TIMEOUT or 180,
        "login_settle_timeout": args.login_settle_timeout or int(os.environ.get("IB_WEB_LOGIN_SETTLE_TIMEOUT", "15") or 15),
    }


def emit(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    for key, value in payload.items():
        print(f"{key}: {value}")


def read_backend_env_values() -> dict[str, str]:
    values: dict[str, str] = {}
    if not BACKEND_ENV_FILE.is_file():
        return values
    for raw_line in BACKEND_ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value.strip()
    return values


def persist_and_verify_env(updates: dict[str, str]) -> tuple[bool, dict[str, str]]:
    manual_gateway_service._persist_ib_web_env_updates(updates)
    current = read_backend_env_values()
    tracked_keys = [
        "IB_WEB_BASE_URL",
        "IB_WEB_ACCOUNT_ID",
        "IB_WEB_COOKIE_SOURCE",
        "IB_WEB_COOKIE_OUTPUT",
        "IB_WEB_TIMEOUT",
    ]
    persisted = {key: current.get(key, "") for key in tracked_keys if key in updates}
    verified = all(current.get(key, "") == updates[key] for key in tracked_keys if key in updates)
    return verified, persisted


def main() -> int:
    args = parse_args()
    credentials = build_credentials(args)
    account_id = str(credentials.get("account_id") or "").strip()
    if not account_id:
        emit({"status": "error", "message": "Missing IB_WEB account_id"}, args.json)
        return 1

    base_url = manual_gateway_service._normalize_ib_web_base_url(str(credentials.get("base_url") or ""))
    verify_ssl = bool(credentials.get("verify_ssl", False))
    timeout = float(credentials.get("timeout", 10.0) or 10.0)

    if manual_gateway_service._should_manage_ib_clientportal(base_url):
        manual_gateway_service._ensure_ib_clientportal_running(base_url, manual_gateway_service._logger)
    resolved_base_url = manual_gateway_service._resolve_ib_web_base_url(
        base_url,
        verify_ssl,
        timeout,
        manual_gateway_service._logger,
    )
    credentials["base_url"] = resolved_base_url

    settings, cookies, authenticated, accounts, detected_account_id = (
        manual_gateway_service._load_ib_web_session_state(
            credentials,
            resolved_base_url,
            verify_ssl,
            timeout,
        )
    )
    if authenticated:
        session = {
            "cookies": cookies,
            "cookie_output": str(settings.get("cookie_output") or ""),
            "cookie_source": str(settings.get("cookie_source") or ""),
            "account_id": detected_account_id or account_id,
            "status_code": 200,
            "used_login": False,
        }
        updates = manual_gateway_service._build_ib_web_env_updates(
            credentials,
            resolved_base_url,
            verify_ssl,
            timeout,
            session,
        )
        env_verified, persisted = persist_and_verify_env(updates)
        if not env_verified:
            emit(
                {
                    "status": "error",
                    "authenticated": True,
                    "used_login": False,
                    "message": "Authenticated session is ready, but src/backend/.env verification failed.",
                    "env_file": str(BACKEND_ENV_FILE),
                    "persisted": persisted,
                },
                args.json,
            )
            return 3
        emit(
            {
                "status": "ok",
                "authenticated": True,
                "used_login": False,
                "base_url": resolved_base_url,
                "account_id": session["account_id"],
                "cookie_source": updates.get("IB_WEB_COOKIE_SOURCE", ""),
                "cookie_output": updates.get("IB_WEB_COOKIE_OUTPUT", ""),
                "accounts": len(accounts),
                "env_file": str(BACKEND_ENV_FILE),
                "env_verified": env_verified,
                "persisted": persisted,
            },
            args.json,
        )
        return 0

    if not args.allow_browser_login:
        emit(
            {
                "status": "error",
                "authenticated": False,
                "used_login": False,
                "message": "Existing IB_WEB cookies are unavailable or expired. Re-run with --allow-browser-login to refresh them.",
                "base_url": resolved_base_url,
                "cookie_source": credentials.get("cookie_source", ""),
                "cookie_output": credentials.get("cookie_output", ""),
            },
            args.json,
        )
        return 2

    if not (credentials.get("username") and credentials.get("password")):
        emit(
            {
                "status": "error",
                "authenticated": False,
                "used_login": False,
                "message": "Browser login requested but username/password are missing.",
            },
            args.json,
        )
        return 1

    _, ensure_authenticated_session, _ = manual_gateway_service._import_ib_web_session_helpers()
    session = ensure_authenticated_session(
        overrides={
            "base_url": resolved_base_url,
            "account_id": credentials.get("account_id", ""),
            "verify_ssl": verify_ssl,
            "timeout": timeout,
            "cookie_source": credentials.get("cookie_source", ""),
            "cookie_browser": credentials.get("cookie_browser", "chrome"),
            "cookie_path": credentials.get("cookie_path", "/sso"),
            "username": credentials.get("username", ""),
            "password": credentials.get("password", ""),
            "login_mode": credentials.get("login_mode", "paper"),
            "login_browser": credentials.get("login_browser", credentials.get("cookie_browser", "chrome")),
            "login_headless": credentials.get("login_headless", False),
            "login_timeout": credentials.get("login_timeout", 180),
            "login_settle_timeout": credentials.get("login_settle_timeout", 15),
            "cookie_output": credentials.get("cookie_output", ""),
        },
        base_dir=manual_gateway_service._ib_web_cookie_base_dir(),
        env_file=manual_gateway_service._backend_env_file(),
    )
    updates = manual_gateway_service._build_ib_web_env_updates(
        credentials,
        resolved_base_url,
        verify_ssl,
        timeout,
        session,
    )
    env_verified, persisted = persist_and_verify_env(updates)
    if not env_verified:
        emit(
            {
                "status": "error",
                "authenticated": True,
                "used_login": bool(session.get("used_login", False)),
                "message": "Authenticated session is ready, but src/backend/.env verification failed.",
                "env_file": str(BACKEND_ENV_FILE),
                "persisted": persisted,
            },
            args.json,
        )
        return 3
    emit(
        {
            "status": "ok",
            "authenticated": True,
            "used_login": bool(session.get("used_login", False)),
            "base_url": resolved_base_url,
            "account_id": session.get("account_id", account_id),
            "cookie_source": updates.get("IB_WEB_COOKIE_SOURCE", ""),
            "cookie_output": updates.get("IB_WEB_COOKIE_OUTPUT", ""),
            "env_file": str(BACKEND_ENV_FILE),
            "env_verified": env_verified,
            "persisted": persisted,
        },
        args.json,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
