"""AI Trading API routes for natural language driven trading.

Provides endpoints for:
- Sending natural language trading instructions
- Confirming pending trades
- Querying trading history
- Managing AI trading configuration
"""

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.schemas.ai_trading import (
    AITradingConfigResponse,
    AITradingRequest,
    AITradingResponse,
    TradeConfirmRequest,
    TradeConfirmResponse,
)
from app.schemas.auth import TokenPayload
from app.services.ai_trading_service import AITradingService, MissingGatewayContextError

router = APIRouter()


@lru_cache
def get_ai_trading_service() -> AITradingService:
    """Get or create the AI trading service singleton."""
    return AITradingService()


def _merge_selectable_accounts(
    paper_accounts: list[dict[str, Any]],
    gateways: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build account selector options from paper accounts and connected gateways."""
    accounts: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for account in paper_accounts:
        account_id = str(account.get("account_id") or "")
        if not account_id:
            continue
        item = {**account, "source": account.get("source") or "paper"}
        key = (str(item.get("source") or "paper"), account_id, str(item.get("gateway_id") or ""))
        if key not in seen:
            seen.add(key)
            accounts.append(item)

    for gateway in gateways:
        if not gateway.get("connected"):
            continue
        gateway_id = str(gateway.get("gateway_id") or "")
        account_id = str(gateway.get("account_id") or gateway_id)
        if not gateway_id or not account_id:
            continue
        exchange_type = str(gateway.get("exchange_type") or "")
        name = f"{exchange_type} · {account_id}" if exchange_type else account_id
        item = {
            "account_id": account_id,
            "name": name,
            "total_equity": None,
            "current_cash": None,
            "is_active": True,
            "source": "gateway",
            "gateway_id": gateway_id,
            "exchange_type": exchange_type,
            "connected": True,
        }
        key = ("gateway", account_id, gateway_id)
        if key not in seen:
            seen.add(key)
            accounts.append(item)

    return accounts


@router.post(
    "/execute",
    response_model=AITradingResponse,
    summary="Execute natural language trade",
)
async def execute_trade(
    request: AITradingRequest,
    current_user: TokenPayload = Depends(get_current_user),
    service: AITradingService = Depends(get_ai_trading_service),
):
    """Process a natural language trading instruction.

    The AI will:
    1. Parse the natural language into a structured trading intent
    2. Assess risk and validate against safety rules
    3. Execute immediately, queue for confirmation, or reject

    Args:
        request: The trading request with natural language message.
        current_user: The authenticated user.
        service: The AI trading service.

    Returns:
        AITradingResponse with parsed intent, risk assessment, and status.
    """
    try:
        result = await service.process_trading_request(
            user_id=current_user.sub,
            request=request,
        )
        return result
    except MissingGatewayContextError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.post(
    "/confirm",
    response_model=TradeConfirmResponse,
    summary="Confirm or reject pending trade",
)
async def confirm_trade(
    request: TradeConfirmRequest,
    current_user: TokenPayload = Depends(get_current_user),
    service: AITradingService = Depends(get_ai_trading_service),
):
    """Confirm or reject a trade that requires user confirmation.

    Args:
        request: Confirmation request with trade_id and decision.
        current_user: The authenticated user.
        service: The AI trading service.

    Returns:
        TradeConfirmResponse with execution result.
    """
    result = await service.confirm_trade(
        user_id=current_user.sub,
        request=request,
    )
    return result


@router.get(
    "/config",
    response_model=AITradingConfigResponse,
    summary="Get AI trading configuration",
)
async def get_config(
    current_user: TokenPayload = Depends(get_current_user),
    service: AITradingService = Depends(get_ai_trading_service),
):
    """Get the current AI trading configuration and limits.

    Returns:
        Current configuration including limits, available gateways, and mode.
    """
    config = service.risk_guard.config
    available_gateways = service.list_available_gateways()
    paper_accounts = await service.list_available_accounts(current_user.sub)
    available_accounts = _merge_selectable_accounts(paper_accounts, available_gateways)
    return AITradingConfigResponse(
        enabled=True,
        default_mode="paper",
        max_single_trade_amount=config.max_single_trade_amount,
        max_daily_trades=config.max_daily_trades,
        max_position_ratio=config.max_position_ratio,
        require_confirmation_above=config.require_confirmation_above,
        blocked_symbols=config.blocked_symbols,
        available_gateways=available_gateways,
        available_accounts=available_accounts,
    )


@router.get(
    "/history",
    summary="Get AI trading history",
)
async def get_history(
    limit: int = 20,
    current_user: TokenPayload = Depends(get_current_user),
    service: AITradingService = Depends(get_ai_trading_service),
):
    """Get the user's AI trading history.

    Args:
        limit: Maximum number of records to return.
        current_user: The authenticated user.
        service: The AI trading service.

    Returns:
        List of recent AI trading log entries.
    """
    items = await service.get_history(user_id=current_user.sub, limit=limit)
    return {"total": len(items), "items": items}


@router.post(
    "/reflect/{trade_id}",
    summary="Generate AI reflection on a trade",
)
async def reflect_on_trade(
    trade_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    service: AITradingService = Depends(get_ai_trading_service),
):
    """Generate AI reflection and lessons learned for a completed trade.

    Args:
        trade_id: The trade ID to reflect on.
        current_user: The authenticated user.
        service: The AI trading service.

    Returns:
        Reflection analysis with suggestions for improvement.
    """
    result = await service.generate_reflection(
        trade_id=trade_id,
        user_id=current_user.sub,
    )
    return result


@router.post(
    "/conditional-orders",
    summary="Create a conditional (trigger) order",
)
async def create_conditional_order(
    condition: str,
    action_message: str,
    gateway_id: str | None = None,
    dry_run: bool = True,
    expiry_hours: float = 24.0,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Create a conditional order that triggers when a condition is met.

    创建条件单，当条件满足时自动触发交易。

    Examples:
    - condition: "BTC drops to 60000 / BTC跌到60000", action_message: "Buy 0.1 BTC / 买入0.1个BTC"
    - condition: "Rebar rises to 4000 / 螺纹钢涨到4000", action_message: "Sell 1 lot rebar / 卖出1手螺纹钢"

    Args:
        condition: Natural language condition description.
        action_message: The trade to execute when triggered.
        gateway_id: Optional gateway for execution.
        dry_run: Whether to use paper trading.
        expiry_hours: Hours until the order expires (default 24h).
        current_user: The authenticated user.

    Returns:
        The created conditional order.
    """
    from app.services.ai_trading_service import get_conditional_order_manager

    manager = get_conditional_order_manager()
    result = manager.create_conditional_order(
        user_id=current_user.sub,
        condition=condition,
        action_message=action_message,
        gateway_id=gateway_id,
        dry_run=dry_run,
        expiry_hours=expiry_hours,
    )
    return result


@router.get(
    "/conditional-orders",
    summary="List conditional orders",
)
async def list_conditional_orders(
    current_user: TokenPayload = Depends(get_current_user),
):
    """List all conditional orders for the current user."""
    from app.services.ai_trading_service import get_conditional_order_manager

    manager = get_conditional_order_manager()
    items = manager.list_conditional_orders(current_user.sub)
    return {"total": len(items), "items": items}


@router.delete(
    "/conditional-orders/{order_id}",
    summary="Cancel a conditional order",
)
async def cancel_conditional_order(
    order_id: str,
    current_user: TokenPayload = Depends(get_current_user),
):
    """Cancel an active conditional order."""
    from app.services.ai_trading_service import get_conditional_order_manager

    manager = get_conditional_order_manager()
    success = manager.cancel_conditional_order(order_id, current_user.sub)
    if not success:
        return {
            "success": False,
            "message": "Conditional order not found or no permission / 条件单不存在或无权操作",
        }
    return {"success": True, "message": "Conditional order cancelled / 条件单已取消"}
