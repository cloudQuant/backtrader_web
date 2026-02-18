"""
Paper Trading Service Tests.

Tests:
- Creating paper trading accounts
- Submitting paper trading orders
- Order fill processing
- Position updates
- Account updates
- Order cancellation
- Account deletion
- Query functions
- Slippage calculation
- Price simulation
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from app.services.paper_trading_service import PaperTradingService
from app.models.paper_trading import (
    Account,
    Position,
    Order,
    OrderType,
    OrderSide,
    OrderStatus,
)


class TestPaperTradingServiceInitialization:
    """Test paper trading service initialization."""

    def test_initialization(self):
        """Test service initialization with required repositories."""
        service = PaperTradingService()
        assert service.account_repo is not None
        assert service.position_repo is not None
        assert service.order_repo is not None
        assert service.trade_repo is not None


@pytest.mark.asyncio
class TestCreateAccount:
    """Test paper trading account creation."""

    async def test_create_account_success(self):
        """Test successful account creation."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.user_id = "user_123"
        mock_account.name = "Test Account"
        mock_account.current_cash = 100000.0
        mock_account.total_equity = 100000.0

        service.account_repo = AsyncMock()
        service.account_repo.create = AsyncMock(return_value=mock_account)

        with patch.object(service, '_notify_account_update', new_callable=AsyncMock):
            result = await service.create_account(
                "user_123",
                "Test Account",
                100000.0
            )

            assert result is not None
            assert result.id == "acc_123"

    async def test_create_account_with_custom_rates(self):
        """Test account creation with custom commission and slippage rates."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"

        service.account_repo = AsyncMock()
        service.account_repo.create = AsyncMock(return_value=mock_account)

        with patch.object(service, '_notify_account_update', new_callable=AsyncMock):
            result = await service.create_account(
                "user_123",
                "Test Account",
                initial_cash=200000.0,
                commission_rate=0.0005,
                slippage_rate=0.0005
            )

            assert result is not None

    async def test_create_account_sends_notification(self):
        """Test that account creation triggers WebSocket notification."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"

        service.account_repo = AsyncMock()
        service.account_repo.create = AsyncMock(return_value=mock_account)

        with patch.object(service, '_notify_account_update', new_callable=AsyncMock) as mock_notify:
            await service.create_account("user_123", "Test Account")
            assert mock_notify.called


@pytest.mark.asyncio
class TestSubmitOrder:
    """Test order submission."""

    async def test_submit_order_success(self):
        """Test successful order submission."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.commission_rate = 0.001

        mock_order = Mock()
        mock_order.id = "order_123"

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)
        service.order_repo = AsyncMock()
        service.order_repo.create = AsyncMock(return_value=mock_order)

        with patch.object(service, '_notify_order_update', new_callable=AsyncMock):
            result = await service.submit_order(
                "acc_123",
                "BTC/USDT",
                "market",
                "buy",
                10,
                price=50000.0
            )

            assert result is not None

    async def test_submit_order_account_not_found(self):
        """Test order submission with non-existent account raises ValueError."""
        service = PaperTradingService()

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Account not found"):
            await service.submit_order(
                "nonexistent_acc",
                "BTC/USDT",
                "market",
                "buy",
                10
            )

    async def test_submit_order_with_stop_limit(self):
        """Test submitting stop-loss and take-profit orders."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.commission_rate = 0.001

        mock_order = Mock()
        mock_order.id = "order_123"

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)
        service.order_repo = AsyncMock()
        service.order_repo.create = AsyncMock(return_value=mock_order)

        with patch.object(service, '_notify_order_update', new_callable=AsyncMock):
            result = await service.submit_order(
                "acc_123",
                "BTC/USDT",
                "limit",
                "buy",
                10,
                price=49000.0,
                stop_price=48000.0,
                limit_price=51000.0
            )

            assert result is not None


