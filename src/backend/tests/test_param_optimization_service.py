"""
Parameter Optimization Service Tests.

Tests:
- OptimizationService class
- run_grid_search method
- run_bayesian_optimization method
- _generate_param_combinations method
- _get_optimization_metric method
- _wait_for_backtest method
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from datetime import datetime

from app.services.optimization_service import OptimizationService


class TestOptimizationService:
    """Tests for OptimizationService class."""

    def test_initialization(self):
        """Test initialization."""
        service = OptimizationService()

        assert service.backtest_service is not None
        assert service.task_repo is not None
        assert service.cache is not None


class TestGenerateParamCombinations:
    """Tests for parameter combination generation."""

    def test_single_param(self):
        """Test single parameter combinations."""
        service = OptimizationService()

        param_grid = {
            'fast': [5, 10, 15]
        }

        combinations = service._generate_param_combinations(param_grid)

        assert len(combinations) == 3
        assert combinations[0] == {'fast': 5}
        assert combinations[1] == {'fast': 10}
        assert combinations[2] == {'fast': 15}

    def test_multiple_params(self):
        """Test multiple parameter combinations (Cartesian product)."""
        service = OptimizationService()

        param_grid = {
            'fast': [5, 10],
            'slow': [20, 30]
        }

        combinations = service._generate_param_combinations(param_grid)

        assert len(combinations) == 4
        assert {'fast': 5, 'slow': 20} in combinations
        assert {'fast': 5, 'slow': 30} in combinations
        assert {'fast': 10, 'slow': 20} in combinations
        assert {'fast': 10, 'slow': 30} in combinations

    def test_three_params(self):
        """Test three parameter combinations."""
        service = OptimizationService()

        param_grid = {
            'fast': [5, 10],
            'slow': [20, 30],
            'signal_period': [5]
        }

        combinations = service._generate_param_combinations(param_grid)

        # 2 * 2 * 1 = 4 combinations
        assert len(combinations) == 4

    def test_empty_param_grid(self):
        """Test empty parameter grid."""
        service = OptimizationService()

        param_grid = {}

        combinations = service._generate_param_combinations(param_grid)

        assert len(combinations) == 1
        assert combinations[0] == {}


class TestGetOptimizationMetric:
    """Tests for getting optimization metric."""

    def test_get_sharpe_ratio(self):
        """Test getting Sharpe ratio."""
        service = OptimizationService()

        result = {
            'metrics': {
                'sharpe_ratio': 1.5,
                'total_return': 0.2,
                'max_drawdown': -0.1
            }
        }

        value = service._get_optimization_metric(result, 'sharpe_ratio')

        assert value == 1.5

    def test_get_max_drawdown(self):
        """Test getting maximum drawdown (negated value)."""
        service = OptimizationService()

        result = {
            'metrics': {
                'sharpe_ratio': 1.5,
                'max_drawdown': -0.1
            }
        }

        value = service._get_optimization_metric(result, 'max_drawdown')

        assert value == 0.1  # -(-0.1) = 0.1

    def test_get_total_return(self):
        """Test getting total return rate."""
        service = OptimizationService()

        result = {
            'metrics': {
                'total_return': 0.25
            }
        }

        value = service._get_optimization_metric(result, 'total_return')

        assert value == 0.25

    def test_get_missing_metric(self):
        """Test getting non-existent metric."""
        service = OptimizationService()

        result = {
            'metrics': {}
        }

        value = service._get_optimization_metric(result, 'sharpe_ratio')

        assert value == float('-inf')

    def test_get_unknown_metric_defaults_to_sharpe(self):
        """Test unknown metric defaults to Sharpe ratio."""
        service = OptimizationService()

        result = {
            'metrics': {
                'sharpe_ratio': 2.0
            }
        }

        value = service._get_optimization_metric(result, 'unknown_metric')

        assert value == 2.0


@pytest.mark.asyncio
class TestWaitForBacktest:
    """Tests for waiting for backtest completion."""

    async def test_wait_for_completed_task(self):
        """Test waiting for completed task."""
        service = OptimizationService()

        mock_result = Mock()
        mock_result.status = 'completed'
        mock_result.sharpe_ratio = 1.5

        service.backtest_service = AsyncMock()
        service.backtest_service.get_task_status = AsyncMock(return_value='completed')
        service.backtest_service.get_result = AsyncMock(return_value=mock_result)

        result = await service._wait_for_backtest('task_123', timeout=10)

        assert result.status == 'completed'

    async def test_wait_for_pending_task_times_out(self):
        """Test wait timeout."""
        service = OptimizationService()

        service.backtest_service = AsyncMock()
        service.backtest_service.get_task_status = AsyncMock(return_value='pending')

        with pytest.raises(RuntimeError) as exc_info:
            await service._wait_for_backtest('task_123', timeout=2)

        assert 'timeout' in str(exc_info.value).lower()

    async def test_wait_for_failed_task(self):
        """Test waiting for failed task."""
        service = OptimizationService()

        mock_result = Mock()
        mock_result.status = 'failed'
        mock_result.error_message = 'Strategy execution failed'

        service.backtest_service = AsyncMock()
        # Return running first to enter polling loop, then failed
        service.backtest_service.get_task_status = AsyncMock(side_effect=['running', 'failed'])
        service.backtest_service.get_result = AsyncMock(return_value=mock_result)

        with pytest.raises(RuntimeError) as exc_info:
            await service._wait_for_backtest('task_123', timeout=10)

        assert 'failed' in str(exc_info.value).lower()

    async def test_wait_for_cancelled_task(self):
        """Test waiting for cancelled task."""
        service = OptimizationService()

        service.backtest_service = AsyncMock()
        # Return running first to enter polling loop, then cancelled
        service.backtest_service.get_task_status = AsyncMock(side_effect=['running', 'cancelled'])

        with pytest.raises(RuntimeError) as exc_info:
            await service._wait_for_backtest('task_123', timeout=10)

        assert 'cancelled' in str(exc_info.value).lower()


@pytest.mark.asyncio
class TestRunGridSearch:
    """Tests for grid search optimization."""

    async def test_run_grid_search_basic(self):
        """Test basic grid search."""
        service = OptimizationService()

        # Mock request
        request = Mock()
        request.strategy_id = 'test_strategy'
        request.metric = 'sharpe_ratio'
        request.param_grid = {
            'fast': [5, 10],
            'slow': [20, 30]
        }
        request.backtest_config = Mock()
        request.backtest_config.model_copy = Mock(return_value=request.backtest_config)

        # Mock backtest service
        mock_response = Mock()
        mock_response.task_id = 'task_123'

        mock_result = Mock()
        mock_result.status = 'completed'
        mock_result.sharpe_ratio = 1.5
        mock_result.total_return = 0.2
        mock_result.max_drawdown = -0.1
        mock_result.annual_return = 0.15
        mock_result.win_rate = 0.6

        service.backtest_service = AsyncMock()
        service.backtest_service.run_backtest = AsyncMock(return_value=mock_response)
        service._wait_for_backtest = AsyncMock(return_value=mock_result)

        result = await service.run_grid_search('user_123', request)

        assert result.best_params is not None
        assert result.n_trials == 4
        assert len(result.all_results) == 4

    async def test_run_grid_search_empty_grid(self):
        """Test empty parameter grid."""
        service = OptimizationService()

        request = Mock()
        request.strategy_id = 'test_strategy'
        request.metric = 'sharpe_ratio'
        request.param_grid = {}
        request.backtest_config = Mock()
        request.backtest_config.model_copy = Mock(return_value=request.backtest_config)

        mock_response = Mock()
        mock_response.task_id = 'task_123'

        mock_result = Mock()
        mock_result.status = 'completed'
        mock_result.sharpe_ratio = 1.5
        mock_result.total_return = 0.2
        mock_result.max_drawdown = -0.1
        mock_result.annual_return = 0.15
        mock_result.win_rate = 0.6

        service.backtest_service = AsyncMock()
        service.backtest_service.run_backtest = AsyncMock(return_value=mock_response)
        service._wait_for_backtest = AsyncMock(return_value=mock_result)

        result = await service.run_grid_search('user_123', request)

        assert result.n_trials == 1


@pytest.mark.asyncio
class TestRunBayesianOptimization:
    """Tests for Bayesian optimization."""

    async def test_run_bayesian_optimization_without_optuna(self):
        """Test exception when Optuna is not installed."""
        service = OptimizationService()

        request = Mock()
        request.strategy_id = 'test_strategy'
        request.metric = 'sharpe_ratio'
        request.n_trials = 10
        request.param_bounds = {
            'fast': {'type': 'int', 'min': 5, 'max': 20}
        }
        request.backtest_config = Mock()
        request.backtest_config.model_copy = Mock(return_value=request.backtest_config)

        # Mock import error by patching builtins.__import__
        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'optuna':
                raise ImportError('No module named optuna')
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            with pytest.raises(ImportError) as exc_info:
                await service.run_bayesian_optimization('user_123', request)

            assert 'Optuna' in str(exc_info.value)

    async def test_run_bayesian_optimization_basic(self):
        """Test basic Bayesian optimization flow."""
        service = OptimizationService()

        request = Mock()
        request.strategy_id = 'test_strategy'
        request.metric = 'sharpe_ratio'
        request.n_trials = 5
        request.param_bounds = {
            'fast': {'type': 'int', 'min': 5, 'max': 20}
        }
        request.backtest_config = Mock()
        request.backtest_config.model_copy = Mock(return_value=request.backtest_config)

        # Mock Optuna study
        mock_trial = Mock()
        mock_trial.params = {'fast': 10}
        mock_trial.value = -1.5

        mock_study = Mock()
        mock_study.best_params = {'fast': 10}
        mock_study.best_trial = mock_trial
        mock_study.trials = [mock_trial]

        # Mock optuna module
        mock_optuna = Mock()
        mock_optuna.create_study.return_value = mock_study

        # Mock backtest result
        mock_result = Mock()
        mock_result.status = 'completed'
        mock_result.sharpe_ratio = 1.5
        mock_result.total_return = 0.2
        mock_result.max_drawdown = -0.1

        # Patch the import inside the method
        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'optuna':
                return mock_optuna
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            # Mock the async method
            service._run_single_backtest = AsyncMock(return_value=mock_result)

            result = await service.run_bayesian_optimization('user_123', request)

            assert result.best_params == {'fast': 10}
            assert result.best_metrics['sharpe_ratio'] == 1.5


@pytest.mark.asyncio
class TestRunSingleBacktest:
    """Tests for running single backtest."""

    async def test_run_single_backtest_success(self):
        """Test successful single backtest run."""
        service = OptimizationService()

        request = Mock()
        request.params = {'fast': 10, 'slow': 20}

        mock_response = Mock()
        mock_response.task_id = 'task_123'

        mock_result = Mock()
        mock_result.status = 'completed'

        service.backtest_service = AsyncMock()
        service.backtest_service.run_backtest = AsyncMock(return_value=mock_response)
        service.backtest_service.get_result = AsyncMock(return_value=mock_result)

        result = await service._run_single_backtest('user_123', request)

        assert result.status == 'completed'


class TestOptimizationServiceIntegration:
    """Tests for optimization service integration."""

    def test_service_can_be_instantiated(self):
        """Test service can be instantiated."""
        service = OptimizationService()
        assert service is not None

    def test_service_has_required_methods(self):
        """Test service has required methods."""
        service = OptimizationService()

        assert hasattr(service, 'run_grid_search')
        assert hasattr(service, 'run_bayesian_optimization')
        assert hasattr(service, '_generate_param_combinations')
        assert hasattr(service, '_get_optimization_metric')
        assert hasattr(service, '_wait_for_backtest')
        assert hasattr(service, '_run_single_backtest')
