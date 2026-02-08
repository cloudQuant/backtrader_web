"""
实时行情数据服务测试

测试：
- 订阅/取消订阅实时行情
- 获取订阅列表
- 获取最新行情
- 批量获取行情
- 获取历史行情
- 更新行情缓存
"""
import pytest
from datetime import datetime
from app.services.realtime_data_service import RealTimeDataService


@pytest.mark.asyncio
class TestRealTimeDataServiceInitialization:
    """测试服务初始化"""

    def test_initialization(self):
        """测试初始化"""
        service = RealTimeDataService()
        assert service._subscriptions == {}
        assert service._tick_cache == {}


@pytest.mark.asyncio
class TestSubscribeTicks:
    """测试订阅实时行情"""

    async def test_subscribe_single_symbol(self):
        """测试订阅单个标的"""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", "broker_1", ["BTC/USDT"])

        assert "user_123" in service._subscriptions
        assert "broker_1" in service._subscriptions["user_123"]
        assert "BTC/USDT" in service._subscriptions["user_123"]["broker_1"]

    async def test_subscribe_multiple_symbols(self):
        """测试订阅多个标的"""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", "broker_1", ["BTC/USDT", "ETH/USDT", "BNB/USDT"])

        assert len(service._subscriptions["user_123"]["broker_1"]) == 3
        assert "BTC/USDT" in service._subscriptions["user_123"]["broker_1"]
        assert "ETH/USDT" in service._subscriptions["user_123"]["broker_1"]
        assert "BNB/USDT" in service._subscriptions["user_123"]["broker_1"]

    async def test_subscribe_with_broker_none(self):
        """测试券商ID为None时使用默认值"""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", None, ["BTC/USDT"])

        assert "default" in service._subscriptions["user_123"]
        assert "BTC/USDT" in service._subscriptions["user_123"]["default"]

    async def test_subscribe_same_symbol_twice(self):
        """测试重复订阅同一标的"""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", "broker_1", ["BTC/USDT"])
        await service.subscribe_ticks("user_123", "broker_1", ["BTC/USDT", "ETH/USDT"])

        # BTC/USDT应该只出现一次
        btc_count = service._subscriptions["user_123"]["broker_1"].count("BTC/USDT")
        assert btc_count == 1
        assert "ETH/USDT" in service._subscriptions["user_123"]["broker_1"]

    async def test_subscribe_different_brokers(self):
        """测试订阅不同券商"""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", "broker_1", ["BTC/USDT"])
        await service.subscribe_ticks("user_123", "broker_2", ["ETH/USDT"])

        assert "broker_1" in service._subscriptions["user_123"]
        assert "broker_2" in service._subscriptions["user_123"]
        assert "BTC/USDT" in service._subscriptions["user_123"]["broker_1"]
        assert "ETH/USDT" in service._subscriptions["user_123"]["broker_2"]

    async def test_subscribe_multiple_users(self):
        """测试多个用户订阅"""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", "broker_1", ["BTC/USDT"])
        await service.subscribe_ticks("user_456", "broker_1", ["ETH/USDT"])

        assert "user_123" in service._subscriptions
        assert "user_456" in service._subscriptions
        assert "BTC/USDT" in service._subscriptions["user_123"]["broker_1"]
        assert "ETH/USDT" in service._subscriptions["user_456"]["broker_1"]


