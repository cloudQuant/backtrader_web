"""LLM budget and fallback guardrail contracts."""

import pytest

from app.services.asset_research.llm_guardrails import (
    LlmBudgetLimits,
    check_cost_budget,
    check_token_budget,
    fallback_reason_for_error,
)


def _limits() -> LlmBudgetLimits:
    return LlmBudgetLimits(
        per_task_tokens=1000,
        daily_tokens=5000,
        monthly_tokens=20000,
        per_task_cost_usd=0.1,
        daily_cost_usd=0.5,
        monthly_cost_usd=2.0,
    )


def test_token_budget_rejects_over_task_and_daily_limits() -> None:
    limits = _limits()

    over_task = check_token_budget(used_tokens=0, requested_tokens=1001, limits=limits)
    over_daily = check_token_budget(used_tokens=4500, requested_tokens=600, limits=limits)
    allowed = check_token_budget(used_tokens=100, requested_tokens=500, limits=limits)

    assert over_task.allowed is False
    assert over_task.fallback_reason == "BUDGET"
    assert over_daily.allowed is False
    assert allowed.allowed is True
    assert allowed.remaining_tokens == 4400


def test_cost_budget_rejects_over_task_limit() -> None:
    result = check_cost_budget(
        used_cost_usd=0.1,
        requested_cost_usd=0.2,
        limits=_limits(),
    )

    assert result.allowed is False
    assert result.fallback_reason == "BUDGET"


def test_fallback_reason_maps_stable_exceptions() -> None:
    assert fallback_reason_for_error(TimeoutError("timeout")) == "TIMEOUT"
    assert fallback_reason_for_error(RuntimeError("429 rate limit")) == "RATE_LIMIT"
    assert fallback_reason_for_error(RuntimeError("model unavailable")) == "MODEL_UNAVAILABLE"


def test_budget_limits_must_be_monotonic() -> None:
    limits = LlmBudgetLimits(
        per_task_tokens=2000,
        daily_tokens=1000,
        monthly_tokens=5000,
        per_task_cost_usd=0.1,
        daily_cost_usd=0.5,
        monthly_cost_usd=2.0,
    )

    with pytest.raises(ValueError, match="LLM_BUDGET_LIMIT_MONOTONIC"):
        limits.validate()

