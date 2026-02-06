"""
参数优化服务

支持网格搜索和贝叶斯优化
"""
import uuid
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging
import itertools

from app.models.backtest import BacktestTask, BacktestResultModel
from app.schemas.backtest_enhanced import (
    OptimizationRequest,
    OptimizationResult,
    BacktestRequest,
    BacktestResult,
    TaskStatus,
)
from app.db.sql_repository import SQLRepository
from app.db.cache import get_cache
from .backtest_service import BacktestService

logger = logging.getLogger(__name__)


class OptimizationService:
    """
    参数优化服务
    
    支持：
    1. 网格搜索：遍历所有参数组合
    2. 贝叶斯优化：使用 Optuna 进行智能优化
    """

    def __init__(self):
        self.backtest_service = BacktestService()
        self.task_repo = SQLRepository(BacktestTask)
        self.cache = get_cache()

    async def run_grid_search(
        self,
        user_id: str,
        request: OptimizationRequest
    ) -> OptimizationResult:
        """
        网格搜索优化

        Args:
            user_id: 用户ID
            request: 优化请求

        Returns:
            OptimizationResult: 优化结果
        """
        logger.info(f"开始网格搜索优化: {request.strategy_id}")

        # 生成所有参数组合
        param_combinations = self._generate_param_combinations(request.param_grid)

        logger.info(f"参数组合总数: {len(param_combinations)}")

        results = []
        completed_count = 0

        # 遍历所有参数组合
        for i, params in enumerate(param_combinations):
            logger.info(f"优化进度: {i+1}/{len(param_combinations)}")

            # 创建回测请求
            backtest_request = request.backtest_config.model_copy()
            backtest_request.params = params

            # 运行回测
            try:
                backtest_response = await self.backtest_service.run_backtest(
                    user_id, backtest_request
                )

                # 等待回测完成
                result = await self._wait_for_backtest(backtest_response.task_id)

                if result.status == TaskStatus.COMPLETED:
                    # 记录结果
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
                    logger.warning(f"回测失败: {backtest_response.task_id}")

            except Exception as e:
                logger.error(f"参数组合执行失败: {params}, {e}")
                continue

        logger.info(f"网格搜索完成: {completed_count}/{len(param_combinations)}")

        # 根据优化目标排序
        results.sort(
            key=lambda x: self._get_optimization_metric(x, request.metric),
            reverse=True  # 最大化指标
        )

        # 返回最优结果
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
        """
        贝叶斯优化

        使用 Optuna 进行智能参数优化

        Args:
            user_id: 用户ID
            request: 优化请求

        Returns:
            OptimizationResult: 优化结果
        """
        logger.info(f"开始贝叶斯优化: {request.strategy_id}")

        try:
            import optuna
        except ImportError:
            raise ImportError("请安装 Optuna: pip install optuna")

        # 定义目标函数
        def objective(trial):
            """Optuna 目标函数"""
            # 从试验中获取参数
            params = {}
            for key, bounds in request.param_bounds.items():
                if bounds.get('type') == 'int':
                    params[key] = trial.suggest_int(key, bounds['min'], bounds['max'])
                elif bounds.get('type') == 'float':
                    params[key] = trial.suggest_float(key, bounds['min'], bounds['max'])
                elif bounds.get('type') == 'categorical':
                    params[key] = trial.suggest_categorical(key, bounds['choices'])

            # 创建回测请求
            backtest_request = request.backtest_config.model_copy()
            backtest_request.params = params

            # 运行回测（同步方式，因为 Optuna 需要在主进程中）
            # 这里需要使用同步的方式，或者通过 asyncio 事件循环
            try:
                result = asyncio.run_coroutine_threadsafe(
                    self._run_single_backtest(user_id, backtest_request),
                    asyncio.get_event_loop()
                ).result()

                if result.status == TaskStatus.COMPLETED:
                    # 根据优化目标返回指标
                    if request.metric == 'sharpe_ratio':
                        return -result.sharpe_ratio  # 最大化夏普比率
                    elif request.metric == 'max_drawdown':
                        return result.max_drawdown  # 最小化最大回撤
                    elif request.metric == 'total_return':
                        return -result.total_return  # 最大化收益率
                    else:
                        return -result.sharpe_ratio
                else:
                    # 如果回测失败，返回最差值
                    return float('-inf') if request.metric in ['sharpe_ratio', 'total_return'] else float('inf')

            except Exception as e:
                logger.error(f"试验失败: {params}, {e}")
                # 返回最差值
                return float('-inf') if request.metric in ['sharpe_ratio', 'total_return'] else float('inf')

        # 创建 Study
        study = optuna.create_study(direction='minimize')

        # 运行优化
        logger.info(f"开始 {request.n_trials} 次试验")
        study.optimize(objective, n_trials=request.n_trials)

        # 获取最优参数
        best_params = study.best_params
        best_value = study.best_trial.value

        # 将负值转回正值
        if request.metric in ['sharpe_ratio', 'total_return']:
            best_value = -best_value

        # 运行最优参数的回测获取完整结果
        backtest_request = request.backtest_config.model_copy()
        backtest_request.params = best_params
        backtest_result = await self._run_single_backtest(user_id, backtest_request)

        # 收集所有试验结果
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

        logger.info(f"贝叶斯优化完成: 最佳指标 = {best_value}")

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
        """
        运行单个回测（辅助方法）

        Args:
            user_id: 用户ID
            request: 回测请求

        Returns:
            BacktestResult: 回测结果
        """
        backtest_response = await self.backtest_service.run_backtest(user_id, request)
        result = await self.backtest_service.get_result(backtest_response.task_id)
        return result

    def _generate_param_combinations(
        self,
        param_grid: Dict[str, List[Any]]
    ) -> List[Dict[str, Any]]:
        """
        生成参数组合（笛卡尔积）

        Args:
            param_grid: 参数网格

        Returns:
            参数组合列表
        """
        keys = list(param_grid.keys())
        values = list(param_grid.values())

        # 使用 itertools.product 生成笛卡尔积
        combinations = list(itertools.product(*values))

        # 转换为字典列表
        return [dict(zip(keys, combo)) for combo in combinations]

    def _get_optimization_metric(
        self,
        result: Dict[str, Any],
        metric: str
    ) -> float:
        """
        获取优化指标的值

        Args:
            result: 回测结果
            metric: 优化目标

        Returns:
            指标值
        """
        metrics = result.get('metrics', {})

        if metric == 'sharpe_ratio':
            return metrics.get('sharpe_ratio', float('-inf'))
        elif metric == 'max_drawdown':
            return -metrics.get('max_drawdown', float('inf'))  # 最小化最大回撤
        elif metric == 'total_return':
            return metrics.get('total_return', float('-inf'))
        else:
            return metrics.get('sharpe_ratio', float('-inf'))

    async def _wait_for_backtest(
        self,
        task_id: str,
        timeout: int = 600
    ) -> BacktestResult:
        """
        等待回测完成

        Args:
            task_id: 任务ID
            timeout: 超时时间（秒）

        Returns:
            BacktestResult: 回测结果
        """
        # 检查任务状态
        status = await self.backtest_service.get_task_status(task_id)
        
        if status != TaskStatus.PENDING and status != TaskStatus.RUNNING:
            # 任务已完成或失败，直接返回结果
            return await self.backtest_service.get_result(task_id)

        # 轮询任务状态
        waited = 0
        while waited < timeout:
            await asyncio.sleep(1)
            waited += 1

            status = await self.backtest_service.get_task_status(task_id)
            
            if status == TaskStatus.COMPLETED:
                return await self.backtest_service.get_result(task_id)
            elif status == TaskStatus.FAILED:
                result = await self.backtest_service.get_result(task_id)
                raise RuntimeError(f"回测失败: {result.error_message}")
            elif status == TaskStatus.CANCELLED:
                raise RuntimeError("回测任务已取消")

        raise RuntimeError(f"回测任务超时（{timeout} 秒）")
