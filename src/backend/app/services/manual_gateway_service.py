import logging
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_logger = logging.getLogger(__name__)
_ib_clientportal_lock = threading.Lock()
_ib_clientportal_process: subprocess.Popen | None = None


def _release_gateway_zmq_ports(runtime) -> None:
    """Clear bt_api_py TCP port caches for a stopped runtime so reconnect
    can reuse or reallocate the same ports without 'Address in use' errors."""
    try:
        from bt_api_py.gateway.config import (
            _TCP_PORT_ASSIGNMENTS,
            _TCP_RESERVED_BASE_PORTS,
        )
    except ImportError:
        return
    config = getattr(runtime, "config", None)
    if config is None:
        return
    # Remove the cached port assignment for this runtime name
    runtime_name = getattr(config, "runtime_name", "")
    if runtime_name:
        base_port = _TCP_PORT_ASSIGNMENTS.pop(runtime_name, None)
        if base_port is not None:
            _TCP_RESERVED_BASE_PORTS.discard(base_port)
    # Also try the seed_input key used internally
    for key in list(_TCP_PORT_ASSIGNMENTS):
        port = _TCP_PORT_ASSIGNMENTS[key]
        cmd_ep = getattr(config, "command_endpoint", "")
        if cmd_ep and str(port) in cmd_ep:
            _TCP_PORT_ASSIGNMENTS.pop(key, None)
            _TCP_RESERVED_BASE_PORTS.discard(port)


def _start_runtime_with_retry(
    gateway_config_cls,
    gateway_runtime_cls,
    kwargs: dict[str, Any],
    max_attempts: int = 2,
) -> tuple:
    """Create config+runtime and start, retrying with fresh ports on ZMQ
    bind failure.  Returns (config, runtime) on success."""
    last_exc = None
    for attempt in range(max_attempts):
        config = gateway_config_cls.from_kwargs(**kwargs)
        runtime = gateway_runtime_cls(config, **kwargs)
        runtime.start_in_thread()
        # Check if start actually bound the sockets (health not in ERROR)
        time.sleep(0.3)
        health = getattr(runtime, "health", None)
        if health is not None:
            snap = health.snapshot() if callable(getattr(health, "snapshot", None)) else {}
            if snap.get("state") == "error":
                errors = snap.get("recent_errors", [])
                err_msg = str(errors[-1]) if errors else "unknown"
                if "Address in use" in err_msg and attempt < max_attempts - 1:
                    _logger.warning(
                        "ZMQ bind failed (attempt %d/%d): %s — retrying with fresh ports",
                        attempt + 1, max_attempts, err_msg,
                    )
                    _release_gateway_zmq_ports(runtime)
                    try:
                        runtime.stop()
                    except Exception:
                        pass
                    time.sleep(0.5)
                    last_exc = RuntimeError(err_msg)
                    continue
                raise RuntimeError(err_msg)
        return config, runtime
    raise last_exc or RuntimeError("Failed to start gateway runtime")


# ---------------------------------------------------------------------------
# Proxy auto-detection for exchange gateways (Binance / OKX / MT5)
# ---------------------------------------------------------------------------
# The .env file may contain HTTPS_PROXY / HTTP_PROXY pointing to a local
# proxy (e.g. Clash, V2Ray).  If that proxy is not running, ALL network
# libraries (httpx, websocket-client, requests …) that honour these env vars
# will fail with WinError 10061 "Connection refused".
#
# Strategy:
#   1. On first gateway connect, TCP-probe the proxy host:port.
#   2. Proxy alive  → keep env vars, return proxy URL for explicit use.
#   3. Proxy dead   → **remove** env vars from os.environ so every library
#      in this process falls back to direct connections automatically.
# ---------------------------------------------------------------------------

_PROXY_ENV_KEYS = (
    "HTTPS_PROXY", "https_proxy",
    "HTTP_PROXY", "http_proxy",
    "ALL_PROXY", "all_proxy",
    "SOCKS_PROXY", "socks_proxy",
)

_proxy_checked = False
_proxy_checked_lock = threading.Lock()


