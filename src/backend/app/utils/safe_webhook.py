"""Validated, address-pinned outbound HTTP delivery for user webhooks.

Webhook URLs are user-controlled. URL parsing alone is insufficient because a
hostname can resolve to loopback/private IPs or change its answer after the
validation step. This module validates every request target (including
redirects) and opens the socket to the validated address rather than resolving
the hostname a second time during connection.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import SplitResult, urlsplit


class UnsafeWebhookURL(ValueError):
    """Raised when a webhook URL could reach a non-public network target."""


@dataclass(frozen=True)
class _WebhookTarget:
    url: str
    hostname: str
    port: int
    address: str


def _parse_webhook_url(url: str) -> SplitResult:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise UnsafeWebhookURL("Webhook URL has an invalid port") from exc

    if parsed.scheme not in {"http", "https"}:
        raise UnsafeWebhookURL("Webhook URL must use http or https")
    if not parsed.hostname or parsed.username or parsed.password:
        raise UnsafeWebhookURL("Webhook URL must not include user credentials")
    if port is not None and not 1 <= port <= 65535:
        raise UnsafeWebhookURL("Webhook URL has an invalid port")
    return parsed


def _resolve_public_address(hostname: str, port: int) -> str:
    try:
        addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeWebhookURL("Webhook hostname could not be resolved") from exc

    if not addresses:
        raise UnsafeWebhookURL("Webhook hostname did not resolve to an address")

    resolved: list[str] = []
    for _family, _socktype, _proto, _canonname, sockaddr in addresses:
        address = str(sockaddr[0])
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise UnsafeWebhookURL("Webhook hostname resolved to an invalid address") from exc
        if not ip.is_global:
            raise UnsafeWebhookURL("Webhook hostname resolves to a non-public address")
        resolved.append(address)

    # Every answer must be global. Selecting the first result is then stable
    # because the connection classes below use this literal IP instead of a
    # second hostname lookup.
    return resolved[0]


def _validated_target(url: str) -> _WebhookTarget:
    parsed = _parse_webhook_url(url)
    hostname = str(parsed.hostname)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return _WebhookTarget(
        url=url,
        hostname=hostname,
        port=port,
        address=_resolve_public_address(hostname, port),
    )


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """HTTP connection that keeps the validated hostname-to-IP binding."""

    def __init__(self, target: _WebhookTarget, **kwargs: object) -> None:
        self._pinned_address = target.address
        super().__init__(target.hostname, port=target.port, **kwargs)

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._pinned_address, self.port),
            self.timeout,
            self.source_address,
        )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection pinned to a validated IP while preserving SNI."""

    def __init__(self, target: _WebhookTarget, **kwargs: object) -> None:
        self._pinned_address = target.address
        super().__init__(target.hostname, port=target.port, **kwargs)

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._pinned_address, self.port),
            self.timeout,
            self.source_address,
        )
        if self._tunnel_host:
            self._tunnel()
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


class _PinnedHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, request: urllib.request.Request) -> Any:
        target = _validated_target(request.full_url)
        return self.do_open(
            lambda _host, **kwargs: _PinnedHTTPConnection(target, **kwargs), request
        )


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, request: urllib.request.Request) -> Any:
        target = _validated_target(request.full_url)
        return self.do_open(
            lambda _host, **kwargs: _PinnedHTTPSConnection(target, **kwargs),
            request,
            context=self._context,
        )


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Validate every redirect before the next request is constructed."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        _validated_target(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_safe_webhook(request: urllib.request.Request, timeout: float) -> Any:
    """Open a user webhook only after URL validation and address pinning.

    Environment proxy settings are intentionally disabled: proxy routing would
    otherwise bypass the target-address guarantee and reintroduce SSRF paths.
    """
    _validated_target(request.full_url)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _PinnedHTTPHandler(),
        _PinnedHTTPSHandler(),
        _SafeRedirectHandler(),
    )
    return opener.open(request, timeout=timeout)
