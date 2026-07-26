"""Proxy discovery for AkShare data sources.

The general gateway proxy check only verifies that a configured proxy port is
open. AkShare Eastmoney calls need a stricter probe because the wrong local
port can be reachable but still fail the target API.
"""

from __future__ import annotations

import logging
import os
import re
import socket
import subprocess
import threading
import urllib.request
from collections.abc import Callable, Iterable
from pathlib import Path
from urllib.parse import urlparse

import requests

_logger = logging.getLogger(__name__)

_PROXY_ENV_KEYS = (
    "AKSHARE_PROXY",
    "AKSHARE_HTTP_PROXY",
    "AKSHARE_HTTPS_PROXY",
    "HTTPS_PROXY",
    "https_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "ALL_PROXY",
    "all_proxy",
    "SOCKS_PROXY",
    "socks_proxy",
    "PROXY_HOST",
)

_PROXY_PORT_ENV_KEYS = (
    "AKSHARE_PROXY_CANDIDATE_PORTS",
    "PROXY_PORT",
    "VPN_PORT",
    "VPN_PROXY_PORT",
    "HTTP_PROXY_PORT",
    "HTTPS_PROXY_PORT",
    "SOCKS_PROXY_PORT",
    "CLASH_PORT",
    "MIXED_PORT",
)

_DEFAULT_PROXY_PORTS = (
    15732,
    7890,
    7891,
    7892,
    7893,
    7897,
    1080,
    1087,
    10808,
    20170,
    20171,
    6152,
    6153,
    8080,
    8118,
    8888,
    9090,
)

_EASTMONEY_PROBE_URL = "https://push2.eastmoney.com/api/qt/clist/get"
_EASTMONEY_PROBE_PARAMS = {
    "pn": "1",
    "pz": "1",
    "po": "1",
    "np": "1",
    "ut": "bd1d9ddb04089700cf9c27f6f7426281",
    "fltt": "2",
    "invt": "2",
    "fid": "f3",
    "fs": "m:0+t:6,m:0+t:80",
    "fields": "f12,f14",
}
_EASTMONEY_PROBE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://quote.eastmoney.com/",
}

_proxy_checked = False
_detected_proxy_url = ""
_proxy_checked_lock = threading.Lock()


def reset_akshare_proxy_detection_cache() -> None:
    global _proxy_checked, _detected_proxy_url
    with _proxy_checked_lock:
        _proxy_checked = False
        _detected_proxy_url = ""


def _normalize_proxy_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    if not parsed.hostname:
        return ""
    return raw


def _get_system_proxies() -> dict[str, str]:
    try:
        proxies = urllib.request.getproxies()
    except Exception:
        return {}
    if not isinstance(proxies, dict):
        return {}
    return {str(key): str(value) for key, value in proxies.items() if value}


def _env_proxy_candidates() -> list[str]:
    candidates: list[str] = []
    for key in _PROXY_ENV_KEYS:
        value = os.environ.get(key, "")
        normalized = _normalize_proxy_url(value)
        if normalized:
            candidates.append(normalized)
    return candidates


def _parse_ports(raw: str) -> list[int]:
    ports: list[int] = []
    for item in re.split(r"[,;\s]+", raw.strip()):
        if not item:
            continue
        try:
            port = int(item)
        except ValueError:
            continue
        if 0 < port < 65536:
            ports.append(port)
    return ports


def _candidate_ports_from_env() -> list[int]:
    ports: list[int] = []
    for key in _PROXY_PORT_ENV_KEYS:
        ports.extend(_parse_ports(os.environ.get(key, "")))
    return ports


def _split_configured_env_files(raw: str) -> list[Path]:
    paths: list[Path] = []
    for item in re.split(r"[,;\s]+", raw.strip()):
        if not item:
            continue
        path = Path(os.path.expanduser(item))
        if not path.is_absolute():
            path = Path.cwd() / path
        paths.append(path)
    return paths


def _default_env_files() -> list[Path]:
    paths = [Path.cwd() / ".env"]
    module_path = Path(__file__).resolve()
    for parent in module_path.parents:
        if parent.name in {"backend", "backtrader_web"}:
            paths.append(parent / ".env")
    return paths


def _configured_env_files() -> list[Path]:
    raw = os.environ.get("AKSHARE_PROXY_ENV_FILES", "")
    paths = _split_configured_env_files(raw) if raw.strip() else _default_env_files()
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _strip_inline_comment(value: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if char == "#" and not in_single and not in_double:
            if index == 0 or value[index - 1].isspace():
                return value[:index].rstrip()
    return value.strip()


def _clean_env_value(value: str) -> str:
    cleaned = _strip_inline_comment(value).strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1]
    return cleaned.strip()


def _env_file_proxy_candidates() -> tuple[list[str], list[int]]:
    candidates: list[str] = []
    ports: list[int] = []
    for path in _configured_env_files():
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            key = key.strip()
            value = _clean_env_value(raw_value)
            if key in _PROXY_ENV_KEYS:
                normalized = _normalize_proxy_url(value)
                if normalized:
                    candidates.append(normalized)
            if key in _PROXY_PORT_ENV_KEYS:
                ports.extend(_parse_ports(value))
    return candidates, ports


