"""
增强的回测 API 路由测试

测试参数优化、报告导出、WebSocket 端点
"""
import pytest
import json
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.main_updated import app
from app.schemas.backtest_enhanced import (
    BacktestRequest,
    OptimizationRequest,
    TaskStatus,
)
from app.models.permission import Permission, Role
from app.models.user import User
from app.websocket_manager import manager as ws_manager


@pytest.fixture
def client():
    """创建测试客户端"""
    return TestClient(app)


@pytest.fixture
def auth_client(client):
    """创建带认证的客户端"""
    # Mock 认证
    with patch('app.api.deps_permissions.get_current_user') as mock_get_user:
        # 创建一个有权限的用户
        user = User(
            id="test-user-api",
            username="testuser",
            email="test@api.example.com",
            hashed_password="hashed",
        )
        user.roles = [Role.USER]

        mock_get_user.return_value = user

        # Mock 权限检查
        with patch('app.api.backtest_enhanced.require_permission') as mock_require_perm:
            mock_require_perm.return_value = lambda perm: lambda user: user

            return client


# ==================== 回测 API 测试 ====================

class TestRunBacktestAPI:
    """测试运行回测 API"""

    def test_run_backtest_success(self, auth_client):
        """测试成功运行回测"""
        request_data = {
            "strategy_id": "ma_cross",
            "symbol": "000001.SZ",
            "start_date": "2023-01-01T00:00:00",
            "end_date": "2023-12-31T00:00:00",
            "initial_cash": 100000,
            "commission": 0.001,
            "params": {"fast_period": 5, "slow_period": 20},
        }

        # Mock BacktestService.run_backtest
        with patch('app.api.backtest_enhanced.BacktestService') as MockBacktestService:
            mock_service = AsyncMock()
            mock_service.run_backtest = AsyncMock(
                return_value=type('Response', (object,), {
                    '__init__': lambda self, task_id, status, message: None,
                    'task_id': task_id,
                    'status': status,
                    'message': message,
                })(
                    task_id="test-task-123",
                    status=TaskStatus.PENDING,
                    message="回测任务已创建",
                )
            )
            MockBacktestService.return_value = mock_service

            response = auth_client.post("/api/v1/backtests/run", json=request_data)

            # 验证响应
            assert response.status_code == 200
            data = response.json()
            assert data["task_id"] == "test-task-123"
            assert data["status"] == "pending"

    def test_run_backtest_invalid_params(self, auth_client):
        """测试无效参数运行回测"""
        request_data = {
            "strategy_id": "ma_cross",
            "symbol": "000001.SZ",
            "start_date": "2023-12-31",  # 晚于结束日期
            "end_date": "2023-01-01",
            "initial_cash": 100000,
            "commission": 0.001,
        }

        response = auth_client.post("/api/v1/backtests/run", json=request_data)

        # 应该返回 422 错误
        assert response.status_code == 422
        assert "end_date" in response.json()["detail"][0]


# ==================== 参数优化 API 测试 ====================

class TestGridSearchAPI:
    """测试网格搜索优化 API"""

    def test_grid_search_success(self, auth_client):
        """测试成功的网格搜索"""
        request_data = {
            "strategy_id": "ma_cross",
            "method": "grid",
            "metric": "sharpe_ratio",
            "backtest_config": {
                "strategy_id": "ma_cross",
                "symbol": "000001.SZ",
                "start_date": "2023-01-01",
                "end_date": "2023-12-31",
                "initial_cash": 100000,
                "commission": 0.001,
            },
            "param_grid": {
                "fast_period": [5, 10],
                "slow_period": [20, 30],
            },
        }

        # Mock OptimizationService
        with patch('app.api.backtest_enhanced.OptimizationService') as MockOptService:
            mock_service = AsyncMock()
            mock_service.run_grid_search = AsyncMock(
                return_value={
                    "best_params": {"fast_period": 10, "slow_period": 30},
                    "best_metrics": {"sharpe_ratio": 2.0, "total_return": 20.0},
                    "all_results": [
                        {
                            "params": {"fast_period": 5, "slow_period": 20},
                            "metrics": {"sharpe_ratio": 1.5},
                        },
                        {
                            "params": {"fast_period": 10, "slow_period": 30},
                            "metrics": {"sharpe_ratio": 2.0},
                        },
                    ],
                    "n_trials": 4,
                }
            )
            MockOptService.return_value = mock_service

            response = auth_client.post("/api/v1/backtests/optimization/grid", json=request_data)

            # 验证响应
            assert response.status_code == 200
            data = response.json()
            assert "best_params" in data
            assert data["best_params"] == {"fast_period": 10, "slow_period": 30}
            assert data["n_trials"] == 4


