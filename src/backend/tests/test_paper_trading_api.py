"""Unit tests for app/api/paper_trading.py.

Tests cover all paper trading endpoints with mocked service layer:
- Account CRUD (create, list, get, delete)
- Order management (submit, list, get, cancel)
- Position queries (list, get)
- Trade history (list)
- Permission checks (403 for unauthorized access)
- Error cases (404 for missing resources)
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

_USER = SimpleNamespace(sub="u1")
_OTHER_USER = SimpleNamespace(sub="u2")


def _make_account(account_id="acct-1", user_id="u1"):
    """Create a mock paper trading account."""
    return SimpleNamespace(
        id=account_id,
        user_id=user_id,
        name="Test Account",
        initial_cash=100000.0,
        current_cash=95000.0,
        total_equity=105000.0,
        commission_rate=0.001,
        slippage_rate=0.0005,
        profit_loss=5000.0,
        profit_loss_pct=5.0,
        created_at="2024-01-01T00:00:00Z",
    )


def _make_order(order_id="ord-1", account_id="acct-1"):
    """Create a mock paper trading order."""
    return SimpleNamespace(
        id=order_id,
        account_id=account_id,
        symbol="BTC/USDT",
        side="buy",
        order_type="limit",
        quantity=0.5,
        price=60000.0,
        status="pending",
        created_at="2024-01-01T00:00:00Z",
    )


def _make_position(position_id="pos-1", account_id="acct-1"):
    """Create a mock paper trading position."""
    return SimpleNamespace(
        id=position_id,
        account_id=account_id,
        symbol="BTC/USDT",
        quantity=0.5,
        avg_price=60000.0,
        market_value=31000.0,
        unrealized_pnl=1000.0,
    )


def _make_trade(trade_id="trd-1"):
    """Create a mock paper trading trade."""
    return SimpleNamespace(
        id=trade_id,
        account_id="acct-1",
        order_id="ord-1",
        symbol="BTC/USDT",
        side="buy",
        quantity=0.5,
        price=60000.0,
        commission=30.0,
        executed_at="2024-01-01T12:00:00Z",
    )


class _MockService:
    """Mock PaperTradingService."""

    def __init__(self):
        self.create_account = AsyncMock(return_value=_make_account())
        self.list_accounts = AsyncMock(return_value=([_make_account()], 1))
        self.get_account = AsyncMock(return_value=_make_account())
        self.delete_account = AsyncMock(return_value=True)
        self.submit_order = AsyncMock(return_value=_make_order())
        self.list_orders = AsyncMock(return_value=([_make_order()], 1))
        self.get_order = AsyncMock(return_value=_make_order())
        self.cancel_order = AsyncMock(return_value=True)
        self.list_positions = AsyncMock(return_value=([_make_position()], 1))
        self.get_position = AsyncMock(return_value=_make_position())
        self.list_trades = AsyncMock(return_value=([_make_trade()], 1))


# ══════════════════════════════════════════════════════════════════════════════
# Account CRUD
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_paper_account():
    """Create account returns created entity."""
    from app.api.paper_trading import create_paper_account

    svc = _MockService()
    request = SimpleNamespace(
        name="My Account",
        initial_cash=100000.0,
        commission_rate=0.001,
        slippage_rate=0.0005,
    )
    result = await create_paper_account(request=request, current_user=_USER, service=svc)
    assert result.id == "acct-1"
    svc.create_account.assert_called_once_with(
        user_id="u1",
        name="My Account",
        initial_cash=100000.0,
        commission_rate=0.001,
        slippage_rate=0.0005,
    )


@pytest.mark.asyncio
async def test_list_paper_accounts():
    """List accounts calls service with correct params and returns response."""
    from datetime import datetime, timezone

    from app.api.paper_trading import list_paper_accounts
    from app.schemas.paper_trading import AccountResponse

    svc = _MockService()
    acct = AccountResponse(
        id="acct-1", user_id="u1", name="Test", initial_cash=100000,
        current_cash=95000, total_equity=105000, profit_loss=5000,
        profit_loss_pct=5.0, commission_rate=0.001, slippage_rate=0.0005,
        is_active=True, created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    svc.list_accounts = AsyncMock(return_value=([acct], 1))
    result = await list_paper_accounts(current_user=_USER, service=svc, limit=20, offset=0)
    assert result.total == 1
    assert len(result.items) == 1
    svc.list_accounts.assert_called_once_with(user_id="u1", limit=20, offset=0)


@pytest.mark.asyncio
async def test_get_paper_account_success():
    """Get account returns entity for owner."""
    from app.api.paper_trading import get_paper_account

    svc = _MockService()
    result = await get_paper_account(account_id="acct-1", current_user=_USER, service=svc)
    assert result.id == "acct-1"


@pytest.mark.asyncio
async def test_get_paper_account_not_found():
    """Get account raises 404 when not found."""
    from app.api.paper_trading import get_paper_account

    svc = _MockService()
    svc.get_account = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc_info:
        await get_paper_account(account_id="missing", current_user=_USER, service=svc)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_paper_account_forbidden():
    """Get account raises 403 when user doesn't own it."""
    from app.api.paper_trading import get_paper_account

    svc = _MockService()
    with pytest.raises(HTTPException) as exc_info:
        await get_paper_account(account_id="acct-1", current_user=_OTHER_USER, service=svc)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_delete_paper_account_success():
    """Delete account returns success message."""
    from app.api.paper_trading import delete_paper_account

    svc = _MockService()
    result = await delete_paper_account(account_id="acct-1", current_user=_USER, service=svc)
    assert result["message"] == "Account deleted successfully"


