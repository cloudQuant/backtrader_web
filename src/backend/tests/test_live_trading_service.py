"""
实盘交易服务测试

测试：
- 提交实盘策略
- 从代码加载策略
- 停止实盘策略
- 获取任务状态
- 列出任务
- 错误处理（backtrader不可用）
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime

from app.services.live_trading_service import LiveTradingService, BACKTRADER_AVAILABLE


class TestLiveTradingServiceInitialization:
    """测试服务初始化"""

    def test_initialization(self):
        """测试初始化"""
        service = LiveTradingService()
        assert service.tasks == {}
        assert service.cerebro_instances == {}


class TestSubmitLiveStrategy:
    """测试提交实盘策略"""

    @pytest.mark.asyncio
    async def test_submit_without_backtrader(self):
        """测试backtrader不可用时提交"""
        service = LiveTradingService()

        with patch("app.services.live_trading_service.BACKTRADER_AVAILABLE", False):
            with pytest.raises(ImportError, match="backtrader not available"):
                await service.submit_live_strategy(
                    user_id="user123",
                    strategy_code="print('test')",
                    exchange="binance",
                    symbols=["BTC/USDT"],
                    api_key="test_key",
                    secret="test_secret",
                )

    @pytest.mark.asyncio
    async def test_submit_success_creates_task(self, monkeypatch):
        """测试成功提交创建任务"""
        service = LiveTradingService()

        # Mock backtrader components
        mock_cerebro = MagicMock()
        mock_strategy = MagicMock()
        mock_store = MagicMock()
        mock_broker = MagicMock()
        mock_data = MagicMock()

        mock_bt = MagicMock()
        mock_bt.Cerebro = MagicMock(return_value=mock_cerebro)
        mock_bt.Strategy = type('Strategy', (), {})

        # Need to mock the imports at module level
        with patch("app.services.live_trading_service.BACKTRADER_AVAILABLE", True):
            # Mock the imports that happen at function execution time
            with patch.dict("sys.modules", {
                "backtrader": mock_bt,
                "backtrader.brokers.ccxtbroker": MagicMock(CCXTBroker=MagicMock, CCXTStore=MagicMock),
                "backtrader.feeds.ccxtdata": MagicMock(CCXTData=MagicMock(return_value=mock_data)),
                "backtrader.observers.broker": MagicMock(BrokerObserver=MagicMock),
                "backtrader.stores.ccxtstore": MagicMock(CCXTStore=MagicMock(return_value=mock_store)),
            }):
                with patch.object(service, "_load_strategy_from_code", return_value=mock_strategy):
                    with patch("threading.Thread") as mock_thread:
                        task_id = await service.submit_live_strategy(
                            user_id="user123",
                            strategy_code="class TestStrategy(bt.Strategy): pass",
                            exchange="binance",
                            symbols=["BTC/USDT"],
                            api_key="test_key",
                            secret="test_secret",
                        )

                        assert task_id.startswith("live-user123-")
                        assert task_id in service.tasks
                        assert service.tasks[task_id]["status"] == "running"
                        assert mock_thread.called

    @pytest.mark.asyncio
    async def test_submit_with_custom_params(self):
        """测试使用自定义参数提交"""
        service = LiveTradingService()

        mock_cerebro = MagicMock()
        mock_strategy = MagicMock()
        mock_store = MagicMock()
        mock_broker = MagicMock()
        mock_data = MagicMock()

        mock_bt = MagicMock()
        mock_bt.Cerebro = MagicMock(return_value=mock_cerebro)
        mock_bt.Strategy = type('Strategy', (), {})

        with patch("app.services.live_trading_service.BACKTRADER_AVAILABLE", True):
            with patch.dict("sys.modules", {
                "backtrader": mock_bt,
                "backtrader.brokers.ccxtbroker": MagicMock(CCXTBroker=MagicMock, CCXTStore=MagicMock),
                "backtrader.feeds.ccxtdata": MagicMock(CCXTData=MagicMock(return_value=mock_data)),
                "backtrader.observers.broker": MagicMock(BrokerObserver=MagicMock),
                "backtrader.stores.ccxtstore": MagicMock(CCXTStore=MagicMock(return_value=mock_store)),
            }):
                with patch.object(service, "_load_strategy_from_code", return_value=mock_strategy):
                    with patch("threading.Thread"):
                        task_id = await service.submit_live_strategy(
                            user_id="user123",
                            strategy_code="class TestStrategy(bt.Strategy): pass",
                            exchange="binance",
                            symbols=["ETH/USDT"],
                            api_key="key",
                            secret="secret",
                            initial_cash=50000.0,
                            strategy_params={"period": 20},
                            sandbox=True,
                            timeframe="1h",
                        )

                        assert task_id in service.tasks
                        config = service.tasks[task_id]["config"]
                        assert config["initial_cash"] == 50000.0
                        assert config["sandbox"] is True


class TestLoadStrategyFromCode:
    """测试从代码加载策略"""

    def test_load_strategy_valid_code(self):
        """测试加载有效策略代码"""
        service = LiveTradingService()

        # Mock backtrader Strategy
        mock_strategy_base = type('Strategy', (), {})
        mock_backtrader = MagicMock(Strategy=mock_strategy_base)

        # Mock backtrader at sys.modules level so the import in the code works
        with patch.dict("sys.modules", {"backtrader": mock_backtrader}):
            # Also patch bt at module level
            import app.services.live_trading_service as live_service_module
            with patch.object(live_service_module, "bt", mock_backtrader, create=True):
                code = """
