"""Start and stop the optional after-close stock-signal scheduler."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from app.services.stock_signal.scheduler import get_stock_signal_scheduler
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


async def register(app: FastAPI, settings: Any) -> None:
    """Start only the explicitly enabled, configuration-complete scheduler."""
    if not settings.STOCK_SIGNAL_SCHEDULE_ENABLED:
        return
    try:
        scheduler = get_stock_signal_scheduler()
        await scheduler.start()
        app.state.stock_signal_scheduler = scheduler
        getattr(app.state, "startup_logger", logger).info("Nightly SSE50 signal scheduler started")
    except Exception:
        getattr(app.state, "startup_logger", logger).exception(
            "Failed to start nightly SSE50 signal scheduler"
        )


async def shutdown(app: FastAPI, settings: Any) -> None:
    """Stop in-process triggers before database resources are disposed."""
    del settings
    scheduler = getattr(app.state, "stock_signal_scheduler", None)
    if scheduler is not None:
        await scheduler.shutdown()
