from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.user import User
from app.schemas.ai_strategy_research import (
    AIStrategyResearchIteration,
    InvestmentMandateCreate,
)
from app.schemas.strategy import StrategyCopilotRunResult, StrategyResponse
from app.schemas.workspace import StrategyUnitResponse, UnitStatusResponse
from app.services.ai_strategy_research_version_service import AIStrategyResearchVersionService
from app.services.investment_mandate_service import InvestmentMandateService
from app.services.research_pipeline_event_service import ResearchPipelineEventService
from tests.conftest import register_and_login

pytestmark = pytest.mark.asyncio


async def test_investment_mandate_parse_and_get(auth_user):
    user_id = await _auth_user_id(auth_user)
    service = InvestmentMandateService()

    mandate = await service.create_mandate(
        user_id,
        InvestmentMandateCreate(
            raw_prompt="为螺纹钢主连设计一个日线趋势策略，目标是控制回撤并获得稳定收益。",
            symbol="RB0",
            timeframe="1d",
            quality_gates={"target_sharpe": 1.0, "min_total_trades": 1},
        ),
    )

    assert mandate.asset_scope["asset_class"] == "futures"
    assert mandate.asset_scope["symbol"] == "RB0"
    assert mandate.timeframe == "1d"
    assert "回撤" in mandate.objective

    loaded = await service.get_mandate(user_id, mandate.id)
    assert loaded is not None
    assert loaded.id == mandate.id


async def test_research_pipeline_event_write_and_query(auth_user):
    user_id = await _auth_user_id(auth_user)
    service = ResearchPipelineEventService()

    created = await service.create_event(
        user_id=user_id,
        run_id="run-a",
        workspace_id="workspace-a",
        stage="backtesting",
        status="failed",
        iteration=1,
        summary="回测提交失败",
        metrics={"sharpe_ratio": 0.0},
        error="queue unavailable",
    )
    timeline = await service.list_events(user_id, "run-a", workspace_id="workspace-a")

    assert created.error == "queue unavailable"
    assert timeline.total == 1
    assert timeline.items[0].stage == "backtesting"
    assert timeline.items[0].metrics["sharpe_ratio"] == 0.0


async def test_ai_research_version_create_and_compare(auth_user):
    user_id = await _auth_user_id(auth_user)
    service = AIStrategyResearchVersionService()

    first = await service.create_from_iteration(
        user_id=user_id,
        run_id="run-v",
        workspace_id="workspace-v",
        mandate_id=None,
        iteration=_iteration(1, "self.buy()", 0.4, passed=False),
    )
    second = await service.create_from_iteration(
        user_id=user_id,
        run_id="run-v",
        workspace_id="workspace-v",
        mandate_id=None,
        iteration=_iteration(2, "self.buy()\nself.close()", 1.2, passed=True),
    )

    versions = await service.list_versions(user_id, "run-v")
    comparison = await service.compare_versions(user_id, first.id, second.id)

    assert versions.total == 2
    assert second.parent_version_id == first.id
    assert comparison is not None
    assert comparison.verdict == "improved"
    assert comparison.metric_deltas["sharpe_ratio"]["delta"] == pytest.approx(0.8)
    assert "self.close()" in comparison.code_diff


async def test_ai_research_direction_a_api(client, auth_headers):
    mandate_response = await client.post(
        "/api/v1/strategy/ai-research/mandates",
        headers=auth_headers,
        json={
            "raw_prompt": "为纯碱期货做 1h 趋势策略，控制回撤。",
            "symbol": "SA0",
            "timeframe": "1h",
            "quality_gates": {"target_sharpe": 1.0},
        },
    )
    assert mandate_response.status_code == 201, mandate_response.text
    mandate = mandate_response.json()

    loaded = await client.get(
        f"/api/v1/strategy/ai-research/mandates/{mandate['id']}",
        headers=auth_headers,
    )
    assert loaded.status_code == 200
    assert loaded.json()["asset_scope"]["asset_class"] == "futures"

    missing_timeline = await client.get(
        "/api/v1/strategy/ai-research/runs/missing/timeline",
        headers=auth_headers,
    )
    assert missing_timeline.status_code == 404