@pytest.mark.asyncio
class TestProcessOrder:
    """Test order processing."""

    async def test_process_order_buy_success(self):
        """Test successful buy order processing."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = OrderSide.BUY
        mock_order.size = 10
        mock_order.price = 50000.0
        mock_order.order_type = "market"

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.slippage_rate = 0.001
        mock_account.current_cash = 600000.0
        mock_account.commission_rate = 0.001

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)

        with patch.object(service, '_get_simulated_price', return_value=50000.0):
            with patch.object(service, '_fill_order', new_callable=AsyncMock):
                with patch.object(service, '_update_position', new_callable=AsyncMock):
                    with patch.object(service, '_update_account', new_callable=AsyncMock):
                        await service._process_order("order_123", "acc_123", mock_account)

    async def test_process_order_order_not_found(self):
        """Test processing of non-existent order logs without exception."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=None)

        with patch.object(service, '_get_simulated_price', return_value=50000.0):
            await service._process_order("nonexistent_order", "acc_123", mock_account)
            # Should not raise exception, only log

    async def test_process_order_insufficient_funds(self):
        """Test order processing with insufficient funds triggers rejection."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = OrderSide.BUY
        mock_order.size = 100
        mock_order.order_type = "market"

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.slippage_rate = 0.001
        mock_account.current_cash = 100.0  # Insufficient funds
        mock_account.commission_rate = 0.001

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)
        service.order_repo.update = AsyncMock()

        with patch.object(service, '_get_simulated_price', return_value=50000.0):
            with patch.object(service, '_reject_order', new_callable=AsyncMock) as mock_reject:
                await service._process_order("order_123", "acc_123", mock_account)
                assert mock_reject.called

    async def test_process_order_sell_insufficient_position(self):
        """Test sell order processing with insufficient position triggers rejection."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = OrderSide.SELL
        mock_order.size = 100
        mock_order.order_type = "market"

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.slippage_rate = 0.001
        mock_account.commission_rate = 0.001

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)
        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[])

        with patch.object(service, '_get_simulated_price', return_value=50000.0):
            with patch.object(service, '_reject_order', new_callable=AsyncMock) as mock_reject:
                await service._process_order("order_123", "acc_123", mock_account)
                assert mock_reject.called


@pytest.mark.asyncio
class TestFillOrder:
    """Test order fill execution."""

    async def test_fill_order(self):
        """Test order fill updates order status and creates trade record."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = OrderSide.BUY
        mock_order.size = 10

        mock_trade = Mock()
        mock_trade.id = "trade_123"

        service.order_repo = AsyncMock()
        service.order_repo.update = AsyncMock()
        service.trade_repo = AsyncMock()
        service.trade_repo.create = AsyncMock(return_value=mock_trade)

        await service._fill_order(mock_order, 50000.0, 50.0)

        assert mock_order.status == OrderStatus.FILLED
        assert mock_order.filled_size == 10
        assert mock_order.avg_fill_price == 50000.0
        assert mock_order.commission == 50.0


@pytest.mark.asyncio
class TestRejectOrder:
    """Test order rejection."""

    async def test_reject_order(self):
        """Test order rejection updates status and reason."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"

        service.order_repo = AsyncMock()
        service.order_repo.update = AsyncMock()

        with patch.object(service, '_notify_order_update', new_callable=AsyncMock):
            await service._reject_order(mock_order, "Insufficient funds")

        assert mock_order.status == OrderStatus.REJECTED
        assert mock_order.rejected_reason == "Insufficient funds"


