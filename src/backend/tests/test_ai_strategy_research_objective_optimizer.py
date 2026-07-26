"""Tests for the opt-in LLM research-objective refinement flow."""

from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.api.strategy.base import get_ai_strategy_research_objective_optimizer
from app.schemas.ai_strategy_research import AIStrategyResearchObjectiveOptimizeRequest
from app.services.ai_router.preferences import ResolvedAIModelPreference
from app.services.ai_router.router import ChatCompletionResponse
from app.services.ai_strategy_research_objective_optimizer import (
    AIStrategyResearchObjectiveOptimizer,
)
from tests.conftest import app


class _ConfiguredPreferenceService:
    async def resolve_for_user(self, user_id: str | None) -> ResolvedAIModelPreference | None:
        return ResolvedAIModelPreference(
            provider="openai_compatible",
            model="test-model",
            base_url="https://example.test/v1",
            api_key="test-key",
            configured=True,
        )


class _UnavailablePreferenceService:
    async def resolve_for_user(self, user_id: str | None) -> ResolvedAIModelPreference | None:
        return None


class _FakeRouter:
    def __init__(self, content: str = "优化后的投研目标") -> None:
        self.content = content
        self.calls: list[dict] = []

    async def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        return ChatCompletionResponse(
            content=self.content,
            model="test-model",
            provider="openai_compatible",
        )


@pytest.mark.asyncio
async def test_objective_optimizer_preserves_config_as_model_hard_constraints():
    router = _FakeRouter("```text\n优化后的螺纹钢投研目标\n```")
    optimizer = AIStrategyResearchObjectiveOptimizer(
        ai_router=router,
        preference_service=_ConfiguredPreferenceService(),
        settings=SimpleNamespace(
            AI_CHAT_TIMEOUT=30, AI_CHAT_MAX_TOKENS=1000, AI_CHAT_TEMPERATURE=0.2
        ),
    )

    response = await optimizer.optimize(
        "user-1",
        AIStrategyResearchObjectiveOptimizeRequest(
            prompt="请为螺纹钢生成策略，目标 Sharpe 不低于 1.3。",
            research_config={
                "symbol": "RB0",
                "target_sharpe": 1.3,
                "min_total_trades": 12,
                "api_key": "must-not-reach-the-model",
            },
        ),
    )

    assert response.prompt == "优化后的螺纹钢投研目标"
    assert response.model == "test-model"
    assert response.provider == "openai_compatible"
    assert router.calls[0]["temperature"] == 0.2
    message = router.calls[0]["messages"][1]["content"]
    assert "目标 Sharpe 不低于 1.3" in message
    assert '"symbol": "RB0"' in message
    assert '"min_total_trades": 12' in message
    assert "must-not-reach-the-model" not in message


@pytest.mark.asyncio
async def test_objective_optimizer_requires_an_explicitly_configured_model():
    optimizer = AIStrategyResearchObjectiveOptimizer(
        ai_router=_FakeRouter(),
        preference_service=_UnavailablePreferenceService(),
        settings=SimpleNamespace(AI_CHAT_ENABLED=False),
    )

    with pytest.raises(ValueError, match="未配置可用的大模型"):
        await optimizer.optimize(
            "user-1",
            AIStrategyResearchObjectiveOptimizeRequest(prompt="生成可执行的趋势策略目标。"),
        )


class _FakeObjectiveOptimizer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, AIStrategyResearchObjectiveOptimizeRequest]] = []

    async def optimize(self, user_id: str, request: AIStrategyResearchObjectiveOptimizeRequest):
        self.calls.append((user_id, request))
        return {
            "prompt": "接口返回的优化投研目标",
            "model": "test-model",
            "provider": "openai_compatible",
        }


@pytest.mark.asyncio
async def test_objective_optimizer_api_requires_auth_and_returns_refined_prompt(
    client: AsyncClient,
    auth_headers: dict,
):
    service = _FakeObjectiveOptimizer()
    app.dependency_overrides[get_ai_strategy_research_objective_optimizer] = lambda: service
    try:
        response = await client.post(
            "/api/v1/strategy/ai-research/objectives/optimize",
            json={
                "prompt": "请为螺纹钢生成策略，目标 Sharpe 不低于 1.3。",
                "research_config": {"symbol": "RB0", "target_sharpe": 1.3},
            },
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_ai_strategy_research_objective_optimizer, None)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "prompt": "接口返回的优化投研目标",
        "model": "test-model",
        "provider": "openai_compatible",
    }
    assert service.calls[0][1].research_config["symbol"] == "RB0"
