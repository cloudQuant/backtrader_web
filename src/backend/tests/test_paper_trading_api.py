"""
Paper Trading API Route Tests.

Tests all paper trading API endpoints:
- Account Management: create, list, details, delete
- Order Management: submit, list, details, cancel
- Position Management: list, details
- Trade Management: list
- WebSocket endpoints
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from fastapi import status


@pytest.fixture
def mock_current_user():
    """Mock current user for testing."""
    user = MagicMock()
    user.sub = "test_user_123"
    return user


@pytest.fixture
def mock_paper_trading_service():
    """Mock PaperTradingService for testing.

    Returns:
        AsyncMock: A mock service with all paper trading methods.
    """
    service = AsyncMock()
    service.create_account = AsyncMock()
    service.list_accounts = AsyncMock(return_value=([], 0))
    service.get_account = AsyncMock(return_value=None)
    service.delete_account = AsyncMock(return_value=True)
    service.submit_order = AsyncMock()
    service.list_orders = AsyncMock(return_value=([], 0))
    service.get_order = AsyncMock(return_value=None)
    service.cancel_order = AsyncMock(return_value=True)
    service.list_positions = AsyncMock(return_value=([], 0))
    service.get_position = AsyncMock(return_value=None)
    service.list_trades = AsyncMock(return_value=([], 0))
    return service


# ==================== Account API Tests ====================

@pytest.mark.asyncio
class TestPaperTradingAccountsAPI:
    """Test paper trading account API endpoints."""

    async def test_create_account_success(self, mock_current_user, mock_paper_trading_service):
        """Test successful paper trading account creation.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import create_paper_account
        from app.schemas.paper_trading import AccountCreate, AccountResponse

        request = AccountCreate(
            name="Test Account",
            initial_cash=100000.0,
            commission_rate=0.001,
            slippage_rate=0.001,
        )

        mock_response = AccountResponse(
            id="acc_123",
            user_id="test_user_123",
            name="Test Account",
            initial_cash=100000.0,
            current_cash=100000.0,
            total_equity=100000.0,
            profit_loss=0.0,
            profit_loss_pct=0.0,
            commission_rate=0.001,
            slippage_rate=0.001,
            is_active=True,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        mock_paper_trading_service.create_account = AsyncMock(return_value=mock_response)

        result = await create_paper_account(
            request=request,
            current_user=mock_current_user,
            service=mock_paper_trading_service
        )

        assert result.id == "acc_123"
        assert result.user_id == "test_user_123"
        assert result.name == "Test Account"
        assert result.initial_cash == 100000.0

        # Verify service was called correctly
        mock_paper_trading_service.create_account.assert_called_once_with(
            user_id="test_user_123",
            name="Test Account",
            initial_cash=100000.0,
            commission_rate=0.001,
            slippage_rate=0.001,
        )

    async def test_create_account_with_defaults(self, mock_current_user, mock_paper_trading_service):
        """Test account creation with default parameter values.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import create_paper_account
        from app.schemas.paper_trading import AccountCreate

        request = AccountCreate(name="Default Account")

        await create_paper_account(
            request=request,
            current_user=mock_current_user,
            service=mock_paper_trading_service
        )

        # Verify default values are used
        call_args = mock_paper_trading_service.create_account.call_args
        assert call_args.kwargs['initial_cash'] == 100000.0
        assert call_args.kwargs['commission_rate'] == 0.001
        assert call_args.kwargs['slippage_rate'] == 0.001

    async def test_list_accounts_empty(self, mock_current_user, mock_paper_trading_service):
        """Test listing accounts when no accounts exist.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import list_paper_accounts

        mock_paper_trading_service.list_accounts = AsyncMock(return_value=([], 0))

        result = await list_paper_accounts(
            current_user=mock_current_user,
            service=mock_paper_trading_service,
            limit=20,
            offset=0
        )

        assert result.total == 0
        assert result.items == []

        mock_paper_trading_service.list_accounts.assert_called_once_with(
            user_id="test_user_123",
            limit=20,
            offset=0
        )

    async def test_list_accounts_with_pagination(self, mock_current_user, mock_paper_trading_service):
        """Test listing accounts with pagination support.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import list_paper_accounts
        from app.schemas.paper_trading import AccountResponse

        mock_accounts = [
            AccountResponse(
                id="acc_1",
                user_id="test_user_123",
                name="Account 1",
                initial_cash=100000.0,
                current_cash=100000.0,
                total_equity=100000.0,
                profit_loss=0.0,
                profit_loss_pct=0.0,
                commission_rate=0.001,
                slippage_rate=0.001,
                is_active=True,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
            AccountResponse(
                id="acc_2",
                user_id="test_user_123",
                name="Account 2",
                initial_cash=200000.0,
                current_cash=200000.0,
                total_equity=200000.0,
                profit_loss=0.0,
                profit_loss_pct=0.0,
                commission_rate=0.002,
                slippage_rate=0.002,
                is_active=True,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
        ]
        mock_paper_trading_service.list_accounts = AsyncMock(return_value=(mock_accounts, 2))

        result = await list_paper_accounts(
            current_user=mock_current_user,
            service=mock_paper_trading_service,
            limit=10,
            offset=0
        )

        assert result.total == 2
        assert len(result.items) == 2

    async def test_get_account_not_found(self, mock_current_user, mock_paper_trading_service):
        """Test getting a non-existent account returns 404.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import get_paper_account
        from fastapi import HTTPException

        mock_paper_trading_service.get_account = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await get_paper_account(
                account_id="nonexistent",
                current_user=mock_current_user,
                service=mock_paper_trading_service
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in exc_info.value.detail

    async def test_get_account_unauthorized(self, mock_current_user, mock_paper_trading_service):
        """Test getting an account owned by another user returns 403.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import get_paper_account
        from fastapi import HTTPException

        mock_account = MagicMock(
            id="acc_other",
            user_id="other_user",  # Different from current user
            name="Other Account",
        )
        mock_paper_trading_service.get_account = AsyncMock(return_value=mock_account)

        with pytest.raises(HTTPException) as exc_info:
            await get_paper_account(
                account_id="acc_other",
                current_user=mock_current_user,
                service=mock_paper_trading_service
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "permission" in exc_info.value.detail.lower()

    async def test_get_account_success(self, mock_current_user, mock_paper_trading_service):
        """Test successful account details retrieval.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import get_paper_account

        mock_account = MagicMock(
            id="acc_123",
            user_id="test_user_123",
            name="Test Account",
            initial_cash=100000.0,
            current_cash=100000.0,
            total_equity=100000.0,
            profit_loss=0.0,
            profit_loss_pct=0.0,
            commission_rate=0.001,
            slippage_rate=0.001,
            is_active=True,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        mock_paper_trading_service.get_account = AsyncMock(return_value=mock_account)

        result = await get_paper_account(
            account_id="acc_123",
            current_user=mock_current_user,
            service=mock_paper_trading_service
        )

        assert result.id == "acc_123"
        assert result.user_id == "test_user_123"

    async def test_delete_account_success(self, mock_current_user, mock_paper_trading_service):
        """Test successful account deletion.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import delete_paper_account

        mock_paper_trading_service.delete_account = AsyncMock(return_value=True)

        result = await delete_paper_account(
            account_id="acc_123",
            current_user=mock_current_user,
            service=mock_paper_trading_service
        )

        assert result == {"message": "Account deleted successfully"}

        mock_paper_trading_service.delete_account.assert_called_once_with(
            "acc_123", "test_user_123"
        )

    async def test_delete_account_not_found(self, mock_current_user, mock_paper_trading_service):
        """Test deleting a non-existent account returns 404.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import delete_paper_account
        from fastapi import HTTPException

        mock_paper_trading_service.delete_account = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await delete_paper_account(
                account_id="nonexistent",
                current_user=mock_current_user,
                service=mock_paper_trading_service
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# ==================== Order API Tests ====================

@pytest.mark.asyncio
class TestPaperTradingOrdersAPI:
    """Test paper trading order API endpoints."""

    async def test_submit_order_market_buy(self, mock_current_user, mock_paper_trading_service):
        """Test submitting a market buy order.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import submit_paper_order
        from app.schemas.paper_trading import OrderRequest, OrderResponse

        request = OrderRequest(
            account_id="acc_123",
            symbol="000001.SZ",
            order_type="market",
            side="buy",
            size=100,
        )

        mock_response = OrderResponse(
            id="order_123",
            account_id="acc_123",
            symbol="000001.SZ",
            order_type="market",
            side="buy",
            size=100,
            price=None,
            stop_price=None,
            limit_price=None,
            filled_size=0,
            avg_fill_price=0.0,
            status="pending",
            rejected_reason=None,
            commission=0.0,
            slippage=0.0,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            filled_at=None,
        )
        mock_paper_trading_service.submit_order = AsyncMock(return_value=mock_response)

        result = await submit_paper_order(
            request=request,
            current_user=mock_current_user,
            service=mock_paper_trading_service
        )

        assert result.id == "order_123"
        assert result.symbol == "000001.SZ"
        assert result.side == "buy"
        assert result.status == "pending"

        mock_paper_trading_service.submit_order.assert_called_once()

    async def test_submit_order_limit_sell(self, mock_current_user, mock_paper_trading_service):
        """Test submitting a limit sell order.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import submit_paper_order
        from app.schemas.paper_trading import OrderRequest, OrderResponse

        request = OrderRequest(
            account_id="acc_123",
            symbol="600000.SH",
            order_type="limit",
            side="sell",
            size=200,
            price=10.5,
        )

        mock_response = OrderResponse(
            id="order_124",
            account_id="acc_123",
            symbol="600000.SH",
            order_type="limit",
            side="sell",
            size=200,
            price=10.5,
            stop_price=None,
            limit_price=None,
            filled_size=0,
            avg_fill_price=0.0,
            status="pending",
            rejected_reason=None,
            commission=0.0,
            slippage=0.0,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            filled_at=None,
        )
        mock_paper_trading_service.submit_order = AsyncMock(return_value=mock_response)

        result = await submit_paper_order(
            request=request,
            current_user=mock_current_user,
            service=mock_paper_trading_service
        )

        assert result.side == "sell"
        assert result.price == 10.5

    async def test_submit_order_stop_loss(self, mock_current_user, mock_paper_trading_service):
        """Test submitting a stop-loss order.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import submit_paper_order
        from app.schemas.paper_trading import OrderRequest, OrderResponse

        request = OrderRequest(
            account_id="acc_123",
            symbol="000001.SZ",
            order_type="stop",
            side="sell",
            size=100,
            stop_price=9.5,
        )

        mock_response = OrderResponse(
            id="order_125",
            account_id="acc_123",
            symbol="000001.SZ",
            order_type="stop",
            side="sell",
            size=100,
            price=None,
            stop_price=9.5,
            limit_price=None,
            filled_size=0,
            avg_fill_price=0.0,
            status="pending",
            rejected_reason=None,
            commission=0.0,
            slippage=0.0,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            filled_at=None,
        )
        mock_paper_trading_service.submit_order = AsyncMock(return_value=mock_response)

        result = await submit_paper_order(
            request=request,
            current_user=mock_current_user,
            service=mock_paper_trading_service
        )

        assert result.stop_price == 9.5

    async def test_list_orders_empty(self, mock_current_user, mock_paper_trading_service):
        """Test listing orders when no orders exist.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import list_paper_orders

        mock_paper_trading_service.list_orders = AsyncMock(return_value=([], 0))

        result = await list_paper_orders(
            current_user=mock_current_user,
            service=mock_paper_trading_service,
            account_id=None,
            symbol=None,
            status=None,
            limit=20,
            offset=0
        )

        assert result.total == 0
        assert result.items == []

        # Verify filters include user_id
        call_kwargs = mock_paper_trading_service.list_orders.call_args.kwargs
        assert call_kwargs['filters']['user_id'] == "test_user_123"

    async def test_list_orders_with_filters(self, mock_current_user, mock_paper_trading_service):
        """Test listing orders with filter parameters.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import list_paper_orders

        mock_paper_trading_service.list_orders = AsyncMock(return_value=([], 0))

        await list_paper_orders(
            current_user=mock_current_user,
            service=mock_paper_trading_service,
            account_id="acc_123",
            symbol="000001.SZ",
            status="pending",
            limit=10,
            offset=0
        )

        # Verify filters are built correctly
        call_kwargs = mock_paper_trading_service.list_orders.call_args.kwargs
        filters = call_kwargs['filters']
        assert filters['user_id'] == "test_user_123"
        assert filters['account_id'] == "acc_123"
        assert filters['symbol'] == "000001.SZ"
        assert filters['status'] == "pending"

    async def test_get_order_not_found(self, mock_current_user, mock_paper_trading_service):
        """Test getting a non-existent order returns 404.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import get_paper_order
        from fastapi import HTTPException

        mock_paper_trading_service.get_order = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await get_paper_order(
                order_id="nonexistent",
                current_user=mock_current_user,
                service=mock_paper_trading_service
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    async def test_get_order_unauthorized(self, mock_current_user, mock_paper_trading_service):
        """Test getting an order from another user's account returns 403.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import get_paper_order
        from fastapi import HTTPException

        mock_order = MagicMock(
            id="order_123",
            account_id="acc_other",
        )
        mock_paper_trading_service.get_order = AsyncMock(return_value=mock_order)

        # Account with different user
        mock_account = MagicMock(
            id="acc_other",
            user_id="other_user",
        )
        mock_paper_trading_service.get_account = AsyncMock(return_value=mock_account)

        with pytest.raises(HTTPException) as exc_info:
            await get_paper_order(
                order_id="order_123",
                current_user=mock_current_user,
                service=mock_paper_trading_service
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    async def test_get_order_success(self, mock_current_user, mock_paper_trading_service):
        """Test successful order details retrieval.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import get_paper_order

        mock_order = MagicMock(
            id="order_123",
            account_id="acc_123",
            symbol="000001.SZ",
            order_type="market",
            side="buy",
            size=100,
            price=None,
            stop_price=None,
            limit_price=None,
            filled_size=50,
            avg_fill_price=10.5,
            status="partial_filled",
            rejected_reason=None,
            commission=5.25,
            slippage=0.1,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            filled_at=datetime.now(),
        )
        mock_paper_trading_service.get_order = AsyncMock(return_value=mock_order)

        # Account with same user
        mock_account = MagicMock(
            id="acc_123",
            user_id="test_user_123",
        )
        mock_paper_trading_service.get_account = AsyncMock(return_value=mock_account)

        result = await get_paper_order(
            order_id="order_123",
            current_user=mock_current_user,
            service=mock_paper_trading_service
        )

        assert result.id == "order_123"
        assert result.status == "partial_filled"

    async def test_cancel_order_success(self, mock_current_user, mock_paper_trading_service):
        """Test successful order cancellation.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import cancel_paper_order

        mock_paper_trading_service.cancel_order = AsyncMock(return_value=True)

        result = await cancel_paper_order(
            order_id="order_123",
            current_user=mock_current_user,
            service=mock_paper_trading_service
        )

        assert result == {"message": "Order has been cancelled"}

        mock_paper_trading_service.cancel_order.assert_called_once_with(
            "order_123", "test_user_123"
        )

    async def test_cancel_order_not_found(self, mock_current_user, mock_paper_trading_service):
        """Test cancelling a non-existent order returns 404.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import cancel_paper_order
        from fastapi import HTTPException

        mock_paper_trading_service.cancel_order = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await cancel_paper_order(
                order_id="nonexistent",
                current_user=mock_current_user,
                service=mock_paper_trading_service
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# ==================== Position API Tests ====================

@pytest.mark.asyncio
class TestPaperTradingPositionsAPI:
    """Test paper trading position API endpoints."""

    async def test_list_positions_empty(self, mock_current_user, mock_paper_trading_service):
        """Test listing positions when no positions exist.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import list_paper_positions

        mock_paper_trading_service.list_positions = AsyncMock(return_value=([], 0))

        result = await list_paper_positions(
            current_user=mock_current_user,
            service=mock_paper_trading_service,
            account_id=None,
            symbol=None,
            limit=20,
            offset=0
        )

        assert result.total == 0
        assert result.items == []

        # Verify filters include user_id
        call_kwargs = mock_paper_trading_service.list_positions.call_args.kwargs
        assert call_kwargs['filters']['user_id'] == "test_user_123"

    async def test_list_positions_with_data(self, mock_current_user, mock_paper_trading_service):
        """Test listing positions with data.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import list_paper_positions
        from app.schemas.paper_trading import PositionResponse

        mock_positions = [
            PositionResponse(
                id="pos_1",
                account_id="acc_123",
                symbol="000001.SZ",
                size=100,
                avg_price=10.0,
                market_value=1050.0,
                unrealized_pnl=50.0,
                unrealized_pnl_pct=5.0,
                entry_price=10.0,
                entry_time=datetime.now(),
                updated_at=datetime.now(),
            ),
        ]
        mock_paper_trading_service.list_positions = AsyncMock(return_value=(mock_positions, 1))

        result = await list_paper_positions(
            current_user=mock_current_user,
            service=mock_paper_trading_service,
            account_id="acc_123",
            symbol=None,
            limit=20,
            offset=0
        )

        assert result.total == 1
        assert len(result.items) == 1
        assert result.items[0].symbol == "000001.SZ"

    async def test_list_positions_with_symbol_filter(self, mock_current_user, mock_paper_trading_service):
        """Test listing positions filtered by symbol.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import list_paper_positions

        mock_paper_trading_service.list_positions = AsyncMock(return_value=([], 0))

        await list_paper_positions(
            current_user=mock_current_user,
            service=mock_paper_trading_service,
            account_id=None,
            symbol="600000.SH",
            limit=20,
            offset=0
        )

        call_kwargs = mock_paper_trading_service.list_positions.call_args.kwargs
        assert call_kwargs['filters']['symbol'] == "600000.SH"

    async def test_get_position_not_found(self, mock_current_user, mock_paper_trading_service):
        """Test getting a non-existent position returns 404.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import get_paper_position
        from fastapi import HTTPException

        mock_paper_trading_service.get_position = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await get_paper_position(
                position_id="nonexistent",
                current_user=mock_current_user,
                service=mock_paper_trading_service
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    async def test_get_position_unauthorized(self, mock_current_user, mock_paper_trading_service):
        """Test getting a position from another user's account returns 403.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import get_paper_position
        from fastapi import HTTPException

        mock_position = MagicMock(
            id="pos_123",
            account_id="acc_other",
            symbol="000001.SZ",
        )
        mock_paper_trading_service.get_position = AsyncMock(return_value=mock_position)

        # Account with different user
        mock_account = MagicMock(
            id="acc_other",
            user_id="other_user",
        )
        mock_paper_trading_service.get_account = AsyncMock(return_value=mock_account)

        with pytest.raises(HTTPException) as exc_info:
            await get_paper_position(
                position_id="pos_123",
                current_user=mock_current_user,
                service=mock_paper_trading_service
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    async def test_get_position_success(self, mock_current_user, mock_paper_trading_service):
        """Test successful position details retrieval.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import get_paper_position

        mock_position = MagicMock(
            id="pos_123",
            account_id="acc_123",
            symbol="000001.SZ",
            size=100,
            avg_price=10.0,
            market_value=1050.0,
            unrealized_pnl=50.0,
            unrealized_pnl_pct=5.0,
            entry_price=10.0,
            entry_time=datetime.now(),
            updated_at=datetime.now(),
        )
        mock_paper_trading_service.get_position = AsyncMock(return_value=mock_position)

        # Account with same user
        mock_account = MagicMock(
            id="acc_123",
            user_id="test_user_123",
        )
        mock_paper_trading_service.get_account = AsyncMock(return_value=mock_account)

        result = await get_paper_position(
            position_id="pos_123",
            current_user=mock_current_user,
            service=mock_paper_trading_service
        )

        assert result.id == "pos_123"
        assert result.symbol == "000001.SZ"


# ==================== Trade API Tests ====================

@pytest.mark.asyncio
class TestPaperTradingTradesAPI:
    """Test paper trading trade API endpoints."""

    async def test_list_trades_empty(self, mock_current_user, mock_paper_trading_service):
        """Test listing trades when no trades exist.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import list_paper_trades

        mock_paper_trading_service.list_trades = AsyncMock(return_value=([], 0))

        result = await list_paper_trades(
            current_user=mock_current_user,
            service=mock_paper_trading_service,
            account_id=None,
            symbol=None,
            side=None,
            limit=20,
            offset=0
        )

        assert result.total == 0
        assert result.items == []

        # Verify filters include user_id
        call_kwargs = mock_paper_trading_service.list_trades.call_args.kwargs
        assert call_kwargs['filters']['user_id'] == "test_user_123"

    async def test_list_trades_with_data(self, mock_current_user, mock_paper_trading_service):
        """Test listing trades with data.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import list_paper_trades
        from app.schemas.paper_trading import TradeResponse

        mock_trades = [
            TradeResponse(
                id="trade_1",
                account_id="acc_123",
                order_id="order_123",
                symbol="000001.SZ",
                side="buy",
                size=100,
                price=10.5,
                commission=5.25,
                slippage=0.1,
                pnl=0.0,
                pnl_pct=0.0,
                created_at=datetime.now(),
            ),
        ]
        mock_paper_trading_service.list_trades = AsyncMock(return_value=(mock_trades, 1))

        result = await list_paper_trades(
            current_user=mock_current_user,
            service=mock_paper_trading_service,
            account_id="acc_123",
            symbol=None,
            side=None,
            limit=20,
            offset=0
        )

        assert result.total == 1
        assert len(result.items) == 1
        assert result.items[0].side == "buy"

    async def test_list_trades_with_filters(self, mock_current_user, mock_paper_trading_service):
        """Test listing trades with filter parameters.

        Args:
            mock_current_user: Mock authenticated user fixture.
            mock_paper_trading_service: Mock service fixture.
        """
        from app.api.paper_trading import list_paper_trades

        mock_paper_trading_service.list_trades = AsyncMock(return_value=([], 0))

        await list_paper_trades(
            current_user=mock_current_user,
            service=mock_paper_trading_service,
            account_id="acc_123",
            symbol="000001.SZ",
            side="buy",
            limit=10,
            offset=0
        )

        # Verify filters are built correctly
        call_kwargs = mock_paper_trading_service.list_trades.call_args.kwargs
        filters = call_kwargs['filters']
        assert filters['user_id'] == "test_user_123"
        assert filters['account_id'] == "acc_123"
        assert filters['symbol'] == "000001.SZ"
        assert filters['side'] == "buy"


# ==================== WebSocket Tests ====================

@pytest.mark.asyncio
class TestPaperTradingWebSocket:
    """Test paper trading WebSocket endpoints."""

    async def test_websocket_account_not_found(self):
        """Test WebSocket connection to non-existent account closes connection."""
        from app.api.paper_trading import websocket_account_endpoint

        mock_ws = MagicMock()
        mock_ws.close = AsyncMock()

        with patch('app.api.paper_trading.PaperTradingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_account = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service

            await websocket_account_endpoint(mock_ws, "nonexistent")

            # Verify websocket closed with policy violation
            mock_ws.close.assert_called_once_with(code=status.WS_1008_POLICY_VIOLATION)

    async def test_websocket_connection_established(self):
        """Test WebSocket connection is established successfully."""
        from app.api.paper_trading import websocket_account_endpoint

        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()

        mock_account = MagicMock(
            id="acc_123",
            current_cash=100000.0,
            total_equity=105000.0,
            profit_loss=5000.0,
            profit_loss_pct=5.0,
        )

        with patch('app.api.paper_trading.PaperTradingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_account = AsyncMock(return_value=mock_account)
            mock_service_class.return_value = mock_service

            with patch('app.websocket_manager.manager') as mock_mgr:
                mock_mgr.connect = AsyncMock()
                mock_mgr.send_to_task = AsyncMock()
                mock_mgr.disconnect = MagicMock()

                # Make the loop exit after one iteration
                with patch('asyncio.sleep', side_effect=[None, Exception("Exit")]):
                    try:
                        await websocket_account_endpoint(mock_ws, "acc_123")
                    except Exception:
                        pass

                # Verify connection was established
                mock_mgr.connect.assert_called_once()

                # Verify initial message was sent
                assert mock_mgr.send_to_task.call_count >= 1

    async def test_websocket_disconnect_handling(self):
        """Test WebSocket disconnect is handled gracefully."""
        from app.api.paper_trading import websocket_account_endpoint
        from fastapi import WebSocketDisconnect

        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()

        mock_account = MagicMock(
            id="acc_123",
            current_cash=100000.0,
            total_equity=100000.0,
            profit_loss=0.0,
            profit_loss_pct=0.0,
        )

        with patch('app.api.paper_trading.PaperTradingService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_account = AsyncMock(return_value=mock_account)
            mock_service_class.return_value = mock_service

            with patch('app.websocket_manager.manager') as mock_mgr:
                mock_mgr.connect = AsyncMock()
                mock_mgr.send_to_task = AsyncMock()
                mock_mgr.disconnect = MagicMock()

                # Make sleep raise WebSocketDisconnect
                with patch('asyncio.sleep', side_effect=WebSocketDisconnect()):
                    await websocket_account_endpoint(mock_ws, "acc_123")

                # Verify disconnect was called
                mock_mgr.disconnect.assert_called_once()


# ==================== Schema Tests ====================

@pytest.mark.asyncio
class TestPaperTradingSchemas:
    """Test paper trading schema validation."""

    async def test_account_create_schema(self):
        """Test account creation schema validation."""
        from app.schemas.paper_trading import AccountCreate
        from pydantic import ValidationError

        # Valid request
        request = AccountCreate(
            name="Test Account",
            initial_cash=100000.0,
            commission_rate=0.001,
            slippage_rate=0.001,
        )
        assert request.name == "Test Account"
        assert request.initial_cash == 100000.0

        # Invalid: empty name
        with pytest.raises(ValidationError):
            AccountCreate(
                name="",
                initial_cash=100000.0,
            )

        # Invalid: negative initial_cash
        with pytest.raises(ValidationError):
            AccountCreate(
                name="Test",
                initial_cash=-1000.0,
            )

    async def test_order_request_schema(self):
        """Test order request schema validation."""
        from app.schemas.paper_trading import OrderRequest
        from pydantic import ValidationError

        # Valid market order
        request = OrderRequest(
            account_id="acc_123",
            symbol="000001.SZ",
            order_type="market",
            side="buy",
            size=100,
        )
        assert request.symbol == "000001.SZ"
        assert request.order_type == "market"

        # Valid limit order
        request = OrderRequest(
            account_id="acc_123",
            symbol="600000.SH",
            order_type="limit",
            side="sell",
            size=200,
            price=10.5,
        )
        assert request.price == 10.5

        # Invalid: wrong symbol format
        with pytest.raises(ValidationError):
            OrderRequest(
                account_id="acc_123",
                symbol="INVALID",
                order_type="market",
                side="buy",
                size=100,
            )

        # Invalid: zero size
        with pytest.raises(ValidationError):
            OrderRequest(
                account_id="acc_123",
                symbol="000001.SZ",
                order_type="market",
                side="buy",
                size=0,
            )


# ==================== Router Tests ====================

@pytest.mark.asyncio
class TestPaperTradingRouter:
    """Test paper trading router configuration."""

    async def test_router_exists(self):
        """Test router is properly defined."""
        from app.api.paper_trading import router

        assert router is not None
        assert hasattr(router, 'routes')

    async def test_router_endpoint_count(self):
        """Test router has expected number of endpoints."""
        from app.api.paper_trading import router

        routes = list(router.routes)
        # Should have 12 routes (11 HTTP + 1 WebSocket)
        assert len(routes) == 12

    async def test_router_has_account_endpoints(self):
        """Test router has account-related endpoints."""
        from app.api.paper_trading import router

        routes = [route for route in router.routes if hasattr(route, 'path')]
        account_routes = [r for r in routes if "/accounts" in r.path]
        assert len(account_routes) > 0

    async def test_router_has_websocket_endpoint(self):
        """Test router has WebSocket endpoint."""
        from app.api.paper_trading import router

        routes = [route for route in router.routes if hasattr(route, 'path')]
        ws_routes = [r for r in routes if "/ws/" in r.path]
        assert len(ws_routes) > 0


# ==================== Dependency Tests ====================

@pytest.mark.asyncio
class TestPaperTradingDependencies:
    """Test paper trading dependency functions."""

    async def test_get_paper_trading_service(self):
        """Test service dependency function returns correct service instance."""
        from app.api.paper_trading import get_paper_trading_service
        from app.services.paper_trading_service import PaperTradingService

        service = get_paper_trading_service()
        assert isinstance(service, PaperTradingService)

    async def test_get_paper_trading_service_callable(self):
        """Test service dependency is callable."""
        from app.api.paper_trading import get_paper_trading_service

        assert callable(get_paper_trading_service)
