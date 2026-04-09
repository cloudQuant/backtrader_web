#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
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
from bt_api_py.functions import ib_web_session as ib_web_session_helpers


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


def _gateway_http_ok(host: str, port: int, timeout: float = 5.0) -> bool:
    """Return True if the gateway actually responds to an HTTPS request (not just TCP)."""
    import requests as _requests
    import urllib3 as _urllib3
    _urllib3.disable_warnings(_urllib3.exceptions.InsecureRequestWarning)
    try:
        r = _requests.get(
            f"https://{host}:{port}/sso/Login",
            verify=False,
            timeout=timeout,
            allow_redirects=True,
        )
        return r.status_code < 500
    except Exception:
        return False


def _kill_gateway_on_port(port: int) -> None:
    """Kill any process listening on *port* so we can restart the gateway."""
    import subprocess as _sp
    try:
        result = _sp.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True, timeout=5,
        )
        pids = [int(p) for p in result.stdout.split() if p.strip().isdigit()]
    except Exception:
        pids = []
    import signal
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    if pids:
        time.sleep(2.0)
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        time.sleep(1.0)


def ensure_local_clientportal_started(base_url: str, timeout: float) -> str:
    normalized = manual_gateway_service._normalize_ib_web_base_url(base_url)
    if not manual_gateway_service._should_manage_ib_clientportal(normalized):
        return normalized
    host, port = manual_gateway_service._parse_base_url_endpoint(normalized)

    # If port is open but gateway is not responding to HTTP, kill and restart.
    if manual_gateway_service._is_tcp_endpoint_reachable(host, port, timeout=2.0):
        if not _gateway_http_ok(host, port, timeout=8.0):
            print(f"[bootstrap] Gateway on {host}:{port} is TCP-open but HTTP-unresponsive, restarting…")
            _kill_gateway_on_port(port)
            # Reset the module-level process reference so _ensure picks up fresh start
            manual_gateway_service._ib_clientportal_process = None
        else:
            print(f"[bootstrap] Gateway on {host}:{port} is responsive, skipping restart.")
            return normalized

    manual_gateway_service._ensure_ib_clientportal_running(
        normalized,
        manual_gateway_service._logger,
        startup_wait_sec=max(float(timeout or 0.0), 30.0),
    )
    time.sleep(2.0)

    # Verify HTTP liveness after startup
    ok = False
    deadline = time.time() + 30.0
    while time.time() < deadline:
        if _gateway_http_ok(host, port, timeout=5.0):
            ok = True
            break
        time.sleep(2.0)
    if not ok:
        raise RuntimeError(
            f"IB Client Portal started but not responding to HTTPS on {host}:{port}"
        )
    print(f"[bootstrap] Gateway on {host}:{port} is up and responding to HTTP.")
    return normalized


def build_browser_login_settings(
    credentials: dict[str, Any],
    resolved_base_url: str,
    verify_ssl: bool,
    timeout: float,
) -> dict[str, Any]:
    return ib_web_session_helpers.load_ib_web_settings(
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
            "login_browser": credentials.get(
                "login_browser",
                credentials.get("cookie_browser", "chrome"),
            ),
            "login_headless": credentials.get("login_headless", False),
            "login_timeout": credentials.get("login_timeout", 180),
            "login_settle_timeout": credentials.get("login_settle_timeout", 15),
            "cookie_output": credentials.get("cookie_output", ""),
        },
        base_dir=manual_gateway_service._ib_web_cookie_base_dir(),
        env_file=manual_gateway_service._backend_env_file(),
    )


