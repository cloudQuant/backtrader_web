"""Start and stop durable paper-runtime snapshot workers with the API lifecycle."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from app.services.paper_runtime_scheduler import get_paper_runtime_snapshot_scheduler
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


async def register(app: FastAPI, settings: Any) -> None:
    """Restore workers for active paper units after application startup."""
    try:
        scheduler = get_paper_runtime_snapshot_scheduler()
        restored = await scheduler.start_existing()
        app.state.paper_runtime_snapshot_scheduler = scheduler
        if restored:
            getattr(app.state, "startup_logger", logger).info(
                "Restored paper-runtime snapshot workers: %s", restored
            )
    except Exception:
        getattr(app.state, "startup_logger", logger).exception(
            "Failed to restore paper-runtime snapshot workers"
        )


async def shutdown(app: FastAPI, settings: Any) -> None:
    """Cancel in-process workers before database resources are released."""
    scheduler = getattr(app.state, "paper_runtime_snapshot_scheduler", None)
    if scheduler is None:
        return
    await scheduler.shutdown()