@pytest.mark.asyncio
async def test_delete_paper_account_not_found():
    """Delete account raises 404 when not found or no permission."""
    from app.api.paper_trading import delete_paper_account

    svc = _MockService()
    svc.delete_account = AsyncMock(return_value=False)
    with pytest.raises(HTTPException) as exc_info:
        await delete_paper_account(account_id="missing", current_user=_USER, service=svc)
    assert exc_info.value.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# Order Management
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_submit_paper_order():
    """Submit order verifies account ownership then unpacks the request to the service."""
    from app.api.paper_trading import submit_paper_order

    svc = _MockService()
    request = SimpleNamespace(
        account_id="acct-1",
        symbol="000001.SZ",
        side="buy",
        order_type="limit",
        size=100,
        price=10.5,
        stop_price=None,
        limit_price=None,
    )
    result = await submit_paper_order(request=request, current_user=_USER, service=svc)
    assert result.id == "ord-1"
    svc.get_account.assert_awaited_once_with("acct-1")
    svc.submit_order.assert_called_once_with(
        account_id="acct-1",
        symbol="000001.SZ",
        order_type="limit",
        side="buy",
        size=100,
        price=10.5,
        stop_price=None,
        limit_price=None,
    )


@pytest.mark.asyncio
async def test_submit_paper_order_rejects_foreign_account():
    """Submitting against another user's account returns 404."""
    from app.api.paper_trading import submit_paper_order

    svc = _MockService()
    svc.get_account = AsyncMock(return_value=_make_account(user_id="someone-else"))
    request = SimpleNamespace(
        account_id="acct-1",
        symbol="000001.SZ",
        side="buy",
        order_type="market",
        size=100,
        price=None,
        stop_price=None,
        limit_price=None,
    )
    with pytest.raises(HTTPException) as exc:
        await submit_paper_order(request=request, current_user=_USER, service=svc)
    assert exc.value.status_code == 404
    svc.submit_order.assert_not_called()


@pytest.mark.asyncio
async def test_list_paper_orders_no_filters():
    """List orders without filters calls service with user_id only."""
    from app.api.paper_trading import list_paper_orders

    svc = _MockService()
    # Skip response model validation — just verify service call
    svc.list_orders = AsyncMock(return_value=([], 0))
    result = await list_paper_orders(
        current_user=_USER, service=svc,
        account_id=None, symbol=None, status=None,
        limit=20, offset=0,
    )
    assert result.total == 0
    svc.list_orders.assert_called_once_with(
        filters={"user_id": "u1"}, limit=20, offset=0
    )


@pytest.mark.asyncio
async def test_list_paper_orders_with_filters():
    """List orders with filters passes them to service."""
    from app.api.paper_trading import list_paper_orders

    svc = _MockService()
    svc.list_orders = AsyncMock(return_value=([], 0))
    await list_paper_orders(
        current_user=_USER, service=svc,
        account_id="acct-1", symbol="BTC/USDT", status="pending",
        limit=10, offset=5,
    )
    svc.list_orders.assert_called_once_with(
        filters={
            "user_id": "u1",
            "account_id": "acct-1",
            "symbol": "BTC/USDT",
            "status": "pending",
        },
        limit=10, offset=5,
    )


@pytest.mark.asyncio
async def test_get_paper_order_success():
    """Get order returns entity for owner."""
    from app.api.paper_trading import get_paper_order

    svc = _MockService()
    result = await get_paper_order(order_id="ord-1", current_user=_USER, service=svc)
    assert result.id == "ord-1"