@pytest.mark.asyncio
class TestUpdatePosition:
    """Test position updates."""

    async def test_update_position_new_long(self):
        """Test creating a new long position."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = OrderSide.BUY
        mock_order.size = 10

        mock_position = Mock()
        mock_position.id = "pos_123"

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[])
        service.position_repo.create = AsyncMock(return_value=mock_position)

        await service._update_position(mock_account, mock_order, 50000.0, 50.0)

        assert service.position_repo.create.called

    async def test_update_position_existing_long(self):
        """Test updating an existing long position."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = OrderSide.BUY
        mock_order.size = 5

        mock_position = Mock()
        mock_position.id = "pos_123"
        mock_position.size = 10
        mock_position.avg_price = 48000.0
        mock_position.market_value = 480000.0

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[mock_position])
        service.position_repo.update = AsyncMock()
        service.trade_repo = AsyncMock()
        service.trade_repo.list = AsyncMock(return_value=[])

        await service._update_position(mock_account, mock_order, 50000.0, 25.0)

        assert service.position_repo.update.called

    async def test_update_position_close_long(self):
        """Test closing a long position."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = OrderSide.SELL
        mock_order.size = 10

        mock_position = Mock()
        mock_position.id = "pos_123"
        mock_position.size = 10
        mock_position.avg_price = 48000.0
        mock_position.market_value = 480000.0

        mock_trade = Mock()
        mock_trade.id = "trade_123"
        mock_trade.pnl = 0.0

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[mock_position])
        service.position_repo.update = AsyncMock()

        service.trade_repo = AsyncMock()
        service.trade_repo.list = AsyncMock(return_value=[mock_trade])
        service.trade_repo.update = AsyncMock()

        await service._update_position(mock_account, mock_order, 50000.0, 50.0)

        assert service.trade_repo.update.called


@pytest.mark.asyncio
class TestUpdateAccount:
    """Test account updates."""

    async def test_update_account_buy(self):
        """Test account update after buy order."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.initial_cash = 100000.0
        mock_account.current_cash = 100000.0

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.side = OrderSide.BUY
        mock_order.size = 10
        mock_order.symbol = "BTC/USDT"

        mock_position = Mock()
        mock_position.market_value = 0.0

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[mock_position])
        service.account_repo = AsyncMock()
        service.account_repo.update = AsyncMock()

        with patch.object(service, '_notify_account_update', new_callable=AsyncMock):
            with patch.object(service, '_notify_position_update', new_callable=AsyncMock):
                await service._update_account(mock_account, mock_order, 50000.0, 50.0)

    async def test_update_account_sell(self):
        """Test account update after sell order."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.initial_cash = 100000.0
        mock_account.current_cash = 100000.0

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.side = OrderSide.SELL
        mock_order.size = 10
        mock_order.symbol = "BTC/USDT"

        mock_position = Mock()
        mock_position.market_value = 0.0

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[mock_position])
        service.account_repo = AsyncMock()
        service.account_repo.update = AsyncMock()

        with patch.object(service, '_notify_account_update', new_callable=AsyncMock):
            with patch.object(service, '_notify_position_update', new_callable=AsyncMock):
                await service._update_account(mock_account, mock_order, 50000.0, 50.0)


@pytest.mark.asyncio
class TestGetAccount:
    """Test account retrieval."""

    async def test_get_account_found(self):
        """Test retrieving an existing account."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)

        result = await service.get_account("acc_123")

        assert result is not None
        assert result.id == "acc_123"

    async def test_get_account_not_found(self):
        """Test retrieving a non-existent account returns None."""
        service = PaperTradingService()

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=None)

        result = await service.get_account("nonexistent")

        assert result is None


@pytest.mark.asyncio
class TestListAccounts:
    """Test account listing."""

    async def test_list_accounts(self):
        """Test listing user accounts."""
        service = PaperTradingService()

        mock_accounts = [Mock(id=f"acc_{i}") for i in range(5)]

        service.account_repo = AsyncMock()
        service.account_repo.list = AsyncMock(return_value=mock_accounts)
        service.account_repo.count = AsyncMock(return_value=5)

        accounts, total = await service.list_accounts("user_123")

        assert len(accounts) == 5
        assert total == 5

    async def test_list_accounts_empty(self):
        """Test listing when user has no accounts."""
        service = PaperTradingService()

        service.account_repo = AsyncMock()
        service.account_repo.list = AsyncMock(return_value=[])
        service.account_repo.count = AsyncMock(return_value=0)

        accounts, total = await service.list_accounts("user_123")

        assert accounts == []
        assert total == 0


@pytest.mark.asyncio
class TestListOrders:
    """Test order listing."""

    async def test_list_orders(self):
        """Test listing orders with filters."""
        service = PaperTradingService()

        mock_orders = [Mock(id=f"order_{i}") for i in range(3)]

        service.order_repo = AsyncMock()
        service.order_repo.list = AsyncMock(return_value=mock_orders)
        service.order_repo.count = AsyncMock(return_value=3)

        orders, total = await service.list_orders({"account_id": "acc_123"})

        assert len(orders) == 3
        assert total == 3


@pytest.mark.asyncio
class TestListPositions:
    """Test position listing."""

    async def test_list_positions(self):
        """Test listing positions with filters."""
        service = PaperTradingService()

        mock_positions = [Mock(id=f"pos_{i}") for i in range(2)]

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=mock_positions)
        service.position_repo.count = AsyncMock(return_value=2)

        positions, total = await service.list_positions({"account_id": "acc_123"})

        assert len(positions) == 2
        assert total == 2


@pytest.mark.asyncio
class TestListTrades:
    """Test trade listing."""

    async def test_list_trades(self):
        """Test listing trades with filters."""
        service = PaperTradingService()

        mock_trades = [Mock(id=f"trade_{i}") for i in range(4)]

        service.trade_repo = AsyncMock()
        service.trade_repo.list = AsyncMock(return_value=mock_trades)
        service.trade_repo.count = AsyncMock(return_value=4)

        trades, total = await service.list_trades({"account_id": "acc_123"})

        assert len(trades) == 4
        assert total == 4


