"""LLM budget and fallback guardrails for asset-research reports."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LlmBudgetLimits:
    """Server-owned token/cost limits used before and after an LLM call."""

    per_task_tokens: int
    daily_tokens: int
    monthly_tokens: int
    per_task_cost_usd: float
    daily_cost_usd: float
    monthly_cost_usd: float

    def validate(self) -> None:
        values = (
            self.per_task_tokens,
            self.daily_tokens,
            self.monthly_tokens,
            self.per_task_cost_usd,
            self.daily_cost_usd,
            self.monthly_cost_usd,
        )
        if any(value < 0 for value in values):
            raise ValueError("LLM_BUDGET_LIMIT_NEGATIVE")
        if self.per_task_tokens > self.daily_tokens or self.daily_tokens > self.monthly_tokens:
            raise ValueError("LLM_BUDGET_LIMIT_MONOTONIC")
        if (
            self.per_task_cost_usd > self.daily_cost_usd
            or self.daily_cost_usd > self.monthly_cost_usd
        ):
            raise ValueError("LLM_BUDGET_LIMIT_MONOTONIC")


@dataclass(frozen=True, slots=True)
class LlmBudgetDecision:
    """Whether an LLM call may proceed and why it must fall back."""

    allowed: bool
    remaining_tokens: int
    remaining_cost_usd: float
    fallback_reason: str | None = None


def check_token_budget(
    *,
    used_tokens: int,
    requested_tokens: int,
    limits: LlmBudgetLimits,
) -> LlmBudgetDecision:
    """Reject calls that would exceed any configured token budget."""
    limits.validate()
    if used_tokens < 0 or requested_tokens < 0:
        raise ValueError("LLM_BUDGET_NEGATIVE")
    remaining_daily = max(0, limits.daily_tokens - used_tokens)
    remaining_monthly = max(0, limits.monthly_tokens - used_tokens)
    remaining = min(remaining_daily, remaining_monthly)
    if requested_tokens > limits.per_task_tokens:
        return LlmBudgetDecision(False, remaining, 0.0, fallback_reason="BUDGET")
    if requested_tokens > remaining:
        return LlmBudgetDecision(False, remaining, 0.0, fallback_reason="BUDGET")
    return LlmBudgetDecision(True, remaining - requested_tokens, 0.0)


def check_cost_budget(
    *,
    used_cost_usd: float,
    requested_cost_usd: float,
    limits: LlmBudgetLimits,
) -> LlmBudgetDecision:
    """Reject calls that would exceed daily or monthly cost budgets."""
    limits.validate()
    if used_cost_usd < 0 or requested_cost_usd < 0:
        raise ValueError("LLM_BUDGET_NEGATIVE")
    remaining_daily = max(0.0, limits.daily_cost_usd - used_cost_usd)
    remaining_monthly = max(0.0, limits.monthly_cost_usd - used_cost_usd)
    remaining = min(remaining_daily, remaining_monthly)
    if requested_cost_usd > limits.per_task_cost_usd:
        return LlmBudgetDecision(False, 0, remaining, fallback_reason="BUDGET")
    if requested_cost_usd > remaining:
        return LlmBudgetDecision(False, 0, remaining, fallback_reason="BUDGET")
    return LlmBudgetDecision(True, 0, remaining - requested_cost_usd)


def fallback_reason_for_error(error: BaseException) -> str:
    """Map a stable exception to a bounded fallback reason for metrics."""
    message = str(error).upper()
    if any(token in message for token in ("429", "RATE_LIMIT", "RATE LIMIT")):
        return "RATE_LIMIT"
    if any(token in message for token in ("TIMEOUT", "TIMED OUT")):
        return "TIMEOUT"
    if any(token in message for token in ("INVALID", "SCHEMA", "PARSE")):
        return "OUTPUT_INVALID"
    if any(token in message for token in ("UNAVAILABLE", "MODEL_NOT_FOUND", "500")):
        return "MODEL_UNAVAILABLE"
    return "MODEL_UNAVAILABLE"

