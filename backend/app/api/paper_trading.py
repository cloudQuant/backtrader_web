"""
模拟交易 API 路由

提供完整的模拟交易功能
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.websockets import WebSocket, WebSocketDisconnect
import json

from app.schemas.paper_trading import (
    AccountCreate,
    AccountResponse,
    AccountListResponse,
    OrderRequest,
    OrderResponse,
    OrderListResponse,
    PositionResponse,
    PositionListResponse,
    TradeListResponse,
)
from app.services.paper_trading_service import PaperTradingService
from app.api.deps import get_current_user

router = APIRouter()


def get_paper_trading_service():
    return PaperTradingService()


# ==================== 模拟账户 API ====================

@router.post("/accounts", response_model=AccountResponse, summary="创建模拟账户")
async def create_paper_account(
    request: AccountCreate,
    current_user=Depends(get_current_user),
    service: PaperTradingService = Depends(get_paper_trading_service),
):
    """创建模拟交易账户"""
    account = await service.create_account(
        user_id=current_user.sub,
        name=request.name,
        initial_cash=request.initial_cash,
        commission_rate=request.commission_rate,
        slippage_rate=request.slippage_rate,
    )
    return account


@router.get("/accounts", response_model=AccountListResponse, summary="获取模拟账户列表")
async def list_paper_accounts(
    current_user=Depends(get_current_user),
    service: PaperTradingService = Depends(get_paper_trading_service),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """获取用户的模拟账户列表"""
    accounts, total = await service.list_accounts(
        user_id=current_user.sub,
        limit=limit,
        offset=offset,
    )
    return AccountListResponse(total=total, items=accounts)


@router.get("/accounts/{account_id}", response_model=AccountResponse, summary="获取模拟账户详情")
async def get_paper_account(
    account_id: str,
    current_user=Depends(get_current_user),
    service: PaperTradingService = Depends(get_paper_trading_service),
):
    """获取模拟账户详情"""
    account = await service.get_account(account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模拟账户不存在"
        )

    # 检查权限
    if account.user_id != current_user.sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问该账户"
        )

    return account


@router.delete("/accounts/{account_id}", summary="删除模拟账户")
async def delete_paper_account(
    account_id: str,
    current_user=Depends(get_current_user),
    service: PaperTradingService = Depends(get_paper_trading_service),
):
    """删除模拟账户"""
    success = await service.delete_account(account_id, current_user.sub)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模拟账户不存在或无权删除"
        )
    return {"message": "删除成功"}


# ==================== 模拟订单 API ====================

@router.post("/orders", response_model=OrderResponse, summary="提交模拟订单")
async def submit_paper_order(
    request: OrderRequest,
    current_user=Depends(get_current_user),
    service: PaperTradingService = Depends(get_paper_trading_service),
):
    """
    提交模拟交易订单
    
    订单类型：
    - market: 市价单
    - limit: 限价单
    - stop: 止损单
    - stop_limit: 止损限价单
    
    买卖方向：
    - buy: 买入（做多）
    - sell: 卖出（平多或做空）
    """
    order = await service.submit_order(
        user_id=current_user.sub,
        request=request,
    )
    return order


@router.get("/orders", response_model=OrderListResponse, summary="获取模拟订单列表")
async def list_paper_orders(
    current_user=Depends(get_current_user),
    service: PaperTradingService = Depends(get_paper_trading_service),
    account_id: Optional[str] = Query(None, description="账户 ID"),
    symbol: Optional[str] = Query(None, description="标的代码"),
    status: Optional[str] = Query(None, description="订单状态"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """获取模拟订单列表"""
    filters = {"user_id": current_user.sub}
    if account_id:
        filters["account_id"] = account_id
    if symbol:
        filters["symbol"] = symbol
    if status:
        filters["status"] = status

    orders, total = await service.list_orders(
        filters=filters,
        limit=limit,
        offset=offset,
    )
    return OrderListResponse(total=total, items=orders)


@router.get("/orders/{order_id}", response_model=OrderResponse, summary="获取模拟订单详情")
async def get_paper_order(
    order_id: str,
    current_user=Depends(get_current_user),
    service: PaperTradingService = Depends(get_paper_trading_service),
):
    """获取模拟订单详情"""
    order = await service.get_order(order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模拟订单不存在"
        )

    # 检查权限
    account = await service.get_account(order.account_id)
    if not account or account.user_id != current_user.sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问该订单"
        )

    return order


@router.delete("/orders/{order_id}", summary="撤销模拟订单")
async def cancel_paper_order(
    order_id: str,
    current_user=Depends(get_current_user),
    service: PaperTradingService = Depends(get_paper_trading_service),
):
    """撤销待成交的模拟订单"""
    success = await service.cancel_order(order_id, current_user.sub)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模拟订单不存在、已成交或无权撤销"
        )
    return {"message": "订单已撤销"}


# ==================== 模拟持仓 API ====================

@router.get("/positions", response_model=PositionListResponse, summary="获取模拟持仓列表")
async def list_paper_positions(
    current_user=Depends(get_current_user),
    service: PaperTradingService = Depends(get_paper_trading_service),
    account_id: Optional[str] = Query(None, description="账户 ID"),
    symbol: Optional[str] = Query(None, description="标的代码"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """获取模拟持仓列表"""
    filters = {"user_id": current_user.sub}
    if account_id:
        filters["account_id"] = account_id
    if symbol:
        filters["symbol"] = symbol

    positions, total = await service.list_positions(
        filters=filters,
        limit=limit,
        offset=offset,
    )
    return PositionListResponse(total=total, items=positions)


@router.get("/positions/{position_id}", response_model=PositionResponse, summary="获取模拟持仓详情")
async def get_paper_position(
    position_id: str,
    current_user=Depends(get_current_user),
    service: PaperTradingService = Depends(get_paper_trading_service),
):
    """获取模拟持仓详情"""
    position = await service.get_position(position_id)
    if not position:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模拟持仓不存在"
        )

    # 检查权限
    account = await service.get_account(position.account_id)
    if not account or account.user_id != current_user.sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问该持仓"
        )

    return position


# ==================== 模拟成交 API ====================

@router.get("/trades", response_model=TradeListResponse, summary="获取模拟成交列表")
async def list_paper_trades(
    current_user=Depends(get_current_user),
    service: PaperTradingService = Depends(get_paper_trading_service),
    account_id: Optional[str] = Query(None, description="账户 ID"),
    symbol: Optional[str] = Query(None, description="标的代码"),
    side: Optional[str] = Query(None, description="买卖方向"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """获取模拟成交列表"""
    filters = {"user_id": current_user.sub}
    if account_id:
        filters["account_id"] = account_id
    if symbol:
        filters["symbol"] = symbol
    if side:
        filters["side"] = side

    trades, total = await service.list_trades(
        filters=filters,
        limit=limit,
        offset=offset,
    )
    return TradeListResponse(total=total, items=trades)


# ==================== WebSocket 端点 ====================

@router.websocket("/ws/account/{account_id}")
async def websocket_account_endpoint(websocket: WebSocket, account_id: str):
    """
    WebSocket 端点 - 模拟交易实时推送

    推送内容：
    - 账户更新（资金、权益、盈亏）
    - 订单更新（状态、成交）
    - 持仓更新（数量、市值、未实现盈亏）
    - 成交更新（新成交）

    连接 URL: ws://host/api/v1/paper-trading/ws/account/{account_id}

    消息类型：
    - connected: 连接成功
    - account_update: 账户更新
    - order_update: 订单更新
    - position_update: 持仓更新
    - trade_update: 成交更新
    """
    from app.websocket_manager import manager as ws_manager, MessageType
    import asyncio

    # 验证账户存在
    service = PaperTradingService()
    account = await service.get_account(account_id)
    if not account:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    client_id = f"ws-client-{id(websocket)}"

    # 建立连接
    await ws_manager.connect(websocket, f"account:{account_id}", client_id)

    try:
        # 发送初始账户信息
        await ws_manager.send_to_task(f"account:{account_id}", {
            "type": MessageType.CONNECTED,
            "account_id": account_id,
            "message": "模拟交易 WebSocket 连接成功",
            "data": {
                "current_cash": account.current_cash,
                "total_equity": account.total_equity,
                "profit_loss": account.profit_loss,
                "profit_loss_pct": account.profit_loss_pct,
            },
        })

        # 保持连接并推送更新
        while True:
            await asyncio.sleep(1)

            # 这里应该从服务获取最新的账户、订单、持仓信息
            # 并通过 WebSocket 推送
            # 暂时使用轮询方式，实际应用中应该使用事件驱动

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, f"account:{account_id}", client_id)
    except Exception as e:
        import logging
        logging.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket, f"account:{account_id}", client_id)