class TestBayesianOptimizationAPI:
    """测试贝叶斯优化 API"""

    def test_bayesian_optimization_success(self, auth_client):
        """测试成功的贝叶斯优化"""
        request_data = {
            "strategy_id": "ma_cross",
            "method": "bayesian",
            "metric": "sharpe_ratio",
            "n_trials": 50,
            "backtest_config": {
                "strategy_id": "ma_cross",
                "symbol": "000001.SZ",
                "start_date": "2023-01-01",
                "end_date": "2023-12-31",
                "initial_cash": 100000,
                "commission": 0.001,
            },
            "param_bounds": {
                "fast_period": {"type": "int", "min": 5, "max": 20},
                "slow_period": {"type": "int", "min": 20, "max": 60},
            },
        }

        # Mock OptimizationService
        with patch('app.api.backtest_enhanced.OptimizationService') as MockOptService:
            mock_service = AsyncMock()
            mock_service.run_bayesian_optimization = AsyncMock(
                return_value={
                    "best_params": {"fast_period": 15, "slow_period": 40},
                    "best_metrics": {"sharpe_ratio": 2.5},
                    "all_results": [],
                    "n_trials": 50,
                }
            )
            MockOptService.return_value = mock_service

            response = auth_client.post("/api/v1/backtests/optimization/bayesian", json=request_data)

            # 验证响应
            assert response.status_code == 200
            data = response.json()
            assert data["best_params"] == {"fast_period": 15, "slow_period": 40}
            assert data["n_trials"] == 50

    def test_bayesian_optimization_invalid_method(self, auth_client):
        """测试使用网格搜索方法调用贝叶斯 API"""
        request_data = {
            "strategy_id": "ma_cross",
            "method": "grid",  # 错误的方法
            "metric": "sharpe_ratio",
            "backtest_config": {
                "strategy_id": "ma_cross",
                "symbol": "000001.SZ",
                "start_date": "2023-01-01",
                "end_date": "2023-12-31",
                "initial_cash": 100000,
                "commission": 0.001,
            },
            "param_grid": {
                "fast_period": [5, 10],
                "slow_period": [20, 30],
            },
        }

        response = auth_client.post("/api/v1/backtests/optimization/bayesian", json=request_data)

        # 应该返回 400 错误
        assert response.status_code == 400
        assert "method" in response.json()["detail"][0]


# ==================== 报告导出 API 测试 ====================

class TestHTMLReportExport:
    """测试 HTML 报告导出"""

    def test_export_html_report(self, auth_client):
        """测试导出 HTML 报告"""
        # Mock BacktestService.get_result
        with patch('app.api.backtest_enhanced.BacktestService') as MockBacktestService:
            mock_service = AsyncMock()
            mock_service.get_result = AsyncMock(
                return_value={
                    "task_id": "test-task-456",
                    "strategy_id": "ma_cross",
                    "symbol": "000001.SZ",
                    "start_date": datetime(2023, 1, 1),
                    "end_date": datetime(2023, 12, 31),
                    "status": TaskStatus.COMPLETED,
                    "total_return": 15.5,
                    "annual_return": 15.5,
                    "sharpe_ratio": 1.8,
                    "max_drawdown": 12.5,
                    "win_rate": 60.0,
                    "total_trades": 20,
                    "profitable_trades": 12,
                    "losing_trades": 8,
                    "params": {"fast_period": 5, "slow_period": 20},
                    "created_at": datetime.utcnow(),
                }
            )
            MockBacktestService.return_value = mock_service

            # Mock ReportService
            with patch('app.api.backtest_enhanced.ReportService') as MockReportService:
                mock_report_service = AsyncMock()
                mock_report_service.generate_html_report = AsyncMock(
                    return_value="<html>...</html>"
                )
                MockReportService.return_value = mock_report_service

                response = auth_client.get("/api/v1/backtests/test-task-456/report/html")

                # 验证响应
                assert response.status_code == 200
                assert response.headers["content-type"] == "text/html; charset=utf-8"
                assert "attachment" in response.headers["content-disposition"]