def _detect_working_proxy(timeout: float = 3.0, force_recheck: bool = False) -> str:
    """Auto-detect a working HTTP(S) proxy from environment variables.

    Returns the proxy URL if reachable, or ``""`` if no proxy / proxy dead.
    When the proxy is unreachable the corresponding env vars are **removed**
    from ``os.environ`` so that downstream libraries (httpx, websocket-client)
    will not attempt to use a dead proxy.
    """
    global _proxy_checked
    with _proxy_checked_lock:
        if not force_recheck and _proxy_checked:
            # Already probed — env vars have been sanitised if needed.
            # Return whatever is (still) in the env.
            return os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or ""

    # Collect candidate proxy URL from environment
    proxy_url = ""
    for key in _PROXY_ENV_KEYS:
        val = os.environ.get(key, "")
        if val:
            proxy_url = val
            break

    if not proxy_url:
        _logger.info("Proxy auto-detect: no proxy env vars set — using direct connection")
        with _proxy_checked_lock:
            _proxy_checked = True
        return ""

    # Parse proxy URL to get host:port for TCP probe
    parsed = urlparse(proxy_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (1080 if "socks" in (parsed.scheme or "") else 8080)

    alive = False
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        alive = True
    except (OSError, TimeoutError):
        alive = False

    if alive:
        _logger.info(
            "Proxy auto-detect: %s is reachable — all traffic will use proxy",
            proxy_url,
        )
    else:
        _logger.warning(
            "Proxy auto-detect: %s is NOT reachable — clearing proxy env vars, "
            "falling back to direct connection",
            proxy_url,
        )
        for key in _PROXY_ENV_KEYS:
            os.environ.pop(key, None)
        proxy_url = ""

    with _proxy_checked_lock:
        _proxy_checked = True
    return proxy_url


def _get_gateway_proxies_kwarg() -> dict[str, str]:
    """Return a ``proxies`` dict suitable for bt_api_py ``Feed`` / ``HttpClient``.

    Also triggers the one-time proxy health check which may clear dead proxy
    env vars from ``os.environ``.

    - Proxy alive  → ``{"https": "<url>", "http": "<url>"}``
    - Proxy dead   → ``{"https": "", "http": ""}`` (disables ``trust_env``)
    """
    proxy = _detect_working_proxy()
    if proxy:
        return {"https": proxy, "http": proxy}
    return {"https": "", "http": ""}


def _get_gateway_ws_proxy_kwargs() -> dict[str, Any]:
    proxy = _detect_working_proxy()
    if not proxy:
        return {
            "http_proxy_host": "",
            "http_proxy_port": None,
            "async_proxy": "",
        }
    parsed = urlparse(proxy)
    return {
        "http_proxy_host": parsed.hostname or "",
        "http_proxy_port": parsed.port,
        "async_proxy": proxy,
    }


def _get_gateway_direct_proxies_kwarg() -> dict[str, str]:
    return {"https": "", "http": ""}


def _get_gateway_direct_ws_proxy_kwargs() -> dict[str, Any]:
    return {
        "http_proxy_host": "",
        "http_proxy_port": None,
        "async_proxy": "",
    }


# ---------------------------------------------------------------------------
# Proxy auto-detection for exchange gateways (Binance / OKX / MT5)
# ---------------------------------------------------------------------------

_CURRENT_CTP_SIMNOW_FRONTS = [
    {
        "name": "simnow_1",
        "td_front": "tcp://182.254.243.31:30001",
        "md_front": "tcp://182.254.243.31:30011",
    },
    {
        "name": "simnow_2",
        "td_front": "tcp://182.254.243.31:30002",
        "md_front": "tcp://182.254.243.31:30012",
    },
    {
        "name": "simnow_3",
        "td_front": "tcp://182.254.243.31:30003",
        "md_front": "tcp://182.254.243.31:30013",
    },
]


def _find_ib_clientportal_dir() -> Path | None:
    current = Path(__file__).resolve()
    jar_name = "ibgroup.web.core.iblink.router.clientportal.gw.jar"
    candidates: list[Path] = []
    for parent in current.parents:
        candidates.append(parent / "src" / "clientportal.gw")
    workspace_root = current.parents[4]
    candidates.append(workspace_root.parent / "tools" / "clientportal")
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "dist" / jar_name).is_file():
            return candidate
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def _backend_env_file() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _ib_web_cookie_base_dir() -> Path:
    bt_api_py_dir = _workspace_root().parent / "bt_api_py"
    if bt_api_py_dir.is_dir():
        return bt_api_py_dir
    return _backend_env_file().parent


