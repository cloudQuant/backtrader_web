"""Local TCP tunnel to bypass TUN proxy for CTP connections.

When a TUN-mode transparent proxy (ViewTurbo / Clash / Surge) is active,
CTP's native TCP connections get intercepted. The proxy completes the TCP
handshake but can't understand the CTP binary protocol, so data never reaches
the real server.

Solution: use the proxy's own HTTP CONNECT method to establish a TCP tunnel:
  CTP SDK -> localhost:LOCAL_PORT -> HTTP CONNECT via proxy -> CTP_SERVER:PORT

The proxy understands HTTP CONNECT and creates a transparent TCP pipe, which
correctly forwards the CTP binary protocol.
"""

from __future__ import annotations

import base64
import logging
import os
import selectors
import shutil
import socket
import subprocess
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import getproxies

logger = logging.getLogger(__name__)

_tunnels: dict[str, _CTPTunnel] = {}
_lock = threading.Lock()

BUFFER_SIZE = 65536
_DISABLED_VALUES = {"0", "false", "no", "off", "disabled"}
_PROXY_ENV_KEYS = (
    "BT_CTP_TUNNEL_PROXY",
    "CTP_TUNNEL_PROXY",
    "CTP_HTTP_PROXY",
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
)


@dataclass(frozen=True)
class _ProxyEndpoint:
    host: str
    port: int
    authorization: str = ""
    source: str = ""


def _is_disabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in _DISABLED_VALUES


def _proxy_from_url(value: str | None, source: str) -> _ProxyEndpoint | None:
    raw = str(value or "").strip()
    if not raw or _is_disabled(raw):
        return None
    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    scheme = parsed.scheme.lower()
    if scheme != "http":
        logger.debug("Ignoring non-HTTP CTP tunnel proxy from %s: %s", source, raw)
        return None
    host = parsed.hostname
    port = parsed.port or 80
    if not host or port <= 0:
        return None
    authorization = ""
    if parsed.username is not None:
        username = unquote(parsed.username)
        password = unquote(parsed.password or "")
        token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        authorization = f"Basic {token}"
    return _ProxyEndpoint(host=host, port=port, authorization=authorization, source=source)


def _proxy_from_scutil_output(output: str) -> _ProxyEndpoint | None:
    host = port = enabled = None
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("HTTPProxy"):
            host = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("HTTPPort"):
            port = int(stripped.split(":", 1)[1].strip())
        elif stripped.startswith("HTTPEnable"):
            enabled = stripped.split(":", 1)[1].strip() == "1"
    if enabled and host and port:
        return _ProxyEndpoint(host=host, port=port, source="scutil")
    return None


