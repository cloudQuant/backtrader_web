"""
Performance monitoring middleware.

Tracks API response times and logs warnings for slow requests.
"""

import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.middleware.logging import get_logger

logger = get_logger(__name__)


class PerformanceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time

        # Add response time header
        response.headers["X-Process-Time"] = f"{process_time:.3f}s"

        # Log slow requests (>500ms)
        if process_time > 0.5:
            logger.warning(
                f"Slow API request detected",
                extra={
                    "path": str(request.url.path),
                    "method": request.method,
                    "process_time": f"{process_time:.3f}s",
                    "query_params": dict(request.query_params),
                    "user_id": request.state.user_id if hasattr(request.state, "user_id") else None,
                },
            )

        # Log all requests for monitoring
        logger.info(
            f"API request completed",
            extra={
                "path": str(request.url.path),
                "method": request.method,
                "process_time": f"{process_time:.3f}s",
                "status_code": response.status_code,
            },
        )

        return response
