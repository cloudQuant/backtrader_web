"""
模拟交易服务测试

测试：
- 创建模拟账户
- 提交模拟订单
- 订单成交处理
- 持仓更新
- 账户更新
- 订单撤销
- 账户删除
- 查询功能
- 滑点计算
- 价格模拟
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


@pytest.mark.asyncio
class TestPaperTradingServiceInitialization:
    """测试服务初始化"""

    def test_initialization(self):
        """测试初始化"""
        service = PaperTradingService()
        assert service.account_repo is not None
        assert service.position_repo is not None
        assert service.order_repo is not None
        assert service.trade_repo is not None


@pytest.mark.asyncio
class TestCreateAccount:
    """测试创建模拟账户"""

    async def test_create_account_success(self):
        """测试成功创建账户"""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"
        mock_account.user_id = "user_123"
        mock_account.name = "测试账户"
        mock_account.current_cash = 100000.0
        mock_account.total_equity = 100000.0

        service.account_repo = AsyncMock()
        service.account_repo.create = AsyncMock(return_value=mock_account)

        with patch.object(service, '_notify_account_update', new_callable=AsyncMock):
            result = await service.create_account(
                "user_123",
                "测试账户",
                100000.0
            )

            assert result is not None
            assert result.id == "acc_123"

    async def test_create_account_with_custom_rates(self):
        """测试创建自定义费率的账户"""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"

        service.account_repo = AsyncMock()
        service.account_repo.create = AsyncMock(return_value=mock_account)

        with patch.object(service, '_notify_account_update', new_callable=AsyncMock):
            result = await service.create_account(
                "user_123",
                "测试账户",
                initial_cash=200000.0,
                commission_rate=0.0005,
                slippage_rate=0.0005
            )

            assert result is not None

    async def test_create_account_sends_notification(self):
        """测试创建账户发送通知"""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"

        service.account_repo = AsyncMock()
        service.account_repo.create = AsyncMock(return_value=mock_account)

        with patch.object(service, '_notify_account_update', new_callable=AsyncMock) as mock_notify:
            await service.create_account("user_123", "测试账户")
            assert mock_notify.called


@pytest.mark.asyncio
class TestSubmitOrder:
    """测试提交订单"""

    async def test_submit_order_success(self):
        """测试成功提交订单"""
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
        """测试账户不存在"""
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
        """测试提交止损止盈订单"""
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
    """测试订单处理"""

    async def test_process_order_buy_success(self):
        """测试买入订单成功处理"""
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
        """测试订单不存在"""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=None)

        with patch.object(service, '_get_simulated_price', return_value=50000.0):
            await service._process_order("nonexistent_order", "acc_123", mock_account)
            # 应该不抛出异常，只记录日志

    async def test_process_order_insufficient_funds(self):
        """测试资金不足"""
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
        mock_account.current_cash = 100.0  # 资金不足
        mock_account.commission_rate = 0.001

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=mock_order)
        service.order_repo.update = AsyncMock()

        with patch.object(service, '_get_simulated_price', return_value=50000.0):
            with patch.object(service, '_reject_order', new_callable=AsyncMock) as mock_reject:
                await service._process_order("order_123", "acc_123", mock_account)
                assert mock_reject.called

    async def test_process_order_sell_insufficient_position(self):
        """测试卖出持仓不足"""
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
    """测试订单成交"""

    async def test_fill_order(self):
        """测试填充订单"""
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
    """测试拒绝订单"""

    async def test_reject_order(self):
        """测试拒绝订单"""
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
    """测试更新持仓"""

    async def test_update_position_new_long(self):
        """测试新建多头持仓"""
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
        """测试更新现有多头持仓"""
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
        """测试平多仓"""
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
        mock_position.market_value = 480000.0  # Added market_value attribute

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
    """测试更新账户"""

    async def test_update_account_buy(self):
        """测试更新账户（买入）"""
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
        """测试更新账户（卖出）"""
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
    """测试获取账户"""

    async def test_get_account_found(self):
        """测试获取存在的账户"""
        service = PaperTradingService()

        mock_account = Mock()
        mock_account.id = "acc_123"

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)

        result = await service.get_account("acc_123")

        assert result is not None
        assert result.id == "acc_123"

    async def test_get_account_not_found(self):
        """测试获取不存在的账户"""
        service = PaperTradingService()

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=None)

        result = await service.get_account("nonexistent")

        assert result is None


@pytest.mark.asyncio
class TestListAccounts:
    """测试列出账户"""

    async def test_list_accounts(self):
        """测试列出账户"""
        service = PaperTradingService()

        mock_accounts = [Mock(id=f"acc_{i}") for i in range(5)]

        service.account_repo = AsyncMock()
        service.account_repo.list = AsyncMock(return_value=mock_accounts)
        service.account_repo.count = AsyncMock(return_value=5)

        accounts, total = await service.list_accounts("user_123")

        assert len(accounts) == 5
        assert total == 5

    async def test_list_accounts_empty(self):
        """测试列出空账户"""
        service = PaperTradingService()

        service.account_repo = AsyncMock()
        service.account_repo.list = AsyncMock(return_value=[])
        service.account_repo.count = AsyncMock(return_value=0)

        accounts, total = await service.list_accounts("user_123")

        assert accounts == []
        assert total == 0


@pytest.mark.asyncio
class TestListOrders:
    """测试列出订单"""

    async def test_list_orders(self):
        """测试列出订单"""
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
    """测试列出持仓"""

    async def test_list_positions(self):
        """测试列出持仓"""
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
    """测试列出成交"""

    async def test_list_trades(self):
        """测试列出成交"""
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
    """测试删除账户"""

    async def test_delete_account_success(self):
        """测试成功删除账户"""
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
        """测试删除不存在的账户"""
        service = PaperTradingService()

        service.account_repo = AsyncMock()
        service.account_repo.get_by_id = AsyncMock(return_value=None)

        result = await service.delete_account("nonexistent", "user_123")

        assert result is False

    async def test_delete_account_wrong_user(self):
        """测试删除其他用户的账户"""
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
    """测试撤销订单"""

    async def test_cancel_order_success(self):
        """测试成功撤销订单"""
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
        """测试撤销不存在的订单"""
        service = PaperTradingService()

        service.order_repo = AsyncMock()
        service.order_repo.get_by_id = AsyncMock(return_value=None)

        result = await service.cancel_order("nonexistent", "user_123")

        assert result is False

    async def test_cancel_order_wrong_user(self):
        """测试撤销其他用户的订单"""
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
        """测试撤销已成交订单"""
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
    """测试获取持仓"""

    async def test_get_position_found(self):
        """测试获取存在的持仓"""
        service = PaperTradingService()

        mock_position = Mock()
        mock_position.id = "pos_123"

        service.position_repo = AsyncMock()
        service.position_repo.get_by_id = AsyncMock(return_value=mock_position)

        result = await service.get_position("pos_123")

        assert result is not None
        assert result.id == "pos_123"

    async def test_get_position_not_found(self):
        """测试获取不存在的持仓"""
        service = PaperTradingService()

        service.position_repo = AsyncMock()
        service.position_repo.get_by_id = AsyncMock(return_value=None)

        result = await service.get_position("nonexistent")

        assert result is None


@pytest.mark.asyncio
class TestCalculateSlippage:
    """测试滑点计算"""

    def test_calculate_slippage_market_order_buy(self):
        """测试市价买入滑点"""
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
        """测试市价卖出滑点"""
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
        """测试限价买入单成交（限价优于市价）"""
        service = PaperTradingService()

        slippage = service._calculate_slippage(
            order_price=49000.0,
            market_price=50000.0,
            slippage_rate=0.001,
            side="buy",
            order_type="limit"
        )

        assert slippage == 50.0  # 市价 * 滑点率

    def test_calculate_slippage_limit_order_buy_not_executed(self):
        """测试限价买入单不成交（限价差于市价）"""
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
        """测试限价卖出单成交（限价低于市价）"""
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
        """测试其他订单类型"""
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
    """测试获取模拟价格"""

    async def test_get_simulated_price_000001(self):
        """测试获取000001价格"""
        service = PaperTradingService()

        price = await service._get_simulated_price("000001")

        assert price == 10.5

    async def test_get_simulated_price_600000(self):
        """测试获取600000价格"""
        service = PaperTradingService()

        price = await service._get_simulated_price("600000")

        assert price == 10.8

    async def test_get_simulated_price_default(self):
        """测试获取默认价格"""
        service = PaperTradingService()

        price = await service._get_simulated_price("BTC/USDT")

        assert price == 10.0


@pytest.mark.asyncio
class TestWebSocketNotifications:
    """测试WebSocket通知"""

    async def test_notify_account_update(self):
        """测试账户更新通知"""
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
        """测试持仓更新通知"""
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
        """测试订单更新通知"""
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
    """测试辅助函数"""

    async def test_get_position_exists(self):
        """测试获取存在的持仓"""
        service = PaperTradingService()

        mock_position = Mock()
        mock_position.id = "pos_123"

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[mock_position])

        result = await service._get_position("acc_123", "BTC/USDT")

        assert result is not None
        assert result.id == "pos_123"

    async def test_get_position_not_exists(self):
        """测试获取不存在的持仓"""
        service = PaperTradingService()

        service.position_repo = AsyncMock()
        service.position_repo.list = AsyncMock(return_value=[])

        result = await service._get_position("acc_123", "BTC/USDT")

        assert result is None

    async def test_get_last_trade_exists(self):
        """测试获取最后成交"""
        service = PaperTradingService()

        mock_trade = Mock()
        mock_trade.id = "trade_123"

        service.trade_repo = AsyncMock()
        service.trade_repo.list = AsyncMock(return_value=[mock_trade])

        result = await service._get_last_trade("order_123")

        assert result is not None

    async def test_get_last_trade_not_exists(self):
        """测试获取不存在的最后成交"""
        service = PaperTradingService()

        service.trade_repo = AsyncMock()
        service.trade_repo.list = AsyncMock(return_value=[])

        result = await service._get_last_trade("order_123")

        assert result is None