class TestPDFReportExport:
    """测试 PDF 报告导出"""

    def test_export_pdf_report(self, auth_client):
        """测试导出 PDF 报告"""
        # Mock BacktestService.get_result
        with patch('app.api.backtest_enhanced.BacktestService') as MockBacktestService:
            mock_service = AsyncMock()
            mock_service.get_result = AsyncMock(
                return_value={
                    "task_id": "test-task-789",
                    "strategy_id": "ma_cross",
                    "symbol": "000001.SZ",
                    "start_date": datetime(2023, 1, 1),
                    "end_date": datetime(2023, 12, 31),
                    "status": TaskStatus.COMPLETED,
                    "total_return": 15.5,
                    "params": {},
                }
            )
            MockBacktestService.return_value = mock_service

            # Mock ReportService
            with patch('app.api.backtest_enhanced.ReportService') as MockReportService:
                mock_report_service = AsyncMock()
                mock_report_service.generate_pdf_report = AsyncMock(
                    return_value=b'%PDF-1.4\n...'
                )
                MockReportService.return_value = mock_report_service

                response = auth_client.get("/api/v1/backtests/test-task-789/report/pdf")

                # 验证响应
                assert response.status_code == 200
                assert response.headers["content-type"] == "application/pdf"
                assert "backtest.pdf" in response.headers["content-disposition"]

    def test_export_pdf_report_not_available(self, auth_client):
        """测试 PDF 生成功能不可用"""
        # Mock BacktestService.get_result
        with patch('app.api.backtest_enhanced.BacktestService') as MockBacktestService:
            mock_service = AsyncMock()
            mock_service.get_result = AsyncMock(
                return_value={
                    "task_id": "test-task-789",
                    "strategy_id": "ma_cross",
                    "status": TaskStatus.COMPLETED,
                }
            )
            MockBacktestService.return_value = mock_service

            # Mock ReportService 抛出 ImportError
            with patch('app.api.backtest_enhanced.ReportService') as MockReportService:
                mock_report_service = AsyncMock()
                mock_report_service.generate_pdf_report = AsyncMock(
                    side_effect=ImportError("weasyprint not available")
                )
                MockReportService.return_value = mock_report_service

                response = auth_client.get("/api/v1/backtests/test-task-789/report/pdf")

                # 应该返回 500 错误
                assert response.status_code == 500
                assert "weasyprint" in response.json()["detail"]


class TestExcelReportExport:
    """测试 Excel 报告导出"""

    def test_export_excel_report(self, auth_client):
        """测试导出 Excel 报告"""
        # Mock BacktestService.get_result
        with patch('app.api.backtest_enhanced.BacktestService') as MockBacktestService:
            mock_service = AsyncMock()
            mock_service.get_result = AsyncMock(
                return_value={
                    "task_id": "test-task-012",
                    "strategy_id": "ma_cross",
                    "symbol": "000001.SZ",
                    "status": TaskStatus.COMPLETED,
                }
            )
            MockBacktestService.return_value = mock_service

            # Mock ReportService
            with patch('app.api.backtest_enhanced.ReportService') as MockReportService:
                mock_report_service = AsyncMock()
                mock_report_service.generate_excel_report = AsyncMock(
                    return_value=b'PK\x03\x04...'  # Excel 文件头
                )
                MockReportService.return_value = mock_report_service

                response = auth_client.get("/api/v1/backtests/test-task-012/report/excel")

                # 验证响应
                assert response.status_code == 200
                assert "sheet" in response.headers["content-type"]
                assert "backtest.xlsx" in response.headers["content-disposition"]


