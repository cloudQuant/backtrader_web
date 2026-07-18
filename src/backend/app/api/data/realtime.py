"""
Realtime market data API routes.

Supports realtime tick subscription and WebSocket streaming across brokers.
"""

import asyncio
import logging
import typing

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from app.api.deps import get_current_user, get_websocket_current_user
from app.schemas.realtime_data import (
    RealtimeTickSubscribeRequest,
    RealtimeTickUnsubscribeRequest,
)
from app.services.realtime_data_service import RealTimeDataService
from app.websocket_manager import MessageType
from app.websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


def get_realtime_data_service() -> typing.Any:
    """Dependency injection for RealTimeDataService.

    Returns:
        RealTimeDataService: An instance of the realtime data service.
    """
    return RealTimeDataService()


# ==================== Realtime Quote Subscription API ====================


@router.post("/ticks/subscribe", summary="Subscribe to realtime quotes", response_model=None)
async def subscribe_realtime_ticks(
    request: RealtimeTickSubscribeRequest,
    current_user: typing.Any = Depends(get_current_user),
    service: RealTimeDataService = Depends(get_realtime_data_service),
) -> typing.Any:
    """Subscribe to realtime tick data for specified symbols.

    Args:
        request: The subscription request containing broker_id and symbols list.
        current_user: The authenticated user.
        service: The realtime data service.

    Returns:
        A dictionary confirming subscription with symbols, broker_id, and status.
    """
    await service.subscribe_ticks(
        user_id=current_user.sub,
        broker_id=request.broker_id,
        symbols=request.symbols,
    )

    return {
        "symbols": request.symbols,
        "broker_id": request.broker_id,
        "status": "subscribed",
        "message": f"Subscribed to {len(request.symbols)} symbols for realtime quotes",
    }


@router.post("/ticks/unsubscribe", summary="Unsubscribe from realtime quotes", response_model=None)
async def unsubscribe_realtime_ticks(
    request: RealtimeTickUnsubscribeRequest,
    current_user: typing.Any = Depends(get_current_user),
    service: RealTimeDataService = Depends(get_realtime_data_service),
) -> typing.Any:
    """Unsubscribe from realtime tick data for specified symbols.

    Args:
        request: The unsubscription request containing broker_id and symbols list.
        current_user: The authenticated user.
        service: The realtime data service.

    Returns:
        A dictionary confirming unsubscription with symbols, broker_id, and status.
    """
    await service.unsubscribe_ticks(
        user_id=current_user.sub,
        broker_id=request.broker_id,
        symbols=request.symbols,
    )

    return {
        "symbols": request.symbols,
        "broker_id": request.broker_id,
        "status": "unsubscribed",
        "message": f"Unsubscribed from {len(request.symbols)} symbols",
    }


# ==================== Realtime Quote Data API ====================


@router.get("/ticks", summary="Get realtime quotes", response_model=None)
async def get_realtime_ticks(
    current_user: typing.Any = Depends(get_current_user),
    service: RealTimeDataService = Depends(get_realtime_data_service),
    broker_id: str | None = Query(None, description="Broker ID"),
    symbol: str | None = Query(None, description="Trading symbol"),
) -> typing.Any:
    """Get the latest tick data (single symbol or all subscribed symbols).

    Args:
        current_user: The authenticated user.
        service: The realtime data service.
        broker_id: Filter by broker ID.
        symbol: Get specific symbol data if provided.

    Returns:
        A dictionary containing tick data for the requested symbols.
    """
    if symbol:
        # Get single symbol quote
        tick_data = await service.get_tick(current_user.sub, broker_id, symbol)
        return {"tick": tick_data}
    else:
        # Get all subscribed symbols quotes
        symbols = await service.get_subscribed_symbols(current_user.sub, broker_id)
        ticks_data = await service.get_ticks(current_user.sub, broker_id, symbols)
        return {"ticks": ticks_data}


