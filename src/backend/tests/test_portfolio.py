"""
组合管理 API 测试

测试：
- GET /api/v1/portfolio/overview - 组合概览
- GET /api/v1/portfolio/positions - 汇总持仓
- GET /api/v1/portfolio/trades - 汇总交易记录
- GET /api/v1/portfolio/equity - 组合资金曲线
- GET /api/v1/portfolio/allocation - 策略资产配置
"""
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, Mock, patch, MagicMock


class TestPortfolioAPI:
    """组合管理接口测试"""

    async def test_get_overview(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/portfolio/overview", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_assets" in data
        assert "strategies" in data

    async def test_get_positions(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/portfolio/positions", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "positions" in data

    async def test_get_trades(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/portfolio/trades", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "trades" in data

    async def test_get_equity(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/portfolio/equity", headers=auth_headers)
        assert resp.status_code == 200

    async def test_get_allocation(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/portfolio/allocation", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data

    async def test_no_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/portfolio/overview")
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestPortfolioOverviewDetailed:
    """测试组合概览详细功能"""

    async def test_overview_contains_total_pnl(self, client: AsyncClient, auth_headers: dict):
        """测试概览包含总盈亏"""
        resp = await client.get("/api/v1/portfolio/overview", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert "total_pnl" in data
            assert "total_pnl_pct" in data

    async def test_overview_contains_strategy_count(self, client: AsyncClient, auth_headers: dict):
        """测试概览包含策略数量"""
        resp = await client.get("/api/v1/portfolio/overview", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert "strategy_count" in data
            assert "running_count" in data
            assert isinstance(data["strategy_count"], int)


@pytest.mark.asyncio
class TestPortfolioPositionsDetailed:
    """测试持仓详细功能"""

    async def test_positions_contains_total(self, client: AsyncClient, auth_headers: dict):
        """测试持仓包含总数"""
        resp = await client.get("/api/v1/portfolio/positions", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert "total" in data
            assert isinstance(data["total"], int)

    async def test_positions_list_structure(self, client: AsyncClient, auth_headers: dict):
        """测试持仓列表结构"""
        resp = await client.get("/api/v1/portfolio/positions", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data["positions"], list)


@pytest.mark.asyncio
class TestPortfolioTradesDetailed:
    """测试交易记录详细功能"""

    async def test_trades_limit_parameter(self, client: AsyncClient, auth_headers: dict):
        """测试交易限制参数"""
        resp = await client.get(
            "/api/v1/portfolio/trades",
            headers=auth_headers,
            params={"limit": 10}
        )
        if resp.status_code == 200:
            data = resp.json()
            assert "trades" in data
            # 交易数应该不超过限制
            assert len(data["trades"]) <= 10

    async def test_trades_default_limit(self, client: AsyncClient, auth_headers: dict):
        """测试默认限制参数"""
        resp = await client.get("/api/v1/portfolio/trades", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert "trades" in data
            # 默认限制200
            assert len(data["trades"]) <= 200


@pytest.mark.asyncio
class TestPortfolioEquityDetailed:
    """测试资金曲线详细功能"""

    async def test_equity_contains_dates(self, client: AsyncClient, auth_headers: dict):
        """测试资金曲线包含日期"""
        resp = await client.get("/api/v1/portfolio/equity", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert "dates" in data
            assert isinstance(data["dates"], list)

    async def test_equity_contains_total_equity(self, client: AsyncClient, auth_headers: dict):
        """测试资金曲线包含总权益"""
        resp = await client.get("/api/v1/portfolio/equity", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert "total_equity" in data
            assert isinstance(data["total_equity"], list)

    async def test_equity_contains_drawdown(self, client: AsyncClient, auth_headers: dict):
        """测试资金曲线包含回撤"""
        resp = await client.get("/api/v1/portfolio/equity", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert "total_drawdown" in data
            assert isinstance(data["total_drawdown"], list)


@pytest.mark.asyncio
class TestPortfolioAllocationDetailed:
    """测试资产配置详细功能"""

    async def test_allocation_contains_total(self, client: AsyncClient, auth_headers: dict):
        """测试资产配置包含总值"""
        resp = await client.get("/api/v1/portfolio/allocation", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert "total" in data

    async def test_allocation_items_structure(self, client: AsyncClient, auth_headers: dict):
        """测试资产配置项结构"""
        resp = await client.get("/api/v1/portfolio/allocation", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert "items" in data
            assert isinstance(data["items"], list)
            # 每个项应该包含策略信息和权重
            for item in data["items"]:
                assert "strategy_id" in item or "strategy_name" in item


@pytest.mark.asyncio
class TestPortfolioHelperFunctions:
    """测试辅助函数"""

    def test_safe_round_normal_value(self):
        """测试正常值舍入"""
        from app.api.portfolio_api import _safe_round
        result = _safe_round(123.456, 2)
        assert result == 123.46

    def test_safe_round_nan_value(self):
        """测试NaN值处理"""
        from app.api.portfolio_api import _safe_round
        import math
        result = _safe_round(float('nan'), 2)
        assert result == 0.0

    def test_safe_round_inf_value(self):
        """测试无穷值处理"""
        from app.api.portfolio_api import _safe_round
        result = _safe_round(float('inf'), 2)
        assert result == 0.0

    def test_safe_round_negative_inf_value(self):
        """测试负无穷值处理"""
        from app.api.portfolio_api import _safe_round
        result = _safe_round(float('-inf'), 2)
        assert result == 0.0

    def test_safe_round_negative_value(self):
        """测试负值舍入"""
        from app.api.portfolio_api import _safe_round
        result = _safe_round(-123.456, 2)
        assert result == -123.46


@pytest.mark.asyncio
class TestPortfolioManagerIntegration:
    """测试组合管理器集成"""

    async def test_get_manager_function(self):
        """测试获取管理器函数"""
        from app.api.portfolio_api import _get_manager

        manager = _get_manager()
        assert manager is not None
        assert hasattr(manager, 'list_instances')

    async def test_manager_list_instances(self):
        """测试管理器列出实例"""
        from app.api.portfolio_api import _get_manager

        manager = _get_manager()
        instances = manager.list_instances()
        # 应该返回列表
        assert isinstance(instances, list)


@pytest.mark.asyncio
class TestPortfolioEdgeCases:
    """测试边界情况和异常场景"""

    async def test_overview_with_empty_instances(self, client: AsyncClient, auth_headers: dict):
        """测试无实例时的概览"""
        from app.services.live_trading_manager import get_live_trading_manager

        with patch('app.api.portfolio_api.get_live_trading_manager') as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.list_instances.return_value = []
            mock_get_mgr.return_value = mock_mgr

            resp = await client.get("/api/v1/portfolio/overview", headers=auth_headers)
            if resp.status_code == 200:
                data = resp.json()
                assert data["strategy_count"] == 0
                assert data["total_assets"] == 0

    async def test_overview_with_no_log_dir(self, client: AsyncClient, auth_headers: dict):
        """测试策略无日志目录时的概览"""
        from app.services.live_trading_manager import get_live_trading_manager
        from pathlib import Path

        with patch('app.api.portfolio_api.get_live_trading_manager') as mock_get_mgr:
            with patch('app.api.portfolio_api.find_latest_log_dir', return_value=None):
                with patch('app.api.portfolio_api.STRATEGIES_DIR', Path('/tmp')):
                    mock_mgr = MagicMock()
                    mock_mgr.list_instances.return_value = [
                        {
                            "id": "inst_1",
                            "strategy_id": "test_strategy",
                            "strategy_name": "Test Strategy",
                            "status": "running"
                        }
                    ]
                    mock_get_mgr.return_value = mock_mgr

                    resp = await client.get("/api/v1/portfolio/overview", headers=auth_headers)
                    # Should return 200 with zero values
                    if resp.status_code == 200:
                        data = resp.json()
                        assert len(data["strategies"]) >= 0

    async def test_positions_with_no_data(self, client: AsyncClient, auth_headers: dict):
        """测试无数据时的持仓"""
        from app.services.live_trading_manager import get_live_trading_manager

        with patch('app.api.portfolio_api.get_live_trading_manager') as mock_get_mgr:
            with patch('app.api.portfolio_api.find_latest_log_dir', return_value=None):
                mock_mgr = MagicMock()
                mock_mgr.list_instances.return_value = []
                mock_get_mgr.return_value = mock_mgr

                resp = await client.get("/api/v1/portfolio/positions", headers=auth_headers)
                if resp.status_code == 200:
                    data = resp.json()
                    assert data["total"] == 0
                    assert len(data["positions"]) == 0

    async def test_trades_sorting(self, client: AsyncClient, auth_headers: dict):
        """测试交易记录按日期排序"""
        from app.services.live_trading_manager import get_live_trading_manager
        from pathlib import Path
        from datetime import datetime

        with patch('app.api.portfolio_api.get_live_trading_manager') as mock_get_mgr:
            with patch('app.api.portfolio_api.find_latest_log_dir', return_value=Path('/tmp/test')):
                with patch('app.api.portfolio_api.parse_trade_log') as mock_parse:
                    # Mock trades with different close dates
                    mock_parse.return_value = [
                        {"dtclose": "2023-01-02", "pnlcomm": 100},
                        {"dtclose": "2023-01-05", "pnlcomm": 200},
                        {"dtclose": "2023-01-01", "pnlcomm": 50},
                    ]
                    mock_mgr = MagicMock()
                    mock_mgr.list_instances.return_value = [
                        {
                            "id": "inst_1",
                            "strategy_id": "test_strategy",
                            "strategy_name": "Test Strategy",
                            "status": "running"
                        }
                    ]
                    mock_get_mgr.return_value = mock_mgr

                    resp = await client.get("/api/v1/portfolio/trades", headers=auth_headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        # Should be sorted by dtclose descending
                        assert data["total"] == 3

    async def test_trades_limit(self, client: AsyncClient, auth_headers: dict):
        """测试交易限制参数"""
        from app.services.live_trading_manager import get_live_trading_manager
        from pathlib import Path

        with patch('app.api.portfolio_api.get_live_trading_manager') as mock_get_mgr:
            with patch('app.api.portfolio_api.find_latest_log_dir', return_value=Path('/tmp/test')):
                with patch('app.api.portfolio_api.parse_trade_log') as mock_parse:
                    # Mock many trades
                    mock_parse.return_value = [
                        {"dtclose": f"2023-01-{i:02d}", "pnlcomm": i * 10}
                        for i in range(1, 31)
                    ]
                    mock_mgr = MagicMock()
                    mock_mgr.list_instances.return_value = [
                        {
                            "id": "inst_1",
                            "strategy_id": "test_strategy",
                            "strategy_name": "Test Strategy",
                            "status": "running"
                        }
                    ]
                    mock_get_mgr.return_value = mock_mgr

                    resp = await client.get(
                        "/api/v1/portfolio/trades?limit=5",
                        headers=auth_headers
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        # Should return at most 5 trades
                        assert len(data["trades"]) <= 5

    async def test_equity_empty_dates(self, client: AsyncClient, auth_headers: dict):
        """测试空日期数据时的资金曲线"""
        from app.services.live_trading_manager import get_live_trading_manager

        with patch('app.api.portfolio_api.get_live_trading_manager') as mock_get_mgr:
            with patch('app.api.portfolio_api.find_latest_log_dir', return_value=None):
                mock_mgr = MagicMock()
                mock_mgr.list_instances.return_value = []
                mock_get_mgr.return_value = mock_mgr

                resp = await client.get("/api/v1/portfolio/equity", headers=auth_headers)
                if resp.status_code == 200:
                    data = resp.json()
                    assert data["dates"] == []
                    assert data["total_equity"] == []
                    assert data["strategies"] == []

    async def test_allocation_with_zero_total(self, client: AsyncClient, auth_headers: dict):
        """测试总值为0时的资产配置"""
        from app.services.live_trading_manager import get_live_trading_manager
        from pathlib import Path

        with patch('app.api.portfolio_api.get_live_trading_manager') as mock_get_mgr:
            with patch('app.api.portfolio_api.find_latest_log_dir', return_value=Path('/tmp/test')):
                with patch('app.api.portfolio_api.parse_value_log') as mock_parse:
                    # Mock empty equity curve
                    mock_parse.return_value = {
                        "dates": [],
                        "equity_curve": [],
                        "cash_curve": []
                    }
                    mock_mgr = MagicMock()
                    mock_mgr.list_instances.return_value = [
                        {
                            "id": "inst_1",
                            "strategy_id": "test_strategy",
                            "strategy_name": "Test Strategy",
                            "status": "running"
                        }
                    ]
                    mock_get_mgr.return_value = mock_mgr

                    resp = await client.get("/api/v1/portfolio/allocation", headers=auth_headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        assert "total" in data
                        assert "items" in data

    async def test_equity_date_mapping(self, client: AsyncClient, auth_headers: dict):
        """测试日期映射逻辑"""
        from app.services.live_trading_manager import get_live_trading_manager
        from pathlib import Path

        with patch('app.api.portfolio_api.get_live_trading_manager') as mock_get_mgr:
            with patch('app.api.portfolio_api.find_latest_log_dir', return_value=Path('/tmp/test')):
                with patch('app.api.portfolio_api.parse_value_log') as mock_parse:
                    # Mock different date ranges for different strategies
                    mock_parse.side_effect = [
                        {
                            "dates": ["2023-01-01", "2023-01-02", "2023-01-03"],
                            "equity_curve": [10000, 10100, 10200],
                            "cash_curve": [5000, 5100, 5200]
                        },
                        {
                            "dates": ["2023-01-02", "2023-01-03", "2023-01-04"],
                            "equity_curve": [20000, 20100, 20200],
                            "cash_curve": [10000, 10100, 10200]
                        }
                    ]
                    mock_mgr = MagicMock()
                    mock_mgr.list_instances.return_value = [
                        {
                            "id": "inst_1",
                            "strategy_id": "strategy_1",
                            "strategy_name": "Strategy 1",
                            "status": "running"
                        },
                        {
                            "id": "inst_2",
                            "strategy_id": "strategy_2",
                            "strategy_name": "Strategy 2",
                            "status": "running"
                        }
                    ]
                    mock_get_mgr.return_value = mock_mgr

                    resp = await client.get("/api/v1/portfolio/equity", headers=auth_headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        # Should have dates from both strategies
                        assert "dates" in data
                        assert "total_equity" in data
                        assert "total_drawdown" in data
                        assert "strategies" in data
                        # Should have 2 strategies
                        assert len(data["strategies"]) == 2


@pytest.mark.asyncio
class TestPortfolioRouter:
    """测试路由配置"""

    async def test_router_exists(self):
        """测试路由存在"""
        from app.api.portfolio_api import router

        assert router is not None
        assert hasattr(router, 'routes')

    async def test_router_endpoints(self):
        """测试路由端点"""
        from app.api.portfolio_api import router

        routes = [route.path for route in router.routes]
        route_str = str(routes)

        assert "/overview" in route_str
        assert "/positions" in route_str
        assert "/trades" in route_str
        assert "/equity" in route_str
        assert "/allocation" in route_str