# ==================== WebSocket 端点测试 ====================

@pytest.mark.asyncio
class TestWebSocketEndpoint:
    """测试 WebSocket 实时推送"""

    @pytest.mark.asyncio
    async def test_websocket_connection(self, client):
        """测试 WebSocket 连接建立"""
        # 使用 testclient 的 websocket 功能
        with client.websocket_connect(f"/api/v1/backtests/ws/backtest/test-task-123") as websocket:
            # 连接建立成功
            # 应该收到连接成功消息
            data = websocket.receive_json()

            assert data["type"] == "connected"
            assert data["task_id"] == "test-task-123"

    @pytest.mark.asyncio
    async def test_websocket_progress_updates(self, client):
        """测试 WebSocket 进度更新"""
        # Mock BacktestService
        with patch('app.api.backtest_enhanced.BacktestService') as MockBacktestService:
            mock_service = AsyncMock()
            mock_service.get_task_status = AsyncMock(return_value="running")
            mock_service.get_result = AsyncMock(
                return_value={
                    "task_id": "test-task-456",
                    "status": "running",
                    "total_return": 10.5,
                    "sharpe_ratio": 1.2,
                    "current_date": "2023-06-30",
                }
            )
            MockBacktestService.return_value = mock_service

            # Mock ConnectionManager
            with patch('app.api.backtest_enhanced.ws_manager') as mock_manager:
                mock_ws_manager = MagicMock()
                mock_ws_manager.connect = AsyncMock()
                mock_ws_manager.send_to_task = AsyncMock()
                mock_ws_manager.disconnect = MagicMock()

                # Mock WebSocket 连接
                mock_websocket = MagicMock()
                mock_websocket.send_json = MagicMock()
                mock_websocket.accept = MagicMock()

                # 创建异步生成器来模拟 WebSocket
                async def mock_websocket_connect(url):
                    """模拟 WebSocket 连接"""
                    yield mock_websocket

                with patch('fastapi.WebSocket.connect', side_effect=mock_websocket_connect):
                    # 发送进度更新
                    await mock_ws_manager.send_to_task(
                        "test-task-456",
                        {
                            "type": "progress",
                            "task_id": "test-task-456",
                            "status": "running",
                            "data": {
                                "total_return": 10.5,
                                "sharpe_ratio": 1.2,
                            },
                        }
                    )

                    # 验证发送了消息
                    mock_websocket.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_completed_message(self, client):
        """测试 WebSocket 完成消息"""
        with patch('app.api.backtest_enhanced.BacktestService') as MockBacktestService:
            mock_service = AsyncMock()
            mock_service.get_task_status = AsyncMock(return_value="completed")
            mock_service.get_result = AsyncMock(
                return_value={
                    "task_id": "test-task-789",
                    "status": "completed",
                    "total_return": 20.5,
                    "sharpe_ratio": 2.1,
                }
            )
            MockBacktestService.return_value = mock_service

            with patch('app.api.backtest_enhanced.ws_manager') as mock_manager:
                mock_ws_manager = MagicMock()
                mock_ws_manager.send_to_task = AsyncMock()

                mock_websocket = MagicMock()
                mock_websocket.send_json = MagicMock()

                async def mock_websocket_connect(url):
                    yield mock_websocket

                with patch('fastapi.WebSocket.connect', side_effect=mock_websocket_connect):
                    await mock_ws_manager.send_to_task(
                        "test-task-789",
                        {
                            "type": "completed",
                            "task_id": "test-task-789",
                            "result": {
                                "status": "completed",
                                "total_return": 20.5,
                                "sharpe_ratio": 2.1,
                            },
                        }
                    )

                    # 验证发送了完成消息
                    mock_websocket.send_json.assert_called_once()
                    data = mock_websocket.send_json.call_args[0][0]
                    assert data["type"] == "completed"


