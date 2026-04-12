"""
Logging middleware for FastAPI request/response logging.

Pure ASGI middleware implementations to avoid BaseHTTPMiddleware task-switching
issues with MySQL async drivers (asyncmy / aiomysql).
"""

import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.utils.logger import audit_logger, bind_request_context, get_logger

logger = get_logger(__name__)

# Query parameter names that must be redacted from logs
_SENSITIVE_PARAMS = frozenset({
    "token", "access_token", "refresh_token",
    "password", "passwd", "secret",
    "key", "api_key", "apikey",
    "authorization", "auth",
})

_SKIP_PATHS = frozenset(["/health", "/metrics", "/docs", "/redoc", "/openapi.json"])


def _sanitize_query_params(query_string: str) -> str | None:
    """Redact sensitive query parameters before logging."""
    if not query_string:
        return None
    from urllib.parse import parse_qs
    params = parse_qs(query_string, keep_blank_values=True)
    sanitized = {}
    for key, vals in params.items():
        if key.lower() in _SENSITIVE_PARAMS:
            sanitized[key] = "***REDACTED***"
        else:
            sanitized[key] = vals[0] if len(vals) == 1 else vals
    return str(sanitized)


def _get_client_ip(scope: Scope) -> str:
    """Extract real client IP from ASGI scope."""
    headers = dict(scope.get("headers", []))
    forwarded = headers.get(b"x-forwarded-for")
    if forwarded:
        return forwarded.decode().split(",")[0].strip()
    real_ip = headers.get(b"x-real-ip")
    if real_ip:
        return real_ip.decode().strip()
    client = scope.get("client")
    return client[0] if client else "unknown"


class LoggingMiddleware:
    """Pure ASGI middleware for logging HTTP requests and responses."""

    def __init__(self, app: ASGIApp, **kwargs):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in _SKIP_PATHS:
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        method = scope.get("method", "?")
        client_ip = _get_client_ip(scope)
        query_string = (scope.get("query_string") or b"").decode()

        request_logger = bind_request_context(
            request_id=request_id,
            user_id=None,
            path=path,
            method=method,
            client_ip=client_ip,
        )

        request_logger.info(
            f"Request started: {method} {path}",
            request_id=request_id,
            method=method,
            path=path,
            query_params=_sanitize_query_params(query_string),
            client_ip=client_ip,
        )

        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
                headers = MutableHeaders(scope=message)
                headers.append("X-Request-ID", request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            duration = time.time() - start_time
            request_logger.error(
                f"Request failed: {method} {path}",
                request_id=request_id,
                method=method,
                path=path,
                duration_ms=round(duration * 1000, 2),
                error_type=type(exc).__name__,
                error_message=str(exc),
                exc_info=True,
            )
            raise
        else:
            duration = time.time() - start_time
            request_logger.info(
                f"Request completed: {method} {path} -> {status_code}",
                request_id=request_id,
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=round(duration * 1000, 2),
            )


class AuditLoggingMiddleware:
    """Pure ASGI middleware for security audit logging."""

    def __init__(self, app: ASGIApp, **kwargs):
        self.app = app
        self._audit_logger = audit_logger

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"

        status_code = 200

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 200)
            await send(message)

        await self.app(scope, receive, send_wrapper)

        if status_code == 401:
            self._audit_logger.log_login(
                user_id="unknown",
                success=False,
                ip=client_ip,
                details=f"{scope.get('method', '?')} {path}",
            )


class PerformanceLoggingMiddleware:
    """Pure ASGI middleware for performance monitoring."""

    def __init__(self, app: ASGIApp, slow_request_threshold: float = 5.0, **kwargs):
        self.app = app
        self.slow_request_threshold = slow_request_threshold
        self._logger = logger.bind(tags=["performance"])

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.time()
        status_code = 200

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 200)
                duration = time.time() - start_time
                headers = MutableHeaders(scope=message)
                headers.append("X-Process-Time", f"{duration:.3f}")
            await send(message)

        await self.app(scope, receive, send_wrapper)

        duration = time.time() - start_time
        if duration > self.slow_request_threshold:
            path = scope.get("path", "")
            method = scope.get("method", "?")
            self._logger.warning(
                f"Slow request detected: {method} {path} took {duration:.2f}s",
                path=path,
                method=method,
                duration=duration,
                status_code=status_code,
            )
