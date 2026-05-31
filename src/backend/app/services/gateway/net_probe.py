"""Pure network-probe helpers extracted from ``gateway/manual.py``.

Iteration 179 §B (REFACTORING_BACKLOG P1#4 slice 1): these are side-effect-free
parsing helpers for ZMQ bind-error inspection and CTP front-endpoint parsing.
They were lifted out of the 2000-line ``manual.py`` so they can be unit-tested
in isolation and so the gateway module shrinks. ``manual.py`` re-exports every
name below, so existing call sites and patch targets keep working unchanged.

No behavioural change: the function bodies are copied verbatim from
``manual.py``.
"""

import re
import socket
from typing import Any
from urllib.parse import urlparse

__all__ = [
    "extract_port_from_zmq_error",
    "extract_err_msg_from_error_entry",
    "is_address_in_use_error",
    "find_recent_bind_error",
    "parse_tcp_front_endpoint",
    "extract_ips_from_fronts",
]


def extract_port_from_zmq_error(err_msg: str) -> int | None:
    """Parse port number from ZMQ 'Address already in use' error string."""
    m = re.search(r":(\d{4,5})['\"]?\s*\)", err_msg)
    if m:
        return int(m.group(1))
    return None


def extract_err_msg_from_error_entry(entry: Any) -> str:
    """Extract a plain string error message from a health snapshot error entry.

    The entry may be a plain string or a dict with a 'message' key.
    """
    if isinstance(entry, dict):
        return str(entry.get("message") or entry).strip()
    return str(entry).strip()


def is_address_in_use_error(err_msg: str) -> bool:
    """Return True if *err_msg* looks like a TCP 'address already in use' error."""
    normalized = str(err_msg or "").lower()
    return "address already in use" in normalized or "address in use" in normalized


def find_recent_bind_error(snapshot: dict[str, Any] | None) -> str:
    """Return the most recent 'address in use' message from a health snapshot."""
    if not isinstance(snapshot, dict):
        return ""
    recent_errors = snapshot.get("recent_errors")
    if not isinstance(recent_errors, list):
        return ""
    for item in reversed(recent_errors):
        message = extract_err_msg_from_error_entry(item)
        if is_address_in_use_error(message):
            return message
    return ""


def parse_tcp_front_endpoint(front: str) -> tuple[str, int] | tuple[None, None]:
    """Parse a ``tcp://host:port`` front address into ``(host, port)``."""
    parsed = urlparse(front or "")
    host = parsed.hostname
    port = parsed.port
    if not host or port is None:
        return None, None
    return host.lower(), port


def extract_ips_from_fronts(*fronts: str) -> list[str]:
    """Extract unique IP addresses from CTP front address strings.

    e.g. ``tcp://1.2.3.4:1234`` -> ``["1.2.3.4"]``. Loopback (``127.*``) and
    non-IP hostnames are skipped.
    """
    seen: set[str] = set()
    result: list[str] = []
    for front in fronts:
        host, _ = parse_tcp_front_endpoint(front)
        if host and host not in seen and not host.startswith("127."):
            try:
                socket.inet_aton(host)
                seen.add(host)
                result.append(host)
            except OSError:
                pass
    return result