def _get_http_proxy_endpoint(
    *,
    environ: dict[str, str] | None = None,
    system_getproxies: Callable[[], dict[str, str]] | None = None,
    run_scutil: Callable[..., Any] | None = subprocess.run,
) -> _ProxyEndpoint | None:
    """Resolve the HTTP proxy used for CTP CONNECT tunnels."""
    env = os.environ if environ is None else environ
    if _is_disabled(env.get("CTP_TUNNEL_ENABLED")) or _is_disabled(
        env.get("BT_CTP_TUNNEL_ENABLED")
    ):
        return None

    for key in _PROXY_ENV_KEYS:
        endpoint = _proxy_from_url(env.get(key), f"env:{key}")
        if endpoint is not None:
            return endpoint

    proxy_getter = getproxies if system_getproxies is None else system_getproxies
    try:
        proxies = proxy_getter() or {}
    except Exception:
        proxies = {}
    for key in ("http", "https"):
        endpoint = _proxy_from_url(proxies.get(key), f"system:{key}")
        if endpoint is not None:
            return endpoint

    should_probe_scutil = run_scutil is not None and (
        run_scutil is not subprocess.run
        or (sys.platform == "darwin" and shutil.which("scutil") is not None)
    )
    if should_probe_scutil:
        try:
            result = run_scutil(
                ["scutil", "--proxy"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            endpoint = _proxy_from_scutil_output(result.stdout)
            if endpoint is not None:
                return endpoint
        except Exception:
            logger.debug("Failed to parse HTTP proxy config from scutil output", exc_info=True)
    return None


def _get_http_proxy() -> tuple[str, int] | tuple[None, None]:
    """Get the active HTTP proxy host and port for CTP tunneling."""
    endpoint = _get_http_proxy_endpoint()
    if endpoint is not None:
        return endpoint.host, endpoint.port
    return None, None


def _build_connect_request(target: str, proxy_authorization: str = "") -> bytes:
    headers = [
        f"CONNECT {target} HTTP/1.1",
        f"Host: {target}",
        "Proxy-Connection: Keep-Alive",
        "Connection: Keep-Alive",
    ]
    if proxy_authorization:
        headers.append(f"Proxy-Authorization: {proxy_authorization}")
    return ("\r\n".join(headers) + "\r\n\r\n").encode("ascii")


class _CTPTunnel:
    """A local TCP tunnel that forwards CTP traffic via HTTP CONNECT proxy."""

    def __init__(
        self,
        remote_host: str,
        remote_port: int,
        proxy_host: str,
        proxy_port: int,
        proxy_authorization: str = "",
        local_port: int = 0,
    ):
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.proxy_authorization = proxy_authorization
        self._server_sock: socket.socket | None = None
        self._local_port = local_port
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    @property
    def local_port(self) -> int:
        return self._local_port

    def start(self) -> int:
        """Start the tunnel. Returns the local port."""
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind(("127.0.0.1", self._local_port))
        self._server_sock.listen(8)
        self._server_sock.settimeout(1.0)
        self._local_port = self._server_sock.getsockname()[1]

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._accept_loop,
            name=f"ctp-tunnel-{self.remote_host}:{self.remote_port}",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "CTP tunnel started: 127.0.0.1:%d -> CONNECT %s:%d via proxy %s:%d",
            self._local_port,
            self.remote_host,
            self.remote_port,
            self.proxy_host,
            self.proxy_port,
        )
        return self._local_port

    def stop(self):
        """Stop the tunnel."""
        self._stop_event.set()
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                logger.debug("Failed to close CTP tunnel server socket", exc_info=True)
        if self._thread:
            self._thread.join(timeout=3.0)
        logger.info("CTP tunnel stopped: port %d", self._local_port)

    def _connect_via_proxy(self) -> tuple[socket.socket, bytes]:
        """Establish a TCP tunnel through the HTTP proxy using CONNECT.

        Returns (socket, leftover_data) where leftover_data is any bytes
        received after the HTTP response headers that belong to the tunneled stream.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10.0)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.connect((self.proxy_host, self.proxy_port))

        target = f"{self.remote_host}:{self.remote_port}"
        sock.sendall(_build_connect_request(target, self.proxy_authorization))

        response = b""
        while b"\r\n\r\n" not in response:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("Proxy closed connection during CONNECT")
            response += chunk

        header_end = response.index(b"\r\n\r\n") + 4
        headers = response[:header_end]
        leftover = response[header_end:]

        status_line = headers.split(b"\r\n")[0].decode(errors="replace")
        if b"200" not in headers.split(b"\r\n")[0]:
            raise ConnectionError(f"Proxy CONNECT failed: {status_line}")

        logger.debug(
            "HTTP CONNECT tunnel established: %s -> %s (leftover=%d bytes)",
            self.proxy_host,
            target,
            len(leftover),
        )
        sock.settimeout(None)
        return sock, leftover

    def _accept_loop(self):
        """Accept incoming connections and create forwarding threads."""
        while not self._stop_event.is_set():
            try:
                client_sock, addr = self._server_sock.accept()
            except TimeoutError:
                continue
            except OSError:
                break

            fwd_thread = threading.Thread(
                target=self._forward,
                args=(client_sock,),
                daemon=True,
                name=f"ctp-fwd-{addr[1]}",
            )
            fwd_thread.start()

    def _forward(self, client_sock: socket.socket):
        """Forward data bidirectionally between client and remote via proxy."""
        remote_sock = None
        sel = None
        try:
            client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            remote_sock, leftover = self._connect_via_proxy()

            if leftover:
                client_sock.sendall(leftover)

            sel = selectors.DefaultSelector()
            sel.register(client_sock, selectors.EVENT_READ, "client")
            sel.register(remote_sock, selectors.EVENT_READ, "remote")

            while not self._stop_event.is_set():
                events = sel.select(timeout=5.0)
                for key, _mask in events:
                    if key.data == "client":
                        data = client_sock.recv(BUFFER_SIZE)
                        if not data:
                            return
                        remote_sock.sendall(data)
                    elif key.data == "remote":
                        data = remote_sock.recv(BUFFER_SIZE)
                        if not data:
                            return
                        client_sock.sendall(data)

        except Exception as exc:
            logger.debug("CTP tunnel forward error: %s", exc)
        finally:
            if sel:
                try:
                    sel.close()
                except Exception:
                    logger.debug("Failed to close CTP tunnel selector", exc_info=True)
            for s in (client_sock, remote_sock):
                if s:
                    try:
                        s.close()
                    except Exception:
                        logger.debug("Failed to close CTP tunnel socket", exc_info=True)


def is_proxy_tunnel_needed() -> bool:
    """Check if a system HTTP proxy is active and CTP traffic needs tunneling."""
    endpoint = _get_http_proxy_endpoint()
    if endpoint is None:
        return False
    try:
        with socket.create_connection((endpoint.host, endpoint.port), timeout=2):
            pass
        return True
    except Exception:
        return False


def ensure_tunnel(remote_host: str, remote_port: int) -> int:
    """Ensure a tunnel exists for the given remote host:port.

    Returns the local port to connect to.
    Raises ConnectionError if no proxy is available.
    """
    proxy = _get_http_proxy_endpoint()
    if proxy is None:
        raise ConnectionError("No system HTTP proxy configured")

    key = f"{remote_host}:{remote_port}|{proxy.host}:{proxy.port}|{proxy.authorization}"
    with _lock:
        if key in _tunnels and not _tunnels[key]._stop_event.is_set():
            return _tunnels[key].local_port

        tunnel = _CTPTunnel(
            remote_host,
            remote_port,
            proxy.host,
            proxy.port,
            proxy_authorization=proxy.authorization,
        )
        local_port = tunnel.start()
        _tunnels[key] = tunnel
        return local_port


def stop_all_tunnels():
    """Stop all active tunnels."""
    with _lock:
        for tunnel in _tunnels.values():
            tunnel.stop()
        _tunnels.clear()
