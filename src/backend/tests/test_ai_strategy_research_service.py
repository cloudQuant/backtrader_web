from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from httpx import AsyncClient

from app.api.strategy.base import get_ai_strategy_research_service
from app.main import app
from app.schemas.ai_strategy_research import (
    AIStrategyResearchRunRequest,
    AIStrategyResearchRunResponse,
)
from app.schemas.strategy import (
    AIStrategyDraft,
    StrategyCopilotBacktestResponse,
    StrategyCopilotDraftResponse,
    StrategyCopilotRunResult,
    StrategyResponse,
)
from app.schemas.workspace import StrategyUnitResponse, UnitStatusResponse, WorkspaceResponse
from app.services.ai_router.preferences import ResolvedAIModelPreference
from app.services.ai_router.router import ChatCompletionResponse
from app.services.ai_strategy_research_service import (
    AIStrategyImprover,
    AIStrategyResearchService,
    LocalStrategyImprover,
)
from app.services.strategy.ai_draft import build_ai_strategy_draft, render_ai_strategy_draft_answer


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _workspace(workspace_id: str, workspace_type: str) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=workspace_id,
        user_id="user-1",
        name=workspace_id,
        workspace_type=workspace_type,
        settings={},
        trading_config={},
        unit_count=0,
        completed_count=0,
        status="idle",
        created_at=_now(),
        updated_at=_now(),
    )


def _strategy(strategy_id: str, draft: AIStrategyDraft) -> StrategyResponse:
    return StrategyResponse(
        id=strategy_id,
        user_id="user-1",
        name=draft.name,
        description=draft.description,
        code=draft.code,
        params=draft.params,
        category=draft.category,
        created_at=_now(),
        updated_at=_now(),
    )


def _unit(
    unit_id: str,
    workspace_id: str,
    strategy: StrategyResponse,
    *,
    metrics: dict[str, Any] | None = None,
) -> StrategyUnitResponse:
    return StrategyUnitResponse(
        id=unit_id,
        workspace_id=workspace_id,
        group_name=strategy.name,
        strategy_id=strategy.id,
        strategy_name=strategy.name,
        symbol="000001.SZ",
        symbol_name="平安银行",
        timeframe="1d",
        timeframe_n=1,
        category=strategy.category,
        data_config={"symbol": "000001.SZ"},
        unit_settings={"initial_cash": 100000.0, "commission": 0.001},
        params={name: spec.default for name, spec in strategy.params.items()},
        optimization_config={},
        trading_mode="paper",
        gateway_config={},
        run_status="completed" if metrics else "idle",
        run_count=1 if metrics else 0,
        metrics_snapshot=metrics or {},
        created_at=_now(),
        updated_at=_now(),
    )


class FakeWorkspaceService:
    def __init__(self) -> None:
        self.workspaces: dict[str, WorkspaceResponse] = {}
        self.statuses: dict[str, UnitStatusResponse] = {}
        self.created_units: list[StrategyUnitResponse] = []
        self.started_units: list[tuple[str, list[str]]] = []
        self.updated_workspaces: list[WorkspaceResponse] = []

    async def create_workspace(self, user_id: str, data):
        workspace_id = "paper-ws" if data.workspace_type == "trading" else "research-ws"
        workspace = _workspace(workspace_id, data.workspace_type)
        self.workspaces[workspace.id] = workspace
        return workspace

    async def get_workspace(self, workspace_id: str, user_id: str):
        return self.workspaces.get(workspace_id)

    async def update_workspace(self, workspace_id: str, user_id: str, data):
        workspace = self.workspaces.get(workspace_id)
        if workspace is None:
            return None
        settings = dict(workspace.settings or {})
        payload = data.model_dump(exclude_unset=True)
        if isinstance(payload.get("settings"), dict):
            settings.update(payload["settings"])
        workspace = workspace.model_copy(update={"settings": settings})
        self.workspaces[workspace.id] = workspace
        self.updated_workspaces.append(workspace)
        return workspace

    async def get_units_status(self, workspace_id: str, user_id: str):
        return list(self.statuses.values())

    async def create_unit(self, workspace_id: str, user_id: str, data):
        strategy = StrategyResponse(
            id=data.strategy_id or "strategy-paper",
            user_id=user_id,
            name=data.strategy_name,
            description="paper",
            code="import backtrader as bt\nclass Paper(bt.Strategy): pass",
            params={},
            category=data.category,
            created_at=_now(),
            updated_at=_now(),
        )
        unit = _unit("paper-unit", workspace_id, strategy)
        self.created_units.append(unit)
        return unit.model_dump(mode="python")

    async def run_units(self, workspace_id: str, user_id: str, unit_ids: list[str], parallel=False):
        self.started_units.append((workspace_id, unit_ids))
        return [{"unit_id": unit_ids[0], "task_id": "paper-task", "status": "running"}]


