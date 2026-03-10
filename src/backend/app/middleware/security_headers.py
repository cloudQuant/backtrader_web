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

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses.

    This middleware adds important security headers to help prevent:
    - Cross-Site Scripting (XSS) attacks
    - Clickjacking attacks
    - MIME sniffing vulnerabilities
    - Information leakage
    - Man-in-the-Middle attacks
    """

    def __init__(self, app: FastAPI):
        """Initialize the security headers middleware.

        Args:
            app: The FastAPI application instance.
        """
        super().__init__(app)
        self.settings = get_settings()

    async def dispatch(self, request: Request, call_next):
        """Process request and add security headers to response.

        Args:
            request: Incoming request.
            call_next: Next middleware or route handler.

        Returns:
            Response with security headers added.
        """
        response: Response = await call_next(request)

        # X-Content-Type-Options: nosniff
        # Prevents MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # X-Frame-Options: DENY
        # Prevents clickjacking by denying framing
        response.headers["X-Frame-Options"] = "DENY"

        # X-XSS-Protection: 1; mode=block
        # Enables browser XSS filtering
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer-Policy: strict-origin-when-cross-origin
        # Controls how much referrer information is sent
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions-Policy: restrictive default
        # Controls which browser features can be used
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=(), usb=()"
        )

        # Content-Security-Policy: 分环境
        # 生产环境已移除 unsafe-eval，降低 XSS 风险；开发环境保留以支持 HMR
        script_src = (
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            if self.settings.DEBUG
            else "script-src 'self' 'unsafe-inline'; "
        )
        csp = (
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
        response.headers["Content-Security-Policy"] = csp

        # Only add HSTS in production with HTTPS
        if not self.settings.DEBUG:
            # Check if request is HTTPS
            if request.url.scheme == "https":
                # Strict-Transport-Security: max-age=31536000; includeSubDomains
                # Enforces HTTPS for 1 year
                response.headers["Strict-Transport-Security"] = (
                    "max-age=31536000; includeSubDomains"
                )

        # Cache control for sensitive endpoints
        if request.url.path in [
            "/api/v1/auth/login",
            "/api/v1/auth/register",
            "/api/v1/auth/refresh",
        ]:
            # Prevent caching of auth endpoints
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        else:
            # Default cache policy
            response.headers["Cache-Control"] = "no-cache"

        # Remove server information
        if "Server" in response.headers:
            del response.headers["Server"]

        # X-Powered-By: hide implementation details
        # Only show in debug mode
        if self.settings.DEBUG:
            response.headers["X-Powered-By"] = "Backtrader Web"
        elif "X-Powered-By" in response.headers:
            del response.headers["X-Powered-By"]

        return response


def add_security_headers(app: FastAPI) -> None:
    """Add security headers middleware to the FastAPI application.

    Args:
        app: The FastAPI application instance.
    """
    app.add_middleware(SecurityHeadersMiddleware)
    logger.info("Security headers middleware registered")
