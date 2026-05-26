"""
Rate limit headers middleware.

Injects X-RateLimit-* headers into all API responses that pass through
slowapi rate limiting, and standardizes 429 responses with Retry-After
and a consistent JSON body.

Headers added:
- X-RateLimit-Limit: Maximum requests allowed in the current window
- X-RateLimit-Remaining: Remaining requests in the current window
- X-RateLimit-Reset: Unix timestamp when the window resets (seconds)
- Retry-After: (429 only) Seconds to wait before retrying

Fail-open: If rate limit state cannot be read, headers are skipped
and a warning is logged.
"""

import json
import time
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.utils.logger import get_logger

logger = get_logger(__name__)


class RateLimitHeadersMiddleware:
    """ASGI middleware to inject rate limit response headers.

    Extracts rate limit state from slowapi's request.state.view_rate_limit
    and injects X-RateLimit-* headers into responses. For 429 responses,
    also adds Retry-After header and standardizes the response body.

    On any exception during header injection, fails open (no headers added)
    and logs a warning.
    """

    def __init__(self, app: ASGIApp, **kwargs: Any) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # State for response interception
        status_code: int = 200
        rate_limit_info: dict[str, str] | None = None
        # For 429 responses, we buffer the start message to fix content-length
        buffered_start: Message | None = None

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, rate_limit_info, buffered_start

            if message["type"] == "http.response.start":
                status_code = message.get("status", 200)

                # Try to extract rate limit info from scope's state
                # slowapi sets request.state.view_rate_limit as a tuple
                # (RateLimitItem, List[str]) after rate limit check
                try:
                    rate_limit_info = self._extract_rate_limit_headers(scope)
                except Exception as exc:
                    # Fail-open: don't add headers, log warning
                    logger.warning(
                        "Failed to extract rate limit state: %s", exc
                    )
                    rate_limit_info = None

                if rate_limit_info:
                    headers = MutableHeaders(scope=message)

                    # Only add headers if not already present (slowapi may have
                    # already injected them at the decorator level)
                    if "X-RateLimit-Limit" not in headers:
                        headers.append("X-RateLimit-Limit", rate_limit_info["limit"])
                    if "X-RateLimit-Remaining" not in headers:
                        headers.append(
                            "X-RateLimit-Remaining", rate_limit_info["remaining"]
                        )
                    if "X-RateLimit-Reset" not in headers:
                        headers.append("X-RateLimit-Reset", rate_limit_info["reset"])

                    # For 429 responses, add Retry-After if not present
                    if status_code == 429 and "Retry-After" not in headers:
                        headers.append("Retry-After", rate_limit_info["retry_after"])

                elif status_code == 429:
                    # Even without rate limit info, try to add a default Retry-After
                    headers = MutableHeaders(scope=message)
                    if "Retry-After" not in headers:
                        headers.append("Retry-After", "60")

                # For 429 responses, buffer the start message so we can fix
                # content-length after deciding whether the body should be standardized.
                if status_code == 429:
                    buffered_start = message
                else:
                    await send(message)

            elif message["type"] == "http.response.body":
                if status_code == 429:
                    original_body = message.get("body", b"")
                    if rate_limit_info is None and _looks_like_structured_json_429(original_body):
                        if buffered_start is not None:
                            await send(buffered_start)
                            buffered_start = None
                        await send(message)
                        return

                    retry_after_seconds = "60"
                    if rate_limit_info and "retry_after" in rate_limit_info:
                        retry_after_seconds = rate_limit_info["retry_after"]

                    standardized_body = json.dumps(
                        {
                            "detail": "Rate limit exceeded",
                            "retry_after": int(retry_after_seconds),
                        }
                    ).encode("utf-8")

                    # Fix content-length in the buffered start message
                    if buffered_start is not None:
                        headers = MutableHeaders(scope=buffered_start)
                        headers["content-type"] = "application/json"
                        headers["content-length"] = str(len(standardized_body))
                        await send(buffered_start)
                        buffered_start = None

                    message = {
                        "type": "http.response.body",
                        "body": standardized_body,
                        "more_body": False,
                    }

                await send(message)
            else:
                await send(message)

        await self.app(scope, receive, send_wrapper)

    def _extract_rate_limit_headers(self, scope: Scope) -> dict[str, str] | None:
        """Extract rate limit info from the ASGI scope's state.

        slowapi stores rate limit info on request.state.view_rate_limit as a
        tuple of (RateLimitItem, List[str]) where:
        - RateLimitItem has .amount (max requests) attribute
        - The list contains key arguments for window stats lookup

        Returns:
            Dict with limit, remaining, reset, retry_after keys, or None
            if rate limit state is not available.
        """
        # Access the Starlette state from scope
        state = scope.get("state")
        if not state:
            return None

        # view_rate_limit may be stored as a dict key or attribute
        view_rate_limit = None
        if isinstance(state, dict):
            view_rate_limit = state.get("view_rate_limit")
        else:
            view_rate_limit = getattr(state, "view_rate_limit", None)

        if view_rate_limit is None:
            return None

        # view_rate_limit is (RateLimitItem, List[str])
        rate_limit_item, key_args = view_rate_limit

        # Get the limiter from app state to call get_window_stats
        app = scope.get("app")
        if app is None:
            return None

        limiter = getattr(getattr(app, "state", None), "limiter", None)
        if limiter is None:
            return None

        # Get window stats from the limiter's underlying storage
        window_stats = limiter.limiter.get_window_stats(rate_limit_item, *key_args)
        # window_stats is (reset_timestamp, remaining_count)
        reset_time = int(1 + window_stats[0])
        remaining = int(window_stats[1])
        limit_amount = rate_limit_item.amount

        # Calculate retry_after as seconds until reset
        retry_after = max(0, reset_time - int(time.time()))

        return {
            "limit": str(limit_amount),
            "remaining": str(remaining),
            "reset": str(reset_time),
            "retry_after": str(retry_after),
        }


def _looks_like_structured_json_429(body: bytes) -> bool:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    return any(key in payload for key in ("error", "message", "details"))