def _local_listening_ports() -> list[int]:
    try:
        result = subprocess.run(
            ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except Exception:
        return []
    ports: set[int] = set()
    for match in re.finditer(
        r"(?:127\.0\.0\.1|\*|localhost):(\d+)\s+\(LISTEN\)",
        result.stdout,
    ):
        try:
            ports.add(int(match.group(1)))
        except ValueError:
            continue
    return sorted(ports)


def _port_proxy_candidates(ports: Iterable[int]) -> list[str]:
    candidates: list[str] = []
    for port in ports:
        if not (0 < int(port) < 65536):
            continue
        candidates.append(f"http://127.0.0.1:{int(port)}")
        candidates.append(f"socks5h://127.0.0.1:{int(port)}")
    return candidates


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _iter_proxy_candidates(
    *,
    listening_ports: Callable[[], Iterable[int]] = _local_listening_ports,
    system_proxies: Callable[[], dict[str, str]] = _get_system_proxies,
) -> list[str]:
    env_file_candidates, env_file_ports = _env_file_proxy_candidates()
    system_candidates = [
        _normalize_proxy_url(value)
        for key, value in system_proxies().items()
        if key.lower() in {"http", "https", "all"}
    ]
    ports = [
        *_candidate_ports_from_env(),
        *env_file_ports,
        *_DEFAULT_PROXY_PORTS,
        *list(listening_ports()),
    ]
    candidates = [
        *_env_proxy_candidates(),
        *env_file_candidates,
        *system_candidates,
        *_port_proxy_candidates(ports),
    ]
    return _dedupe(candidate for candidate in candidates if candidate)


def _proxy_port_open(
    proxy_url: str,
    *,
    timeout: float,
    socket_connect: Callable[..., object] = socket.create_connection,
) -> bool:
    parsed = urlparse(proxy_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port
    if port is None:
        port = 1080 if "socks" in (parsed.scheme or "") else 8080
    try:
        sock = socket_connect((host, port), timeout=timeout)
        close = getattr(sock, "close", None)
        if callable(close):
            close()
        return True
    except (OSError, TimeoutError):
        return False


def _resolve_probe_timeout(timeout: float | None) -> float:
    if timeout is not None:
        return max(float(timeout), 0.1)
    raw = os.environ.get("AKSHARE_PROXY_PROBE_TIMEOUT", "1.5")
    try:
        return max(float(raw), 0.1)
    except ValueError:
        return 1.5


def _default_request_get(url: str, **kwargs: object):
    session = requests.Session()
    session.trust_env = False
    return session.get(url, **kwargs)


def _eastmoney_response_ok(response: object) -> bool:
    status_code = int(getattr(response, "status_code", 0) or 0)
    text = str(getattr(response, "text", "") or "")
    if status_code != 200:
        return False
    if "<html" in text[:200].lower():
        return False
    return '"data"' in text and ('"diff"' in text or '"total"' in text)


def _probe_eastmoney(
    proxy_url: str,
    *,
    timeout: float,
    request_get: Callable[..., object] = _default_request_get,
) -> bool:
    kwargs: dict[str, object] = {
        "params": _EASTMONEY_PROBE_PARAMS,
        "headers": _EASTMONEY_PROBE_HEADERS,
        "timeout": timeout,
    }
    if proxy_url:
        kwargs["proxies"] = {"http": proxy_url, "https": proxy_url}
    try:
        response = request_get(_EASTMONEY_PROBE_URL, **kwargs)
    except Exception:
        return False
    return _eastmoney_response_ok(response)


def _clear_proxy_env() -> None:
    for key in _PROXY_ENV_KEYS:
        os.environ.pop(key, None)


def _apply_proxy_env(proxy_url: str) -> None:
    _clear_proxy_env()
    if not proxy_url:
        return
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        os.environ[key] = proxy_url
    no_proxy = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    entries = [item.strip() for item in no_proxy.split(",") if item.strip()]
    for entry in ("localhost", "127.0.0.1"):
        if entry not in entries:
            entries.append(entry)
    os.environ["NO_PROXY"] = ",".join(entries)


def configure_akshare_network_proxy(
    *,
    force_recheck: bool = False,
    timeout: float | None = None,
    request_get: Callable[..., object] = _default_request_get,
    socket_connect: Callable[..., object] = socket.create_connection,
    listening_ports: Callable[[], Iterable[int]] = _local_listening_ports,
    system_proxies: Callable[[], dict[str, str]] = _get_system_proxies,
) -> str:
    """Configure process proxy env for AkShare calls.

    Returns the selected proxy URL, or an empty string when direct access works
    or no working proxy is available.
    """
    if os.environ.get("AKSHARE_PROXY_AUTO", "1").strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        return ""

    global _proxy_checked, _detected_proxy_url
    with _proxy_checked_lock:
        if _proxy_checked and not force_recheck:
            return _detected_proxy_url

    probe_timeout = _resolve_probe_timeout(timeout)

    if _probe_eastmoney("", timeout=probe_timeout, request_get=request_get):
        _clear_proxy_env()
        with _proxy_checked_lock:
            _proxy_checked = True
            _detected_proxy_url = ""
        _logger.info("AkShare proxy auto-detect: Eastmoney direct access works")
        return ""

    for candidate in _iter_proxy_candidates(
        listening_ports=listening_ports,
        system_proxies=system_proxies,
    ):
        if not _proxy_port_open(candidate, timeout=probe_timeout, socket_connect=socket_connect):
            continue
        if not _probe_eastmoney(candidate, timeout=probe_timeout, request_get=request_get):
            continue
        _apply_proxy_env(candidate)
        with _proxy_checked_lock:
            _proxy_checked = True
            _detected_proxy_url = candidate
        _logger.info("AkShare proxy auto-detect: using %s for Eastmoney", candidate)
        return candidate

    _clear_proxy_env()
    with _proxy_checked_lock:
        _proxy_checked = True
        _detected_proxy_url = ""
    _logger.warning("AkShare proxy auto-detect: no working Eastmoney proxy found")
    return ""
