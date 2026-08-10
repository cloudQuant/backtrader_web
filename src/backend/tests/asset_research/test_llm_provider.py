"""Provider wiring contracts for asset-research LLM reports."""

from app.services.asset_research.llm_guardrails import LlmBudgetLimits
from app.services.asset_research.llm_provider import (
    AssetResearchLlmConfig,
    build_asset_research_llm_call,
)


def _config() -> AssetResearchLlmConfig:
    return AssetResearchLlmConfig(
        enabled=True,
        model="test/model",
        provider="litellm",
        base_url=None,
        api_key="test-key",
        max_tokens=6000,
        budget_limits=LlmBudgetLimits(
            per_task_tokens=1000,
            daily_tokens=5000,
            monthly_tokens=20000,
            per_task_cost_usd=0.1,
            daily_cost_usd=0.5,
            monthly_cost_usd=2.0,
        ),
    )


class _FakeRouter:
    async def chat_completion(self, **kwargs: object) -> object:
        class Response:
            content = "report-content"

        return Response()


def test_build_llm_call_returns_none_when_disabled() -> None:
    config = _config()
    config = AssetResearchLlmConfig(
        enabled=False,
        model=config.model,
        provider=config.provider,
        base_url=config.base_url,
        api_key=config.api_key,
        max_tokens=config.max_tokens,
        budget_limits=config.budget_limits,
    )

    assert build_asset_research_llm_call(config, router=_FakeRouter()) is None


def test_build_llm_call_uses_existing_ai_router() -> None:
    call = build_asset_research_llm_call(_config(), router=_FakeRouter())

    assert call is not None

    async def run() -> str:
        assert call is not None
        return await call("prompt")

    import asyncio

    assert asyncio.run(run()) == "report-content"

