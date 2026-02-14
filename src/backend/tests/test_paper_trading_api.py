"""
模拟交易 API 路由完整测试

测试所有模拟交易 API 端点：
- 账户管理：创建、列表、详情、删除
- 订单管理：提交、列表、详情、撤销
- 持仓管理：列表、详情
- 成交管理：列表
- WebSocket 端点
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from fastapi import status


@pytest.fixture
def mock_current_user():
    """Mock current user"""
    user = MagicMock()
    user.sub = "test_user_123"
    return user


@pytest.fixture
def mock_paper_trading_service():
    """Mock PaperTradingService"""
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


# ==================== 账户 API 测试 ====================

@pytest.mark.asyncio
class TestPaperTradingAccountsAPI:
    """测试模拟账户 API"""

    async def test_create_account_success(self, mock_current_user, mock_paper_trading_service):
        """测试成功创建模拟账户"""
        from app.api.paper_trading import create_paper_account
        from app.schemas.paper_trading import AccountCreate, AccountResponse

        request = AccountCreate(
            name="测试账户",
            initial_cash=100000.0,
            commission_rate=0.001,
            slippage_rate=0.001,
        )

        mock_response = AccountResponse(
            id="acc_123",
            user_id="test_user_123",
            name="测试账户",
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
        assert result.name == "测试账户"
        assert result.initial_cash == 100000.0

        # Verify service was called correctly
        mock_paper_trading_service.create_account.assert_called_once_with(
            user_id="test_user_123",
            name="测试账户",
            initial_cash=100000.0,
            commission_rate=0.001,
            slippage_rate=0.001,
        )

    async def test_create_account_with_defaults(self, mock_current_user, mock_paper_trading_service):
        """测试使用默认值创建账户"""
        from app.api.paper_trading import create_paper_account
        from app.schemas.paper_trading import AccountCreate

        request = AccountCreate(name="默认账户")

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
        """测试空账户列表"""
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
        """测试分页获取账户列表"""
        from app.api.paper_trading import list_paper_accounts
        from app.schemas.paper_trading import AccountResponse

        mock_accounts = [
            AccountResponse(
                id="acc_1",
                user_id="test_user_123",
                name="账户1",
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
                name="账户2",
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
        """测试获取不存在的账户"""
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
        assert "不存在" in exc_info.value.detail

    async def test_get_account_unauthorized(self, mock_current_user, mock_paper_trading_service):
        """测试获取无权访问的账户"""
        from app.api.paper_trading import get_paper_account
        from fastapi import HTTPException

        mock_account = MagicMock(
            id="acc_other",
            user_id="other_user",  # Different from current user
            name="其他账户",
        )
        mock_paper_trading_service.get_account = AsyncMock(return_value=mock_account)

        with pytest.raises(HTTPException) as exc_info:
            await get_paper_account(
                account_id="acc_other",
                current_user=mock_current_user,
                service=mock_paper_trading_service
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "无权访问" in exc_info.value.detail

    async def test_get_account_success(self, mock_current_user, mock_paper_trading_service):
        """测试成功获取账户详情"""
        from app.api.paper_trading import get_paper_account

        mock_account = MagicMock(
            id="acc_123",
            user_id="test_user_123",
            name="测试账户",
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
        """测试成功删除账户"""
        from app.api.paper_trading import delete_paper_account

        mock_paper_trading_service.delete_account = AsyncMock(return_value=True)

        result = await delete_paper_account(
            account_id="acc_123",
            current_user=mock_current_user,
            service=mock_paper_trading_service
        )

        assert result == {"message": "删除成功"}

        mock_paper_trading_service.delete_account.assert_called_once_with(
            "acc_123", "test_user_123"
        )

    async def test_delete_account_not_found(self, mock_current_user, mock_paper_trading_service):
        """测试删除不存在的账户"""
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


# ==================== 订单 API 测试 ====================

@pytest.mark.asyncio
class TestPaperTradingOrdersAPI:
    """测试模拟订单 API"""

    async def test_submit_order_market_buy(self, mock_current_user, mock_paper_trading_service):
        """测试提交市价买单"""
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
        """测试提交限价卖单"""
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
        """测试提交止损单"""
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
        """测试空订单列表"""
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
        """测试使用筛选条件获取订单列表"""
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
        """测试获取不存在的订单"""
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
        """测试获取无权访问的订单"""
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
        """测试成功获取订单详情"""
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
        """测试成功撤销订单"""
        from app.api.paper_trading import cancel_paper_order

        mock_paper_trading_service.cancel_order = AsyncMock(return_value=True)

        result = await cancel_paper_order(
            order_id="order_123",
            current_user=mock_current_user,
            service=mock_paper_trading_service
        )

        assert result == {"message": "订单已撤销"}

        mock_paper_trading_service.cancel_order.assert_called_once_with(
            "order_123", "test_user_123"
        )

    async def test_cancel_order_not_found(self, mock_current_user, mock_paper_trading_service):
        """测试撤销不存在的订单"""
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


# ==================== 持仓 API 测试 ====================

@pytest.mark.asyncio
class TestPaperTradingPositionsAPI:
    """测试模拟持仓 API"""

    async def test_list_positions_empty(self, mock_current_user, mock_paper_trading_service):
        """测试空持仓列表"""
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
        """测试获取持仓列表"""
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
        """测试使用标的代码筛选持仓"""
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
        """测试获取不存在的持仓"""
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
        """测试获取无权访问的持仓"""
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
        """测试成功获取持仓详情"""
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


# ==================== 成交 API 测试 ====================

@pytest.mark.asyncio
class TestPaperTradingTradesAPI:
    """测试模拟成交 API"""

    async def test_list_trades_empty(self, mock_current_user, mock_paper_trading_service):
        """测试空成交列表"""
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
        """测试获取成交列表"""
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
        """测试使用筛选条件获取成交列表"""
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


# ==================== WebSocket 测试 ====================

@pytest.mark.asyncio
class TestPaperTradingWebSocket:
    """测试模拟交易 WebSocket"""

    async def test_websocket_account_not_found(self):
        """测试WebSocket连接不存在的账户"""
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
        """测试WebSocket连接建立"""
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
        """测试WebSocket断开连接处理"""
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


# ==================== Schema 测试 ====================

@pytest.mark.asyncio
class TestPaperTradingSchemas:
    """测试模拟交易 Schema"""

    async def test_account_create_schema(self):
        """测试账户创建 Schema"""
        from app.schemas.paper_trading import AccountCreate
        from pydantic import ValidationError

        # Valid request
        request = AccountCreate(
            name="测试账户",
            initial_cash=100000.0,
            commission_rate=0.001,
            slippage_rate=0.001,
        )
        assert request.name == "测试账户"
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
                name="测试",
                initial_cash=-1000.0,
            )

    async def test_order_request_schema(self):
        """测试订单请求 Schema"""
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


# ==================== 路由测试 ====================

@pytest.mark.asyncio
class TestPaperTradingRouter:
    """测试模拟交易路由"""

    async def test_router_exists(self):
        """测试路由存在"""
        from app.api.paper_trading import router

        assert router is not None
        assert hasattr(router, 'routes')

    async def test_router_endpoint_count(self):
        """测试路由端点数量"""
        from app.api.paper_trading import router

        routes = list(router.routes)
        # Should have 12 routes (11 HTTP + 1 WebSocket)
        assert len(routes) == 12

    async def test_router_has_account_endpoints(self):
        """测试有账户端点"""
        from app.api.paper_trading import router

        routes = [route for route in router.routes if hasattr(route, 'path')]
        account_routes = [r for r in routes if "/accounts" in r.path]
        assert len(account_routes) > 0

    async def test_router_has_websocket_endpoint(self):
        """测试有WebSocket端点"""
        from app.api.paper_trading import router

        routes = [route for route in router.routes if hasattr(route, 'path')]
        ws_routes = [r for r in routes if "/ws/" in r.path]
        assert len(ws_routes) > 0


# ==================== 依赖函数测试 ====================

@pytest.mark.asyncio
class TestPaperTradingDependencies:
    """测试模拟交易依赖函数"""

    async def test_get_paper_trading_service(self):
        """测试服务依赖函数"""
        from app.api.paper_trading import get_paper_trading_service
        from app.services.paper_trading_service import PaperTradingService

        service = get_paper_trading_service()
        assert isinstance(service, PaperTradingService)

    async def test_get_paper_trading_service_callable(self):
        """测试服务可调用"""
        from app.api.paper_trading import get_paper_trading_service

        assert callable(get_paper_trading_service)
