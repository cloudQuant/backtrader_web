"""
Realtime market data API routes.

Supports realtime tick subscription and WebSocket streaming across brokers.
"""
import asyncio
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
import logging

from app.schemas.realtime_data import (
    RealtimeTickSubscribeRequest,
    RealtimeTickUnsubscribeRequest,
    RealtimeHistoricalTickRequest,
    RealtimeTickResponse,
    RealtimeTickUpdate,
    RealtimeTickBatchResponse,
    RealtimeTickListResponse,
)
from app.services.realtime_data_service import RealTimeDataService
from app.api.deps import get_current_user
from app.websocket_manager import manager as ws_manager, MessageType

logger = logging.getLogger(__name__)

router = APIRouter()


def get_realtime_data_service():
    return RealTimeDataService()


# ==================== 实时行情订阅 API ====================

@router.post("/ticks/subscribe", summary="订阅实时行情")
async def subscribe_realtime_ticks(
    request: RealtimeTickSubscribeRequest,
    current_user=Depends(get_current_user),
    service: RealTimeDataService = Depends(get_realtime_data_service),
):
    """
    Subscribe to realtime ticks.
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
        "message": f"已订阅 {len(request.symbols)} 个标的的实时行情",
    }


@router.post("/ticks/unsubscribe", summary="取消订阅实时行情")
async def unsubscribe_realtime_ticks(
    request: RealtimeTickUnsubscribeRequest,
    current_user=Depends(get_current_user),
    service: RealTimeDataService = Depends(get_realtime_data_service),
):
    """
    Unsubscribe from realtime ticks.
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
        "message": f"已取消订阅 {len(request.symbols)} 个标的的实时行情",
    }


# ==================== 实时行情数据 API ====================

@router.get("/ticks", summary="获取实时行情")
async def get_realtime_ticks(
    current_user=Depends(get_current_user),
    service: RealTimeDataService = Depends(get_realtime_data_service),
    broker_id: Optional[str] = Query(None, description="券商 ID"),
    symbol: Optional[str] = Query(None, description="标的代码"),
):
    """
    Get the latest ticks (single symbol or all subscribed symbols).
    """
    if symbol:
        # 获取单个标的行情
        tick_data = await service.get_tick(current_user.sub, broker_id, symbol)
        return {"tick": tick_data}
    else:
        # 获取所有订阅标的行情
        symbols = await service.get_subscribed_symbols(current_user.sub, broker_id)
        ticks_data = await service.get_ticks(current_user.sub, broker_id, symbols)
        return {"ticks": ticks_data}


@router.get("/ticks/batch", summary="批量获取实时行情")
async def get_realtime_ticks_batch(
    current_user=Depends(get_current_user),
    service: RealTimeDataService = Depends(get_realtime_data_service),
    broker_id: str = Query(..., description="券商 ID"),
    symbols: str = Query(..., description="标的代码列表（逗号分隔）"),
):
    """
    Batch fetch ticks for a broker and a comma-separated symbol list.
    """
    symbol_list = symbols.split(',')
    ticks = await service.get_ticks(current_user.sub, broker_id, symbol_list)

    return {
        "broker_id": broker_id,
        "ticks": ticks,
    }


# ==================== 历史行情 API ====================

@router.get("/ticks/historical", summary="获取历史行情")
async def get_historical_ticks(
    broker_id: str = Query(..., description="券商 ID"),
    symbol: str = Query(..., description="标的代码（如 BTC/USDT）"),
    start_date: str = Query(..., description="开始日期（ISO 8601 格式）"),
    end_date: str = Query(..., description="结束日期（ISO 8601 格式）"),
    frequency: str = Query("1d", description="频率"),
    current_user=Depends(get_current_user),
    service: RealTimeDataService = Depends(get_realtime_data_service),
):
    """
    Get historical ticks for a symbol.
    """
    from datetime import datetime

    # 验证日期格式
    try:
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"日期格式错误: {e}"
        )

    ticks = await service.get_historical_data(
        user_id=current_user.sub,
        broker_id=broker_id,
        symbol=symbol,
        start_date=start_dt,
        end_date=end_dt,
        frequency=frequency,
    )

    return {
        "symbol": symbol,
        "frequency": frequency,
        "ticks": ticks,
        "total": len(ticks),
    }


# ==================== WebSocket 实时推送 ====================

@router.websocket("/ws/ticks/{broker_id}")
async def realtime_tick_websocket(
    websocket,
    broker_id: str,
):
    """
    WebSocket endpoint for realtime tick streaming.

    URL:
        ws://host/api/v1/realtime/ws/ticks/{broker_id}
    """
    client_id = f"ws-realtime-client-{id(websocket)}"

    # 建立连接
    await ws_manager.connect(websocket, f"ticks:{broker_id}", client_id)

    try:
        # 发送初始信息
        await ws_manager.send_to_task(f"ticks:{broker_id}", {
            "type": MessageType.CONNECTED,
            "broker_id": broker_id,
            "message": "实时行情 WebSocket 连接成功",
        })

        # 保持连接
        while True:
            await asyncio.sleep(1)

            # 这里应该从实时数据服务获取最新行情
            # 并通过 WebSocket 推送
            # 暂时使用轮询方式，实际应用中应该使用事件驱动

            # 模拟推送（实际应用中应该实时推送）
            # TODO: 集成 RealTimeDataService 的实时推送功能

    except Exception as e:
        logger.error(f"Realtime tick WebSocket error: {e}")
        ws_manager.disconnect(websocket, f"ticks:{broker_id}", client_id)
