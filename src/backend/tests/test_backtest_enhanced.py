"""
Enhanced Backtest API Tests.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.api import backtest, backtest_enhanced
from app.schemas.backtest_enhanced import BacktestResult, TaskStatus

# Valid backtest request configuration
VALID_BACKTEST_REQUEST = {
    "strategy_id": "001_ma_cross",
    "symbol": "000001.SZ",
    "start_date": "2023-01-01T00:00:00",
    "end_date": "2023-06-30T00:00:00",
    "initial_cash": 100000,
    "commission": 0.001,
    "params": {},
}


# Valid optimization request
VALID_OPTIMIZATION_REQUEST = {
    "strategy_id": "strat1",
    "backtest_config": VALID_BACKTEST_REQUEST,
    "method": "grid",
    "param_grid": {"period": [10, 20, 30]},
}


@pytest.fixture
def clear_lru_cache():
    """Clear lru_cache before each test to enable proper mocking."""
    # Clear the lru_cache
    backtest.get_backtest_service.cache_clear()
    backtest_enhanced.get_backtest_service.cache_clear()
    backtest_enhanced.get_report_service.cache_clear()
    yield
    # Clear again after test
    backtest.get_backtest_service.cache_clear()
    backtest_enhanced.get_backtest_service.cache_clear()
    backtest_enhanced.get_report_service.cache_clear()


class TestStrategyReportMetadata:
    def test_prefers_template_metadata(self):
        from app.api import backtest_enhanced

        template = MagicMock()
        template.name = "Template Strategy"
        template.description = "Template description"

        with patch("app.api.backtest_enhanced.get_template_by_id", return_value=template):
            result = backtest_enhanced._build_strategy_report_metadata("s1")

        assert result == {
            "name": "Template Strategy",
            "description": "Template description",
        }

    def test_falls_back_to_strategy_config(self, tmp_path):
        from app.api import backtest_enhanced

        strategy_dir = tmp_path / "backtest" / "s1"
        strategy_dir.mkdir(parents=True)
        (strategy_dir / "config.yaml").write_text(
            "strategy:\n  name: Config Strategy\n  description: Config description\n",
            encoding="utf-8",
        )

        with patch("app.api.backtest_enhanced.get_template_by_id", return_value=None):
            with patch("app.api.backtest_enhanced.STRATEGIES_DIR", tmp_path):
                result = backtest_enhanced._build_strategy_report_metadata("s1")

        assert result == {
            "name": "Config Strategy",
            "description": "Config description",
        }

    def test_uses_default_fallback_when_metadata_missing(self):
        from app.api import backtest_enhanced

        with patch("app.api.backtest_enhanced.get_template_by_id", return_value=None):
            result = backtest_enhanced._build_strategy_report_metadata("missing")

        assert result == {
            "name": "Strategy missing",
            "description": "Strategy metadata unavailable",
        }


class TestEnhancedBacktestSchema:
    def test_backtest_result_allows_negative_max_drawdown(self):
        result = BacktestResult(
            task_id="task-1",
            strategy_id="s1",
            symbol="000001.SZ",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 6, 1),
            status=TaskStatus.COMPLETED,
            total_return=12.5,
            annual_return=10.2,
            sharpe_ratio=1.4,
            max_drawdown=-8.3,
            win_rate=55.0,
            total_trades=10,
            profitable_trades=6,
            losing_trades=4,
            equity_curve=[],
            equity_dates=[],
            drawdown_curve=[],
            trades=[],
            created_at=datetime(2024, 6, 2),
            error_message=None,
        )

        assert result.max_drawdown == -8.3


@pytest.mark.asyncio
class TestEnhancedBacktestRun:
    """Tests for enhanced backtest run."""

    async def test_run_backtest_requires_auth(self, client: AsyncClient):
        """Test that authentication is required."""
        resp = await client.post("/api/v1/backtest/run", json=VALID_BACKTEST_REQUEST)
        assert resp.status_code == 401  # Unauthorized for unauthenticated requests

    async def test_run_backtest_success(self, client: AsyncClient, auth_headers: dict):
        """Test successful backtest run."""
        with patch("app.services.backtest_service.BacktestService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.run_backtest = AsyncMock(
                return_value=MagicMock(
                    task_id="task123",
                    status="pending",
                )
            )
            mock_service_class.return_value = mock_service

            with patch("app.api.backtest_enhanced.ws_manager") as mock_ws:
                mock_ws.send_to_task = AsyncMock()

                resp = await client.post(
                    "/api/v1/backtest/run", headers=auth_headers, json=VALID_BACKTEST_REQUEST
                )
                assert resp.status_code == 200

    async def test_run_backtest_invalid_data(self, client: AsyncClient, auth_headers: dict):
        """Test invalid data."""
        resp = await client.post(
            "/api/v1/backtest/run",
            headers=auth_headers,
            json={
                "strategy_id": "",  # Invalid
            },
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestEnhancedBacktestGetResult:
    """Tests for enhanced backtest result retrieval."""

    async def test_get_result_requires_auth(self, client: AsyncClient):
        """Test that authentication is required."""
        resp = await client.get("/api/v1/backtest/task123")
        assert resp.status_code == 401  # Unauthorized for unauthenticated requests

    async def test_get_result_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test when result does not exist."""
        with patch("app.api.backtest.BacktestService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_result = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service

            resp = await client.get("/api/v1/backtest/nonexistent", headers=auth_headers)
            assert resp.status_code == 404

    async def test_get_result_success(
        self, client: AsyncClient, auth_headers: dict, clear_lru_cache
    ):
        """Test getting result."""
        mock_service = AsyncMock()
        mock_service.get_result = AsyncMock(
            return_value={
                "task_id": "task123",
                "strategy_id": "strat1",
                "symbol": "000001.SZ",
                "start_date": "2023-01-01T00:00:00Z",
                "end_date": "2023-06-30T00:00:00Z",
                "status": "completed",
                "total_return": 10.0,
                "annual_return": 10.0,
                "sharpe_ratio": 1.2,
                "max_drawdown": 5.0,
                "win_rate": 50.0,
                "total_trades": 2,
                "profitable_trades": 1,
                "losing_trades": 1,
                "equity_curve": [100000.0],
                "equity_dates": ["2023-01-01"],
                "drawdown_curve": [0.0],
                "trades": [],
                "created_at": "2023-07-01T00:00:00Z",
                "error_message": None,
            }
        )

        with patch("app.api.backtest.BacktestService", return_value=mock_service):
            resp = await client.get("/api/v1/backtest/task123", headers=auth_headers)
            assert resp.status_code == 200


@pytest.mark.asyncio
class TestEnhancedBacktestStatus:
    """Tests for enhanced backtest status."""

    async def test_get_status_requires_auth(self, client: AsyncClient):
        """Test that authentication is required."""
        resp = await client.get("/api/v1/backtest/task123/status")
        assert resp.status_code == 401  # Unauthorized for unauthenticated requests

    async def test_get_status_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test when task does not exist."""
        with patch("app.services.backtest_service.BacktestService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_task_status = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service

            resp = await client.get("/api/v1/backtest/nonexistent/status", headers=auth_headers)
            assert resp.status_code == 404

    async def test_get_status_success(
        self, client: AsyncClient, auth_headers: dict, clear_lru_cache
    ):
        """Test getting status."""
        mock_service = AsyncMock()
        mock_service.get_task_status = AsyncMock(return_value="completed")

        with patch("app.api.backtest.BacktestService", return_value=mock_service):
            resp = await client.get("/api/v1/backtest/task123/status", headers=auth_headers)
            assert resp.status_code == 200


@pytest.mark.asyncio
class TestEnhancedBacktestList:
    """Tests for enhanced backtest list."""

    async def test_list_requires_auth(self, client: AsyncClient):
        """Test that authentication is required."""
        resp = await client.get("/api/v1/backtest/")
        assert resp.status_code == 401  # Unauthorized for unauthenticated requests

    async def test_list_success(self, client: AsyncClient, auth_headers: dict):
        """Test successful listing."""
        with patch("app.services.backtest_service.BacktestService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.list_results = AsyncMock(
                return_value=MagicMock(
                    items=[],
                    total=0,
                )
            )
            mock_service_class.return_value = mock_service

            resp = await client.get("/api/v1/backtest/", headers=auth_headers)
            assert resp.status_code == 200

    async def test_list_with_sort(self, client: AsyncClient, auth_headers: dict):
        """Test sorting."""
        with patch("app.services.backtest_service.BacktestService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.list_results = AsyncMock(
                return_value=MagicMock(
                    items=[],
                    total=0,
                )
            )
            mock_service_class.return_value = mock_service

            resp = await client.get(
                "/api/v1/backtest/?sort_by=created_at&sort_order=desc", headers=auth_headers
            )
            assert resp.status_code == 200

    async def test_list_invalid_limit(self, client: AsyncClient, auth_headers: dict):
        """Test invalid limit."""
        resp = await client.get("/api/v1/backtest/?limit=200", headers=auth_headers)
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestEnhancedBacktestDelete:
    """Tests for enhanced backtest delete."""

    async def test_delete_requires_auth(self, client: AsyncClient):
        """Test that authentication is required."""
        resp = await client.delete("/api/v1/backtest/task123")
        assert resp.status_code == 401  # Unauthorized for unauthenticated requests

    async def test_delete_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test deleting non-existent task."""
        with patch("app.services.backtest_service.BacktestService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.delete_result = AsyncMock(return_value=False)
            mock_service_class.return_value = mock_service

            resp = await client.delete("/api/v1/backtest/nonexistent", headers=auth_headers)
            assert resp.status_code == 404

    async def test_delete_success(self, client: AsyncClient, auth_headers: dict, clear_lru_cache):
        """Test deletion."""
        mock_service = AsyncMock()
        mock_service.delete_result = AsyncMock(return_value=True)

        with patch("app.api.backtest.BacktestService", return_value=mock_service):
            resp = await client.delete("/api/v1/backtest/task123", headers=auth_headers)
            assert resp.status_code == 200


@pytest.mark.asyncio
class TestEnhancedBacktestCancel:
    """Tests for enhanced backtest cancel on /backtests."""

    async def test_cancel_requires_auth(self, client: AsyncClient):
        """Test that authentication is required."""
        resp = await client.post("/api/v1/backtests/task123/cancel")
        assert resp.status_code == 401  # Unauthorized for unauthenticated requests

    async def test_cancel_not_found(self, client: AsyncClient, auth_headers: dict, clear_lru_cache):
        """Test cancel failure on enhanced route."""
        mock_service = AsyncMock()
        mock_service.cancel_task = AsyncMock(return_value=False)

        with patch("app.api.backtest_enhanced.BacktestService", return_value=mock_service):
            resp = await client.post("/api/v1/backtests/nonexistent/cancel", headers=auth_headers)
            assert resp.status_code == 400

    async def test_cancel_success(self, client: AsyncClient, auth_headers: dict, clear_lru_cache):
        """Test cancel success on enhanced route."""
        mock_service = AsyncMock()
        mock_service.cancel_task = AsyncMock(return_value=True)

        with patch("app.api.backtest_enhanced.BacktestService", return_value=mock_service):
            resp = await client.post("/api/v1/backtests/task123/cancel", headers=auth_headers)
            assert resp.status_code == 200


@pytest.mark.asyncio
class TestGridSearchOptimization:
    """Tests for grid search optimization."""

    async def test_grid_search_requires_auth(self, client: AsyncClient):
        """Test that authentication is required."""
        resp = await client.post(
            "/api/v1/backtests/optimization/grid",
            json={
                "strategy_id": "strat1",
                "backtest_config": VALID_BACKTEST_REQUEST,
                "method": "grid",
                "param_grid": {"period": [10, 20, 30]},
            },
        )
        assert resp.status_code == 401  # Unauthorized for unauthenticated requests

    async def test_grid_search_wrong_method(self, client: AsyncClient, auth_headers: dict):
        """Test method mismatch - returns 422 because schema validation."""
        resp = await client.post(
            "/api/v1/backtests/optimization/grid",
            headers=auth_headers,
            json={
                "strategy_id": "strat1",
                "backtest_config": VALID_BACKTEST_REQUEST,
                "method": "bayesian",  # Wrong method
                "param_grid": {"period": [10, 20, 30]},
            },
        )
        # Schema validation returns 422, not 400
        assert resp.status_code == 422

    async def test_grid_search_success(
        self, client: AsyncClient, auth_headers: dict, clear_lru_cache
    ):
        """Test grid search."""
        with patch(
            "app.api.optimization_api.submit_backtest_optimization_task_internal",
            new=AsyncMock(
                return_value=MagicMock(
                    task_id="opt-task-1", total_combinations=3, message="submitted"
                )
            ),
        ):
            with patch(
                "app.api.backtest_enhanced._await_legacy_optimization_task_result",
                new=AsyncMock(
                    return_value={
                        "best_params": {"period": 20},
                        "best_metrics": {"sharpe_ratio": 1.5},
                        "all_results": [
                            {"params": {"period": 20}, "metrics": {"sharpe_ratio": 1.5}}
                        ],
                        "n_trials": 1,
                    }
                ),
            ):
                resp = await client.post(
                    "/api/v1/backtests/optimization/grid",
                    headers=auth_headers,
                    json={
                        "strategy_id": "strat1",
                        "backtest_config": VALID_BACKTEST_REQUEST,
                        "method": "grid",
                        "param_grid": {"period": [10, 20, 30]},
                    },
                )
        assert resp.status_code == 200
        assert resp.headers["Deprecation"] == "true"
        assert resp.headers["X-Deprecated-Endpoint"] == "/api/v1/optimization/submit/backtest"


@pytest.mark.asyncio
class TestBayesianOptimization:
    """Tests for Bayesian optimization."""

    async def test_bayesian_requires_auth(self, client: AsyncClient):
        """Test that authentication is required."""
        resp = await client.post(
            "/api/v1/backtests/optimization/bayesian",
            json={
                "strategy_id": "strat1",
                "backtest_config": VALID_BACKTEST_REQUEST,
                "method": "bayesian",
                "param_bounds": {"period": {"min": 5, "max": 50}},
            },
        )
        assert resp.status_code == 401  # Unauthorized for unauthenticated requests

    async def test_bayesian_wrong_method(self, client: AsyncClient, auth_headers: dict):
        """Test method mismatch - returns 422 because schema validation."""
        resp = await client.post(
            "/api/v1/backtests/optimization/bayesian",
            headers=auth_headers,
            json={
                "strategy_id": "strat1",
                "backtest_config": VALID_BACKTEST_REQUEST,
                "method": "grid",  # Wrong method
                "param_bounds": {"period": {"min": 5, "max": 50}},
            },
        )
        # Schema validation returns 422, not 400
        assert resp.status_code == 422

    async def test_bayesian_success(self, client: AsyncClient, auth_headers: dict, clear_lru_cache):
        """Test Bayesian optimization."""
        with patch(
            "app.api.optimization_api.submit_backtest_optimization_task_internal",
            new=AsyncMock(
                return_value=MagicMock(
                    task_id="opt-task-2", total_combinations=5, message="submitted"
                )
            ),
        ):
            with patch(
                "app.api.backtest_enhanced._await_legacy_optimization_task_result",
                new=AsyncMock(
                    return_value={
                        "best_params": {"period": 18},
                        "best_metrics": {"sharpe_ratio": 1.8},
                        "all_results": [
                            {"params": {"period": 18}, "metrics": {"sharpe_ratio": 1.8}}
                        ],
                        "n_trials": 1,
                    }
                ),
            ):
                resp = await client.post(
                    "/api/v1/backtests/optimization/bayesian",
                    headers=auth_headers,
                    json={
                        "strategy_id": "strat1",
                        "backtest_config": VALID_BACKTEST_REQUEST,
                        "method": "bayesian",
                        "param_bounds": {"period": {"min": 5, "max": 50}},
                    },
                )
        assert resp.status_code == 200
        assert resp.headers["Deprecation"] == "true"
        assert resp.headers["X-Deprecated-Endpoint"] == "/api/v1/optimization/submit/backtest"


@pytest.mark.asyncio
class TestReportExportHTML:
    """Tests for HTML report export."""

    async def test_html_report_requires_auth(self, client: AsyncClient):
        """Test that authentication is required."""
        resp = await client.get("/api/v1/backtests/task123/report/html")
        assert resp.status_code == 401  # Unauthorized for unauthenticated requests

    async def test_html_report_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test when task does not exist."""
        resp = await client.get("/api/v1/backtests/nonexistent/report/html", headers=auth_headers)
        assert resp.status_code == 404

    async def test_html_report_success(
        self, client: AsyncClient, auth_headers: dict, clear_lru_cache
    ):
        """Test HTML export (may return 404 or 500)."""
        mock_result = MagicMock()
        mock_result.strategy_id = "strat1"
        mock_result.model_dump = MagicMock(return_value={"task_id": "task123"})

        mock_backtest_service = AsyncMock()
        mock_backtest_service.get_result = AsyncMock(return_value=mock_result)

        mock_report_service = AsyncMock()
        mock_report_service.generate_html_report = AsyncMock(return_value="<html>Report</html>")

        with patch("app.api.backtest_enhanced.BacktestService", return_value=mock_backtest_service):
            with patch("app.api.backtest_enhanced.ReportService", return_value=mock_report_service):
                resp = await client.get(
                    "/api/v1/backtests/task123/report/html", headers=auth_headers
                )
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestReportExportPDF:
    """Tests for PDF report export."""

    async def test_pdf_report_requires_auth(self, client: AsyncClient):
        """Test that authentication is required."""
        resp = await client.get("/api/v1/backtests/task123/report/pdf")
        assert resp.status_code == 401  # Unauthorized for unauthenticated requests

    async def test_pdf_report_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test when task does not exist."""
        resp = await client.get("/api/v1/backtests/nonexistent/report/pdf", headers=auth_headers)
        assert resp.status_code == 404

    async def test_pdf_report_import_error(
        self, client: AsyncClient, auth_headers: dict, clear_lru_cache
    ):
        """Test PDF export (may return 500 because no weasyprint)."""
        mock_result = MagicMock()
        mock_result.strategy_id = "strat1"
        mock_result.model_dump = MagicMock(return_value={"task_id": "task123"})

        mock_backtest_service = AsyncMock()
        mock_backtest_service.get_result = AsyncMock(return_value=mock_result)

        mock_report_service = AsyncMock()
        mock_report_service.generate_pdf_report = AsyncMock(
            side_effect=ImportError("weasyprint not installed")
        )

        with patch("app.api.backtest_enhanced.BacktestService", return_value=mock_backtest_service):
            with patch("app.api.backtest_enhanced.ReportService", return_value=mock_report_service):
                resp = await client.get(
                    "/api/v1/backtests/task123/report/pdf", headers=auth_headers
                )
        assert resp.status_code == 500

    async def test_pdf_report_success(
        self, client: AsyncClient, auth_headers: dict, clear_lru_cache
    ):
        """Test PDF export (may return 404 or 500)."""
        mock_result = MagicMock()
        mock_result.strategy_id = "strat1"
        mock_result.model_dump = MagicMock(return_value={"task_id": "task123"})

        mock_backtest_service = AsyncMock()
        mock_backtest_service.get_result = AsyncMock(return_value=mock_result)

        mock_report_service = AsyncMock()
        mock_report_service.generate_pdf_report = AsyncMock(return_value=b"pdf")

        with patch("app.api.backtest_enhanced.BacktestService", return_value=mock_backtest_service):
            with patch("app.api.backtest_enhanced.ReportService", return_value=mock_report_service):
                resp = await client.get(
                    "/api/v1/backtests/task123/report/pdf", headers=auth_headers
                )
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestReportExportExcel:
    """Tests for Excel report export."""

    async def test_excel_report_requires_auth(self, client: AsyncClient):
        """Test that authentication is required."""
        resp = await client.get("/api/v1/backtests/task123/report/excel")
        assert resp.status_code == 401  # Unauthorized for unauthenticated requests

    async def test_excel_report_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test when task does not exist."""
        resp = await client.get("/api/v1/backtests/nonexistent/report/excel", headers=auth_headers)
        assert resp.status_code == 404

    async def test_excel_report_import_error(
        self, client: AsyncClient, auth_headers: dict, clear_lru_cache
    ):
        """Test Excel export (may return 500 because no openpyxl)."""
        mock_result = MagicMock()
        mock_result.strategy_id = "strat1"
        mock_result.model_dump = MagicMock(return_value={"task_id": "task123"})

        mock_backtest_service = AsyncMock()
        mock_backtest_service.get_result = AsyncMock(return_value=mock_result)

        mock_report_service = AsyncMock()
        mock_report_service.generate_excel_report = AsyncMock(
            side_effect=ImportError("openpyxl not installed")
        )

        with patch("app.api.backtest_enhanced.BacktestService", return_value=mock_backtest_service):
            with patch("app.api.backtest_enhanced.ReportService", return_value=mock_report_service):
                resp = await client.get(
                    "/api/v1/backtests/task123/report/excel", headers=auth_headers
                )
        assert resp.status_code == 500

    async def test_excel_report_success(
        self, client: AsyncClient, auth_headers: dict, clear_lru_cache
    ):
        """Test Excel export (may return 404 or 500)."""
        mock_result = MagicMock()
        mock_result.strategy_id = "strat1"
        mock_result.model_dump = MagicMock(return_value={"task_id": "task123"})

        mock_backtest_service = AsyncMock()
        mock_backtest_service.get_result = AsyncMock(return_value=mock_result)

        mock_report_service = AsyncMock()
        mock_report_service.generate_excel_report = AsyncMock(return_value=b"excel")

        with patch("app.api.backtest_enhanced.BacktestService", return_value=mock_backtest_service):
            with patch("app.api.backtest_enhanced.ReportService", return_value=mock_report_service):
                resp = await client.get(
                    "/api/v1/backtests/task123/report/excel", headers=auth_headers
                )
        assert resp.status_code == 200


class TestServiceSingletons:
    """Tests for service singletons."""

    def test_get_backtest_service_singleton(self):
        """Test BacktestService singleton."""
        from app.api.backtest_enhanced import get_backtest_service

        svc1 = get_backtest_service()
        svc2 = get_backtest_service()
        assert svc1 is svc2

    def test_get_report_service_singleton(self):
        """Test ReportService singleton."""
        from app.api.backtest_enhanced import get_report_service

        svc1 = get_report_service()
        svc2 = get_report_service()
        assert svc1 is svc2


@pytest.mark.asyncio
class TestWebSocketEndpoint:
    """Tests for WebSocket endpoint."""

    async def test_websocket_connection(self):
        """Test WebSocket connection."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.api.backtest_enhanced import websocket_endpoint
        from app.schemas.backtest_enhanced import TaskStatus

        # Create mock WebSocket object
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=[asyncio.TimeoutError()])

        # Mock WebSocket manager - both connect and disconnect need to be async
        with patch(
            "app.api.backtest_enhanced.get_websocket_current_user",
            return_value=(MagicMock(sub="user-1"), "access-token"),
        ):
            with patch("app.api.backtest_enhanced.ws_manager") as mock_mgr:
                mock_mgr.connect = AsyncMock()
                mock_mgr.disconnect = MagicMock()
                mock_mgr.send_to_task = AsyncMock()
                mock_mgr.get_connection_count = MagicMock(return_value=1)

                # Mock backtest service - return CANCELLED status to exit loop quickly
                with patch("app.api.backtest_enhanced.get_backtest_service") as mock_service:
                    mock_svc = AsyncMock()
                    mock_svc.get_task_status = AsyncMock(return_value=TaskStatus.CANCELLED)
                    mock_svc.get_result = AsyncMock(return_value=None)
                    mock_service.return_value = mock_svc

                    await websocket_endpoint(mock_ws, "task123")

                    client_id = mock_mgr.connect.await_args.args[2]
                    mock_mgr.connect.assert_awaited_once_with(
                        mock_ws, "task123", client_id, "access-token"
                    )
                    mock_mgr.send_to_task.assert_awaited_once_with(
                        "task123",
                        {
                            "type": "cancelled",
                            "task_id": "task123",
                            "status": TaskStatus.CANCELLED,
                            "message": "Task cancelled",
                        },
                    )
                    mock_mgr.disconnect.assert_called_once_with(mock_ws, "task123", client_id)

    async def test_websocket_sends_progress(self):
        """Test WebSocket sends progress."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.api.backtest_enhanced import websocket_endpoint
        from app.schemas.backtest_enhanced import BacktestResult, TaskStatus

        # Create mock WebSocket object
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.receive_text = AsyncMock(
            side_effect=[asyncio.TimeoutError(), asyncio.TimeoutError()]
        )

        # Create mock result
        mock_result = MagicMock(spec=BacktestResult)
        mock_result.model_dump = MagicMock(return_value={"status": "completed"})

        # Mock WebSocket manager
        with patch(
            "app.api.backtest_enhanced.get_websocket_current_user",
            return_value=(MagicMock(sub="user-1"), "access-token"),
        ):
            with patch("app.api.backtest_enhanced.ws_manager") as mock_mgr:
                mock_mgr.connect = AsyncMock()
                mock_mgr.disconnect = MagicMock()
                mock_mgr.send_to_task = AsyncMock()

                # Mock backtest service - return running first, then completed
                with patch("app.api.backtest_enhanced.get_backtest_service") as mock_service:
                    mock_svc = AsyncMock()
                    mock_svc.get_task_status = AsyncMock(
                        side_effect=[TaskStatus.RUNNING, TaskStatus.RUNNING, TaskStatus.COMPLETED]
                    )
                    mock_svc.get_result = AsyncMock(return_value=mock_result)
                    mock_service.return_value = mock_svc

                    await websocket_endpoint(mock_ws, "task123")

                    client_id = mock_mgr.connect.await_args.args[2]
                    mock_mgr.connect.assert_awaited_once_with(
                        mock_ws, "task123", client_id, "access-token"
                    )
                    assert mock_mgr.send_to_task.await_args_list[0].args == (
                        "task123",
                        {
                            "type": "progress",
                            "task_id": "task123",
                            "status": TaskStatus.RUNNING,
                            "progress": 0,
                            "message": "Backtest task is running",
                            "data": {},
                        },
                    )
                    assert mock_mgr.send_to_task.await_args_list[1].args == (
                        "task123",
                        {
                            "type": "completed",
                            "task_id": "task123",
                            "status": TaskStatus.COMPLETED,
                            "progress": 100,
                            "message": "Backtest completed",
                            "result": {"status": "completed"},
                        },
                    )

    async def test_websocket_handles_failure(self):
        """Test WebSocket handles failure status."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.api.backtest_enhanced import websocket_endpoint
        from app.schemas.backtest_enhanced import TaskStatus

        # Create mock WebSocket object
        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=[asyncio.TimeoutError()])

        # Create mock result
        mock_result = MagicMock()
        mock_result.error_message = "Test error"

        # Mock WebSocket manager
        with patch(
            "app.api.backtest_enhanced.get_websocket_current_user",
            return_value=(MagicMock(sub="user-1"), "access-token"),
        ):
            with patch("app.api.backtest_enhanced.ws_manager") as mock_mgr:
                mock_mgr.connect = AsyncMock()
                mock_mgr.disconnect = MagicMock()
                mock_mgr.send_to_task = AsyncMock()

                # Mock backtest service - return failed status
                with patch("app.api.backtest_enhanced.get_backtest_service") as mock_service:
                    mock_svc = AsyncMock()
                    mock_svc.get_task_status = AsyncMock(return_value=TaskStatus.FAILED)
                    mock_svc.get_result = AsyncMock(return_value=mock_result)
                    mock_service.return_value = mock_svc

                    await websocket_endpoint(mock_ws, "task123")

                    client_id = mock_mgr.connect.await_args.args[2]
                    mock_mgr.connect.assert_awaited_once_with(
                        mock_ws, "task123", client_id, "access-token"
                    )
                    mock_mgr.send_to_task.assert_awaited_once_with(
                        "task123",
                        {
                            "type": "failed",
                            "task_id": "task123",
                            "status": TaskStatus.FAILED,
                            "message": "Test error",
                            "error": "Test error",
                        },
                    )


