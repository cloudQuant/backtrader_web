"""
回测结果对比服务

支持多个回测结果的对比和分析
"""
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging

from app.models.comparison import Comparison, ComparisonType
from app.schemas.comparison import (
    ComparisonCreate,
    ComparisonResponse,
    ComparisonUpdate,
    ComparisonListResponse,
)
from app.services.backtest_service import BacktestService
from app.db.sql_repository import SQLRepository
from app.websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)


class ComparisonService:
    """
    回测结果对比服务

    功能：
    1. 创建对比
    2. 添加/移除回测任务
    3. 生成对比分析
    4. 分享对比
    """

    def __init__(self):
        self.comparison_repo = SQLRepository(Comparison)
        self.backtest_service = BacktestService()

    async def create_comparison(
        self,
        user_id: str,
        name: str,
        backtest_task_ids: List[str],
        description: Optional[str] = None,
        comparison_type: str = ComparisonType.METRICS,
        is_public: bool = False,
    ) -> ComparisonResponse:
        """
        创建对比

        Args:
            user_id: 用户 ID
            name: 对比名称
            description: 对比描述
            backtest_task_ids: 回测任务 ID 列表
            comparison_type: 对比类型
            is_public: 是否公开

        Returns:
            ComparisonResponse: 创建的对比
        """
        # 验证回测任务存在
        for task_id in backtest_task_ids:
            result = await self.backtest_service.get_result(task_id)
            if not result:
                raise ValueError(f"回测任务不存在: {task_id}")

        # 获取所有回测结果
        backtest_results = {}
        for task_id in backtest_task_ids:
            result = await self.backtest_service.get_result(task_id)
            backtest_results[task_id] = {
                "strategy_id": result.strategy_id,
                "symbol": result.symbol,
                "total_return": result.total_return,
                "annual_return": result.annual_return,
                "sharpe_ratio": result.sharpe_ratio,
                "max_drawdown": result.max_drawdown,
                "win_rate": result.win_rate,
                "total_trades": result.total_trades,
                "equity_curve": result.equity_curve,
                "equity_dates": result.equity_dates,
                "drawdown_curve": result.drawdown_curve,
                "trades": result.trades,
            }

        # 生成对比数据
        comparison_data = await self._generate_comparison_data(
            backtest_results, comparison_type
        )

        # 创建对比
        comparison = Comparison(
            user_id=user_id,
            name=name,
            description=description,
            type=comparison_type,
            backtest_task_ids=backtest_task_ids,
            comparison_data=comparison_data,
            is_public=is_public,
        )

        comparison = await self.comparison_repo.create(comparison)

        logger.info(f"Created comparison: {comparison.id} with {len(backtest_task_ids)} backtests")

        return self._to_response(comparison)

    async def _generate_comparison_data(
        self,
        backtest_results: Dict[str, Dict[str, Any]],
        comparison_type: str,
    ) -> Dict[str, Any]:
        """
        生成对比数据

        Args:
            backtest_results: 回测结果字典
            comparison_type: 对比类型

        Returns:
            Dict: 对比数据
        """
        comparison_data = {
            "backtest_tasks": backtest_results,
            "type": comparison_type,
        }

        if comparison_type == ComparisonType.METRICS:
            # 指标对比
            comparison_data["metrics_comparison"] = self._compare_metrics(backtest_results)
            comparison_data["best_metrics"] = self._find_best_metrics(backtest_results)

        elif comparison_type == ComparisonType.EQUITY:
            # 资金曲线对比
            comparison_data["equity_comparison"] = self._compare_equity(backtest_results)

        elif comparison_type == ComparisonType.TRADES:
            # 交易对比
            comparison_data["trades_comparison"] = self._compare_trades(backtest_results)

        elif comparison_type == ComparisonType.DRAWDOWN:
            # 回撤对比
            comparison_data["drawdown_comparison"] = self._compare_drawdown(backtest_results)

        return comparison_data

    def _compare_metrics(
        self,
        backtest_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        对比性能指标

        Args:
            backtest_results: 回测结果字典

        Returns:
            Dict: 指标对比
        """
        metrics_comparison = {
            "total_return": {},
            "annual_return": {},
            "sharpe_ratio": {},
            "max_drawdown": {},
            "win_rate": {},
        }

        for task_id, result in backtest_results.items():
            metrics_comparison["total_return"][task_id] = result["total_return"]
            metrics_comparison["annual_return"][task_id] = result["annual_return"]
            metrics_comparison["sharpe_ratio"][task_id] = result["sharpe_ratio"]
            metrics_comparison["max_drawdown"][task_id] = result["max_drawdown"]
            metrics_comparison["win_rate"][task_id] = result["win_rate"]

        return metrics_comparison

    def _find_best_metrics(
        self,
        backtest_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        找到最优指标

        Args:
            backtest_results: 回测结果字典

        Returns:
            Dict: 最优指标
        """
        best_metrics = {
            "total_return": {"task_id": None, "value": float('-inf')},
            "annual_return": {"task_id": None, "value": float('-inf')},
            "sharpe_ratio": {"task_id": None, "value": float('-inf')},
            "max_drawdown": {"task_id": None, "value": float('inf')},
            "win_rate": {"task_id": None, "value": 0.0},
        }

        for task_id, result in backtest_results.items():
            # 总收益率（最大化）
            if result["total_return"] > best_metrics["total_return"]["value"]:
                best_metrics["total_return"] = {"task_id": task_id, "value": result["total_return"]}

            # 年化收益率（最大化）
            if result["annual_return"] > best_metrics["annual_return"]["value"]:
                best_metrics["annual_return"] = {"task_id": task_id, "value": result["annual_return"]}

            # 夏普比率（最大化）
            if result["sharpe_ratio"] > best_metrics["sharpe_ratio"]["value"]:
                best_metrics["sharpe_ratio"] = {"task_id": task_id, "value": result["sharpe_ratio"]}

            # 最大回撤（最小化）
            if result["max_drawdown"] < best_metrics["max_drawdown"]["value"]:
                best_metrics["max_drawdown"] = {"task_id": task_id, "value": result["max_drawdown"]}

            # 胜率（最大化）
            if result["win_rate"] > best_metrics["win_rate"]["value"]:
                best_metrics["win_rate"] = {"task_id": task_id, "value": result["win_rate"]}

        return best_metrics

    def _compare_equity(
        self,
        backtest_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        对比资金曲线

        Args:
            backtest_results: 回测结果字典

        Returns:
            Dict: 资金曲线对比
        """
        equity_comparison = {
            "dates": [],
            "curves": {},
        }

        # 收集所有日期
        all_dates = set()
        for task_id, result in backtest_results.items():
            all_dates.update(result["equity_dates"])
        equity_comparison["dates"] = sorted(list(all_dates))

        # 收集资金曲线数据
        for task_id, result in backtest_results.items():
            # 对齐日期
            aligned_curve = []
            result_dates = result["equity_dates"]
            result_curve = result["equity_curve"]

            for date in equity_comparison["dates"]:
                if date in result_dates:
                    index = result_dates.index(date)
                    aligned_curve.append(result_curve[index])
                else:
                    # 使用前一个值或初始资金
                    if aligned_curve:
                        aligned_curve.append(aligned_curve[-1])
                    else:
                        aligned_curve.append(100000.0)  # 默认初始资金

            equity_comparison["curves"][task_id] = aligned_curve

        return equity_comparison

    def _compare_trades(
        self,
        backtest_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        对比交易记录

        Args:
            backtest_results: 回测结果字典

        Returns:
            Dict: 交易对比
        """
        trades_comparison = {
            "trade_counts": {},
            "win_rates": {},
        }

        for task_id, result in backtest_results.items():
            total_trades = result["total_trades"]
            profitable_trades = result["profitable_trades"]
            losing_trades = result["losing_trades"]
            win_rate = result["win_rate"]

            trades_comparison["trade_counts"][task_id] = {
                "total": total_trades,
                "profitable": profitable_trades,
                "losing": losing_trades,
            }
            trades_comparison["win_rates"][task_id] = win_rate

        return trades_comparison

    def _compare_drawdown(
        self,
        backtest_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        对比最大回撤

        Args:
            backtest_results: 回测结果字典

        Returns:
            Dict: 回撤对比
        """
        drawdown_comparison = {
            "max_drawdowns": {},
            "drawdown_curves": {},
        }

        # 收集最大回撤
        for task_id, result in backtest_results.items():
            drawdown_comparison["max_drawdowns"][task_id] = result["max_drawdown"]
            drawdown_comparison["drawdown_curves"][task_id] = result["drawdown_curve"]

        return drawdown_comparison

    async def update_comparison(
        self,
        comparison_id: str,
        user_id: str,
        update_data: ComparisonUpdate,
    ) -> Optional[ComparisonResponse]:
        """
        更新对比

        Args:
            comparison_id: 对比 ID
            user_id: 用户 ID
            update_data: 更新数据

        Returns:
            ComparisonResponse or None
        """
        comparison = await self.comparison_repo.get_by_id(comparison_id)
        if not comparison or comparison.user_id != user_id:
            return None

        update_dict = {}
        if update_data.name is not None:
            update_dict["name"] = update_data.name
        if update_data.description is not None:
            update_dict["description"] = update_data.description
        if update_data.is_public is not None:
            update_dict["is_public"] = update_data.is_public
        if update_data.backtest_task_ids is not None:
            update_dict["backtest_task_ids"] = update_data.backtest_task_ids
            # 重新生成对比数据
            backtest_results = {}
            for task_id in update_data.backtest_task_ids:
                result = await self.backtest_service.get_result(task_id)
                if result:
                    backtest_results[task_id] = {
                        "strategy_id": result.strategy_id,
                        "total_return": result.total_return,
                        "sharpe_ratio": result.sharpe_ratio,
                        "max_drawdown": result.max_drawdown,
                        "win_rate": result.win_rate,
                        "equity_curve": result.equity_curve,
                        "equity_dates": result.equity_dates,
                        "drawdown_curve": result.drawdown_curve,
                    }

            update_dict["comparison_data"] = await self._generate_comparison_data(
                backtest_results, comparison.type
            )

        if update_dict:
            update_dict["updated_at"] = datetime.utcnow()
            comparison = await self.comparison_repo.update(comparison_id, update_dict)

        return self._to_response(comparison)

    async def delete_comparison(
        self,
        comparison_id: str,
        user_id: str,
    ) -> bool:
        """
        删除对比

        Args:
            comparison_id: 对比 ID
            user_id: 用户 ID

        Returns:
            bool: 是否删除成功
        """
        comparison = await self.comparison_repo.get_by_id(comparison_id)
        if not comparison or comparison.user_id != user_id:
            return False

        await self.comparison_repo.delete(comparison_id)
        return True

    async def get_comparison(
        self,
        comparison_id: str,
        user_id: str,
    ) -> Optional[ComparisonResponse]:
        """
        获取对比

        Args:
            comparison_id: 对比 ID
            user_id: 用户 ID

        Returns:
            ComparisonResponse or None
        """
        comparison = await self.comparison_repo.get_by_id(comparison_id)

        # 检查权限
        if not comparison:
            return None

        # 只能访问公开的或自己的对比
        if not comparison.is_public and comparison.user_id != user_id:
            return None

        return self._to_response(comparison)

    async def list_comparisons(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        is_public: Optional[bool] = None,
    ) -> tuple[List[Comparison], int]:
        """
        列出对比

        Args:
            user_id: 用户 ID
            limit: 每页数量
            offset: 偏移量
            is_public: 是否只公开的

        Returns:
            (comparisons, total)
        """
        filters = {"user_id": user_id}

        # 如果只看公开的，则不限制用户（或者限制为公开的）
        if is_public is not None:
            if is_public:
                filters = {"is_public": True}
            else:
                filters = {"user_id": user_id, "is_public": False}

        comparisons = await self.comparison_repo.list(
            filters=filters,
            skip=offset,
            limit=limit,
            sort_by="created_at",
            sort_order="desc",
        )

        total = await self.comparison_repo.count(filters=filters)

        return comparisons, total

    def _to_response(self, comparison: Comparison) -> ComparisonResponse:
        """
        转换为响应模型

        Args:
            comparison: 对比模型

        Returns:
            ComparisonResponse
        """
        return ComparisonResponse(
            id=comparison.id,
            user_id=comparison.user_id,
            name=comparison.name,
            description=comparison.description,
            type=comparison.type,
            backtest_task_ids=comparison.backtest_task_ids,
            comparison_data=comparison.comparison_data,
            is_favorite=comparison.is_favorite,
            is_public=comparison.is_public,
            created_at=comparison.created_at,
            updated_at=comparison.updated_at,
        )
