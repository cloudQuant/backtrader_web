from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_IB_WEB_LOGIN_LOCK = threading.Lock()


def _ib_web_session_module() -> Any:
    """Load either the legacy helper or the standalone IB Web runtime package."""
    try:
        from bt_api_py.functions import ib_web_session
    except ModuleNotFoundError as exc:
        if exc.name not in {
            "bt_api_py",
            "bt_api_py.functions",
            "bt_api_py.functions.ib_web_session",
        }:
            raise
        import sys

        ib_web_source = Path(__file__).resolve().parents[5].parent / "bt_api_ib_web" / "src"
        if ib_web_source.is_dir() and str(ib_web_source) not in sys.path:
            sys.path.insert(0, str(ib_web_source))
        from bt_api_ib_web.runtime import session as ib_web_session

    return ib_web_session


def ib_web_cookie_base_dir(
    installed_bt_api_py_dir: Callable[[], Path | None],
    backend_env_file: Callable[[], Path],
) -> Path:
    bt_api_py_dir = installed_bt_api_py_dir()
    if bt_api_py_dir is not None and bt_api_py_dir.is_dir():
        return bt_api_py_dir
    return backend_env_file().parent


def to_backend_env_relative_path(
    path_value: str,
    cookie_base_dir: Callable[[], Path],
) -> str:
    candidate = str(path_value or "").strip()
    if not candidate:
        return ""
    resolved = Path(candidate)
    if not resolved.is_absolute():
        resolved = (cookie_base_dir() / resolved).resolve()
    bt_api_parts = resolved.parts
    if "bt_api_py" in bt_api_parts:
        bt_api_index = max(index for index, part in enumerate(bt_api_parts) if part == "bt_api_py")
        relative_parts = bt_api_parts[bt_api_index + 1 :]
        if relative_parts:
            return "/".join(relative_parts)
    base_dir = cookie_base_dir().resolve()
    try:
        return str(resolved.relative_to(base_dir)).replace("\\", "/")
    except ValueError:
        return str(resolved)


def normalize_ib_web_base_url(base_url: str) -> str:
    raw = str(base_url or "https://localhost:5000").strip()
    parsed = urlparse(raw)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or parsed.path or "localhost:5000"
    path = parsed.path if parsed.netloc else ""
    normalized_path = path.rstrip("/")
    if normalized_path in {"", "/"}:
        normalized_path = "/v1/api"
    return parsed._replace(scheme=scheme, netloc=netloc, path=normalized_path).geturl()


def swap_url_scheme(base_url: str, scheme: str) -> str:
    parsed = urlparse(base_url)
    return parsed._replace(scheme=scheme).geturl()


def load_ib_web_session_state(
    credentials: dict[str, Any],
    base_url: str,
    verify_ssl: bool,
    timeout: float,
    cookie_base_dir: Callable[[], Path],
    backend_env_file_for_helpers: Callable[[], Path],
) -> tuple[dict[str, Any], dict[str, str], bool, list[dict[str, Any]], str]:
    session_helpers = _ib_web_session_module()

    settings = session_helpers.load_ib_web_settings(
        overrides={
            "base_url": base_url,
            "account_id": credentials.get("account_id", ""),
            "verify_ssl": verify_ssl,
            "timeout": timeout,
            "cookie_source": credentials.get("cookie_source", ""),
            "cookie_browser": credentials.get("cookie_browser", "chrome"),
            "cookie_path": credentials.get("cookie_path", "/sso"),
            "cookie_output": credentials.get("cookie_output", ""),
        },
        base_dir=cookie_base_dir(),
        env_file=backend_env_file_for_helpers(),
    )
    cookies = session_helpers.current_cookie_payload(settings)
    authenticated = (
        session_helpers.cookies_are_authenticated(settings, cookies) if cookies else False
    )
    accounts = (
        session_helpers.fetch_accounts(
            str(settings.get("base_url") or base_url),
            cookies,
            verify_ssl=bool(settings.get("verify_ssl", verify_ssl)),
            timeout=int(settings.get("timeout", timeout)),
        )
        if authenticated
        else []
    )
    account_id = (
        session_helpers.pick_account_id(accounts, str(settings.get("login_mode") or "paper"))
        if accounts
        else ""
    )
    return settings, cookies, authenticated, accounts, account_id


