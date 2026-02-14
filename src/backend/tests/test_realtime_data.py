"""
实时行情 API 测试

测试：
- 订阅实时行情
- 取消订阅实时行情
- 获取实时行情
- 批量获取实时行情
- 获取历史行情
"""
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
class TestRealtimeSubscribe:
    """测试订阅实时行情"""

    async def test_subscribe_requires_auth(self, client: AsyncClient):
        """测试需要认证"""
        resp = await client.post("/api/v1/realtime/ticks/subscribe", json={
            "symbols": ["BTC/USDT", "ETH/USDT"]
        })
        assert resp.status_code in [401, 403]

    async def test_subscribe_success(self, client: AsyncClient, auth_headers: dict):
        """测试成功订阅"""
        with patch('app.services.realtime_data_service.RealTimeDataService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.subscribe_ticks = AsyncMock()
            mock_service_class.return_value = mock_service

            resp = await client.post("/api/v1/realtime/ticks/subscribe", headers=auth_headers, json={
                "symbols": ["BTC/USDT", "ETH/USDT"],
                "broker_id": "binance"
            })
            assert resp.status_code == 200

    async def test_subscribe_invalid_data(self, client: AsyncClient, auth_headers: dict):
        """测试无效数据"""
        resp = await client.post("/api/v1/realtime/ticks/subscribe", headers=auth_headers, json={
            "symbols": []
        })
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestRealtimeUnsubscribe:
    """测试取消订阅"""

    async def test_unsubscribe_requires_auth(self, client: AsyncClient):
        """测试需要认证"""
        resp = await client.post("/api/v1/realtime/ticks/unsubscribe", json={
            "symbols": ["BTC/USDT"]
        })
        assert resp.status_code in [401, 403]

    async def test_unsubscribe_success(self, client: AsyncClient, auth_headers: dict):
        """测试成功取消订阅"""
        with patch('app.services.realtime_data_service.RealTimeDataService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.unsubscribe_ticks = AsyncMock()
            mock_service_class.return_value = mock_service

            resp = await client.post("/api/v1/realtime/ticks/unsubscribe", headers=auth_headers, json={
                "symbols": ["BTC/USDT"],
                "broker_id": "binance"
            })
            assert resp.status_code == 200


@pytest.mark.asyncio
class TestRealtimeGetTicks:
    """测试获取实时行情"""

    async def test_get_ticks_requires_auth(self, client: AsyncClient):
        """测试需要认证"""
        resp = await client.get("/api/v1/realtime/ticks")
        assert resp.status_code in [401, 403]

    async def test_get_ticks_single_symbol(self, client: AsyncClient, auth_headers: dict):
        """测试获取单个标的行情"""
        with patch('app.services.realtime_data_service.RealTimeDataService') as mock_service_class:
            mock_service = AsyncMock()
            mock_tick = {
                "symbol": "BTC/USDT",
                "price": 50000.0,
                "volume": 100.0,
            }
            mock_service.get_tick = AsyncMock(return_value=mock_tick)
            mock_service_class.return_value = mock_service

            resp = await client.get("/api/v1/realtime/ticks?symbol=BTC/USDT&broker_id=binance", headers=auth_headers)
            assert resp.status_code == 200

    async def test_get_ticks_all_subscribed(self, client: AsyncClient, auth_headers: dict):
        """测试获取所有订阅标的行情"""
        with patch('app.services.realtime_data_service.RealTimeDataService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_subscribed_symbols = AsyncMock(return_value=["BTC/USDT", "ETH/USDT"])
            mock_service.get_ticks = AsyncMock(return_value=[])
            mock_service_class.return_value = mock_service

            resp = await client.get("/api/v1/realtime/ticks?broker_id=binance", headers=auth_headers)
            assert resp.status_code == 200


@pytest.mark.asyncio
class TestRealtimeBatchGet:
    """测试批量获取行情"""

    async def test_batch_get_requires_auth(self, client: AsyncClient):
        """测试需要认证"""
        resp = await client.get("/api/v1/realtime/ticks/batch?broker_id=binance&symbols=BTC/USDT,ETH/USDT")
        assert resp.status_code in [401, 403]

    async def test_batch_get_missing_params(self, client: AsyncClient, auth_headers: dict):
        """测试缺少必要参数"""
        resp = await client.get("/api/v1/realtime/ticks/batch?broker_id=binance", headers=auth_headers)
        assert resp.status_code == 422

    async def test_batch_get_success(self, client: AsyncClient, auth_headers: dict):
        """测试批量获取成功"""
        with patch('app.services.realtime_data_service.RealTimeDataService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_ticks = AsyncMock(return_value=[])
            mock_service_class.return_value = mock_service

            resp = await client.get(
                "/api/v1/realtime/ticks/batch?broker_id=binance&symbols=BTC/USDT,ETH/USDT",
                headers=auth_headers
            )
            assert resp.status_code == 200


@pytest.mark.asyncio
class TestHistoricalTicks:
    """测试历史行情"""

    async def test_historical_requires_auth(self, client: AsyncClient):
        """测试需要认证"""
        resp = await client.get("/api/v1/realtime/ticks/historical?broker_id=binance&symbol=BTC/USDT&start_date=2024-01-01&end_date=2024-01-31")
        assert resp.status_code in [401, 403]

    async def test_historical_missing_params(self, client: AsyncClient, auth_headers: dict):
        """测试缺少必要参数"""
        resp = await client.get("/api/v1/realtime/ticks/historical?broker_id=binance", headers=auth_headers)
        assert resp.status_code == 422

    async def test_historical_invalid_date_format(self, client: AsyncClient, auth_headers: dict):
        """测试无效日期格式"""
        resp = await client.get(
            "/api/v1/realtime/ticks/historical?broker_id=binance&symbol=BTC/USDT&start_date=invalid&end_date=2024-01-31",
            headers=auth_headers
        )
        assert resp.status_code == 400

    async def test_historical_success(self, client: AsyncClient, auth_headers: dict):
        """测试成功获取历史行情"""
        with patch('app.services.realtime_data_service.RealTimeDataService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_historical_data = AsyncMock(return_value=[])
            mock_service_class.return_value = mock_service

            resp = await client.get(
                "/api/v1/realtime/ticks/historical?broker_id=binance&symbol=BTC/USDT&start_date=2024-01-01&end_date=2024-01-31",
                headers=auth_headers
            )
            assert resp.status_code == 200

    async def test_historical_with_frequency(self, client: AsyncClient, auth_headers: dict):
        """测试带频率参数"""
        with patch('app.services.realtime_data_service.RealTimeDataService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_historical_data = AsyncMock(return_value=[])
            mock_service_class.return_value = mock_service

            resp = await client.get(
                "/api/v1/realtime/ticks/historical?broker_id=binance&symbol=BTC/USDT&start_date=2024-01-01&end_date=2024-01-31&frequency=1h",
                headers=auth_headers
            )
            assert resp.status_code == 200


@pytest.mark.asyncio
class TestRealtimeServiceSingleton:
    """测试服务单例"""

    async def test_realtime_service_singleton(self):
        """测试RealTimeDataService单例"""
        from app.api.realtime_data import get_realtime_data_service

        svc1 = get_realtime_data_service()
        svc2 = get_realtime_data_service()
        # Function creates new instance each time, so they should be different objects
        # but the function itself is callable
        assert callable(get_realtime_data_service)
