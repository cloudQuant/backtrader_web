import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.services.gateway_launch_builder import (
    build_gateway_session_key,
    build_gateway_session_key_from_runtime_kwargs,
    normalize_gateway_asset_type,
    resolve_gateway_transport,
)

_logger = logging.getLogger(__name__)
_ib_clientportal_lock = threading.Lock()
_ib_clientportal_process: subprocess.Popen | None = None


def _kill_process_on_port(port: int) -> None:
    """Kill any process holding *port* so ZMQ can rebind on retry.

    Uses psutil when available, falls back to lsof (macOS/Linux).
    """
    try:
        import psutil

        for conn in psutil.net_connections(kind="tcp"):
            status = str(getattr(conn, "status", "") or "").upper()
            if conn.laddr.port == port and conn.pid and status == "LISTEN":
                try:
                    proc = psutil.Process(conn.pid)
                    if proc.pid != os.getpid():
                        proc.kill()
                        _logger.warning("Killed process PID=%d holding port %d", proc.pid, port)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        return
    except ImportError:
        pass
    except Exception:
        pass
    # Fallback: lsof (macOS / Linux)
    try:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for pid_str in result.stdout.splitlines():
            pid_str = pid_str.strip()
            if pid_str and pid_str.isdigit():
                pid = int(pid_str)
                if pid != os.getpid():
                    try:
                        os.kill(pid, 9)
                        _logger.warning(
                            "Killed process PID=%d holding port %d (via lsof)", pid, port
                        )
                    except (OSError, ProcessLookupError):
                        pass
    except Exception:
        pass


def _extract_port_from_zmq_error(err_msg: str) -> int | None:
    """Parse port number from ZMQ 'Address already in use' error string."""
    m = re.search(r":(\d{4,5})['\"]?\s*\)", err_msg)
    if m:
        return int(m.group(1))
    return None


def _extract_err_msg_from_error_entry(entry: Any) -> str:
    """Extract a plain string error message from a health snapshot error entry.
    The entry may be a plain string or a dict with a 'message' key."""
    if isinstance(entry, dict):
        return str(entry.get("message") or entry).strip()
    return str(entry).strip()


def _is_address_in_use_error(err_msg: str) -> bool:
    normalized = str(err_msg or "").lower()
    return "address already in use" in normalized or "address in use" in normalized


def _find_recent_bind_error(snapshot: dict[str, Any] | None) -> str:
    if not isinstance(snapshot, dict):
        return ""
    recent_errors = snapshot.get("recent_errors")
    if not isinstance(recent_errors, list):
        return ""
    for item in reversed(recent_errors):
        message = _extract_err_msg_from_error_entry(item)
        if _is_address_in_use_error(message):
            return message
    return ""


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
    max_attempts: int = 3,
) -> tuple:
    """Create config+runtime and start, retrying with fresh ports on ZMQ
    bind failure.  Returns (config, runtime) on success."""
    last_exc = None
    for attempt in range(max_attempts):
        config = gateway_config_cls.from_kwargs(**kwargs)
        runtime = gateway_runtime_cls(config, **kwargs)
        runtime.start_in_thread()
        # Wait longer so ZMQ bind errors surface in the health snapshot
        time.sleep(1.0)
        health = getattr(runtime, "health", None)
        if health is not None:
            snap = health.snapshot() if callable(getattr(health, "snapshot", None)) else {}
            bind_err_msg = _find_recent_bind_error(snap)
            if snap.get("state") == "error" or bind_err_msg:
                errors = snap.get("recent_errors", [])
                raw_entry = errors[-1] if errors else None
                err_msg = bind_err_msg or (
                    _extract_err_msg_from_error_entry(raw_entry)
                    if raw_entry is not None
                    else "unknown"
                )
                if _is_address_in_use_error(err_msg) and attempt < max_attempts - 1:
                    _logger.warning(
                        "ZMQ bind failed (attempt %d/%d): %s — freeing port and retrying",
                        attempt + 1,
                        max_attempts,
                        err_msg,
                    )
                    port = _extract_port_from_zmq_error(err_msg)
                    if port:
                        _kill_process_on_port(port)
                    runtime_name = str(
                        getattr(config, "runtime_name", "") or "gateway-runtime"
                    ).strip()
                    kwargs["gateway_runtime_name"] = (
                        f"{runtime_name}-retry-{attempt + 2}-{int(time.time() * 1000)}"
                    )
                    _release_gateway_zmq_ports(runtime)
                    try:
                        runtime.stop()
                    except Exception:
                        pass
                    time.sleep(1.0)
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
    "HTTPS_PROXY",
    "https_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "ALL_PROXY",
    "all_proxy",
    "SOCKS_PROXY",
    "socks_proxy",
)