def resolve_ib_web_base_url(
    base_url: str,
    verify_ssl: bool,
    timeout: float,
    logger,
    should_manage_clientportal: Callable[[str], bool],
    import_session_helpers: Callable[[], tuple[Any, Any, Any]],
) -> str:
    normalized = normalize_ib_web_base_url(base_url)
    if not should_manage_clientportal(normalized):
        return normalized
    auth_status, _, _ = import_session_helpers()
    candidates = [normalized]
    alternate_scheme = "http" if urlparse(normalized).scheme == "https" else "https"
    alternate = swap_url_scheme(normalized, alternate_scheme)
    if alternate != normalized:
        candidates.append(alternate)
    last_error: Exception | None = None
    request_timeout = min(max(int(timeout), 2), 5)
    deadline = time.monotonic() + max(float(timeout), 0.0) + 8.0
    while time.monotonic() < deadline:
        for candidate in candidates:
            try:
                auth_status(
                    candidate,
                    {},
                    verify_ssl=verify_ssl,
                    timeout=request_timeout,
                )
                if candidate != normalized:
                    logger.warning(
                        "IB Web base_url protocol fallback applied: %s -> %s",
                        normalized,
                        candidate,
                    )
                return candidate
            except Exception as exc:
                last_error = exc
        if time.monotonic() + 1.0 >= deadline:
            break
        time.sleep(1.0)
    if last_error is not None:
        logger.warning(
            "IB Web base_url probe failed for %s: %s: %s",
            normalized,
            type(last_error).__name__,
            last_error,
        )
    return normalized


def _ib_web_login_url(base_url: str) -> str:
    """Return the Client Portal login page for an API base URL."""
    parsed = urlparse(base_url)
    return parsed._replace(
        path="/sso/Login",
        params="",
        query="forwardTo=22&RL=1&ip2loc=US",
        fragment="",
    ).geturl()


def _wait_for_browser_authenticated_session(
    driver: Any,
    session_helpers: Any,
    base_url: str,
    verify_ssl: bool,
    timeout: float,
    login_timeout: float,
    headless: bool,
    login_mode: str,
) -> dict[str, str]:
    """Wait for the browser login flow to produce an authenticated API session."""
    deadline = time.monotonic() + max(login_timeout, timeout, 1.0)
    last_cookies: dict[str, str] = {}
    rejected_credentials = False
    while time.monotonic() < deadline:
        last_cookies = {
            str(cookie["name"]): str(cookie["value"])
            for cookie in driver.get_cookies()
            if cookie.get("name") and cookie.get("value")
        }
        if last_cookies:
            try:
                response = session_helpers.auth_status(
                    base_url,
                    last_cookies,
                    verify_ssl=verify_ssl,
                    timeout=max(2, int(timeout)),
                )
            except Exception:
                response = None
            if response is not None and session_helpers.auth_response_is_authenticated(response):
                return last_cookies

        login_errors = driver.find_elements("css selector", ".xyz-errormessage")
        if any((error.text or "").strip() for error in login_errors):
            rejected_credentials = True
            if headless:
                mode = "paper" if str(login_mode).strip().lower() == "paper" else "live"
                raise RuntimeError(
                    f"IB Client Portal rejected the configured {mode} login credentials"
                )

        # A security-card or two-factor challenge cannot be completed inside a
        # headless browser.  Fail promptly with an actionable message instead
        # of consuming the full gateway startup timeout.
        if headless:
            challenge_fields = driver.find_elements(
                "css selector",
                "#xyz-field-bronze-response, #xyz-field-silver-response, "
                "#xyz-field-gold-response, #xyz-field-temp-response",
            )
            if any(field.is_displayed() for field in challenge_fields):
                raise RuntimeError(
                    "IB Client Portal requires interactive security verification; "
                    "set IB_WEB_LOGIN_HEADLESS=false and complete it in the opened browser"
                )
        time.sleep(1.0)

    if rejected_credentials:
        mode = "paper" if str(login_mode).strip().lower() == "paper" else "live"
        raise RuntimeError(
            f"IB Client Portal rejected the configured {mode} login credentials; "
            "correct them in the opened browser and retry"
        )
    raise RuntimeError("IB Client Portal login did not create an authenticated session")