@pytest.mark.asyncio
class TestBacktestListSorting:
    """Tests for backtest list sorting."""

    async def test_list_with_sharpe_sort(self, client: AsyncClient, auth_headers: dict):
        """Test sorting by Sharpe ratio."""
        with patch("app.services.backtest_service.BacktestService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.list_results = AsyncMock(
                return_value=MagicMock(
                    items=[],
                    total=0,
                )
            )
            mock_service_class.return_value = mock_service

            resp = await client.get(
                "/api/v1/backtest/?sort_by=sharpe_ratio&sort_order=desc", headers=auth_headers
            )
            assert resp.status_code == 200

    async def test_list_with_return_sort(self, client: AsyncClient, auth_headers: dict):
        """Test sorting by return rate."""
        with patch("app.services.backtest_service.BacktestService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.list_results = AsyncMock(
                return_value=MagicMock(
                    items=[],
                    total=0,
                )
            )
            mock_service_class.return_value = mock_service

            resp = await client.get(
                "/api/v1/backtest/?sort_by=total_return&sort_order=asc", headers=auth_headers
            )
            assert resp.status_code == 200

    async def test_list_with_pagination(self, client: AsyncClient, auth_headers: dict):
        """Test pagination."""
        with patch("app.services.backtest_service.BacktestService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.list_results = AsyncMock(
                return_value=MagicMock(
                    items=[],
                    total=0,
                )
            )
            mock_service_class.return_value = mock_service

            resp = await client.get("/api/v1/backtest/?limit=10&offset=20", headers=auth_headers)
            assert resp.status_code == 200


