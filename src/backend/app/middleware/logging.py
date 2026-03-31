"""
Logging middleware for FastAPI request/response logging.

Automatically adds request ID, tracks request duration,
and logs all requests and responses.
"""

import time
import uuid
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.utils.logger import audit_logger, bind_request_context, get_logger

logger = get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging HTTP requests and responses.

    Features:
    - Automatic request ID generation
    - Request duration tracking
    - Request/response body logging (configurable)
    - Sensitive data filtering
    """

    # Query parameter names that must be redacted from logs
    _SENSITIVE_PARAMS = frozenset({
        "token", "access_token", "refresh_token",
        "password", "passwd", "secret",
        "key", "api_key", "apikey",
        "authorization", "auth",
    })

    def __init__(
        self,
        app: ASGIApp,
        log_body: bool = False,
        log_headers: bool = False,
        skip_paths: list = None,
    ):
        """Initialize logging middleware.

        Args:
            app: ASGI application.
            log_body: Whether to log request/response bodies.
            log_headers: Whether to log request/response headers.
            skip_paths: List of paths to skip logging (e.g., /health).
        """
        super().__init__(app)
        self.log_body = log_body
        self.log_headers = log_headers
        self.skip_paths = set(
            skip_paths or ["/health", "/metrics", "/docs", "/redoc", "/openapi.json"]
        )

    @classmethod
    def _sanitize_query_params(cls, query_params) -> str | None:
        """Redact sensitive query parameters before logging.

        Args:
            query_params: The request query parameters.

        Returns:
            Sanitized string representation, or None if empty.
        """
        if not query_params:
            return None
        sanitized = {}
        for key in query_params:
            if key.lower() in cls._SENSITIVE_PARAMS:
                sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = query_params[key]
        return str(sanitized)

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """Extract real client IP, respecting X-Forwarded-For header.

        Args:
            request: The incoming HTTP request.

        Returns:
            The client IP address string.
        """
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # First IP in the chain is the original client
            return forwarded_for.split(",")[0].strip()
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and log details.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware or route handler.

        Returns:
            HTTP response from the route handler.
        """
        # Skip logging for health check and docs endpoints
        if request.url.path in self.skip_paths:
            return await call_next(request)

        # Generate request ID
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        # Get client IP (respects X-Forwarded-For)
        client_ip = self._get_client_ip(request)

        # Bind request context to logger
        request_logger = bind_request_context(
            request_id=request_id,
            user_id=getattr(request.state, "user_id", None),
            path=request.url.path,
            method=request.method,
            client_ip=client_ip,
        )

        # Log incoming request (with sensitive params redacted)
        request_logger.info(
            f"Request started: {request.method} {request.url.path}",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            query_params=self._sanitize_query_params(request.query_params),
            client_ip=client_ip,
        )

        # Process request
        try:
            response = await call_next(request)

            # Calculate duration
            duration = time.time() - start_time

            # Log response
            request_logger.info(
                f"Request completed: {request.method} {request.url.path} -> {response.status_code}",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration * 1000, 2),
                user_id=getattr(request.state, "user_id", None),
            )

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            # Log error
            duration = time.time() - start_time
            request_logger.error(
                f"Request failed: {request.method} {request.url.path}",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                duration_ms=round(duration * 1000, 2),
                user_id=getattr(request.state, "user_id", None),
                error_type=type(e).__name__,
                error_message=str(e),
                exc_info=True,
            )
            raise


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for security audit logging.

    Logs authentication and authorization events.
    """

    def __init__(self, app: ASGIApp):
        """Initialize audit logging middleware.

        Args:
            app: ASGI application.
        """
        super().__init__(app)
        self.audit_logger = audit_logger

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and log audit events.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware or route handler.

        Returns:
            HTTP response from the route handler.
        """
        # Get user info from request state (set by auth middleware)
        user_id = getattr(request.state, "user_id", None)
        client_ip = request.client.host if request.client else "unknown"

        # Track authentication events
        if request.url.path.startswith("/api/v1/auth/login"):
            # Login is handled in the route handler, just track the request here
            # No action needed - login events are logged by auth_service
            pass
        elif request.url.path.startswith("/api/v1/auth/logout"):
            # Log logout
            if user_id:
                self.audit_logger.log_logout(user_id=user_id)

        # Process request
        response = await call_next(request)

        # Log failed authentication attempts
        if response.status_code == 401:
            self.audit_logger.log_login(
                user_id=user_id or "unknown",
                success=False,
                ip=client_ip,
                details=f"{request.method} {request.url.path}",
            )

        return response


class PerformanceLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for performance monitoring.

    Logs slow requests and performance metrics.
    """

    def __init__(self, app: ASGIApp, slow_request_threshold: float = 5.0):
        """Initialize performance logging middleware.

        Args:
            app: ASGI application.
            slow_request_threshold: Threshold in seconds for logging slow requests.
        """
        super().__init__(app)
        self.slow_request_threshold = slow_request_threshold
        self.logger = logger.bind(tags=["performance"])

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and track performance metrics.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware or route handler.

        Returns:
            HTTP response from the route handler.
        """
        start_time = time.time()

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration = time.time() - start_time

        # Log slow requests
        if duration > self.slow_request_threshold:
            self.logger.warning(
                f"Slow request detected: {request.method} {request.url.path} took {duration:.2f}s",
                path=request.url.path,
                method=request.method,
                duration=duration,
                status_code=response.status_code,
            )

        # Add performance timing to response header
        response.headers["X-Process-Time"] = f"{duration:.3f}"

        return response