def _to_backend_env_relative_path(path_value: str) -> str:
    candidate = str(path_value or "").strip()
    if not candidate:
        return ""
    resolved = Path(candidate)
    if not resolved.is_absolute():
        resolved = (_ib_web_cookie_base_dir() / resolved).resolve()
    base_dir = _ib_web_cookie_base_dir().resolve()
    try:
        return str(resolved.relative_to(base_dir)).replace("\\", "/")
    except ValueError:
        return str(resolved)


def _normalize_ib_web_base_url(base_url: str) -> str:
    raw = str(base_url or "https://localhost:5000").strip()
    parsed = urlparse(raw)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or parsed.path or "localhost:5000"
    path = parsed.path if parsed.netloc else ""
    normalized_path = path.rstrip("/")
    if normalized_path in {"", "/"}:
        normalized_path = "/v1/api"
    return parsed._replace(scheme=scheme, netloc=netloc, path=normalized_path).geturl()


def _swap_url_scheme(base_url: str, scheme: str) -> str:
    parsed = urlparse(base_url)
    return parsed._replace(scheme=scheme).geturl()


def _import_ib_web_session_helpers():
    workspace_dir = Path(__file__).resolve().parents[5]
    bt_api_py_dir = workspace_dir / "bt_api_py"
    if bt_api_py_dir.is_dir() and str(bt_api_py_dir) not in sys.path:
        sys.path.insert(0, str(bt_api_py_dir))
    from bt_api_py.functions.ib_web_session import (
        auth_status,
        ensure_authenticated_session,
        upsert_env_file,
    )

    return auth_status, ensure_authenticated_session, upsert_env_file


def _load_ib_web_session_state(
    credentials: dict[str, Any],
    base_url: str,
    verify_ssl: bool,
    timeout: float,
) -> tuple[dict[str, Any], dict[str, str], bool, list[dict[str, Any]], str]:
    workspace_dir = Path(__file__).resolve().parents[5]
    bt_api_py_dir = workspace_dir / "bt_api_py"
    if bt_api_py_dir.is_dir() and str(bt_api_py_dir) not in sys.path:
        sys.path.insert(0, str(bt_api_py_dir))
    from bt_api_py.functions.ib_web_session import (
        cookies_are_authenticated,
        current_cookie_payload,
        fetch_accounts,
        load_ib_web_settings,
        pick_account_id,
    )

    settings = load_ib_web_settings(
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
        base_dir=_ib_web_cookie_base_dir(),
        env_file=_backend_env_file(),
    )
    cookies = current_cookie_payload(settings)
    authenticated = cookies_are_authenticated(settings, cookies) if cookies else False
    accounts = (
        fetch_accounts(
            str(settings.get("base_url") or base_url),
            cookies,
            verify_ssl=bool(settings.get("verify_ssl", verify_ssl)),
            timeout=int(settings.get("timeout", timeout)),
        )
        if authenticated
        else []
    )
    account_id = pick_account_id(accounts, str(settings.get("login_mode") or "paper")) if accounts else ""
    return settings, cookies, authenticated, accounts, account_id


def _parse_base_url_endpoint(base_url: str) -> tuple[str, int]:
    parsed = urlparse(base_url or "https://localhost:5000")
    host = (parsed.hostname or "localhost").lower()
    if parsed.port is not None:
        return host, parsed.port
    if parsed.scheme == "http":
        return host, 80
    return host, 443


def _should_manage_ib_clientportal(base_url: str) -> bool:
    host, _ = _parse_base_url_endpoint(base_url)
    return host in {"localhost", "127.0.0.1"}


def _is_tcp_endpoint_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wait_for_tcp_endpoint(host: str, port: int, timeout_sec: float) -> bool:
    deadline = time.monotonic() + max(timeout_sec, 0.0)
    while time.monotonic() < deadline:
        if _is_tcp_endpoint_reachable(host, port, timeout=0.5):
            return True
        time.sleep(0.5)
    return _is_tcp_endpoint_reachable(host, port, timeout=0.5)


