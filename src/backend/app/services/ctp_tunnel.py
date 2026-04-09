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

import logging
import selectors
import socket
import subprocess
import threading
from typing import Optional

logger = logging.getLogger(__name__)

_tunnels: dict[str, "_CTPTunnel"] = {}
_lock = threading.Lock()

BUFFER_SIZE = 65536


def _get_http_proxy() -> tuple[str, int] | tuple[None, None]:
    """Get the system HTTP proxy host and port on macOS via scutil."""
    try:
        result = subprocess.run(
            ["scutil", "--proxy"],
            capture_output=True, text=True, timeout=5,
        )
        host = port = enabled = None
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("HTTPProxy"):
                host = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("HTTPPort"):
                port = int(stripped.split(":", 1)[1].strip())
            elif stripped.startswith("HTTPEnable"):
                enabled = stripped.split(":", 1)[1].strip() == "1"
        if enabled and host and port:
            return host, port
    except Exception:
        pass
    return None, None


class _CTPTunnel:
    """A local TCP tunnel that forwards CTP traffic via HTTP CONNECT proxy."""

    def __init__(
        self,
        remote_host: str,
        remote_port: int,
        proxy_host: str,
        proxy_port: int,
        local_port: int = 0,
    ):
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self._server_sock: Optional[socket.socket] = None
        self._local_port = local_port
        self._thread: Optional[threading.Thread] = None
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
            self._local_port, self.remote_host, self.remote_port,
            self.proxy_host, self.proxy_port,
        )
        return self._local_port

    def stop(self):
        """Stop the tunnel."""
        self._stop_event.set()
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
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
        connect_req = (
            f"CONNECT {target} HTTP/1.1\r\n"
            f"Host: {target}\r\n"
            f"\r\n"
        ).encode()
        sock.sendall(connect_req)

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
            self.proxy_host, target, len(leftover),
        )
        sock.settimeout(None)
        return sock, leftover

    def _accept_loop(self):
        """Accept incoming connections and create forwarding threads."""
        while not self._stop_event.is_set():
            try:
                client_sock, addr = self._server_sock.accept()
            except socket.timeout:
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
                for key, mask in events:
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
                    pass
            for s in (client_sock, remote_sock):
                if s:
                    try:
                        s.close()
                    except Exception:
                        pass


def is_proxy_tunnel_needed() -> bool:
    """Check if a system HTTP proxy is active and CTP traffic needs tunneling."""
    host, port = _get_http_proxy()
    if not host or not port:
        return False
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def ensure_tunnel(remote_host: str, remote_port: int) -> int:
    """Ensure a tunnel exists for the given remote host:port.

    Returns the local port to connect to.
    Raises ConnectionError if no proxy is available.
    """
    proxy_host, proxy_port = _get_http_proxy()
    if not proxy_host or not proxy_port:
        raise ConnectionError("No system HTTP proxy configured")

    key = f"{remote_host}:{remote_port}"
    with _lock:
        if key in _tunnels and not _tunnels[key]._stop_event.is_set():
            return _tunnels[key].local_port

        tunnel = _CTPTunnel(remote_host, remote_port, proxy_host, proxy_port)
        local_port = tunnel.start()
        _tunnels[key] = tunnel
        return local_port


def stop_all_tunnels():
    """Stop all active tunnels."""
    with _lock:
        for tunnel in _tunnels.values():
            tunnel.stop()
        _tunnels.clear()
