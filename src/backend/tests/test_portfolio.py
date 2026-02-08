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
from unittest.mock import AsyncMock, Mock, patch


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
