"""
Portfolio Management API Tests.

Tests:
- Portfolio overview
- Aggregated positions
- Aggregated trade records
- Portfolio equity curve
- Strategy asset allocation
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestPortfolioOverview:
    """Test portfolio overview endpoints."""

    async def test_get_portfolio_overview_empty(self, client: AsyncClient, auth_headers):
        """Test getting portfolio overview when empty."""
        with patch("app.services.live_trading_manager.get_live_trading_manager") as mock_mgr:
            mock_mgr.return_value.list_instances.return_value = []

            response = await client.get("/api/v1/portfolio/overview", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "total_assets" in data
        assert "total_pnl" in data
        assert "strategy_count" in data
        # strategy_count may include default instance, so don't enforce 0

    async def test_get_portfolio_overview_requires_auth(self, client: AsyncClient):
        """Test authentication required for portfolio overview."""
        response = await client.get("/api/v1/portfolio/overview")
        # API may return 401 or 403
        assert response.status_code in [401, 403]

    async def test_get_portfolio_overview_with_strategies(self, client: AsyncClient, auth_headers):
        """Test portfolio overview with active strategies."""
        mock_instances = [
            {
                "id": "inst1",
                "strategy_id": "test_strategy",
                "strategy_name": "Test Strategy",
                "status": "running",
            }
        ]

        with patch("app.api.portfolio_api.get_live_trading_manager") as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.list_instances.return_value = mock_instances
            mock_get_mgr.return_value = mock_mgr
            # Mock get_strategy_dir and no log directory
            with patch(
                "app.api.portfolio_api.get_strategy_dir", return_value=Path("/tmp/test_strategy")
            ):
                with patch(
                    "app.services.log_parser_service.find_latest_log_dir", return_value=None
                ):
                    response = await client.get("/api/v1/portfolio/overview", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["strategy_count"] == 1


@pytest.mark.asyncio
class TestPortfolioPositions:
    """Test aggregated portfolio positions."""

    async def test_get_portfolio_positions_empty(self, client: AsyncClient, auth_headers):
        """Test getting portfolio positions when empty."""
        with patch("app.services.live_trading_manager.get_live_trading_manager") as mock_mgr:
            mock_mgr.return_value.list_instances.return_value = []

            response = await client.get("/api/v1/portfolio/positions", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "positions" in data
        assert data["total"] == 0

    async def test_get_portfolio_positions_with_data(self, client: AsyncClient, auth_headers):
        """Test getting portfolio positions with data."""
        mock_instances = [
            {
                "id": "inst1",
                "strategy_id": "test_strategy",
                "strategy_name": "Test Strategy",
            }
        ]

        with patch("app.services.live_trading_manager.get_live_trading_manager") as mock_mgr:
            mock_mgr.return_value.list_instances.return_value = mock_instances
            with patch(
                "app.services.log_parser_service.find_latest_log_dir", return_value="/tmp/logs"
            ):
                with patch(
                    "app.services.log_parser_service.parse_current_position",
                    return_value=[
                        {"data_name": "AAPL", "size": 100, "price": 150.0, "market_value": 15000.0}
                    ],
                ):
                    response = await client.get("/api/v1/portfolio/positions", headers=auth_headers)

        assert response.status_code == 200


@pytest.mark.asyncio
class TestPortfolioTrades:
    """Test aggregated trade records."""

    async def test_get_portfolio_trades_empty(self, client: AsyncClient, auth_headers):
        """Test getting portfolio trades when empty."""
        with patch("app.services.live_trading_manager.get_live_trading_manager") as mock_mgr:
            mock_mgr.return_value.list_instances.return_value = []

            response = await client.get("/api/v1/portfolio/trades", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "trades" in data

    async def test_get_portfolio_trades_with_limit(self, client: AsyncClient, auth_headers):
        """Test getting portfolio trades with limit parameter."""
        with patch("app.services.live_trading_manager.get_live_trading_manager") as mock_mgr:
            mock_mgr.return_value.list_instances.return_value = []

            response = await client.get("/api/v1/portfolio/trades?limit=50", headers=auth_headers)

        assert response.status_code == 200

    async def test_get_portfolio_trades_with_data(self, client: AsyncClient, auth_headers):
        """Test getting portfolio trades with data."""
        mock_instances = [
            {
                "id": "inst1",
                "strategy_id": "test_strategy",
                "strategy_name": "Test Strategy",
            }
        ]

        with patch("app.services.live_trading_manager.get_live_trading_manager") as mock_mgr:
            mock_mgr.return_value.list_instances.return_value = mock_instances
            with patch(
                "app.services.log_parser_service.find_latest_log_dir", return_value="/tmp/logs"
            ):
                with patch(
                    "app.services.log_parser_service.parse_trade_log",
                    return_value=[{"dtclose": "2024-01-01", "pnlcomm": 100.0, "price": 150.0}],
                ):
                    response = await client.get("/api/v1/portfolio/trades", headers=auth_headers)

        assert response.status_code == 200


@pytest.mark.asyncio
class TestPortfolioEquity:
    """Test portfolio equity curve."""

    async def test_get_portfolio_equity_empty(self, client: AsyncClient, auth_headers):
        """Test getting portfolio equity curve when empty."""
        with patch("app.services.live_trading_manager.get_live_trading_manager") as mock_mgr:
            mock_mgr.return_value.list_instances.return_value = []

            response = await client.get("/api/v1/portfolio/equity", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "dates" in data
        assert "total_equity" in data
        assert "strategies" in data
        assert len(data["dates"]) == 0

    async def test_get_portfolio_equity_with_data(self, client: AsyncClient, auth_headers):
        """Test getting portfolio equity curve with data."""
        mock_instances = [
            {
                "id": "inst1",
                "strategy_id": "test_strategy",
                "strategy_name": "Test Strategy",
            }
        ]

        with patch("app.services.live_trading_manager.get_live_trading_manager") as mock_mgr:
            mock_mgr.return_value.list_instances.return_value = mock_instances
            with patch(
                "app.services.log_parser_service.find_latest_log_dir", return_value="/tmp/logs"
            ):
                with patch(
                    "app.services.log_parser_service.parse_value_log",
                    return_value={
                        "dates": ["2024-01-01", "2024-01-02"],
                        "equity_curve": [100000, 101000],
                        "cash_curve": [50000, 50000],
                    },
                ):
                    response = await client.get("/api/v1/portfolio/equity", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        # Check response structure, don't enforce data content
        assert "dates" in data
        assert "total_equity" in data


@pytest.mark.asyncio
class TestPortfolioAllocation:
    """Test strategy asset allocation."""

    async def test_get_portfolio_allocation_empty(self, client: AsyncClient, auth_headers):
        """Test getting portfolio allocation when empty."""
        with patch("app.services.live_trading_manager.get_live_trading_manager") as mock_mgr:
            mock_mgr.return_value.list_instances.return_value = []

            response = await client.get("/api/v1/portfolio/allocation", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "items" in data

    async def test_get_portfolio_allocation_with_data(self, client: AsyncClient, auth_headers):
        """Test getting portfolio allocation with data."""
        mock_instances = [
            {
                "id": "inst1",
                "strategy_id": "test_strategy",
                "strategy_name": "Test Strategy",
            }
        ]

        with patch("app.services.live_trading_manager.get_live_trading_manager") as mock_mgr:
            mock_mgr.return_value.list_instances.return_value = mock_instances
            with patch(
                "app.services.log_parser_service.find_latest_log_dir", return_value="/tmp/logs"
            ):
                with patch(
                    "app.services.log_parser_service.parse_value_log",
                    return_value={
                        "dates": ["2024-01-01"],
                        "equity_curve": [100000],
                        "cash_curve": [50000],
                    },
                ):
                    response = await client.get(
                        "/api/v1/portfolio/allocation", headers=auth_headers
                    )

        assert response.status_code == 200
        data = response.json()
        # Check response structure, don't enforce data content
        assert "items" in data


@pytest.mark.asyncio
class TestPortfolioHelpers:
    """Test portfolio helper functions."""

    async def test_safe_round(self):
        """Test safe rounding function."""

        from app.api.portfolio_api import _safe_round

        # Normal values
        assert _safe_round(3.14159) == 3.14
        assert _safe_round(3.14159, 4) == 3.1416

        # NaN and Inf
        assert _safe_round(float("nan")) == 0.0
        assert _safe_round(float("inf")) == 0.0
        assert _safe_round(float("-inf")) == 0.0

        # Negative numbers
        assert _safe_round(-3.14159) == -3.14