def login_ib_web_session_with_browser(
    credentials: dict[str, Any],
    base_url: str,
    verify_ssl: bool,
    timeout: float,
    *,
    cookie_base_dir: Callable[[], Path],
    backend_env_file_for_helpers: Callable[[], Path],
) -> dict[str, Any]:
    """Log in to the local Client Portal and save the newly issued cookies.

    The IB Web runtime package only validates a pre-existing cookie file.  It
    does not use the configured username/password itself, so an expired
    Client Portal session used to fail every strategy start.  This small
    browser flow is deliberately local-only: it submits credentials to the
    Client Portal started on the same machine and persists only the returned
    session cookies.
    """
    username = str(credentials.get("username") or "").strip()
    password = str(credentials.get("password") or "").strip()
    if not username or not password:
        raise RuntimeError("IB Client Portal username and password are not configured")

    session_helpers = _ib_web_session_module()
    settings = session_helpers.load_ib_web_settings(
        overrides={
            "base_url": base_url,
            "account_id": credentials.get("account_id", ""),
            "verify_ssl": verify_ssl,
            "timeout": timeout,
            "cookie_source": credentials.get("cookie_source", ""),
            "cookie_browser": credentials.get("cookie_browser", "chrome"),
            "cookie_path": credentials.get("cookie_path", "/sso"),
            "username": username,
            "password": password,
            "login_mode": credentials.get("login_mode", "paper"),
            "login_browser": credentials.get("login_browser", "chrome"),
            "login_headless": credentials.get("login_headless", False),
            "login_timeout": credentials.get("login_timeout", 180),
            "cookie_output": credentials.get("cookie_output", ""),
        },
        base_dir=cookie_base_dir(),
        env_file=backend_env_file_for_helpers(),
    )
    browser = str(settings.get("login_browser") or "chrome").strip().lower()
    if browser not in {"chrome", "chromium"}:
        raise RuntimeError(f"Unsupported IB Client Portal login browser: {browser}")

    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as expected
        from selenium.webdriver.support.ui import WebDriverWait
    except ModuleNotFoundError as exc:
        raise RuntimeError("Selenium is required for automatic IB Client Portal login") from exc

    headless = bool(settings.get("login_headless", False))
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-notifications")

    # A trading workspace can start many strategy units at once.  Keep a
    # single login flow in flight so an expired shared session does not open a
    # browser window per unit.  Waiters re-check the cookie file written by
    # the first successful flow before attempting another login.
    with _IB_WEB_LOGIN_LOCK:
        existing_cookies = session_helpers.current_cookie_payload(settings)
        if existing_cookies and session_helpers.cookies_are_authenticated(
            settings, existing_cookies
        ):
            cookies = existing_cookies
        else:
            driver = webdriver.Chrome(options=options)
            try:
                driver.get(_ib_web_login_url(base_url))
                wait = WebDriverWait(driver, max(10, min(int(timeout), 30)))
                if str(settings.get("login_mode") or "paper").strip().lower() == "paper":
                    paper_switch = wait.until(
                        expected.presence_of_element_located((By.ID, "toggle1"))
                    )
                    if not paper_switch.is_selected():
                        driver.execute_script("arguments[0].click();", paper_switch)
                wait.until(
                    expected.presence_of_element_located((By.ID, "xyz-field-username"))
                ).send_keys(username)
                wait.until(
                    expected.presence_of_element_located((By.ID, "xyz-field-password"))
                ).send_keys(password)
                wait.until(
                    expected.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
                ).click()
                cookies = _wait_for_browser_authenticated_session(
                    driver,
                    session_helpers,
                    base_url,
                    verify_ssl,
                    timeout,
                    float(settings.get("login_timeout") or 180),
                    headless,
                    str(settings.get("login_mode") or "paper"),
                )
            finally:
                driver.quit()

    cookie_output = str(settings.get("cookie_output") or "").strip()
    session_helpers.save_cookies_to_file(cookies, cookie_output)
    accounts = session_helpers.fetch_accounts(
        base_url,
        cookies,
        verify_ssl=verify_ssl,
        timeout=max(2, int(timeout)),
    )
    account_id = str(
        credentials.get("account_id") or ""
    ).strip() or session_helpers.pick_account_id(
        accounts,
        str(settings.get("login_mode") or "paper"),
    )
    return {
        "cookies": cookies,
        "cookie_output": cookie_output,
        "cookie_source": session_helpers.normalize_cookie_source(
            f"file:{cookie_output}",
            base_dir=settings.get("cookie_base_dir"),
        ),
        "account_id": account_id,
        "status_code": 200,
        "used_login": True,
    }


