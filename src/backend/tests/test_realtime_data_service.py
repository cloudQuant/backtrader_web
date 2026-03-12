"""
Real-time Market Data Service Tests.

Tests:
- Subscribe/unsubscribe to real-time market data
- Get subscription list
- Get latest market data
- Batch get market data
- Get historical market data
- Update market data cache
"""

from datetime import datetime

import pytest

from app.services.realtime_data_service import RealTimeDataService


class TestRealTimeDataServiceInitialization:
    """Tests for service initialization."""

    def test_initialization(self):
        """Test initialization."""
        service = RealTimeDataService()
        assert service._subscriptions == {}
        assert service._tick_cache == {}


@pytest.mark.asyncio
class TestSubscribeTicks:
    """Tests for subscribing to real-time market data."""

    async def test_subscribe_single_symbol(self):
        """Test subscribing to a single symbol."""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", "broker_1", ["BTC/USDT"])

        assert "user_123" in service._subscriptions
        assert "broker_1" in service._subscriptions["user_123"]
        assert "BTC/USDT" in service._subscriptions["user_123"]["broker_1"]

    async def test_subscribe_multiple_symbols(self):
        """Test subscribing to multiple symbols."""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", "broker_1", ["BTC/USDT", "ETH/USDT", "BNB/USDT"])

        assert len(service._subscriptions["user_123"]["broker_1"]) == 3
        assert "BTC/USDT" in service._subscriptions["user_123"]["broker_1"]
        assert "ETH/USDT" in service._subscriptions["user_123"]["broker_1"]
        assert "BNB/USDT" in service._subscriptions["user_123"]["broker_1"]

    async def test_subscribe_with_broker_none(self):
        """Test using default value when broker_id is None."""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", None, ["BTC/USDT"])

        assert "default" in service._subscriptions["user_123"]
        assert "BTC/USDT" in service._subscriptions["user_123"]["default"]

    async def test_subscribe_same_symbol_twice(self):
        """Test subscribing to the same symbol twice."""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", "broker_1", ["BTC/USDT"])
        await service.subscribe_ticks("user_123", "broker_1", ["BTC/USDT", "ETH/USDT"])

        # BTC/USDT should only appear once
        btc_count = service._subscriptions["user_123"]["broker_1"].count("BTC/USDT")
        assert btc_count == 1
        assert "ETH/USDT" in service._subscriptions["user_123"]["broker_1"]

    async def test_subscribe_different_brokers(self):
        """Test subscribing to different brokers."""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", "broker_1", ["BTC/USDT"])
        await service.subscribe_ticks("user_123", "broker_2", ["ETH/USDT"])

        assert "broker_1" in service._subscriptions["user_123"]
        assert "broker_2" in service._subscriptions["user_123"]
        assert "BTC/USDT" in service._subscriptions["user_123"]["broker_1"]
        assert "ETH/USDT" in service._subscriptions["user_123"]["broker_2"]

    async def test_subscribe_multiple_users(self):
        """Test multiple users subscribing."""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", "broker_1", ["BTC/USDT"])
        await service.subscribe_ticks("user_456", "broker_1", ["ETH/USDT"])

        assert "user_123" in service._subscriptions
        assert "user_456" in service._subscriptions
        assert "BTC/USDT" in service._subscriptions["user_123"]["broker_1"]
        assert "ETH/USDT" in service._subscriptions["user_456"]["broker_1"]


@pytest.mark.asyncio
class TestUnsubscribeTicks:
    """Tests for unsubscribing from market data."""

    async def test_unsubscribe_single_symbol(self):
        """Test unsubscribing from a single symbol."""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", "broker_1", ["BTC/USDT", "ETH/USDT"])
        await service.unsubscribe_ticks("user_123", "broker_1", ["BTC/USDT"])

        assert "BTC/USDT" not in service._subscriptions["user_123"]["broker_1"]
        assert "ETH/USDT" in service._subscriptions["user_123"]["broker_1"]

    async def test_unsubscribe_multiple_symbols(self):
        """Test unsubscribing from multiple symbols."""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", "broker_1", ["BTC/USDT", "ETH/USDT", "BNB/USDT"])
        await service.unsubscribe_ticks("user_123", "broker_1", ["BTC/USDT", "ETH/USDT"])

        assert "BTC/USDT" not in service._subscriptions["user_123"]["broker_1"]
        assert "ETH/USDT" not in service._subscriptions["user_123"]["broker_1"]
        assert "BNB/USDT" in service._subscriptions["user_123"]["broker_1"]

    async def test_unsubscribe_nonexistent_symbol(self):
        """Test unsubscribing from a non-existent symbol."""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", "broker_1", ["BTC/USDT"])
        await service.unsubscribe_ticks("user_123", "broker_1", ["ETH/USDT"])

        # BTC/USDT should still exist
        assert "BTC/USDT" in service._subscriptions["user_123"]["broker_1"]

    async def test_unsubscribe_with_broker_none(self):
        """Test using default value when broker_id is None."""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", None, ["BTC/USDT"])
        await service.unsubscribe_ticks("user_123", None, ["BTC/USDT"])

        assert "BTC/USDT" not in service._subscriptions["user_123"]["default"]

    async def test_unsubscribe_nonexistent_user(self):
        """Test unsubscribing a non-existent user."""
        service = RealTimeDataService()

        # Should not raise an exception
        await service.unsubscribe_ticks("nonexistent_user", "broker_1", ["BTC/USDT"])
        assert True


