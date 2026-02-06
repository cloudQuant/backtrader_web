"""
模拟交易服务测试（完整版）

确保所有功能都可以正常工作
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from decimal import Decimal
from datetime import datetime, timedelta
import uuid

# 尝试导入，如果失败则跳过
try:
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
    SERVICES_AVAILABLE = True
except ImportError:
    SERVICES_AVAILABLE = False
    pytest.skip(reason="Paper trading service not available")


@pytest.fixture
def mock_repository():
    """模拟存储库"""
    repo = Mock()
    repo.create = AsyncMock(return_value=Mock(id=str(uuid.uuid4())))
    repo.get_by_id = AsyncMock(return_value=Mock())
    repo.get = AsyncMock(return_value=[Mock()])
    repo.list = AsyncMock(return_value=[])
    repo.count = AsyncMock(return_value=0)
    repo.update = AsyncMock(return_value=Mock())
    repo.delete = AsyncMock(return_value=True)
    return repo


@pytest.mark.asyncio
class TestCreateAccount:
    """测试创建模拟账户"""

    @pytest.mark.skipif(not SERVICES_AVAILABLE, reason="Service not available")
    async def test_create_account_success(self, mock_repository):
        """测试成功创建账户"""
        if not SERVICES_AVAILABLE:
            return

        service = PaperTradingService()
        service.account_repo = mock_repository()
        service.position_repo = mock_repository()
        service.order_repo = mock_repository()
        service.trade_repo = mock_repository()

        account = await service.create_account(
            user_id="user-123",
            name="测试账户",
            initial_cash=100000.0,
            commission_rate=0.001,
            slippage_rate=0.001,
        )

        # 验证账户信息
        assert account.id is not None
        assert account.name == "测试账户"
        assert account.initial_cash == 100000.0
        assert account.current_cash == 100000.0
        assert account.total_equity == 100000.0
        assert account.commission_rate == 0.001
        assert account.slippage_rate == 0.001
        assert account.is_active == True

    @pytest.mark.skipif(not SERVICES_AVAILABLE, reason="Service not available")
    async def test_create_account_with_custom_params(self, mock_repository):
        """测试自定义参数创建账户"""
        if not SERVICES_AVAILABLE:
            return

        service = PaperTradingService()
        service.account_repo = mock_repository()

        account = await service.create_account(
            user_id="user-456",
            name="自定义账户",
            initial_cash=50000.0,
            commission_rate=0.0005,
            slippage_rate=0.0005,
        )

        assert account.commission_rate == 0.0005
        assert account.slippage_rate == 0.0005


@pytest.mark.asyncio
class TestSubmitOrder:
    """测试提交订单"""

    @pytest.mark.skipif(not SERVICES_AVAILABLE, reason="Service not available")
    async def test_submit_market_buy_order(self, mock_repository):
        """测试市价买单"""
        if not SERVICES_AVAILABLE:
            return

        service = PaperTradingService()
        service.account_repo = mock_repository()
        service.position_repo = mock_repository()
        service.order_repo = mock_repository()

        # Mock 账户
        mock_account = Mock(
            id="account-123",
            user_id="user-123",
            name="测试账户",
            initial_cash=100000.0,
            current_cash=95000.0,
            total_equity=100000.0,
            commission_rate=0.001,
            slippage_rate=0.001,
            is_active=True,
        )
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)

        # Mock 持仓（无持仓）
        service.position_repo.list = AsyncMock(return_value=[])
        service.position_repo.get_by_id = AsyncMock(return_value=None)

        # Mock order 创建
        mock_order = Mock(
            id=str(uuid.uuid4()),
            symbol="000001.SZ",
            order_type=OrderType.MARKET,
            side=OrderSide.BUY,
            size=100,
            status=OrderStatus.FILLED,
        )
        service.order_repo.create = AsyncMock(return_value=mock_order)

        # Mock 价格
        with patch.object(service, '_get_simulated_price', return_value=10.5):
            order = await service.submit_order(
                user_id="user-123",
                account_id="account-123",
                symbol="000001.SZ",
                order_type="market",
                side="buy",
                size=100,
            )

        # 验证订单
        assert order.symbol == "000001.SZ"
        assert order.order_type == OrderType.MARKET
        assert order.side == OrderSide.BUY
        assert order.size == 100
        assert order.status == OrderStatus.FILLED
        assert order.filled_size == 100
        assert order.avg_fill_price == 10.5  # 市价买入

    @pytest.mark.skipif(not SERVICES_AVAILABLE, reason="Service not available")
    async def test_submit_limit_sell_order(self, mock_repository):
        """测试限价卖单"""
        if not SERVICES_AVAILABLE:
            return

        service = PaperTradingService()
        service.account_repo = mock_repository()
        service.position_repo = mock_repository()
        service.order_repo = mock_repository()

        # Mock 账户
        mock_account = Mock(
            id="account-456",
            user_id="user-456",
            name="测试账户2",
            initial_cash=100000.0,
            current_cash=100000.0,
            total_equity=100000.0,
            commission_rate=0.001,
            slippage_rate=0.001,
            is_active=True,
        )
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)

        # Mock 持仓（有持仓）
        mock_position = Mock(
            id="position-123",
            symbol="000002.SZ",
            size=100,
            avg_price=10.0,
        side="long",
            market_value=1000.0,
        unrealized_pnl=100.0,
        unrealized_pnl_pct=10.0,
        entry_price=10.0,
        entry_time=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        )
        service.position_repo.get_by_id = AsyncMock(return_value=mock_position)
        service.position_repo.list = AsyncMock(return_value=[mock_position])

        # Mock order 创建
        mock_order = Mock(
            id=str(uuid.uuid4()),
            symbol="000002.SZ",
            order_type=OrderType.LIMIT,
            side=OrderSide.SELL,
            size=50,
            status=OrderStatus.FILLED,
        )
        service.order_repo.create = AsyncMock(return_value=mock_order)

        # Mock 价格
        with patch.object(service, '_get_simulated_price', return_value=10.2):
            order = await service.submit_order(
                user_id="user-456",
                account_id="account-456",
                symbol="000002.SZ",
                order_type="limit",
                side="sell",
                size=50,
                price=10.2,
            )

        # 验证订单
        assert order.symbol == "000002.SZ"
        assert order.price == 10.2
        assert order.side == OrderSide.SELL


@pytest.mark.asyncio
class TestOrderExecution:
    """测试订单执行"""

    @pytest.mark.skipif(not SERVICES_AVAILABLE, reason="Service not available")
    async def test_process_order_insufficient_funds(self, mock_repository):
        """测试资金不足"""
        if not SERVICES_AVAILABLE:
            return

        service = PaperTradingService()
        service.account_repo = mock_repository()
        service.position_repo = mock_repository()
        service.order_repo = mock_repository()

        # Mock 账户（只有 500 现金）
        mock_account = Mock(
            id="account-789",
            user_id="user-789",
            name="测试账户3",
            initial_cash=100000.0,
            current_cash=500.0,
            total_equity=100000.0,
            commission_rate=0.001,
            slippage_rate=0.001,
            is_active=True,
        )
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)

        # Mock order
        mock_order = Mock(id=str(uuid.uuid4()))
        service.order_repo.create = AsyncMock(return_value=mock_order)

        # 提交订单（应该被拒绝）
        order = await service.submit_order(
            user_id="user-789",
            account_id="account-789",
            symbol="000001.SZ",
            order_type="market",
            side="buy",
            size=100,  # 需要 1050 现金
            price=None,
        )

        # 验证订单被拒绝
        assert order.status == OrderStatus.REJECTED

    @pytest.mark.skipif(not SERVICES_AVAILABLE, reason="Service not available")
    async def test_process_order_insufficient_position(self, mock_repository):
        """测试持仓不足"""
        if not SERVICES_AVAILABLE:
            return

        service = PaperTradingService()
        service.account_repo = mock_repository()
        service.position_repo = mock_repository()
        service.order_repo = mock_repository()

        # Mock 账户
        mock_account = Mock(
            id="account-101",
            user_id="user-101",
            name="测试账户4",
            initial_cash=100000.0,
            current_cash=100000.0,
            total_equity=100000.0,
            commission_rate=0.001,
            slippage_rate=0.001,
            is_active=True,
        )
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)

        # Mock 持仓（空头持仓为0）
        mock_position = Mock(
            id="position-456",
            symbol="000003.SZ",
            size=0,
            avg_price=0.0,
            side="flat",
            market_value=0.0,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
            entry_price=0.0,
            entry_time=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        service.position_repo.get_by_id = AsyncMock(return_value=mock_position)
        service.position_repo.list = AsyncMock(return_value=[mock_position])

        # Mock order
        mock_order = Mock(id=str(uuid.uuid4()))
        service.order_repo.create = AsyncMock(return_value=mock_order)

        # 提交卖单（应该被拒绝）
        order = await service.submit_order(
            user_id="user-101",
            account_id="account-101",
            symbol="000003.SZ",
            order_type="market",
            side="sell",
            size=100,  # 没有持仓
        )

        # 验证订单被拒绝
        assert order.status == OrderStatus.REJECTED


@pytest.mark.asyncio
class TestPositionUpdate:
    """测试持仓更新"""

    @pytest.mark.skipif(not SERVICES_AVAILABLE, reason="Service not available")
    async def test_open_long_position(self, mock_repository):
        """测试开多头仓位"""
        if not SERVICES_AVAILABLE:
            return

        service = PaperTradingService()
        service.account_repo = mock_repository()
        service.position_repo = mock_repository()
        service.order_repo = mock_repository()

        # Mock 账户
        mock_account = Mock(
            id="account-202",
            user_id="user-202",
            name="测试账户5",
            initial_cash=100000.0,
            current_cash=95000.0,
            total_equity=100000.0,
            commission_rate=0.001,
            slippage_rate=0.001,
            is_active=True,
        )
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)
        service.position_repo.get = AsyncMock(return_value=Mock())
        service.position_repo.update = AsyncMock(return_value=Mock())
        service.position_repo.list = AsyncMock(return_value=[])

        # Mock order
        mock_order = Mock(
            id=str(uuid.uuid4()),
            symbol="000001.SZ",
            order_type=OrderType.MARKET,
            side=OrderSide.BUY,
            size=100,
            status=OrderStatus.FILLED,
        )
        service.order_repo.create = AsyncMock(return_value=mock_order)

        # Mock 价格
        with patch.object(service, '_get_simulated_price', return_value=10.0):
            # 处理订单
            await service._process_order(mock_order)

        # 验证持仓已创建
        positions = await service.position_repo.list(
            filters={"symbol": "000001.SZ", "user_id": "user-202"}
        )

        assert len(positions) == 1
        position = positions[0]
        assert position.symbol == "000001.SZ"
        assert position.size == 100
        assert position.side == "long"
        assert position.avg_price == 10.0
        assert position.market_value == 1000.0
        assert position.unrealized_pnl == 0.0  # 刚开仓，无盈亏

    @pytest.mark.skipif(not SERVICES_AVAILABLE, reason="Service not available")
    async def test_close_long_position(self, mock_repository):
        """测试平多头仓位"""
        if not SERVICES_AVAILABLE:
            return

        service = PaperTradingService()
        service.account_repo = mock_repository()
        service.position_repo = mock_repository()
        service.order_repo = mock_repository()

        # Mock 账户和持仓
        mock_account = Mock(
            id="account-303",
            user_id="user-303",
            name="测试账户6",
            initial_cash=100000.0,
            current_cash=100000.0,
            total_equity=100000.0,
            commission_rate=0.001,
            slippage_rate=0.001,
            is_active=True,
        )
        service.account_repo.get_by_id = AsyncMock(return_value=mock_account)
        service.account_repo.update = AsyncMock(return_value=Mock())

        mock_position = Mock(
            id="position-789",
            symbol="000001.SZ",
            size=100,
            avg_price=10.0,
            side="long",
            market_value=1000.0,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
            entry_price=10.0,
            entry_time=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        service.position_repo.get_by_id = AsyncMock(return_value=mock_position)
        service.position_repo.list = AsyncMock(return_value=[mock_position])

        # Mock order
        mock_order = Mock(
            id=str(uuid.uuid4()),
            symbol="000001.SZ",
            order_type=OrderType.MARKET,
            side=OrderSide.SELL,
            size=100,
            status=OrderStatus.FILLED,
        )
        service.order_repo.create = AsyncMock(return_value=mock_order)

        # Mock 价格（平仓盈利）
        with patch.object(service, '_get_simulated_price', return_value=11.0):
            # 处理订单
            await service._process_order(mock_order)

        # 验证持仓
        position = await service.position_repo.get_by_id("position-789")
        assert position is not None
        assert position.size == 0
        assert position.unrealized_pnl == 100.0  # 100 * (11.0 - 10.0)


@pytest.mark.asyncio
class TestSlippageCalculation:
    """测试滑点计算"""

    @pytest.mark.skipif(not SERVICES_AVAILABLE, reason="Service not available")
    async def test_market_buy_slippage(self, mock_repository):
        """测试市价买单滑点"""
        if not SERVICES_AVAILABLE:
            return

        service = PaperTradingService()

        # 测试市价买单（应该有正滑点）
        slippage = service._calculate_slippage(
            order_price=None,
            market_price=10.0,
            slippage_rate=0.001,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
        )

        assert slippage == 0.01  # 买入价格 = 市价 + 滑点

    @pytest.mark.skipif(not SERVICES_AVAILABLE, reason="Service not available")
    async def test_market_sell_slippage(self, mock_repository):
        """测试市价卖单滑点"""
        if not SERVICES_AVAILABLE:
            return

        service = PaperTradingService()

        # 测试市价卖单（应该有负滑点）
        slippage = service._calculate_slippage(
            order_price=None,
            market_price=10.0,
            slippage_rate=0.001,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
        )

        assert slippage == -0.01  # 卖出价格 = 市价 - 滑点

    @pytest.mark.skipif(not SERVICES_AVAILABLE, reason="Service not available")
    async def test_limit_order_slippage(self, mock_repository):
        """测试限价单滑点（限价优于市价，不应滑点）"""
        if not SERVICES_AVAILABLE:
            return

        service = PaperTradingService()

        # 测试限价买单（限价 < 市价，买入价格不应滑点）
        slippage = service._calculate_slippage(
            order_price=9.5,  # 限价 9.5
            market_price=10.0,  # 市价 10.0
            slippage_rate=0.001,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
        )

        assert slippage == 0.0  # 限价买入，成交价应为限价
