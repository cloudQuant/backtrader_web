"""The persisted structured signal remains authoritative over AI narrative text."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.stock_analysis.analysis_engine import StockAnalysisEngine


class _TimeoutingRouter:
    async def chat_completion(self, **_kwargs: object) -> object:
        raise TimeoutError()


class _NoModelPreference:
    def resolve_model_key(self, _model_id: str | None) -> None:
        return None

    async def resolve_for_user(self, _user_id: str) -> None:
        return None


async def _no_budget_limit(**_kwargs: object) -> None:
    return None


@pytest.mark.asyncio
async def test_ai_stage_cannot_replace_the_persisted_watch_signal_with_its_own_text() -> None:
    db = SimpleNamespace(add=lambda _value: None)
    engine = StockAnalysisEngine(
        db,
        ai_router=_TimeoutingRouter(),
        model_preference_service=_NoModelPreference(),
        budget_checker=_no_budget_limit,
        settings=SimpleNamespace(
            AI_CHAT_ENABLED=True,
            AI_CHAT_BASE_URL="http://ai.local",
            AI_CHAT_API_KEY="test-key",
            AI_CHAT_MODEL="test-model",
            AI_CHAT_TIMEOUT=1,
            AI_CHAT_TEMPERATURE=0.2,
        ),
    )
    structured = {
        "action": "观望",
        "signal_action": "WATCH",
        "confidence_score": 0.5,
        "risk_score": 0.7,
        "eligibility_status": "degraded",
        "quality_reasons": ["news_unavailable"],
        "feature_version": "ohlcv-v1",
        "decision_policy_version": "baseline-v1",
        "model_version": "deterministic-shadow-v1",
    }

    output = await engine.enhance(
        task_id="authority-test",
        user_id="user-1",
        model_id=None,
        symbol="600000.SH",
        market_type="A股",
        research_depth="标准",
        selected_modules=["market"],
        snapshot={"quote": {"price": 10.0}},
        pipeline_output={
            "final_trade_decision": "最终交易建议：买入。",
            "structured_signal_decision": structured,
            "scores": {},
        },
    )

    assert output["decision"] == structured
    assert output["decision"]["action"] == "观望"
    assert output["ai_stage_generation"]["degraded"] is True
