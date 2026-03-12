"""
Auto-trading schedule API routes.

Provides endpoints for configuring and querying the automatic
start/stop scheduler for Chinese futures market hours.
"""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.services.auto_trading_scheduler import AutoTradingScheduler, get_auto_trading_scheduler

router = APIRouter()


def _get_scheduler() -> AutoTradingScheduler:
    """Return the global AutoTradingScheduler instance."""
    return get_auto_trading_scheduler()


@router.get("/config", summary="Get auto-trading configuration")
async def get_config(
    current_user=Depends(get_current_user),
    sched: AutoTradingScheduler = Depends(_get_scheduler),
):
    """Return the current auto-trading configuration.

    Returns:
        enabled, buffer_minutes, sessions, and scope.
    """
    return sched.get_config()


@router.put("/config", summary="Update auto-trading configuration")
async def update_config(
    body: dict,
    current_user=Depends(get_current_user),
    sched: AutoTradingScheduler = Depends(_get_scheduler),
):
    """Update auto-trading configuration.

    Accepts any subset of: enabled, buffer_minutes, sessions, scope.

    Returns:
        The updated configuration.
    """
    return sched.update_config(
        enabled=body.get("enabled"),
        buffer_minutes=body.get("buffer_minutes"),
        sessions=body.get("sessions"),
        scope=body.get("scope"),
    )


@router.get("/schedule", summary="Get today's computed schedule")
async def get_schedule(
    current_user=Depends(get_current_user),
    sched: AutoTradingScheduler = Depends(_get_scheduler),
):
    """Return today's computed start/stop times.

    Returns:
        A list of session schedules with start/stop times.
    """
    return {"schedule": sched.get_schedule(), "config": sched.get_config()}