def login_and_save_cookies_resilient(settings: dict[str, Any]) -> dict[str, Any]:
    username = str(settings.get("username") or "")
    password = str(settings.get("password") or "")
    if not username or not password:
        raise RuntimeError("IB_WEB_USERNAME and IB_WEB_PASSWORD are required")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("playwright is required. Install: pip install playwright") from None
    login_mode = str(settings.get("login_mode") or "paper")
    browser_name = str(settings.get("login_browser") or "chrome")
    launch_headless = bool(settings.get("login_headless", False))
    launch_timeout = int(settings.get("login_timeout", 180))
    base_url = str(settings.get("base_url") or "https://localhost:5000/v1/api")
    verify_ssl = bool(settings.get("verify_ssl", False))
    timeout = int(settings.get("timeout", 10))
    configured_account_id = str(settings.get("account_id") or "").strip()
    settle_timeout = max(int(settings.get("login_settle_timeout", 8) or 8), 0)
    cookie_output = str(
        settings.get("cookie_output")
        or ib_web_session_helpers.default_cookie_output(base_dir=settings.get("cookie_base_dir"))
    )
    cookie_output_path = ib_web_session_helpers.resolve_local_path(
        cookie_output,
        base_dir=settings.get("cookie_base_dir"),
    )
    origin = ib_web_session_helpers.gateway_origin(base_url)
    login_url = f"{origin}/sso/Login?forwardTo=22&RL=1&ip2loc=US"
    with sync_playwright() as playwright:
        browser_type = playwright.chromium
        launch_kwargs: dict[str, Any] = {"headless": launch_headless}
        if browser_name == "firefox":
            browser_type = playwright.firefox
        elif browser_name == "webkit":
            browser_type = playwright.webkit
        elif browser_name == "edge":
            launch_kwargs["channel"] = "msedge"
        elif browser_name == "chrome":
            launch_kwargs["channel"] = "chrome"
        try:
            browser = browser_type.launch(**launch_kwargs)
        except Exception:
            launch_kwargs.pop("channel", None)
            browser = browser_type.launch(**launch_kwargs)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        page.set_default_timeout(15000)
        page.set_default_navigation_timeout(45000)
        navigation_errors: list[str] = []
        loaded_form = False
        for target in (origin, login_url):
            try:
                page.goto(target, wait_until="commit", timeout=45000)
                page.wait_for_timeout(2000)
                page.wait_for_selector(
                    "input[name='password'], input[id='password'], input[type='password']",
                    timeout=15000,
                )
                loaded_form = True
                break
            except Exception as exc:
                navigation_errors.append(f"{target}: {type(exc).__name__}: {exc}")
        if not loaded_form:
            browser.close()
            raise RuntimeError(
                "Unable to open IB Client Portal login page: " + " | ".join(navigation_errors)
            )
        mode_changed = ib_web_session_helpers._click_mode(page, login_mode)
        if mode_changed:
            page.wait_for_timeout(1000)
        ib_web_session_helpers._fill_credentials(page, username, password)
        page.wait_for_timeout(300)
        ib_web_session_helpers._submit_login(page)
        deadline = time.time() + launch_timeout
        cookies: dict[str, str] = {}
        last_status = None
        while time.time() < deadline:
            page.wait_for_timeout(2000)
            cookies = ib_web_session_helpers._cookie_dict_from_context(context, origin)
            if not cookies:
                continue
            try:
                response = ib_web_session_helpers.auth_status(
                    base_url,
                    cookies,
                    verify_ssl=verify_ssl,
                    timeout=timeout,
                )
            except ib_web_session_helpers.requests.RequestException:
                continue
            last_status = response.status_code
            if response.status_code != 200:
                continue
            try:
                accounts = ib_web_session_helpers.fetch_accounts(
                    base_url,
                    cookies,
                    verify_ssl=verify_ssl,
                    timeout=timeout,
                )
            except ib_web_session_helpers.requests.RequestException:
                accounts = []
            account_id = (
                ib_web_session_helpers.pick_account_id(accounts, login_mode)
                or configured_account_id
            )
            if not account_id:
                continue
            if settle_timeout > 0:
                settle_deadline = min(time.time() + settle_timeout, deadline)
                stable = False
                while time.time() < settle_deadline:
                    page.wait_for_timeout(2000)
                    refreshed_cookies = ib_web_session_helpers._cookie_dict_from_context(context, origin)
                    if not refreshed_cookies:
                        continue
                    try:
                        stable_response = ib_web_session_helpers.auth_status(
                            base_url,
                            refreshed_cookies,
                            verify_ssl=verify_ssl,
                            timeout=timeout,
                        )
                    except ib_web_session_helpers.requests.RequestException:
                        continue
                    if stable_response.status_code != 200:
                        continue
                    try:
                        stable_accounts = ib_web_session_helpers.fetch_accounts(
                            base_url,
                            refreshed_cookies,
                            verify_ssl=verify_ssl,
                            timeout=timeout,
                        )
                    except ib_web_session_helpers.requests.RequestException:
                        stable_accounts = []
                    stable_account_id = (
                        ib_web_session_helpers.pick_account_id(stable_accounts, login_mode)
                        or account_id
                        or configured_account_id
                    )
                    if stable_account_id:
                        cookies = refreshed_cookies
                        account_id = stable_account_id
                        stable = True
                        break
                if not stable:
                    continue
            ib_web_session_helpers.save_cookies_to_file(cookies, str(cookie_output_path))
            browser.close()
            return {
                "cookies": cookies,
                "cookie_output": str(cookie_output_path),
                "cookie_output_relative": ib_web_session_helpers.to_relative_path(
                    cookie_output_path,
                    base_dir=settings.get("cookie_base_dir"),
                ),
                "cookie_source": ib_web_session_helpers.normalize_cookie_source(
                    f"file:{cookie_output_path}",
                    base_dir=settings.get("cookie_base_dir"),
                ),
                "account_id": account_id,
                "status_code": response.status_code,
                "used_login": True,
            }
        browser.close()
    raise RuntimeError(f"Timed out waiting for authenticated session, last status={last_status}")


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

    verify_ssl = bool(credentials.get("verify_ssl", False))
    timeout = float(credentials.get("timeout", 10.0) or 10.0)
    base_url = ensure_local_clientportal_started(
        str(credentials.get("base_url") or ""),
        timeout,
    )

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

    session = login_and_save_cookies_resilient(
        build_browser_login_settings(
            credentials,
            resolved_base_url,
            verify_ssl,
            timeout,
        )
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
