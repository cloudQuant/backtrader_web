"""
Parameter Optimization API Complete Tests.

Tests:
- Getting strategy parameters
- Submitting optimization tasks
- Querying optimization progress
- Getting optimization results
- Canceling optimization tasks
"""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import HTTPException


@pytest.fixture
def mock_current_user():
    """Mock current user."""
    user = MagicMock()
    user.sub = "test_user_123"
    return user


@pytest.fixture
def mock_strategy_template():
    """Mock strategy template."""
    tpl = MagicMock()
    tpl.id = "test_strategy"
    tpl.name = "Test Strategy"
    tpl.params = {
        "fast_period": MagicMock(type="int", default=10, description="Fast period"),
        "slow_period": MagicMock(type="int", default=20, description="Slow period"),
    }
    return tpl


# ==================== Get Strategy Parameters Tests ====================

@pytest.mark.asyncio
class TestOptimizationStrategyParams:
    """Tests for getting strategy parameters."""

    async def test_get_strategy_params_success(self, mock_current_user, mock_strategy_template):
        """Test successful strategy parameter retrieval."""
        from app.api.optimization_api import get_strategy_params

        with patch('app.api.optimization_api.get_template_by_id', return_value=mock_strategy_template):
            result = await get_strategy_params(
                strategy_id="test_strategy",
                current_user=mock_current_user
            )

            assert result["strategy_id"] == "test_strategy"
            assert result["strategy_name"] == "Test Strategy"
            assert len(result["params"]) == 2
            assert result["params"][0]["name"] == "fast_period"
            assert result["params"][0]["type"] == "int"

    async def test_get_strategy_params_not_found(self, mock_current_user):
        """Test when strategy does not exist."""
        from app.api.optimization_api import get_strategy_params

        with patch('app.api.optimization_api.get_template_by_id', return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await get_strategy_params(
                    strategy_id="nonexistent",
                    current_user=mock_current_user
                )

            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail

    async def test_get_strategy_params_empty_params(self, mock_current_user):
        """Test strategy with no parameters."""
        from app.api.optimization_api import get_strategy_params

        tpl = MagicMock()
        tpl.id = "no_params_strategy"
        tpl.name = "No Params Strategy"
        tpl.params = {}

        with patch('app.api.optimization_api.get_template_by_id', return_value=tpl):
            result = await get_strategy_params(
                strategy_id="no_params_strategy",
                current_user=mock_current_user
            )

            assert result["params"] == []


# ==================== Submit Optimization Task Tests ====================

@pytest.mark.asyncio
class TestOptimizationSubmit:
    """Tests for submitting optimization tasks."""

    async def test_submit_optimization_success(self, mock_current_user, mock_strategy_template):
        """Test successful optimization task submission."""
        from app.api.optimization_api import submit_optimization_task, OptimizationSubmitRequest, ParamRangeSpec

        request = OptimizationSubmitRequest(
            strategy_id="test_strategy",
            param_ranges={
                "fast": ParamRangeSpec(start=5, end=15, step=5, type="int"),
            },
            n_workers=4,
        )

        with patch('app.api.optimization_api.get_template_by_id', return_value=mock_strategy_template):
            with patch('app.services.param_optimization_service.generate_param_grid', return_value=[{"fast": 5}, {"fast": 10}, {"fast": 15}]):
                with patch('app.api.optimization_api.submit_optimization', return_value="task_123"):
                    result = await submit_optimization_task(
                        request=request,
                        current_user=mock_current_user
                    )

                    assert result.task_id == "task_123"
                    assert result.total_combinations == 3
                    assert "submitted" in result.message.lower()

    async def test_submit_optimization_strategy_not_found(self, mock_current_user):
        """Test when strategy does not exist."""
        from app.api.optimization_api import submit_optimization_task, OptimizationSubmitRequest, ParamRangeSpec

        request = OptimizationSubmitRequest(
            strategy_id="nonexistent",
            param_ranges={
                "fast": ParamRangeSpec(start=5, end=15, step=5, type="int"),
            },
        )

        with patch('app.api.optimization_api.get_template_by_id', return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await submit_optimization_task(
                    request=request,
                    current_user=mock_current_user
                )

            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail

    async def test_submit_optimization_empty_grid(self, mock_current_user, mock_strategy_template):
        """Test when parameter grid is empty."""
        from app.api.optimization_api import submit_optimization_task, OptimizationSubmitRequest, ParamRangeSpec

        request = OptimizationSubmitRequest(
            strategy_id="test_strategy",
            param_ranges={
                "fast": ParamRangeSpec(start=5, end=15, step=5, type="int"),
            },
        )

        with patch('app.api.optimization_api.get_template_by_id', return_value=mock_strategy_template):
            with patch('app.services.strategy_service.get_template_by_id', return_value=mock_strategy_template):
                with patch('app.services.param_optimization_service.generate_param_grid', return_value=[]):
                    with pytest.raises(HTTPException) as exc_info:
                        await submit_optimization_task(
                            request=request,
                            current_user=mock_current_user
                        )

                    assert exc_info.value.status_code == 400
                    assert "empty" in exc_info.value.detail.lower() or "parameter" in exc_info.value.detail.lower()

    async def test_submit_optimization_value_error(self, mock_current_user, mock_strategy_template):
        """Test when service returns ValueError."""
        from app.api.optimization_api import submit_optimization_task, OptimizationSubmitRequest, ParamRangeSpec

        request = OptimizationSubmitRequest(
            strategy_id="test_strategy",
            param_ranges={
                "fast": ParamRangeSpec(start=5, end=15, step=5, type="int"),
            },
        )

        with patch('app.api.optimization_api.get_template_by_id', return_value=mock_strategy_template):
            with patch('app.services.param_optimization_service.generate_param_grid', return_value=[{"fast": 5}]):
                with patch('app.api.optimization_api.submit_optimization', side_effect=ValueError("Invalid parameters")):
                    with pytest.raises(HTTPException) as exc_info:
                        await submit_optimization_task(
                            request=request,
                            current_user=mock_current_user
                        )

                    assert exc_info.value.status_code == 400
                    assert "Invalid parameters" in exc_info.value.detail

    async def test_submit_optimization_default_workers(self, mock_current_user, mock_strategy_template):
        """Test default worker count."""
        from app.api.optimization_api import submit_optimization_task, OptimizationSubmitRequest, ParamRangeSpec

        request = OptimizationSubmitRequest(
            strategy_id="test_strategy",
            param_ranges={
                "fast": ParamRangeSpec(start=5, end=15, step=5, type="int"),
            },
            # n_workers defaults to 4
        )

        with patch('app.api.optimization_api.get_template_by_id', return_value=mock_strategy_template):
            with patch('app.services.param_optimization_service.generate_param_grid', return_value=[{"fast": 5}]):
                with patch('app.api.optimization_api.submit_optimization', return_value="task_123") as mock_submit:
                    await submit_optimization_task(
                        request=request,
                        current_user=mock_current_user
                    )

                    # Verify n_workers=4 was passed
                    call_kwargs = mock_submit.call_args.kwargs
                    assert call_kwargs['n_workers'] == 4


# ==================== Query Optimization Progress Tests ====================

@pytest.mark.asyncio
class TestOptimizationProgress:
    """Tests for querying optimization progress."""

    async def test_get_progress_success(self, mock_current_user):
        """Test successful progress retrieval."""
        from app.api.optimization_api import get_progress

        mock_progress = {
            "task_id": "task_123",
            "status": "running",
            "completed": 5,
            "total": 10,
            "progress": 50.0,
        }

        with patch('app.api.optimization_api.get_optimization_progress', return_value=mock_progress):
            result = await get_progress(
                task_id="task_123",
                current_user=mock_current_user
            )

            assert result["task_id"] == "task_123"
            assert result["status"] == "running"
            assert result["progress"] == 50.0

    async def test_get_progress_not_found(self, mock_current_user):
        """Test when task does not exist."""
        from app.api.optimization_api import get_progress

        with patch('app.api.optimization_api.get_optimization_progress', return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await get_progress(
                    task_id="nonexistent",
                    current_user=mock_current_user
                )

            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail


# ==================== Get Optimization Results Tests ====================

@pytest.mark.asyncio
class TestOptimizationResults:
    """Tests for getting optimization results."""

    async def test_get_results_success(self, mock_current_user):
        """Test successful results retrieval."""
        from app.api.optimization_api import get_results

        mock_results = {
            "task_id": "task_123",
            "status": "completed",
            "best_params": {"fast": 10, "slow": 20},
            "best_return": 0.15,
            "all_results": [],
        }

        with patch('app.api.optimization_api.get_optimization_results', return_value=mock_results):
            result = await get_results(
                task_id="task_123",
                current_user=mock_current_user
            )

            assert result["task_id"] == "task_123"
            assert result["status"] == "completed"
            assert result["best_return"] == 0.15

    async def test_get_results_not_found(self, mock_current_user):
        """Test when task does not exist."""
        from app.api.optimization_api import get_results

        with patch('app.services.param_optimization_service.get_optimization_results', return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await get_results(
                    task_id="nonexistent",
                    current_user=mock_current_user
                )

            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail


# ==================== Cancel Optimization Task Tests ====================

@pytest.mark.asyncio
class TestOptimizationCancel:
    """Tests for canceling optimization tasks."""

    async def test_cancel_task_success(self, mock_current_user):
        """Test successful task cancellation."""
        from app.api.optimization_api import cancel_task

        with patch('app.api.optimization_api.cancel_optimization', return_value=True):
            result = await cancel_task(
                task_id="task_123",
                current_user=mock_current_user
            )

            assert result["message"] == "Cancellation requested"
            assert result["task_id"] == "task_123"

    async def test_cancel_task_not_found(self, mock_current_user):
        """Test when task does not exist."""
        from app.api.optimization_api import cancel_task

        with patch('app.services.param_optimization_service.cancel_optimization', return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await cancel_task(
                    task_id="nonexistent",
                    current_user=mock_current_user
                )

            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail


# ==================== Schema Tests ====================

@pytest.mark.asyncio
class TestOptimizationSchemas:
    """Tests for optimization schemas."""

    async def test_param_range_spec_schema(self):
        """Test parameter range schema."""
        from app.api.optimization_api import ParamRangeSpec

        spec = ParamRangeSpec(
            start=5,
            end=15,
            step=5,
            type="int"
        )
        assert spec.start == 5
        assert spec.end == 15
        assert spec.step == 5
        assert spec.type == "int"

    async def test_optimization_submit_request_schema(self):
        """Test optimization submit request schema."""
        from app.api.optimization_api import OptimizationSubmitRequest, ParamRangeSpec

        request = OptimizationSubmitRequest(
            strategy_id="test_strategy",
            param_ranges={
                "fast": ParamRangeSpec(start=5, end=15, step=5, type="int"),
                "slow": ParamRangeSpec(start=20, end=30, step=5, type="int"),
            },
            n_workers=8,
        )
        assert request.strategy_id == "test_strategy"
        assert len(request.param_ranges) == 2
        assert request.n_workers == 8

    async def test_optimization_submit_response_schema(self):
        """Test optimization submit response schema."""
        from app.api.optimization_api import OptimizationSubmitResponse

        response = OptimizationSubmitResponse(
            task_id="task_123",
            total_combinations=100,
            message="Optimization task submitted"
        )
        assert response.task_id == "task_123"
        assert response.total_combinations == 100

    async def test_optimization_submit_request_defaults(self):
        """Test optimization submit request default values."""
        from app.api.optimization_api import OptimizationSubmitRequest, ParamRangeSpec

        request = OptimizationSubmitRequest(
            strategy_id="test_strategy",
            param_ranges={
                "fast": ParamRangeSpec(start=5, end=15, step=5),
            },
        )
        # n_workers defaults to 4
        assert request.n_workers == 4

    async def test_optimization_submit_request_validation_n_workers_min(self):
        """Test n_workers minimum value validation."""
        from app.api.optimization_api import OptimizationSubmitRequest, ParamRangeSpec
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            OptimizationSubmitRequest(
                strategy_id="test_strategy",
                param_ranges={"fast": ParamRangeSpec(start=5, end=15, step=5)},
                n_workers=0,  # Should be >= 1
            )

    async def test_optimization_submit_request_validation_n_workers_max(self):
        """Test n_workers maximum value validation."""
        from app.api.optimization_api import OptimizationSubmitRequest, ParamRangeSpec
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            OptimizationSubmitRequest(
                strategy_id="test_strategy",
                param_ranges={"fast": ParamRangeSpec(start=5, end=15, step=5)},
                n_workers=100,  # Should be <= 32
            )


# ==================== Router Tests ====================

@pytest.mark.asyncio
class TestOptimizationRouter:
    """Tests for optimization router."""

    async def test_router_exists(self):
        """Test that router exists."""
        from app.api.optimization_api import router

        assert router is not None
        assert hasattr(router, 'routes')

    async def test_router_endpoint_count(self):
        """Test router endpoint count."""
        from app.api.optimization_api import router

        routes = list(router.routes)
        # Should have 5 routes
        assert len(routes) == 5

    async def test_router_has_strategy_params_endpoint(self):
        """Test that strategy params endpoint exists."""
        from app.api.optimization_api import router

        routes = [route for route in router.routes if hasattr(route, 'path')]
        params_routes = [r for r in routes if "/strategy-params/" in r.path]
        assert len(params_routes) > 0

    async def test_router_has_submit_endpoint(self):
        """Test that submit endpoint exists."""
        from app.api.optimization_api import router

        routes = [route for route in router.routes if hasattr(route, 'path') and hasattr(route, 'methods')]
        submit_routes = [r for r in routes if "/submit" in r.path and "POST" in r.methods]
        assert len(submit_routes) > 0

    async def test_router_has_progress_endpoint(self):
        """Test that progress endpoint exists."""
        from app.api.optimization_api import router

        routes = [route for route in router.routes if hasattr(route, 'path')]
        progress_routes = [r for r in routes if "/progress/" in r.path]
        assert len(progress_routes) > 0

    async def test_router_has_results_endpoint(self):
        """Test that results endpoint exists."""
        from app.api.optimization_api import router

        routes = [route for route in router.routes if hasattr(route, 'path')]
        results_routes = [r for r in routes if "/results/" in r.path]
        assert len(results_routes) > 0

    async def test_router_has_cancel_endpoint(self):
        """Test that cancel endpoint exists."""
        from app.api.optimization_api import router

        routes = [route for route in router.routes if hasattr(route, 'path') and hasattr(route, 'methods')]
        cancel_routes = [r for r in routes if "/cancel/" in r.path and "POST" in r.methods]
        assert len(cancel_routes) > 0


# ==================== Service Function Tests ====================

@pytest.mark.asyncio
class TestOptimizationService:
    """Tests for optimization service."""

    async def test_generate_param_grid_exists(self):
        """Test that parameter grid generation function exists."""
        from app.services.param_optimization_service import generate_param_grid

        param_ranges = {
            "fast": {"start": 5, "end": 15, "step": 5, "type": "int"},
            "slow": {"start": 20, "end": 30, "step": 5, "type": "int"}
        }

        grid = generate_param_grid(param_ranges)
        assert isinstance(grid, list)
        assert len(grid) > 0

    async def test_submit_optimization_exists(self):
        """Test that submit optimization function exists."""
        from app.services.param_optimization_service import submit_optimization

        # Test that function exists and is callable
        assert callable(submit_optimization)

    async def test_get_optimization_progress_exists(self):
        """Test that get progress function exists."""
        from app.services.param_optimization_service import get_optimization_progress

        # Test that function exists and is callable
        assert callable(get_optimization_progress)

    async def test_get_optimization_results_exists(self):
        """Test that get results function exists."""
        from app.services.param_optimization_service import get_optimization_results

        # Test that function exists and is callable
        assert callable(get_optimization_results)

    async def test_cancel_optimization_exists(self):
        """Test that cancel optimization function exists."""
        from app.services.param_optimization_service import cancel_optimization

        # Test that function exists and is callable
        assert callable(cancel_optimization)
