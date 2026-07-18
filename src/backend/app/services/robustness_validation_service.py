"""Robustness validation service for Direction B."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.backtest import BacktestTask
from app.models.market_data_trust import RobustnessTestResultModel
from app.schemas.market_data_trust import (
    QualityGateEvaluation,
    RobustnessTestResultResponse,
    RobustnessValidationRequest,
)
from app.schemas.overfitting import OverfittingAnalysisRequest, OverfittingMethod
from app.services.overfitting.service import OverfittingService


class RobustnessValidationService:
    """Run and persist robustness validations for backtest results."""

    def __init__(self, overfitting_service: OverfittingService | None = None) -> None:
        self.overfitting_service = overfitting_service or OverfittingService()

    async def run_for_backtest(
        self,
        *,
        backtest_id: str,
        user_id: str,
        request: RobustnessValidationRequest | None = None,
    ) -> RobustnessTestResultResponse:
        config = request or RobustnessValidationRequest()
        backtest_result = await self.overfitting_service.backtest_service.get_result(
            backtest_id,
            user_id=user_id,
        )
        if backtest_result is None:
            raise ValueError("Backtest result not found")

        methods = [_method_from_text(item) for item in config.methods]
        analysis = await self.overfitting_service.calculate_analysis(
            backtest_result,
            OverfittingAnalysisRequest(
                methods=methods,
                monte_carlo_iterations=config.monte_carlo_iterations,
                random_seed=config.random_seed,
            ),
            user_id=user_id,
        )
        gates = self._gate_evaluations(analysis, config)
        status = (
            "passed" if all(item.passed for item in gates if item.severity == "error") else "failed"
        )
        task = await self._get_backtest_task(backtest_id, user_id)
        report = analysis.model_dump(mode="json")
        model = RobustnessTestResultModel(
            user_id=user_id,
            run_id=config.run_id,
            strategy_version_id=config.strategy_version_id
            or (str(task.strategy_version_id) if task and task.strategy_version_id else None),
            backtest_id=backtest_id,
            method="overfitting_suite",
            status=status,
            metrics={
                "robustness_score": analysis.robustness_score,
                "overall_level": analysis.overall_level.value,
                "method_count": len(analysis.methods),
            },
            gate_evaluations=[item.model_dump(mode="json") for item in gates],
            report=report,
            error_message=analysis.error_message,
        )
        async with async_session_maker() as session:
            session.add(model)
            await session.commit()
            await session.refresh(model)
        return RobustnessTestResultResponse.model_validate(model)

    async def get_latest(
        self,
        *,
        backtest_id: str,
        user_id: str,
    ) -> RobustnessTestResultResponse | None:
        async with async_session_maker() as session:
            result = await session.execute(
                select(RobustnessTestResultModel)
                .where(
                    RobustnessTestResultModel.backtest_id == backtest_id,
                    RobustnessTestResultModel.user_id == user_id,
                )
                .order_by(RobustnessTestResultModel.created_at.desc())
                .limit(1)
            )
            model = result.scalars().first()
        return RobustnessTestResultResponse.model_validate(model) if model else None

    async def _get_backtest_task(self, backtest_id: str, user_id: str) -> BacktestTask | None:
        async with async_session_maker() as session:
            task = await session.get(BacktestTask, backtest_id)
            if task is None or str(task.user_id) != str(user_id):
                return None
            return task

    @staticmethod
    def _gate_evaluations(
        analysis: Any,
        request: RobustnessValidationRequest,
    ) -> list[QualityGateEvaluation]:
        score = float(analysis.robustness_score or 0.0)
        overall_level = str(analysis.overall_level.value)
        no_high_risk = overall_level != "high"
        return [
            QualityGateEvaluation(
                key="robustness_score",
                label="稳健性得分",
                actual=score,
                threshold=request.min_robustness_score,
                operator=">=",
                passed=score >= request.min_robustness_score,
                severity="error",
                message=(f"稳健性得分 {score:.2f} 低于 {request.min_robustness_score:.2f}。"),
            ),
            QualityGateEvaluation(
                key="overfitting_risk",
                label="过拟合风险",
                actual=overall_level,
                threshold="high",
                operator="!=",
                passed=no_high_risk or not request.require_no_high_risk,
                severity="error" if request.require_no_high_risk else "warning",
                message="存在 high 级过拟合风险，不能进入模拟交易。",
            ),
        ]


def _method_from_text(value: str) -> OverfittingMethod:
    text = str(value or "").strip()
    try:
        return OverfittingMethod(text)
    except ValueError:
        return OverfittingMethod.MONTE_CARLO


@lru_cache
def get_robustness_validation_service() -> RobustnessValidationService:
    return RobustnessValidationService()
