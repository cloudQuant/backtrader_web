import logging
import os
import socket
import subprocess
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

_logger = logging.getLogger(__name__)


def kill_process_on_port(
    port: int,
    *,
    current_pid: Callable[[], int] = os.getpid,
    run_command: Callable[..., Any] = subprocess.run,
    kill_pid: Callable[[int, int], None] = os.kill,
    logger: logging.Logger = _logger,
) -> None:
    """Kill any process holding *port* so ZMQ can rebind on retry.

    Uses psutil when available, falls back to lsof on macOS/Linux.
    """
    try:
        import psutil

        for conn in psutil.net_connections(kind="tcp"):
            status = str(getattr(conn, "status", "") or "").upper()
            laddr = conn.laddr
            laddr_port = getattr(laddr, "port", None)
            if laddr_port == port and conn.pid and status == "LISTEN":
                try:
                    proc = psutil.Process(conn.pid)
                    if proc.pid != current_pid():
                        proc.kill()
                        logger.warning("Killed process PID=%d holding port %d", proc.pid, port)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        return
    except ImportError:
        pass
    except Exception:
        logger.debug("psutil-based port release failed for port %d", port, exc_info=True)

    try:
        result = run_command(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for pid_str in result.stdout.splitlines():
            pid_str = pid_str.strip()
            if pid_str and pid_str.isdigit():
                pid = int(pid_str)
                if pid != current_pid():
                    try:
                        kill_pid(pid, 9)
                        logger.warning(
                            "Killed process PID=%d holding port %d (via lsof)", pid, port
                        )
                    except (OSError, ProcessLookupError):
                        pass
    except Exception:
        logger.debug("lsof-based port release failed for port %d", port, exc_info=True)


def parse_base_url_endpoint(base_url: str) -> tuple[str, int]:
    parsed = urlparse(base_url or "https://localhost:5000")
    host = (parsed.hostname or "localhost").lower()
    if parsed.port is not None:
        return host, parsed.port
    if parsed.scheme == "http":
        return host, 80
    return host, 443


def is_tcp_endpoint_reachable(
    host: str,
    port: int,
    timeout: float = 1.0,
    *,
    create_connection: Callable[..., Any] = socket.create_connection,
) -> bool:
    try:
        conn = create_connection((host, port), timeout=timeout)
    except OSError:
        return False
    close = getattr(conn, "close", None)
    if callable(close):
        close()
    return True


def wait_for_tcp_endpoint(
    host: str,
    port: int,
    timeout_sec: float,
    *,
    is_reachable: Callable[..., bool] = is_tcp_endpoint_reachable,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    deadline = monotonic() + max(timeout_sec, 0.0)
    while monotonic() < deadline:
        if is_reachable(host, port, timeout=0.5):
            return True
        sleep(0.5)
    return is_reachable(host, port, timeout=0.5)