def bootstrap_ib_web_session(
    credentials: dict[str, Any],
    base_url: str,
    verify_ssl: bool,
    timeout: float,
    *,
    allow_interactive_login: bool,
    load_session_state: Callable[
        [dict[str, Any], str, bool, float],
        tuple[dict[str, Any], dict[str, str], bool, list[dict[str, Any]], str],
    ],
    import_session_helpers: Callable[[], tuple[Any, Any, Any]],
    load_env_values: Callable[[], dict[str, str]],
    backend_env_file_for_helpers: Callable[[], Path],
    cookie_base_dir: Callable[[], Path],
    logger,
) -> dict[str, Any] | None:
    has_cookie_config = bool(
        credentials.get("cookies")
        or credentials.get("cookie_source")
        or credentials.get("cookie_output")
    )
    has_login_credentials = bool(credentials.get("username") and credentials.get("password"))
    logger.info(
        "IB_WEB bootstrap: has_cookie_config=%s, has_login_credentials=%s, "
        "cookie_source_configured=%s, cookie_output_configured=%s",
        has_cookie_config,
        has_login_credentials,
        bool(credentials.get("cookie_source")),
        bool(credentials.get("cookie_output")),
    )
    if has_cookie_config:
        try:
            settings, cookies, authenticated, _, account_id = load_session_state(
                credentials,
                base_url,
                verify_ssl,
                timeout,
            )
        except Exception as exc:
            if not allow_interactive_login:
                raise RuntimeError(
                    "IB Web恢复失败: 本地会话已失效，请在页面中手动重新连接"
                ) from exc
            logger.warning(
                "IB_WEB bootstrap: failed to load existing session, falling back to login: %s: %s",
                type(exc).__name__,
                exc,
            )
        else:
            if authenticated:
                return {
                    "cookies": cookies,
                    "cookie_output": str(settings.get("cookie_output") or ""),
                    "cookie_source": str(settings.get("cookie_source") or ""),
                    "account_id": account_id or str(settings.get("account_id") or ""),
                    "status_code": 200,
                    "used_login": False,
                }
            if not allow_interactive_login:
                raise RuntimeError("IB Web恢复失败: 本地会话已失效，请在页面中手动重新连接")
            logger.info("IB_WEB bootstrap: cookies expired/invalid, will try login")
    if not allow_interactive_login:
        if credentials.get("access_token"):
            return None
        raise RuntimeError("IB Web恢复失败: 未找到有效会话，请在页面中手动重新连接")
    login_credentials = dict(credentials)
    if not has_login_credentials:
        try:
            _, ensure_authenticated_session, _ = import_session_helpers()
            env_values = load_env_values()
            env_file = backend_env_file_for_helpers()
            login_credentials.update(
                {
                    "username": env_values.get("IB_WEB_USERNAME", ""),
                    "password": env_values.get("IB_WEB_PASSWORD", ""),
                    "login_mode": env_values.get("IB_WEB_LOGIN_MODE", "paper"),
                    "login_browser": env_values.get("IB_WEB_LOGIN_BROWSER", "chrome"),
                    "login_headless": env_values.get("IB_WEB_LOGIN_HEADLESS", "false"),
                    "login_timeout": env_values.get("IB_WEB_LOGIN_TIMEOUT", "180"),
                    "cookie_source": env_values.get("IB_WEB_COOKIE_SOURCE", ""),
                    "cookie_output": env_values.get("IB_WEB_COOKIE_OUTPUT", ""),
                    "cookie_browser": env_values.get("IB_WEB_COOKIE_BROWSER", "chrome"),
                    "cookie_path": env_values.get("IB_WEB_COOKIE_PATH", "/sso"),
                }
            )
            return ensure_authenticated_session(
                overrides={
                    "base_url": base_url,
                    "account_id": credentials.get("account_id", ""),
                    "verify_ssl": verify_ssl,
                    "timeout": timeout,
                    "username": env_values.get("IB_WEB_USERNAME", ""),
                    "password": env_values.get("IB_WEB_PASSWORD", ""),
                    "login_mode": env_values.get("IB_WEB_LOGIN_MODE", "paper"),
                    "login_browser": env_values.get("IB_WEB_LOGIN_BROWSER", "chrome"),
                    "login_headless": env_values.get("IB_WEB_LOGIN_HEADLESS", "false"),
                    "login_timeout": env_values.get("IB_WEB_LOGIN_TIMEOUT", "180"),
                    "cookie_source": env_values.get("IB_WEB_COOKIE_SOURCE", ""),
                    "cookie_output": env_values.get("IB_WEB_COOKIE_OUTPUT", ""),
                    "cookie_browser": env_values.get("IB_WEB_COOKIE_BROWSER", "chrome"),
                    "cookie_path": env_values.get("IB_WEB_COOKIE_PATH", "/sso"),
                },
                base_dir=cookie_base_dir(),
                env_file=env_file,
            )
        except Exception as exc:
            logger.warning(
                "IB_WEB existing-session bootstrap failed; starting browser login: %s",
                type(exc).__name__,
            )
            return login_ib_web_session_with_browser(
                login_credentials,
                base_url,
                verify_ssl,
                timeout,
                cookie_base_dir=cookie_base_dir,
                backend_env_file_for_helpers=backend_env_file_for_helpers,
            )
    return login_ib_web_session_with_browser(
        login_credentials,
        base_url,
        verify_ssl,
        timeout,
        cookie_base_dir=cookie_base_dir,
        backend_env_file_for_helpers=backend_env_file_for_helpers,
    )