class FakeStrategyService:
    def __init__(self, workspace_service: FakeWorkspaceService, metrics_by_round: list[dict[str, Any]]):
        self.workspace_service = workspace_service
        self.metrics_by_round = metrics_by_round
        self.generated = 0
        self.submitted_drafts: list[AIStrategyDraft] = []

    async def generate_copilot_draft(self, user_id: str, request):
        draft = build_ai_strategy_draft(request.prompt)
        self.generated += 1
        return StrategyCopilotDraftResponse(
            answer=render_ai_strategy_draft_answer(draft),
            strategy_draft=draft,
            citations=[],
            context_chunks_used=0,
            tokens_used=0,
            model_id=None,
            reasoning=None,
        )

    async def backtest_copilot_draft(self, user_id: str, workspace_id: str, request):
        round_index = len(self.submitted_drafts)
        self.submitted_drafts.append(request.strategy_draft)
        strategy = _strategy(f"strategy-{round_index + 1}", request.strategy_draft)
        metrics = self.metrics_by_round[round_index]
        unit = _unit(f"unit-{round_index + 1}", workspace_id, strategy, metrics=metrics)
        self.workspace_service.statuses[unit.id] = UnitStatusResponse(
            id=unit.id,
            run_status="completed",
            last_task_id=f"task-{round_index + 1}",
            metrics_snapshot=metrics,
            run_count=1,
            trading_mode="paper",
        )
        return StrategyCopilotBacktestResponse(
            workspace_id=workspace_id,
            created_strategy=True,
            strategy=strategy,
            unit=unit,
            run_result=StrategyCopilotRunResult(
                unit_id=unit.id,
                task_id=f"task-{round_index + 1}",
                status="running",
            ),
            unit_status=None,
            report_ready=False,
            report=None,
        )


async def _noop_sleep(_: float) -> None:
    return None


class FakePreferenceService:
    async def resolve_for_user(self, user_id: str | None):
        return ResolvedAIModelPreference(
            provider="openai_compatible",
            model="research-model",
            base_url="http://local-ai",
            api_key="test-key",
            configured=True,
        )


class FakeAISettings:
    AI_CHAT_ENABLED = False
    AI_CHAT_TIMEOUT = 10.0
    AI_CHAT_TEMPERATURE = 0.2
    AI_CHAT_MODEL = ""
    AI_CHAT_BASE_URL = ""
    AI_CHAT_API_KEY = ""


class FakeAIChatRouter:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, Any]] = []

    async def chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        return ChatCompletionResponse(
            content=self.content,
            model="research-model",
            provider="fake",
            total_tokens=123,
        )


@pytest.mark.asyncio
async def test_ai_strategy_improver_uses_model_json_to_rewrite_strategy():
    draft = build_ai_strategy_draft("请生成一个均线趋势策略")
    router = FakeAIChatRouter(
        """
        {
          "name": "AI改进趋势策略",
          "description": "AI revised strategy",
          "code": "import backtrader as bt\\nclass ImprovedStrategy(bt.Strategy):\\n    params = (('risk_pct', 0.01),)\\n    def next(self):\\n        pass\\n",
          "params": {
            "risk_pct": {"type": "float", "default": 0.01, "min": 0.001, "max": 0.05, "description": "risk"}
          },
          "category": "trend",
          "assumptions": ["使用日线趋势过滤"],
          "risk_points": ["需要样本外验证"],
          "next_steps": ["继续回测"],
          "notes": ["重写了策略结构"]
        }
        """
    )
    improver = AIStrategyImprover(
        ai_router=router,
        preference_service=FakePreferenceService(),
        settings=FakeAISettings(),
    )

    result = await improver.improve(
        draft,
        iteration=1,
        metrics={"sharpe_ratio": 0.2, "total_trades": 3},
        target_sharpe=1.0,
        user_id="user-1",
        request=AIStrategyResearchRunRequest(prompt="均线趋势", symbol="000001.SZ"),
    )

    assert router.calls
    assert result.draft.name == "AI改进趋势策略"
    assert "class ImprovedStrategy" in result.draft.code
    assert result.draft.params["risk_pct"].default == 0.01
    assert result.notes[0] == "AI模型 research-model 改稿"
    assert "重写了策略结构" in result.notes


@pytest.mark.asyncio
async def test_ai_strategy_improver_falls_back_when_model_payload_is_invalid():
    draft = build_ai_strategy_draft("请生成一个均线趋势策略")
    improver = AIStrategyImprover(
        ai_router=FakeAIChatRouter("not json"),
        preference_service=FakePreferenceService(),
        settings=FakeAISettings(),
    )

    result = await improver.improve(
        draft,
        iteration=1,
        metrics={"sharpe_ratio": 0.2, "total_trades": 0},
        target_sharpe=1.0,
        user_id="user-1",
        request=AIStrategyResearchRunRequest(prompt="均线趋势", symbol="000001.SZ"),
    )

    assert result.draft.name.endswith("v2")
    assert result.notes[0].startswith("AI模型改稿不可用，已使用本地规则回退")
    assert any("调整均线窗口" in note for note in result.notes)


