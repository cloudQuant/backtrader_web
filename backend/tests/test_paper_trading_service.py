"""
模拟交易服务测试

测试模拟交易账户、订单、持仓、成交功能
"""
import pytest
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from datetime import datetime
from decimal import Decimal

from app.services.paper_trading_service import PaperTradingService
from app.models.paper_trading import (
    Account,
    Position,
    Order,
    OrderType,
    OrderSide,
    OrderStatus,
    PaperTrade,
)


@pytest.fixture
def paper_trading_service():
    """创建模拟交易服务"""
    service = PaperTradingService()
    # Mock repositories
    service.account_repo = AsyncMock()
    service.position_repo = AsyncMock()
    service.order_repo = AsyncMock()
    service.trade_repo = AsyncMock()
    return service


@pytest.fixture
def mock_account():
    """创建模拟账户"""
    return Account(
        id="account-123",
        user_id="user-456",
        name="测试账户",
        initial_cash=100000.0,
        current_cash=100000.0,
        total_equity=100000.0,
        profit_loss=0.0,
        profit_loss_pct=0.0,
        commission_rate=0.001,
        slippage_rate=0.001,
    )


class TestCreateAccount:
    """测试创建模拟账户"""

    @pytest.mark.asyncio
    async def test_create_account_success(self, paper_trading_service):
        """测试成功创建模拟账户"""
        service = paper_trading_service
        service.account_repo.create = AsyncMock(
            return_value=Mock(id="account-123")
        )

        # Mock WebSocket 推送
        with patch.object(service, '_notify_account_update', new_callable=AsyncMock()) as mock_notify:
            account = await service.create_account(
                user_id="user-456",
                name="测试账户",
                initial_cash=100000.0,
                commission_rate=0.001,
                slippage_rate=0.001,
            )

            # 验证账户创建
            assert account.id == "account-123"
            assert account.name == "测试账户"
            assert account.initial_cash == 100000.0

            # 验证推送被调用
            mock_notify.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_account_with_defaults(self, paper_trading_service):
        """测试创建模拟账户（使用默认值）"""
        service = paper_trading_service
        service.account_repo.create = AsyncMock(
            return_value=Mock(id="account-456")
        )

        with patch.object(service, '_notify_account_update', new_callable=AsyncMock()):
            account = await service.create_account(
                user_id="user-789",
                name="默认账户",
            )

            # 验证默认值
            assert account.initial_cash == 100000.0
            assert account.commission_rate == 0.001
            assert account.slippage_rate == 0.001


class TestSubmitOrder:
    """测试提交模拟订单"""

    @pytest.mark.asyncio
    async def test_submit_market_buy_order(self, paper_trading_service, mock_account):
        """测试提交市价买单"""
        service = paper_trading_service

        # Mock account
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)

        # Mock order 创建
        mock_order = Mock(
            id="order-123",
            order_type=OrderType.MARKET,
            side=OrderSide.BUY,
            size=100,
            status=OrderStatus.PENDING,
        )
        service.order_repo.create = AsyncMock(return_value=mock_order)

        # Mock price
        with patch.object(service, '_get_simulated_price', return_value=10.5):
            # Mock process_order
            with patch.object(service, '_process_order', new_callable=AsyncMock()) as mock_process:
                order = await service.submit_order(
                    user_id="user-456",
                    account_id="account-123",
                    symbol="000001.SZ",
                    order_type="market",
                    side="buy",
                    size=100,
                )

                # 验证订单
                assert order.id == "order-123"
                assert order.symbol == "000001.SZ"
                assert order.side == "buy"
                assert order.size == 100
                assert order.order_type == "market"

                # 验证 process_order 被调用
                mock_process.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_submit_limit_sell_order(self, paper_trading_service, mock_account):
        """测试提交限价卖单"""
        service = paper_trading_service
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)

        mock_order = Mock(
            id="order-456",
            order_type=OrderType.LIMIT,
            side=OrderSide.SELL,
            size=50,
            price=11.0,
            status=OrderStatus.PENDING,
        )
        service.order_repo.create = AsyncMock(return_value=mock_order)

        with patch.object(service, '_get_simulated_price', return_value=10.5):
            with patch.object(service, '_process_order', new_callable=AsyncMock()):
                order = await service.submit_order(
                    user_id="user-456",
                    account_id="account-123",
                    symbol="000001.SZ",
                    order_type="limit",
                    side="sell",
                    size=50,
                    price=11.0,
                )

                assert order.price == 11.0

    @pytest.mark.asyncio
    async def test_insufficient_funds(self, paper_trading_service, mock_account):
        """测试资金不足"""
        service = paper_trading_service

        # 账户只有 500 现金
        mock_account.current_cash = 500.0
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)

        mock_order = Mock(
            id="order-789",
            status=OrderStatus.PENDING,
        )
        service.order_repo.create = AsyncMock(return_value=mock_order)

        with patch.object(service, '_get_simulated_price', return_value=10.5):
            with patch.object(service, '_process_order', new_callable=AsyncMock()):
                order = await service.submit_order(
                    user_id="user-456",
                    account_id="account-123",
                    symbol="000001.SZ",
                    order_type="market",
                    side="buy",
                    size=100,  # 100 * 10.5 = 1050, 需要 500 现金
                )

                # 验证订单被拒绝
                assert order.status == OrderStatus.REJECTED

    @pytest.mark.asyncio
    async def test_insufficient_position(self, paper_trading_service, mock_account):
        """测试持仓不足"""
        service = paper_trading_service
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)

        # Mock position（无持仓）
        service.position_repo.list = AsyncMock(return_value=[])

        mock_order = Mock(
            id="order-012",
            status=OrderStatus.PENDING,
        )
        service.order_repo.create = AsyncMock(return_value=mock_order)

        with patch.object(service, '_get_simulated_price', return_value=10.5):
            with patch.object(service, '_process_order', new_callable=AsyncMock()):
                order = await service.submit_order(
                    user_id="user-456",
                    account_id="account-123",
                    symbol="000001.SZ",
                    order_type="market",
                    side="sell",
                    size=100,  # 没有持仓
                )

                # 验证订单被拒绝
                assert order.status == OrderStatus.REJECTED