@pytest.mark.asyncio
class TestOptimizationMethodValidation:
    """Tests for optimization method validation - test method mismatch scenarios."""

    async def test_grid_search_with_wrong_method_raises_400(
        self, client: AsyncClient, auth_headers: dict, clear_lru_cache
    ):
        """Test grid search endpoint with bayesian method returns 400."""
        # Need to bypass schema validation to test API-level method check
        # Create request with wrong method
        wrong_method_request = {
            "strategy_id": "strat1",
            "backtest_config": VALID_BACKTEST_REQUEST,
            "method": "bayesian",  # Wrong for grid endpoint
            "param_grid": {"period": [10, 20, 30]},
        }

        # Will be intercepted at schema level, so returns 422
        # But if schema validation passes, API will check method and return 400
        resp = await client.post(
            "/api/v1/backtests/optimization/grid", headers=auth_headers, json=wrong_method_request
        )
        # Schema validation catches it first
        assert resp.status_code == 422

    async def test_bayesian_with_wrong_method_raises_400(
        self, client: AsyncClient, auth_headers: dict, clear_lru_cache
    ):
        """Test Bayesian endpoint with grid method returns 400."""
        wrong_method_request = {
            "strategy_id": "strat1",
            "backtest_config": VALID_BACKTEST_REQUEST,
            "method": "grid",  # Wrong for bayesian endpoint
            "param_bounds": {"period": {"min": 5, "max": 50}},
        }

        resp = await client.post(
            "/api/v1/backtests/optimization/bayesian",
            headers=auth_headers,
            json=wrong_method_request,
        )
        # Schema validation catches it first
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestReportGenerationWithMocks:
    """Tests for report generation - using correct mocks."""

    async def test_html_report_with_valid_task(
        self, client: AsyncClient, auth_headers: dict, clear_lru_cache
    ):
        """Test HTML report generation - task exists."""
        from app.schemas.backtest_enhanced import BacktestResult

        mock_result = MagicMock(spec=BacktestResult)
        mock_result.strategy_id = "strat1"
        mock_result.task_id = "task123"
        mock_result.model_dump = MagicMock(return_value={"task_id": "task123"})

        mock_backtest_service = AsyncMock()
        mock_backtest_service.get_result = AsyncMock(return_value=mock_result)

        mock_report_service = AsyncMock()
        mock_report_service.generate_html_report = AsyncMock(return_value="<html>Report</html>")

        with patch("app.api.backtest_enhanced.BacktestService", return_value=mock_backtest_service):
            with patch("app.api.backtest_enhanced.ReportService", return_value=mock_report_service):
                resp = await client.get(
                    "/api/v1/backtests/task123/report/html", headers=auth_headers
                )
                assert resp.status_code == 200

    async def test_html_report_passes_user_id(
        self,
        client: AsyncClient,
        auth_headers: dict,
        clear_lru_cache,
    ):
        """Ensure report endpoints enforce ownership checks via user_id."""
        from app.schemas.backtest_enhanced import BacktestResult

        me = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert me.status_code == 200
        user_id = me.json()["id"]

        mock_result = MagicMock(spec=BacktestResult)
        mock_result.strategy_id = "strat1"
        mock_result.task_id = "task123"
        mock_result.model_dump = MagicMock(return_value={"task_id": "task123"})

        mock_backtest_service = AsyncMock()
        mock_backtest_service.get_result = AsyncMock(return_value=mock_result)

        mock_report_service = AsyncMock()
        mock_report_service.generate_html_report = AsyncMock(return_value="<html>Report</html>")

        with patch("app.api.backtest_enhanced.BacktestService", return_value=mock_backtest_service):
            with patch("app.api.backtest_enhanced.ReportService", return_value=mock_report_service):
                resp = await client.get(
                    "/api/v1/backtests/task123/report/html", headers=auth_headers
                )
                assert resp.status_code == 200
                mock_backtest_service.get_result.assert_awaited_with("task123", user_id=user_id)

    async def test_pdf_report_with_import_error(
        self, client: AsyncClient, auth_headers: dict, clear_lru_cache
    ):
        """Test PDF report generation - ImportError handling."""
        from app.schemas.backtest_enhanced import BacktestResult

        mock_result = MagicMock(spec=BacktestResult)
        mock_result.strategy_id = "strat1"
        mock_result.task_id = "task123"
        mock_result.model_dump = MagicMock(return_value={"task_id": "task123"})

        mock_backtest_service = AsyncMock()
        mock_backtest_service.get_result = AsyncMock(return_value=mock_result)

        # Mock report_service to raise ImportError
        mock_report_service = AsyncMock()
        mock_report_service.generate_pdf_report = AsyncMock(
            side_effect=ImportError("weasyprint not installed")
        )

        with patch("app.api.backtest_enhanced.BacktestService", return_value=mock_backtest_service):
            with patch("app.api.backtest_enhanced.ReportService", return_value=mock_report_service):
                resp = await client.get(
                    "/api/v1/backtests/task123/report/pdf", headers=auth_headers
                )
                assert resp.status_code == 500

    async def test_excel_report_with_import_error(
        self, client: AsyncClient, auth_headers: dict, clear_lru_cache
    ):
        """Test Excel report generation - ImportError handling."""
        from app.schemas.backtest_enhanced import BacktestResult

        mock_result = MagicMock(spec=BacktestResult)
        mock_result.strategy_id = "strat1"
        mock_result.task_id = "task123"
        mock_result.model_dump = MagicMock(return_value={"task_id": "task123"})

        mock_backtest_service = AsyncMock()
        mock_backtest_service.get_result = AsyncMock(return_value=mock_result)

        # Mock report_service to raise ImportError
        mock_report_service = AsyncMock()
        mock_report_service.generate_excel_report = AsyncMock(
            side_effect=ImportError("openpyxl not installed")
        )

        with patch("app.api.backtest_enhanced.BacktestService", return_value=mock_backtest_service):
            with patch("app.api.backtest_enhanced.ReportService", return_value=mock_report_service):
                resp = await client.get(
                    "/api/v1/backtests/task123/report/excel", headers=auth_headers
                )
                assert resp.status_code == 500