def _resolve_ib_web_base_url(
    base_url: str,
    verify_ssl: bool,
    timeout: float,
    logger,
) -> str:
    normalized = _normalize_ib_web_base_url(base_url)
    if not _should_manage_ib_clientportal(normalized):
        return normalized
    auth_status, _, _ = _import_ib_web_session_helpers()
    candidates = [normalized]
    alternate_scheme = "http" if urlparse(normalized).scheme == "https" else "https"
    alternate = _swap_url_scheme(normalized, alternate_scheme)
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


def _bootstrap_ib_web_session(
    credentials: dict[str, Any],
    base_url: str,
    verify_ssl: bool,
    timeout: float,
) -> dict[str, Any] | None:
    has_cookie_config = bool(
        credentials.get("cookies")
        or credentials.get("cookie_source")
        or credentials.get("cookie_output")
    )
    has_login_credentials = bool(credentials.get("username") and credentials.get("password"))
    _logger.info(
        "IB_WEB bootstrap: has_cookie_config=%s, has_login_credentials=%s, "
        "cookie_source=%r, cookie_output=%r, username=%r",
        has_cookie_config,
        has_login_credentials,
        credentials.get("cookie_source"),
        credentials.get("cookie_output"),
        credentials.get("username"),
    )
    if has_cookie_config:
        settings, cookies, authenticated, _, account_id = _load_ib_web_session_state(
            credentials,
            base_url,
            verify_ssl,
            timeout,
        )
        if authenticated:
            return {
                "cookies": cookies,
                "cookie_output": str(settings.get("cookie_output") or ""),
                "cookie_source": str(settings.get("cookie_source") or ""),
                "account_id": account_id or str(settings.get("account_id") or ""),
                "status_code": 200,
                "used_login": False,
            }
        _logger.info("IB_WEB bootstrap: cookies expired/invalid, will try login")
        # Fall through to ensure_authenticated_session for browser login
    _, ensure_authenticated_session, _ = _import_ib_web_session_helpers()
    if not has_login_credentials:
        # Fallback: auto-detect credentials and cookies from .env / default
        # cookie output path.  ensure_authenticated_session reads IB_WEB_*
        # env vars, checks existing cookies, and falls back to browser login.
        # NOTE: We must explicitly pass username/password in overrides because
        # Windows ``os.environ["USERNAME"]`` (the OS login name) shadows the
        # ``pick("username", ...)`` lookup before the .env ``IB_WEB_USERNAME``
        # value is reached.
        try:
            from dotenv import dotenv_values as _dotenv_values

            _env = _dotenv_values(_backend_env_file())
            return ensure_authenticated_session(
                overrides={
                    "base_url": base_url,
                    "account_id": credentials.get("account_id", ""),
                    "verify_ssl": verify_ssl,
                    "timeout": timeout,
                    "username": _env.get("IB_WEB_USERNAME", ""),
                    "password": _env.get("IB_WEB_PASSWORD", ""),
                    "login_mode": _env.get("IB_WEB_LOGIN_MODE", "paper"),
                    "login_browser": _env.get("IB_WEB_LOGIN_BROWSER", "chrome"),
                    "login_headless": _env.get("IB_WEB_LOGIN_HEADLESS", "false"),
                    "login_timeout": _env.get("IB_WEB_LOGIN_TIMEOUT", "180"),
                    "cookie_source": _env.get("IB_WEB_COOKIE_SOURCE", ""),
                    "cookie_output": _env.get("IB_WEB_COOKIE_OUTPUT", ""),
                    "cookie_browser": _env.get("IB_WEB_COOKIE_BROWSER", "chrome"),
                    "cookie_path": _env.get("IB_WEB_COOKIE_PATH", "/sso"),
                },
                base_dir=_ib_web_cookie_base_dir(),
                env_file=_backend_env_file(),
            )
        except Exception as exc:
            _logger.warning(
                "IB_WEB auto-session bootstrap failed: %s: %s",
                type(exc).__name__, exc,
            )
            return None
    return ensure_authenticated_session(
        overrides={
            "base_url": base_url,
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
            "login_timeout": 180
            if credentials.get("login_timeout") in {None, ""}
            else credentials.get("login_timeout"),
            "cookie_output": credentials.get("cookie_output", ""),
        },
        base_dir=_ib_web_cookie_base_dir(),
        env_file=_backend_env_file(),
    )


