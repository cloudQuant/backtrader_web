from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import pytest
from httpx import AsyncClient

from app.api.strategy.base import get_ai_strategy_research_service, get_ai_strategy_research_tasks
from app.main import app
from app.schemas.ai_strategy_research import (
    AIStrategyPaperTradingReview,
    AIStrategyPaperTradingRuleEvaluation,
    AIStrategyPaperTradingStart,
    AIStrategyPaperTradingStartRequest,
    AIStrategyResearchRunListResponse,
    AIStrategyResearchRunRecord,
    AIStrategyResearchRunRequest,
    AIStrategyResearchRunResponse,
)
from app.schemas.strategy import (
    AIStrategyDraft,
    StrategyCopilotBacktestRequest,
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
from app.services.ai_strategy_research_task_manager import AIStrategyResearchTaskManager
from app.services.strategy.ai_draft import build_ai_strategy_draft, render_ai_strategy_draft_answer
from app.services.strategy.core import _runtime_metadata_from_copilot_request


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
        self.updated_units: list[StrategyUnitResponse] = []
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
                "optimization_config": data.optimization_config,
                "gateway_config": data.gateway_config.model_dump(
                    mode="python",
                    exclude_none=True,
                )
                if hasattr(data.gateway_config, "model_dump")
                else data.gateway_config,
            }
        )
        self.units[unit.id] = unit
        self.created_units.append(unit)
        return unit.model_dump(mode="python")

    async def update_unit(self, workspace_id: str, unit_id: str, user_id: str, data):
        unit = self.units.get(unit_id)
        if unit is None or unit.workspace_id != workspace_id:
            return None
        payload = data.model_dump(exclude_unset=True)
        unit = unit.model_copy(update=payload)
        self.units[unit.id] = unit
        self.updated_units.append(unit)
        return unit.model_dump(mode="python")

    async def run_units(self, workspace_id: str, user_id: str, unit_ids: list[str], parallel=False):
        self.started_units.append((workspace_id, unit_ids))
        return [{"unit_id": unit_ids[0], "task_id": "paper-task", "status": "running"}]


class FakePaperStartFailingWorkspaceService(FakeWorkspaceService):
    async def create_unit(self, workspace_id: str, user_id: str, data):
        return None


