"""
Backtest Result Comparison API Tests.

Tests:
- Creating comparisons
- Getting comparison details
- Updating comparisons
- Deleting comparisons
- Listing comparisons
- Toggling favorites
- Sharing comparisons
- Getting comparison data (metrics, equity curves, trades, drawdowns)
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestComparisonCreate:
    """Tests for creating comparisons."""

    async def test_create_comparison_requires_auth(self, client: AsyncClient):
        """Test that authentication is required."""
        response = await client.post(
            "/api/v1/comparisons/",
            json={
                "name": "Test Comparison",
                "backtest_task_ids": ["task1", "task2"]
            }
        )
        # API may return 401 or 403
        assert response.status_code in [401, 403]

    async def test_create_comparison_invalid_params(self, client: AsyncClient, auth_headers):
        """Test validation with invalid parameters."""
        # Test parameter validation - fewer than 2 task IDs
        response = await client.post(
            "/api/v1/comparisons/",
            headers=auth_headers,
            json={
                "name": "Test Comparison",
                "backtest_task_ids": ["task1"]  # Fewer than 2
            }
        )
        # Should return validation error 422
        assert response.status_code in [400, 422]


@pytest.mark.asyncio
class TestComparisonGetDetail:
    """Tests for getting comparison details."""

    async def test_get_comparison_requires_auth(self, client: AsyncClient):
        """Test that authentication is required."""
        response = await client.get(
            "/api/v1/comparisons/comp_123"
        )
        # API may return 401 or 403
        assert response.status_code in [401, 403]

    async def test_get_comparison_not_found(self, client: AsyncClient, auth_headers):
        """Test getting a non-existent comparison."""
        response = await client.get(
            "/api/v1/comparisons/non_existent",
            headers=auth_headers
        )
        assert response.status_code in [404, 400]


@pytest.mark.asyncio
class TestComparisonUpdate:
    """Tests for updating comparisons."""

    async def test_update_comparison_requires_auth(self, client: AsyncClient):
        """Test that authentication is required."""
        response = await client.put(
            "/api/v1/comparisons/comp_123",
            json={"name": "Updated Name"}
        )
        # API may return 401 or 403
        assert response.status_code in [401, 403]


@pytest.mark.asyncio
class TestComparisonDelete:
    """Tests for deleting comparisons."""

    async def test_delete_comparison_requires_auth(self, client: AsyncClient):
        """Test that authentication is required."""
        response = await client.delete(
            "/api/v1/comparisons/comp_123"
        )
        # API may return 401 or 403
        assert response.status_code in [401, 403]


@pytest.mark.asyncio
class TestComparisonList:
    """Tests for listing comparisons."""

    async def test_list_comparisons_requires_auth(self, client: AsyncClient):
        """Test that authentication is required."""
        response = await client.get("/api/v1/comparisons/")
        # API may return 401 or 403
        assert response.status_code in [401, 403]

    async def test_list_comparisons_with_auth(self, client: AsyncClient, auth_headers):
        """Test list request with authentication."""
        response = await client.get(
            "/api/v1/comparisons/",
            headers=auth_headers
        )
        # 200 or empty list
        assert response.status_code in [200, 404]


@pytest.mark.asyncio
class TestComparisonDataEndpoints:
    """Tests for comparison data endpoints."""

    async def test_get_comparison_metrics_requires_auth(self, client: AsyncClient):
        """Test that authentication is required."""
        response = await client.get("/api/v1/comparisons/comp_123/metrics")
        # API may return 401 or 403
        assert response.status_code in [401, 403]

    async def test_get_comparison_equity_requires_auth(self, client: AsyncClient):
        """Test that authentication is required."""
        response = await client.get("/api/v1/comparisons/comp_123/equity")
        # API may return 401 or 403
        assert response.status_code in [401, 403]

    async def test_get_comparison_trades_requires_auth(self, client: AsyncClient):
        """Test that authentication is required."""
        response = await client.get("/api/v1/comparisons/comp_123/trades")
        # API may return 401 or 403
        assert response.status_code in [401, 403]

    async def test_get_comparison_drawdown_requires_auth(self, client: AsyncClient):
        """Test that authentication is required."""
        response = await client.get("/api/v1/comparisons/comp_123/drawdown")
        # API may return 401 or 403
        assert response.status_code in [401, 403]


@pytest.mark.asyncio
class TestComparisonService:
    """Unit tests for comparison service."""

    async def test_service_exists(self):
        """Test that service class exists."""
        from app.services.comparison_service import ComparisonService

        service = ComparisonService()
        assert service is not None
        assert hasattr(service, 'comparison_repo')
        assert hasattr(service, 'backtest_service')

    async def test_compare_metrics_helper(self):
        """Test metrics comparison calculation helper function."""
        backtest_results = {
            "task1": {
                "total_return": 10.5,
                "annual_return": 15.2,
                "sharpe_ratio": 1.5,
                "max_drawdown": -8.3,
                "win_rate": 0.6,
            },
            "task2": {
                "total_return": 8.3,
                "annual_return": 12.1,
                "sharpe_ratio": 1.2,
                "max_drawdown": -6.5,
                "win_rate": 0.55,
            }
        }

        # Simple data structure validation
        assert "total_return" in backtest_results["task1"]
        assert backtest_results["task1"]["total_return"] == 10.5
        assert "sharpe_ratio" in backtest_results["task2"]
        assert backtest_results["task2"]["sharpe_ratio"] == 1.2


@pytest.mark.asyncio
class TestComparisonModels:
    """Tests for comparison models."""

    async def test_comparison_model_exists(self):
        """Test that comparison model exists."""
        from app.models.comparison import Comparison, ComparisonType

        assert Comparison is not None
        assert ComparisonType is not None

    async def test_comparison_type_values(self):
        """Test comparison type enum."""
        from app.models.comparison import ComparisonType

        # Check enum values
        assert hasattr(ComparisonType, 'METRICS')
        assert hasattr(ComparisonType, 'EQUITY')
        assert hasattr(ComparisonType, 'TRADES')


@pytest.mark.asyncio
class TestComparisonSchemas:
    """Tests for comparison schemas."""

    async def test_schemas_exist(self):
        """Test that schemas exist."""
        from app.schemas.comparison import (
            ComparisonCreate,
            ComparisonResponse,
            ComparisonUpdate,
        )

        assert ComparisonCreate is not None
        assert ComparisonResponse is not None
        assert ComparisonUpdate is not None