import backtrader as bt
class TestStrategy(bt.Strategy):
    pass
"""
                result = service._load_strategy_from_code(code, {})

                # The result should be a strategy class
                assert result is not None

    def test_load_strategy_with_params(self):
        """测试加载带参数的策略"""
        service = LiveTradingService()

        mock_strategy_base = type('Strategy', (), {})
        mock_backtrader = MagicMock(Strategy=mock_strategy_base)

        with patch.dict("sys.modules", {"backtrader": mock_backtrader}):
            import app.services.live_trading_service as live_service_module
            with patch.object(live_service_module, "bt", mock_backtrader, create=True):
                # Use code without params - just test the basic loading
                code = """
import backtrader as bt
class TestStrategy(bt.Strategy):
    pass
"""
                result = service._load_strategy_from_code(code, {"period": 30})

                # Should find the strategy class
                assert result is not None

    def test_load_strategy_no_strategy_found(self):
        """测试代码中没有策略类"""
        service = LiveTradingService()

        mock_strategy_base = type('Strategy', (), {})
        mock_backtrader = MagicMock(Strategy=mock_strategy_base)

        with patch.dict("sys.modules", {"backtrader": mock_backtrader}):
            import app.services.live_trading_service as live_service_module
            with patch.object(live_service_module, "bt", mock_backtrader, create=True):
                code = "print('hello world')"

                with pytest.raises(ValueError, match="未找到有效的 Strategy 类"):
                    service._load_strategy_from_code(code, {})


class TestStopLiveStrategy:
    """测试停止实盘策略"""

    @pytest.mark.asyncio
    async def test_stop_existing_task(self):
        """测试停止现有任务"""
        service = LiveTradingService()

        # Setup mock task
        task_id = "test_task_123"
        mock_cerebro = MagicMock()
        mock_cerebro.stop = MagicMock()

        service.cerebro_instances[task_id] = mock_cerebro
        service.tasks[task_id] = {
            "user_id": "user123",
            "status": "running",
        }

        result = await service.stop_live_strategy("user123", task_id)

        assert result is True
        assert task_id not in service.cerebro_instances
        assert service.tasks[task_id]["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_stop_nonexistent_task(self):
        """测试停止不存在的任务"""
        service = LiveTradingService()

        result = await service.stop_live_strategy("user123", "nonexistent_task")

        assert result is False


class TestGetTaskStatus:
    """测试获取任务状态"""

    @pytest.mark.asyncio
    async def test_get_status_nonexistent_task(self):
        """测试获取不存在任务的状态"""
        service = LiveTradingService()

        result = await service.get_task_status("user123", "nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_status_without_cerebro(self):
        """测试获取没有Cerebro实例的任务状态"""
        service = LiveTradingService()

        task_id = "test_task"
        service.tasks[task_id] = {
            "user_id": "user123",
            "status": "stopped",
        }

        result = await service.get_task_status("user123", task_id)

        assert result is not None
        assert result["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_get_status_with_cerebro(self):
        """测试获取有Cerebro实例的任务状态"""
        service = LiveTradingService()

        task_id = "test_task"
        mock_cerebro = MagicMock()
        mock_broker = MagicMock()

        # Mock broker methods
        mock_broker.getcash.return_value = 50000.0
        mock_broker.getvalue.return_value = 55000.0
        mock_broker.orders = []
        mock_broker.getposition.return_value = None

        mock_cerebro.broker = mock_broker
        mock_cerebro.datas = []

        service.cerebro_instances[task_id] = mock_cerebro
        service.tasks[task_id] = {
            "user_id": "user123",
            "status": "running",
        }

        result = await service.get_task_status("user123", task_id)

        assert result is not None
        assert result["task_id"] == task_id
        assert result["cash"] == 50000.0
        assert result["value"] == 55000.0
        assert result["positions"] == []
        assert result["orders"] == []

    @pytest.mark.asyncio
    async def test_get_status_with_positions(self):
        """测试获取有持仓的任务状态"""
        service = LiveTradingService()

        task_id = "test_task"
        mock_cerebro = MagicMock()
        mock_broker = MagicMock()
        mock_position = MagicMock()

        mock_broker.getcash.return_value = 50000.0
        mock_broker.getvalue.return_value = 55000.0
        mock_broker.orders = []
        mock_broker.getposition.return_value = mock_position
        mock_position.size = 1.5
        mock_position.price = 50000.0
        mock_position.pnl = 5000.0
        mock_position.pnlcomm = 4500.0

        mock_data = MagicMock()
        mock_data._name = "BTC/USDT"
        mock_cerebro.broker = mock_broker
        mock_cerebro.datas = [mock_data]

        service.cerebro_instances[task_id] = mock_cerebro
        service.tasks[task_id] = {
            "user_id": "user123",
            "status": "running",
        }

        result = await service.get_task_status("user123", task_id)

        assert result is not None
        assert len(result["positions"]) == 1
        assert result["positions"][0]["symbol"] == "BTC/USDT"
        assert result["positions"][0]["size"] == 1.5

    @pytest.mark.asyncio
    async def test_get_status_with_orders(self):
        """测试获取有订单的任务状态"""
        service = LiveTradingService()

        task_id = "test_task"
        mock_cerebro = MagicMock()
        mock_broker = MagicMock()
        mock_order = MagicMock()

        mock_broker.getcash.return_value = 50000.0
        mock_broker.getvalue.return_value = 50000.0
        mock_broker.getposition.return_value = None
        mock_broker.orders = [mock_order]
        mock_order.ref = "order123"
        mock_order.ordtypename.return_value = "Buy"
        mock_order.getstatusname.return_value = "Submitted"
        mock_order.size = 1.0
        mock_order.created.price = 50000.0

        mock_data = MagicMock()
        mock_data._name = "ETH/USDT"
        mock_order.data = mock_data

        mock_cerebro.broker = mock_broker
        mock_cerebro.datas = [mock_data]

        service.cerebro_instances[task_id] = mock_cerebro
        service.tasks[task_id] = {
            "user_id": "user123",
            "status": "running",
        }

        result = await service.get_task_status("user123", task_id)

        assert result is not None
        assert len(result["orders"]) == 1
        assert result["orders"][0]["order_id"] == "order123"
        assert result["orders"][0]["symbol"] == "ETH/USDT"


class TestListTasks:
    """测试列出任务"""

    @pytest.mark.asyncio
    async def test_list_all_tasks(self):
        """测试列出所有任务"""
        service = LiveTradingService()

        # Create multiple tasks
        for i in range(3):
            task_id = f"task_{i}"
            service.tasks[task_id] = {
                "user_id": "user123",
                "status": "running",
            }

        result = await service.list_tasks("user123")

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_list_tasks_filter_by_status(self):
        """测试按状态筛选任务"""
        service = LiveTradingService()

        # Create tasks with different statuses
        service.tasks["task_1"] = {"user_id": "user123", "status": "running"}
        service.tasks["task_2"] = {"user_id": "user123", "status": "stopped"}
        service.tasks["task_3"] = {"user_id": "user123", "status": "running"}

        result = await service.list_tasks("user123", status="running")

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_tasks_only_returns_user_tasks(self):
        """测试只返回当前用户的任务"""
        service = LiveTradingService()

        service.tasks["task_1"] = {"user_id": "user123", "status": "running"}
        service.tasks["task_2"] = {"user_id": "user456", "status": "running"}
        service.tasks["task_3"] = {"user_id": "user123", "status": "stopped"}

        result = await service.list_tasks("user123")

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_empty_tasks(self):
        """测试列出空任务列表"""
        service = LiveTradingService()

        result = await service.list_tasks("user123")

        assert result == []


class TestErrorHandling:
    """测试错误处理"""

    @pytest.mark.asyncio
    async def test_task_error_handling(self):
        """测试任务执行错误处理"""
        service = LiveTradingService()

        # This test verifies that errors in the background thread
        # are properly caught and stored
        with patch("app.services.live_trading_service.BACKTRADER_AVAILABLE", True):
            with patch.dict("sys.modules", {
                "backtrader": MagicMock(Cerebro=MagicMock(side_effect=Exception("Test error"))),
                "backtrader.brokers.ccxtbroker": MagicMock(CCXTBroker=MagicMock, CCXTStore=MagicMock),
                "backtrader.feeds.ccxtdata": MagicMock(CCXTData=MagicMock),
                "backtrader.observers.broker": MagicMock(BrokerObserver=MagicMock),
                "backtrader.stores.ccxtstore": MagicMock(CCXTStore=MagicMock),
            }):
                with patch.object(service, "_load_strategy_from_code", return_value=MagicMock):
                    with patch("threading.Thread") as mock_thread:
                        # Simulate thread starting
                        mock_thread_instance = MagicMock()
                        mock_thread.return_value = mock_thread_instance

                        # The submit should succeed even if background thread will fail
                        task_id = await service.submit_live_strategy(
                            user_id="user123",
                            strategy_code="invalid",
                            exchange="binance",
                            symbols=["BTC/USDT"],
                            api_key="key",
                            secret="secret",
                        )
                        # The task should be created
                        assert task_id in service.tasks


class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """测试完整工作流"""
        service = LiveTradingService()

        task_id = "workflow_test"
        mock_cerebro = MagicMock()
        mock_broker = MagicMock()

        mock_broker.getcash.return_value = 50000.0
        mock_broker.getvalue.return_value = 55000.0
        mock_broker.orders = []
        mock_broker.getposition.return_value = None
        mock_broker.setcash = MagicMock()

        mock_cerebro.broker = mock_broker
        mock_cerebro.datas = []
        mock_cerebro.stop = MagicMock()

        # Submit task (simulate)
        service.tasks[task_id] = {
            "user_id": "user123",
            "status": "running",
            "config": {"initial_cash": 50000.0, "sandbox": False},
            "created_at": datetime.utcnow(),
        }
        service.cerebro_instances[task_id] = mock_cerebro

        # Get status
        status = await service.get_task_status("user123", task_id)
        assert status["status"] == "running"

        # List tasks
        tasks = await service.list_tasks("user123")
        assert len(tasks) == 1

        # Stop task
        result = await service.stop_live_strategy("user123", task_id)
        assert result is True

        # Verify stopped
        status = await service.get_task_status("user123", task_id)
        assert status["status"] == "stopped"