@pytest.mark.asyncio
async def test_research_loop_improves_until_sharpe_target_then_starts_paper():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeStrategyService(
        workspace_service,
        [
            {"sharpe_ratio": 1.42, "total_trades": 0, "max_drawdown": -12.0},
            {"sharpe_ratio": 1.21, "total_trades": 5, "max_drawdown": -6.0},
        ],
    )
    service = AIStrategyResearchService(
        strategy_service=strategy_service,
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )

    result = await service.run(
        "user-1",
        AIStrategyResearchRunRequest(
            prompt="请生成一个双均线趋势策略，目标夏普率 1.0",
            symbol="000001.SZ",
            symbol_name="平安银行",
            target_sharpe=1.0,
            max_iterations=3,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is True
    assert result.status == "achieved"
    assert result.best_iteration == 2
    assert result.best_strategy is not None
    assert result.best_strategy.id == "strategy-2"
    assert len(result.iterations) == 2
    assert result.iterations[1].improvement_notes
    assert len(strategy_service.submitted_drafts) == 2
    assert strategy_service.submitted_drafts[1].name.endswith("v2")
    assert result.paper_trading is not None
    assert result.paper_trading.started is True
    assert workspace_service.started_units == [("paper-ws", ["paper-unit"])]
    assert result.run_id
    assert result.run_record is not None
    assert result.run_record.best_strategy_id == "strategy-2"
    assert result.run_record.paper_trading_started is True
    assert result.research_workspace.settings["ai_research"]["last_run"]["run_id"] == result.run_id
    assert result.research_workspace.settings["ai_research"]["runs"][0]["run_id"] == result.run_id
    assert result.research_workspace.settings["ai_research"]["runs"][0]["iterations"][0][
        "failure_reason"
    ] == "Only 0 trades, below minimum 1"


@pytest.mark.asyncio
async def test_research_loop_stops_after_max_iterations_without_paper():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeStrategyService(
        workspace_service,
        [
            {"sharpe_ratio": 0.1, "total_trades": 1},
            {"sharpe_ratio": 0.2, "total_trades": 1},
        ],
    )
    service = AIStrategyResearchService(
        strategy_service=strategy_service,
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )

    result = await service.run(
        "user-1",
        AIStrategyResearchRunRequest(
            prompt="请生成一个 RSI 策略",
            symbol="000001.SZ",
            target_sharpe=1.0,
            max_iterations=2,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is False
    assert result.status == "max_iterations_reached"
    assert result.paper_trading is None
    assert workspace_service.started_units == []


class FakeResearchAPIService:
    async def run(self, user_id: str, request: AIStrategyResearchRunRequest):
        workspace = _workspace("research-api-ws", "research")
        draft = build_ai_strategy_draft(request.prompt)
        strategy = _strategy("strategy-api", draft)
        unit = _unit(
            "unit-api",
            workspace.id,
            strategy,
            metrics={"sharpe_ratio": 1.05, "total_trades": 4},
        )
        return AIStrategyResearchRunResponse(
            run_id="api-run",
            status="achieved",
            achieved=True,
            target_sharpe=request.target_sharpe,
            started_at="2026-01-01T00:00:00+00:00",
            completed_at="2026-01-01T00:01:00+00:00",
            best_iteration=1,
            best_metrics={"sharpe_ratio": 1.05, "total_trades": 4},
            research_workspace=workspace,
            iterations=[
                {
                    "iteration": 1,
                    "strategy": strategy,
                    "unit": unit,
                    "run_result": {
                        "unit_id": unit.id,
                        "task_id": "task-api",
                        "status": "completed",
                    },
                    "unit_status": {
                        "id": unit.id,
                        "run_status": "completed",
                        "metrics_snapshot": {"sharpe_ratio": 1.05, "total_trades": 4},
                    },
                    "metrics": {"sharpe_ratio": 1.05, "total_trades": 4},
                    "sharpe_ratio": 1.05,
                    "total_trades": 4,
                    "passed": True,
                }
            ],
            best_strategy=strategy,
            paper_trading=None,
            message="Target Sharpe 1.000 achieved",
        )


@pytest.mark.asyncio
async def test_ai_strategy_research_api_endpoint(client: AsyncClient, auth_headers: dict):
    app.dependency_overrides[get_ai_strategy_research_service] = lambda: FakeResearchAPIService()
    try:
        response = await client.post(
            "/api/v1/strategy/ai-research/run",
            headers=auth_headers,
            json={
                "prompt": "生成一个均线策略并优化到夏普率 1.0",
                "symbol": "000001.SZ",
                "target_sharpe": 1.0,
                "max_iterations": 2,
            },
        )
    finally:
        app.dependency_overrides.pop(get_ai_strategy_research_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["achieved"] is True
    assert payload["run_id"] == "api-run"
    assert payload["research_workspace"]["id"] == "research-api-ws"
    assert payload["iterations"][0]["sharpe_ratio"] == 1.05