def _build_ib_web_env_updates(
    credentials: dict[str, Any],
    base_url: str,
    verify_ssl: bool,
    timeout: float,
    session: dict[str, Any] | None,
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
        backend_relative_output = _to_backend_env_relative_path(cookie_output_value)
        updates["IB_WEB_COOKIE_OUTPUT"] = backend_relative_output
        updates["IB_WEB_COOKIE_SOURCE"] = f"file:{backend_relative_output}"
    elif credentials.get("cookie_output"):
        cookie_output = _to_backend_env_relative_path(str(credentials["cookie_output"]))
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


def _persist_ib_web_env_updates(updates: dict[str, str]) -> None:
    filtered = {key: value for key, value in updates.items() if value not in {None, ""}}
    if not filtered:
        return
    _, _, upsert_env_file = _import_ib_web_session_helpers()
    env_file = _backend_env_file()
    upsert_env_file(env_file, filtered)
    from app import config as app_config

    app_config._settings = None


def _build_ib_clientportal_command(clientportal_dir: Path) -> list[str]:
    if sys.platform == "win32":
        return ["cmd", "/c", str(clientportal_dir / "bin" / "run.bat"), r"root\conf.yaml"]
    return ["/bin/bash", str(clientportal_dir / "bin" / "run.sh"), "root/conf.yaml"]


def _start_ib_clientportal_background(clientportal_dir: Path) -> subprocess.Popen:
    kwargs: dict[str, Any] = {
        "cwd": str(clientportal_dir),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "CREATE_NO_WINDOW", 0
        )
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(_build_ib_clientportal_command(clientportal_dir), **kwargs)


def _ensure_ib_clientportal_running(base_url: str, logger, startup_wait_sec: float = 8.0) -> None:
    global _ib_clientportal_process
    if not _should_manage_ib_clientportal(base_url):
        return
    host, port = _parse_base_url_endpoint(base_url)
    if _is_tcp_endpoint_reachable(host, port, timeout=1.0):
        return
    with _ib_clientportal_lock:
        if _is_tcp_endpoint_reachable(host, port, timeout=1.0):
            return
        clientportal_dir = _find_ib_clientportal_dir()
        if clientportal_dir is None:
            raise FileNotFoundError("IB clientportal directory not found at src/clientportal.gw")
        process = _ib_clientportal_process
        if process is None or process.poll() is not None:
            _ib_clientportal_process = _start_ib_clientportal_background(clientportal_dir)
            logger.info("Started IB clientportal in background from %s", clientportal_dir)
        if not _wait_for_tcp_endpoint(host, port, timeout_sec=startup_wait_sec):
            raise RuntimeError(f"IB clientportal did not become ready on {host}:{port}")


def _resolve_manual_account_id(exchange_type: str, credentials: dict[str, Any]) -> str:
    explicit = credentials.get("account_id") or credentials.get("user_id") or ""
    if explicit:
        return str(explicit)
    api_key = str(credentials.get("api_key") or "").strip()
    if api_key:
        suffix = api_key[-6:] if len(api_key) > 6 else api_key
        return f"{str(exchange_type).lower()}-{suffix}"
    return ""


def _extract_runtime_connect_error(snapshot: dict[str, Any] | None) -> str:
    if not isinstance(snapshot, dict):
        return ""
    recent_errors = snapshot.get("recent_errors")
    if not isinstance(recent_errors, list):
        return ""
    for item in reversed(recent_errors):
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "")
        message = str(item.get("message") or "").strip()
        if source == "adapter_connect" and message:
            return message
    for item in reversed(recent_errors):
        if not isinstance(item, dict):
            continue
        message = str(item.get("message") or "").strip()
        if message:
            return message
    return ""


def _resolve_startup_timeout_sec(credentials: dict[str, Any], default: float) -> float:
    candidate = credentials.get("startup_timeout_sec")
    if candidate in (None, ""):
        candidate = credentials.get("timeout")
    try:
        timeout = float(candidate)
    except (TypeError, ValueError):
        return default
    return timeout if timeout > 0 else default


def _parse_tcp_front_endpoint(front: str) -> tuple[str, int] | tuple[None, None]:
    parsed = urlparse(front or "")
    host = parsed.hostname
    port = parsed.port
    if not host or port is None:
        return None, None
    return host.lower(), port