@pytest.mark.asyncio
class TestUnsubscribeTicks:
    """测试取消订阅"""

    async def test_unsubscribe_single_symbol(self):
        """测试取消单个标的订阅"""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", "broker_1", ["BTC/USDT", "ETH/USDT"])
        await service.unsubscribe_ticks("user_123", "broker_1", ["BTC/USDT"])

        assert "BTC/USDT" not in service._subscriptions["user_123"]["broker_1"]
        assert "ETH/USDT" in service._subscriptions["user_123"]["broker_1"]

    async def test_unsubscribe_multiple_symbols(self):
        """测试取消多个标的订阅"""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", "broker_1", ["BTC/USDT", "ETH/USDT", "BNB/USDT"])
        await service.unsubscribe_ticks("user_123", "broker_1", ["BTC/USDT", "ETH/USDT"])

        assert "BTC/USDT" not in service._subscriptions["user_123"]["broker_1"]
        assert "ETH/USDT" not in service._subscriptions["user_123"]["broker_1"]
        assert "BNB/USDT" in service._subscriptions["user_123"]["broker_1"]

    async def test_unsubscribe_nonexistent_symbol(self):
        """测试取消不存在的标的订阅"""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", "broker_1", ["BTC/USDT"])
        await service.unsubscribe_ticks("user_123", "broker_1", ["ETH/USDT"])

        # BTC/USDT应该仍然存在
        assert "BTC/USDT" in service._subscriptions["user_123"]["broker_1"]

    async def test_unsubscribe_with_broker_none(self):
        """测试券商ID为None时使用默认值"""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", None, ["BTC/USDT"])
        await service.unsubscribe_ticks("user_123", None, ["BTC/USDT"])

        assert "BTC/USDT" not in service._subscriptions["user_123"]["default"]

    async def test_unsubscribe_nonexistent_user(self):
        """测试取消不存在的用户订阅"""
        service = RealTimeDataService()

        # 不应该抛出异常
        await service.unsubscribe_ticks("nonexistent_user", "broker_1", ["BTC/USDT"])
        assert True


@pytest.mark.asyncio
class TestGetSubscribedSymbols:
    """测试获取订阅列表"""

    async def test_get_subscribed_symbols(self):
        """测试获取订阅列表"""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", "broker_1", ["BTC/USDT", "ETH/USDT"])

        symbols = await service.get_subscribed_symbols("user_123", "broker_1")

        assert symbols == ["BTC/USDT", "ETH/USDT"]

    async def test_get_subscribed_symbols_empty(self):
        """测试获取空订阅列表"""
        service = RealTimeDataService()

        symbols = await service.get_subscribed_symbols("user_123", "broker_1")

        assert symbols == []

    async def test_get_subscribed_symbols_with_broker_none(self):
        """测试券商ID为None时使用默认值"""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", None, ["BTC/USDT"])

        symbols = await service.get_subscribed_symbols("user_123", None)

        assert symbols == ["BTC/USDT"]

    async def test_get_subscribed_symbols_different_brokers(self):
        """测试获取不同券商的订阅"""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", "broker_1", ["BTC/USDT"])
        await service.subscribe_ticks("user_123", "broker_2", ["ETH/USDT"])

        broker1_symbols = await service.get_subscribed_symbols("user_123", "broker_1")
        broker2_symbols = await service.get_subscribed_symbols("user_123", "broker_2")

        assert broker1_symbols == ["BTC/USDT"]
        assert broker2_symbols == ["ETH/USDT"]


@pytest.mark.asyncio
class TestGetTick:
    """测试获取单个行情"""

    async def test_get_tick_from_cache(self):
        """测试从缓存获取行情"""
        service = RealTimeDataService()

        tick_data = {
            "symbol": "BTC/USDT",
            "price": 50000.0,
            "volume": 100.0,
        }
        service.update_tick("broker_1", "BTC/USDT", tick_data)

        result = await service.get_tick("user_123", "broker_1", "BTC/USDT")

        assert result["symbol"] == "BTC/USDT"
        assert result["price"] == 50000.0

    async def test_get_tick_not_cached(self):
        """测试获取未缓存的行情（返回模拟数据）"""
        service = RealTimeDataService()

        result = await service.get_tick("user_123", "broker_1", "BTC/USDT")

        assert result is not None
        assert result["symbol"] == "BTC/USDT"
        assert "timestamp" in result
        assert "open" in result
        assert "high" in result
        assert "low" in result
        assert "close" in result

    async def test_get_tick_with_broker_none(self):
        """测试券商ID为None时使用默认值"""
        service = RealTimeDataService()

        tick_data = {"symbol": "BTC/USDT", "price": 50000.0}
        service.update_tick("default", "BTC/USDT", tick_data)

        result = await service.get_tick("user_123", None, "BTC/USDT")

        assert result["price"] == 50000.0