def build_ib_web_env_updates(
    credentials: dict[str, Any],
    base_url: str,
    verify_ssl: bool,
    timeout: float,
    session: dict[str, Any] | None,
    to_relative_path: Callable[[str], str],
) -> dict[str, str]:
    updates = {
        "IB_WEB_BASE_URL": base_url,
        "IB_WEB_VERIFY_SSL": "true" if verify_ssl else "false",
        "IB_WEB_TIMEOUT": str(timeout),
    }
    account_id = str(
        (session or {}).get("account_id") or credentials.get("account_id") or ""
    ).strip()
    if account_id:
        updates["IB_WEB_ACCOUNT_ID"] = account_id
    cookie_output_value = str((session or {}).get("cookie_output") or "").strip()
    if cookie_output_value:
        backend_relative_output = to_relative_path(cookie_output_value)
        updates["IB_WEB_COOKIE_OUTPUT"] = backend_relative_output
        updates["IB_WEB_COOKIE_SOURCE"] = f"file:{backend_relative_output}"
    elif credentials.get("cookie_output"):
        cookie_output = to_relative_path(str(credentials["cookie_output"]))
        updates["IB_WEB_COOKIE_OUTPUT"] = cookie_output
        updates["IB_WEB_COOKIE_SOURCE"] = f"file:{cookie_output}"
    elif credentials.get("cookie_source"):
        updates["IB_WEB_COOKIE_SOURCE"] = str(credentials["cookie_source"])
    for key in (
        "cookie_browser",
        "cookie_path",
        "username",
        "password",
        "login_mode",
        "login_browser",
    ):
        value = str(credentials.get(key) or "").strip()
        if value:
            updates[f"IB_WEB_{key.upper()}"] = value
    if credentials.get("login_headless") is not None:
        updates["IB_WEB_LOGIN_HEADLESS"] = (
            "true" if bool(credentials.get("login_headless")) else "false"
        )
    if credentials.get("login_timeout") not in {None, ""}:
        updates["IB_WEB_LOGIN_TIMEOUT"] = str(credentials.get("login_timeout"))
    return updates


