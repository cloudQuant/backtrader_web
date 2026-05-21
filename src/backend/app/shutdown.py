"""
Graceful shutdown manager.

Coordinates orderly shutdown of the application by:
1. Setting a shutting_down flag (so health checks return 503)
2. Closing all active WebSocket connections with 1001 Going Away
3. Waiting for in-flight connections to drain before proceeding
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.config import get_settings
from app.websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)


class GracefulShutdownManager:
    """Manages graceful shutdown of the application.

    Attributes:
        is_shutting_down: Whether shutdown has been initiated.
    """

    def __init__(self) -> None:
        self._shutting_down = False

    @property
    def is_shutting_down(self) -> bool:
        """Whether shutdown has been initiated."""
        return self._shutting_down

    async def initiate(self, app) -> None:
        """Initiate graceful shutdown sequence.

        Steps:
            1. Set app.state.shutting_down = True
            2. Log shutdown start with ISO 8601 timestamp and connection count
            3. Close all WebSocket connections with 1001 Going Away
            4. Wait for connections to drain (up to SHUTDOWN_TIMEOUT)
            5. Log shutdown completion

        Args:
            app: The FastAPI application instance.
        """
        settings = get_settings()
        timeout = settings.SHUTDOWN_TIMEOUT

        # 1. Set shutting_down flag
        app.state.shutting_down = True
        self._shutting_down = True

        # 2. Log shutdown start
        active_connections = ws_manager.get_total_connections()
        start_time = datetime.now(timezone.utc).isoformat()
        logger.info(
            "Graceful shutdown initiated at %s, active_connections=%d, timeout=%ds",
            start_time,
            active_connections,
            timeout,
        )

        # 3. Close all WebSocket connections
        closed = await ws_manager.close_all(code=1001, reason="Going Away")
        if closed:
            logger.info("Sent close frames to %d WebSocket connections", closed)

        # 4. Wait for connections to drain
        elapsed = 0.0
        poll_interval = 0.5
        while elapsed < timeout:
            remaining = ws_manager.get_total_connections()
            if remaining == 0:
                break
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        # 5. Log completion
        remaining = ws_manager.get_total_connections()
        if remaining > 0:
            logger.warning(
                "Graceful shutdown completed with %d connections still active after %.1fs",
                remaining,
                elapsed,
            )
        else:
            logger.info("Graceful shutdown completed, all connections drained in %.1fs", elapsed)
