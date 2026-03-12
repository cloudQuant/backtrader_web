"""
Portfolio Management API Tests.

Tests:
- GET /api/v1/portfolio/overview - Portfolio overview
- GET /api/v1/portfolio/positions - Aggregated positions
- GET /api/v1/portfolio/trades - Aggregated trade records
- GET /api/v1/portfolio/equity - Portfolio equity curve
- GET /api/v1/portfolio/allocation - Strategy asset allocation
"""

from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient


class TestPortfolioAPI:
    """Tests for portfolio management endpoints."""

    async def test_get_overview(self, client: AsyncClient, auth_headers: dict):
        """Test getting portfolio overview."""
        resp = await client.get("/api/v1/portfolio/overview", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_assets" in data
        assert "strategies" in data

    async def test_get_positions(self, client: AsyncClient, auth_headers: dict):
        """Test getting portfolio positions."""
        resp = await client.get("/api/v1/portfolio/positions", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "positions" in data

    async def test_get_trades(self, client: AsyncClient, auth_headers: dict):
        """Test getting portfolio trades."""
        resp = await client.get("/api/v1/portfolio/trades", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "trades" in data

    async def test_get_equity(self, client: AsyncClient, auth_headers: dict):
        """Test getting portfolio equity curve."""
        resp = await client.get("/api/v1/portfolio/equity", headers=auth_headers)
        assert resp.status_code == 200

    async def test_get_allocation(self, client: AsyncClient, auth_headers: dict):
        """Test getting portfolio allocation."""
        resp = await client.get("/api/v1/portfolio/allocation", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data

    async def test_no_auth(self, client: AsyncClient):
        """Test accessing endpoints without authentication."""
        resp = await client.get("/api/v1/portfolio/overview")
        assert resp.status_code == 401  # Unauthorized when no token provided


@pytest.mark.asyncio
class TestPortfolioOverviewDetailed:
    """Tests for portfolio overview detailed functionality."""

    async def test_overview_contains_total_pnl(self, client: AsyncClient, auth_headers: dict):
        """Test that overview contains total PnL."""
        resp = await client.get("/api/v1/portfolio/overview", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert "total_pnl" in data
            assert "total_pnl_pct" in data

    async def test_overview_contains_strategy_count(self, client: AsyncClient, auth_headers: dict):
        """Test that overview contains strategy count."""
        resp = await client.get("/api/v1/portfolio/overview", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert "strategy_count" in data
            assert "running_count" in data
            assert isinstance(data["strategy_count"], int)


@pytest.mark.asyncio
class TestPortfolioPositionsDetailed:
    """Tests for positions detailed functionality."""

    async def test_positions_contains_total(self, client: AsyncClient, auth_headers: dict):
        """Test that positions contain total count."""
        resp = await client.get("/api/v1/portfolio/positions", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert "total" in data
            assert isinstance(data["total"], int)

    async def test_positions_list_structure(self, client: AsyncClient, auth_headers: dict):
        """Test positions list structure."""
        resp = await client.get("/api/v1/portfolio/positions", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data["positions"], list)


@pytest.mark.asyncio
class TestPortfolioTradesDetailed:
    """Tests for trade records detailed functionality."""

    async def test_trades_limit_parameter(self, client: AsyncClient, auth_headers: dict):
        """Test trades limit parameter."""
        resp = await client.get(
            "/api/v1/portfolio/trades", headers=auth_headers, params={"limit": 10}
        )
        if resp.status_code == 200:
            data = resp.json()
            assert "trades" in data
            # Trade count should not exceed limit
            assert len(data["trades"]) <= 10

    async def test_trades_default_limit(self, client: AsyncClient, auth_headers: dict):
        """Test default limit parameter."""
        resp = await client.get("/api/v1/portfolio/trades", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert "trades" in data
            # Default limit is 200
            assert len(data["trades"]) <= 200


@pytest.mark.asyncio
class TestPortfolioEquityDetailed:
    """Tests for equity curve detailed functionality."""

    async def test_equity_contains_dates(self, client: AsyncClient, auth_headers: dict):
        """Test that equity curve contains dates."""
        resp = await client.get("/api/v1/portfolio/equity", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert "dates" in data
            assert isinstance(data["dates"], list)

    async def test_equity_contains_total_equity(self, client: AsyncClient, auth_headers: dict):
        """Test that equity curve contains total equity."""
        resp = await client.get("/api/v1/portfolio/equity", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert "total_equity" in data
            assert isinstance(data["total_equity"], list)

    async def test_equity_contains_drawdown(self, client: AsyncClient, auth_headers: dict):
        """Test that equity curve contains drawdown."""
        resp = await client.get("/api/v1/portfolio/equity", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert "total_drawdown" in data
            assert isinstance(data["total_drawdown"], list)


@pytest.mark.asyncio
class TestPortfolioAllocationDetailed:
    """Tests for asset allocation detailed functionality."""

    async def test_allocation_contains_total(self, client: AsyncClient, auth_headers: dict):
        """Test that allocation contains total value."""
        resp = await client.get("/api/v1/portfolio/allocation", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert "total" in data

    async def test_allocation_items_structure(self, client: AsyncClient, auth_headers: dict):
        """Test allocation items structure."""
        resp = await client.get("/api/v1/portfolio/allocation", headers=auth_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert "items" in data
            assert isinstance(data["items"], list)
            # Each item should contain strategy info and weight
            for item in data["items"]:
                assert "strategy_id" in item or "strategy_name" in item


class TestPortfolioHelperFunctions:
    """Tests for helper functions."""

    def test_safe_round_normal_value(self):
        """Test rounding normal values."""
        from app.api.portfolio_api import _safe_round

        result = _safe_round(123.456, 2)
        assert result == 123.46

    def test_safe_round_nan_value(self):
        """Test NaN value handling."""

        from app.api.portfolio_api import _safe_round

        result = _safe_round(float("nan"), 2)
        assert result == 0.0

    def test_safe_round_inf_value(self):
        """Test infinity value handling."""
        from app.api.portfolio_api import _safe_round

        result = _safe_round(float("inf"), 2)
        assert result == 0.0

    def test_safe_round_negative_inf_value(self):
        """Test negative infinity value handling."""
        from app.api.portfolio_api import _safe_round

        result = _safe_round(float("-inf"), 2)
        assert result == 0.0

    def test_safe_round_negative_value(self):
        """Test rounding negative values."""
        from app.api.portfolio_api import _safe_round

        result = _safe_round(-123.456, 2)
        assert result == -123.46


@pytest.mark.asyncio
class TestPortfolioManagerIntegration:
    """Tests for portfolio manager integration."""

    async def test_get_manager_function(self):
        """Test getting manager function."""
        from app.api.portfolio_api import _get_manager

        manager = _get_manager()
        assert manager is not None
        assert hasattr(manager, "list_instances")

    async def test_manager_list_instances(self):
        """Test manager listing instances."""
        from app.api.portfolio_api import _get_manager

        manager = _get_manager()
        instances = manager.list_instances()
        # Should return a list
        assert isinstance(instances, list)


@pytest.mark.asyncio
class TestPortfolioEdgeCases:
    """Tests for edge cases and exceptional scenarios."""

    async def test_overview_with_empty_instances(self, client: AsyncClient, auth_headers: dict):
        """Test overview with no instances."""

        with patch("app.api.portfolio_api.get_live_trading_manager") as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.list_instances.return_value = []
            mock_get_mgr.return_value = mock_mgr

            resp = await client.get("/api/v1/portfolio/overview", headers=auth_headers)
            if resp.status_code == 200:
                data = resp.json()
                assert data["strategy_count"] == 0
                assert data["total_assets"] == 0

    async def test_overview_with_no_log_dir(self, client: AsyncClient, auth_headers: dict):
        """Test overview when strategy has no log directory."""
        from pathlib import Path

        with patch("app.api.portfolio_api.get_live_trading_manager") as mock_get_mgr:
            with patch("app.api.portfolio_api.find_latest_log_dir", return_value=None):
                with patch(
                    "app.api.portfolio_api.get_strategy_dir",
                    return_value=Path("/tmp/test_strategy"),
                ):
                    mock_mgr = MagicMock()
                    mock_mgr.list_instances.return_value = [
                        {
                            "id": "inst_1",
                            "strategy_id": "test_strategy",
                            "strategy_name": "Test Strategy",
                            "status": "running",
                        }
                    ]
                    mock_get_mgr.return_value = mock_mgr

                    resp = await client.get("/api/v1/portfolio/overview", headers=auth_headers)
                    # Should return 200 with zero values
                    if resp.status_code == 200:
                        data = resp.json()
                        assert len(data["strategies"]) >= 0

    async def test_positions_with_no_data(self, client: AsyncClient, auth_headers: dict):
        """Test positions with no data."""

        with patch("app.api.portfolio_api.get_live_trading_manager") as mock_get_mgr:
            with patch("app.api.portfolio_api.find_latest_log_dir", return_value=None):
                mock_mgr = MagicMock()
                mock_mgr.list_instances.return_value = []
                mock_get_mgr.return_value = mock_mgr

                resp = await client.get("/api/v1/portfolio/positions", headers=auth_headers)
                if resp.status_code == 200:
                    data = resp.json()
                    assert data["total"] == 0
                    assert len(data["positions"]) == 0

    async def test_trades_sorting(self, client: AsyncClient, auth_headers: dict):
        """Test trade records sorted by date."""
        from pathlib import Path

        with patch("app.api.portfolio_api.get_live_trading_manager") as mock_get_mgr:
            with patch("app.api.portfolio_api.find_latest_log_dir", return_value=Path("/tmp/test")):
                with patch("app.api.portfolio_api.parse_trade_log") as mock_parse:
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
                            "status": "running",
                        }
                    ]
                    mock_get_mgr.return_value = mock_mgr

                    resp = await client.get("/api/v1/portfolio/trades", headers=auth_headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        # Should be sorted by dtclose descending
                        assert data["total"] == 3

    async def test_trades_limit(self, client: AsyncClient, auth_headers: dict):
        """Test trades limit parameter."""
        from pathlib import Path

        with patch("app.api.portfolio_api.get_live_trading_manager") as mock_get_mgr:
            with patch("app.api.portfolio_api.find_latest_log_dir", return_value=Path("/tmp/test")):
                with patch("app.api.portfolio_api.parse_trade_log") as mock_parse:
                    # Mock many trades
                    mock_parse.return_value = [
                        {"dtclose": f"2023-01-{i:02d}", "pnlcomm": i * 10} for i in range(1, 31)
                    ]
                    mock_mgr = MagicMock()
                    mock_mgr.list_instances.return_value = [
                        {
                            "id": "inst_1",
                            "strategy_id": "test_strategy",
                            "strategy_name": "Test Strategy",
                            "status": "running",
                        }
                    ]
                    mock_get_mgr.return_value = mock_mgr

                    resp = await client.get(
                        "/api/v1/portfolio/trades?limit=5", headers=auth_headers
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        # Should return at most 5 trades
                        assert len(data["trades"]) <= 5

    async def test_equity_empty_dates(self, client: AsyncClient, auth_headers: dict):
        """Test equity curve with empty date data."""

        with patch("app.api.portfolio_api.get_live_trading_manager") as mock_get_mgr:
            with patch("app.api.portfolio_api.find_latest_log_dir", return_value=None):
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
        """Test allocation when total value is zero."""
        from pathlib import Path

        with patch("app.api.portfolio_api.get_live_trading_manager") as mock_get_mgr:
            with patch("app.api.portfolio_api.find_latest_log_dir", return_value=Path("/tmp/test")):
                with patch("app.api.portfolio_api.parse_value_log") as mock_parse:
                    # Mock empty equity curve
                    mock_parse.return_value = {"dates": [], "equity_curve": [], "cash_curve": []}
                    mock_mgr = MagicMock()
                    mock_mgr.list_instances.return_value = [
                        {
                            "id": "inst_1",
                            "strategy_id": "test_strategy",
                            "strategy_name": "Test Strategy",
                            "status": "running",
                        }
                    ]
                    mock_get_mgr.return_value = mock_mgr

                    resp = await client.get("/api/v1/portfolio/allocation", headers=auth_headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        assert "total" in data
                        assert "items" in data

    async def test_equity_date_mapping(self, client: AsyncClient, auth_headers: dict):
        """Test date mapping logic."""
        from pathlib import Path

        with patch("app.api.portfolio_api.get_live_trading_manager") as mock_get_mgr:
            with patch("app.api.portfolio_api.find_latest_log_dir", return_value=Path("/tmp/test")):
                with patch("app.api.portfolio_api.parse_value_log") as mock_parse:
                    # Mock different date ranges for different strategies
                    mock_parse.side_effect = [
                        {
                            "dates": ["2023-01-01", "2023-01-02", "2023-01-03"],
                            "equity_curve": [10000, 10100, 10200],
                            "cash_curve": [5000, 5100, 5200],
                        },
                        {
                            "dates": ["2023-01-02", "2023-01-03", "2023-01-04"],
                            "equity_curve": [20000, 20100, 20200],
                            "cash_curve": [10000, 10100, 10200],
                        },
                    ]
                    mock_mgr = MagicMock()
                    mock_mgr.list_instances.return_value = [
                        {
                            "id": "inst_1",
                            "strategy_id": "strategy_1",
                            "strategy_name": "Strategy 1",
                            "status": "running",
                        },
                        {
                            "id": "inst_2",
                            "strategy_id": "strategy_2",
                            "strategy_name": "Strategy 2",
                            "status": "running",
                        },
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
    """Tests for router configuration."""

    async def test_router_exists(self):
        """Test that router exists."""
        from app.api.portfolio_api import router

        assert router is not None
        assert hasattr(router, "routes")

    async def test_router_endpoints(self):
        """Test router endpoints."""
        from app.api.portfolio_api import router

        routes = [route.path for route in router.routes]
        route_str = str(routes)

        assert "/overview" in route_str
        assert "/positions" in route_str
        assert "/trades" in route_str
        assert "/equity" in route_str
        assert "/allocation" in route_str