# ==================== 集成测试 ====================

class TestBacktestAPIIntegration:
    """回测 API 集成测试"""

    def test_full_backtest_workflow(self, auth_client):
        """测试完整的回测工作流"""
        # 1. 提交回测任务
        request_data = {
            "strategy_id": "ma_cross",
            "symbol": "000001.SZ",
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
            "initial_cash": 100000,
            "commission": 0.001,
            "params": {"fast_period": 5, "slow_period": 20},
        }

        with patch('app.api.backtest_enhanced.BacktestService') as MockBacktestService:
            mock_service = AsyncMock()
            mock_service.run_backtest = AsyncMock(
                return_value=type('Response', (object,), {
                    '__init__': lambda self, **kwargs: setattr(self, 'task_id', kwargs.get('task_id')) or None,
                })(
                    task_id="test-integration-task",
                    status=TaskStatus.PENDING,
                    message="回测任务已创建",
                )
            )
            mock_service.get_task_status = AsyncMock(return_value="completed")
            mock_service.get_result = AsyncMock(
                return_value={
                    "task_id": "test-integration-task",
                    "status": "completed",
                    "total_return": 18.5,
                    "sharpe_ratio": 1.9,
                    "max_drawdown": 11.0,
                }
            )
            MockBacktestService.return_value = mock_service

            # 提交任务
            run_response = auth_client.post("/api/v1/backtests/run", json=request_data)
            assert run_response.status_code == 200
            task_id = run_response.json()["task_id"]

            # 查询任务状态
            status_response = auth_client.get(f"/api/v1/backtests/{task_id}/status")
            assert status_response.status_code == 200
            assert status_response.json()["status"] == "completed"

            # 获取回测结果
            result_response = auth_client.get(f"/api/v1/backtests/{task_id}")
            assert result_response.status_code == 200
            result = result_response.json()
            assert result["total_return"] == 18.5
            assert result["sharpe_ratio"] == 1.9


class TestOptimizationAPIIntegration:
    """参数优化 API 集成测试"""

    def test_full_grid_search_workflow(self, auth_client):
        """测试完整的网格搜索工作流"""
        request_data = {
            "strategy_id": "ma_cross",
            "method": "grid",
            "metric": "sharpe_ratio",
            "backtest_config": {
                "strategy_id": "ma_cross",
                "symbol": "000001.SZ",
                "start_date": "2023-01-01",
                "end_date": "2023-12-31",
                "initial_cash": 100000,
                "commission": 0.001,
            },
            "param_grid": {
                "fast_period": [5, 10, 15],
                "slow_period": [20, 30, 40],
            },
        }

        with patch('app.api.backtest_enhanced.OptimizationService') as MockOptService:
            mock_service = AsyncMock()
            mock_service.run_grid_search = AsyncMock(
                return_value={
                    "best_params": {"fast_period": 10, "slow_period": 30},
                    "best_metrics": {"sharpe_ratio": 2.1},
                    "all_results": [
                        {
                            "params": {"fast_period": 5, "slow_period": 20},
                            "metrics": {"sharpe_ratio": 1.8},
                        },
                        {
                            "params": {"fast_period": 10, "slow_period": 30},
                            "metrics": {"sharpe_ratio": 2.1},
                        },
                        {
                            "params": {"fast_period": 15, "slow_period": 40},
                            "metrics": {"sharpe_ratio": 1.5},
                        },
                    ],
                    "n_trials": 9,  # 3 * 3 = 9
                }
            )
            MockOptService.return_value = mock_service

            # 运行网格搜索
            response = auth_client.post("/api/v1/backtests/optimization/grid", json=request_data)

            # 验证结果
            assert response.status_code == 200
            data = response.json()
            assert data["best_params"] == {"fast_period": 10, "slow_period": 30}
            assert data["best_metrics"]["sharpe_ratio"] == 2.1
            assert data["n_trials"] == 9
            assert len(data["all_results"]) == 9
