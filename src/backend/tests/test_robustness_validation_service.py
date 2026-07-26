"""Robustness-validation gates and failure-path tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.schemas.market_data_trust import RobustnessValidationRequest
from app.services.robustness_validation_service import RobustnessValidationService


def test_robustness_gates_pass_and_fail_deterministically():
    request = RobustnessValidationRequest(min_robustness_score=60, require_no_high_risk=True)

    passed = RobustnessValidationService._gate_evaluations(
        SimpleNamespace(robustness_score=80, overall_level=SimpleNamespace(value="low")), request
    )
    failed = RobustnessValidationService._gate_evaluations(
        SimpleNamespace(robustness_score=50, overall_level=SimpleNamespace(value="high")), request
    )

    assert all(item.passed for item in passed)
    assert not any(item.passed for item in failed)


@pytest.mark.asyncio
async def test_robustness_validation_rejects_a_missing_or_cross_owner_backtest():
    class _Backtests:
        async def get_result(self, *_: object, **__: object) -> None:
            return None

    service = RobustnessValidationService(
        overfitting_service=SimpleNamespace(backtest_service=_Backtests())
    )

    with pytest.raises(ValueError, match="Backtest result not found"):
        await service.run_for_backtest(backtest_id="missing", user_id="owner")