def _resolve_ctp_front_pair(td_front: str, md_front: str, logger) -> tuple[str, str]:
    requested = next(
        (
            item
            for item in _CURRENT_CTP_SIMNOW_FRONTS
            if item["td_front"] == td_front and item["md_front"] == md_front
        ),
        None,
    )
    if requested is None:
        return td_front, md_front

    candidates = [requested] + [item for item in _CURRENT_CTP_SIMNOW_FRONTS if item is not requested]
    status_messages: list[str] = []
    for candidate in candidates:
        td_host, td_port = _parse_tcp_front_endpoint(candidate["td_front"])
        md_host, md_port = _parse_tcp_front_endpoint(candidate["md_front"])
        td_reachable = bool(td_host and td_port and _is_tcp_endpoint_reachable(td_host, td_port, timeout=1.0))
        md_reachable = bool(md_host and md_port and _is_tcp_endpoint_reachable(md_host, md_port, timeout=1.0))
        status_messages.append(
            f"{candidate['name']}(td={'ok' if td_reachable else 'down'}, md={'ok' if md_reachable else 'down'})"
        )
        if td_reachable and md_reachable:
            if candidate is not requested:
                logger.warning(
                    "Requested CTP SimNow front %s is unavailable, switching to %s",
                    requested["name"],
                    candidate["name"],
                )
            return candidate["td_front"], candidate["md_front"]

    raise ConnectionError("CTP SimNow当前三组前置均不可达: " + "; ".join(status_messages))


def _format_ctp_connect_error(exc: Exception) -> str:
    message = str(exc).strip()
    lowered = message.lower()
    if "ctp native api" in lowered or "git lfs pointer detected" in lowered:
        return f"CTP连接失败: 底层CTP原生SDK不可用，请在 bt_api_py 仓库执行 git lfs pull 恢复 framework 二进制后重试。原始错误: {type(exc).__name__}: {message}"
    if "simnow当前三组前置均不可达" in message.lower() or "simnow当前三组前置均不可达" in message:
        return f"CTP连接失败: {message}"
    return f"CTP连接失败: {type(exc).__name__}: {message}"


