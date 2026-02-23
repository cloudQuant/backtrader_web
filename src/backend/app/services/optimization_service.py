"""
Optimization service.

Supports grid search and Bayesian optimization.
"""
import asyncio
import itertools
import logging
from typing import Any, Dict, List

from app.db.cache import get_cache
from app.db.sql_repository import SQLRepository
from app.models.backtest import BacktestTask
from app.schemas.backtest_enhanced import (
    BacktestRequest,
    BacktestResult,
    OptimizationRequest,
    OptimizationResult,
    TaskStatus,
)

from .backtest_service import BacktestService

logger = logging.getLogger(__name__)


class OptimizationService:
    """Service for parameter optimization.

    Supports:
        1. Grid search: Iterate through all parameter combinations.
        2. Bayesian optimization: Use Optuna for intelligent optimization.

    Attributes:
        backtest_service: Service for running backtests.
        task_repo: Repository for backtest tasks.
        cache: Cache instance for storing results.
    """

    def __init__(self):
        """Initialize the OptimizationService."""
        self.backtest_service = BacktestService()
        self.task_repo = SQLRepository(BacktestTask)
        self.cache = get_cache()

    async def run_grid_search(
        self,
        user_id: str,
        request: OptimizationRequest
    ) -> OptimizationResult:
        """Run grid search optimization.

        Args:
            user_id: The user ID.
            request: The optimization request.

        Returns:
            OptimizationResult: The optimization results containing best parameters
                and metrics.
        """
        logger.info(f"Starting grid search optimization: {request.strategy_id}")

        # Generate all parameter combinations
        param_combinations = self._generate_param_combinations(request.param_grid)

        logger.info(f"Total parameter combinations: {len(param_combinations)}")

        results = []
        completed_count = 0

        # Iterate through all parameter combinations
        for i, params in enumerate(param_combinations):
            logger.info(f"Optimization progress: {i+1}/{len(param_combinations)}")

            # Create backtest request
            backtest_request = request.backtest_config.model_copy()
            backtest_request.params = params

            # Run backtest
            try:
                backtest_response = await self.backtest_service.run_backtest(
                    user_id, backtest_request
                )

                # Wait for backtest to complete
                result = await self._wait_for_backtest(backtest_response.task_id)

                if result.status == TaskStatus.COMPLETED:
                    # Record result
                    results.append({
                        'params': params,
                        'metrics': {
                            'sharpe_ratio': result.sharpe_ratio,
                            'total_return': result.total_return,
                            'max_drawdown': result.max_drawdown,
                            'annual_return': result.annual_return,
                            'win_rate': result.win_rate,
                        }
                    })
                    completed_count += 1
                else:
                    logger.warning(f"Backtest failed: {backtest_response.task_id}")

            except Exception as e:
                logger.error(f"Parameter combination execution failed: {params}, {e}")
                continue

        logger.info(f"Grid search completed: {completed_count}/{len(param_combinations)}")

        # Sort by optimization metric
        results.sort(
            key=lambda x: self._get_optimization_metric(x, request.metric),
            reverse=True  # Maximize metric
        )

        # Return best result
        best_result = results[0] if results else None

        return OptimizationResult(
            best_params=best_result['params'] if best_result else {},
            best_metrics=best_result['metrics'] if best_result else {},
            all_results=results,
            n_trials=completed_count,
        )

    async def run_bayesian_optimization(
        self,
        user_id: str,
        request: OptimizationRequest
    ) -> OptimizationResult:
        """Run Bayesian optimization.

        Uses Optuna for intelligent parameter optimization.

        Args:
            user_id: The user ID.
            request: The optimization request.

        Returns:
            OptimizationResult: The optimization results containing best parameters
                and metrics.

        Raises:
            ImportError: If Optuna is not installed.
        """
        logger.info(f"Starting Bayesian optimization: {request.strategy_id}")

        try:
            import optuna
        except ImportError:
            raise ImportError("Please install Optuna: pip install optuna")

        # Define objective function
        def objective(trial):
            """Optuna objective function.

            Args:
                trial: An Optuna trial object.

            Returns:
                float: The optimization metric value.
            """
            # Get parameters from trial
            params = {}
            for key, bounds in request.param_bounds.items():
                if bounds.get('type') == 'int':
                    params[key] = trial.suggest_int(key, bounds['min'], bounds['max'])
                elif bounds.get('type') == 'float':
                    params[key] = trial.suggest_float(key, bounds['min'], bounds['max'])
                elif bounds.get('type') == 'categorical':
                    params[key] = trial.suggest_categorical(key, bounds['choices'])

            # Create backtest request
            backtest_request = request.backtest_config.model_copy()
            backtest_request.params = params

            # Run backtest (synchronous mode as Optuna requires main process)
            # Use synchronous mode or asyncio event loop
            try:
                result = asyncio.run_coroutine_threadsafe(
                    self._run_single_backtest(user_id, backtest_request),
                    asyncio.get_event_loop()
                ).result()

                if result.status == TaskStatus.COMPLETED:
                    # Return metric based on optimization target
                    if request.metric == 'sharpe_ratio':
                        return -result.sharpe_ratio  # Maximize Sharpe ratio
                    elif request.metric == 'max_drawdown':
                        return result.max_drawdown  # Minimize max drawdown
                    elif request.metric == 'total_return':
                        return -result.total_return  # Maximize total return
                    else:
                        return -result.sharpe_ratio
                else:
                    # If backtest fails, return worst value
                    return float('-inf') if request.metric in ['sharpe_ratio', 'total_return'] else float('inf')

            except Exception as e:
                logger.error(f"Trial failed: {params}, {e}")
                # Return worst value
                return float('-inf') if request.metric in ['sharpe_ratio', 'total_return'] else float('inf')

        # Create Study
        study = optuna.create_study(direction='minimize')

        # Run optimization
        logger.info(f"Starting {request.n_trials} trials")
        study.optimize(objective, n_trials=request.n_trials)

        # Get best parameters
        best_params = study.best_params
        best_value = study.best_trial.value

        # Convert negative values back to positive
        if request.metric in ['sharpe_ratio', 'total_return']:
            best_value = -best_value

        # Run backtest with best parameters to get complete results
        backtest_request = request.backtest_config.model_copy()
        backtest_request.params = best_params
        _backtest_result = await self._run_single_backtest(user_id, backtest_request)

        # Collect all trial results
        all_results = []
        for trial in study.trials:
            params = trial.params
            value = -trial.value if request.metric in ['sharpe_ratio', 'total_return'] else trial.value
            all_results.append({
                'params': params,
                'metrics': {
                    request.metric: value,
                }
            })

        logger.info(f"Bayesian optimization completed: Best metric = {best_value}")

        return OptimizationResult(
            best_params=best_params,
            best_metrics={request.metric: best_value},
            all_results=all_results,
            n_trials=request.n_trials,
        )

    async def _run_single_backtest(
        self,
        user_id: str,
        request: BacktestRequest
    ) -> BacktestResult:
        """Run a single backtest (helper method).

        Note: Must wait for backtest to complete before retrieving results.

        Args:
            user_id: The user ID.
            request: The backtest request.

        Returns:
            BacktestResult: The backtest result.
        """
        backtest_response = await self.backtest_service.run_backtest(user_id, request)
        result = await self._wait_for_backtest(backtest_response.task_id)
        return result

    def _generate_param_combinations(
        self,
        param_grid: Dict[str, List[Any]]
    ) -> List[Dict[str, Any]]:
        """Generate parameter combinations (Cartesian product).

        Args:
            param_grid: The parameter grid with keys mapping to lists of values.

        Returns:
            List[Dict[str, Any]]: A list of parameter combination dictionaries.
        """
        keys = list(param_grid.keys())
        values = list(param_grid.values())

        # Use itertools.product to generate Cartesian product
        combinations = list(itertools.product(*values))

        # Convert to list of dictionaries
        return [dict(zip(keys, combo)) for combo in combinations]

    def _get_optimization_metric(
        self,
        result: Dict[str, Any],
        metric: str
    ) -> float:
        """Get the value of the optimization metric.

        Args:
            result: The backtest result containing metrics.
            metric: The optimization target metric name.

        Returns:
            float: The metric value, adjusted for maximization.
        """
        metrics = result.get('metrics', {})

        if metric == 'sharpe_ratio':
            return metrics.get('sharpe_ratio', float('-inf'))
        elif metric == 'max_drawdown':
            return -metrics.get('max_drawdown', float('inf'))  # Minimize max drawdown
        elif metric == 'total_return':
            return metrics.get('total_return', float('-inf'))
        else:
            return metrics.get('sharpe_ratio', float('-inf'))

    async def _wait_for_backtest(
        self,
        task_id: str,
        timeout: int = 600
    ) -> BacktestResult:
        """Wait for backtest to complete.

        Args:
            task_id: The task ID.
            timeout: The timeout in seconds.

        Returns:
            BacktestResult: The backtest result.

        Raises:
            RuntimeError: If the backtest fails, is cancelled, or times out.
        """
        # Check task status
        status = await self.backtest_service.get_task_status(task_id)

        if status != TaskStatus.PENDING and status != TaskStatus.RUNNING:
            # Task completed or failed, return result directly
            return await self.backtest_service.get_result(task_id)

        # Poll task status
        waited = 0
        while waited < timeout:
            await asyncio.sleep(1)
            waited += 1

            status = await self.backtest_service.get_task_status(task_id)

            if status == TaskStatus.COMPLETED:
                return await self.backtest_service.get_result(task_id)
            elif status == TaskStatus.FAILED:
                result = await self.backtest_service.get_result(task_id)
                raise RuntimeError(f"Backtest failed: {result.error_message}")
            elif status == TaskStatus.CANCELLED:
                raise RuntimeError("Backtest task cancelled")

        raise RuntimeError(f"Backtest task timeout ({timeout} seconds)")
