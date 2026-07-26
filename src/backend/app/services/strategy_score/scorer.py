"""Strategy score orchestration service."""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.db.sql_repository import SQLRepository
from app.models.strategy_score import StrategyScoreModel
from app.schemas.backtest import BacktestResult
from app.schemas.strategy_score import ScoreLevel, StrategyScoreResponse
from app.services.backtest_service import BacktestService
from app.services.overfitting import OverfittingService
from app.services.strategy_score.dimensions import (
    score_benchmark_comparison_dimension,
    score_executability_dimension,
    score_overfitting_risk_dimension,
    score_profitability_dimension,
    score_risk_control_dimension,
    score_stability_dimension,
)

DEFAULT_DISCLAIMER = "评分仅供研究参考，不构成投资建议。"
DEFAULT_WEIGHTS = {
    "profitability": 0.2,
    "risk_control": 0.2,
    "stability": 0.2,
    "overfitting_risk": 0.15,
    "executability": 0.15,
    "benchmark_comparison": 0.1,
}


class StrategyScoreService:
    """Calculate and persist strategy scores."""

    def __init__(
        self,
        backtest_service: BacktestService | None = None,
        overfitting_service: OverfittingService | None = None,
    ) -> None:
        self.settings = get_settings()
        self.backtest_service = backtest_service or BacktestService()
        self.overfitting_service = overfitting_service or OverfittingService(
            backtest_service=self.backtest_service
        )
        self.score_repo = SQLRepository(StrategyScoreModel)

    def _normalized_weights(self) -> dict[str, float]:
        configured = dict(DEFAULT_WEIGHTS)
        configured.update(getattr(self.settings, "STRATEGY_SCORE_WEIGHTS", {}) or {})
        filtered = {
            key: max(0.0, float(configured.get(key, default_value)))
            for key, default_value in DEFAULT_WEIGHTS.items()
        }
        total_weight = sum(filtered.values())
        if total_weight <= 0:
            return dict(DEFAULT_WEIGHTS)
        return {key: value / total_weight for key, value in filtered.items()}

    @staticmethod
    def _score_to_level(total_score: float) -> ScoreLevel:
        if total_score >= 85:
            return ScoreLevel.S
        if total_score >= 70:
            return ScoreLevel.A
        if total_score >= 55:
            return ScoreLevel.B
        if total_score >= 40:
            return ScoreLevel.C
        return ScoreLevel.D

    def calculate_score(
        self,
        backtest_result: BacktestResult,
        *,
        overfitting_analysis=None,
    ) -> StrategyScoreResponse:
        weights = self._normalized_weights()
        dimensions = [
            score_profitability_dimension(backtest_result, weights["profitability"]),
            score_risk_control_dimension(backtest_result, weights["risk_control"]),
            score_stability_dimension(backtest_result, weights["stability"]),
            score_overfitting_risk_dimension(
                backtest_result,
                weights["overfitting_risk"],
                analysis=overfitting_analysis,
            ),
            score_executability_dimension(backtest_result, weights["executability"]),
            score_benchmark_comparison_dimension(backtest_result, weights["benchmark_comparison"]),
        ]
        total_score = round(sum(item.score * item.weight for item in dimensions), 2)
        return StrategyScoreResponse(
            backtest_id=backtest_result.task_id,
            total_score=total_score,
            level=self._score_to_level(total_score),
            model_version=getattr(self.settings, "STRATEGY_SCORE_MODEL_VERSION", "v1"),
            disclaimer=DEFAULT_DISCLAIMER,
            dimensions=dimensions,
        )

    async def score_backtest(
        self,
        *,
        backtest_id: str | None = None,
        user_id: str | None = None,
        backtest_result: BacktestResult | None = None,
    ) -> StrategyScoreResponse:
        resolved_result = await self._resolve_backtest_result(
            backtest_id=backtest_id,
            user_id=user_id,
            backtest_result=backtest_result,
        )
        overfitting_analysis = await self.overfitting_service.get_cached_analysis(
            resolved_result.task_id,
            user_id=user_id,
        )
        response = self.calculate_score(
            resolved_result,
            overfitting_analysis=overfitting_analysis,
        )
        await self._persist_score(response, self._normalized_weights())
        return response

    async def get_score_by_backtest_id(
        self,
        backtest_id: str,
        *,
        user_id: str | None = None,
    ) -> StrategyScoreResponse | None:
        authorized = await self.backtest_service.get_result(backtest_id, user_id=user_id)
        if authorized is None:
            return None
        model = await self.score_repo.get_by_field("backtest_id", backtest_id)
        if model is None:
            return None
        return self._to_response(model)

    async def _resolve_backtest_result(
        self,
        *,
        backtest_id: str | None,
        user_id: str | None,
        backtest_result: BacktestResult | None,
    ) -> BacktestResult:
        if backtest_result is not None:
            if backtest_id and backtest_id != backtest_result.task_id:
                raise ValueError(
                    "backtest_id must match backtest_result.task_id when both are provided"
                )
            return backtest_result
        if not backtest_id:
            raise ValueError("backtest_id is required when backtest_result is not provided")
        resolved_result = await self.backtest_service.get_result(backtest_id, user_id=user_id)
        if resolved_result is None:
            raise ValueError("Backtest result not found")
        return resolved_result

    async def _persist_score(
        self,
        response: StrategyScoreResponse,
        weights: dict[str, float],
    ) -> None:
        existing = await self.score_repo.get_by_field("backtest_id", response.backtest_id)
        payload: dict[str, Any] = {
            "total_score": response.total_score,
            "level": response.level.value,
            "model_version": response.model_version,
            "disclaimer": response.disclaimer,
            "dimensions": [item.model_dump(mode="json") for item in response.dimensions],
            "weights": weights,
        }
        if existing is not None:
            await self.score_repo.update(existing.id, payload)
            return
        await self.score_repo.create(
            StrategyScoreModel(
                backtest_id=response.backtest_id,
                total_score=response.total_score,
                level=response.level.value,
                model_version=response.model_version,
                disclaimer=response.disclaimer,
                dimensions=[item.model_dump(mode="json") for item in response.dimensions],
                weights=weights,
            )
        )

    def _to_response(self, model: StrategyScoreModel) -> StrategyScoreResponse:
        return StrategyScoreResponse(
            backtest_id=str(model.backtest_id),
            total_score=round(float(model.total_score or 0.0), 2),
            level=ScoreLevel(str(model.level or "D")),
            model_version=str(model.model_version or "v1"),
            disclaimer=str(model.disclaimer or DEFAULT_DISCLAIMER),
            dimensions=list(model.dimensions or []),
        )