def _wait_for_runtime_ready(
    runtime,
    logger,
    timeout_sec: float,
    poll_interval_sec: float = 0.2,
) -> None:
    deadline = time.monotonic() + max(timeout_sec, 0.0)
    last_snapshot: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        adapter_connected = getattr(runtime, "_adapter_connected", None)
        if isinstance(adapter_connected, bool) and adapter_connected:
            return
        health = getattr(runtime, "health", None)
        if health is not None:
            try:
                snapshot = health.snapshot()
            except Exception:
                snapshot = None
            if isinstance(snapshot, dict):
                last_snapshot = snapshot
                if snapshot.get("market_connection") == "connected":
                    return
                if snapshot.get("state") == "error" or snapshot.get("market_connection") == "error":
                    message = _extract_runtime_connect_error(snapshot) or "gateway adapter failed to connect"
                    raise RuntimeError(message)
        time.sleep(poll_interval_sec)
    message = _extract_runtime_connect_error(last_snapshot)
    if message:
        raise RuntimeError(message)
    logger.warning("Gateway runtime did not become ready within %.1fs", timeout_sec)
    raise TimeoutError(f"gateway runtime not ready after {timeout_sec:.1f}s")


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
    # One-time proxy health check: clears dead proxy env vars so ALL
    # downstream libraries (httpx, websocket-client, …) use direct connections.
    _detect_working_proxy()

    exchange_type = normalize_exchange_type(exchange_type)
    account_id = _resolve_manual_account_id(exchange_type, credentials)
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
    if exchange_type == "BINANCE":
        return connect_binance_gateway(
            gateways,
            key,
            credentials,
            import_gateway_runtime_classes,
            default_transport,
            logger,
        )
    if exchange_type == "OKX":
        return connect_okx_gateway(
            gateways,
            key,
            credentials,
            import_gateway_runtime_classes,
            default_transport,
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
        "asset_type": credentials.get("asset_type") or "",
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
        resolved_td_front, resolved_md_front = _resolve_ctp_front_pair(
            str(credentials["td_front"]),
            str(credentials["md_front"]),
            logger,
        )
        gateway_config_cls, gateway_runtime_cls = import_gateway_runtime_classes()
        startup_timeout_sec = _resolve_startup_timeout_sec(credentials, default=20.0)
        kwargs = {
            "exchange_type": "CTP",
            "asset_type": "FUTURE",
            "account_id": credentials.get("account_id") or credentials["user_id"],
            "transport": default_transport,
            "md_address": resolved_md_front,
            "td_address": resolved_td_front,
            "broker_id": credentials["broker_id"],
            "investor_id": credentials["user_id"],
            "user_id": credentials["user_id"],
            "password": credentials["password"],
            "app_id": credentials.get("app_id", "simnow_client_test"),
            "auth_code": credentials.get("auth_code", "0000000000000000"),
            "startup_timeout_sec": startup_timeout_sec,
            "gateway_startup_timeout_sec": startup_timeout_sec,
        }
        config = gateway_config_cls.from_kwargs(**kwargs)
        runtime = gateway_runtime_cls(config, **kwargs)
        runtime.start_in_thread()
        ready_timeout = max(float(getattr(config, "startup_timeout_sec", 10.0) or 10.0) * 3.0 + 4.0, 8.0)
        _wait_for_runtime_ready(runtime, logger, timeout_sec=ready_timeout)
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
        if "runtime" in locals():
            try:
                runtime.stop()
            except Exception:
                logger.debug("Failed to stop CTP runtime after connect error", exc_info=True)
        logger.exception("Failed to connect CTP gateway %s", key)
        return {
            "gateway_key": key,
            "status": "error",
            "message": _format_ctp_connect_error(exc),
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
        source_credentials = credentials
        verify_ssl = coerce_bool(credentials.get("verify_ssl"), default=False)
        timeout = coerce_float(credentials.get("timeout"), default=10.0)
        base_url = _normalize_ib_web_base_url(
            credentials.get("base_url", "https://localhost:5000")
        )
        _ensure_ib_clientportal_running(base_url, logger)
        base_url = _resolve_ib_web_base_url(base_url, verify_ssl, timeout, logger)
        session = _bootstrap_ib_web_session(credentials, base_url, verify_ssl, timeout)
        resolved_account_id = str((session or {}).get("account_id") or account_id).strip()
        source_credentials["account_id"] = resolved_account_id
        source_credentials["base_url"] = base_url
        credentials = dict(source_credentials)
        if session is not None:
            if session.get("cookie_output"):
                cookie_output = _to_backend_env_relative_path(str(session["cookie_output"]))
                credentials["cookie_output"] = cookie_output
                credentials["cookie_source"] = f"file:{cookie_output}"
                source_credentials["cookie_output"] = cookie_output
                source_credentials["cookie_source"] = f"file:{cookie_output}"
            if session.get("cookies"):
                credentials["cookies"] = session["cookies"]
            _persist_ib_web_env_updates(
                _build_ib_web_env_updates(
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
            "transport": default_transport,
            "base_url": base_url,
            "verify_ssl": verify_ssl,
            "timeout": timeout,
            "cookie_base_dir": str(_ib_web_cookie_base_dir()),
        }
        if _should_manage_ib_clientportal(base_url):
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
        ready_timeout = max(float(getattr(config, "startup_timeout_sec", 10.0) or 10.0) * 3.0 + 4.0, 8.0)
        _wait_for_runtime_ready(runtime, logger, timeout_sec=ready_timeout)
        gateways[key] = {
            "config": config,
            "runtime": runtime,
            "instances": set(),
            "ref_count": 0,
            "lock": threading.Lock(),
            "manual": True,
            "exchange_type": "IB_WEB",
            "account_id": resolved_account_id,
        }
        _persist_ib_web_env_updates(
            _build_ib_web_env_updates(
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


def connect_binance_gateway(
    gateways: dict[str, dict[str, Any]],
    key: str,
    credentials: dict[str, Any],
    import_gateway_runtime_classes,
    default_transport: str,
    logger,
) -> dict[str, Any]:
    required = ["api_key", "secret_key"]
    missing = [field for field in required if not credentials.get(field)]
    if missing:
        return {
            "gateway_key": key,
            "status": "error",
            "message": f"Missing required fields: {', '.join(missing)}",
        }
    try:
        gateway_config_cls, gateway_runtime_cls = import_gateway_runtime_classes()
        account_id = _resolve_manual_account_id("BINANCE", credentials)
        gateway_proxies = _get_gateway_direct_proxies_kwarg()
        ws_proxy_kwargs = _get_gateway_direct_ws_proxy_kwargs()
        kwargs = {
            "exchange_type": "BINANCE",
            "asset_type": credentials.get("asset_type", "SWAP"),
            "account_id": account_id,
            "transport": default_transport,
            "api_key": credentials["api_key"],
            "secret_key": credentials["secret_key"],
            "testnet": bool(credentials.get("testnet", False)),
            "proxies": gateway_proxies,
            **ws_proxy_kwargs,
        }
        if credentials.get("base_url"):
            kwargs["base_url"] = credentials["base_url"]
        config, runtime = _start_runtime_with_retry(
            gateway_config_cls, gateway_runtime_cls, kwargs,
        )
        gateways[key] = {
            "config": config,
            "runtime": runtime,
            "instances": set(),
            "ref_count": 0,
            "lock": threading.Lock(),
            "manual": True,
            "exchange_type": "BINANCE",
            "asset_type": kwargs["asset_type"],
            "account_id": account_id,
        }
        return {
            "gateway_key": key,
            "status": "connected",
            "message": "Binance gateway started successfully",
        }
    except Exception as exc:
        logger.exception("Failed to connect Binance gateway %s", key)
        return {
            "gateway_key": key,
            "status": "error",
            "message": f"Binance连接失败: {type(exc).__name__}: {exc}",
        }


def connect_okx_gateway(
    gateways: dict[str, dict[str, Any]],
    key: str,
    credentials: dict[str, Any],
    import_gateway_runtime_classes,
    default_transport: str,
    logger,
) -> dict[str, Any]:
    required = ["api_key", "secret_key", "passphrase"]
    missing = [field for field in required if not credentials.get(field)]
    if missing:
        return {
            "gateway_key": key,
            "status": "error",
            "message": f"Missing required fields: {', '.join(missing)}",
        }
    try:
        gateway_config_cls, gateway_runtime_cls = import_gateway_runtime_classes()
        account_id = _resolve_manual_account_id("OKX", credentials)
        gateway_proxies = _get_gateway_direct_proxies_kwarg()
        ws_proxy_kwargs = _get_gateway_direct_ws_proxy_kwargs()
        kwargs = {
            "exchange_type": "OKX",
            "asset_type": credentials.get("asset_type", "SWAP"),
            "account_id": account_id,
            "transport": default_transport,
            "api_key": credentials["api_key"],
            "secret_key": credentials["secret_key"],
            "passphrase": credentials["passphrase"],
            "testnet": bool(credentials.get("testnet", False)),
            "proxies": gateway_proxies,
            **ws_proxy_kwargs,
        }
        if credentials.get("base_url"):
            kwargs["base_url"] = credentials["base_url"]
        config, runtime = _start_runtime_with_retry(
            gateway_config_cls, gateway_runtime_cls, kwargs,
        )
        gateways[key] = {
            "config": config,
            "runtime": runtime,
            "instances": set(),
            "ref_count": 0,
            "lock": threading.Lock(),
            "manual": True,
            "exchange_type": "OKX",
            "asset_type": kwargs["asset_type"],
            "account_id": account_id,
        }
        return {
            "gateway_key": key,
            "status": "connected",
            "message": "OKX gateway started successfully",
        }
    except Exception as exc:
        logger.exception("Failed to connect OKX gateway %s", key)
        return {
            "gateway_key": key,
            "status": "error",
            "message": f"OKX连接失败: {type(exc).__name__}: {exc}",
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
        config, runtime = _start_runtime_with_retry(
            gateway_config_cls, gateway_runtime_cls, kwargs,
        )
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
        # Wait for the runtime thread to fully exit so ZMQ ports are released
        thread = getattr(runtime, "thread", None)
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)
        # Clear bt_api_py port caches so reconnect can reuse the ports
        _release_gateway_zmq_ports(runtime)
    gateways.pop(gateway_key, None)
    return {
        "gateway_key": gateway_key,
        "status": "disconnected",
        "message": "Gateway disconnected",
    }