@pytest.mark.asyncio
class TestWebSocketDisconnectHandling:
    """Tests for WebSocket disconnect handling."""

    async def test_websocket_disconnect_gracefully(self, clear_lru_cache):
        """Test WebSocket graceful disconnect."""
        from starlette.websockets import WebSocketDisconnect

        from app.api.backtest_enhanced import websocket_endpoint
        from app.schemas.backtest_enhanced import TaskStatus

        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())

        with patch(
            "app.api.backtest_enhanced.get_websocket_current_user",
            return_value=(MagicMock(sub="user-1"), "access-token"),
        ):
            with patch("app.api.backtest_enhanced.ws_manager") as mock_mgr:
                mock_mgr.connect = AsyncMock()
                mock_mgr.disconnect = MagicMock()
                mock_mgr.send_to_task = AsyncMock()

                with patch("app.api.backtest_enhanced.get_backtest_service") as mock_service:
                    mock_svc = AsyncMock()
                    mock_svc.get_task_status = AsyncMock(return_value=TaskStatus.RUNNING)
                    mock_svc.get_result = AsyncMock(return_value=None)
                    mock_service.return_value = mock_svc

                    await websocket_endpoint(mock_ws, "task123")

                    client_id = mock_mgr.connect.await_args.args[2]
                    mock_mgr.connect.assert_awaited_once_with(
                        mock_ws, "task123", client_id, "access-token"
                    )
                    mock_mgr.disconnect.assert_called_once_with(mock_ws, "task123", client_id)

    async def test_websocket_exception_handling(self, clear_lru_cache):
        """Test WebSocket exception handling."""
        from app.api.backtest_enhanced import websocket_endpoint
        from app.schemas.backtest_enhanced import TaskStatus

        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=Exception("Connection error"))

        with patch(
            "app.api.backtest_enhanced.get_websocket_current_user",
            return_value=(MagicMock(sub="user-1"), "access-token"),
        ):
            with patch("app.api.backtest_enhanced.ws_manager") as mock_mgr:
                mock_mgr.connect = AsyncMock()
                mock_mgr.disconnect = MagicMock()
                mock_mgr.send_to_task = AsyncMock()

                with patch("app.api.backtest_enhanced.get_backtest_service") as mock_service:
                    mock_svc = AsyncMock()
                    mock_svc.get_task_status = AsyncMock(return_value=TaskStatus.RUNNING)
                    mock_svc.get_result = AsyncMock(return_value=None)
                    mock_service.return_value = mock_svc

                    await websocket_endpoint(mock_ws, "task123")

                    client_id = mock_mgr.connect.await_args.args[2]
                    mock_mgr.connect.assert_awaited_once_with(
                        mock_ws, "task123", client_id, "access-token"
                    )
                    mock_mgr.disconnect.assert_called_once_with(mock_ws, "task123", client_id)