@pytest.mark.asyncio
class TestGetSubscribedSymbols:
    """Tests for getting subscription list."""

    async def test_get_subscribed_symbols(self):
        """Test getting subscription list."""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", "broker_1", ["BTC/USDT", "ETH/USDT"])

        symbols = await service.get_subscribed_symbols("user_123", "broker_1")

        assert symbols == ["BTC/USDT", "ETH/USDT"]

    async def test_get_subscribed_symbols_empty(self):
        """Test getting empty subscription list."""
        service = RealTimeDataService()

        symbols = await service.get_subscribed_symbols("user_123", "broker_1")

        assert symbols == []

    async def test_get_subscribed_symbols_with_broker_none(self):
        """Test using default value when broker_id is None."""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", None, ["BTC/USDT"])

        symbols = await service.get_subscribed_symbols("user_123", None)

        assert symbols == ["BTC/USDT"]

    async def test_get_subscribed_symbols_different_brokers(self):
        """Test getting subscriptions for different brokers."""
        service = RealTimeDataService()

        await service.subscribe_ticks("user_123", "broker_1", ["BTC/USDT"])
        await service.subscribe_ticks("user_123", "broker_2", ["ETH/USDT"])

        broker1_symbols = await service.get_subscribed_symbols("user_123", "broker_1")
        broker2_symbols = await service.get_subscribed_symbols("user_123", "broker_2")

        assert broker1_symbols == ["BTC/USDT"]
        assert broker2_symbols == ["ETH/USDT"]


@pytest.mark.asyncio
class TestGetTick:
    """Tests for getting single market data."""

    async def test_get_tick_from_cache(self):
        """Test getting market data from cache."""
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
        """Test getting uncached market data (returns mock data)."""
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
        """Test using default value when broker_id is None."""
        service = RealTimeDataService()

        tick_data = {"symbol": "BTC/USDT", "price": 50000.0}
        service.update_tick("default", "BTC/USDT", tick_data)

        result = await service.get_tick("user_123", None, "BTC/USDT")

        assert result["price"] == 50000.0


@pytest.mark.asyncio
class TestGetTicks:
    """Tests for batch getting market data."""

    async def test_get_multiple_ticks(self):
        """Test batch getting multiple market data."""
        service = RealTimeDataService()

        service.update_tick("broker_1", "BTC/USDT", {"symbol": "BTC/USDT", "price": 50000.0})
        service.update_tick("broker_1", "ETH/USDT", {"symbol": "ETH/USDT", "price": 3000.0})

        result = await service.get_ticks("user_123", "broker_1", ["BTC/USDT", "ETH/USDT"])

        assert "BTC/USDT" in result
        assert "ETH/USDT" in result
        assert result["BTC/USDT"]["price"] == 50000.0
        assert result["ETH/USDT"]["price"] == 3000.0

    async def test_get_ticks_empty_list(self):
        """Test getting empty list of market data."""
        service = RealTimeDataService()

        result = await service.get_ticks("user_123", "broker_1", [])

        assert result == {}

    async def test_get_ticks_mixed_cached_and_uncached(self):
        """Test mixed cached and uncached market data."""
        service = RealTimeDataService()

        service.update_tick("broker_1", "BTC/USDT", {"symbol": "BTC/USDT", "price": 50000.0})

        result = await service.get_ticks("user_123", "broker_1", ["BTC/USDT", "ETH/USDT"])

        # BTC/USDT from cache
        assert result["BTC/USDT"]["price"] == 50000.0
        # ETH/USDT from mock data
        assert result["ETH/USDT"]["symbol"] == "ETH/USDT"


@pytest.mark.asyncio
class TestGetHistoricalData:
    """Tests for getting historical market data."""

    async def test_get_historical_data(self):
        """Test getting historical market data."""
        service = RealTimeDataService()

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        result = await service.get_historical_data(
            "user_123", "broker_1", "BTC/USDT", start, end, "1d"
        )

        # Currently returns empty list
        assert result == []

    async def test_get_historical_data_different_frequency(self):
        """Test historical data with different frequencies."""
        service = RealTimeDataService()

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)

        result_1d = await service.get_historical_data(
            "user_123", "broker_1", "BTC/USDT", start, end, "1d"
        )
        result_1h = await service.get_historical_data(
            "user_123", "broker_1", "BTC/USDT", start, end, "1h"
        )

        # Both return empty lists
        assert result_1d == []
        assert result_1h == []


class TestUpdateTick:
    """Tests for updating market data cache."""

    def test_update_tick_new_broker(self):
        """Test updating market data for a new broker."""
        service = RealTimeDataService()

        tick_data = {"symbol": "BTC/USDT", "price": 50000.0}
        service.update_tick("broker_1", "BTC/USDT", tick_data)

        assert "broker_1" in service._tick_cache
        assert service._tick_cache["broker_1"]["BTC/USDT"] == tick_data

    def test_update_tick_existing_broker(self):
        """Test updating market data for an existing broker."""
        service = RealTimeDataService()

        tick_data1 = {"symbol": "BTC/USDT", "price": 50000.0}
        tick_data2 = {"symbol": "BTC/USDT", "price": 51000.0}

        service.update_tick("broker_1", "BTC/USDT", tick_data1)
        service.update_tick("broker_1", "BTC/USDT", tick_data2)

        # Should be overwritten
        assert service._tick_cache["broker_1"]["BTC/USDT"]["price"] == 51000.0

    def test_update_tick_multiple_symbols(self):
        """Test updating market data for multiple symbols."""
        service = RealTimeDataService()

        service.update_tick("broker_1", "BTC/USDT", {"symbol": "BTC/USDT", "price": 50000.0})
        service.update_tick("broker_1", "ETH/USDT", {"symbol": "ETH/USDT", "price": 3000.0})

        assert len(service._tick_cache["broker_1"]) == 2
        assert service._tick_cache["broker_1"]["BTC/USDT"]["price"] == 50000.0
        assert service._tick_cache["broker_1"]["ETH/USDT"]["price"] == 3000.0
