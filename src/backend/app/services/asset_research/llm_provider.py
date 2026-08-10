"""Provider wiring for optional asset-research LLM report generation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from app.config import Settings, get_settings
from app.services.ai_router.router import AIChatRouter
from app.services.asset_research.llm_guardrails import LlmBudgetLimits


@dataclass(frozen=True, slots=True)
class AssetResearchLlmConfig:
    """Immutable provider and budget configuration for one report call."""

    enabled: bool
    model: str
    provider: str
    base_url: str | None
    api_key: str | None
    max_tokens: int
    budget_limits: LlmBudgetLimits


def asset_research_llm_config(settings: Settings | None = None) -> AssetResearchLlmConfig:
    """Build provider config from server settings without exposing env secrets."""
    resolved = settings or get_settings()
    api_key: str | None = None
    api_key_env = resolved.ASSET_RESEARCH_LLM_API_KEY_ENV
    if api_key_env:
        api_key = os.environ.get(api_key_env)
    return AssetResearchLlmConfig(
        enabled=bool(resolved.ASSET_RESEARCH_LLM_REPORT_ENABLED),
        model=resolved.ASSET_RESEARCH_LLM_MODEL.strip(),
        provider=resolved.ASSET_RESEARCH_LLM_PROVIDER.strip(),
        base_url=resolved.ASSET_RESEARCH_LLM_BASE_URL,
        api_key=api_key,
        max_tokens=resolved.ASSET_RESEARCH_LLM_MAX_TOKENS,
        budget_limits=LlmBudgetLimits(
            per_task_tokens=resolved.ASSET_RESEARCH_LLM_PER_TASK_TOKENS,
            daily_tokens=resolved.ASSET_RESEARCH_LLM_DAILY_TOKENS,
            monthly_tokens=resolved.ASSET_RESEARCH_LLM_MONTHLY_TOKENS,
            per_task_cost_usd=resolved.ASSET_RESEARCH_LLM_PER_TASK_COST_USD,
            daily_cost_usd=resolved.ASSET_RESEARCH_LLM_DAILY_COST_USD,
            monthly_cost_usd=resolved.ASSET_RESEARCH_LLM_MONTHLY_COST_USD,
        ),
    )


def build_asset_research_llm_call(
    config: AssetResearchLlmConfig,
    *,
    router: Any | None = None,
) -> Any | None:
    """Return an async callable used by ``llm_report_generator`` or None."""
    if not config.enabled or not config.model:
        return None
    ai_router = router if router is not None else AIChatRouter()

    async def call(prompt: str) -> str:
        response = await ai_router.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model=config.model,
            provider=config.provider or None,
            base_url=config.base_url,
            api_key=config.api_key,
            max_tokens=config.max_tokens,
        )
        return response.content

    return call

