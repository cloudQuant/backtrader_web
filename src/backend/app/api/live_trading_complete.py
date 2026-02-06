"""
实盘交易 API 路由（完整版）

基于 backtrader 的完整架构，使用 Cerebro + Store + Broker
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
import logging

from app.schemas.live_trading import (
    LiveTradingSubmitRequest,
    LiveTradingTaskResponse,
    LiveTradingTaskListResponse,
    LiveTradingDataResponse,
    LiveAccountInfo,
    LiveTradingPosition,
    LiveTradingOrder,
    LiveTradingTrade,
)
from app.services.live_trading_service import LiveTradingService
from app.api.deps import get_current_user
from app.websocket_manager import manager as ws_manager, MessageType

logger = logging.getLogger(__name__)

router = APIRouter()


def get_live_trading_service():
    return LiveTradingService()


# ==================== 实盘策略提交 API ====================

@router.post("/live/submit", response_model=LiveTradingTaskResponse, summary="提交实盘交易策略")
async def submit_live_strategy(
    request: LiveTradingSubmitRequest,
    current_user=Depends(get_current_user),
    service: LiveTradingService = Depends(get_live_trading_service),
):
    """
    提交实盘交易策略并运行
    
    请求体：
    - strategy_name: 策略名称（内置策略：SMACross, etc.）
    - strategy_code: 策略代码
    - exchange: 交易所
    - symbols: 标的列表
    - initial_cash: 初始资金
    - strategy_params: 策略参数
    - timeframe: 时间周期
    - start_date: 开始时间
    - end_date: 结束时间
    - api_key: API Key
    - secret: Secret Key
    - sandbox: 是否测试环境
    """
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

    # 推送任务创建通知
    await ws_manager.send_to_task(f"user:{current_user.sub}:live", {
        "type": MessageType.PROGRESS,
        "task_id": task_id,
        "message": "实盘交易策略已提交",
        "data": request.model_dump(),
    })

    return {
        "task_id": task_id,
        "status": "submitted",
        "message": "实盘交易策略已提交",
    }


# ==================== 实盘任务管理 API ====================

@router.get("/live/tasks", response_model=LiveTradingTaskListResponse, summary="获取实盘交易任务列表")
async def list_live_tasks(
    current_user=Depends(get_current_user),
    service: LiveTradingService = Depends(get_live_trading_service),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """获取用户的实盘交易任务列表"""
    tasks, total = await service.list_tasks(
        user_id=current_user.sub,
        limit=limit,
        offset=offset,
    )

    return LiveTradingTaskListResponse(total=total, items=tasks)


@router.get("/live/tasks/{task_id}", response_model=LiveTradingTaskResponse, summary="获取实盘交易任务状态")
async def get_live_task_status(
    task_id: str,
    current_user=Depends(get_current_user),
    service: LiveTradingService = Depends(get_live_trading_service),
):
    """获取实盘交易任务状态"""
    task = await service.get_task_status(current_user.sub, task_id)

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="实盘交易任务不存在"
        )

    return task


# ==================== 实盘任务控制 API ====================

@router.post("/live/tasks/{task_id}/stop", summary="停止实盘交易任务")
async def stop_live_strategy(
    task_id: str,
    current_user=Depends(get_current_user),
    service: LiveTradingService = Depends(get_live_trading_service),
):
    """停止实盘交易策略"""
    success = await service.stop_live_trading(task_id, current_user.sub)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="实盘交易任务不存在或无权停止"
        )

    # 推送停止通知
    await ws_manager.send_to_task(f"live:{task_id}", {
        "type": MessageType.PROGRESS,
        "task_id": task_id,
        "message": "实盘交易任务已停止",
    })

    return {"message": "实盘交易任务已停止"}


# ==================== 实盘交易数据 API ====================

@router.get("/live/tasks/{task_id}/data", response_model=LiveTradingDataResponse, summary="获取实盘交易数据")
async def get_live_trading_data(
    task_id: str,
    current_user=Depends(get_current_user),
    service: LiveTradingService = Depends(get_live_trading_service),
):
    """
    获取实盘交易数据（账户、持仓、订单、成交）
    """
    status = await service.get_task_status(current_user.sub, task_id)
    data = await service.get_task_data(task_id)

    return {
        "task_id": task_id,
        "status": status.get("status", "stopped"),
        "data": data,
    }


# ==================== WebSocket 端点 ====================

@router.websocket("/ws/live/{task_id}")
async def live_trading_websocket(
    websocket,
    task_id: str,
):
    """
    WebSocket 端点 - 实盘交易实时推送
    
    推送内容：
    - 账户更新（现金、权益）
    - 持仓更新（数量、市值、盈亏）
    - 订单更新（状态、成交）
    - 成交更新
    - 策略信号（买入、卖出）
    - 行情更新
    
    连接 URL: ws://host/api/v1/live-trading/ws/live/{task_id}
    
    消息类型：
    - connected: 连接成功
    - account_update: 账户更新
    - position_update: 持仓更新
    - order_update: 订单更新
    - trade_update: 成交更新
    - signal_update: 策略信号
    - tick_update: 行情更新
    """
    client_id = f"ws-live-client-{id(websocket)}"

    # 建立连接
    await ws_manager.connect(websocket, f"live:{task_id}", client_id)

    try:
        # 发送初始信息
        await ws_manager.send_to_task(f"live:{task_id}", {
            "type": MessageType.CONNECTED,
            "task_id": task_id,
            "message": "实盘交易 WebSocket 连接成功",
        })

        # 保持连接并推送更新
        while True:
            await asyncio.sleep(1)

            # 这里应该从 backtrader 实盘模块获取最新数据
            # 并通过 WebSocket 推送
            # 暂时使用轮询方式，实际应用中应该使用事件驱动

    except Exception as e:
        logger.error(f"Live trading WebSocket error: {e}")
        ws_manager.disconnect(websocket, f"live:{task_id}", client_id)
