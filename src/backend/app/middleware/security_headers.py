"""
Security headers middleware for HTTP response security.

This middleware adds security-related HTTP headers to responses to prevent
common web vulnerabilities such as XSS, clickjacking, and other attacks.

Implemented security headers:
- X-Content-Type-Options: Prevents MIME sniffing
- X-Frame-Options: Prevents clickjacking
- X-XSS-Protection: Enables XSS filtering
- Strict-Transport-Security: Enforces HTTPS (production only)
- Content-Security-Policy: Controls resource loading
- Referrer-Policy: Controls referrer information leakage
- Permissions-Policy: Controls browser features

Reference: https://owasp.org/www-project-secure-headers/
"""

from fastapi import FastAPI
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

_AUTH_PATHS = frozenset(
    [
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/refresh",
    ]
)


class SecurityHeadersMiddleware:
    """Pure ASGI middleware to add security headers to all responses.

    This middleware adds important security headers to help prevent:
    - Cross-Site Scripting (XSS) attacks
    - Clickjacking attacks
    - MIME sniffing vulnerabilities
    - Information leakage
    - Man-in-the-Middle attacks
    """

    def __init__(self, app: ASGIApp, **kwargs):
        """Initialize the security headers middleware."""
        self.app = app
        self.settings = get_settings()

        # Pre-compute CSP header
        script_src = (
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            if self.settings.DEBUG
            else "script-src 'self' 'unsafe-inline'; "
        )
        self._csp = (
            "default-src 'self'; "
            f"{script_src}"
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        scheme = scope.get("scheme", "http")

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append("X-Content-Type-Options", "nosniff")
                headers.append("X-Frame-Options", "DENY")
                headers.append("X-XSS-Protection", "1; mode=block")
                headers.append("Referrer-Policy", "strict-origin-when-cross-origin")
                headers.append(
                    "Permissions-Policy",
                    "geolocation=(), microphone=(), camera=(), payment=(), usb=()",
                )
                headers.append("Content-Security-Policy", self._csp)

                if not self.settings.DEBUG and scheme == "https":
                    headers.append(
                        "Strict-Transport-Security",
                        "max-age=31536000; includeSubDomains",
                    )

                if path in _AUTH_PATHS:
                    headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
                    headers.append("Pragma", "no-cache")
                    headers.append("Expires", "0")
                else:
                    headers["Cache-Control"] = "no-cache"

                if self.settings.DEBUG:
                    headers.append("X-Powered-By", "Backtrader Web")

            await send(message)

        await self.app(scope, receive, send_wrapper)


def add_security_headers(app: FastAPI) -> None:
    """Add security headers middleware to the FastAPI application.

    Args:
        app: The FastAPI application instance.
    """
    app.add_middleware(SecurityHeadersMiddleware)
    logger.info("Security headers middleware registered")
