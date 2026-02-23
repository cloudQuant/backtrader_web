"""
Backtest comparison service.

Supports comparing and analyzing multiple backtest results.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.db.sql_repository import SQLRepository
from app.models.comparison import Comparison, ComparisonType
from app.schemas.comparison import (
    ComparisonResponse,
    ComparisonUpdate,
)
from app.services.backtest_service import BacktestService

logger = logging.getLogger(__name__)


class ComparisonService:
    """Service for comparing and analyzing backtest results.

    This service provides functionality for:
    1. Creating comparisons between multiple backtest results
    2. Adding/removing backtest tasks from comparisons
    3. Generating comparative analysis data
    4. Sharing comparisons with other users
    """

    def __init__(self):
        """Initialize the ComparisonService.

        Creates instances of the comparison repository and backtest service.
        """
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
        """Create a new comparison between backtest results.

        Args:
            user_id: The ID of the user creating the comparison.
            name: The name of the comparison.
            backtest_task_ids: List of backtest task IDs to compare.
            description: Optional description of the comparison.
            comparison_type: The type of comparison to perform.
                Defaults to ComparisonType.METRICS.
            is_public: Whether the comparison is publicly accessible.
                Defaults to False.

        Returns:
            ComparisonResponse: The created comparison object.

        Raises:
            ValueError: If any of the specified backtest tasks do not exist.
        """
        # Verify that all backtest tasks exist
        for task_id in backtest_task_ids:
            result = await self.backtest_service.get_result(task_id)
            if not result:
                raise ValueError(f"Backtest task not found: {task_id}")

        # Retrieve all backtest results
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

        # Generate comparison data
        comparison_data = await self._generate_comparison_data(
            backtest_results, comparison_type
        )

        # Create the comparison
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
        """Generate comparison data based on the specified comparison type.

        Args:
            backtest_results: Dictionary of backtest results keyed by task ID.
            comparison_type: The type of comparison to generate.

        Returns:
            Dict containing the comparison data for the specified type.
        """
        comparison_data = {
            "backtest_tasks": backtest_results,
            "type": comparison_type,
        }

        if comparison_type == ComparisonType.METRICS:
            # Performance metrics comparison
            comparison_data["metrics_comparison"] = self._compare_metrics(backtest_results)
            comparison_data["best_metrics"] = self._find_best_metrics(backtest_results)

        elif comparison_type == ComparisonType.EQUITY:
            # Equity curve comparison
            comparison_data["equity_comparison"] = self._compare_equity(backtest_results)

        elif comparison_type == ComparisonType.TRADES:
            # Trade comparison
            comparison_data["trades_comparison"] = self._compare_trades(backtest_results)

        elif comparison_type == ComparisonType.DRAWDOWN:
            # Drawdown comparison
            comparison_data["drawdown_comparison"] = self._compare_drawdown(backtest_results)

        return comparison_data

    def _compare_metrics(
        self,
        backtest_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Compare performance metrics across multiple backtest results.

        Args:
            backtest_results: Dictionary of backtest results keyed by task ID.

        Returns:
            Dictionary containing metric comparisons for total return,
            annual return, Sharpe ratio, maximum drawdown, and win rate.
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
        """Identify the best performing metrics across all backtest results.

        Args:
            backtest_results: Dictionary of backtest results keyed by task ID.

        Returns:
            Dictionary containing the task ID and value for each best metric.
            For return-based metrics (total return, annual return, Sharpe ratio,
            win rate), the maximum value is selected. For maximum drawdown,
            the minimum value is selected.
        """
        best_metrics = {
            "total_return": {"task_id": None, "value": float('-inf')},
            "annual_return": {"task_id": None, "value": float('-inf')},
            "sharpe_ratio": {"task_id": None, "value": float('-inf')},
            "max_drawdown": {"task_id": None, "value": float('inf')},
            "win_rate": {"task_id": None, "value": 0.0},
        }

        for task_id, result in backtest_results.items():
            # Total return (maximize)
            if result["total_return"] > best_metrics["total_return"]["value"]:
                best_metrics["total_return"] = {"task_id": task_id, "value": result["total_return"]}

            # Annual return (maximize)
            if result["annual_return"] > best_metrics["annual_return"]["value"]:
                best_metrics["annual_return"] = {"task_id": task_id, "value": result["annual_return"]}

            # Sharpe ratio (maximize)
            if result["sharpe_ratio"] > best_metrics["sharpe_ratio"]["value"]:
                best_metrics["sharpe_ratio"] = {"task_id": task_id, "value": result["sharpe_ratio"]}

            # Maximum drawdown (minimize)
            if result["max_drawdown"] < best_metrics["max_drawdown"]["value"]:
                best_metrics["max_drawdown"] = {"task_id": task_id, "value": result["max_drawdown"]}

            # Win rate (maximize)
            if result["win_rate"] > best_metrics["win_rate"]["value"]:
                best_metrics["win_rate"] = {"task_id": task_id, "value": result["win_rate"]}

        return best_metrics

    def _compare_equity(
        self,
        backtest_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Compare equity curves across multiple backtest results.

        Args:
            backtest_results: Dictionary of backtest results keyed by task ID.

        Returns:
            Dictionary containing aligned dates and equity curves for comparison.
            The curves are aligned to a common date timeline for proper comparison.
        """
        equity_comparison = {
            "dates": [],
            "curves": {},
        }

        # Collect all dates from all backtest results
        all_dates = set()
        for task_id, result in backtest_results.items():
            all_dates.update(result["equity_dates"])
        equity_comparison["dates"] = sorted(list(all_dates))

        # Collect equity curve data
        for task_id, result in backtest_results.items():
            # Align dates
            aligned_curve = []
            result_dates = result["equity_dates"]
            result_curve = result["equity_curve"]

            for date in equity_comparison["dates"]:
                if date in result_dates:
                    index = result_dates.index(date)
                    aligned_curve.append(result_curve[index])
                else:
                    # Use previous value or initial capital
                    if aligned_curve:
                        aligned_curve.append(aligned_curve[-1])
                    else:
                        aligned_curve.append(100000.0)  # Default initial capital

            equity_comparison["curves"][task_id] = aligned_curve

        return equity_comparison

    def _compare_trades(
        self,
        backtest_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Compare trade statistics across multiple backtest results.

        Args:
            backtest_results: Dictionary of backtest results keyed by task ID.

        Returns:
            Dictionary containing trade counts and win rates for each backtest.
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
        """Compare drawdown metrics across multiple backtest results.

        Args:
            backtest_results: Dictionary of backtest results keyed by task ID.

        Returns:
            Dictionary containing maximum drawdown values and drawdown curves
            for each backtest result.
        """
        drawdown_comparison = {
            "max_drawdowns": {},
            "drawdown_curves": {},
        }

        # Collect maximum drawdown values and curves
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
        """Update an existing comparison.

        Args:
            comparison_id: The ID of the comparison to update.
            user_id: The ID of the user attempting the update.
            update_data: The data to update in the comparison.

        Returns:
            ComparisonResponse if the update was successful, None if the
            comparison was not found or the user does not have permission.
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
            # Regenerate comparison data
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
            update_dict["updated_at"] = datetime.now(timezone.utc)
            comparison = await self.comparison_repo.update(comparison_id, update_dict)

        return self._to_response(comparison)

    async def delete_comparison(
        self,
        comparison_id: str,
        user_id: str,
    ) -> bool:
        """Delete a comparison.

        Args:
            comparison_id: The ID of the comparison to delete.
            user_id: The ID of the user attempting the deletion.

        Returns:
            True if the deletion was successful, False if the comparison
            was not found or the user does not have permission.
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
        """Retrieve a comparison by ID.

        Args:
            comparison_id: The ID of the comparison to retrieve.
            user_id: The ID of the user requesting the comparison.

        Returns:
            ComparisonResponse if found and accessible, None otherwise.
            Users can only access their own comparisons or public comparisons.
        """
        comparison = await self.comparison_repo.get_by_id(comparison_id)

        # Check permissions
        if not comparison:
            return None

        # Only allow access to public comparisons or own comparisons
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
        """List comparisons with filtering and pagination.

        Args:
            user_id: The ID of the user requesting the list.
            limit: Maximum number of results to return. Defaults to 20.
            offset: Number of results to skip for pagination. Defaults to 0.
            is_public: Filter for public comparisons only. If True, returns
                all public comparisons. If False, returns user's private
                comparisons. If None, returns user's all comparisons.

        Returns:
            A tuple containing (list of comparisons, total count).
        """
        filters = {"user_id": user_id}

        # If filtering by public status, adjust filters accordingly
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
        """Convert a Comparison model to a ComparisonResponse schema.

        Args:
            comparison: The Comparison model instance.

        Returns:
            ComparisonResponse: The response schema representation.
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