class FakePaperRunFailingWorkspaceService(FakeWorkspaceService):
    async def run_units(self, workspace_id: str, user_id: str, unit_ids: list[str], parallel=False):
        self.started_units.append((workspace_id, unit_ids))
        return [{"unit_id": unit_ids[0], "task_id": "paper-task", "status": "failed"}]


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
        self.generate_requests: list[Any] = []
        self.submitted_drafts: list[AIStrategyDraft] = []
        self.submitted_backtest_requests: list[Any] = []

    async def generate_copilot_draft(self, user_id: str, request):
        self.generate_requests.append(request)
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
        self.submitted_backtest_requests.append(request)
        strategy = _strategy(f"strategy-{round_index + 1}", request.strategy_draft)
        metrics = self.metrics_by_round[round_index]
        unit = _unit(f"unit-{round_index + 1}", workspace_id, strategy, metrics=metrics).model_copy(
            update={
                "data_config": request.data_config,
                "unit_settings": request.unit_settings,
                "optimization_config": request.optimization_config,
            }
        )
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
    def __init__(self, workspace_service: FakeWorkspaceService) -> None:
        self.workspace_service = workspace_service
        self.backtest_called = False
        self.submitted_drafts: list[AIStrategyDraft] = []

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
        self.submitted_drafts.append(request.strategy_draft)
        assert "not_a_strategy" not in request.strategy_draft.code
        strategy = _strategy("fallback-strategy", request.strategy_draft)
        metrics = {"sharpe_ratio": 1.2, "total_trades": 4, "max_drawdown": -4.0}
        unit = _unit("fallback-unit", workspace_id, strategy, metrics=metrics).model_copy(
            update={
                "data_config": request.data_config,
                "unit_settings": request.unit_settings,
                "optimization_config": request.optimization_config,
            }
        )
        self.workspace_service.units[unit.id] = unit
        self.workspace_service.statuses[unit.id] = UnitStatusResponse(
            id=unit.id,
            run_status="completed",
            last_task_id="fallback-task",
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
                task_id="fallback-task",
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
    assert "suggested_improvement_plan" in payload
    assert any("止损" in item for item in payload["suggested_improvement_plan"])
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
            knowledge_base_id="kb-quant",
            thinking_mode=True,
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
    assert strategy_service.generate_requests[0].knowledge_base_id == "kb-quant"
    assert strategy_service.generate_requests[0].thinking_mode is True
    initial_prompt = strategy_service.generate_requests[0].prompt
    assert initial_prompt.startswith("请生成一个双均线趋势策略，目标夏普率 1.0")
    assert '"target_sharpe": 1.0' in initial_prompt
    assert '"symbol": "000001.SZ"' in initial_prompt
    assert '"rolling_sharpe"' in initial_prompt
    assert "自动回测、评估质量门槛" in initial_prompt
    assert len(result.iterations) == 2
    assert result.iterations[1].improvement_notes
    assert len(strategy_service.submitted_drafts) == 2
    first_draft = strategy_service.submitted_drafts[0]
    assert first_draft.data_source.symbol == "000001.SZ"
    assert first_draft.data_source.symbol_name == "平安银行"
    assert first_draft.data_source.timeframe == "1d"
    assert first_draft.backtest_defaults.initial_cash == pytest.approx(100000.0)
    assert first_draft.backtest_defaults.commission == pytest.approx(0.001)
    assert strategy_service.submitted_drafts[1].name.endswith("v2")
    improved_draft = strategy_service.submitted_drafts[1]
    assert improved_draft.data_source.symbol == "000001.SZ"
    assert improved_draft.backtest_defaults.initial_cash == pytest.approx(100000.0)
    assert improved_draft.suggested_symbol == "000001.SZ"
    assert "模拟交易" in improved_draft.next_steps[2]
    assert result.paper_trading is not None
    assert result.paper_trading.started is True
    assert result.paper_trading.handoff is not None
    assert result.paper_trading.handoff["run_id"] == result.run_id
    assert result.paper_trading.handoff["research_strategy_id"] == "strategy-2"
    assert result.paper_trading.handoff["paper_unit_id"] == "paper-unit"
    assert result.paper_trading.handoff["achieved_diagnostics"]["promotion_ready"] is True
    assert result.paper_trading.handoff["paper_monitoring_plan"][0]["key"] == "rolling_sharpe"
    assert result.paper_trading.unit.unit_settings["ai_research_handoff"]["run_id"] == result.run_id
    assert result.paper_trading.unit.unit_settings["ai_research_handoff"]["paper_task_id"] == "paper-task"
    assert result.paper_trading.unit.data_config["ai_research_run_id"] == result.run_id
    assert workspace_service.updated_units[-1].id == "paper-unit"
    assert workspace_service.updated_units[-1].unit_settings["ai_research_handoff"][
        "paper_task_id"
    ] == "paper-task"
    assert workspace_service.units["paper-unit"].unit_settings["ai_research_handoff"][
        "paper_monitoring_plan"
    ][0]["key"] == "rolling_sharpe"
    assert (
        result.paper_trading.workspace.settings["ai_research_handoff"]["last_handoff"]["run_id"]
        == result.run_id
    )
    assert workspace_service.started_units == [("paper-ws", ["paper-unit"])]
    assert result.run_id
    assert result.iterations[0].diagnostics["failure_categories"] == ["trade_count"]
    assert "有效交易样本数" in result.iterations[0].improvement_plan[0]
    assert result.best_diagnostics["promotion_ready"] is True
    assert result.paper_monitoring_plan[0]["threshold"] == 0.6
    assert result.run_record is not None
    assert result.run_record.knowledge_base_id == "kb-quant"
    assert result.run_record.thinking_mode is True
    assert result.run_record.best_strategy_id == "strategy-2"
    assert result.run_record.paper_trading_started is True
    assert result.run_record.best_quality_score == 100.0
    assert result.run_record.best_diagnostics["promotion_ready"] is True
    assert result.run_record.paper_monitoring_plan == result.paper_monitoring_plan
    assert result.run_record.paper_handoff["paper_task_id"] == "paper-task"
    assert result.run_record.paper_handoff["paper_monitoring_plan"][0]["key"] == "rolling_sharpe"
    assert result.run_record.pipeline["current_stage"] == "paper_trading"
    assert result.run_record.pipeline["steps"][3]["key"] == "paper_trading"
    assert result.run_record.best_quality_gate_evaluations[0]["key"] == "sharpe"
    assert result.next_actions == [
        "策略已通过验收并进入模拟交易，下一步跟踪模拟账户成交、持仓和风控指标。",
        "保留当前研究工作区，后续用样本外区间复核策略稳定性。",
    ]
    assert result.run_record.next_actions == result.next_actions
    assert result.run_record.quality_gates == {
        "target_sharpe": 1.0,
        "min_total_trades": 1,
        "out_of_sample_validation": True,
        "out_of_sample_ratio": 0.25,
        "min_out_of_sample_sharpe": 0.6,
        "min_out_of_sample_trades": 1,
    }
    assert result.paper_trading.handoff["quality_gates"] == result.run_record.quality_gates
    assert result.research_workspace.settings["ai_research"]["last_run"]["run_id"] == result.run_id
    assert result.research_workspace.settings["ai_research"]["runs"][0]["run_id"] == result.run_id
    assert result.research_workspace.settings["ai_research"]["runs"][0]["iterations"][0][
        "failure_reason"
    ] == "Only 0 trades, below minimum 1"
    assert result.research_workspace.settings["ai_research"]["runs"][0]["iterations"][0][
        "diagnostics"
    ]["failure_categories"] == ["trade_count"]
    assert "系统将基于本轮失败原因生成下一版策略" in result.research_workspace.settings[
        "ai_research"
    ]["runs"][0]["iterations"][0]["next_actions"][-1]


@pytest.mark.asyncio
async def test_research_loop_persists_achieved_run_when_paper_start_fails():
    workspace_service = FakePaperStartFailingWorkspaceService()
    strategy_service = FakeStrategyService(
        workspace_service,
        [{"sharpe_ratio": 1.18, "total_trades": 6, "max_drawdown": -4.0}],
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
            prompt="请生成一个趋势策略",
            symbol="000001.SZ",
            target_sharpe=1.0,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is True
    assert result.status == "achieved"
    assert result.paper_trading is None
    assert result.pipeline["current_stage"] == "paper_trading_failed"
    assert result.pipeline["paper_trading_error"] == "Failed to create paper trading unit"
    assert result.pipeline["steps"][3]["status"] == "failed"
    assert any("模拟交易启动错误" in item for item in result.next_actions)
    assert result.run_record is not None
    assert result.run_record.achieved is True
    assert result.run_record.paper_trading_started is False
    assert result.run_record.pipeline["current_stage"] == "paper_trading_failed"
    persisted_run = result.research_workspace.settings["ai_research"]["runs"][0]
    assert persisted_run["run_id"] == result.run_id
    assert persisted_run["achieved"] is True
    assert persisted_run["paper_trading_started"] is False


@pytest.mark.asyncio
async def test_research_loop_persists_achieved_run_when_paper_run_fails():
    workspace_service = FakePaperRunFailingWorkspaceService()
    strategy_service = FakeStrategyService(
        workspace_service,
        [{"sharpe_ratio": 1.18, "total_trades": 6, "max_drawdown": -4.0}],
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
            prompt="请生成一个趋势策略",
            symbol="000001.SZ",
            target_sharpe=1.0,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is True
    assert result.status == "achieved"
    assert result.paper_trading is not None
    assert result.paper_trading.started is False
    assert result.paper_trading.run_result is not None
    assert result.paper_trading.run_result.status == "failed"
    assert result.pipeline["current_stage"] == "paper_trading_failed"
    assert result.pipeline["paper_trading_error"] == "Paper trading run finished with status failed"
    assert result.pipeline["steps"][3]["status"] == "failed"
    assert any("模拟交易启动错误" in item for item in result.next_actions)
    assert result.run_record is not None
    assert result.run_record.paper_trading_started is False
    assert result.run_record.paper_workspace_id == "paper-ws"
    assert result.run_record.paper_unit_id == "paper-unit"
    assert result.run_record.paper_handoff["paper_run_status"] == "failed"
    assert result.run_record.pipeline["current_stage"] == "paper_trading_failed"
    persisted_run = result.research_workspace.settings["ai_research"]["runs"][0]
    assert persisted_run["run_id"] == result.run_id
    assert persisted_run["paper_trading_started"] is False
    assert persisted_run["paper_workspace_id"] == "paper-ws"
    assert persisted_run["paper_unit_id"] == "paper-unit"
    assert persisted_run["paper_handoff"]["paper_run_status"] == "failed"
    assert persisted_run["pipeline"]["current_stage"] == "paper_trading_failed"


@pytest.mark.asyncio
async def test_research_loop_validates_out_of_sample_before_paper_when_dates_are_available():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeStrategyService(
        workspace_service,
        [
            {"sharpe_ratio": 1.32, "total_trades": 12, "max_drawdown": -4.0},
            {"sharpe_ratio": 0.92, "total_trades": 3, "max_drawdown": -2.0},
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
            prompt="请生成一个趋势策略并做样本外验证",
            symbol="000001.SZ",
            symbol_name="平安银行",
            start_date="2024-01-01",
            end_date="2024-01-20",
            target_sharpe=1.0,
            min_total_trades=4,
            min_out_of_sample_sharpe=0.8,
            min_out_of_sample_trades=2,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is True
    assert result.paper_trading is not None
    assert len(strategy_service.submitted_backtest_requests) == 2
    train_request, validation_request = strategy_service.submitted_backtest_requests
    assert train_request.data_config["start_date"] == "2024-01-01"
    assert train_request.data_config["end_date"] == "2024-01-15"
    assert validation_request.data_config["start_date"] == "2024-01-16"
    assert validation_request.data_config["end_date"] == "2024-01-20"
    assert "训练样本" in train_request.group_name
    assert "样本外验证" in validation_request.group_name

    iteration = result.iterations[0]
    assert iteration.passed is True
    assert iteration.validation_status == "passed"
    assert iteration.validation_window == {
        "train_start": "2024-01-01",
        "train_end": "2024-01-15",
        "validation_start": "2024-01-16",
        "validation_end": "2024-01-20",
    }
    assert iteration.validation_metrics["sharpe_ratio"] == pytest.approx(0.92)
    assert [item["key"] for item in iteration.validation_gate_evaluations] == [
        "out_of_sample_sharpe",
        "out_of_sample_total_trades",
    ]
    assert iteration.validation_failures == []
    assert result.paper_trading.handoff is not None
    assert result.paper_trading.handoff["research_strategy_id"] == "strategy-1"
    assert result.paper_trading.handoff["out_of_sample_validation"]["status"] == "passed"
    assert result.run_record is not None
    assert result.run_record.quality_gates["min_out_of_sample_sharpe"] == 0.8
    assert result.run_record.quality_gates["min_out_of_sample_trades"] == 2
    assert result.run_record.paper_handoff["out_of_sample_validation"]["metrics"][
        "sharpe_ratio"
    ] == pytest.approx(0.92)
    assert result.run_record.iterations[0]["validation_task_id"] == "task-2"
    assert result.run_record.iterations[0]["validation_run_status"] == "completed"


@pytest.mark.asyncio
async def test_research_loop_continues_when_out_of_sample_validation_fails():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeStrategyService(
        workspace_service,
        [
            {"sharpe_ratio": 1.2, "total_trades": 8, "max_drawdown": -3.0},
            {"sharpe_ratio": 0.3, "total_trades": 1, "max_drawdown": -2.0},
            {"sharpe_ratio": 1.18, "total_trades": 9, "max_drawdown": -4.0},
            {"sharpe_ratio": 0.95, "total_trades": 3, "max_drawdown": -2.5},
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
            prompt="请生成一个趋势策略并持续优化到样本外达标",
            symbol="000001.SZ",
            start_date="2024-01-01",
            end_date="2024-01-20",
            target_sharpe=1.0,
            min_total_trades=4,
            min_out_of_sample_sharpe=0.8,
            min_out_of_sample_trades=2,
            max_iterations=2,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is True
    assert len(result.iterations) == 2
    assert len(strategy_service.submitted_backtest_requests) == 4
    assert result.iterations[0].passed is False
    assert result.iterations[0].validation_status == "failed"
    assert any(
        "Out-of-sample Sharpe" in failure
        for failure in result.iterations[0].validation_failures
    )
    assert any(
        "Out-of-sample only 1 trades" in failure
        for failure in result.iterations[0].validation_failures
    )
    assert result.iterations[0].diagnostics["promotion_ready"] is False
    assert "sharpe" in result.iterations[0].diagnostics["failure_categories"]
    assert result.iterations[1].passed is True
    assert result.iterations[1].validation_status == "passed"
    assert result.best_strategy is not None
    assert result.best_strategy.id == "strategy-3"
    assert result.paper_trading is not None
    assert result.paper_trading.handoff is not None
    assert result.paper_trading.handoff["research_strategy_id"] == "strategy-3"
    assert result.paper_trading.handoff["out_of_sample_validation"]["status"] == "passed"
    assert result.run_record is not None
    assert result.run_record.iterations[0]["validation_status"] == "failed"
    assert result.run_record.iterations[1]["validation_status"] == "passed"


def test_copilot_workspace_runtime_metadata_extracts_contract_specs():
    draft = build_ai_strategy_draft("请生成一个股指期货趋势策略")
    request = StrategyCopilotBacktestRequest(
        strategy_draft=draft,
        symbol="IF2609",
        data_config={
            "contract_metadata": {
                "IF2609": {
                    "multiplier": 300,
                    "margin_rate": 0.1,
                }
            }
        },
        unit_settings={
            "contract_specs": {
                "CFFEX.IF2609": {
                    "commission_rate": 0.000023,
                }
            }
        },
    )

    metadata = _runtime_metadata_from_copilot_request(request)

    assert metadata["contract_metadata"]["IF2609"]["multiplier"] == 300
    assert metadata["contract_specs"]["CFFEX.IF2609"]["commission_rate"] == 0.000023


@pytest.mark.asyncio
async def test_research_loop_enriches_backtest_with_asset_specs(monkeypatch):
    def fake_resolve_asset_specs(instance, strategy_dir, gateway=None, symbols=None):
        assert "IF2609" in symbols
        return {
            "IF2609": {
                "symbol": "IF2609",
                "source": "local_futures_commission",
                "multiplier": 300,
                "margin_rate": 0.1,
                "commission_rate": 0.000023,
                "close_today_commission_rate": 0.000345,
            }
        }

    monkeypatch.setattr(
        "app.services.ai_strategy_research_service.resolve_asset_specs",
        fake_resolve_asset_specs,
    )
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeStrategyService(
        workspace_service,
        [
            {"sharpe_ratio": 1.2, "total_trades": 5, "max_drawdown": -3.0},
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
            prompt="请生成一个股指期货趋势策略",
            symbol="IF2609",
            target_sharpe=1.0,
            max_iterations=1,
            start_paper_trading=False,
            poll_interval_seconds=0.1,
        ),
    )

    backtest_request = strategy_service.submitted_backtest_requests[0]
    contract_metadata = backtest_request.data_config["contract_metadata"]["IF2609"]
    unit_metadata = backtest_request.unit_settings["contract_metadata"]["IF2609"]
    assert contract_metadata["multiplier"] == 300
    assert unit_metadata["margin_rate"] == 0.1
    assert backtest_request.unit_settings["multiplier"] == 300
    assert backtest_request.unit_settings["margin"] == pytest.approx(0.1)
    assert backtest_request.unit_settings["commission"] == pytest.approx(0.000023)
    assert backtest_request.unit_settings["asset_spec_source"] == "local_futures_commission"
    initial_prompt = strategy_service.generate_requests[0].prompt
    assert '"IF2609"' in initial_prompt
    assert '"multiplier": 300' in initial_prompt
    assert '"commission_source": "asset_specs_or_default"' in initial_prompt
    assert "local_futures_commission" in initial_prompt
    assert strategy_service.submitted_drafts[0].backtest_defaults.commission == pytest.approx(
        0.000023
    )
    assert result.run_record is not None
    assert result.run_record.commission == pytest.approx(0.000023)
    unit_snapshot = result.run_record.iterations[0]["unit_snapshot"]
    assert unit_snapshot["data_config"]["contract_metadata"]["IF2609"]["multiplier"] == 300
    assert unit_snapshot["unit_settings"]["commission"] == pytest.approx(0.000023)
    assert unit_snapshot["unit_settings"]["asset_spec_source"] == "local_futures_commission"


@pytest.mark.asyncio
async def test_research_loop_emits_progress_snapshots():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeStrategyService(
        workspace_service,
        [
            {"sharpe_ratio": 1.2, "total_trades": 5, "max_drawdown": -3.0},
        ],
    )
    service = AIStrategyResearchService(
        strategy_service=strategy_service,
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )
    events: list[dict[str, Any]] = []

    await service.run(
        "user-1",
        AIStrategyResearchRunRequest(
            prompt="请生成一个趋势策略",
            symbol="000001.SZ",
            target_sharpe=1.0,
            max_iterations=2,
            start_paper_trading=False,
            poll_interval_seconds=0.1,
        ),
        progress_callback=events.append,
    )

    stages = [item["current_stage"] for item in events]
    assert stages[:3] == ["initializing", "drafting", "backtesting"]
    assert "evaluating" in stages
    submitted = next(
        item for item in events if item.get("message") == "Backtest task submitted for iteration 1"
    )
    assert submitted["current_backtest_task_id"] == "task-1"
    evaluating = next(item for item in events if item["current_stage"] == "evaluating")
    assert evaluating["current_iteration"] == 1
    assert evaluating["iteration_count"] == 1
    assert evaluating["max_iterations"] == 2
    assert evaluating["latest_iteration"]["sharpe_ratio"] == pytest.approx(1.2)
    assert evaluating["progress"] > 10


@pytest.mark.asyncio
async def test_review_paper_trading_run_evaluates_monitoring_plan():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeStrategyService(
        workspace_service,
        [
            {"sharpe_ratio": 1.18, "total_trades": 6, "max_drawdown": -4.0},
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
            prompt="请生成一个趋势策略",
            symbol="000001.SZ",
            target_sharpe=1.0,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )
    workspace_service.statuses["paper-unit"] = UnitStatusResponse(
        id="paper-unit",
        run_status="running",
        last_task_id="paper-task",
        metrics_snapshot={
            "rolling_sharpe": 0.72,
            "max_drawdown": 4.5,
            "closed_trades": 3,
            "slippage_and_commission_delta": 0.0002,
        },
        trading_snapshot={
            "valuation_status": "confirmed",
            "position_source": "gateway",
            "asset_spec_source": "paper_gateway",
            "valuation_warnings": [],
        },
        run_count=1,
        trading_mode="paper",
    )

    review = await service.review_paper_trading_run("user-1", result.run_id)

    assert review.status == "ready_for_live_candidate"
    assert review.ready_for_live is True
    assert review.paper_workspace_id == "paper-ws"
    assert review.paper_unit_id == "paper-unit"
    assert review.reviewed_at
    assert review.pipeline["current_stage"] == "live_candidate"
    assert review.pipeline["ready_for_live"] is True
    assert [item.status for item in review.evaluations] == [
        "passed",
        "passed",
        "passed",
        "passed",
        "passed",
    ]
    assert review.evaluations[0].source == "unit_status.metrics_snapshot"
    assert review.evaluations[-1].key == "valuation_confidence"
    assert review.evaluations[-1].source == "unit_status.trading_snapshot"
    assert "实盘候选" in review.next_actions[0]
    updated_run = workspace_service.workspaces["research-ws"].settings["ai_research"]["runs"][0]
    assert updated_run["run_id"] == result.run_id
    assert updated_run["paper_review_status"] == "ready_for_live_candidate"
    assert updated_run["paper_review_ready_for_live"] is True
    assert updated_run["paper_reviewed_at"] == review.reviewed_at
    assert updated_run["paper_review_evaluations"][0]["key"] == "rolling_sharpe"
    assert "实盘候选" in updated_run["paper_review_next_actions"][0]
    assert updated_run["pipeline"]["current_stage"] == "live_candidate"
    assert updated_run["pipeline"]["ready_for_live"] is True


@pytest.mark.asyncio
async def test_review_paper_trading_blocks_live_candidate_when_valuation_is_unconfirmed():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeStrategyService(
        workspace_service,
        [
            {"sharpe_ratio": 1.18, "total_trades": 6, "max_drawdown": -4.0},
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
            prompt="请生成一个趋势策略",
            symbol="000001.SZ",
            target_sharpe=1.0,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )
    workspace_service.statuses["paper-unit"] = UnitStatusResponse(
        id="paper-unit",
        run_status="running",
        last_task_id="paper-task",
        metrics_snapshot={
            "rolling_sharpe": 0.72,
            "max_drawdown": 4.5,
            "closed_trades": 3,
            "slippage_and_commission_delta": 0.0002,
        },
        trading_snapshot={
            "valuation_status": "estimated",
            "valuation_warnings": ["手续费未确认，持仓盈亏未扣除真实手续费"],
        },
        run_count=1,
        trading_mode="paper",
    )

    review = await service.review_paper_trading_run("user-1", result.run_id)

    valuation = next(item for item in review.evaluations if item.key == "valuation_confidence")
    assert valuation.status == "failed"
    assert valuation.actual == 0.0
    assert review.status == "needs_research_review"
    assert review.ready_for_live is False
    assert "资产信息" in review.next_actions[0]


@pytest.mark.asyncio
async def test_review_paper_trading_confirms_valuation_from_unit_asset_specs(monkeypatch):
    def fake_resolve_asset_specs(instance, strategy_dir, gateway=None, symbols=None):
        assert "IF2609" in symbols
        return {
            "IF2609": {
                "symbol": "IF2609",
                "source": "local_futures_commission",
                "multiplier": 300,
                "margin_rate": 0.1,
                "commission_rate": 0.002,
            }
        }

    monkeypatch.setattr(
        "app.services.ai_strategy_research_service.resolve_asset_specs",
        fake_resolve_asset_specs,
    )
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeStrategyService(
        workspace_service,
        [
            {"sharpe_ratio": 1.18, "total_trades": 6, "max_drawdown": -4.0},
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
            prompt="请生成一个股指期货趋势策略",
            symbol="IF2609",
            target_sharpe=1.0,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )
    assert result.paper_trading is not None
    assert result.paper_trading.handoff is not None
    assert result.paper_trading.handoff["backtest_environment"]["commission"] == pytest.approx(
        0.002
    )
    assert result.paper_trading.handoff["backtest_environment"]["asset_spec_source"] == (
        "local_futures_commission"
    )
    execution_cost_rule = next(
        item for item in result.paper_monitoring_plan if item["key"] == "execution_cost"
    )
    assert execution_cost_rule["threshold"] == pytest.approx(0.004)
    workspace_service.statuses["paper-unit"] = UnitStatusResponse(
        id="paper-unit",
        run_status="running",
        last_task_id="paper-task",
        metrics_snapshot={
            "rolling_sharpe": 0.72,
            "max_drawdown": 4.5,
            "closed_trades": 3,
            "slippage_and_commission_delta": 0.0002,
        },
        run_count=1,
        trading_mode="paper",
    )

    review = await service.review_paper_trading_run("user-1", result.run_id)

    valuation = next(item for item in review.evaluations if item.key == "valuation_confidence")
    assert valuation.status == "passed"
    assert valuation.actual == 1.0
    assert valuation.source == "unit.unit_settings.contract_metadata"
    assert review.status == "ready_for_live_candidate"
    assert review.ready_for_live is True


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
async def test_research_loop_falls_back_when_seed_strategy_is_invalid():
    workspace_service = FakeWorkspaceService()
    seed_draft = build_ai_strategy_draft("请生成一个均线趋势策略").model_copy(
        update={
            "name": "无效种子策略",
            "code": "def not_a_strategy():\n    return 1\n",
        }
    )
    seed_strategy = _strategy("seed-strategy", seed_draft)
    strategy_service = FakeStrategyService(
        workspace_service,
        [{"sharpe_ratio": 1.16, "total_trades": 6, "max_drawdown": -5.0}],
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
    assert "not_a_strategy" not in strategy_service.submitted_drafts[0].code
    assert "class AIGeneratedStrategy" in strategy_service.submitted_drafts[0].code
    assert result.iterations[0].improvement_notes[0].startswith("种子策略代码不可运行")
    assert result.run_record is not None
    assert result.run_record.seed_strategy_id == "seed-strategy"


@pytest.mark.asyncio
async def test_research_loop_can_continue_from_previous_run_best_strategy():
    workspace_service = FakeWorkspaceService()
    previous_record = {
        **_run_record(
            "previous-run",
            workspace_id="research-ws",
            completed_at="2026-01-01T00:01:00+00:00",
        ),
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "initial_cash": 250000.0,
        "commission": 0.000023,
        "annual_days": 244,
        "calc_method": "log",
        "weight_mode": "value",
    }
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={
            "settings": {
                "ai_research": {
                    "runs": [previous_record]
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
            out_of_sample_validation=False,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is True
    assert result.research_workspace.id == "research-ws"
    assert strategy_service.generated == 0
    assert strategy_service.submitted_drafts[0].name == "历史最佳策略"
    backtest_request = strategy_service.submitted_backtest_requests[0]
    assert backtest_request.data_config["start_date"] == "2024-01-01"
    assert backtest_request.data_config["end_date"] == "2024-12-31"
    assert backtest_request.unit_settings["initial_cash"] == pytest.approx(250000.0)
    assert backtest_request.unit_settings["commission"] == pytest.approx(0.000023)
    assert backtest_request.unit_settings["annual_days"] == 244
    assert backtest_request.unit_settings["calc_method"] == "log"
    assert backtest_request.unit_settings["weight_mode"] == "value"
    assert result.run_record is not None
    assert result.run_record.seed_strategy_id == "strategy-2"
    assert result.run_record.continued_from_run_id == "previous-run"
    assert result.run_record.start_date == "2024-01-01"
    assert result.run_record.commission == pytest.approx(0.000023)


@pytest.mark.asyncio
async def test_research_loop_continuation_improves_failed_research_before_backtest():
    workspace_service = FakeWorkspaceService()
    previous_record = {
        **_run_record(
            "failed-research-run",
            workspace_id="research-ws",
            completed_at="2026-01-01T00:01:00+00:00",
        ),
        "status": "max_iterations_reached",
        "achieved": False,
        "best_iteration": 2,
        "best_sharpe": 0.72,
        "best_metrics": {"sharpe_ratio": 0.72, "total_trades": 4, "max_drawdown": -12.0},
        "next_actions": ["下一轮改稿应直接针对：Sharpe 0.720 below target 1.000"],
        "iterations": [
            {
                "iteration": 2,
                "strategy_id": "strategy-2",
                "strategy_name": "历史未达标策略",
                "unit_id": "unit-2",
                "task_id": "task-2",
                "run_status": "completed",
                "metrics": {"sharpe_ratio": 0.72, "total_trades": 4, "max_drawdown": -12.0},
                "sharpe_ratio": 0.72,
                "total_trades": 4,
                "quality_score": 72.0,
                "quality_gate_evaluations": [],
                "passed": False,
                "failure_reason": "Sharpe 0.720 below target 1.000",
                "quality_gate_failures": ["Sharpe 0.720 below target 1.000"],
                "improvement_plan": ["减少低质量入场，增加趋势/波动过滤。"],
                "improvement_notes": [],
                "next_actions": [],
            }
        ],
    }
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={"settings": {"ai_research": {"runs": [previous_record]}}}
    )
    seed_draft = build_ai_strategy_draft("请生成一个均线趋势策略").model_copy(
        update={"name": "历史未达标策略"}
    )
    seed_strategy = _strategy("strategy-2", seed_draft)
    strategy_service = FakeStrategyService(
        workspace_service,
        [{"sharpe_ratio": 1.12, "total_trades": 6, "max_drawdown": -6.0}],
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
            prompt="继续上一轮未达标投研",
            symbol="000001.SZ",
            target_sharpe=1.0,
            continue_from_run_id="failed-research-run",
            start_paper_trading=False,
            out_of_sample_validation=False,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is True
    assert strategy_service.generated == 0
    assert strategy_service.submitted_drafts[0].name == "历史未达标策略 v1"
    assert "基于上一轮投研未达标原因" in result.iterations[0].improvement_notes[0]
    assert any(
        "Sharpe 0.720 below target 1.000" in note
        for note in result.iterations[0].improvement_notes
    )
    assert result.run_record is not None
    assert result.run_record.continued_from_run_id == "failed-research-run"


@pytest.mark.asyncio
async def test_research_loop_continuation_uses_failed_paper_review_before_backtest():
    workspace_service = FakeWorkspaceService()
    record = {
        **_run_record(
            "paper-failed-run",
            workspace_id="research-ws",
            completed_at="2026-01-01T00:01:00+00:00",
        ),
        "paper_trading_started": True,
        "paper_review_status": "needs_research_review",
        "paper_review_ready_for_live": False,
        "paper_reviewed_at": "2026-01-02T00:00:00+00:00",
        "paper_review_evaluations": [
            {
                "key": "drawdown_guard",
                "label": "模拟交易最大回撤",
                "metric": "max_drawdown",
                "window": "since paper start",
                "direction": "max",
                "threshold": 10.0,
                "actual": 18.0,
                "source": "unit_status.metrics_snapshot",
                "status": "failed",
                "passed": False,
                "action": "停止自动交易并收紧风控。",
            }
        ],
        "paper_review_next_actions": ["停止自动交易并收紧风控。"],
    }
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={"settings": {"ai_research": {"runs": [record]}}}
    )
    seed_draft = build_ai_strategy_draft("请生成一个均线趋势策略").model_copy(
        update={"name": "模拟失败策略"}
    )
    seed_strategy = _strategy("strategy-2", seed_draft)
    strategy_service = FakeStrategyService(
        workspace_service,
        [{"sharpe_ratio": 1.15, "total_trades": 6, "max_drawdown": -8.0}],
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
            prompt="继续模拟失败后的策略投研",
            symbol="000001.SZ",
            target_sharpe=1.0,
            continue_from_run_id="paper-failed-run",
            start_paper_trading=False,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is True
    assert strategy_service.generated == 0
    assert strategy_service.submitted_drafts[0].name.endswith("v1")
    assert "模拟失败策略 v1" == strategy_service.submitted_drafts[0].name
    assert "基于上一轮模拟交易复核结果" in result.iterations[0].improvement_notes[0]
    assert any("止损" in note or "风控" in note for note in result.iterations[0].improvement_notes)
    assert result.run_record is not None
    assert result.run_record.continued_from_run_id == "paper-failed-run"


@pytest.mark.asyncio
async def test_research_loop_continuation_uses_paper_start_failure_before_backtest():
    workspace_service = FakeWorkspaceService()
    pipeline = {
        "current_stage": "paper_trading_failed",
        "status": "achieved",
        "progress": 60,
        "ready_for_live": False,
        "paper_trading_error": "Failed to create paper trading unit",
        "steps": [
            {
                "key": "paper_trading",
                "label": "启动模拟交易",
                "status": "failed",
                "error": "Failed to create paper trading unit",
            }
        ],
    }
    record = {
        **_run_record(
            "paper-start-failed-run",
            workspace_id="research-ws",
            completed_at="2026-01-01T00:01:00+00:00",
        ),
        "paper_trading_started": False,
        "paper_workspace_id": None,
        "paper_unit_id": None,
        "pipeline": pipeline,
        "next_actions": ["模拟交易启动错误：Failed to create paper trading unit"],
    }
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={"settings": {"ai_research": {"runs": [record]}}}
    )
    seed_draft = build_ai_strategy_draft("请生成一个均线趋势策略").model_copy(
        update={"name": "模拟启动失败策略"}
    )
    seed_strategy = _strategy("strategy-2", seed_draft)
    strategy_service = FakeStrategyService(
        workspace_service,
        [{"sharpe_ratio": 1.18, "total_trades": 6, "max_drawdown": -4.0}],
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
            prompt="继续模拟启动失败后的策略投研",
            symbol="000001.SZ",
            target_sharpe=1.0,
            continue_from_run_id="paper-start-failed-run",
            start_paper_trading=False,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is True
    assert strategy_service.generated == 0
    assert strategy_service.submitted_drafts[0].name == "模拟启动失败策略 v1"
    assert "基于上一轮模拟交易启动失败原因" in result.iterations[0].improvement_notes[0]
    assert any("模拟交易启动失败：Failed to create paper trading unit" in note for note in result.iterations[0].improvement_notes)
    assert result.run_record is not None
    assert result.run_record.continued_from_run_id == "paper-start-failed-run"


@pytest.mark.asyncio
async def test_research_loop_falls_back_when_initial_generated_strategy_is_invalid():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeInvalidDraftStrategyService(workspace_service)
    service = AIStrategyResearchService(
        strategy_service=strategy_service,
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )

    result = await service.run(
        "user-1",
        AIStrategyResearchRunRequest(
            prompt="请生成一个无效策略",
            symbol="000001.SZ",
            max_iterations=1,
            poll_interval_seconds=0.1,
            start_paper_trading=False,
        ),
    )

    assert result.achieved is True
    assert strategy_service.backtest_called is True
    assert strategy_service.submitted_drafts
    assert "class AIGeneratedStrategy" in strategy_service.submitted_drafts[0].code
    assert result.iterations[0].improvement_notes[0].startswith("AI初始策略代码不可运行")


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
    assert result.handoff["paper_monitoring_plan"][0]["key"] == "rolling_sharpe"
    assert workspace_service.started_units == [("paper-ws", ["paper-unit"])]
    assert workspace_service.updated_units[-1].unit_settings["ai_research_handoff"][
        "paper_task_id"
    ] == "paper-task"
    updated_run = workspace_service.workspaces["research-ws"].settings["ai_research"]["runs"][0]
    assert updated_run["run_id"] == "previous-run"
    assert updated_run["paper_trading_started"] is True
    assert updated_run["paper_workspace_id"] == "paper-ws"
    assert updated_run["paper_unit_id"] == "paper-unit"
    assert updated_run["paper_monitoring_plan"][0]["key"] == "rolling_sharpe"
    assert updated_run["paper_handoff"]["paper_task_id"] == "paper-task"
    assert updated_run["pipeline"]["current_stage"] == "paper_trading"


@pytest.mark.asyncio
async def test_start_paper_trading_from_history_uses_iteration_unit_snapshot():
    workspace_service = FakeWorkspaceService()
    seed_draft = build_ai_strategy_draft("请生成一个股指期货趋势策略").model_copy(
        update={"name": "历史期货策略"}
    )
    strategy = _strategy("strategy-2", seed_draft)
    unit_snapshot = {
        "id": "missing-research-unit",
        "workspace_id": "research-ws",
        "group_name": "历史期货策略",
        "strategy_id": strategy.id,
        "strategy_name": strategy.name,
        "symbol": "IF2609",
        "symbol_name": "沪深300股指期货",
        "timeframe": "1d",
        "timeframe_n": 1,
        "category": strategy.category,
        "data_config": {
            "symbol": "IF2609",
            "contract_metadata": {
                "IF2609": {
                    "multiplier": 300,
                    "margin_rate": 0.1,
                }
            },
        },
        "unit_settings": {
            "initial_cash": 250000.0,
            "commission": 0.000023,
            "annual_days": 244,
            "calc_method": "log",
            "weight_mode": "value",
            "multiplier": 300,
            "margin": 0.1,
            "asset_spec_source": "local_futures_commission",
        },
        "params": {},
        "optimization_config": {"enabled": False},
        "gateway_config": {"name": "paper_gateway"},
        "trading_mode": "paper",
    }
    record = {
        **_run_record(
            "previous-run",
            workspace_id="research-ws",
            completed_at="2026-01-01T00:01:00+00:00",
        ),
        "symbol": "IF2609",
        "symbol_name": "沪深300股指期货",
        "initial_cash": 250000.0,
        "commission": 0.000023,
        "annual_days": 244,
        "calc_method": "log",
        "weight_mode": "value",
        "best_strategy_id": strategy.id,
        "best_strategy_name": strategy.name,
        "paper_workspace_id": None,
        "paper_unit_id": None,
        "paper_trading_started": False,
        "iterations": [
            {
                "iteration": 2,
                "strategy_id": strategy.id,
                "strategy_name": strategy.name,
                "unit_id": "missing-research-unit",
                "unit_snapshot": unit_snapshot,
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
    created_unit = workspace_service.created_units[-1]
    assert created_unit.data_config["contract_metadata"]["IF2609"]["multiplier"] == 300
    assert created_unit.unit_settings["commission"] == pytest.approx(0.000023)
    assert created_unit.unit_settings["multiplier"] == 300
    assert created_unit.unit_settings["margin"] == pytest.approx(0.1)
    assert created_unit.unit_settings["asset_spec_source"] == "local_futures_commission"
    assert created_unit.optimization_config == {"enabled": False}
    assert created_unit.gateway_config == {"name": "paper_gateway", "params": {}}
    assert result.handoff["backtest_environment"]["commission"] == pytest.approx(0.000023)
    assert result.handoff["backtest_environment"]["multiplier"] == 300
    assert result.handoff["backtest_environment"]["asset_spec_source"] == (
        "local_futures_commission"
    )


@pytest.mark.asyncio
async def test_start_paper_trading_from_history_persists_start_failure():
    workspace_service = FakePaperStartFailingWorkspaceService()
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
                "quality_gate_evaluations": [],
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

    with pytest.raises(ValueError, match="Failed to create paper trading unit"):
        await service.start_paper_trading_from_run(
            "user-1",
            "previous-run",
            AIStrategyPaperTradingStartRequest(research_workspace_id="research-ws"),
        )

    updated_run = workspace_service.workspaces["research-ws"].settings["ai_research"]["runs"][0]
    assert updated_run["run_id"] == "previous-run"
    assert updated_run["paper_trading_started"] is False
    assert updated_run["pipeline"]["current_stage"] == "paper_trading_failed"
    assert updated_run["pipeline"]["paper_trading_error"] == "Failed to create paper trading unit"
    assert updated_run["pipeline"]["steps"][3]["status"] == "failed"
    assert "模拟交易启动错误" in updated_run["next_actions"][0]
    assert "继续投研" in updated_run["next_actions"][-1]


@pytest.mark.asyncio
async def test_start_paper_trading_from_history_persists_run_failure():
    workspace_service = FakePaperRunFailingWorkspaceService()
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

    assert result.started is False
    assert result.run_result is not None
    assert result.run_result.status == "failed"
    assert workspace_service.started_units == [("paper-ws", ["paper-unit"])]
    updated_run = workspace_service.workspaces["research-ws"].settings["ai_research"]["runs"][0]
    assert updated_run["run_id"] == "previous-run"
    assert updated_run["paper_trading_started"] is False
    assert updated_run["paper_workspace_id"] == "paper-ws"
    assert updated_run["paper_unit_id"] == "paper-unit"
    assert updated_run["paper_handoff"]["paper_run_status"] == "failed"
    assert updated_run["pipeline"]["current_stage"] == "paper_trading_failed"
    assert (
        updated_run["pipeline"]["paper_trading_error"]
        == "Paper trading run finished with status failed"
    )
    assert updated_run["pipeline"]["steps"][3]["status"] == "failed"
    assert "模拟交易启动错误" in updated_run["next_actions"][0]


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
    assert result.items[0].pipeline["current_stage"] == "paper_trading"
    assert result.items[0].pipeline["progress"] > 0

    scoped = await service.list_run_records(
        "user-1",
        research_workspace_id="research-a",
        limit=20,
    )
    assert scoped.total == 1
    assert scoped.items[0].run_id == "older-run"
    assert scoped.items[0].pipeline["current_stage"] == "paper_trading"


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

    async def review_paper_trading_run(
        self,
        user_id: str,
        run_id: str,
        *,
        research_workspace_id: str | None = None,
    ):
        workspace = _workspace("paper-api-ws", "trading")
        draft = build_ai_strategy_draft("生成一个均线策略")
        strategy = _strategy("strategy-api", draft)
        unit = _unit("paper-api-unit", workspace.id, strategy)
        return AIStrategyPaperTradingReview(
            run_id=run_id,
            research_workspace_id=research_workspace_id or "research-api-ws",
            paper_workspace_id=workspace.id,
            paper_unit_id=unit.id,
            paper_trading_started=True,
            workspace=workspace,
            unit=unit,
            unit_status=UnitStatusResponse(
                id=unit.id,
                run_status="running",
                metrics_snapshot={"rolling_sharpe": 0.8},
                trading_mode="paper",
            ),
            monitoring_plan=[
                {
                    "key": "rolling_sharpe",
                    "label": "模拟交易滚动 Sharpe",
                    "metric": "rolling_sharpe",
                    "window": "30 trading days",
                    "direction": "min",
                    "threshold": 0.6,
                    "action": "继续观察",
                }
            ],
            evaluations=[
                AIStrategyPaperTradingRuleEvaluation(
                    key="rolling_sharpe",
                    label="模拟交易滚动 Sharpe",
                    metric="rolling_sharpe",
                    window="30 trading days",
                    direction="min",
                    threshold=0.6,
                    actual=0.8,
                    source="unit_status.metrics_snapshot",
                    status="passed",
                    passed=True,
                    action="继续观察",
                )
            ],
            ready_for_live=True,
            status="ready_for_live_candidate",
            reviewed_at="2026-01-01T00:02:00+00:00",
            pipeline={
                "current_stage": "live_candidate",
                "status": "achieved",
                "progress": 100,
                "ready_for_live": True,
                "steps": [],
            },
            next_actions=["模拟交易监控计划已全部通过，可作为实盘候选进入人工复核。"],
        )


class SlowResearchAPIService:
    async def run(
        self,
        user_id: str,
        request: AIStrategyResearchRunRequest,
        *,
        progress_callback=None,
    ):
        if progress_callback is not None:
            await progress_callback(
                {
                    "current_stage": "backtesting",
                    "progress": 25.0,
                    "current_iteration": 1,
                    "iteration_count": 0,
                    "max_iterations": request.max_iterations,
                    "current_backtest_task_id": "child-backtest-task",
                    "message": "slow fake backtest",
                }
            )
        await asyncio.sleep(60)
        raise AssertionError("slow research task should have been cancelled")


class FakeBacktestCancelService:
    def __init__(self) -> None:
        self.cancelled: list[tuple[str, str]] = []

    async def cancel_task(self, task_id: str, user_id: str) -> bool:
        self.cancelled.append((task_id, user_id))
        return True


@pytest.mark.asyncio
async def test_ai_strategy_research_task_manager_runs_task_and_scopes_user():
    manager = AIStrategyResearchTaskManager()

    submitted = await manager.submit(
        "user-1",
        AIStrategyResearchRunRequest(prompt="生成趋势策略", symbol="000001.SZ"),
        service=FakeResearchAPIService(),
    )

    assert submitted.status == "pending"
    task = None
    for _ in range(20):
        task = await manager.get_task("user-1", submitted.task_id)
        if task is not None and task.status == "completed":
            break
        await asyncio.sleep(0.01)

    assert task is not None
    assert task.status == "completed"
    assert task.run_id == "api-run"
    assert task.progress == 100.0
    assert task.current_stage == "completed"
    assert task.iteration_count == 1
    assert task.max_iterations == 3
    assert task.latest_iteration is not None
    assert task.latest_iteration["iteration"] == 1
    assert task.result is not None
    assert task.result.achieved is True
    assert await manager.get_task("other-user", submitted.task_id) is None

    tasks = await manager.list_tasks("user-1")
    assert [item.task_id for item in tasks] == [submitted.task_id]
    assert await manager.list_tasks("user-1", active_only=True) == []


@pytest.mark.asyncio
async def test_ai_strategy_research_task_manager_cancels_running_task():
    backtest_service = FakeBacktestCancelService()
    manager = AIStrategyResearchTaskManager(backtest_service_factory=lambda: backtest_service)
    submitted = await manager.submit(
        "user-1",
        AIStrategyResearchRunRequest(prompt="生成趋势策略", symbol="000001.SZ"),
        service=SlowResearchAPIService(),
    )

    running = None
    for _ in range(20):
        running = await manager.get_task("user-1", submitted.task_id)
        if running is not None and running.current_stage == "backtesting":
            break
        await asyncio.sleep(0.01)

    assert running is not None
    assert running.status == "running"
    assert running.progress == pytest.approx(25.0)
    assert running.current_backtest_task_id == "child-backtest-task"

    cancelled = await manager.cancel_task("user-1", submitted.task_id)
    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert cancelled.current_stage == "cancelled"
    assert cancelled.cancelled_backtest_task_id == "child-backtest-task"
    assert cancelled.child_cancelled is True
    assert backtest_service.cancelled == [("child-backtest-task", "user-1")]
    assert await manager.cancel_task("other-user", submitted.task_id) is None

    final = None
    for _ in range(20):
        final = await manager.get_task("user-1", submitted.task_id)
        if final is not None and final.status == "cancelled":
            break
        await asyncio.sleep(0.01)
    assert final is not None
    assert final.status == "cancelled"
    assert final.completed_at


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
async def test_ai_strategy_research_task_api_endpoint(
    client: AsyncClient,
    auth_headers: dict,
):
    backtest_service = FakeBacktestCancelService()
    task_manager = AIStrategyResearchTaskManager(backtest_service_factory=lambda: backtest_service)
    app.dependency_overrides[get_ai_strategy_research_service] = lambda: FakeResearchAPIService()
    app.dependency_overrides[get_ai_strategy_research_tasks] = lambda: task_manager
    try:
        response = await client.post(
            "/api/v1/strategy/ai-research/tasks",
            headers=auth_headers,
            json={
                "prompt": "生成一个均线策略并优化到夏普率 1.0",
                "symbol": "000001.SZ",
                "target_sharpe": 1.0,
                "max_iterations": 2,
            },
        )
        assert response.status_code == 202
        task_id = response.json()["task_id"]
        list_response = await client.get(
            "/api/v1/strategy/ai-research/tasks",
            headers=auth_headers,
            params={"active_only": False, "limit": 5},
        )
        assert list_response.status_code == 200
        list_payload = list_response.json()
        assert list_payload["total"] == 1
        assert list_payload["items"][0]["task_id"] == task_id
        payload = None
        for _ in range(20):
            status_response = await client.get(
                f"/api/v1/strategy/ai-research/tasks/{task_id}",
                headers=auth_headers,
            )
            assert status_response.status_code == 200
            payload = status_response.json()
            if payload["status"] == "completed":
                break
            await asyncio.sleep(0.01)
    finally:
        app.dependency_overrides.pop(get_ai_strategy_research_service, None)
        app.dependency_overrides.pop(get_ai_strategy_research_tasks, None)

    assert payload is not None
    assert payload["status"] == "completed"
    assert payload["run_id"] == "api-run"
    assert payload["progress"] == 100.0
    assert payload["current_stage"] == "completed"
    assert payload["iteration_count"] == 1
    assert payload["max_iterations"] == 2
    assert payload["latest_iteration"]["iteration"] == 1
    assert payload["result"]["achieved"] is True
    assert payload["result"]["research_workspace"]["id"] == "research-api-ws"


@pytest.mark.asyncio
async def test_ai_strategy_research_task_cancel_endpoint(
    client: AsyncClient,
    auth_headers: dict,
):
    backtest_service = FakeBacktestCancelService()
    task_manager = AIStrategyResearchTaskManager(backtest_service_factory=lambda: backtest_service)
    app.dependency_overrides[get_ai_strategy_research_service] = lambda: SlowResearchAPIService()
    app.dependency_overrides[get_ai_strategy_research_tasks] = lambda: task_manager
    try:
        response = await client.post(
            "/api/v1/strategy/ai-research/tasks",
            headers=auth_headers,
            json={
                "prompt": "生成一个均线策略并优化到夏普率 1.0",
                "symbol": "000001.SZ",
                "target_sharpe": 1.0,
                "max_iterations": 2,
            },
        )
        assert response.status_code == 202
        task_id = response.json()["task_id"]
        for _ in range(20):
            status_response = await client.get(
                f"/api/v1/strategy/ai-research/tasks/{task_id}",
                headers=auth_headers,
            )
            assert status_response.status_code == 200
            if status_response.json()["current_stage"] == "backtesting":
                break
            await asyncio.sleep(0.01)

        cancel_response = await client.post(
            f"/api/v1/strategy/ai-research/tasks/{task_id}/cancel",
            headers=auth_headers,
        )
    finally:
        app.dependency_overrides.pop(get_ai_strategy_research_service, None)
        app.dependency_overrides.pop(get_ai_strategy_research_tasks, None)

    assert cancel_response.status_code == 200
    payload = cancel_response.json()
    assert payload["status"] == "cancelled"
    assert payload["current_stage"] == "cancelled"
    assert payload["cancelled_backtest_task_id"] == "child-backtest-task"
    assert payload["child_cancelled"] is True
    assert payload["completed_at"]
    assert backtest_service.cancelled
    assert backtest_service.cancelled[0][0] == "child-backtest-task"
    assert backtest_service.cancelled[0][1]


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


@pytest.mark.asyncio
async def test_ai_strategy_research_paper_review_endpoint(
    client: AsyncClient,
    auth_headers: dict,
):
    app.dependency_overrides[get_ai_strategy_research_service] = lambda: FakeResearchAPIService()
    try:
        response = await client.get(
            "/api/v1/strategy/ai-research/runs/api-history-run/paper-trading/review",
            headers=auth_headers,
            params={"research_workspace_id": "research-api-ws"},
        )
    finally:
        app.dependency_overrides.pop(get_ai_strategy_research_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready_for_live_candidate"
    assert payload["ready_for_live"] is True
    assert payload["evaluations"][0]["metric"] == "rolling_sharpe"
    assert payload["evaluations"][0]["status"] == "passed"