@pytest.mark.asyncio
class TestBacktestGetResultWithUserCheck:
    """Tests for user check when getting results."""

    async def test_get_result_with_user_id_param(
        self, client: AsyncClient, auth_headers: dict, clear_lru_cache
    ):
        """Test getting result passes user_id parameter."""
        me = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert me.status_code == 200
        user_id = me.json()["id"]

        mock_service = AsyncMock()
        mock_service.get_result = AsyncMock(
            return_value={
                "task_id": "task123",
                "strategy_id": "strat1",
                "symbol": "000001.SZ",
                "start_date": "2023-01-01T00:00:00Z",
                "end_date": "2023-06-30T00:00:00Z",
                "status": "completed",
                "total_return": 10.0,
                "annual_return": 10.0,
                "sharpe_ratio": 1.2,
                "max_drawdown": 5.0,
                "win_rate": 50.0,
                "total_trades": 2,
                "profitable_trades": 1,
                "losing_trades": 1,
                "equity_curve": [100000.0],
                "equity_dates": ["2023-01-01"],
                "drawdown_curve": [0.0],
                "trades": [],
                "created_at": "2023-07-01T00:00:00Z",
                "error_message": None,
            }
        )

        with patch("app.api.backtest.BacktestService", return_value=mock_service):
            resp = await client.get("/api/v1/backtest/task123", headers=auth_headers)
            assert resp.status_code == 200
            mock_service.get_result.assert_awaited_with("task123", user_id=user_id)


@pytest.mark.asyncio
class TestEnhancedBacktestListSortOrder:
    """Tests for enhanced backtest list sort_order mapping to bool."""

    async def test_list_sort_order_asc_maps_to_false(
        self,
        client: AsyncClient,
        auth_headers: dict,
        clear_lru_cache,
    ):
        mock_service = AsyncMock()
        mock_service.list_results = AsyncMock(return_value=MagicMock(items=[], total=0))

        with patch("app.api.backtest_enhanced.BacktestService", return_value=mock_service):
            resp = await client.get("/api/v1/backtests/?sort_order=asc", headers=auth_headers)
            assert resp.status_code == 200
            # args: (user_id, limit, offset, sort_by, sort_desc)
            assert mock_service.list_results.await_args.args[-1] is False
