"""
Live trading API routes (full version).

Based on Backtrader's Cerebro + Store + Broker architecture.
"""

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.deps import get_current_user, mark_deprecated
from app.schemas.live_trading import (
    LiveTradingDataResponse,
    LiveTradingSubmitRequest,
    LiveTradingTaskListResponse,
    LiveTradingTaskResponse,
)
from app.services.live_trading_service import LiveTradingService
from app.websocket_manager import MessageType
from app.websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(deprecated=True)
_DEPRECATED_SUCCESSOR = "/api/v1/live-trading"


def get_live_trading_service():
    """Dependency injection for LiveTradingService.

    Returns:
        LiveTradingService: An instance of the live trading service.
    """
    return LiveTradingService()


# ==================== Live Trading Strategy Submission API ====================


@router.post(
    "/live/submit", response_model=LiveTradingTaskResponse, summary="Submit live trading strategy"
)
async def submit_live_strategy(
    request: LiveTradingSubmitRequest,
    response: Response,
    current_user=Depends(get_current_user),
    service: LiveTradingService = Depends(get_live_trading_service),
):
    """Submit a live trading strategy and start execution.

    .. deprecated:: 1.0.0
        Use :func:`app.api.live_trading_api` instead.
    """
    mark_deprecated(response, _DEPRECATED_SUCCESSOR, "live-trading-crypto")
    task_id = await service.start_live_trading(
        user_id=current_user.sub,
        strategy_name=request.strategy_name,
        strategy_code=request.strategy_code,
        exchange=request.exchange,
        symbols=request.symbols,
        initial_cash=request.initial_cash,
        strategy_params=request.strategy_params,
        timeframe=request.timeframe,
        start_date=request.start_date,
        end_date=request.end_date,
        api_key=request.api_key,
        secret=request.secret,
        sandbox=request.sandbox,
    )

    # Return response matching LiveTradingTaskResponse schema
    return LiveTradingTaskResponse(
        task_id=task_id,
        user_id=current_user.sub,
        status="submitted",
        config=request.model_dump(),
        created_at=datetime.now(),
    )


# ==================== Live Task Management API ====================


@router.get(
    "/live/tasks", response_model=LiveTradingTaskListResponse, summary="List live trading tasks"
)
async def list_live_tasks(
    response: Response,
    current_user=Depends(get_current_user),
    service: LiveTradingService = Depends(get_live_trading_service),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Get the current user's live trading task list.

    .. deprecated:: 1.0.0
        Use :func:`app.api.live_trading_api` instead.
    """
    mark_deprecated(response, _DEPRECATED_SUCCESSOR, "live-trading-crypto")
    tasks = await service.list_tasks(current_user.sub)

    return {
        "tasks": tasks,
        "total": len(tasks),
    }


@router.get(
    "/live/tasks/{task_id}",
    response_model=LiveTradingTaskResponse,
    summary="Get live trading task status",
)
async def get_live_task_status(
    task_id: str,
    response: Response,
    current_user=Depends(get_current_user),
    service: LiveTradingService = Depends(get_live_trading_service),
):
    """Get the status of a live trading task.

    .. deprecated:: 1.0.0
        Use :func:`app.api.live_trading_api` instead.
    """
    mark_deprecated(response, _DEPRECATED_SUCCESSOR, "live-trading-crypto")
    task = await service.get_task_status(task_id, current_user.sub)

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Live trading task not found"
        )

    return task


# ==================== Live Task Control API ====================


@router.post("/live/tasks/{task_id}/stop", summary="Stop live trading task")
async def stop_live_strategy(
    task_id: str,
    response: Response,
    current_user=Depends(get_current_user),
    service: LiveTradingService = Depends(get_live_trading_service),
):
    """Stop a running live trading strategy.

    .. deprecated:: 1.0.0
        Use :func:`app.api.live_trading_api` instead.
    """
    mark_deprecated(response, _DEPRECATED_SUCCESSOR, "live-trading-crypto")
    success = await service.stop_live_trading(task_id, current_user.sub)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Live trading task not found or no permission to stop",
        )

    # Push stop notification
    await ws_manager.send_to_task(
        f"live:{task_id}",
        {
            "type": MessageType.PROGRESS,
            "task_id": task_id,
            "message": "Live trading task has been stopped",
        },
    )

    return {"message": "Live trading task has been stopped"}


# ==================== Live Trading Data API ====================


@router.get(
    "/live/tasks/{task_id}/data",
    response_model=LiveTradingDataResponse,
    summary="Get live trading data",
)
async def get_live_trading_data(
    task_id: str,
    response: Response,
    current_user=Depends(get_current_user),
    service: LiveTradingService = Depends(get_live_trading_service),
):
    """Get live trading data including account, positions, orders, and trades.

    .. deprecated:: 1.0.0
        Use :func:`app.api.live_trading_api` instead.
    """
    mark_deprecated(response, _DEPRECATED_SUCCESSOR, "live-trading-crypto")
    task_status = await service.get_task_status(task_id, current_user.sub)
    if not task_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Live trading task not found"
        )

    data = await service.get_task_data(task_id)

    # Return response matching LiveTradingDataResponse schema
    # data should contain: cash, value, positions, orders
    return LiveTradingDataResponse(
        task_id=task_id,
        status=task_status.get("status", "stopped")
        if isinstance(task_status, dict)
        else getattr(task_status, "status", "stopped"),
        cash=data.get("cash", 0.0) if isinstance(data, dict) else getattr(data, "cash", 0.0),
        value=data.get("value", 0.0) if isinstance(data, dict) else getattr(data, "value", 0.0),
        positions=data.get("positions", [])
        if isinstance(data, dict)
        else getattr(data, "positions", []),
        orders=data.get("orders", []) if isinstance(data, dict) else getattr(data, "orders", []),
    )


# ==================== WebSocket Real-time Push ====================


@router.websocket("/ws/live/{task_id}")
async def live_trading_websocket(
    websocket,
    task_id: str,
):
    """WebSocket endpoint for live trading real-time updates.

    Pushes:
        - Account updates (cash, equity)
        - Position updates (quantity, market value, PnL)
        - Order updates (status, fills)
        - Trade updates
        - Strategy signals (buy, sell)
        - Market data updates

    Connection URL: ws://host/api/v1/live-trading/ws/live/{task_id}

    Message types:
        - connected: Connection successful
        - account_update: Account data update
        - position_update: Position data update
        - order_update: Order status update
        - trade_update: New trade notification
        - signal_update: Strategy signal
        - tick_update: Market data update

    Args:
        websocket: The WebSocket connection instance.
        task_id: The unique identifier of the live trading task.
    """
    client_id = f"ws-live-client-{id(websocket)}"

    # Establish connection
    await ws_manager.connect(websocket, f"live:{task_id}", client_id)

    try:
        # Send initial message
        await ws_manager.send_to_task(
            f"live:{task_id}",
            {
                "type": MessageType.CONNECTED,
                "task_id": task_id,
                "message": "Live trading WebSocket connection successful",
            },
        )

        # Keep connection alive and push updates
        while True:
            await asyncio.sleep(1)

            # Latest data should be fetched from backtrader live module
            # and pushed via WebSocket
            # Temporarily using polling; should use event-driven in production

    except Exception as e:
        logger.error(f"Live trading WebSocket error: {e}")
        ws_manager.disconnect(websocket, f"live:{task_id}", client_id)