@pytest.mark.asyncio
class TestGetTicks:
    """测试批量获取行情"""

    async def test_get_multiple_ticks(self):
        """测试批量获取多个行情"""
        service = RealTimeDataService()

        service.update_tick("broker_1", "BTC/USDT", {"symbol": "BTC/USDT", "price": 50000.0})
        service.update_tick("broker_1", "ETH/USDT", {"symbol": "ETH/USDT", "price": 3000.0})

        result = await service.get_ticks("user_123", "broker_1", ["BTC/USDT", "ETH/USDT"])

        assert "BTC/USDT" in result
        assert "ETH/USDT" in result
        assert result["BTC/USDT"]["price"] == 50000.0
        assert result["ETH/USDT"]["price"] == 3000.0

    async def test_get_ticks_empty_list(self):
        """测试获取空列表行情"""
        service = RealTimeDataService()

        result = await service.get_ticks("user_123", "broker_1", [])

        assert result == {}

    async def test_get_ticks_mixed_cached_and_uncached(self):
        """测试混合缓存和未缓存的行情"""
        service = RealTimeDataService()

        service.update_tick("broker_1", "BTC/USDT", {"symbol": "BTC/USDT", "price": 50000.0})

        result = await service.get_ticks("user_123", "broker_1", ["BTC/USDT", "ETH/USDT"])

        # BTC/USDT来自缓存
        assert result["BTC/USDT"]["price"] == 50000.0
        # ETH/USDT来自模拟数据
        assert result["ETH/USDT"]["symbol"] == "ETH/USDT"


@pytest.mark.asyncio
class TestGetHistoricalData:
    """测试获取历史行情"""

    async def test_get_historical_data(self):
        """测试获取历史行情"""
        service = RealTimeDataService()

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        result = await service.get_historical_data(
            "user_123",
            "broker_1",
            "BTC/USDT",
            start,
            end,
            "1d"
        )

        # 目前返回空列表
        assert result == []

    async def test_get_historical_data_different_frequency(self):
        """测试不同频率的历史数据"""
        service = RealTimeDataService()

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        result_1d = await service.get_historical_data(
            "user_123", "broker_1", "BTC/USDT", start, end, "1d"
        )
        result_1h = await service.get_historical_data(
            "user_123", "broker_1", "BTC/USDT", start, end, "1h"
        )

        # 都返回空列表
        assert result_1d == []
        assert result_1h == []


@pytest.mark.asyncio
class TestUpdateTick:
    """测试更新行情缓存"""

    def test_update_tick_new_broker(self):
        """测试更新新券商的行情"""
        service = RealTimeDataService()

        tick_data = {"symbol": "BTC/USDT", "price": 50000.0}
        service.update_tick("broker_1", "BTC/USDT", tick_data)

        assert "broker_1" in service._tick_cache
        assert service._tick_cache["broker_1"]["BTC/USDT"] == tick_data

    def test_update_tick_existing_broker(self):
        """测试更新已有券商的行情"""
        service = RealTimeDataService()

        tick_data1 = {"symbol": "BTC/USDT", "price": 50000.0}
        tick_data2 = {"symbol": "BTC/USDT", "price": 51000.0}

        service.update_tick("broker_1", "BTC/USDT", tick_data1)
        service.update_tick("broker_1", "BTC/USDT", tick_data2)

        # 应该被覆盖
        assert service._tick_cache["broker_1"]["BTC/USDT"]["price"] == 51000.0

    def test_update_tick_multiple_symbols(self):
        """测试更新多个标的的行情"""
        service = RealTimeDataService()

        service.update_tick("broker_1", "BTC/USDT", {"symbol": "BTC/USDT", "price": 50000.0})
        service.update_tick("broker_1", "ETH/USDT", {"symbol": "ETH/USDT", "price": 3000.0})

        assert len(service._tick_cache["broker_1"]) == 2
        assert service._tick_cache["broker_1"]["BTC/USDT"]["price"] == 50000.0
        assert service._tick_cache["broker_1"]["ETH/USDT"]["price"] == 3000.0
