"""Lifecycle hooks for durable multi-asset research workers."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from app.services.asset_research.outcome_scheduler import get_asset_research_outcome_runner
from app.services.asset_research.scheduler import get_asset_research_schedule_runner
from app.services.asset_research.task_runner import get_asset_research_task_runner
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


async def register(app: FastAPI, settings: Any) -> None:
    """Start durable interactive, schedule, and outcome workers independently."""
    startup_logger = getattr(app.state, "startup_logger", logger)
    if getattr(settings, "ASSET_RESEARCH_TASK_RUNNER_ENABLED", False):
        try:
            task_runner = get_asset_research_task_runner()
            await task_runner.start()
            app.state.asset_research_task_runner = task_runner
            startup_logger.info("Multi-asset interactive task worker started")
        except Exception:
            startup_logger.exception("Failed to start multi-asset interactive task worker")
    if getattr(settings, "ASSET_RESEARCH_SCHEDULE_ENABLED", False):
        try:
            schedule_runner = get_asset_research_schedule_runner()
            await schedule_runner.start()
            app.state.asset_research_schedule_runner = schedule_runner
            startup_logger.info("Multi-asset shadow schedule worker started")
        except Exception:
            startup_logger.exception("Failed to start multi-asset shadow schedule worker")
    if getattr(settings, "ASSET_RESEARCH_OUTCOME_EVALUATOR_ENABLED", False):
        try:
            outcome_runner = get_asset_research_outcome_runner()
            await outcome_runner.start()
            app.state.asset_research_outcome_runner = outcome_runner
            startup_logger.info("Multi-asset outcome evaluator worker started")
        except Exception:
            startup_logger.exception("Failed to start multi-asset outcome evaluator worker")


async def shutdown(app: FastAPI, settings: Any) -> None:
    """Stop in-process triggers; database leases remain recoverable by expiry."""
    del settings
    task_runner = getattr(app.state, "asset_research_task_runner", None)
    if task_runner is not None:
        await task_runner.shutdown()
    schedule_runner = getattr(app.state, "asset_research_schedule_runner", None)
    if schedule_runner is not None:
        await schedule_runner.shutdown()
    outcome_runner = getattr(app.state, "asset_research_outcome_runner", None)
    if outcome_runner is not None:
        await outcome_runner.shutdown()