@router.get("/ticks/batch", summary="Batch get realtime quotes", response_model=None)
async def get_realtime_ticks_batch(
    current_user: typing.Any = Depends(get_current_user),
    service: RealTimeDataService = Depends(get_realtime_data_service),
    broker_id: str = Query(..., description="Broker ID"),
    symbols: str = Query(..., description="Comma-separated symbol list"),
) -> typing.Any:
    """Batch fetch tick data for a broker and comma-separated symbol list.

    Args:
        current_user: The authenticated user.
        service: The realtime data service.
        broker_id: The broker ID to fetch data from.
        symbols: Comma-separated list of symbols to fetch.

    Returns:
        A dictionary containing broker_id and list of tick data.
    """
    symbol_list = symbols.split(",")
    ticks = await service.get_ticks(current_user.sub, broker_id, symbol_list)

    return {
        "broker_id": broker_id,
        "ticks": ticks,
    }


# ==================== Historical Quote API ====================


@router.get("/ticks/historical", summary="Get historical quotes", response_model=None)
async def get_historical_ticks(
    broker_id: str = Query(..., description="Broker ID"),
    symbol: str = Query(..., description="Trading symbol (e.g., BTC/USDT)"),
    start_date: str = Query(..., description="Start date (ISO 8601 format)"),
    end_date: str = Query(..., description="End date (ISO 8601 format)"),
    frequency: str = Query("1d", description="Data frequency"),
    current_user: typing.Any = Depends(get_current_user),
    service: RealTimeDataService = Depends(get_realtime_data_service),
) -> typing.Any:
    """Get historical tick data for a symbol.

    Args:
        broker_id: The broker ID to fetch data from.
        symbol: The trading symbol (e.g., BTC/USDT).
        start_date: Start date in ISO 8601 format.
        end_date: End date in ISO 8601 format.
        frequency: Data frequency (e.g., 1m, 5m, 1h, 1d).
        current_user: The authenticated user.
        service: The realtime data service.

    Returns:
        A dictionary containing symbol, frequency, ticks list, and total count.

    Raises:
        HTTPException: If date format is invalid (400).
    """
    from datetime import datetime

    # Validate date format
    try:
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid date format: {e}"
        ) from e

    try:
        ticks = await service.get_historical_data(
            user_id=current_user.sub,
            broker_id=broker_id,
            symbol=symbol,
            start_date=start_dt,
            end_date=end_dt,
            frequency=frequency,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {
        "symbol": symbol,
        "frequency": frequency,
        "ticks": ticks,
        "total": len(ticks),
    }


# ==================== WebSocket Real-time Push ====================


@router.websocket("/ws/ticks/{broker_id}")
async def realtime_tick_websocket(
    websocket: WebSocket,
    broker_id: str,
) -> typing.Any:
    """WebSocket endpoint for realtime tick streaming.

    URL:
        ws://host/api/v1/realtime/ws/ticks/{broker_id}

    Args:
        websocket: The WebSocket connection instance.
        broker_id: The broker ID for which to stream tick data.
    """
    current_user, accepted_subprotocol = get_websocket_current_user(websocket)
    if current_user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    client_id = f"ws-realtime-client-{id(websocket)}"
    channel = f"ticks:{current_user.sub}:{broker_id}"

    # Establish connection
    await ws_manager.connect(websocket, channel, client_id, accepted_subprotocol)

    try:
        # Send initial message
        await ws_manager.send_to_task(
            channel,
            {
                "type": MessageType.CONNECTED,
                "broker_id": broker_id,
                "streaming_enabled": False,
                "push_mode": "keepalive_only",
                "message": "Realtime quote WebSocket connected; live tick push is not available yet",
            },
        )

        # Keep connection alive
        while True:
            await asyncio.sleep(1)

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Realtime tick WebSocket error for broker %s", broker_id)
    finally:
        ws_manager.disconnect(websocket, channel, client_id)