@pytest.mark.asyncio
class TestDeleteAccount:
    """Test account deletion."""

    async def test_delete_account_success(self):
        """Test successful account deletion."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.user_id = "user_123"

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)
        service.account_repo.update = AsyncMock()

        result = await service.delete_account("acc_123", "user_123")

        assert result is True

    async def test_delete_account_not_found(self):
        """Test deleting non-existent account returns False."""
        service = PaperTradingService()

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=None)

        result = await service.delete_account("nonexistent", "user_123")

        assert result is False

    async def test_delete_account_wrong_user(self):
        """Test deleting account owned by another user returns False."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.user_id = "other_user"

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)

        result = await service.delete_account("acc_123", "user_123")

        assert result is False


@pytest.mark.asyncio
class TestCancelOrder:
    """Test order cancellation."""

    async def test_cancel_order_success(self):
        """Test successful order cancellation."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.status = OrderStatus.PENDING

        mock_account = Mock()
        mock_account.user_id = "user_123"

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)
        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)
        service.order_repo.update = AsyncMock()

        with patch.object(service, '_notify_order_update', new_callable=AsyncMock):
            result = await service.cancel_order("order_123", "user_123")

            assert result is True

    async def test_cancel_order_not_found(self):
        """Test cancelling non-existent order returns False."""
        service = PaperTradingService()

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=None)

        result = await service.cancel_order("nonexistent", "user_123")

        assert result is False

    async def test_cancel_order_wrong_user(self):
        """Test cancelling order from another user's account returns False."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.status = OrderStatus.PENDING

        mock_account = Mock()
        mock_account.user_id = "other_user"

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)
        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)

        result = await service.cancel_order("order_123", "user_123")

        assert result is False

    async def test_cancel_order_already_filled(self):
        """Test cancelling already filled order returns False."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.status = OrderStatus.FILLED

        mock_account = Mock()
        mock_account.user_id = "user_123"

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)
        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)

        result = await service.cancel_order("order_123", "user_123")

        assert result is False


@pytest.mark.asyncio
class TestGetPosition:
    """Test position retrieval."""

    async def test_get_position_found(self):
        """Test retrieving an existing position."""
        service = PaperTradingService()

        mock_position = Mock()
        mock_position.id = "pos_123"

        service.position_repo = AsyncMock()
        service.position_repo.get_by_id = AsyncMock(return_value=mock_position)

        result = await service.get_position("pos_123")

        assert result is not None
        assert result.id == "pos_123"

    async def test_get_position_not_found(self):
        """Test retrieving non-existent position returns None."""
        service = PaperTradingService()

        service.position_repo = AsyncMock()
        service.position_repo.get_by_id = AsyncMock(return_value=None)

        result = await service.get_position("nonexistent")

        assert result is None


class TestCalculateSlippage:
    """Test slippage calculation."""

    def test_calculate_slippage_market_order_buy(self):
        """Test slippage calculation for market buy order."""
        service = PaperTradingService()

        slippage = service._calculate_slippage(
            order_price=None,
            market_price=50000.0,
            slippage_rate=0.001,
            side="buy",
            order_type="market"
        )

        assert slippage == 50.0  # 50000 * 0.001

    def test_calculate_slippage_market_order_sell(self):
        """Test slippage calculation for market sell order."""
        service = PaperTradingService()

        slippage = service._calculate_slippage(
            order_price=None,
            market_price=50000.0,
            slippage_rate=0.001,
            side="sell",
            order_type="market"
        )

        assert slippage == -50.0  # -50000 * 0.001

    def test_calculate_slippage_limit_order_buy_executed(self):
        """Test slippage for executed limit buy order (limit better than market)."""
        service = PaperTradingService()

        slippage = service._calculate_slippage(
            order_price=49000.0,
            market_price=50000.0,
            slippage_rate=0.001,
            side="buy",
            order_type="limit"
        )

        assert slippage == 50.0  # Market price * slippage rate

    def test_calculate_slippage_limit_order_buy_not_executed(self):
        """Test slippage for unexecuted limit buy order (limit worse than market)."""
        service = PaperTradingService()

        slippage = service._calculate_slippage(
            order_price=51000.0,
            market_price=50000.0,
            slippage_rate=0.001,
            side="buy",
            order_type="limit"
        )

        assert slippage == 0.0

    def test_calculate_slippage_limit_order_sell_executed(self):
        """Test slippage for executed limit sell order (limit below market)."""
        service = PaperTradingService()

        slippage = service._calculate_slippage(
            order_price=51000.0,
            market_price=50000.0,
            slippage_rate=0.001,
            side="sell",
            order_type="limit"
        )

        assert slippage == -50.0

    def test_calculate_slippage_other_order_type(self):
        """Test slippage calculation for other order types."""
        service = PaperTradingService()

        slippage = service._calculate_slippage(
            order_price=50000.0,
            market_price=50000.0,
            slippage_rate=0.001,
            side="buy",
            order_type="stop"
        )

        assert slippage == 0.0


@pytest.mark.asyncio
class TestGetSimulatedPrice:
    """Test simulated price retrieval."""

    async def test_get_simulated_price_000001(self):
        """Test getting price for symbol 000001."""
        service = PaperTradingService()

        price = await service._get_simulated_price("000001")

        assert price == 10.5

    async def test_get_simulated_price_600000(self):
        """Test getting price for symbol 600000."""
        service = PaperTradingService()

        price = await service._get_simulated_price("600000")

        assert price == 10.8

    async def test_get_simulated_price_default(self):
        """Test getting default price for unknown symbols."""
        service = PaperTradingService()

        price = await service._get_simulated_price("BTC/USDT")

        assert price == 10.0


@pytest.mark.asyncio
class TestWebSocketNotifications:
    """Test WebSocket notification functions."""

    async def test_notify_account_update(self):
        """Test account update WebSocket notification."""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.current_cash = 100000.0
        mock_account.total_equity = 100000.0
        mock_account.profit_loss = 0.0
        mock_account.profit_loss_pct = 0.0

        with patch('app.services.paper_trading_service.ws_manager') as mock_ws:
            mock_ws.send_to_task = AsyncMock()
            await service._notify_account_update(mock_account)
            assert mock_ws.send_to_task.called

    async def test_notify_position_update(self):
        """Test position update WebSocket notification."""
        service = PaperTradingService()

        mock_position = Mock()
        mock_position.id = "pos_123"
        mock_position.symbol = "BTC/USDT"
        mock_position.size = 10
        mock_position.avg_price = 50000.0
        mock_position.market_value = 500000.0
        mock_position.unrealized_pnl = 0.0
        mock_position.unrealized_pnl_pct = 0.0

        with patch('app.services.paper_trading_service.ws_manager') as mock_ws:
            mock_ws.send_to_task = AsyncMock()
            await service._notify_position_update(mock_position)
            assert mock_ws.send_to_task.called

    async def test_notify_order_update(self):
        """Test order update WebSocket notification."""
        service = PaperTradingService()

        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.account_id = "acc_123"
        mock_order.symbol = "BTC/USDT"
        mock_order.side = "buy"
        mock_order.size = 10
        mock_order.price = 50000.0
        mock_order.status = OrderStatus.FILLED
        mock_order.filled_size = 10

        with patch('app.services.paper_trading_service.ws_manager') as mock_ws:
            mock_ws.send_to_task = AsyncMock()
            await service._notify_order_update("acc_123", mock_order)
            assert mock_ws.send_to_task.called


@pytest.mark.asyncio
class TestHelperFunctions:
    """Test helper functions."""

    async def test_get_position_exists(self):
        """Test retrieving existing position for account and symbol."""
        service = PaperTradingService()

        mock_position = Mock()
        mock_position.id = "pos_123"

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[mock_position])

        result = await service._get_position("acc_123", "BTC/USDT")

        assert result is not None
        assert result.id == "pos_123"

    async def test_get_position_not_exists(self):
        """Test retrieving non-existent position returns None."""
        service = PaperTradingService()

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[])

        result = await service._get_position("acc_123", "BTC/USDT")

        assert result is None

    async def test_get_last_trade_exists(self):
        """Test retrieving last trade for an order."""
        service = PaperTradingService()

        mock_trade = Mock()
        mock_trade.id = "trade_123"

        service.trade_repo = AsyncMock()
        service.trade_repo.list = AsyncMock(return_value=[mock_trade])

        result = await service._get_last_trade("order_123")

        assert result is not None

    async def test_get_last_trade_not_exists(self):
        """Test retrieving last trade when no trades exist returns None."""
        service = PaperTradingService()

        service.trade_repo = AsyncMock()
        service.trade_repo.list = AsyncMock(return_value=[])

        result = await service._get_last_trade("order_123")

        assert result is None