_proxy_checked = False
_detected_proxy_url = ""
_proxy_checked_lock = threading.Lock()


def _get_system_proxy_url() -> str:
    try:
        system_proxies = urllib.request.getproxies()
    except Exception:
        return ""
    if not isinstance(system_proxies, dict):
        return ""
    proxy_url = system_proxies.get("https") or system_proxies.get("http") or ""
    return str(proxy_url or "").strip()


def _detect_working_proxy(timeout: float = 3.0, force_recheck: bool = False) -> str:
    """Auto-detect a working HTTP(S) proxy from environment variables.

    Returns the proxy URL if reachable, or ``""`` if no proxy / proxy dead.
    When the proxy is unreachable the corresponding env vars are **removed**
    from ``os.environ`` so that downstream libraries (httpx, websocket-client)
    will not attempt to use a dead proxy.
    """
    global _proxy_checked, _detected_proxy_url
    with _proxy_checked_lock:
        if not force_recheck and _proxy_checked:
            return _detected_proxy_url

    # Collect candidate proxy URL from environment first, then fall back to
    # system proxy settings on macOS if env vars are not populated.
    proxy_url = ""
    proxy_source = ""
    for key in _PROXY_ENV_KEYS:
        val = os.environ.get(key, "")
        if val:
            proxy_url = val
            proxy_source = f"env:{key}"
            break

    if not proxy_url:
        proxy_url = _get_system_proxy_url()
        if proxy_url:
            proxy_source = "system"

    if not proxy_url:
        _logger.info("Proxy auto-detect: no env/system proxy found — using direct connection")
        with _proxy_checked_lock:
            _proxy_checked = True
            _detected_proxy_url = ""
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
            "Proxy auto-detect: %s (%s) is reachable — all traffic will use proxy",
            proxy_url,
            proxy_source or "unknown",
        )
    else:
        _logger.warning(
            "Proxy auto-detect: %s (%s) is NOT reachable — clearing proxy env vars, "
            "falling back to direct connection",
            proxy_url,
            proxy_source or "unknown",
        )
        for key in _PROXY_ENV_KEYS:
            os.environ.pop(key, None)
        proxy_url = ""

    with _proxy_checked_lock:
        _proxy_checked = True
        _detected_proxy_url = proxy_url
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