class TestSlippageCalculation:
    """测试滑点计算"""

    def test_market_buy_slippage(self, paper_trading_service):
        """测试市价买单滑点"""
        service = paper_trading_service

        slippage = service._calculate_slippage(
            order_price=None,
            market_price=10.0,
            slippage_rate=0.001,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
        )

        # 买单滑点为正值
        assert slippage == 0.01  # 10.0 * 0.001

    def test_market_sell_slippage(self, paper_trading_service):
        """测试市价卖单滑点"""
        service = paper_trading_service

        slippage = service._calculate_slippage(
            order_price=None,
            market_price=10.0,
            slippage_rate=0.001,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
        )

        # 卖单滑点为负值
        assert slippage == -0.01  # -10.0 * 0.001

    def test_limit_order_slippage(self, paper_trading_service):
        """测试限价单滑点"""
        service = paper_trading_service

        # 限价单限价优于市价，不滑点
        slippage = service._calculate_slippage(
            order_price=9.5,
            market_price=10.0,
            slippage_rate=0.001,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
        )

        assert slippage == 0.01  # 10.0 * 0.001

    def test_limit_order_no_slippage(self, paper_trading_service):
        """测试限价单不成交"""
        service = paper_trading_service

        # 限价单限价劣于市价，不成交
        slippage = service._calculate_slippage(
            order_price=11.0,
            market_price=10.0,
            slippage_rate=0.001,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
        )

        assert slippage == 0.0


class TestPositionUpdate:
    """测试持仓更新"""

    @pytest.mark.asyncio
    async def test_open_long_position(self, paper_trading_service, mock_account):
        """测试开多头仓位"""
        service = paper_trading_service
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)

        # Mock position（之前无持仓）
        service.position_repo.list = AsyncMock(return_value=[])

        # Mock position 创建
        mock_position = Mock(
            id="position-123",
            symbol="000001.SZ",
            size=100,
            avg_price=10.5,
        )
        service.position_repo.create = AsyncMock(return_value=mock_position)

        # Mock position 获取
        service.position_repo.get_by_id = AsyncMock(return_value=mock_position)

        # Mock account 更新
        service.account_repo.update = AsyncMock()

        with patch.object(service, '_notify_position_update', new_callable=AsyncMock()):
            with patch.object(service, '_notify_account_update', new_callable=AsyncMock()):
                order = Mock(
                    order_type=OrderType.MARKET,
                    side=OrderSide.BUY,
                    size=100,
                )

                await service._update_position(
                    account=mock_account,
                    order=order,
                    price=10.5,
                    commission=1.05,  # 100 * 10.5 * 0.001
                )

                # 验证 position 被创建
                service.position_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_long_position(self, paper_trading_service, mock_account):
        """测试平多头仓位"""
        service = paper_trading_service
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)

        # Mock position（之前有 100 股多头）
        mock_position = Mock(
            id="position-456",
            symbol="000001.SZ",
            size=100,
            avg_price=10.0,
            market_value=1050.0,
            unrealized_pnl=50.0,
            unrealized_pnl_pct=5.0,
            entry_price=10.0,
        )
        service.position_repo.list = AsyncMock(return_value=[mock_position])
        service.position_repo.get_by_id = AsyncMock(return_value=mock_position)
        service.position_repo.update = AsyncMock()

        # Mock account 更新
        service.account_repo.update = AsyncMock()

        with patch.object(service, '_notify_position_update', new_callable=AsyncMock()):
            with patch.object(service, '_notify_account_update', new_callable=AsyncMock()):
                # Mock trade 更新
                mock_trade = Mock(pnl=50.0)
                service.trade_repo.list = AsyncMock(return_value=[mock_trade])
                service.trade_repo.update = AsyncMock()

                order = Mock(
                    order_type=OrderType.MARKET,
                    side=OrderSide.SELL,
                    size=100,
                )

                await service._update_position(
                    account=mock_account,
                    order=order,
                    price=11.0,  # 11.0 卖出，盈利 100
                    commission=1.1,  # 100 * 11.0 * 0.001
                )

                # 验证 position 被更新为 0
                service.position_repo.update.assert_called()
                update_kwargs = service.position_repo.update.call_args[0][1]
                assert update_kwargs["size"] == 0