async def test_ai_research_a_version_timeline_api_enforces_owner_scope(client, auth_user):
    user, headers = auth_user
    user_id = await _auth_user_id(auth_user)
    version_service = AIStrategyResearchVersionService()
    first = await version_service.create_from_iteration(
        user_id=user_id,
        run_id="run-api-a",
        workspace_id="workspace-api-a",
        mandate_id=None,
        iteration=_iteration(1, "self.buy()", 0.5, passed=False),
    )
    second = await version_service.create_from_iteration(
        user_id=user_id,
        run_id="run-api-a",
        workspace_id="workspace-api-a",
        mandate_id=None,
        iteration=_iteration(2, "self.buy()\nself.close()", 1.3, passed=True),
    )
    await ResearchPipelineEventService().create_event(
        user_id=user_id,
        run_id="run-api-a",
        workspace_id="workspace-api-a",
        stage="backtesting",
        status="failed",
        summary="回测失败，可定位原因。",
        error="deterministic fixture failure",
    )
    _, other_headers = await register_and_login(client, username="ai-research-a-other")

    timeline = await client.get(
        "/api/v1/strategy/ai-research/runs/run-api-a/timeline",
        headers=headers,
    )
    versions = await client.get(
        "/api/v1/strategy/ai-research/runs/run-api-a/versions",
        headers=headers,
    )
    detail = await client.get(
        f"/api/v1/strategy/ai-research/versions/{second.id}",
        headers=headers,
    )
    comparison = await client.get(
        f"/api/v1/strategy/ai-research/versions/{first.id}/compare/{second.id}",
        headers=headers,
    )
    cross_user = await client.get(
        f"/api/v1/strategy/ai-research/versions/{second.id}",
        headers=other_headers,
    )

    assert user["username"]
    assert timeline.status_code == 200
    assert timeline.json()["items"][0]["error"] == "deterministic fixture failure"
    assert versions.status_code == 200
    assert versions.json()["total"] == 2
    assert detail.status_code == 200
    assert detail.json()["created_at"]
    assert comparison.status_code == 200
    assert comparison.json()["metric_deltas"]["sharpe_ratio"]["delta"] == pytest.approx(0.8)
    assert cross_user.status_code == 404


def _iteration(
    iteration: int,
    code: str,
    sharpe: float,
    *,
    passed: bool,
) -> AIStrategyResearchIteration:
    now = datetime.now(timezone.utc)
    strategy = StrategyResponse(
        id=f"strategy-{iteration}",
        user_id="user-a",
        name=f"策略 {iteration}",
        description="测试策略",
        code=code,
        params={},
        category="custom",
        created_at=now,
        updated_at=now,
    )
    unit = StrategyUnitResponse(
        id=f"unit-{iteration}",
        workspace_id="workspace-v",
        group_name="AI投研",
        strategy_id=strategy.id,
        strategy_name=strategy.name,
        symbol="RB0",
        symbol_name="RB0",
        timeframe="1d",
        timeframe_n=1,
        category="custom",
        created_at=now,
        updated_at=now,
    )
    run_result = StrategyCopilotRunResult(
        unit_id=unit.id,
        task_id=f"task-{iteration}",
        status="completed",
    )
    unit_status = UnitStatusResponse(
        id=unit.id,
        run_status="completed",
        last_task_id=run_result.task_id,
        metrics_snapshot={"sharpe_ratio": sharpe, "total_trades": 3},
    )
    return AIStrategyResearchIteration(
        iteration=iteration,
        strategy=strategy,
        unit=unit,
        run_result=run_result,
        unit_status=unit_status,
        metrics={"sharpe_ratio": sharpe, "total_trades": 3},
        sharpe_ratio=sharpe,
        total_trades=3,
        quality_score=sharpe,
        quality_gate_evaluations=[
            {
                "key": "target_sharpe",
                "label": "Sharpe",
                "actual": sharpe,
                "target": 1.0,
                "direction": "min",
                "passed": passed,
                "score": sharpe,
            }
        ],
        passed=passed,
        failure_reason=None if passed else "Sharpe 未达标",
        quality_gate_failures=[] if passed else ["Sharpe 未达标"],
        diagnostics={"summary": "测试诊断"},
        improvement_plan=["提高过滤条件"],
        improvement_notes=[f"第 {iteration} 轮改稿"],
        next_actions=["继续观察"],
    )


async def _auth_user_id(auth_user) -> str:
    user, _ = auth_user
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.username == user["username"]))
        model = result.scalar_one()
    return model.id