def _pick_explicit_or_setting(
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


def _merge_ib_web_default_credentials(credentials: dict[str, Any]) -> dict[str, Any]:
    from app.config import get_settings

    settings = get_settings()
    resolved = dict(credentials)
    login_mode = (
        str(
            _pick_explicit_or_setting(
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
        _pick_explicit_or_setting(
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
            _pick_explicit_or_setting(
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
        _pick_explicit_or_setting(
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
        _pick_explicit_or_setting(
            resolved.get("access_token"),
            settings,
            "IB_WEB_ACCESS_TOKEN",
            f"IB_{mode_prefix}_ACCESS_TOKEN",
            "IB_ACCESS_TOKEN",
            default="",
        )
        or ""
    ).strip()
    resolved["verify_ssl"] = _pick_explicit_or_setting(
        resolved.get("verify_ssl"),
        settings,
        "IB_WEB_VERIFY_SSL",
        f"IB_{mode_prefix}_VERIFY_SSL",
        "IB_VERIFY_SSL",
        default=False,
    )
    resolved["timeout"] = _pick_explicit_or_setting(
        resolved.get("timeout"),
        settings,
        "IB_WEB_TIMEOUT",
        f"IB_{mode_prefix}_TIMEOUT",
        "IB_TIMEOUT",
        default=10.0,
    )
    resolved["cookie_browser"] = (
        str(
            _pick_explicit_or_setting(
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
            _pick_explicit_or_setting(
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
        _pick_explicit_or_setting(
            resolved.get("cookie_output"),
            settings,
            "IB_WEB_COOKIE_OUTPUT",
            "IB_COOKIE_OUTPUT",
            default="",
        )
        or ""
    ).strip()
    resolved["cookie_source"] = str(
        _pick_explicit_or_setting(
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
        _pick_explicit_or_setting(
            resolved.get("username"),
            settings,
            "IB_WEB_USERNAME",
            "IB_USERNAME",
            default="",
        )
        or ""
    ).strip()
    resolved["password"] = str(
        _pick_explicit_or_setting(
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
            _pick_explicit_or_setting(
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
    resolved["login_headless"] = _pick_explicit_or_setting(
        resolved.get("login_headless"),
        settings,
        "IB_WEB_LOGIN_HEADLESS",
        "IB_LOGIN_HEADLESS",
        default=False,
    )
    resolved["login_timeout"] = _pick_explicit_or_setting(
        resolved.get("login_timeout"),
        settings,
        "IB_WEB_LOGIN_TIMEOUT",
        "IB_LOGIN_TIMEOUT",
        default=180,
    )
    return resolved


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
    bt_api_parts = resolved.parts
    if "bt_api_py" in bt_api_parts:
        bt_api_index = max(index for index, part in enumerate(bt_api_parts) if part == "bt_api_py")
        relative_parts = bt_api_parts[bt_api_index + 1 :]
        if relative_parts:
            return "/".join(relative_parts)
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
    account_id = (
        pick_account_id(accounts, str(settings.get("login_mode") or "paper")) if accounts else ""
    )
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
    allow_interactive_login: bool = True,
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
        try:
            settings, cookies, authenticated, _, account_id = _load_ib_web_session_state(
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
            _logger.warning(
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
            _logger.info("IB_WEB bootstrap: cookies expired/invalid, will try login")
        # Fall through to ensure_authenticated_session for browser login
    if not allow_interactive_login:
        if credentials.get("access_token"):
            return None
        raise RuntimeError("IB Web恢复失败: 未找到有效会话，请在页面中手动重新连接")
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
                type(exc).__name__,
                exc,
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
    try:
        _, _, upsert_env_file = _import_ib_web_session_helpers()
    except ModuleNotFoundError:
        _logger.warning(
            "IB_WEB env persistence skipped because bt_api_py session helpers are unavailable"
        )
        return
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
    explicit = (
        credentials.get("account_id")
        or credentials.get("user_id")
        or (credentials.get("login") if str(exchange_type).upper() == "MT5" else "")
        or ""
    )
    if explicit:
        return str(explicit)
    api_key = str(credentials.get("api_key") or "").strip()
    if api_key:
        suffix = api_key[-6:] if len(api_key) > 6 else api_key
        return f"{str(exchange_type).lower()}-{suffix}"
    return ""


def _gateway_state_value(state: dict[str, Any], key: str, default: Any = "") -> Any:
    if key in state:
        value = state.get(key)
        if value is not None and value != "":
            return value
    config = state.get("config")
    if isinstance(config, dict):
        return config.get(key, default)
    return getattr(config, key, default)


def _resolve_gateway_state_session_key(state: dict[str, Any]) -> str:
    session_key = str(state.get("session_key") or "").strip()
    if session_key:
        return session_key
    runtime_kwargs = {
        "exchange_type": _gateway_state_value(state, "exchange_type", ""),
        "asset_type": _gateway_state_value(state, "asset_type", ""),
        "account_id": _gateway_state_value(state, "account_id", ""),
        "broker_id": _gateway_state_value(state, "broker_id", ""),
        "td_address": _gateway_state_value(state, "td_address", ""),
        "md_address": _gateway_state_value(state, "md_address", ""),
        "base_url": _gateway_state_value(state, "base_url", ""),
        "login_mode": _gateway_state_value(state, "login_mode", ""),
        "testnet": _gateway_state_value(state, "testnet", None),
        "server": _gateway_state_value(state, "server", ""),
        "ws_uri": _gateway_state_value(state, "ws_uri", ""),
    }
    resolved = build_gateway_session_key_from_runtime_kwargs(runtime_kwargs)
    if resolved:
        state["session_key"] = resolved
    return resolved


def _build_manual_gateway_session_key(exchange_type: str, credentials: dict[str, Any]) -> str:
    normalized_exchange_type = str(exchange_type or "").strip().upper()
    account_id = _resolve_manual_account_id(normalized_exchange_type, credentials)
    asset_type = normalize_gateway_asset_type(
        normalized_exchange_type,
        credentials.get("asset_type"),
    )
    broker_id = credentials.get("broker_id") or credentials.get("brokerid") or ""
    td_address = credentials.get("td_front") or credentials.get("td_address") or ""
    md_address = credentials.get("md_front") or credentials.get("md_address") or ""
    base_url = credentials.get("base_url") or ""
    login_mode = credentials.get("login_mode") or ""
    testnet = credentials.get("testnet")
    server = credentials.get("server") or ""
    ws_uri = credentials.get("ws_uri") or ""
    return build_gateway_session_key(
        normalized_exchange_type,
        account_id,
        asset_type=asset_type,
        broker_id=broker_id,
        td_address=td_address,
        md_address=md_address,
        base_url=base_url,
        login_mode=login_mode,
        testnet=testnet,
        server=server,
        ws_uri=ws_uri,
    )


def _find_gateway_key_by_session_key(
    gateways: dict[str, dict[str, Any]],
    session_key: str,
) -> str | None:
    if not session_key:
        return None
    for gateway_key, state in gateways.items():
        if not isinstance(state, dict):
            continue
        if _resolve_gateway_state_session_key(state) != session_key:
            continue
        if state.get("runtime") is None:
            continue
        return gateway_key
    return None


def _promote_gateway_state_to_manual(
    state: dict[str, Any],
    exchange_type: str,
    account_id: str,
    asset_type: str,
    session_key: str,
) -> None:
    state["manual"] = True
    state["exchange_type"] = exchange_type
    state["account_id"] = account_id
    if asset_type:
        state["asset_type"] = asset_type
    if session_key:
        state["session_key"] = session_key


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

    candidates = [requested] + [
        item for item in _CURRENT_CTP_SIMNOW_FRONTS if item is not requested
    ]
    status_messages: list[str] = []
    for candidate in candidates:
        td_host, td_port = _parse_tcp_front_endpoint(candidate["td_front"])
        md_host, md_port = _parse_tcp_front_endpoint(candidate["md_front"])
        td_reachable = bool(
            td_host and td_port and _is_tcp_endpoint_reachable(td_host, td_port, timeout=1.0)
        )
        md_reachable = bool(
            md_host and md_port and _is_tcp_endpoint_reachable(md_host, md_port, timeout=1.0)
        )
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

    from app.services.ctp_tunnel import is_proxy_tunnel_needed

    if is_proxy_tunnel_needed():
        logger.warning(
            "All current CTP SimNow fronts failed raw TCP reachability checks; "
            "continuing with requested front because proxy tunnel fallback is available: %s",
            "; ".join(status_messages),
        )
        return requested["td_front"], requested["md_front"]

    raise ConnectionError("CTP SimNow当前三组前置均不可达: " + "; ".join(status_messages))


def _is_macos_tun_proxy_active() -> bool:
    """Detect if macOS has an active TUN transparent proxy (Clash/Surge/V2Ray etc.)."""
    if sys.platform != "darwin":
        return False
    try:
        ifconfig = subprocess.run(
            ["ifconfig"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        utun_count = ifconfig.stdout.count("utun")
        if utun_count < 5:
            return False
        scutil = subprocess.run(
            ["scutil", "--proxy"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return "HTTPEnable : 1" in scutil.stdout or "SOCKSEnable : 1" in scutil.stdout
    except Exception:
        return False


def _get_macos_default_gateway() -> tuple[str, str] | tuple[None, None]:
    """Return (gateway_ip, interface) for the default route on macOS."""
    try:
        result = subprocess.run(
            ["route", "-n", "get", "default"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        gateway = interface = None
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("gateway:"):
                gateway = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("interface:"):
                interface = stripped.split(":", 1)[1].strip()
        return gateway, interface
    except Exception:
        return None, None


def _check_route_goes_through_tun(ip: str) -> bool:
    """Check if a specific IP is routed through a TUN interface (proxy)."""
    try:
        result = subprocess.run(
            ["route", "-n", "get", ip],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("interface:"):
                iface = stripped.split(":", 1)[1].strip()
                return iface.startswith("utun")
    except Exception:
        pass
    return False


def _has_host_route(ip: str, expected_iface: str) -> bool:
    """Check if a host-specific route already exists for *ip* through *expected_iface*."""
    try:
        r = subprocess.run(
            ["route", "-n", "get", ip],
            capture_output=True,
            text=True,
            timeout=5,
        )
        iface = None
        is_host = False
        for line in r.stdout.splitlines():
            s = line.strip()
            if s.startswith("interface:"):
                iface = s.split(":", 1)[1].strip()
            if s.startswith("destination:") and ip in s:
                is_host = True
        return is_host and iface == expected_iface
    except Exception:
        return False


def _add_direct_route_for_ip(ip: str, gateway: str, interface: str, logger) -> bool:
    """Add a host route so *ip* bypasses TUN and goes through the physical gateway.

    Tries in order:
      1. Check if a matching host route already exists
      2. ``sudo -n`` (no password prompt, works if user recently used sudo)
      3. ``osascript`` to prompt admin password via macOS GUI dialog
      4. Plain ``route add`` (usually fails without root)

    Returns True if the route is confirmed usable.
    """
    if _has_host_route(ip, interface):
        logger.debug("Host route for %s via %s already exists", ip, interface)
        return True

    strategies = [
        ["sudo", "-n", "route", "-n", "add", "-host", ip, gateway],
        [
            "osascript",
            "-e",
            f'do shell script "route -n add -host {ip} {gateway}" with administrator privileges',
        ],
        ["route", "-n", "add", "-host", ip, gateway],
    ]
    for cmd in strategies:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            output = (r.stdout or "") + (r.stderr or "")
            if r.returncode == 0 or "already in table" in output.lower():
                logger.info("Added direct route for %s via %s", ip, gateway)
                return True
        except Exception:
            continue
    return False


def _extract_ips_from_fronts(*fronts: str) -> list[str]:
    """Extract unique IP addresses from CTP front address strings like tcp://1.2.3.4:1234."""
    seen: set[str] = set()
    result: list[str] = []
    for front in fronts:
        host, _ = _parse_tcp_front_endpoint(front)
        if host and host not in seen and not host.startswith("127."):
            try:
                socket.inet_aton(host)
                seen.add(host)
                result.append(host)
            except OSError:
                pass
    return result


def _add_ips_to_proxy_bypass_file(ips: list[str], logger) -> bool:
    """Add IPs to proxy app's user-defined direct/local bypass list.

    Supports ViewTurbo (user_local.txt) and similar proxy apps.
    Returns True if any IPs were successfully added.
    """
    home = os.path.expanduser("~")
    bypass_files = [
        os.path.join(home, "Library", "Application Support", "ViewTurbo", "user_local.txt"),
        os.path.join(home, "Library", "Application Support", "Clash Verge", "user_local.txt"),
    ]

    for fpath in bypass_files:
        if not os.path.isfile(fpath):
            continue
        try:
            existing = set()
            with open(fpath, encoding="utf-8") as fh:
                for line in fh:
                    stripped = line.strip()
                    if stripped:
                        existing.add(stripped)

            to_add = [ip for ip in ips if ip not in existing]
            if not to_add:
                logger.debug("CTP IPs already in %s", fpath)
                return True

            with open(fpath, "a", encoding="utf-8") as fh:
                for ip in to_add:
                    fh.write(f"{ip}\n")
            logger.info("已将CTP服务器IP写入代理直连列表 %s: %s", fpath, to_add)
            return True
        except Exception as exc:
            logger.debug("Failed to update %s: %s", fpath, exc)
    return False


def _find_clash_external_controller() -> tuple[str, str] | tuple[None, None]:
    """Find Clash external controller (host:port) and secret from config files.

    Searches common Clash Verge / Clash Meta / mihomo config locations.
    Returns (base_url, secret) or (None, None).
    """
    home = os.path.expanduser("~")
    config_dirs = [
        os.path.join(home, ".config", "clash"),
        os.path.join(home, ".config", "mihomo"),
    ]
    app_support = os.path.join(home, "Library", "Application Support")
    try:
        for entry in os.listdir(app_support):
            if "clash" in entry.lower() or "mihomo" in entry.lower():
                config_dirs.append(os.path.join(app_support, entry))
    except OSError:
        pass

    for d in config_dirs:
        for fname in ("config.yaml", "verge.yaml", "clash.yaml"):
            fpath = os.path.join(d, fname)
            if not os.path.isfile(fpath):
                continue
            try:
                with open(fpath, encoding="utf-8") as fh:
                    content = fh.read(16384)
                port = secret = None
                for line in content.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("external-controller:"):
                        port = stripped.split(":", 2)[-1].strip().strip("'\"")
                    elif stripped.startswith("secret:"):
                        secret = stripped.split(":", 1)[1].strip().strip("'\"")
                if port:
                    host_port = port if ":" in port else f"127.0.0.1:{port}"
                    return f"http://{host_port}", secret or ""
            except Exception:
                continue

    for port in (9090, 9097, 19090):
        try:
            import urllib.request

            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/version",
                headers={"User-Agent": "backtrader-web"},
            )
            resp = urllib.request.urlopen(req, timeout=2)
            if resp.status == 200:
                return f"http://127.0.0.1:{port}", ""
        except Exception:
            continue
    return None, None


def _clash_api_add_direct_rules(ips: list[str], logger) -> bool:
    """Try to add DIRECT rules for IPs via Clash external controller API."""
    base_url, secret = _find_clash_external_controller()
    if not base_url:
        return False

    import json as _json
    import urllib.request

    headers = {"Content-Type": "application/json", "User-Agent": "backtrader-web"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"

    for ip in ips:
        payload = _json.dumps({"payload": f"IP-CIDR,{ip}/32,DIRECT,no-resolve"}).encode()
        try:
            req = urllib.request.Request(
                f"{base_url}/rules/prepend",
                data=payload,
                headers=headers,
                method="POST",
            )
            urllib.request.urlopen(req, timeout=3)
            logger.info("Clash API: added DIRECT rule for %s", ip)
        except Exception:
            try:
                req = urllib.request.Request(
                    f"{base_url}/rules",
                    data=_json.dumps(
                        {
                            "prepend": [f"IP-CIDR,{ip}/32,DIRECT,no-resolve"],
                        }
                    ).encode(),
                    headers=headers,
                    method="PATCH",
                )
                urllib.request.urlopen(req, timeout=3)
                logger.info("Clash API (PATCH): added DIRECT rule for %s", ip)
            except Exception as exc:
                logger.debug("Clash API rule add failed for %s: %s", ip, exc)
                return False
    return True


def _ensure_ctp_direct_routes(td_front: str, md_front: str, logger) -> None:
    """If a TUN proxy is active, bypass it for CTP server IPs.

    CTP uses native C++ TCP sockets which get intercepted by transparent proxies
    (Clash TUN / Surge Enhanced Mode / V2Ray tun2socks). The proxy cannot parse
    the CTP binary protocol and drops connections.

    Strategy (tried in order):
      1. Clash external controller API — add DIRECT rules
      2. Explicit host routes via ``route add`` (needs sudo)
      3. Log manual instructions as fallback
    """
    if not _is_macos_tun_proxy_active():
        return

    ips = _extract_ips_from_fronts(td_front, md_front)
    if not ips:
        return

    logger.info("检测到TUN代理(Clash/Surge/ViewTurbo等)，尝试为CTP服务器IP绕过代理: %s", ips)

    if _add_ips_to_proxy_bypass_file(ips, logger):
        logger.info("已将CTP IP写入代理直连列表（可能需要重启代理软件生效）")

    if _clash_api_add_direct_rules(ips, logger):
        logger.info("已通过Clash API为CTP添加DIRECT规则")
        return

    gateway, interface = _get_macos_default_gateway()
    if not gateway:
        logger.warning(
            "检测到TUN代理拦截CTP流量，但无法获取默认网关。请手动运行: %s",
            " && ".join(f"sudo route add -host {ip} <网关IP>" for ip in ips),
        )
        return

    logger.info("Clash API不可用，尝试添加直连路由: %s -> %s (%s)", ips, gateway, interface)
    failed_ips: list[str] = []
    for ip in ips:
        if not _add_direct_route_for_ip(ip, gateway, interface or "en0", logger):
            failed_ips.append(ip)

    if failed_ips:
        cmds = " && ".join(f"sudo route add -host {ip} {gateway}" for ip in failed_ips)
        logger.warning(
            "无法自动添加CTP直连路由(需要sudo权限)。请手动执行: %s",
            cmds,
        )


def _maybe_tunnel_ctp_fronts(td_front: str, md_front: str, logger) -> tuple[str, str]:
    """If a system HTTP proxy is active, create HTTP CONNECT tunnels for CTP fronts.

    CTP uses native C++ TCP sockets that get intercepted by transparent proxies
    which can't parse CTP's binary protocol. By tunneling through HTTP CONNECT,
    the proxy establishes a transparent byte pipe that CTP can use normally.

    Returns (td_front, md_front) — possibly rewritten to ``tcp://127.0.0.1:<port>``.
    """
    from app.services.ctp_tunnel import ensure_tunnel, is_proxy_tunnel_needed

    if not is_proxy_tunnel_needed():
        return td_front, md_front

    logger.info("检测到系统HTTP代理，创建HTTP CONNECT隧道以绕过CTP流量拦截")

    def _rewrite(front: str) -> str:
        host, port = _parse_tcp_front_endpoint(front)
        if not host or not port:
            return front
        try:
            local_port = ensure_tunnel(host, port)
            rewritten = f"tcp://127.0.0.1:{local_port}"
            logger.info(
                "CTP隧道: %s -> CONNECT %s:%d via proxy -> %s",
                rewritten,
                host,
                port,
                front,
            )
            return rewritten
        except Exception as exc:
            logger.warning("创建CTP隧道失败(%s:%d): %s, 使用原始地址", host, port, exc)
            return front

    return _rewrite(td_front), _rewrite(md_front)


def _detect_system_tun_proxy() -> str | None:
    """Return a user-facing hint if TUN proxy is active, else None."""
    if _is_macos_tun_proxy_active():
        return (
            "检测到系统代理(Clash/Surge/ViewTurbo等)可能拦截了CTP的TCP流量。"
            "CTP使用原生TCP连接，透明代理无法解析其二进制协议。"
            "系统已自动通过HTTP CONNECT隧道转发CTP流量。"
            "如仍无法连接，请检查代理软件是否允许CONNECT方法。"
        )
    return None


def _format_ctp_connect_error(exc: Exception) -> str:
    message = str(exc).strip()
    lowered = message.lower()
    if "ctp native api" in lowered or "git lfs pointer detected" in lowered:
        return f"CTP连接失败: 底层CTP原生SDK不可用，请在 bt_api_py 仓库执行 git lfs pull 恢复 framework 二进制后重试。原始错误: {type(exc).__name__}: {message}"
    if "simnow当前三组前置均不可达" in message.lower() or "simnow当前三组前置均不可达" in message:
        return f"CTP连接失败: {message}"
    proxy_hint = ""
    if (
        "market not ready" in lowered
        or "trade not ready" in lowered
        or "not ready" in lowered
        or "timeout" in lowered
    ):
        hint = _detect_system_tun_proxy()
        if hint:
            proxy_hint = f" 提示: {hint} 可运行: sudo bash scripts/setup_ctp_proxy_bypass.sh"
    return f"CTP连接失败: {type(exc).__name__}: {message}{proxy_hint}"


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
                    message = (
                        _extract_runtime_connect_error(snapshot)
                        or "gateway adapter failed to connect"
                    )
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
    allow_interactive_login: bool = True,
) -> dict[str, Any]:
    # One-time proxy health check: clears dead proxy env vars so ALL
    # downstream libraries (httpx, websocket-client, …) use direct connections.
    _detect_working_proxy()

    exchange_type = normalize_exchange_type(exchange_type)
    account_id = _resolve_manual_account_id(exchange_type, credentials)
    asset_type = normalize_gateway_asset_type(exchange_type, credentials.get("asset_type"))
    session_key = _build_manual_gateway_session_key(exchange_type, credentials)
    existing_key = _find_gateway_key_by_session_key(gateways, session_key)
    if existing_key:
        state = gateways.get(existing_key)
        if state is None:
            state = {}
        _promote_gateway_state_to_manual(state, exchange_type, account_id, asset_type, session_key)
        return {
            "gateway_key": existing_key,
            "status": "connected",
            "message": "Gateway already active",
        }
    key = f"manual:{exchange_type}:{account_id}"
    if key in gateways:
        state = gateways.get(key)
        if state is None:
            state = {}
        _promote_gateway_state_to_manual(state, exchange_type, account_id, asset_type, session_key)
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
            allow_interactive_login=allow_interactive_login,
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
        "asset_type": asset_type,
        "account_id": account_id,
        "session_key": session_key,
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
        _ensure_ctp_direct_routes(resolved_td_front, resolved_md_front, logger)
        gateway_config_cls, gateway_runtime_cls = import_gateway_runtime_classes()
        startup_timeout_sec = _resolve_startup_timeout_sec(credentials, default=20.0)
        base_kwargs = {
            "exchange_type": "CTP",
            "asset_type": "FUTURE",
            "account_id": credentials.get("account_id") or credentials["user_id"],
            "transport": resolve_gateway_transport(
                "CTP", credentials.get("transport"), default_transport
            ),
            "broker_id": credentials["broker_id"],
            "investor_id": credentials["user_id"],
            "user_id": credentials["user_id"],
            "password": credentials["password"],
            "app_id": credentials.get("app_id", "simnow_client_test"),
            "auth_code": credentials.get("auth_code", "0000000000000000"),
            "startup_timeout_sec": startup_timeout_sec,
            "gateway_startup_timeout_sec": startup_timeout_sec,
        }
        ready_timeout = max(startup_timeout_sec * 3.0 + 4.0, 8.0)
        runtime = None

        def _connect_with_fronts(td_front: str, md_front: str) -> tuple[Any, Any, dict[str, Any]]:
            nonlocal runtime
            attempt_kwargs = dict(base_kwargs)
            attempt_kwargs["td_address"] = td_front
            attempt_kwargs["md_address"] = md_front
            config, runtime = _start_runtime_with_retry(
                gateway_config_cls,
                gateway_runtime_cls,
                attempt_kwargs,
            )
            _wait_for_runtime_ready(runtime, logger, timeout_sec=ready_timeout)
            return config, runtime, attempt_kwargs

        try:
            config, runtime, kwargs = _connect_with_fronts(resolved_td_front, resolved_md_front)
        except Exception as direct_exc:
            if runtime is not None:
                try:
                    runtime.stop()
                except Exception:
                    logger.debug(
                        "Failed to stop direct CTP runtime after connect error", exc_info=True
                    )
                _release_gateway_zmq_ports(runtime)
                runtime = None
            from app.services.ctp_tunnel import is_proxy_tunnel_needed

            if not is_proxy_tunnel_needed():
                raise
            tunneled_td, tunneled_md = _maybe_tunnel_ctp_fronts(
                resolved_td_front,
                resolved_md_front,
                logger,
            )
            if tunneled_td == resolved_td_front and tunneled_md == resolved_md_front:
                raise
            logger.warning(
                "CTP直连启动失败，回退到HTTP CONNECT隧道: %s: %s",
                type(direct_exc).__name__,
                direct_exc,
            )
            config, runtime, kwargs = _connect_with_fronts(tunneled_td, tunneled_md)
        gateways[key] = {
            "config": config,
            "runtime": runtime,
            "instances": set(),
            "ref_count": 0,
            "lock": threading.Lock(),
            "manual": True,
            "exchange_type": "CTP",
            "asset_type": kwargs["asset_type"],
            "account_id": kwargs["account_id"],
            "session_key": build_gateway_session_key_from_runtime_kwargs(kwargs),
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
            _release_gateway_zmq_ports(runtime)
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
    allow_interactive_login: bool = True,
) -> dict[str, Any]:
    credentials = _merge_ib_web_default_credentials(credentials)
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
        base_url = _normalize_ib_web_base_url(credentials.get("base_url", "https://localhost:5000"))
        _ensure_ib_clientportal_running(base_url, logger)
        base_url = _resolve_ib_web_base_url(base_url, verify_ssl, timeout, logger)
        session = _bootstrap_ib_web_session(
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
            "transport": resolve_gateway_transport(
                "IB_WEB", credentials.get("transport"), default_transport
            ),
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
        ready_timeout = max(
            float(getattr(config, "startup_timeout_sec", 10.0) or 10.0) * 3.0 + 4.0, 8.0
        )
        _wait_for_runtime_ready(runtime, logger, timeout_sec=ready_timeout)
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
            "session_key": build_gateway_session_key_from_runtime_kwargs(kwargs),
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
        gateway_proxies = _get_gateway_proxies_kwarg()
        ws_proxy_kwargs = _get_gateway_ws_proxy_kwargs()
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
            gateway_config_cls,
            gateway_runtime_cls,
            kwargs,
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
            "session_key": build_gateway_session_key_from_runtime_kwargs(kwargs),
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
        gateway_proxies = _get_gateway_proxies_kwarg()
        ws_proxy_kwargs = _get_gateway_ws_proxy_kwargs()
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
            gateway_config_cls,
            gateway_runtime_cls,
            kwargs,
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
            "session_key": build_gateway_session_key_from_runtime_kwargs(kwargs),
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
            gateway_config_cls,
            gateway_runtime_cls,
            kwargs,
        )
        gateways[key] = {
            "config": config,
            "runtime": runtime,
            "instances": set(),
            "ref_count": 0,
            "lock": threading.Lock(),
            "manual": True,
            "exchange_type": "MT5",
            "asset_type": kwargs["asset_type"],
            "account_id": account_id,
            "session_key": build_gateway_session_key_from_runtime_kwargs(kwargs),
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


def disconnect_gateway(gateways: dict[str, dict[str, Any]], gateway_key: str) -> dict[str, Any]:
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
    active_instances = state.get("instances", set()) or set()
    ref_count = max(int(state.get("ref_count", 0) or 0), len(active_instances))
    if ref_count > 0:
        return {
            "gateway_key": gateway_key,
            "status": "error",
            "message": "Gateway is currently in use by strategy instances",
        }
    runtime = state.get("runtime")
    if runtime is not None:
        try:
            runtime.stop()
        except Exception as e:
            _logger.warning(f"Error stopping gateway {gateway_key}: {e}")
        # Wait for the runtime thread to fully exit so ZMQ ports are released
        try:
            thread = getattr(runtime, "thread", None)
            if thread is not None and thread.is_alive():
                thread.join(timeout=5.0)
        except Exception as e:
            _logger.warning(f"Error joining gateway thread {gateway_key}: {e}")
        # Clear bt_api_py port caches so reconnect can reuse the ports
        try:
            _release_gateway_zmq_ports(runtime)
        except Exception as e:
            _logger.warning(f"Error releasing gateway ports {gateway_key}: {e}")
    gateways.pop(gateway_key, None)
    return {
        "gateway_key": gateway_key,
        "status": "disconnected",
        "message": "Gateway disconnected",
    }