class TestAccountUpdate:
    """测试账户更新"""

    @pytest.mark.asyncio
    async def test_update_account_after_trade(self, paper_trading_service, mock_account):
        """测试交易后更新账户"""
        service = paper_trading_service
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)
        service.account_repo.update = AsyncMock()

        # Mock positions
        mock_position = Mock(
            symbol="000001.SZ",
            market_value=50000.0,
        )
        service.position_repo.list = AsyncMock(return_value=[mock_position])

        with patch.object(service, '_notify_account_update', new_callable=AsyncMock()):
            order = Mock(side="buy")
            await service._update_account(
                account=mock_account,
                order=order,
                price=10.0,
                commission=1.0,
            )

            # 验证账户更新
            service.account_repo.update.assert_awaited_once()
            update_kwargs = service.account_repo.update.call_args[0][1]

            # 验证现金减少（买单）
            assert update_kwargs["current_cash"] < mock_account.current_cash
            # 验证权益增加
            assert update_kwargs["total_equity"] > mock_account.total_equity

    @pytest.mark.asyncio
    async def test_calculate_profit_loss(self, paper_trading_service):
        """测试计算盈亏"""
        service = paper_trading_service

        account = Account(
            initial_cash=100000.0,
            current_cash=100000.0,
            total_equity=105000.0,
        )

        # Mock positions
        mock_position = Mock(market_value=5000.0)
        service.position_repo.list = AsyncMock(return_value=[mock_position])

        service.account_repo.update = AsyncMock()

        with patch.object(service, '_notify_account_update', new_callable=AsyncMock()):
            await service._update_account(
                account=account,
                order=Mock(),
                price=0,
                commission=0,
            )

            # 验证盈亏计算
            update_kwargs = service.account_repo.update.call_args[0][1]
            assert update_kwargs["profit_loss"] == 5000.0
            assert update_kwargs["profit_loss_pct"] == 5.0


class TestWebSocketNotifications:
    """测试 WebSocket 通知"""

    @pytest.mark.asyncio
    async def test_account_update_notification(self, paper_trading_service, mock_account):
        """测试账户更新 WebSocket 通知"""
        service = paper_trading_service

        with patch('app.websocket_manager.manager') as mock_manager:
            mock_manager.send_to_task = AsyncMock()

            await service._notify_account_update(mock_account)

            # 验证 WebSocket 推送
            mock_manager.send_to_task.assert_awaited_once()
            call_args = mock_manager.send_to_task.call_args[0]
            assert call_args[0] == f"account:{mock_account.id}"
            assert call_args[1]["type"] == "progress"
            assert "total_equity" in call_args[1]["data"]

    @pytest.mark.asyncio
    async def test_order_update_notification(self, paper_trading_service, mock_account):
        """测试订单更新 WebSocket 通知"""
        service = paper_trading_service

        with patch('app.websocket_manager.manager') as mock_manager:
            mock_manager.send_to_task = AsyncMock()

            mock_order = Mock(id="order-123", status="filled")

            await service._notify_order_update("account-456", mock_order)

            # 验证 WebSocket 推送
            mock_manager.send_to_task.assert_awaited_once()
            call_args = mock_manager.send_to_task.call_args[0]
            assert call_args[0] == "account:456"
            assert call_args[1]["type"] == "progress"
            assert call_args[1]["order_id"] == "order-123"
