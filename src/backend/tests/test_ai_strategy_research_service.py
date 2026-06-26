from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest
from httpx import AsyncClient

from app.api.strategy.base import get_ai_strategy_research_service
from app.main import app
from app.schemas.ai_strategy_research import (
    AIStrategyPaperTradingStart,
    AIStrategyPaperTradingStartRequest,
    AIStrategyResearchRunListResponse,
    AIStrategyResearchRunRecord,
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


def _run_record(run_id: str, *, workspace_id: str, completed_at: str):
    return {
        "run_id": run_id,
        "prompt": "生成趋势策略",
        "symbol": "000001.SZ",
        "symbol_name": "平安银行",
        "timeframe": "1d",
        "timeframe_n": 1,
        "status": "achieved",
        "achieved": True,
        "target_sharpe": 1.0,
        "min_total_trades": 1,
        "max_iterations": 3,
        "iteration_count": 2,
        "best_iteration": 2,
        "best_sharpe": 1.21,
        "best_quality_score": 100.0,
        "best_quality_gate_evaluations": [
            {
                "key": "sharpe",
                "label": "Sharpe",
                "actual": 1.21,
                "target": 1.0,
                "direction": "min",
                "passed": True,
                "score": 1.0,
            }
        ],
        "best_metrics": {"sharpe_ratio": 1.21, "total_trades": 5},
        "best_strategy_id": "strategy-2",
        "best_strategy_name": "AI趋势策略",
        "research_workspace_id": workspace_id,
        "paper_workspace_id": "paper-ws",
        "paper_unit_id": "paper-unit",
        "paper_trading_started": True,
        "next_actions": ["继续跟踪模拟交易"],
        "started_at": completed_at,
        "completed_at": completed_at,
        "iterations": [],
    }


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
        self.units: dict[str, StrategyUnitResponse] = {}
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

    async def list_workspaces(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
        workspace_type: str | None = None,
    ):
        items = [
            workspace
            for workspace in self.workspaces.values()
            if workspace_type is None or workspace.workspace_type == workspace_type
        ]
        return len(items), items[skip : skip + limit]

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

    async def get_unit(self, workspace_id: str, unit_id: str, user_id: str):
        unit = self.units.get(unit_id)
        if unit is None or unit.workspace_id != workspace_id:
            return None
        return unit

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
        unit = _unit("paper-unit", workspace_id, strategy).model_copy(
            update={
                "data_config": data.data_config,
                "unit_settings": data.unit_settings,
                "gateway_config": data.gateway_config,
            }
        )
        self.units[unit.id] = unit
        self.created_units.append(unit)
        return unit.model_dump(mode="python")

    async def run_units(self, workspace_id: str, user_id: str, unit_ids: list[str], parallel=False):
        self.started_units.append((workspace_id, unit_ids))
        return [{"unit_id": unit_ids[0], "task_id": "paper-task", "status": "running"}]


class FakeStrategyService:
    def __init__(
        self,
        workspace_service: FakeWorkspaceService,
        metrics_by_round: list[dict[str, Any]],
        *,
        strategies: dict[str, StrategyResponse] | None = None,
    ):
        self.workspace_service = workspace_service
        self.metrics_by_round = metrics_by_round
        self.strategies = strategies or {}
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
        self.workspace_service.units[unit.id] = unit
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

    async def get_strategy(self, strategy_id: str, user_id: str):
        return self.strategies.get(strategy_id)


class FakeInvalidDraftStrategyService:
    def __init__(self) -> None:
        self.backtest_called = False

    async def generate_copilot_draft(self, user_id: str, request):
        draft = build_ai_strategy_draft(request.prompt).model_copy(
            update={"code": "def not_a_strategy():\n    return 1\n"}
        )
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
        self.backtest_called = True
        raise AssertionError("invalid strategy draft should not be submitted to backtest")


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


def test_ai_strategy_draft_class_name_is_valid_with_numeric_goal():
    draft = build_ai_strategy_draft("请生成一个双均线趋势策略，目标夏普率 1.0")

    compile(draft.code, "<strategy>", "exec")
    assert "class AIGeneratedStrategy(bt.Strategy):" in draft.code


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
        quality_gate_failures=["Max drawdown 18.000 exceeds limit 10.000"],
        user_id="user-1",
        request=AIStrategyResearchRunRequest(
            prompt="均线趋势",
            symbol="000001.SZ",
            max_drawdown_limit=10.0,
        ),
    )

    assert router.calls
    payload = json.loads(router.calls[0]["messages"][1]["content"])
    assert payload["quality_gate_failures"] == ["Max drawdown 18.000 exceeds limit 10.000"]
    assert payload["quality_gates"]["max_drawdown_limit"] == 10.0
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
async def test_ai_strategy_improver_falls_back_when_model_code_is_not_strategy():
    draft = build_ai_strategy_draft("请生成一个均线趋势策略")
    improver = AIStrategyImprover(
        ai_router=FakeAIChatRouter(
            """
            {
              "name": "无效策略",
              "description": "invalid",
              "code": "def not_a_strategy():\\n    return 1\\n",
              "notes": ["模型没有返回 Backtrader Strategy 类"]
            }
            """
        ),
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
    assert "not_a_strategy" not in result.draft.code
    assert result.notes[0].startswith("AI模型改稿不可用，已使用本地规则回退")
    assert "must define a class inheriting from bt.Strategy" in result.notes[0]


@pytest.mark.asyncio
async def test_local_strategy_improver_uses_quality_gate_failures():
    draft = build_ai_strategy_draft("请生成一个均线趋势策略")

    result = await LocalStrategyImprover().improve(
        draft,
        iteration=1,
        metrics={"sharpe_ratio": 1.2, "total_trades": 5, "max_drawdown": -0.18},
        target_sharpe=1.0,
        quality_gate_failures=["Max drawdown 18.000 exceeds limit 10.000"],
        request=AIStrategyResearchRunRequest(
            prompt="均线趋势",
            symbol="000001.SZ",
            max_drawdown_limit=10.0,
        ),
    )

    assert result.draft.params["stop_loss_pct"].default == 0.024
    assert any("本轮未通过验收门槛" in note for note in result.notes)


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
    assert result.paper_trading.handoff is not None
    assert result.paper_trading.handoff["run_id"] == result.run_id
    assert result.paper_trading.handoff["research_strategy_id"] == "strategy-2"
    assert result.paper_trading.handoff["paper_unit_id"] == "paper-unit"
    assert result.paper_trading.unit.unit_settings["ai_research_handoff"]["run_id"] == result.run_id
    assert result.paper_trading.unit.data_config["ai_research_run_id"] == result.run_id
    assert (
        result.paper_trading.workspace.settings["ai_research_handoff"]["last_handoff"]["run_id"]
        == result.run_id
    )
    assert workspace_service.started_units == [("paper-ws", ["paper-unit"])]
    assert result.run_id
    assert result.run_record is not None
    assert result.run_record.best_strategy_id == "strategy-2"
    assert result.run_record.paper_trading_started is True
    assert result.run_record.best_quality_score == 100.0
    assert result.run_record.best_quality_gate_evaluations[0]["key"] == "sharpe"
    assert result.next_actions == [
        "策略已通过验收并进入模拟交易，下一步跟踪模拟账户成交、持仓和风控指标。",
        "保留当前研究工作区，后续用样本外区间复核策略稳定性。",
    ]
    assert result.run_record.next_actions == result.next_actions
    assert result.run_record.quality_gates == {
        "target_sharpe": 1.0,
        "min_total_trades": 1,
    }
    assert result.paper_trading.handoff["quality_gates"] == result.run_record.quality_gates
    assert result.research_workspace.settings["ai_research"]["last_run"]["run_id"] == result.run_id
    assert result.research_workspace.settings["ai_research"]["runs"][0]["run_id"] == result.run_id
    assert result.research_workspace.settings["ai_research"]["runs"][0]["iterations"][0][
        "failure_reason"
    ] == "Only 0 trades, below minimum 1"
    assert "系统将基于本轮失败原因生成下一版策略" in result.research_workspace.settings[
        "ai_research"
    ]["runs"][0]["iterations"][0]["next_actions"][-1]


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
    assert result.next_actions[0] == "目标未达成，优先查看最后一轮质量门槛失败原因和改稿说明。"
    assert result.run_record is not None
    assert result.run_record.next_actions == result.next_actions
    assert workspace_service.started_units == []


@pytest.mark.asyncio
async def test_research_loop_selects_quality_scored_best_candidate():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeStrategyService(
        workspace_service,
        [
            {"sharpe_ratio": 1.4, "total_trades": 0},
            {"sharpe_ratio": 0.9, "total_trades": 5},
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
            prompt="请生成一个趋势策略并继续优化",
            symbol="000001.SZ",
            target_sharpe=1.0,
            min_total_trades=1,
            max_iterations=2,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is False
    assert result.best_iteration == 2
    assert result.best_strategy is not None
    assert result.best_strategy.id == "strategy-2"
    assert result.iterations[0].quality_score == 50.0
    assert result.iterations[1].quality_score == 95.0
    assert result.iterations[1].quality_gate_evaluations == [
        {
            "key": "sharpe",
            "label": "Sharpe",
            "actual": 0.9,
            "target": 1.0,
            "direction": "min",
            "passed": False,
            "score": 0.9,
        },
        {
            "key": "total_trades",
            "label": "Total trades",
            "actual": 5.0,
            "target": 1.0,
            "direction": "min",
            "passed": True,
            "score": 1.0,
        },
    ]
    assert result.best_quality_score == 95.0
    assert result.run_record is not None
    assert result.run_record.best_quality_score == 95.0
    assert result.run_record.best_quality_gate_evaluations == result.iterations[1].quality_gate_evaluations


@pytest.mark.asyncio
async def test_research_loop_can_start_from_seed_strategy_without_regenerating():
    workspace_service = FakeWorkspaceService()
    seed_draft = build_ai_strategy_draft("请生成一个均线趋势策略").model_copy(
        update={"name": "上一轮最佳策略"}
    )
    seed_strategy = _strategy("seed-strategy", seed_draft)
    strategy_service = FakeStrategyService(
        workspace_service,
        [{"sharpe_ratio": 1.12, "total_trades": 6}],
        strategies={"seed-strategy": seed_strategy},
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
            prompt="继续优化上一轮最佳策略",
            symbol="000001.SZ",
            target_sharpe=1.0,
            seed_strategy_id="seed-strategy",
            start_paper_trading=False,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is True
    assert strategy_service.generated == 0
    assert strategy_service.submitted_drafts[0].name == "上一轮最佳策略"
    assert strategy_service.submitted_drafts[0].rationale == "Seeded from strategy seed-strategy"
    assert result.run_record is not None
    assert result.run_record.seed_strategy_id == "seed-strategy"
    assert result.run_record.continued_from_run_id is None


@pytest.mark.asyncio
async def test_research_loop_can_continue_from_previous_run_best_strategy():
    workspace_service = FakeWorkspaceService()
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={
            "settings": {
                "ai_research": {
                    "runs": [
                        _run_record(
                            "previous-run",
                            workspace_id="research-ws",
                            completed_at="2026-01-01T00:01:00+00:00",
                        )
                    ]
                }
            }
        }
    )
    seed_draft = build_ai_strategy_draft("请生成一个均线趋势策略").model_copy(
        update={"name": "历史最佳策略"}
    )
    seed_strategy = _strategy("strategy-2", seed_draft)
    strategy_service = FakeStrategyService(
        workspace_service,
        [{"sharpe_ratio": 1.18, "total_trades": 7}],
        strategies={"strategy-2": seed_strategy},
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
            prompt="继续上一轮未完成投研",
            symbol="000001.SZ",
            target_sharpe=1.0,
            continue_from_run_id="previous-run",
            start_paper_trading=False,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is True
    assert result.research_workspace.id == "research-ws"
    assert strategy_service.generated == 0
    assert strategy_service.submitted_drafts[0].name == "历史最佳策略"
    assert result.run_record is not None
    assert result.run_record.seed_strategy_id == "strategy-2"
    assert result.run_record.continued_from_run_id == "previous-run"


@pytest.mark.asyncio
async def test_research_loop_rejects_invalid_generated_strategy_before_backtest():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeInvalidDraftStrategyService()
    service = AIStrategyResearchService(
        strategy_service=strategy_service,
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )

    with pytest.raises(ValueError, match="Generated strategy code validation failed"):
        await service.run(
            "user-1",
            AIStrategyResearchRunRequest(
                prompt="请生成一个无效策略",
                symbol="000001.SZ",
                max_iterations=1,
                poll_interval_seconds=0.1,
            ),
        )

    assert strategy_service.backtest_called is False


@pytest.mark.asyncio
async def test_research_loop_blocks_paper_when_quality_gate_fails():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeStrategyService(
        workspace_service,
        [
            {
                "sharpe_ratio": 1.42,
                "total_trades": 5,
                "max_drawdown": -25.0,
                "total_return": 12.0,
                "win_rate": 60.0,
            },
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
            prompt="请生成一个双均线趋势策略",
            symbol="000001.SZ",
            target_sharpe=1.0,
            max_drawdown_limit=10.0,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is False
    assert result.paper_trading is None
    assert result.iterations[0].passed is False
    assert result.iterations[0].quality_gate_failures == [
        "Max drawdown 25.000 exceeds limit 10.000"
    ]
    assert result.iterations[0].failure_reason == "Max drawdown 25.000 exceeds limit 10.000"
    assert "收紧止损、单笔风险和仓位暴露" in result.iterations[0].next_actions[0]
    assert workspace_service.started_units == []


@pytest.mark.asyncio
async def test_research_loop_quality_gates_accept_ratio_metrics():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeStrategyService(
        workspace_service,
        [
            {
                "sharpe_ratio": 1.42,
                "total_trades": 5,
                "max_drawdown": -0.08,
                "total_return": 0.15,
                "annual_return": 0.12,
                "win_rate": 0.62,
            },
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
            prompt="请生成一个双均线趋势策略",
            symbol="000001.SZ",
            target_sharpe=1.0,
            max_drawdown_limit=10.0,
            min_total_return=10.0,
            min_annual_return=8.0,
            min_win_rate=50.0,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is True
    assert result.paper_trading is not None
    assert result.iterations[0].quality_gate_failures == []
    assert result.run_record is not None
    assert result.run_record.quality_gates["max_drawdown_limit"] == 10.0
    assert result.paper_trading.handoff is not None
    assert result.paper_trading.handoff["quality_gates"] == result.run_record.quality_gates


@pytest.mark.asyncio
async def test_start_paper_trading_from_achieved_research_run_record():
    workspace_service = FakeWorkspaceService()
    seed_draft = build_ai_strategy_draft("请生成一个均线趋势策略").model_copy(
        update={"name": "历史最佳策略"}
    )
    strategy = _strategy("strategy-2", seed_draft)
    research_unit = _unit(
        "unit-2",
        "research-ws",
        strategy,
        metrics={"sharpe_ratio": 1.21, "total_trades": 5},
    )
    workspace_service.units[research_unit.id] = research_unit
    record = {
        **_run_record(
            "previous-run",
            workspace_id="research-ws",
            completed_at="2026-01-01T00:01:00+00:00",
        ),
        "paper_workspace_id": None,
        "paper_unit_id": None,
        "paper_trading_started": False,
        "iterations": [
            {
                "iteration": 2,
                "strategy_id": strategy.id,
                "strategy_name": strategy.name,
                "unit_id": research_unit.id,
                "task_id": "task-2",
                "run_status": "completed",
                "metrics": {"sharpe_ratio": 1.21, "total_trades": 5},
                "sharpe_ratio": 1.21,
                "total_trades": 5,
                "quality_score": 100.0,
                "quality_gate_evaluations": [
                    {
                        "key": "sharpe",
                        "label": "Sharpe",
                        "actual": 1.21,
                        "target": 1.0,
                        "direction": "min",
                        "passed": True,
                        "score": 1.0,
                    }
                ],
                "passed": True,
                "quality_gate_failures": [],
                "improvement_notes": [],
                "next_actions": [],
            }
        ],
    }
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={"settings": {"ai_research": {"runs": [record]}}}
    )
    strategy_service = FakeStrategyService(
        workspace_service,
        [],
        strategies={strategy.id: strategy},
    )
    service = AIStrategyResearchService(
        strategy_service=strategy_service,
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )

    result = await service.start_paper_trading_from_run(
        "user-1",
        "previous-run",
        AIStrategyPaperTradingStartRequest(research_workspace_id="research-ws"),
    )

    assert result.started is True
    assert result.handoff is not None
    assert result.handoff["run_id"] == "previous-run"
    assert result.handoff["research_strategy_id"] == strategy.id
    assert result.handoff["achieved_quality_gate_evaluations"][0]["key"] == "sharpe"
    assert workspace_service.started_units == [("paper-ws", ["paper-unit"])]
    updated_run = workspace_service.workspaces["research-ws"].settings["ai_research"]["runs"][0]
    assert updated_run["run_id"] == "previous-run"
    assert updated_run["paper_trading_started"] is True
    assert updated_run["paper_workspace_id"] == "paper-ws"
    assert updated_run["paper_unit_id"] == "paper-unit"


@pytest.mark.asyncio
async def test_list_research_run_records_reads_workspace_history():
    workspace_service = FakeWorkspaceService()
    workspace_service.workspaces["research-a"] = _workspace("research-a", "research").model_copy(
        update={
            "settings": {
                "ai_research": {
                    "runs": [
                        _run_record(
                            "older-run",
                            workspace_id="research-a",
                            completed_at="2026-01-01T00:00:00+00:00",
                        )
                    ]
                }
            }
        }
    )
    workspace_service.workspaces["research-b"] = _workspace("research-b", "research").model_copy(
        update={
            "settings": {
                "ai_research": {
                    "runs": [
                        _run_record(
                            "newer-run",
                            workspace_id="research-b",
                            completed_at="2026-01-02T00:00:00+00:00",
                        )
                    ]
                }
            }
        }
    )
    workspace_service.workspaces["paper-ws"] = _workspace("paper-ws", "trading")
    service = AIStrategyResearchService(
        strategy_service=FakeStrategyService(workspace_service, []),
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )

    result = await service.list_run_records("user-1", limit=1)

    assert result.total == 2
    assert [item.run_id for item in result.items] == ["newer-run"]

    scoped = await service.list_run_records(
        "user-1",
        research_workspace_id="research-a",
        limit=20,
    )
    assert scoped.total == 1
    assert scoped.items[0].run_id == "older-run"


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

    async def list_run_records(
        self,
        user_id: str,
        *,
        research_workspace_id: str | None = None,
        limit: int = 20,
    ):
        return AIStrategyResearchRunListResponse(
            total=1,
            items=[
                AIStrategyResearchRunRecord.model_validate(
                    _run_record(
                        "api-history-run",
                        workspace_id=research_workspace_id or "research-api-ws",
                        completed_at="2026-01-01T00:01:00+00:00",
                    )
                )
            ],
        )

    async def start_paper_trading_from_run(
        self,
        user_id: str,
        run_id: str,
        request: AIStrategyPaperTradingStartRequest,
    ):
        workspace = _workspace("paper-api-ws", "trading")
        draft = build_ai_strategy_draft("生成一个均线策略")
        strategy = _strategy("strategy-api", draft)
        unit = _unit("paper-api-unit", workspace.id, strategy)
        return AIStrategyPaperTradingStart(
            workspace=workspace,
            unit=unit,
            run_result=StrategyCopilotRunResult(
                unit_id=unit.id,
                task_id="paper-api-task",
                status="running",
            ),
            started=True,
            handoff={
                "run_id": run_id,
                "research_workspace_id": request.research_workspace_id,
                "paper_workspace_id": workspace.id,
                "paper_unit_id": unit.id,
            },
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
    assert payload["next_actions"] == []


@pytest.mark.asyncio
async def test_ai_strategy_research_run_history_endpoint(
    client: AsyncClient,
    auth_headers: dict,
):
    app.dependency_overrides[get_ai_strategy_research_service] = lambda: FakeResearchAPIService()
    try:
        response = await client.get(
            "/api/v1/strategy/ai-research/runs",
            headers=auth_headers,
            params={"research_workspace_id": "research-api-ws", "limit": 5},
        )
    finally:
        app.dependency_overrides.pop(get_ai_strategy_research_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["run_id"] == "api-history-run"
    assert payload["items"][0]["research_workspace_id"] == "research-api-ws"


@pytest.mark.asyncio
async def test_ai_strategy_research_start_paper_from_history_endpoint(
    client: AsyncClient,
    auth_headers: dict,
):
    app.dependency_overrides[get_ai_strategy_research_service] = lambda: FakeResearchAPIService()
    try:
        response = await client.post(
            "/api/v1/strategy/ai-research/runs/api-history-run/paper-trading",
            headers=auth_headers,
            json={"research_workspace_id": "research-api-ws"},
        )
    finally:
        app.dependency_overrides.pop(get_ai_strategy_research_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["started"] is True
    assert payload["workspace"]["id"] == "paper-api-ws"
    assert payload["unit"]["id"] == "paper-api-unit"
    assert payload["handoff"]["run_id"] == "api-history-run"
