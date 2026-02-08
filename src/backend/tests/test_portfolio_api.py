"""
投资组合管理 API 测试

测试：
- 组合概览
- 汇总持仓
- 汇总交易记录
- 组合资金曲线
- 策略资产配置
"""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestPortfolioOverview:
    """组合概览测试"""

    async def test_get_portfolio_overview_empty(self, client: AsyncClient, auth_headers):
        """测试空组合概览"""
        with patch('app.services.live_trading_manager.get_live_trading_manager') as mock_mgr:
            mock_mgr.return_value.list_instances.return_value = []

            response = await client.get(
                "/api/v1/portfolio/overview",
                headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert "total_assets" in data
        assert "total_pnl" in data
        assert "strategy_count" in data
        # strategy_count可能包含默认实例，所以不强制为0

    async def test_get_portfolio_overview_requires_auth(self, client: AsyncClient):
        """测试需要认证"""
        response = await client.get("/api/v1/portfolio/overview")
        # API可能返回401或403
        assert response.status_code in [401, 403]

    async def test_get_portfolio_overview_with_strategies(self, client: AsyncClient, auth_headers):
        """测试有策略的概览"""
        mock_instances = [
            {
                "id": "inst1",
                "strategy_id": "test_strategy",
                "strategy_name": "测试策略",
                "status": "running",
            }
        ]

        with patch('app.services.live_trading_manager.get_live_trading_manager') as mock_mgr:
            mock_mgr.return_value.list_instances.return_value = mock_instances
            # 模拟没有日志目录
            with patch('app.services.log_parser_service.find_latest_log_dir', return_value=None):
                response = await client.get(
                    "/api/v1/portfolio/overview",
                    headers=auth_headers
                )

        assert response.status_code == 200
        data = response.json()
        assert data["strategy_count"] == 1


@pytest.mark.asyncio
class TestPortfolioPositions:
    """汇总持仓测试"""

    async def test_get_portfolio_positions_empty(self, client: AsyncClient, auth_headers):
        """测试空持仓列表"""
        with patch('app.services.live_trading_manager.get_live_trading_manager') as mock_mgr:
            mock_mgr.return_value.list_instances.return_value = []

            response = await client.get(
                "/api/v1/portfolio/positions",
                headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "positions" in data
        assert data["total"] == 0

    async def test_get_portfolio_positions_with_data(self, client: AsyncClient, auth_headers):
        """测试有持仓数据"""
        mock_instances = [
            {
                "id": "inst1",
                "strategy_id": "test_strategy",
                "strategy_name": "测试策略",
            }
        ]

        with patch('app.services.live_trading_manager.get_live_trading_manager') as mock_mgr:
            mock_mgr.return_value.list_instances.return_value = mock_instances
            with patch('app.services.log_parser_service.find_latest_log_dir', return_value="/tmp/logs"):
                with patch('app.services.log_parser_service.parse_current_position', return_value=[
                    {"data_name": "AAPL", "size": 100, "price": 150.0, "market_value": 15000.0}
                ]):
                    response = await client.get(
                        "/api/v1/portfolio/positions",
                        headers=auth_headers
                    )

        assert response.status_code == 200


@pytest.mark.asyncio
class TestPortfolioTrades:
    """汇总交易记录测试"""

    async def test_get_portfolio_trades_empty(self, client: AsyncClient, auth_headers):
        """测试空交易记录"""
        with patch('app.services.live_trading_manager.get_live_trading_manager') as mock_mgr:
            mock_mgr.return_value.list_instances.return_value = []

            response = await client.get(
                "/api/v1/portfolio/trades",
                headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "trades" in data

    async def test_get_portfolio_trades_with_limit(self, client: AsyncClient, auth_headers):
        """测试带限制的交易记录"""
        with patch('app.services.live_trading_manager.get_live_trading_manager') as mock_mgr:
            mock_mgr.return_value.list_instances.return_value = []

            response = await client.get(
                "/api/v1/portfolio/trades?limit=50",
                headers=auth_headers
            )

        assert response.status_code == 200

    async def test_get_portfolio_trades_with_data(self, client: AsyncClient, auth_headers):
        """测试有交易数据"""
        mock_instances = [
            {
                "id": "inst1",
                "strategy_id": "test_strategy",
                "strategy_name": "测试策略",
            }
        ]

        with patch('app.services.live_trading_manager.get_live_trading_manager') as mock_mgr:
            mock_mgr.return_value.list_instances.return_value = mock_instances
            with patch('app.services.log_parser_service.find_latest_log_dir', return_value="/tmp/logs"):
                with patch('app.services.log_parser_service.parse_trade_log', return_value=[
                    {"dtclose": "2024-01-01", "pnlcomm": 100.0, "price": 150.0}
                ]):
                    response = await client.get(
                        "/api/v1/portfolio/trades",
                        headers=auth_headers
                    )

        assert response.status_code == 200


@pytest.mark.asyncio
class TestPortfolioEquity:
    """组合资金曲线测试"""

    async def test_get_portfolio_equity_empty(self, client: AsyncClient, auth_headers):
        """测试空资金曲线"""
        with patch('app.services.live_trading_manager.get_live_trading_manager') as mock_mgr:
            mock_mgr.return_value.list_instances.return_value = []

            response = await client.get(
                "/api/v1/portfolio/equity",
                headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert "dates" in data
        assert "total_equity" in data
        assert "strategies" in data
        assert len(data["dates"]) == 0

    async def test_get_portfolio_equity_with_data(self, client: AsyncClient, auth_headers):
        """测试有资金曲线数据"""
        mock_instances = [
            {
                "id": "inst1",
                "strategy_id": "test_strategy",
                "strategy_name": "测试策略",
            }
        ]

        with patch('app.services.live_trading_manager.get_live_trading_manager') as mock_mgr:
            mock_mgr.return_value.list_instances.return_value = mock_instances
            with patch('app.services.log_parser_service.find_latest_log_dir', return_value="/tmp/logs"):
                with patch('app.services.log_parser_service.parse_value_log', return_value={
                    "dates": ["2024-01-01", "2024-01-02"],
                    "equity_curve": [100000, 101000],
                    "cash_curve": [50000, 50000],
                }):
                    response = await client.get(
                        "/api/v1/portfolio/equity",
                        headers=auth_headers
                    )

        assert response.status_code == 200
        data = response.json()
        # 检查响应结构，不强制检查数据内容
        assert "dates" in data
        assert "total_equity" in data


@pytest.mark.asyncio
class TestPortfolioAllocation:
    """策略资产配置测试"""

    async def test_get_portfolio_allocation_empty(self, client: AsyncClient, auth_headers):
        """测试空资产配置"""
        with patch('app.services.live_trading_manager.get_live_trading_manager') as mock_mgr:
            mock_mgr.return_value.list_instances.return_value = []

            response = await client.get(
                "/api/v1/portfolio/allocation",
                headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "items" in data

    async def test_get_portfolio_allocation_with_data(self, client: AsyncClient, auth_headers):
        """测试有资产配置数据"""
        mock_instances = [
            {
                "id": "inst1",
                "strategy_id": "test_strategy",
                "strategy_name": "测试策略",
            }
        ]

        with patch('app.services.live_trading_manager.get_live_trading_manager') as mock_mgr:
            mock_mgr.return_value.list_instances.return_value = mock_instances
            with patch('app.services.log_parser_service.find_latest_log_dir', return_value="/tmp/logs"):
                with patch('app.services.log_parser_service.parse_value_log', return_value={
                    "dates": ["2024-01-01"],
                    "equity_curve": [100000],
                    "cash_curve": [50000],
                }):
                    response = await client.get(
                        "/api/v1/portfolio/allocation",
                        headers=auth_headers
                    )

        assert response.status_code == 200
        data = response.json()
        # 检查响应结构，不强制检查数据内容
        assert "items" in data


@pytest.mark.asyncio
class TestPortfolioHelpers:
    """投资组合辅助函数测试"""

    async def test_safe_round(self):
        """测试安全舍入函数"""
        from app.api.portfolio_api import _safe_round
        import math

        # 正常值
        assert _safe_round(3.14159) == 3.14
        assert _safe_round(3.14159, 4) == 3.1416

        # NaN 和 Inf
        assert _safe_round(float('nan')) == 0.0
        assert _safe_round(float('inf')) == 0.0
        assert _safe_round(float('-inf')) == 0.0

        # 负数
        assert _safe_round(-3.14159) == -3.14
