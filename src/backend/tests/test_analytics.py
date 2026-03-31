"""Analytics service API tests.

Tests:
- GET /api/v1/analytics/{task_id}/detail - Get backtest details
- GET /api/v1/analytics/{task_id}/kline - Get K-line data
- GET /api/v1/analytics/{task_id}/monthly-returns - Get monthly returns
- GET /api/v1/analytics/{task_id}/export - Export backtest results
- GET /api/v1/analytics/{task_id}/optimization - Get optimization results
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestAnalyticsDetailEndpoint:
    """Tests for backtest detail endpoint."""

    async def test_get_backtest_detail_requires_auth(self, client: AsyncClient):
        """Test that authentication is required.

        Args:
            client: Async HTTP client.

        Returns:
            None
        """
        resp = await client.get("/api/v1/analytics/task-123/detail")
        assert resp.status_code == 401  # Unauthorized for unauthenticated requests

    async def test_get_backtest_detail_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test getting a non-existent task.

        Args:
            client: Async HTTP client.
            auth_headers: Authentication headers.

        Returns:
            None
        """
        with patch("app.api.analytics.get_backtest_data", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            resp = await client.get(
                "/api/v1/analytics/nonexistent-task-id/detail", headers=auth_headers
            )
        assert resp.status_code == 404

    async def test_get_backtest_detail_success(self, client: AsyncClient, auth_headers: dict):
        """Test successfully getting backtest details.

        Args:
            client: Async HTTP client.
            auth_headers: Authentication headers.

        Returns:
            None
        """
        with patch("app.api.analytics.get_backtest_data", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "task_id": "task-123",
                "strategy_name": "test_strategy",
                "symbol": "000001.SZ",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "equity_curve": [{"date": "2024-01-01", "total_assets": 100000.0, "cash": 30000.0, "position_value": 70000.0}],
                "drawdown_curve": [{"date": "2024-01-01", "drawdown": 0.0, "peak": 100000.0, "trough": 100000.0}],
                "trades": [{"id": 1, "datetime": "2024-01-01 10:00:00", "symbol": "000001.SZ", "direction": "buy", "price": 10.0, "size": 100, "value": 1000.0, "commission": 1.0, "pnl": 10.0, "cumulative_pnl": 10.0}],
                "created_at": "2024-01-01",
            }
            with patch("app.services.analytics_service.AnalyticsService.calculate_metrics") as mock_metrics:
                mock_metrics.return_value = {
                    "initial_capital": 100000.0,
                    "final_assets": 101000.0,
                    "total_return": 0.01,
                    "annualized_return": 0.01,
                    "max_drawdown": 0.0,
                    "max_drawdown_duration": 0,
                    "sharpe_ratio": 1.0,
                    "sortino_ratio": 1.0,
                    "calmar_ratio": 1.0,
                    "win_rate": 1.0,
                    "profit_factor": 2.0,
                    "trade_count": 1,
                    "avg_trade_return": 0.01,
                    "avg_holding_days": 1.0,
                    "avg_win": 10.0,
                    "avg_loss": 0.0,
                    "max_consecutive_wins": 1,
                    "max_consecutive_losses": 0,
                }
                with patch("app.services.analytics_service.AnalyticsService.process_equity_curve") as mock_equity:
                    mock_equity.return_value = [{"date": "2024-01-01", "total_assets": 100000.0, "cash": 30000.0, "position_value": 70000.0}]
                    with patch("app.services.analytics_service.AnalyticsService.process_drawdown_curve") as mock_drawdown:
                        mock_drawdown.return_value = [{"date": "2024-01-01", "drawdown": 0.0, "peak": 100000.0, "trough": 100000.0}]
                        with patch("app.services.analytics_service.AnalyticsService.process_trades") as mock_trades:
                            mock_trades.return_value = [{"id": 1, "datetime": "2024-01-01 10:00:00", "symbol": "000001.SZ", "direction": "buy", "price": 10.0, "size": 100, "value": 1000.0, "commission": 1.0, "pnl": 10.0, "cumulative_pnl": 10.0}]
                            resp = await client.get(
                                "/api/v1/analytics/task-123/detail", headers=auth_headers
                            )
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestAnalyticsKlineEndpoint:
    """Tests for K-line data endpoint."""

    async def test_get_kline_requires_auth(self, client: AsyncClient):
        """Test that authentication is required.

        Args:
            client: Async HTTP client.

        Returns:
            None
        """
        resp = await client.get("/api/v1/analytics/task-123/kline")
        assert resp.status_code == 401  # Unauthorized for unauthenticated requests

    async def test_get_kline_with_date_filters(self, client: AsyncClient, auth_headers: dict):
        """Test K-line endpoint with date filters.

        Args:
            client: Async HTTP client.
            auth_headers: Authentication headers.

        Returns:
            None
        """
        with patch("app.api.analytics.get_backtest_data", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "symbol": "000001.SZ",
                "klines": [{"date": "2024-01-01", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.3, "volume": 1000000}],
                "signals": [{"date": "2024-01-01", "type": "buy", "price": 10.3, "size": 100}],
                "log_indicators": {"ma5": [10.3]},
            }
            with patch("app.services.analytics_service.AnalyticsService.process_signals") as mock_signals:
                mock_signals.return_value = [{"date": "2024-01-01", "type": "buy", "price": 10.3, "size": 100}]
                resp = await client.get(
                    "/api/v1/analytics/task-123/kline",
                    headers=auth_headers,
                    params={"start_date": "2024-01-01", "end_date": "2024-12-31"},
                )
        assert resp.status_code == 200

    async def test_get_kline_with_only_start_date(self, client: AsyncClient, auth_headers: dict):
        """Test K-line endpoint with only start date.

        Args:
            client: Async HTTP client.
            auth_headers: Authentication headers.

        Returns:
            None
        """
        with patch("app.api.analytics.get_backtest_data", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "symbol": "000001.SZ",
                "klines": [{"date": "2024-01-02", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.3, "volume": 1000000}],
                "signals": [{"date": "2024-01-02", "type": "buy", "price": 10.3, "size": 100}],
                "log_indicators": {"ma5": [10.3]},
            }
            with patch("app.services.analytics_service.AnalyticsService.process_signals") as mock_signals:
                mock_signals.return_value = [{"date": "2024-01-02", "type": "buy", "price": 10.3, "size": 100}]
                resp = await client.get(
                    "/api/v1/analytics/task-123/kline",
                    headers=auth_headers,
                    params={"start_date": "2024-01-01"},
                )
        assert resp.status_code == 200

    async def test_get_kline_with_only_end_date(self, client: AsyncClient, auth_headers: dict):
        """Test K-line endpoint with only end date.

        Args:
            client: Async HTTP client.
            auth_headers: Authentication headers.

        Returns:
            None
        """
        with patch("app.api.analytics.get_backtest_data", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "symbol": "000001.SZ",
                "klines": [{"date": "2024-01-02", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.3, "volume": 1000000}],
                "signals": [{"date": "2024-01-02", "type": "buy", "price": 10.3, "size": 100}],
                "log_indicators": {"ma5": [10.3]},
            }
            with patch("app.services.analytics_service.AnalyticsService.process_signals") as mock_signals:
                mock_signals.return_value = [{"date": "2024-01-02", "type": "buy", "price": 10.3, "size": 100}]
                resp = await client.get(
                    "/api/v1/analytics/task-123/kline",
                    headers=auth_headers,
                    params={"end_date": "2024-12-31"},
                )
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestAnalyticsMonthlyReturnsEndpoint:
    """Tests for monthly returns endpoint."""

    async def test_get_monthly_returns_requires_auth(self, client: AsyncClient):
        """Test that authentication is required.

        Args:
            client: Async HTTP client.

        Returns:
            None
        """
        resp = await client.get("/api/v1/analytics/task-123/monthly-returns")
        assert resp.status_code == 401  # Unauthorized for unauthenticated requests

    async def test_get_monthly_returns_not_found(self, client: AsyncClient, auth_headers: dict):
        """Test getting monthly returns for non-existent task.

        Args:
            client: Async HTTP client.
            auth_headers: Authentication headers.

        Returns:
            None
        """
        with patch("app.api.analytics.get_backtest_data", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            resp = await client.get(
                "/api/v1/analytics/nonexistent/monthly-returns", headers=auth_headers
            )
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestAnalyticsExportEndpoint:
    """Tests for export endpoint."""

    async def test_export_requires_auth(self, client: AsyncClient):
        """Test that authentication is required.

        Args:
            client: Async HTTP client.

        Returns:
            None
        """
        resp = await client.get("/api/v1/analytics/task-123/export")
        assert resp.status_code == 401  # Unauthorized for unauthenticated requests

    async def test_export_default_format(self, client: AsyncClient, auth_headers: dict):
        """Test export with default format.

        Args:
            client: Async HTTP client.
            auth_headers: Authentication headers.

        Returns:
            None
        """
        with patch("app.api.analytics.get_backtest_data", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "task_id": "task-123",
                "strategy_name": "test_strategy",
                "symbol": "000001.SZ",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "trades": [],
                "equity_curve": [],
                "drawdown_curve": [],
                "monthly_returns": {},
                "created_at": "2024-01-01",
            }
            resp = await client.get("/api/v1/analytics/task-123/export", headers=auth_headers)
        assert resp.status_code == 200

    async def test_export_csv_format(self, client: AsyncClient, auth_headers: dict):
        """Test export with CSV format.

        Args:
            client: Async HTTP client.
            auth_headers: Authentication headers.

        Returns:
            None
        """
        with patch("app.api.analytics.get_backtest_data", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "task_id": "task-123",
                "strategy_name": "test_strategy",
                "symbol": "000001.SZ",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "trades": [],
                "equity_curve": [],
                "drawdown_curve": [],
                "monthly_returns": {},
                "created_at": "2024-01-01",
            }
            resp = await client.get(
                "/api/v1/analytics/task-123/export", headers=auth_headers, params={"format": "csv"}
            )
        assert resp.status_code == 200

    async def test_export_json_format(self, client: AsyncClient, auth_headers: dict):
        """Test export with JSON format.

        Args:
            client: Async HTTP client.
            auth_headers: Authentication headers.

        Returns:
            None
        """
        with patch("app.api.analytics.get_backtest_data", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "task_id": "task-123",
                "strategy_name": "test_strategy",
                "symbol": "000001.SZ",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "trades": [],
                "equity_curve": [],
                "drawdown_curve": [],
                "monthly_returns": {},
                "created_at": "2024-01-01",
            }
            resp = await client.get(
                "/api/v1/analytics/task-123/export", headers=auth_headers, params={"format": "json"}
            )
        assert resp.status_code == 200

    async def test_export_unsupported_format(self, client: AsyncClient, auth_headers: dict):
        """Test export with unsupported format.

        Args:
            client: Async HTTP client.
            auth_headers: Authentication headers.

        Returns:
            None
        """
        with patch("app.api.analytics.get_backtest_data", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "task_id": "task-123",
                "strategy_name": "test_strategy",
                "symbol": "000001.SZ",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "trades": [],
                "equity_curve": [],
                "drawdown_curve": [],
                "monthly_returns": {},
                "created_at": "2024-01-01",
            }
            resp = await client.get(
                "/api/v1/analytics/task-123/export",
                headers=auth_headers,
                params={"format": "xml"},
            )
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestAnalyticsOptimizationEndpoint:
    """Tests for optimization result endpoint."""

    async def test_get_optimization_requires_auth(self, client: AsyncClient):
        """Test that authentication is required.

        Args:
            client: Async HTTP client.

        Returns:
            None
        """
        resp = await client.get("/api/v1/analytics/task-123/optimization")
        assert resp.status_code == 401  # Unauthorized for unauthenticated requests

    async def test_get_optimization_not_available(self, client: AsyncClient, auth_headers: dict):
        """Test when optimization results are not available.

        Args:
            client: Async HTTP client.
            auth_headers: Authentication headers.

        Returns:
            None
        """
        resp = await client.get("/api/v1/analytics/task-123/optimization", headers=auth_headers)
        # This endpoint always returns 404
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestAnalyticsHelperFunctions:
    """Tests for helper functions."""

    async def test_resolve_log_dir_from_db(self):
        """Test resolving log directory from database.

        Returns:
            None
        """
        from app.api.analytics import _resolve_log_dir

        mock_task = Mock()
        mock_task.log_dir = "/path/to/logs"

        with patch("app.api.analytics.SQLRepository") as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_task)
            MockRepo.return_value = mock_repo_instance

            result = await _resolve_log_dir("task-123", "test_strategy")
            assert result is None

    async def test_resolve_log_dir_fallback(self):
        """Test fallback to latest directory.

        Returns:
            None
        """
        from app.api.analytics import _resolve_log_dir

        with patch("app.api.analytics.SQLRepository") as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_id = AsyncMock(return_value=None)
            MockRepo.return_value = mock_repo_instance

            with patch("app.api.analytics.find_latest_log_dir") as mock_find:
                mock_find.return_value = None  # None means no directory

                result = await _resolve_log_dir("task-123", "test_strategy")
                assert result is None
                mock_find.assert_called_once()


@pytest.mark.asyncio
class TestGetBacktestData:
    """Tests for get_backtest_data function."""

    async def test_get_backtest_data_with_empty_result(self):
        """Test with empty result.

        Returns:
            None
        """
        from app.api.analytics import get_backtest_data

        mock_service = AsyncMock()
        mock_service.get_result = AsyncMock(return_value=None)

        result = await get_backtest_data("task-123", mock_service)
        assert result is None

    async def test_get_backtest_data_structure(self):
        """Test return data structure.

        Returns:
            None
        """
        from app.api.analytics import get_backtest_data

        mock_result = Mock()
        mock_result.strategy_id = "SMACross"
        mock_result.symbol = "BTC/USDT"
        mock_result.start_date = "2024-01-01"
        mock_result.end_date = "2024-12-31"
        mock_result.created_at = "2024-01-01"
        mock_result.equity_curve = [100000, 105000]
        mock_result.equity_dates = ["2024-01-01", "2024-01-02"]
        mock_result.drawdown_curve = [0, -0.02]
        mock_result.trades = []
        mock_result.log_dir = None

        mock_service = AsyncMock()
        mock_service.get_result = AsyncMock(return_value=mock_result)

        with patch("app.api.analytics._resolve_log_dir", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = None

            result = await get_backtest_data("task-123", mock_service)

            assert result is not None
            assert result["task_id"] == "task-123"
            assert result["strategy_name"] == "SMACross"
            assert result["symbol"] == "BTC/USDT"

    async def test_get_backtest_data_with_cash_curve(self):
        """Test getting cash curve from logs.

        Returns:
            None
        """
        from app.api.analytics import get_backtest_data

        mock_result = Mock()
        mock_result.strategy_id = "test_strategy"
        mock_result.symbol = "000001.SZ"
        mock_result.start_date = "2024-01-01"
        mock_result.end_date = "2024-12-31"
        mock_result.created_at = "2024-01-01"
        mock_result.equity_curve = [100000, 101000]
        mock_result.equity_dates = ["2024-01-01", "2024-01-02"]
        mock_result.drawdown_curve = [0, -0.02]
        mock_result.trades = []

        mock_service = AsyncMock()
        mock_service.get_result = AsyncMock(return_value=mock_result)

        # Mock log dir with cash data
        mock_log_dir = Path("/tmp/logs")
        with patch("app.api.analytics._resolve_log_dir", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = mock_log_dir

            with patch("app.api.analytics.parse_value_log") as mock_parse:
                mock_parse.return_value = {
                    "dates": ["2024-01-01", "2024-01-02"],
                    "cash_curve": [30000, 30500],
                }

                result = await get_backtest_data("task-123", mock_service)
                assert result is not None
                assert "equity_curve" in result
                assert len(result["equity_curve"]) == 2

    async def test_get_backtest_data_with_trades(self):
        """Test data with trade records.

        Returns:
            None
        """
        from app.api.analytics import get_backtest_data

        mock_trade = Mock()
        mock_trade.model_dump.return_value = {
            "datetime": "2024-01-01T10:00:00",
            "dtopen": "2024-01-01T09:30:00",
            "dtclose": "2024-01-01T15:00:00",
            "direction": "buy",
            "price": 10.0,
            "size": 100,
            "value": 1000,
            "commission": 1.0,
            "pnlcomm": 50.0,
            "barlen": 1,
        }

        mock_result = Mock()
        mock_result.strategy_id = "test_strategy"
        mock_result.symbol = "000001.SZ"
        mock_result.start_date = "2024-01-01"
        mock_result.end_date = "2024-12-31"
        mock_result.created_at = "2024-01-01"
        mock_result.equity_curve = [100000]
        mock_result.equity_dates = ["2024-01-01"]
        mock_result.drawdown_curve = [0]
        mock_result.trades = [mock_trade]
        mock_result.log_dir = None

        mock_service = AsyncMock()
        mock_service.get_result = AsyncMock(return_value=mock_result)

        with patch("app.api.analytics._resolve_log_dir", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = None

            result = await get_backtest_data("task-123", mock_service)
            assert result is not None
            assert "trades" in result
            assert len(result["trades"]) == 1


@pytest.mark.asyncio
class TestAnalyticsServiceSingletons:
    """Tests for service singletons."""

    async def test_analytics_service_singleton(self):
        """Test AnalyticsService singleton.

        Returns:
            None
        """
        from app.api.analytics import get_analytics_service

        svc1 = get_analytics_service()
        svc2 = get_analytics_service()
        assert svc1 is svc2  # lru_cache should return same instance

    async def test_backtest_service_singleton(self):
        """Test BacktestService singleton.

        Returns:
            None
        """
        from app.api.analytics import get_backtest_service

        svc1 = get_backtest_service()
        svc2 = get_backtest_service()
        assert svc1 is svc2  # lru_cache should return same instance


@pytest.mark.asyncio
class TestGetBacktestDataExtended:
    """Extended tests for get_backtest_data function."""

    async def test_resolve_log_dir_success_from_db(self):
        """Test successfully resolving log directory from database.

        Returns:
            None
        """
        from pathlib import Path

        from app.api.analytics import _resolve_log_dir

        mock_task = MagicMock()
        mock_task.log_dir = "/tmp/test_logs"

        with patch("app.api.analytics.SQLRepository") as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_task)
            MockRepo.return_value = mock_repo_instance

            with patch("pathlib.Path.is_dir", return_value=True):
                result = await _resolve_log_dir("task-123", "test_strategy")
                assert result == Path("/tmp/test_logs")

    async def test_get_backtest_data_with_klines_from_log(self):
        """Test getting K-line data from logs.

        Returns:
            None
        """
        from pathlib import Path

        from app.api.analytics import get_backtest_data

        mock_result = Mock()
        mock_result.strategy_id = "test_strategy"
        mock_result.symbol = "000001.SZ"
        mock_result.start_date = "2024-01-01"
        mock_result.end_date = "2024-12-31"
        mock_result.created_at = "2024-01-01"
        mock_result.equity_curve = [100000, 101000]
        mock_result.equity_dates = ["2024-01-01", "2024-01-02"]
        mock_result.drawdown_curve = [0, -0.01]
        mock_result.trades = []

        mock_service = AsyncMock()
        mock_service.get_result = AsyncMock(return_value=mock_result)

        mock_log_dir = Path("/tmp/logs")

        with patch("app.api.analytics._resolve_log_dir", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = mock_log_dir

            # Mock parse_data_log to return kline data
            with patch("app.api.analytics.parse_data_log") as mock_parse_data:
                mock_parse_data.return_value = {
                    "dates": ["2024-01-01", "2024-01-02"],
                    "ohlc": [[10.0, 10.3, 9.8, 10.5], [10.3, 10.8, 10.0, 10.6]],
                    "volumes": [1000000, 1200000],
                    "indicators": {"ma5": [10.1, 10.4], "ma10": [10.2, 10.3]},
                }

                with patch("app.api.analytics.parse_value_log", return_value={}):
                    result = await get_backtest_data("task-123", mock_service)

                    assert result is not None
                    assert "klines" in result
                    assert len(result["klines"]) == 2
                    assert result["klines"][0]["open"] == 10.0
                    assert result["klines"][0]["close"] == 10.3
                    assert result["klines"][0]["high"] == 10.5
                    assert result["klines"][0]["low"] == 9.8
                    assert "log_indicators" in result

    async def test_get_backtest_data_with_parse_exception(self):
        """Test K-line data parsing exception handling.

        Returns:
            None
        """
        from app.api.analytics import get_backtest_data

        mock_result = Mock()
        mock_result.strategy_id = "test_strategy"
        mock_result.symbol = "000001.SZ"
        mock_result.start_date = "2024-01-01"
        mock_result.end_date = "2024-12-31"
        mock_result.created_at = "2024-01-01"
        mock_result.equity_curve = [100000]
        mock_result.equity_dates = ["2024-01-01"]
        mock_result.drawdown_curve = [0]
        mock_result.trades = []

        mock_service = AsyncMock()
        mock_service.get_result = AsyncMock(return_value=mock_result)

        with patch("app.api.analytics._resolve_log_dir", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = Path("/tmp/logs")

            # Mock parse_data_log to raise exception
            with patch("app.api.analytics.parse_data_log", side_effect=Exception("Parse error")):
                with patch("app.api.analytics.parse_value_log", return_value={}):
                    result = await get_backtest_data("task-123", mock_service)

                    # Should handle exception gracefully - klines will be computed from service
                    assert result is not None
                    assert "klines" in result
                    # log_indicators should be empty due to exception
                    assert result.get("log_indicators") == {}


@pytest.mark.asyncio
class TestAnalyticsKlineWithFilters:
    """Tests for K-line data with filters and indicators."""

    async def test_get_kline_with_date_filters_and_signals(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test date filtering and signal filtering.

        Args:
            client: Async HTTP client.
            auth_headers: Authentication headers.

        Returns:
            None
        """
        with patch("app.api.analytics.get_backtest_data", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "symbol": "000001.SZ",
                "klines": [{"date": "2024-01-01", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.3, "volume": 1000000}],
                "signals": [{"date": "2024-01-01", "type": "buy", "price": 10.3, "size": 100}],
                "log_indicators": {"ma5": [10.3]},
            }
            with patch("app.services.analytics_service.AnalyticsService.process_signals") as mock_signals:
                mock_signals.return_value = [{"date": "2024-01-01", "type": "buy", "price": 10.3, "size": 100}]
                resp = await client.get(
                    "/api/v1/analytics/task-123/kline",
                    headers=auth_headers,
                    params={"start_date": "2024-01-01", "end_date": "2024-12-31"},
                )
        assert resp.status_code == 200

    async def test_get_kline_returns_indicators_from_log(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test returning indicators from logs.

        Args:
            client: Async HTTP client.
            auth_headers: Authentication headers.

        Returns:
            None
        """
        with patch("app.api.analytics.get_backtest_data", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "symbol": "000001.SZ",
                "klines": [{"date": "2024-01-01", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.3, "volume": 1000000}],
                "signals": [{"date": "2024-01-01", "type": "buy", "price": 10.3, "size": 100}],
                "log_indicators": {"ma5": [10.3], "ma10": [10.2]},
            }
            with patch("app.services.analytics_service.AnalyticsService.process_signals") as mock_signals:
                mock_signals.return_value = [{"date": "2024-01-01", "type": "buy", "price": 10.3, "size": 100}]
                resp = await client.get("/api/v1/analytics/task-123/kline", headers=auth_headers)
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestAnalyticsExportWithData:
    """Tests for export functionality with data."""

    async def test_export_with_trades_data(self):
        """Test CSV export with trade data.

        Returns:
            None
        """

        from app.api.analytics import export_backtest_results

        mock_result = {
            "task_id": "task-123",
            "strategy_name": "test_strategy",
            "symbol": "000001.SZ",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "trades": [{"date": "2024-01-01", "direction": "buy", "price": 10.0, "size": 100}],
            "equity_curve": [],
            "drawdown_curve": [],
            "monthly_returns": {},
            "created_at": "2024-01-01",
        }

        with patch("app.api.analytics.get_backtest_data", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_result

            # Mock current_user
            mock_user = Mock()
            mock_user.username = "test_user"

            # Mock services
            with patch("app.api.analytics.get_analytics_service"):
                with patch("app.api.analytics.get_backtest_service"):
                    result = await export_backtest_results(
                        task_id="task-123",
                        format="csv",
                        current_user=mock_user,
                        service=Mock(),
                        backtest_service=AsyncMock(),
                    )

                    # Should return StreamingResponse
                    assert result is not None
                    assert hasattr(result, "body_iterator")

    async def test_export_json_format_with_data(self):
        """Test JSON format export with data.

        Returns:
            None
        """
        from app.api.analytics import export_backtest_results

        mock_result = {
            "task_id": "task-123",
            "strategy_name": "test_strategy",
            "symbol": "000001.SZ",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "trades": [],
            "equity_curve": [],
            "drawdown_curve": [],
            "monthly_returns": {},
            "created_at": "2024-01-01",
        }

        with patch("app.api.analytics.get_backtest_data", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_result

            mock_user = Mock()
            mock_user.username = "test_user"

            with patch("app.api.analytics.get_analytics_service"):
                with patch("app.api.analytics.get_backtest_service"):
                    result = await export_backtest_results(
                        task_id="task-123",
                        format="json",
                        current_user=mock_user,
                        service=Mock(),
                        backtest_service=AsyncMock(),
                    )

                    assert result is not None
                    assert hasattr(result, "body_iterator")


@pytest.mark.asyncio
class TestAnalyticsMonthlyReturnsWithData:
    """Tests for monthly returns handling."""

    async def test_monthly_returns_exception_in_calculation(self):
        """Test exception handling in monthly returns calculation.

        Returns:
            None
        """
        from app.api.analytics import get_backtest_data

        # Mock result with invalid date to trigger exception
        mock_result = Mock()
        mock_result.strategy_id = "test_strategy"
        mock_result.symbol = "000001.SZ"
        mock_result.start_date = "2024-01-01"
        mock_result.end_date = "2024-12-31"
        mock_result.created_at = "2024-01-01"
        mock_result.equity_curve = [100000, 101000]
        # Use invalid date to trigger exception in datetime parsing
        mock_result.equity_dates = ["invalid-date", "2024-01-02"]
        mock_result.drawdown_curve = [0, -0.01]
        mock_result.trades = []
        mock_result.log_dir = None

        mock_service = AsyncMock()
        mock_service.get_result = AsyncMock(return_value=mock_result)

        with patch("app.api.analytics._resolve_log_dir", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = None

            result = await get_backtest_data("task-123", mock_service)

            # Should handle invalid date gracefully
            assert result is not None
            assert "monthly_returns" in result
