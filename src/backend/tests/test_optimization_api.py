"""
参数优化 API 完整测试

测试：
- 获取策略参数
- 提交优化任务
- 查询优化进度
- 获取优化结果
- 取消优化任务
"""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import HTTPException


@pytest.fixture
def mock_current_user():
    """Mock current user"""
    user = MagicMock()
    user.sub = "test_user_123"
    return user


@pytest.fixture
def mock_strategy_template():
    """Mock strategy template"""
    tpl = MagicMock()
    tpl.id = "test_strategy"
    tpl.name = "Test Strategy"
    tpl.params = {
        "fast_period": MagicMock(type="int", default=10, description="Fast period"),
        "slow_period": MagicMock(type="int", default=20, description="Slow period"),
    }
    return tpl


# ==================== 获取策略参数测试 ====================

@pytest.mark.asyncio
class TestOptimizationStrategyParams:
    """获取策略参数测试"""

    async def test_get_strategy_params_success(self, mock_current_user, mock_strategy_template):
        """测试成功获取策略参数"""
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
        """测试策略不存在"""
        from app.api.optimization_api import get_strategy_params

        with patch('app.api.optimization_api.get_template_by_id', return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await get_strategy_params(
                    strategy_id="nonexistent",
                    current_user=mock_current_user
                )

            assert exc_info.value.status_code == 404
            assert "不存在" in exc_info.value.detail

    async def test_get_strategy_params_empty_params(self, mock_current_user):
        """测试策略无参数"""
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


# ==================== 提交优化任务测试 ====================

@pytest.mark.asyncio
class TestOptimizationSubmit:
    """提交优化任务测试"""

    async def test_submit_optimization_success(self, mock_current_user, mock_strategy_template):
        """测试成功提交优化任务"""
        from app.api.optimization_api import submit_optimization_task, OptimizationSubmitRequest, ParamRangeSpec

        request = OptimizationSubmitRequest(
            strategy_id="test_strategy",
            param_ranges={
                "fast": ParamRangeSpec(start=5, end=15, step=5, type="int"),
            },
            n_workers=4,
        )

        with patch('app.api.optimization_api.get_template_by_id', return_value=mock_strategy_template):
            with patch('app.services.strategy_service.get_template_by_id', return_value=mock_strategy_template):
                with patch('app.services.param_optimization_service.generate_param_grid', return_value=[{"fast": 5}, {"fast": 10}, {"fast": 15}]):
                    with patch('app.services.param_optimization_service.submit_optimization', return_value="task_123"):
                        result = await submit_optimization_task(
                            request=request,
                            current_user=mock_current_user
                        )

                        assert result.task_id == "task_123"
                        assert result.total_combinations == 3
                        assert "已提交" in result.message

    async def test_submit_optimization_strategy_not_found(self, mock_current_user):
        """测试策略不存在"""
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
            assert "不存在" in exc_info.value.detail

    async def test_submit_optimization_empty_grid(self, mock_current_user, mock_strategy_template):
        """测试参数网格为空"""
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
                    assert "参数网格为空" in exc_info.value.detail

    async def test_submit_optimization_value_error(self, mock_current_user, mock_strategy_template):
        """测试服务返回 ValueError"""
        from app.api.optimization_api import submit_optimization_task, OptimizationSubmitRequest, ParamRangeSpec

        request = OptimizationSubmitRequest(
            strategy_id="test_strategy",
            param_ranges={
                "fast": ParamRangeSpec(start=5, end=15, step=5, type="int"),
            },
        )

        with patch('app.api.optimization_api.get_template_by_id', return_value=mock_strategy_template):
            with patch('app.services.strategy_service.get_template_by_id', return_value=mock_strategy_template):
                with patch('app.services.param_optimization_service.generate_param_grid', return_value=[{"fast": 5}]):
                    with patch('app.services.param_optimization_service.submit_optimization', side_effect=ValueError("Invalid parameters")):
                        with pytest.raises(HTTPException) as exc_info:
                        await submit_optimization_task(
                            request=request,
                            current_user=mock_current_user
                        )

                    assert exc_info.value.status_code == 400
                    assert "Invalid parameters" in exc_info.value.detail

    async def test_submit_optimization_default_workers(self, mock_current_user, mock_strategy_template):
        """测试默认 worker 数量"""
        from app.api.optimization_api import submit_optimization_task, OptimizationSubmitRequest, ParamRangeSpec

        request = OptimizationSubmitRequest(
            strategy_id="test_strategy",
            param_ranges={
                "fast": ParamRangeSpec(start=5, end=15, step=5, type="int"),
            },
            # n_workers defaults to 4
        )

        with patch('app.api.optimization_api.get_template_by_id', return_value=mock_strategy_template):
            with patch('app.services.strategy_service.get_template_by_id', return_value=mock_strategy_template):
                with patch('app.services.param_optimization_service.generate_param_grid', return_value=[{"fast": 5}]):
                    with patch('app.services.param_optimization_service.submit_optimization', return_value="task_123") as mock_submit:
                    await submit_optimization_task(
                        request=request,
                        current_user=mock_current_user
                    )

                    # Verify n_workers=4 was passed
                    call_kwargs = mock_submit.call_args.kwargs
                    assert call_kwargs['n_workers'] == 4


# ==================== 查询优化进度测试 ====================

@pytest.mark.asyncio
class TestOptimizationProgress:
    """查询优化进度测试"""

    async def test_get_progress_success(self, mock_current_user):
        """测试成功获取进度"""
        from app.api.optimization_api import get_progress

        mock_progress = {
            "task_id": "task_123",
            "status": "running",
            "completed": 5,
            "total": 10,
            "progress": 50.0,
        }

        with patch('app.services.param_optimization_service.get_optimization_progress', return_value=mock_progress):
            result = await get_progress(
                task_id="task_123",
                current_user=mock_current_user
            )

            assert result["task_id"] == "task_123"
            assert result["status"] == "running"
            assert result["progress"] == 50.0

    async def test_get_progress_not_found(self, mock_current_user):
        """测试任务不存在"""
        from app.api.optimization_api import get_progress

        with patch('app.api.optimization_api.get_optimization_progress', return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await get_progress(
                    task_id="nonexistent",
                    current_user=mock_current_user
                )

            assert exc_info.value.status_code == 404
            assert "不存在" in exc_info.value.detail


# ==================== 获取优化结果测试 ====================

@pytest.mark.asyncio
class TestOptimizationResults:
    """获取优化结果测试"""

    async def test_get_results_success(self, mock_current_user):
        """测试成功获取结果"""
        from app.api.optimization_api import get_results

        mock_results = {
            "task_id": "task_123",
            "status": "completed",
            "best_params": {"fast": 10, "slow": 20},
            "best_return": 0.15,
            "all_results": [],
        }

        with patch('app.services.param_optimization_service.get_optimization_results', return_value=mock_results):
            result = await get_results(
                task_id="task_123",
                current_user=mock_current_user
            )

            assert result["task_id"] == "task_123"
            assert result["status"] == "completed"
            assert result["best_return"] == 0.15

    async def test_get_results_not_found(self, mock_current_user):
        """测试任务不存在"""
        from app.api.optimization_api import get_results

        with patch('app.services.param_optimization_service.get_optimization_results', return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await get_results(
                    task_id="nonexistent",
                    current_user=mock_current_user
                )

            assert exc_info.value.status_code == 404
            assert "不存在" in exc_info.value.detail


# ==================== 取消优化任务测试 ====================

@pytest.mark.asyncio
class TestOptimizationCancel:
    """取消优化任务测试"""

    async def test_cancel_task_success(self, mock_current_user):
        """测试成功取消任务"""
        from app.api.optimization_api import cancel_task

        with patch('app.services.param_optimization_service.cancel_optimization', return_value=True):
            result = await cancel_task(
                task_id="task_123",
                current_user=mock_current_user
            )

            assert result["message"] == "已请求取消"
            assert result["task_id"] == "task_123"

    async def test_cancel_task_not_found(self, mock_current_user):
        """测试任务不存在"""
        from app.api.optimization_api import cancel_task

        with patch('app.services.param_optimization_service.cancel_optimization', return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await cancel_task(
                    task_id="nonexistent",
                    current_user=mock_current_user
                )

            assert exc_info.value.status_code == 404
            assert "不存在" in exc_info.value.detail


# ==================== Schema 测试 ====================

@pytest.mark.asyncio
class TestOptimizationSchemas:
    """测试优化 Schema"""

    async def test_param_range_spec_schema(self):
        """测试参数范围 Schema"""
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
        """测试优化提交请求 Schema"""
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
        """测试优化提交响应 Schema"""
        from app.api.optimization_api import OptimizationSubmitResponse

        response = OptimizationSubmitResponse(
            task_id="task_123",
            total_combinations=100,
            message="优化任务已提交"
        )
        assert response.task_id == "task_123"
        assert response.total_combinations == 100

    async def test_optimization_submit_request_defaults(self):
        """测试优化提交请求默认值"""
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
        """测试 n_workers 最小值验证"""
        from app.api.optimization_api import OptimizationSubmitRequest, ParamRangeSpec
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            OptimizationSubmitRequest(
                strategy_id="test_strategy",
                param_ranges={"fast": ParamRangeSpec(start=5, end=15, step=5)},
                n_workers=0,  # Should be >= 1
            )

    async def test_optimization_submit_request_validation_n_workers_max(self):
        """测试 n_workers 最大值验证"""
        from app.api.optimization_api import OptimizationSubmitRequest, ParamRangeSpec
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            OptimizationSubmitRequest(
                strategy_id="test_strategy",
                param_ranges={"fast": ParamRangeSpec(start=5, end=15, step=5)},
                n_workers=100,  # Should be <= 32
            )


# ==================== 路由测试 ====================

@pytest.mark.asyncio
class TestOptimizationRouter:
    """测试优化路由"""

    async def test_router_exists(self):
        """测试路由存在"""
        from app.api.optimization_api import router

        assert router is not None
        assert hasattr(router, 'routes')

    async def test_router_endpoint_count(self):
        """测试路由端点数量"""
        from app.api.optimization_api import router

        routes = list(router.routes)
        # Should have 5 routes
        assert len(routes) == 5

    async def test_router_has_strategy_params_endpoint(self):
        """测试有获取策略参数端点"""
        from app.api.optimization_api import router

        routes = [route for route in router.routes if hasattr(route, 'path')]
        params_routes = [r for r in routes if "/strategy-params/" in r.path]
        assert len(params_routes) > 0

    async def test_router_has_submit_endpoint(self):
        """测试有提交优化端点"""
        from app.api.optimization_api import router

        routes = [route for route in router.routes if hasattr(route, 'path') and hasattr(route, 'methods')]
        submit_routes = [r for r in routes if "/submit" in r.path and "POST" in r.methods]
        assert len(submit_routes) > 0

    async def test_router_has_progress_endpoint(self):
        """测试有进度查询端点"""
        from app.api.optimization_api import router

        routes = [route for route in router.routes if hasattr(route, 'path')]
        progress_routes = [r for r in routes if "/progress/" in r.path]
        assert len(progress_routes) > 0

    async def test_router_has_results_endpoint(self):
        """测试有结果获取端点"""
        from app.api.optimization_api import router

        routes = [route for route in router.routes if hasattr(route, 'path')]
        results_routes = [r for r in routes if "/results/" in r.path]
        assert len(results_routes) > 0

    async def test_router_has_cancel_endpoint(self):
        """测试有取消任务端点"""
        from app.api.optimization_api import router

        routes = [route for route in router.routes if hasattr(route, 'path') and hasattr(route, 'methods')]
        cancel_routes = [r for r in routes if "/cancel/" in r.path and "POST" in r.methods]
        assert len(cancel_routes) > 0


# ==================== 服务函数测试 ====================

@pytest.mark.asyncio
class TestOptimizationService:
    """优化服务测试"""

    async def test_generate_param_grid_exists(self):
        """测试参数网格生成函数存在"""
        from app.services.param_optimization_service import generate_param_grid

        param_ranges = {
            "fast": {"start": 5, "end": 15, "step": 5, "type": "int"},
            "slow": {"start": 20, "end": 30, "step": 5, "type": "int"}
        }

        grid = generate_param_grid(param_ranges)
        assert isinstance(grid, list)
        assert len(grid) > 0

    async def test_submit_optimization_exists(self):
        """测试提交优化函数存在"""
        from app.services.param_optimization_service import submit_optimization

        # Test that function exists and is callable
        assert callable(submit_optimization)

    async def test_get_optimization_progress_exists(self):
        """测试获取进度函数存在"""
        from app.services.param_optimization_service import get_optimization_progress

        # Test that function exists and is callable
        assert callable(get_optimization_progress)

    async def test_get_optimization_results_exists(self):
        """测试获取结果函数存在"""
        from app.services.param_optimization_service import get_optimization_results

        # Test that function exists and is callable
        assert callable(get_optimization_results)

    async def test_cancel_optimization_exists(self):
        """测试取消优化函数存在"""
        from app.services.param_optimization_service import cancel_optimization

        # Test that function exists and is callable
        assert callable(cancel_optimization)
