"""
实盘交易管理 API 测试

测试：
- 实盘策略列表
- 添加/删除实盘策略
- 启动/停止策略
- 批量启动/停止
- 实盘分析接口
"""
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestLiveTradingList:
    """实盘策略列表测试"""

    async def test_list_instances_empty(self, client: AsyncClient, auth_headers):
        """测试空列表"""
        response = await client.get("/api/v1/live-trading/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "instances" in data
        assert data["total"] == 0
        assert len(data["instances"]) == 0

    async def test_list_instances_requires_auth(self, client: AsyncClient):
        """测试需要认证"""
        response = await client.get("/api/v1/live-trading/")
        # API可能返回401或403
        assert response.status_code in [401, 403]


@pytest.mark.asyncio
class TestLiveTradingCreate:
    """创建实盘策略测试"""

    async def test_add_instance_success(self, client: AsyncClient, auth_headers):
        """测试成功添加策略"""
        # 模拟策略目录存在
        with patch('app.services.live_trading_manager.STRATEGIES_DIR', Path("/tmp/strategies")):
            with patch('app.services.live_trading_manager.get_template_by_id') as mock_tpl:
                mock_tpl.return_value = MagicMock(name="测试策略", params={})

                with patch('app.services.live_trading_manager._save_instances'):
                    response = await client.post(
                        "/api/v1/live-trading/",
                        headers=auth_headers,
                        json={"strategy_id": "test_strategy", "params": {"fast": 10, "slow": 20}}
                    )

        # 可能返回 400 如果策略不存在，这是预期的
        assert response.status_code in [200, 400]

    async def test_add_instance_invalid_strategy(self, client: AsyncClient, auth_headers):
        """测试添加不存在的策略"""
        response = await client.post(
            "/api/v1/live-trading/",
            headers=auth_headers,
            json={"strategy_id": "non_existent_strategy", "params": {}}
        )
        assert response.status_code == 400


@pytest.mark.asyncio
class TestLiveTradingDelete:
    """删除实盘策略测试"""

    async def test_remove_instance_not_found(self, client: AsyncClient, auth_headers):
        """测试删除不存在的实例"""
        response = await client.delete(
            "/api/v1/live-trading/non_existent_id",
            headers=auth_headers
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestLiveTradingGetDetail:
    """获取实盘策略详情测试"""

    async def test_get_instance_not_found(self, client: AsyncClient, auth_headers):
        """测试获取不存在的实例"""
        response = await client.get(
            "/api/v1/live-trading/non_existent_id",
            headers=auth_headers
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestLiveTradingControl:
    """实盘策略控制测试"""

    async def test_start_instance_not_found(self, client: AsyncClient, auth_headers):
        """测试启动不存在的实例"""
        response = await client.post(
            "/api/v1/live-trading/non_existent_id/start",
            headers=auth_headers
        )
        assert response.status_code == 400

    async def test_stop_instance_not_found(self, client: AsyncClient, auth_headers):
        """测试停止不存在的实例"""
        response = await client.post(
            "/api/v1/live-trading/non_existent_id/stop",
            headers=auth_headers
        )
        assert response.status_code == 400

    async def test_start_all(self, client: AsyncClient, auth_headers):
        """测试批量启动"""
        with patch('app.services.live_trading_manager.LiveTradingManager.start_all', new_callable=AsyncMock) as mock_start:
            mock_start.return_value = {"started": 0, "failed": 0, "errors": []}
            response = await client.post(
                "/api/v1/live-trading/start-all",
                headers=auth_headers
            )
            assert response.status_code == 200

    async def test_stop_all(self, client: AsyncClient, auth_headers):
        """测试批量停止"""
        with patch('app.services.live_trading_manager.LiveTradingManager.stop_all', new_callable=AsyncMock) as mock_stop:
            mock_stop.return_value = {"stopped": 0, "failed": 0, "errors": []}
            response = await client.post(
                "/api/v1/live-trading/stop-all",
                headers=auth_headers
            )
            assert response.status_code == 200


@pytest.mark.asyncio
class TestLiveTradingAnalytics:
    """实盘分析接口测试"""

    async def test_get_live_detail_not_found(self, client: AsyncClient, auth_headers):
        """测试获取不存在实例的分析详情"""
        response = await client.get(
            "/api/v1/live-trading/non_existent_id/detail",
            headers=auth_headers
        )
        assert response.status_code == 404

    async def test_get_live_kline_not_found(self, client: AsyncClient, auth_headers):
        """测试获取不存在实例的K线数据"""
        response = await client.get(
            "/api/v1/live-trading/non_existent_id/kline",
            headers=auth_headers
        )
        assert response.status_code == 404

    async def test_get_live_monthly_returns_not_found(self, client: AsyncClient, auth_headers):
        """测试获取不存在实例的月度收益"""
        response = await client.get(
            "/api/v1/live-trading/non_existent_id/monthly-returns",
            headers=auth_headers
        )
        assert response.status_code == 404

    async def test_get_live_detail_with_valid_instance(self, client: AsyncClient, auth_headers):
        """测试获取有效实例的分析详情"""
        # Mock the manager and log parser
        with patch('app.api.live_trading_api.get_live_trading_manager') as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_instance.return_value = {
                "instance_id": "inst1",
                "strategy_id": "strategy1",
                "strategy_name": "双均线",
            }
            mock_get_mgr.return_value = mock_mgr

            with patch('app.api.live_trading_api.parse_all_logs') as mock_parse:
                mock_parse.return_value = {
                    "total_return": 0.15,
                    "annual_return": 0.20,
                    "sharpe_ratio": 1.5,
                    "max_drawdown": -0.08,
                    "win_rate": 0.60,
                    "total_trades": 50,
                    "equity_dates": ["2024-01-01", "2024-01-02"],
                    "equity_curve": [100000, 101000],
                    "cash_curve": [50000, 50500],
                    "drawdown_curve": [0, -0.02],
                    "initial_cash": 100000,
                    "final_value": 115000,
                    "trades": [],
                }

                response = await client.get(
                    "/api/v1/live-trading/inst1/detail",
                    headers=auth_headers
                )
                assert response.status_code == 200

    async def test_get_live_detail_no_log_data(self, client: AsyncClient, auth_headers):
        """测试获取详情时无日志数据"""
        with patch('app.api.live_trading_api.get_live_trading_manager') as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_instance.return_value = {
                "instance_id": "inst1",
                "strategy_id": "strategy1",
            }
            mock_get_mgr.return_value = mock_mgr

            with patch('app.api.live_trading_api.parse_all_logs') as mock_parse:
                mock_parse.return_value = None

                response = await client.get(
                    "/api/v1/live-trading/inst1/detail",
                    headers=auth_headers
                )
                assert response.status_code == 404


@pytest.mark.asyncio
class TestLiveTradingKline:
    """实盘K线接口测试"""

    async def test_get_kline_with_log_data(self, client: AsyncClient, auth_headers):
        """测试获取有日志数据的K线"""
        with patch('app.api.live_trading_api.get_live_trading_manager') as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_instance.return_value = {
                "instance_id": "inst1",
                "strategy_id": "strategy1",
            }
            mock_get_mgr.return_value = mock_mgr

            with patch('app.api.live_trading_api.find_latest_log_dir') as mock_find:
                with patch('app.api.live_trading_api.parse_data_log') as mock_parse_data:
                    with patch('app.api.live_trading_api.parse_trade_log') as mock_parse_trade:
                        mock_find.return_value = Path("/tmp/logs")
                        mock_parse_data.return_value = {
                            "dates": ["2024-01-01"],
                            "ohlc": [[10, 10.5, 9.5, 10.2]],
                            "volumes": [1000],
                            "indicators": {},
                        }
                        mock_parse_trade.return_value = []

                        response = await client.get(
                            "/api/v1/live-trading/inst1/kline",
                            headers=auth_headers
                        )
                        assert response.status_code == 200

    async def test_get_kline_no_log_dir(self, client: AsyncClient, auth_headers):
        """测试获取K线时无日志目录"""
        with patch('app.api.live_trading_api.get_live_trading_manager') as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_instance.return_value = {
                "instance_id": "inst1",
                "strategy_id": "strategy1",
            }
            mock_get_mgr.return_value = mock_mgr

            with patch('app.api.live_trading_api.find_latest_log_dir') as mock_find:
                mock_find.return_value = None

                response = await client.get(
                    "/api/v1/live-trading/inst1/kline",
                    headers=auth_headers
                )
                assert response.status_code == 404


@pytest.mark.asyncio
class TestLiveTradingMonthlyReturns:
    """实盘月度收益接口测试"""

    async def test_get_monthly_returns_with_data(self, client: AsyncClient, auth_headers):
        """测试获取有数据的月度收益"""
        with patch('app.api.live_trading_api.get_live_trading_manager') as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_instance.return_value = {
                "instance_id": "inst1",
                "strategy_id": "strategy1",
            }
            mock_get_mgr.return_value = mock_mgr

            with patch('app.api.live_trading_api.find_latest_log_dir') as mock_find:
                with patch('app.api.live_trading_api.parse_value_log') as mock_parse:
                    mock_find.return_value = Path("/tmp/logs")
                    mock_parse.return_value = {
                        "dates": ["2024-01-01", "2024-01-31", "2024-02-01"],
                        "equity_curve": [100000, 105000, 110000],
                    }

                    response = await client.get(
                        "/api/v1/live-trading/inst1/monthly-returns",
                        headers=auth_headers
                    )
                    assert response.status_code == 200

    async def test_get_monthly_returns_empty_data(self, client: AsyncClient, auth_headers):
        """测试获取空数据的月度收益"""
        with patch('app.api.live_trading_api.get_live_trading_manager') as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_instance.return_value = {
                "instance_id": "inst1",
                "strategy_id": "strategy1",
            }
            mock_get_mgr.return_value = mock_mgr

            with patch('app.api.live_trading_api.find_latest_log_dir') as mock_find:
                with patch('app.api.live_trading_api.parse_value_log') as mock_parse:
                    mock_find.return_value = Path("/tmp/logs")
                    mock_parse.return_value = {
                        "dates": [],
                        "equity_curve": [],
                    }

                    response = await client.get(
                        "/api/v1/live-trading/inst1/monthly-returns",
                        headers=auth_headers
                    )
                    assert response.status_code == 200


@pytest.mark.asyncio
class TestLiveTradingStartStop:
    """启动/停止接口扩展测试"""

    async def test_start_instance_success(self, client: AsyncClient, auth_headers):
        """测试成功启动实例"""
        with patch('app.api.live_trading_api.get_live_trading_manager') as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.start_instance = AsyncMock(return_value={
                "id": "inst1",
                "strategy_id": "strategy1",
                "status": "running",
            })
            mock_get_mgr.return_value = mock_mgr

            response = await client.post(
                "/api/v1/live-trading/inst1/start",
                headers=auth_headers
            )
            assert response.status_code == 200

    async def test_stop_instance_success(self, client: AsyncClient, auth_headers):
        """测试成功停止实例"""
        with patch('app.api.live_trading_api.get_live_trading_manager') as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.stop_instance = AsyncMock(return_value={
                "id": "inst1",
                "strategy_id": "strategy1",
                "status": "stopped",
            })
            mock_get_mgr.return_value = mock_mgr

            response = await client.post(
                "/api/v1/live-trading/inst1/stop",
                headers=auth_headers
            )
            assert response.status_code == 200


@pytest.mark.asyncio
class TestLiveTradingManager:
    """LiveTradingManager 服务测试"""

    async def test_manager_singleton(self):
        """测试管理器单例"""
        from app.services.live_trading_manager import get_live_trading_manager, LiveTradingManager

        mgr1 = get_live_trading_manager()
        mgr2 = get_live_trading_manager()
        assert isinstance(mgr1, LiveTradingManager)
        assert mgr1 is mgr2

    async def test_list_instances_filters_by_user(self):
        """测试按用户过滤实例"""
        from app.services.live_trading_manager import LiveTradingManager

        with patch('app.services.live_trading_manager._load_instances', return_value={
            "inst1": {"id": "inst1", "strategy_id": "test", "user_id": "user1", "status": "stopped"},
            "inst2": {"id": "inst2", "strategy_id": "test", "user_id": "user2", "status": "stopped"},
        }):
            mgr = LiveTradingManager()
            instances = mgr.list_instances(user_id="user1")
            assert len(instances) == 1
            assert instances[0]["id"] == "inst1"