def connect_ib_web_gateway(
    gateways: dict[str, dict[str, Any]],
    key: str,
    credentials: dict[str, Any],
    coerce_bool,
    coerce_float,
    import_gateway_runtime_classes,
    default_transport: str,
    logger,
    *,
    allow_interactive_login: bool,
    merge_credentials,
    normalize_base_url,
    ensure_clientportal_running,
    resolve_base_url,
    bootstrap_session,
    to_relative_path,
    persist_env_updates,
    build_env_updates,
    cookie_base_dir,
    should_manage_clientportal,
    resolve_transport,
    build_session_key,
    wait_for_runtime_ready,
) -> dict[str, Any]:
    credentials = merge_credentials(credentials)
    account_id = credentials.get("account_id", "")
    if not account_id:
        return {
            "gateway_key": key,
            "status": "error",
            "message": "Missing required field: account_id",
        }
    try:
        gateway_config_cls, gateway_runtime_cls = import_gateway_runtime_classes()
        source_credentials = credentials
        verify_ssl = coerce_bool(credentials.get("verify_ssl"), default=False)
        timeout = coerce_float(credentials.get("timeout"), default=10.0)
        base_url = normalize_base_url(credentials.get("base_url", "https://localhost:5000"))
        ensure_clientportal_running(base_url, logger)
        base_url = resolve_base_url(base_url, verify_ssl, timeout, logger)
        session = bootstrap_session(
            credentials,
            base_url,
            verify_ssl,
            timeout,
            allow_interactive_login=allow_interactive_login,
        )
        resolved_account_id = str((session or {}).get("account_id") or account_id).strip()
        source_credentials["account_id"] = resolved_account_id
        source_credentials["base_url"] = base_url
        credentials = dict(source_credentials)
        if session is not None:
            if session.get("cookie_output"):
                cookie_output = to_relative_path(str(session["cookie_output"]))
                credentials["cookie_output"] = cookie_output
                credentials["cookie_source"] = f"file:{cookie_output}"
                source_credentials["cookie_output"] = cookie_output
                source_credentials["cookie_source"] = f"file:{cookie_output}"
            if session.get("cookies"):
                credentials["cookies"] = session["cookies"]
            persist_env_updates(
                build_env_updates(
                    credentials,
                    base_url,
                    verify_ssl,
                    timeout,
                    session,
                )
            )
        kwargs = {
            "exchange_type": "IB_WEB",
            "asset_type": credentials.get("asset_type", "STK"),
            "account_id": resolved_account_id,
            "transport": resolve_transport(
                "IB_WEB", credentials.get("transport"), default_transport
            ),
            "base_url": base_url,
            "verify_ssl": verify_ssl,
            "timeout": timeout,
            "cookie_base_dir": str(cookie_base_dir()),
        }
        if should_manage_clientportal(base_url):
            kwargs["proxies"] = {}
            kwargs["async_proxy"] = ""
        if credentials.get("access_token"):
            kwargs["access_token"] = credentials["access_token"]
        if credentials.get("cookie_source"):
            kwargs["cookie_source"] = credentials["cookie_source"]
        if credentials.get("cookie_browser"):
            kwargs["cookie_browser"] = credentials["cookie_browser"]
        if credentials.get("cookie_path"):
            kwargs["cookie_path"] = credentials["cookie_path"]
        if credentials.get("cookies"):
            kwargs["cookies"] = credentials["cookies"]
        if credentials.get("username"):
            kwargs["username"] = credentials["username"]
        if credentials.get("password"):
            kwargs["password"] = credentials["password"]
        if credentials.get("login_mode"):
            kwargs["login_mode"] = credentials["login_mode"]
        if credentials.get("login_browser"):
            kwargs["login_browser"] = credentials["login_browser"]
        if credentials.get("login_headless") is not None:
            kwargs["login_headless"] = coerce_bool(
                credentials.get("login_headless"),
                default=False,
            )
        if credentials.get("login_timeout") not in {None, ""}:
            kwargs["login_timeout"] = coerce_float(
                credentials.get("login_timeout"),
                default=180.0,
            )
        if credentials.get("cookie_output"):
            kwargs["cookie_output"] = credentials["cookie_output"]
        config = gateway_config_cls.from_kwargs(**kwargs)
        runtime = gateway_runtime_cls(config, **kwargs)
        runtime.start_in_thread()
        ready_timeout = max(
            float(getattr(config, "startup_timeout_sec", 10.0) or 10.0) * 3.0 + 4.0, 8.0
        )
        wait_for_runtime_ready(runtime, logger, timeout_sec=ready_timeout)
        gateways[key] = {
            "config": config,
            "runtime": runtime,
            "instances": set(),
            "ref_count": 0,
            "lock": threading.Lock(),
            "manual": True,
            "exchange_type": "IB_WEB",
            "asset_type": kwargs["asset_type"],
            "account_id": resolved_account_id,
            "session_key": build_session_key(kwargs),
        }
        persist_env_updates(
            build_env_updates(
                credentials,
                base_url,
                verify_ssl,
                timeout,
                session,
            )
        )
        return {
            "gateway_key": key,
            "status": "connected",
            "message": "IB Web gateway started successfully",
        }
    except Exception as exc:
        if "runtime" in locals():
            try:
                runtime.stop()
            except Exception:
                logger.debug("Failed to stop IB Web runtime after connect error", exc_info=True)
        logger.exception("Failed to connect IB Web gateway %s", key)
        return {
            "gateway_key": key,
            "status": "error",
            "message": f"IB Web连接失败: {type(exc).__name__}: {exc}",
        }
