"""
Shared utilities and dependencies for live trading and simulation API routes.

Both modules use the same LiveTradingManager and log directory resolution logic.
"""

from pathlib import Path

from fastapi import HTTPException

from app.services.live_trading_manager import LiveTradingManager, get_live_trading_manager
from app.services.log_parser_service import find_latest_log_dir
from app.services.strategy_service import get_strategy_dir


def get_live_trading_manager_dep() -> LiveTradingManager:
    """Dependency: get the global LiveTradingManager instance.

    Used by live_trading_api, simulation, and portfolio_api routers.

    Returns:
        The global LiveTradingManager instance.
    """
    return get_live_trading_manager()


def get_strategy_log_dir(mgr: LiveTradingManager, instance_id: str, user_id: str) -> Path:
    """Get the latest log directory for a strategy instance.

    Args:
        mgr: The live trading manager instance.
        instance_id: The ID of the instance.
        user_id: User ID for permission check.

    Returns:
        The path to the log directory.

    Raises:
        HTTPException: If the instance or log directory is not found.
    """
    inst = mgr.get_instance(instance_id, user_id=user_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Instance not found")
    try:
        strategy_dir = get_strategy_dir(inst["strategy_id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    log_dir = find_latest_log_dir(strategy_dir)
    if not log_dir:
        raise HTTPException(
            status_code=404, detail="No log data available, please run the strategy first"
        )
    return log_dir