@pytest.mark.asyncio
async def test_get_paper_order_not_found():
    """Get order raises 404 when not found."""
    from app.api.paper_trading import get_paper_order

    svc = _MockService()
    svc.get_order = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc_info:
        await get_paper_order(order_id="missing", current_user=_USER, service=svc)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_paper_order_forbidden():
    """Get order raises 403 when user doesn't own the account."""
    from app.api.paper_trading import get_paper_order

    svc = _MockService()
    # get_account returns account owned by u1, but current_user is u2
    with pytest.raises(HTTPException) as exc_info:
        await get_paper_order(order_id="ord-1", current_user=_OTHER_USER, service=svc)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_get_paper_order_account_not_found():
    """Get order raises 403 when account lookup returns None."""
    from app.api.paper_trading import get_paper_order

    svc = _MockService()
    svc.get_account = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc_info:
        await get_paper_order(order_id="ord-1", current_user=_USER, service=svc)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_cancel_paper_order_success():
    """Cancel order returns success message."""
    from app.api.paper_trading import cancel_paper_order

    svc = _MockService()
    result = await cancel_paper_order(order_id="ord-1", current_user=_USER, service=svc)
    assert result["message"] == "Order has been cancelled"


@pytest.mark.asyncio
async def test_cancel_paper_order_not_found():
    """Cancel order raises 404 when not found or already filled."""
    from app.api.paper_trading import cancel_paper_order

    svc = _MockService()
    svc.cancel_order = AsyncMock(return_value=False)
    with pytest.raises(HTTPException) as exc_info:
        await cancel_paper_order(order_id="missing", current_user=_USER, service=svc)
    assert exc_info.value.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# Position Queries
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_paper_positions_no_filters():
    """List positions without filters calls service with user_id only."""
    from app.api.paper_trading import list_paper_positions

    svc = _MockService()
    svc.list_positions = AsyncMock(return_value=([], 0))
    result = await list_paper_positions(
        current_user=_USER, service=svc,
        account_id=None, symbol=None,
        limit=20, offset=0,
    )
    assert result.total == 0


@pytest.mark.asyncio
async def test_list_paper_positions_with_filters():
    """List positions with filters passes them to service."""
    from app.api.paper_trading import list_paper_positions

    svc = _MockService()
    svc.list_positions = AsyncMock(return_value=([], 0))
    await list_paper_positions(
        current_user=_USER, service=svc,
        account_id="acct-1", symbol="ETH/USDT",
        limit=10, offset=0,
    )
    svc.list_positions.assert_called_once_with(
        filters={"user_id": "u1", "account_id": "acct-1", "symbol": "ETH/USDT"},
        limit=10, offset=0,
    )


@pytest.mark.asyncio
async def test_get_paper_position_success():
    """Get position returns entity for owner."""
    from app.api.paper_trading import get_paper_position

    svc = _MockService()
    result = await get_paper_position(position_id="pos-1", current_user=_USER, service=svc)
    assert result.id == "pos-1"


@pytest.mark.asyncio
async def test_get_paper_position_not_found():
    """Get position raises 404 when not found."""
    from app.api.paper_trading import get_paper_position

    svc = _MockService()
    svc.get_position = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc_info:
        await get_paper_position(position_id="missing", current_user=_USER, service=svc)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_paper_position_forbidden():
    """Get position raises 403 when user doesn't own the account."""
    from app.api.paper_trading import get_paper_position

    svc = _MockService()
    with pytest.raises(HTTPException) as exc_info:
        await get_paper_position(position_id="pos-1", current_user=_OTHER_USER, service=svc)
    assert exc_info.value.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# Trade History
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_paper_trades_no_filters():
    """List trades without filters calls service with user_id only."""
    from app.api.paper_trading import list_paper_trades

    svc = _MockService()
    svc.list_trades = AsyncMock(return_value=([], 0))
    result = await list_paper_trades(
        current_user=_USER, service=svc,
        account_id=None, symbol=None, side=None,
        limit=20, offset=0,
    )
    assert result.total == 0


@pytest.mark.asyncio
async def test_list_paper_trades_with_filters():
    """List trades with all filters passes them to service."""
    from app.api.paper_trading import list_paper_trades

    svc = _MockService()
    svc.list_trades = AsyncMock(return_value=([], 0))
    await list_paper_trades(
        current_user=_USER, service=svc,
        account_id="acct-1", symbol="BTC/USDT", side="buy",
        limit=50, offset=10,
    )
    svc.list_trades.assert_called_once_with(
        filters={
            "user_id": "u1",
            "account_id": "acct-1",
            "symbol": "BTC/USDT",
            "side": "buy",
        },
        limit=50, offset=10,
    )
