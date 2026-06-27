from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import AsyncClient

from app.api.strategy.base import get_ai_strategy_research_service, get_ai_strategy_research_tasks
from app.main import app
from app.schemas.ai_strategy_research import (
    AIStrategyLiveHandoffApprovalRecord,
    AIStrategyLiveHandoffApprovalRequest,
    AIStrategyLiveHandoffPackage,
    AIStrategyLiveTradingPrepareRequest,
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
    StrategyImprovement,
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
        self.stopped_units: list[tuple[str, list[str]]] = []
        self.updated_workspaces: list[WorkspaceResponse] = []

    async def create_workspace(self, user_id: str, data):
        workspace_id = "paper-ws" if data.workspace_type == "trading" else "research-ws"
        workspace = _workspace(workspace_id, data.workspace_type).model_copy(
            update={
                "name": data.name,
                "description": data.description,
            }
        )
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
        unit_id = "live-unit" if data.trading_mode == "live" else "paper-unit"
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
        unit = _unit(unit_id, workspace_id, strategy).model_copy(
            update={
                "data_config": data.data_config,
                "unit_settings": data.unit_settings,
                "optimization_config": data.optimization_config,
                "trading_mode": data.trading_mode,
                "lock_trading": data.lock_trading,
                "lock_running": data.lock_running,
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

    async def stop_units(self, workspace_id: str, user_id: str, unit_ids: list[str]):
        self.stopped_units.append((workspace_id, unit_ids))
        for unit_id in unit_ids:
            unit = self.units.get(unit_id)
            if unit is not None and unit.workspace_id == workspace_id:
                self.units[unit_id] = unit.model_copy(update={"run_status": "cancelled"})
        return [{"unit_id": unit_id, "cancelled": True} for unit_id in unit_ids]


class FakePaperStartFailingWorkspaceService(FakeWorkspaceService):
    async def create_unit(self, workspace_id: str, user_id: str, data):
        return None


class FakePaperRunFailingWorkspaceService(FakeWorkspaceService):
    async def run_units(self, workspace_id: str, user_id: str, unit_ids: list[str], parallel=False):
        self.started_units.append((workspace_id, unit_ids))
        return [{"unit_id": unit_ids[0], "task_id": "paper-task", "status": "failed"}]


class FakePaperRunTimeoutWorkspaceService(FakeWorkspaceService):
    async def run_units(self, workspace_id: str, user_id: str, unit_ids: list[str], parallel=False):
        self.started_units.append((workspace_id, unit_ids))
        return [{"unit_id": unit_ids[0], "task_id": "paper-task", "status": "timeout"}]


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

    async def create_strategy(self, user_id: str, strategy_create):
        draft = build_ai_strategy_draft("保存AI投研草案").model_copy(
            update={
                "name": strategy_create.name,
                "description": strategy_create.description or "",
                "code": strategy_create.code,
                "params": strategy_create.params,
                "category": strategy_create.category,
            }
        )
        strategy = _strategy(f"saved-strategy-{len(self.strategies) + 1}", draft)
        self.strategies[strategy.id] = strategy
        return strategy


class FakePendingBacktestStrategyService(FakeStrategyService):
    async def backtest_copilot_draft(self, user_id: str, workspace_id: str, request):
        round_index = len(self.submitted_drafts)
        self.submitted_drafts.append(request.strategy_draft)
        self.submitted_backtest_requests.append(request)
        strategy = _strategy(f"strategy-{round_index + 1}", request.strategy_draft)
        unit = _unit(f"unit-{round_index + 1}", workspace_id, strategy).model_copy(
            update={
                "data_config": request.data_config,
                "unit_settings": request.unit_settings,
                "optimization_config": request.optimization_config,
                "run_status": "running",
            }
        )
        self.workspace_service.units[unit.id] = unit
        task_id = f"task-{round_index + 1}"
        return StrategyCopilotBacktestResponse(
            workspace_id=workspace_id,
            created_strategy=True,
            strategy=strategy,
            unit=unit,
            run_result=StrategyCopilotRunResult(
                unit_id=unit.id,
                task_id=task_id,
                status="running",
            ),
            unit_status=UnitStatusResponse(
                id=unit.id,
                run_status="running",
                last_task_id=task_id,
                metrics_snapshot={},
                run_count=0,
                trading_mode="paper",
            ),
            report_ready=False,
            report=None,
        )


class FakeBlockingDraftGenerationStrategyService(FakeStrategyService):
    def __init__(self, workspace_service: FakeWorkspaceService):
        super().__init__(workspace_service, [])
        self.started = asyncio.Event()

    async def generate_copilot_draft(self, user_id: str, request):
        self.generate_requests.append(request)
        self.started.set()
        await asyncio.sleep(60)
        raise AssertionError("blocking draft generation should have been cancelled")


class FakeBlockingBacktestSubmitStrategyService(FakeStrategyService):
    def __init__(self, workspace_service: FakeWorkspaceService):
        super().__init__(workspace_service, [])
        self.started = asyncio.Event()

    async def backtest_copilot_draft(self, user_id: str, workspace_id: str, request):
        self.submitted_drafts.append(request.strategy_draft)
        self.submitted_backtest_requests.append(request)
        self.started.set()
        await asyncio.sleep(60)
        raise AssertionError("blocking backtest submission should have been cancelled")


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


class FakeRuntimeInvalidDraftStrategyService(FakeInvalidDraftStrategyService):
    async def generate_copilot_draft(self, user_id: str, request):
        draft = build_ai_strategy_draft(request.prompt).model_copy(
            update={
                "code": (
                    "import backtrader as bt\n"
                    "x = missing_research_runtime_name\n"
                    "class LooksValidStrategy(bt.Strategy):\n"
                    "    def next(self):\n"
                    "        pass\n"
                )
            }
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


class FakeValidationSubmitFailingStrategyService(FakeStrategyService):
    async def backtest_copilot_draft(self, user_id: str, workspace_id: str, request):
        if self.submitted_backtest_requests:
            self.submitted_backtest_requests.append(request)
            return None
        return await super().backtest_copilot_draft(user_id, workspace_id, request)


class FakeBacktestSubmitFailingStrategyService(FakeStrategyService):
    def __init__(
        self,
        workspace_service: FakeWorkspaceService,
        metrics_by_round: list[dict[str, Any]],
        *,
        fail_count: int,
    ) -> None:
        super().__init__(workspace_service, metrics_by_round)
        self.fail_count = fail_count

    async def backtest_copilot_draft(self, user_id: str, workspace_id: str, request):
        if len(self.submitted_backtest_requests) < self.fail_count:
            self.submitted_backtest_requests.append(request)
            return None
        return await super().backtest_copilot_draft(user_id, workspace_id, request)


class FakeDraftFailingStrategyService(FakeStrategyService):
    async def generate_copilot_draft(self, user_id: str, request):
        self.generate_requests.append(request)
        raise RuntimeError("knowledge base unavailable")


class InvalidThenRepairingImprover:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def improve(
        self,
        draft: AIStrategyDraft,
        *,
        iteration: int,
        metrics: dict[str, Any],
        target_sharpe: float,
        quality_gate_failures: list[str] | None = None,
        user_id: str | None = None,
        request: AIStrategyResearchRunRequest | None = None,
    ) -> StrategyImprovement:
        self.calls.append(
            {
                "iteration": iteration,
                "metrics": metrics,
                "quality_gate_failures": list(quality_gate_failures or []),
            }
        )
        if len(self.calls) == 1:
            return StrategyImprovement(
                draft=draft.model_copy(
                    deep=True,
                    update={
                        "name": "无效改稿",
                        "code": "def not_a_strategy():\n    return 1\n",
                    },
                ),
                notes=["故意返回无效代码以触发回测前修复"],
            )
        repaired = build_ai_strategy_draft(
            request.prompt if request is not None else "请生成一个均线趋势策略"
        ).model_copy(update={"name": "修复后策略"})
        return StrategyImprovement(draft=repaired, notes=["修复策略代码后继续回测"])


class FailingImprover:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def improve(
        self,
        draft: AIStrategyDraft,
        *,
        iteration: int,
        metrics: dict[str, Any],
        target_sharpe: float,
        quality_gate_failures: list[str] | None = None,
        user_id: str | None = None,
        request: AIStrategyResearchRunRequest | None = None,
    ) -> StrategyImprovement:
        self.calls.append(
            {
                "iteration": iteration,
                "metrics": metrics,
                "quality_gate_failures": list(quality_gate_failures or []),
            }
        )
        raise RuntimeError("improver backend unavailable")


class RecordingImprover:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.local = LocalStrategyImprover()

    async def improve(
        self,
        draft: AIStrategyDraft,
        *,
        iteration: int,
        metrics: dict[str, Any],
        target_sharpe: float,
        quality_gate_failures: list[str] | None = None,
        user_id: str | None = None,
        request: AIStrategyResearchRunRequest | None = None,
    ) -> StrategyImprovement:
        self.calls.append(
            {
                "iteration": iteration,
                "metrics": dict(metrics),
                "quality_gate_failures": list(quality_gate_failures or []),
            }
        )
        return await self.local.improve(
            draft,
            iteration=iteration,
            metrics=metrics,
            target_sharpe=target_sharpe,
            quality_gate_failures=quality_gate_failures,
            user_id=user_id,
            request=request,
        )


class BlockingImprover:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def improve(
        self,
        draft: AIStrategyDraft,
        *,
        iteration: int,
        metrics: dict[str, Any],
        target_sharpe: float,
        quality_gate_failures: list[str] | None = None,
        user_id: str | None = None,
        request: AIStrategyResearchRunRequest | None = None,
    ) -> StrategyImprovement:
        self.started.set()
        await asyncio.sleep(60)
        raise AssertionError("blocking improver should have been cancelled")


class BlockingSleep:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def __call__(self, _: float) -> None:
        self.started.set()
        await asyncio.sleep(60)


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
async def test_ai_strategy_improver_uses_model_json_to_rewrite_strategy(monkeypatch):
    def fake_resolve_asset_specs(instance, strategy_dir, gateway=None, symbols=None):
        assert "IF2609" in symbols
        return {
            "IF2609": {
                "multiplier": 300,
                "margin_rate": 0.1,
                "commission_rate": 0.000023,
                "source": "test_contract_metadata",
            }
        }

    monkeypatch.setattr(
        "app.services.ai_strategy_research_service.resolve_asset_specs",
        fake_resolve_asset_specs,
    )
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
            symbol="IF2609",
            max_drawdown_limit=10.0,
            data_config={
                "contract_metadata": {
                    "IF2609": {
                        "multiplier": 300,
                        "margin_rate": 0.1,
                        "commission_rate": 0.000023,
                        "source": "test_contract_metadata",
                    }
                }
            },
        ),
    )

    assert router.calls
    payload = json.loads(router.calls[0]["messages"][1]["content"])
    assert payload["quality_gate_failures"] == ["Max drawdown 18.000 exceeds limit 10.000"]
    assert payload["quality_gates"]["max_drawdown_limit"] == 10.0
    assert payload["asset_specs"]["IF2609"]["multiplier"] == 300
    assert payload["asset_specs"]["IF2609"]["commission_rate"] == pytest.approx(0.000023)
    assert payload["backtest_environment"]["commission"] == pytest.approx(0.000023)
    assert payload["backtest_environment"]["multiplier"] == 300
    assert "suggested_improvement_plan" in payload
    assert any("止损" in item for item in payload["suggested_improvement_plan"])
    assert result.draft.name == "AI改进趋势策略"
    assert "class ImprovedStrategy" in result.draft.code
    assert result.draft.params["risk_pct"].default == 0.01
    assert result.notes[0] == "AI模型 research-model 改稿"
    assert "重写了策略结构" in result.notes


@pytest.mark.asyncio
async def test_ai_strategy_improver_plans_for_valuation_context_failures():
    draft = build_ai_strategy_draft("请生成一个股指期货策略")
    router = FakeAIChatRouter(
        """
        {
          "name": "估值修正策略",
          "description": "AI revised strategy",
          "code": "import backtrader as bt\\nclass ValuationAwareStrategy(bt.Strategy):\\n    params = (('risk_pct', 0.01),)\\n    def next(self):\\n        pass\\n",
          "params": {
            "risk_pct": {"type": "float", "default": 0.01, "min": 0.001, "max": 0.05, "description": "risk"}
          },
          "category": "trend",
          "assumptions": ["使用已确认资产规格"],
          "risk_points": ["需要核对合约乘数"],
          "next_steps": ["继续回测"],
          "notes": ["补充估值上下文"]
        }
        """
    )
    improver = AIStrategyImprover(
        ai_router=router,
        preference_service=FakePreferenceService(),
        settings=FakeAISettings(),
    )

    await improver.improve(
        draft,
        iteration=1,
        metrics={"sharpe_ratio": 0.9, "total_trades": 20},
        target_sharpe=1.0,
        quality_gate_failures=[
            "估值与资产规格确认 paper review failed: 0.000 / 1.000 (min); "
            "action: 持仓估值、合约乘数、保证金或手续费未确认。"
        ],
        user_id="user-1",
        request=AIStrategyResearchRunRequest(
            prompt="股指期货策略",
            symbol="IF2609",
            data_config={
                "contract_metadata": {
                    "IF2609": {
                        "multiplier": 300,
                        "margin_rate": 0.1,
                        "commission_rate": 0.000023,
                        "source": "paper_handoff_exchange_specs",
                    }
                }
            },
        ),
    )

    payload = json.loads(router.calls[0]["messages"][1]["content"])
    assert any(
        "资产规格" in item and "估值" in item
        for item in payload["suggested_improvement_plan"]
    )
    assert payload["asset_specs"]["IF2609"]["multiplier"] == 300


@pytest.mark.asyncio
async def test_ai_strategy_improver_prefers_structured_research_feedback_plan():
    draft = build_ai_strategy_draft("请生成一个样本外稳健策略")
    router = FakeAIChatRouter(
        """
        {
          "name": "样本外稳健策略",
          "description": "AI revised strategy",
          "code": "import backtrader as bt\\nclass RobustStrategy(bt.Strategy):\\n    params = (('risk_pct', 0.01),)\\n    def next(self):\\n        pass\\n",
          "params": {
            "risk_pct": {"type": "float", "default": 0.01, "min": 0.001, "max": 0.05, "description": "risk"}
          },
          "category": "trend",
          "notes": ["使用结构化诊断计划"]
        }
        """
    )
    improver = AIStrategyImprover(
        ai_router=router,
        preference_service=FakePreferenceService(),
        settings=FakeAISettings(),
    )

    await improver.improve(
        draft,
        iteration=1,
        metrics={
            "sharpe_ratio": 1.2,
            "total_trades": 8,
            "out_of_sample_sharpe": 0.3,
            "research_feedback": {
                "failure_categories": ["out_of_sample", "sharpe"],
                "weaknesses": ["Out-of-sample Sharpe 未达标"],
                "improvement_plan": ["根据样本外失败降低过拟合并扩大验证样本"],
                "promotion_ready": False,
                "out_of_sample_validation": {
                    "status": "failed",
                    "failures": ["Out-of-sample Sharpe 0.300 below target 0.800"],
                },
            },
        },
        target_sharpe=1.0,
        quality_gate_failures=["Out-of-sample Sharpe 0.300 below target 0.800"],
        user_id="user-1",
        request=AIStrategyResearchRunRequest(prompt="样本外稳健策略", symbol="000001.SZ"),
    )

    payload = json.loads(router.calls[0]["messages"][1]["content"])
    assert payload["research_feedback"]["failure_categories"] == ["out_of_sample", "sharpe"]
    assert payload["research_feedback"]["out_of_sample_validation"]["status"] == "failed"
    assert payload["suggested_improvement_plan"] == ["根据样本外失败降低过拟合并扩大验证样本"]
    assert payload["previous_metrics"]["out_of_sample_sharpe"] == pytest.approx(0.3)


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
async def test_ai_strategy_improver_falls_back_when_model_code_fails_sandbox_execution():
    draft = build_ai_strategy_draft("请生成一个均线趋势策略")
    improver = AIStrategyImprover(
        ai_router=FakeAIChatRouter(
            """
            {
              "name": "裸Strategy策略",
              "description": "invalid runtime",
              "code": "class BareStrategy(Strategy):\\n    def next(self):\\n        pass\\n",
              "notes": ["模型返回了沙箱无法执行的裸 Strategy 基类"]
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
    assert "BareStrategy" not in result.draft.code
    assert result.notes[0].startswith("AI模型改稿不可用，已使用本地规则回退")
    assert "sandbox validation failed" in result.notes[0]
    assert "Undefined name" in result.notes[0]


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
async def test_local_strategy_improver_becomes_conservative_after_regression():
    draft = build_ai_strategy_draft("请生成一个均线趋势策略")

    result = await LocalStrategyImprover().improve(
        draft,
        iteration=2,
        metrics={
            "sharpe_ratio": 0.61,
            "total_trades": 5,
            "iteration_progress": {
                "status": "regressed",
                "previous_iteration": 1,
                "sharpe_delta": -0.21,
            },
        },
        target_sharpe=1.0,
        quality_gate_failures=["Sharpe 0.610 below target 1.000"],
        request=AIStrategyResearchRunRequest(prompt="均线趋势", symbol="000001.SZ"),
    )

    assert result.draft.params["risk_pct"].default == pytest.approx(0.013)
    assert result.draft.params["take_profit_pct"].default == pytest.approx(0.0824)
    assert result.draft.params["fast_period"].default == 10
    assert result.draft.params["slow_period"].default == 31
    assert any("保守修复" in note for note in result.notes)
    assert "('risk_pct', 0.013)" in result.draft.code


@pytest.mark.asyncio
async def test_local_strategy_improver_expands_signal_changes_after_stall():
    draft = build_ai_strategy_draft("请生成一个均线趋势策略")

    result = await LocalStrategyImprover().improve(
        draft,
        iteration=2,
        metrics={
            "sharpe_ratio": 0.82,
            "total_trades": 5,
            "iteration_progress": {
                "status": "stalled",
                "previous_iteration": 1,
                "sharpe_delta": 0.0,
            },
        },
        target_sharpe=1.0,
        quality_gate_failures=["Sharpe 0.820 below target 1.000"],
        request=AIStrategyResearchRunRequest(prompt="均线趋势", symbol="000001.SZ"),
    )

    assert result.draft.params["risk_pct"].default == pytest.approx(0.016)
    assert result.draft.params["take_profit_pct"].default == pytest.approx(0.092)
    assert result.draft.params["fast_period"].default == 9
    assert result.draft.params["slow_period"].default == 33
    assert any("基本停滞" in note for note in result.notes)
    assert "('fast_period', 9)" in result.draft.code


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
            backtest_timeout_seconds=1200,
            poll_interval_seconds=0.1,
            gateway_config={
                "name": "paper_gateway",
                "params": {"exchange": "sim"},
            },
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
    assert result.paper_trading.handoff["gateway_config"] == {
        "name": "paper_gateway",
        "params": {"exchange": "sim"},
    }
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
    assert result.run_record.backtest_timeout_seconds == pytest.approx(1200)
    assert result.run_record.poll_interval_seconds == pytest.approx(0.1)
    assert result.run_record.paper_trading_started is True
    assert result.run_record.best_quality_score == 100.0
    assert result.run_record.best_diagnostics["promotion_ready"] is True
    assert result.run_record.paper_monitoring_plan == result.paper_monitoring_plan
    assert result.run_record.paper_handoff["paper_task_id"] == "paper-task"
    assert result.run_record.paper_handoff["gateway_config"]["params"]["exchange"] == "sim"
    assert result.run_record.paper_handoff["paper_monitoring_plan"][0]["key"] == "rolling_sharpe"
    assert result.run_record.paper_review_status == "monitoring"
    assert result.run_record.paper_review_ready_for_live is False
    assert result.run_record.paper_reviewed_at
    assert result.run_record.paper_review_evaluations[0]["key"] == "rolling_sharpe"
    assert result.run_record.paper_review_evaluations[0]["status"] == "pending"
    assert "继续收集模拟交易数据" in result.run_record.paper_review_next_actions[0]
    assert result.pipeline["current_stage"] == "paper_review"
    assert result.run_record.pipeline["current_stage"] == "paper_review"
    assert result.run_record.pipeline["steps"][3]["key"] == "paper_trading"
    assert result.run_record.pipeline["steps"][4]["review_status"] == "monitoring"
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
    assert result.paper_trading.handoff["backtest_timeout_seconds"] == 1200
    assert result.paper_trading.handoff["poll_interval_seconds"] == 0.1
    assert result.research_workspace.settings["ai_research"]["last_run"]["run_id"] == result.run_id
    assert result.research_workspace.settings["ai_research"]["runs"][0]["run_id"] == result.run_id
    assert (
        result.research_workspace.settings["ai_research"]["runs"][0]["paper_review_status"]
        == "monitoring"
    )
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
async def test_research_run_record_redacts_gateway_secrets_in_paper_handoff():
    workspace_service = FakeWorkspaceService()
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
            gateway_config={
                "name": "paper_gateway",
                "api_key": "real-api-key",
                "params": {
                    "secret_key": "real-secret",
                    "passphrase": "real-passphrase",
                    "exchange": "sim",
                    "broker_id": "9999",
                },
            },
        ),
    )

    assert result.paper_trading is not None
    assert result.paper_trading.handoff["gateway_config"]["api_key"] == "real-api-key"
    assert result.run_record is not None
    record_gateway = result.run_record.paper_handoff["gateway_config"]
    assert record_gateway["api_key"] == "***"
    assert record_gateway["params"]["secret_key"] == "***"
    assert record_gateway["params"]["passphrase"] == "***"
    assert record_gateway["params"]["exchange"] == "sim"
    assert record_gateway["params"]["broker_id"] == "9999"
    persisted_run = workspace_service.workspaces["research-ws"].settings["ai_research"]["runs"][0]
    persisted_gateway = persisted_run["paper_handoff"]["gateway_config"]
    assert persisted_gateway["api_key"] == "***"
    assert persisted_gateway["params"]["secret_key"] == "***"
    assert persisted_gateway["params"]["passphrase"] == "***"
    assert persisted_gateway["params"]["exchange"] == "sim"


@pytest.mark.asyncio
async def test_research_loop_falls_back_when_initial_draft_generation_fails():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeDraftFailingStrategyService(
        workspace_service,
        [{"sharpe_ratio": 1.18, "total_trades": 6, "max_drawdown": -4.0}],
    )
    service = AIStrategyResearchService(
        strategy_service=strategy_service,
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )
    progress_events: list[dict[str, Any]] = []

    result = await service.run(
        "user-1",
        AIStrategyResearchRunRequest(
            prompt="请生成一个双均线趋势策略",
            symbol="000001.SZ",
            knowledge_base_id="kb-broken",
            thinking_mode=True,
            target_sharpe=1.0,
            start_paper_trading=False,
            out_of_sample_validation=False,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
        progress_callback=progress_events.append,
    )

    assert result.achieved is True
    assert result.status == "achieved"
    assert strategy_service.generate_requests[0].knowledge_base_id == "kb-broken"
    assert strategy_service.generate_requests[0].thinking_mode is True
    assert strategy_service.submitted_drafts
    assert "class AIGeneratedStrategy" in strategy_service.submitted_drafts[0].code
    assert result.iterations[0].improvement_notes[0].startswith("AI初始策略生成失败")
    assert any(event["current_stage"] == "draft_generation_failed" for event in progress_events)
    assert any(event.get("run_id") == result.run_id for event in progress_events)
    assert any(
        event.get("research_workspace_id") == result.research_workspace.id
        for event in progress_events
    )
    assert result.run_record is not None
    assert result.run_record.knowledge_base_id == "kb-broken"
    assert result.research_workspace.settings["ai_research"]["runs"][0]["run_id"] == result.run_id


@pytest.mark.asyncio
async def test_research_loop_falls_back_when_improver_fails():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeStrategyService(
        workspace_service,
        [
            {"sharpe_ratio": 0.25, "total_trades": 0, "max_drawdown": -8.0},
            {"sharpe_ratio": 1.18, "total_trades": 6, "max_drawdown": -4.0},
        ],
    )
    improver = FailingImprover()
    service = AIStrategyResearchService(
        strategy_service=strategy_service,
        workspace_service=workspace_service,
        improver=improver,
        sleep=_noop_sleep,
    )

    result = await service.run(
        "user-1",
        AIStrategyResearchRunRequest(
            prompt="请生成一个双均线趋势策略",
            symbol="000001.SZ",
            target_sharpe=1.0,
            start_paper_trading=False,
            out_of_sample_validation=False,
            max_iterations=2,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is True
    assert result.status == "achieved"
    assert result.best_iteration == 2
    assert len(improver.calls) == 1
    assert len(strategy_service.submitted_drafts) == 2
    assert result.iterations[1].improvement_notes[0].startswith(
        "AI投研改稿失败，已使用本地规则回退"
    )
    assert result.run_record is not None
    assert result.run_record.status == "achieved"


@pytest.mark.asyncio
async def test_research_loop_tracks_iteration_progress_for_next_improvement():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeStrategyService(
        workspace_service,
        [
            {"sharpe_ratio": 0.82, "total_trades": 4, "max_drawdown": -4.0},
            {"sharpe_ratio": 0.61, "total_trades": 3, "max_drawdown": -6.0},
            {"sharpe_ratio": 0.7, "total_trades": 3, "max_drawdown": -5.0},
        ],
    )
    improver = RecordingImprover()
    service = AIStrategyResearchService(
        strategy_service=strategy_service,
        workspace_service=workspace_service,
        improver=improver,
        sleep=_noop_sleep,
    )

    result = await service.run(
        "user-1",
        AIStrategyResearchRunRequest(
            prompt="请生成一个双均线趋势策略",
            symbol="000001.SZ",
            target_sharpe=1.0,
            start_paper_trading=False,
            out_of_sample_validation=False,
            max_iterations=3,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is False
    assert len(result.iterations) == 3
    assert result.iterations[0].diagnostics["iteration_progress"]["status"] == "baseline"
    assert result.iterations[1].diagnostics["iteration_progress"]["status"] == "regressed"
    assert result.iterations[1].diagnostics["iteration_progress"]["previous_iteration"] == 1
    assert result.iterations[1].diagnostics["iteration_progress"]["sharpe_delta"] == pytest.approx(
        -0.21
    )
    assert "退化" in result.iterations[1].improvement_plan[0]
    assert len(improver.calls) == 2
    assert improver.calls[0]["metrics"]["iteration_progress"]["status"] == "baseline"
    assert improver.calls[0]["metrics"]["research_feedback"]["promotion_ready"] is False
    assert "sharpe" in improver.calls[0]["metrics"]["failure_categories"]
    assert any("Sharpe" in item for item in improver.calls[0]["metrics"]["weaknesses"])
    assert any("收益波动比" in item for item in improver.calls[0]["metrics"]["improvement_plan"])
    assert improver.calls[1]["metrics"]["iteration_progress"]["status"] == "regressed"
    assert improver.calls[1]["metrics"]["iteration_progress"]["previous_iteration"] == 1
    assert improver.calls[1]["metrics"]["research_feedback"]["iteration_progress"]["status"] == (
        "regressed"
    )
    assert strategy_service.submitted_drafts[2].params["risk_pct"].default == pytest.approx(0.013)
    assert strategy_service.submitted_drafts[2].params["slow_period"].default == 31
    assert any("回退到当前最佳第 1 轮策略" in note for note in result.iterations[2].improvement_notes)
    assert result.run_record is not None
    persisted_second = result.research_workspace.settings["ai_research"]["runs"][0]["iterations"][1]
    assert persisted_second["diagnostics"]["iteration_progress"]["status"] == "regressed"
    assert persisted_second["improvement_plan"][0].startswith("本轮自动改稿相对上一轮退化")


@pytest.mark.asyncio
async def test_research_loop_repairs_invalid_improved_strategy_before_backtest():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeStrategyService(
        workspace_service,
        [
            {"sharpe_ratio": 0.2, "total_trades": 5, "max_drawdown": -4.0},
            {"sharpe_ratio": 1.2, "total_trades": 6, "max_drawdown": -3.0},
        ],
    )
    improver = InvalidThenRepairingImprover()
    service = AIStrategyResearchService(
        strategy_service=strategy_service,
        workspace_service=workspace_service,
        improver=improver,
        sleep=_noop_sleep,
    )
    progress_events: list[dict[str, Any]] = []

    result = await service.run(
        "user-1",
        AIStrategyResearchRunRequest(
            prompt="请生成一个双均线趋势策略",
            symbol="000001.SZ",
            target_sharpe=1.0,
            start_paper_trading=False,
            out_of_sample_validation=False,
            max_iterations=2,
            poll_interval_seconds=0.1,
        ),
        progress_callback=progress_events.append,
    )

    assert result.achieved is True
    assert result.best_iteration == 2
    assert len(strategy_service.submitted_drafts) == 2
    assert "not_a_strategy" not in strategy_service.submitted_drafts[1].code
    assert strategy_service.submitted_drafts[1].name == "修复后策略"
    assert len(improver.calls) == 2
    assert any(
        "Strategy code validation failed before backtest" in failure
        for failure in improver.calls[1]["quality_gate_failures"]
    )
    assert any(event["current_stage"] == "repairing_code" for event in progress_events)
    assert any(
        "第 2 轮回测前策略代码校验失败" in note
        for note in result.iterations[1].improvement_notes
    )
    assert result.run_record is not None
    assert result.run_record.status == "achieved"


@pytest.mark.asyncio
async def test_research_loop_continues_after_backtest_submission_failure():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeBacktestSubmitFailingStrategyService(
        workspace_service,
        [{"sharpe_ratio": 1.2, "total_trades": 6, "max_drawdown": -3.0}],
        fail_count=1,
    )
    service = AIStrategyResearchService(
        strategy_service=strategy_service,
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )
    progress_events: list[dict[str, Any]] = []

    result = await service.run(
        "user-1",
        AIStrategyResearchRunRequest(
            prompt="请生成一个双均线趋势策略",
            symbol="000001.SZ",
            target_sharpe=1.0,
            start_paper_trading=False,
            out_of_sample_validation=False,
            max_iterations=2,
            poll_interval_seconds=0.1,
        ),
        progress_callback=progress_events.append,
    )

    assert result.achieved is True
    assert result.status == "achieved"
    assert result.best_iteration == 2
    assert len(result.iterations) == 1
    assert result.iterations[0].iteration == 2
    assert len(strategy_service.submitted_backtest_requests) == 2
    assert any(
        event["current_stage"] == "backtest_submission_failed" for event in progress_events
    )
    assert any(
        "第 1 轮回测提交失败" in note for note in result.iterations[0].improvement_notes
    )
    assert result.run_record is not None
    assert result.run_record.status == "achieved"


@pytest.mark.asyncio
async def test_research_loop_persists_when_all_backtest_submissions_fail():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeBacktestSubmitFailingStrategyService(
        workspace_service,
        [],
        fail_count=2,
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
            start_paper_trading=False,
            out_of_sample_validation=False,
            max_iterations=2,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is False
    assert result.status == "backtest_submission_failed"
    assert result.iterations == []
    assert result.best_diagnostics["failure_categories"] == ["backtest_submission"]
    assert result.pipeline["current_stage"] == "backtest_failed"
    assert result.pipeline["steps"][1]["status"] == "failed"
    assert "最近一次提交失败" in result.next_actions[-1]
    assert result.run_record is not None
    assert result.run_record.status == "backtest_submission_failed"
    assert result.run_record.best_strategy_id == "saved-strategy-1"
    assert result.run_record.best_strategy_name.endswith("待回测")
    assert result.run_record.best_diagnostics["promotion_ready"] is False
    persisted_run = result.research_workspace.settings["ai_research"]["runs"][0]
    assert persisted_run["run_id"] == result.run_id
    assert persisted_run["status"] == "backtest_submission_failed"
    assert persisted_run["best_strategy_id"] == "saved-strategy-1"
    assert persisted_run["best_diagnostics"]["failure_categories"] == ["backtest_submission"]


@pytest.mark.asyncio
async def test_research_loop_persists_completed_iterations_when_cancelled():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeStrategyService(
        workspace_service,
        [{"sharpe_ratio": 0.2, "total_trades": 1, "max_drawdown": -3.0}],
    )
    improver = BlockingImprover()
    service = AIStrategyResearchService(
        strategy_service=strategy_service,
        workspace_service=workspace_service,
        improver=improver,
        sleep=_noop_sleep,
    )

    task = asyncio.create_task(
        service.run(
            "user-1",
            AIStrategyResearchRunRequest(
                prompt="请生成一个双均线趋势策略",
                symbol="000001.SZ",
                target_sharpe=1.0,
                start_paper_trading=False,
                out_of_sample_validation=False,
                max_iterations=2,
                poll_interval_seconds=0.1,
            ),
        )
    )
    await asyncio.wait_for(improver.started.wait(), timeout=1.0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    persisted_run = workspace_service.workspaces["research-ws"].settings["ai_research"]["runs"][0]
    assert persisted_run["status"] == "cancelled"
    assert persisted_run["achieved"] is False
    assert persisted_run["iteration_count"] == 1
    assert persisted_run["best_iteration"] == 1
    assert persisted_run["best_strategy_id"] == "strategy-1"
    assert persisted_run["best_metrics"]["sharpe_ratio"] == pytest.approx(0.2)
    assert persisted_run["iterations"][0]["iteration"] == 1
    assert persisted_run["pipeline"]["current_stage"] == "cancelled"
    assert persisted_run["pipeline"]["steps"][1]["status"] == "cancelled"
    assert "已保存取消前完成的回测迭代" in persisted_run["next_actions"][0]


@pytest.mark.asyncio
async def test_research_loop_persists_submitted_iteration_when_cancelled_before_result():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakePendingBacktestStrategyService(workspace_service, [])
    sleep = BlockingSleep()
    service = AIStrategyResearchService(
        strategy_service=strategy_service,
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=sleep,
    )

    task = asyncio.create_task(
        service.run(
            "user-1",
            AIStrategyResearchRunRequest(
                prompt="请生成一个双均线趋势策略",
                symbol="000001.SZ",
                target_sharpe=1.0,
                start_paper_trading=False,
                out_of_sample_validation=False,
                max_iterations=2,
                poll_interval_seconds=0.1,
            ),
        )
    )
    await asyncio.wait_for(sleep.started.wait(), timeout=1.0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    persisted_run = workspace_service.workspaces["research-ws"].settings["ai_research"]["runs"][0]
    assert persisted_run["status"] == "cancelled"
    assert persisted_run["achieved"] is False
    assert persisted_run["iteration_count"] == 1
    assert persisted_run["best_iteration"] == 1
    assert persisted_run["best_strategy_id"] == "strategy-1"
    assert persisted_run["best_quality_score"] == 0.0
    assert persisted_run["pipeline"]["current_stage"] == "cancelled"
    assert persisted_run["pipeline"]["steps"][1]["status"] == "cancelled"

    iteration = persisted_run["iterations"][0]
    assert iteration["iteration"] == 1
    assert iteration["task_id"] == "task-1"
    assert iteration["run_status"] == "cancelled"
    assert iteration["strategy_snapshot"]["id"] == "strategy-1"
    assert "backtrader" in iteration["strategy_snapshot"]["code"]
    assert iteration["unit_snapshot"]["id"] == "unit-1"
    assert any("cancelled while waiting" in item for item in iteration["quality_gate_failures"])
    assert "已提交的回测策略" in iteration["improvement_notes"][0]


@pytest.mark.asyncio
async def test_research_loop_persists_draft_when_cancelled_during_initial_generation():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeBlockingDraftGenerationStrategyService(workspace_service)
    service = AIStrategyResearchService(
        strategy_service=strategy_service,
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )

    task = asyncio.create_task(
        service.run(
            "user-1",
            AIStrategyResearchRunRequest(
                prompt="请生成一个双均线趋势策略",
                symbol="000001.SZ",
                target_sharpe=1.0,
                start_paper_trading=False,
                out_of_sample_validation=False,
                max_iterations=2,
                poll_interval_seconds=0.1,
            ),
        )
    )
    await asyncio.wait_for(strategy_service.started.wait(), timeout=1.0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    persisted_run = workspace_service.workspaces["research-ws"].settings["ai_research"]["runs"][0]
    assert persisted_run["status"] == "cancelled"
    assert persisted_run["achieved"] is False
    assert persisted_run["iteration_count"] == 0
    assert persisted_run["best_iteration"] is None
    assert persisted_run["best_strategy_id"] == "saved-strategy-1"
    assert persisted_run["best_strategy_name"].endswith("待回测")
    assert persisted_run["best_diagnostics"]["failure_categories"] == [
        "cancelled",
        "draft_only",
    ]
    assert any(
        "initial strategy draft" in item
        for item in persisted_run["best_diagnostics"]["weaknesses"]
    )
    assert persisted_run["pipeline"]["current_stage"] == "cancelled"
    assert persisted_run["pipeline"]["steps"][1]["status"] == "cancelled"
    assert "待回测策略草案" in persisted_run["next_actions"][0]
    assert persisted_run["iterations"] == []
    assert "backtrader" in strategy_service.strategies["saved-strategy-1"].code


@pytest.mark.asyncio
async def test_research_loop_persists_draft_when_cancelled_during_backtest_submission():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeBlockingBacktestSubmitStrategyService(workspace_service)
    service = AIStrategyResearchService(
        strategy_service=strategy_service,
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )

    task = asyncio.create_task(
        service.run(
            "user-1",
            AIStrategyResearchRunRequest(
                prompt="请生成一个双均线趋势策略",
                symbol="000001.SZ",
                target_sharpe=1.0,
                start_paper_trading=False,
                out_of_sample_validation=False,
                max_iterations=2,
                poll_interval_seconds=0.1,
            ),
        )
    )
    await asyncio.wait_for(strategy_service.started.wait(), timeout=1.0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    persisted_run = workspace_service.workspaces["research-ws"].settings["ai_research"]["runs"][0]
    assert persisted_run["status"] == "cancelled"
    assert persisted_run["achieved"] is False
    assert persisted_run["iteration_count"] == 0
    assert persisted_run["best_iteration"] is None
    assert persisted_run["best_strategy_id"] == "saved-strategy-1"
    assert persisted_run["best_strategy_name"].endswith("待回测")
    assert persisted_run["best_diagnostics"]["failure_categories"] == [
        "cancelled",
        "draft_only",
    ]
    assert any(
        "submitting backtest iteration 1" in item
        for item in persisted_run["best_diagnostics"]["weaknesses"]
    )
    assert persisted_run["pipeline"]["current_stage"] == "cancelled"
    assert persisted_run["pipeline"]["steps"][1]["status"] == "cancelled"
    assert "待回测策略草案" in persisted_run["next_actions"][0]
    assert persisted_run["iterations"] == []
    assert len(strategy_service.submitted_drafts) == 1
    assert strategy_service.strategies["saved-strategy-1"].code.strip() == (
        strategy_service.submitted_drafts[0].code.strip()
    )


@pytest.mark.asyncio
async def test_research_loop_can_continue_from_backtest_submission_failure():
    workspace_service = FakeWorkspaceService()
    failed_record = {
        **_run_record(
            "backtest-submit-failed-run",
            workspace_id="research-ws",
            completed_at="2026-01-01T00:01:00+00:00",
        ),
        "status": "backtest_submission_failed",
        "achieved": False,
        "iteration_count": 0,
        "best_iteration": None,
        "best_strategy_id": "saved-strategy-1",
        "best_strategy_name": "保存草案 - 待回测",
        "best_metrics": {},
        "best_diagnostics": {
            "summary": "投研循环在提交回测任务时失败，尚未产生可评估的回测结果。",
            "failure_categories": ["backtest_submission"],
            "weaknesses": ["Backtest submission failed before iteration 2: queue unavailable"],
            "improvement_plan": ["检查回测队列并继续提交。"],
            "promotion_ready": False,
        },
        "pipeline": {
            "current_stage": "backtest_failed",
            "status": "backtest_submission_failed",
            "progress": 20,
            "ready_for_live": False,
            "steps": [],
        },
        "next_actions": ["最近一次提交失败：queue unavailable"],
        "iterations": [],
    }
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={"settings": {"ai_research": {"runs": [failed_record]}}}
    )
    seed_draft = build_ai_strategy_draft("请生成一个均线趋势策略").model_copy(
        update={"name": "保存草案 - 待回测"}
    )
    seed_strategy = _strategy("saved-strategy-1", seed_draft)
    strategy_service = FakeStrategyService(
        workspace_service,
        [{"sharpe_ratio": 1.18, "total_trades": 7, "max_drawdown": -4.0}],
        strategies={"saved-strategy-1": seed_strategy},
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
            prompt="继续上一轮回测提交失败的投研",
            symbol="000001.SZ",
            target_sharpe=1.0,
            continue_from_run_id="backtest-submit-failed-run",
            start_paper_trading=False,
            out_of_sample_validation=False,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is True
    assert strategy_service.generated == 0
    assert strategy_service.submitted_drafts[0].name.endswith("v1")
    assert any(
        "Backtest submission failed before iteration 2" in note
        for note in result.iterations[0].improvement_notes
    )
    assert result.run_record is not None
    assert result.run_record.seed_strategy_id == "saved-strategy-1"
    assert result.run_record.continued_from_run_id == "backtest-submit-failed-run"


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
async def test_research_loop_treats_timeout_paper_run_as_start_failure():
    workspace_service = FakePaperRunTimeoutWorkspaceService()
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
    assert result.paper_trading is not None
    assert result.paper_trading.started is False
    assert result.paper_trading.run_result is not None
    assert result.paper_trading.run_result.status == "timeout"
    assert result.pipeline["current_stage"] == "paper_trading_failed"
    assert result.pipeline["paper_trading_error"] == "Paper trading run finished with status timeout"
    assert result.run_record is not None
    assert result.run_record.paper_trading_started is False
    assert result.run_record.paper_handoff["paper_run_status"] == "timeout"
    assert result.run_record.pipeline["current_stage"] == "paper_trading_failed"


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
async def test_research_loop_records_out_of_sample_submission_failure():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeValidationSubmitFailingStrategyService(
        workspace_service,
        [{"sharpe_ratio": 1.32, "total_trades": 12, "max_drawdown": -4.0}],
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
            start_date="2024-01-01",
            end_date="2024-01-20",
            target_sharpe=1.0,
            min_total_trades=4,
            max_iterations=1,
            poll_interval_seconds=0.1,
            start_paper_trading=False,
        ),
    )

    assert result.achieved is False
    assert result.status == "max_iterations_reached"
    assert result.paper_trading is None
    assert len(strategy_service.submitted_backtest_requests) == 2
    iteration = result.iterations[0]
    assert iteration.passed is False
    assert iteration.validation_status == "failed"
    assert iteration.validation_unit is None
    assert iteration.validation_run_result is None
    assert iteration.validation_failures == [
        "Out-of-sample validation failed to start: "
        "Research workspace or generated validation strategy was not found"
    ]
    assert iteration.failure_reason == iteration.validation_failure_reason
    assert iteration.diagnostics["promotion_ready"] is False
    assert result.run_record is not None
    assert result.run_record.iterations[0]["validation_status"] == "failed"
    assert result.research_workspace.settings["ai_research"]["runs"][0]["run_id"] == result.run_id


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
    improver = RecordingImprover()
    service = AIStrategyResearchService(
        strategy_service=strategy_service,
        workspace_service=workspace_service,
        improver=improver,
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
    assert "out_of_sample" in result.iterations[0].diagnostics["failure_categories"]
    assert "sharpe" in result.iterations[0].diagnostics["failure_categories"]
    assert len(improver.calls) == 1
    improvement_metrics = improver.calls[0]["metrics"]
    assert "out_of_sample" in improvement_metrics["failure_categories"]
    assert improvement_metrics["research_feedback"]["out_of_sample_validation"]["status"] == "failed"
    assert any("样本外验证未通过" in item for item in improvement_metrics["improvement_plan"])
    assert improvement_metrics["promotion_ready"] is False
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
    assert result.run_record.asset_specs["IF2609"]["multiplier"] == 300
    assert result.run_record.asset_specs["IF2609"]["commission_rate"] == pytest.approx(0.000023)
    assert result.run_record.backtest_environment["commission"] == pytest.approx(0.000023)
    assert result.run_record.backtest_environment["multiplier"] == 300
    assert result.run_record.backtest_environment["margin"] == pytest.approx(0.1)
    assert result.run_record.backtest_environment["asset_spec_source"] == (
        "local_futures_commission"
    )
    strategy_snapshot = result.run_record.iterations[0]["strategy_snapshot"]
    assert strategy_snapshot["id"] == result.iterations[0].strategy.id
    assert strategy_snapshot["name"] == result.iterations[0].strategy.name
    assert "bt.Strategy" in strategy_snapshot["code"]
    assert isinstance(strategy_snapshot["params"], dict)
    unit_snapshot = result.run_record.iterations[0]["unit_snapshot"]
    assert unit_snapshot["data_config"]["contract_metadata"]["IF2609"]["multiplier"] == 300
    assert unit_snapshot["unit_settings"]["commission"] == pytest.approx(0.000023)
    assert unit_snapshot["unit_settings"]["asset_spec_source"] == "local_futures_commission"
    persisted_run = result.research_workspace.settings["ai_research"]["runs"][0]
    assert "bt.Strategy" in persisted_run["iterations"][0]["strategy_snapshot"]["code"]
    assert persisted_run["asset_specs"]["IF2609"]["margin_rate"] == pytest.approx(0.1)
    assert persisted_run["backtest_environment"]["commission"] == pytest.approx(0.000023)


@pytest.mark.asyncio
async def test_research_loop_continuation_restores_record_runtime_metadata(monkeypatch):
    def fake_resolve_asset_specs(instance, strategy_dir, gateway=None, symbols=None):
        return {}

    monkeypatch.setattr(
        "app.services.ai_strategy_research_service.resolve_asset_specs",
        fake_resolve_asset_specs,
    )
    workspace_service = FakeWorkspaceService()
    seed_draft = build_ai_strategy_draft("请生成一个股指期货趋势策略").model_copy(
        update={"name": "历史期货策略"}
    )
    seed_strategy = _strategy("futures-strategy-1", seed_draft)
    unit_snapshot = {
        "id": "history-unit",
        "workspace_id": "research-ws",
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
            "asset_spec_source": "previous_exchange_specs",
        },
        "optimization_config": {"enabled": True, "max_trials": 8},
        "gateway_config": {"name": "paper_gateway", "params": {"exchange": "CFFEX"}},
    }
    record = {
        **_run_record(
            "previous-futures-run",
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
        "best_strategy_id": seed_strategy.id,
        "best_strategy_name": seed_strategy.name,
        "asset_specs": {
            "IF2609": {
                "symbol": "IF2609",
                "source": "previous_exchange_specs",
                "multiplier": 300,
                "margin_rate": 0.1,
                "commission_rate": 0.000023,
            }
        },
        "backtest_environment": {
            "initial_cash": 250000.0,
            "commission": 0.000023,
            "annual_days": 244,
            "calc_method": "log",
            "weight_mode": "value",
            "multiplier": 300,
            "margin": 0.1,
            "asset_spec_source": "previous_exchange_specs",
        },
        "iterations": [
            {
                "iteration": 2,
                "strategy_id": seed_strategy.id,
                "strategy_name": seed_strategy.name,
                "unit_id": "history-unit",
                "unit_snapshot": unit_snapshot,
                "task_id": "task-history",
                "run_status": "completed",
                "metrics": {"sharpe_ratio": 0.72, "total_trades": 4},
                "sharpe_ratio": 0.72,
                "total_trades": 4,
                "quality_score": 72.0,
                "quality_gate_evaluations": [],
                "passed": False,
                "quality_gate_failures": ["Sharpe 0.720 below target 1.000"],
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
        [{"sharpe_ratio": 1.18, "total_trades": 7, "max_drawdown": -4.0}],
        strategies={seed_strategy.id: seed_strategy},
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
            prompt="继续股指期货策略投研",
            symbol="IF2609",
            target_sharpe=1.0,
            continue_from_run_id="previous-futures-run",
            start_paper_trading=False,
            out_of_sample_validation=False,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )

    assert strategy_service.generated == 0
    backtest_request = strategy_service.submitted_backtest_requests[0]
    contract_metadata = backtest_request.data_config["contract_metadata"]["IF2609"]
    unit_metadata = backtest_request.unit_settings["contract_metadata"]["IF2609"]
    assert contract_metadata["multiplier"] == 300
    assert unit_metadata["commission_rate"] == pytest.approx(0.000023)
    assert backtest_request.unit_settings["commission"] == pytest.approx(0.000023)
    assert backtest_request.unit_settings["multiplier"] == 300
    assert backtest_request.unit_settings["margin"] == pytest.approx(0.1)
    assert backtest_request.unit_settings["asset_spec_source"] == "previous_exchange_specs"
    assert backtest_request.optimization_config == {"enabled": True, "max_trials": 8}
    assert result.run_record is not None
    assert result.run_record.continued_from_run_id == "previous-futures-run"
    assert result.run_record.asset_specs["IF2609"]["multiplier"] == 300
    assert result.run_record.backtest_environment["asset_spec_source"] == (
        "previous_exchange_specs"
    )


@pytest.mark.asyncio
async def test_research_loop_continuation_restores_paper_handoff_runtime_metadata(monkeypatch):
    def fake_resolve_asset_specs(instance, strategy_dir, gateway=None, symbols=None):
        return {}

    monkeypatch.setattr(
        "app.services.ai_strategy_research_service.resolve_asset_specs",
        fake_resolve_asset_specs,
    )
    workspace_service = FakeWorkspaceService()
    seed_draft = build_ai_strategy_draft("请生成一个股指期货趋势策略").model_copy(
        update={"name": "历史期货策略"}
    )
    seed_strategy = _strategy("futures-strategy-1", seed_draft)
    record = {
        **_run_record(
            "previous-handoff-run",
            workspace_id="research-ws",
            completed_at="2026-01-01T00:01:00+00:00",
        ),
        "symbol": "IF2609",
        "symbol_name": "沪深300股指期货",
        "initial_cash": 100000.0,
        "commission": 0.001,
        "annual_days": 252,
        "calc_method": "simple",
        "weight_mode": "equal",
        "best_strategy_id": seed_strategy.id,
        "best_strategy_name": seed_strategy.name,
        "asset_specs": {
            "IF2609": {
                "symbol": "IF2609",
                "source": "stale_local_defaults",
                "multiplier": 200,
                "margin_rate": 0.2,
                "commission_rate": 0.001,
            }
        },
        "backtest_environment": {
            "initial_cash": 100000.0,
            "commission": 0.001,
            "annual_days": 252,
            "calc_method": "simple",
            "weight_mode": "equal",
            "multiplier": 200,
            "margin": 0.2,
            "asset_spec_source": "stale_local_defaults",
        },
        "paper_handoff": {
            "asset_specs": {
                "IF2609": {
                    "symbol": "IF2609",
                    "source": "paper_handoff_exchange_specs",
                    "multiplier": 300,
                    "margin_rate": 0.1,
                    "commission_rate": 0.000023,
                }
            },
            "backtest_environment": {
                "initial_cash": 250000.0,
                "commission": 0.000023,
                "annual_days": 244,
                "calc_method": "log",
                "weight_mode": "value",
                "multiplier": 300,
                "margin": 0.1,
                "asset_spec_source": "paper_handoff_exchange_specs",
            },
            "gateway_config": {
                "name": "paper_gateway",
                "api_key": "***",
                "params": {
                    "exchange": "CFFEX",
                    "asset_type": "future",
                    "secret_key": "***",
                    "passphrase": "***",
                },
            },
        },
        "iterations": [
            {
                "iteration": 2,
                "strategy_id": seed_strategy.id,
                "strategy_name": seed_strategy.name,
                "unit_id": "history-unit",
                "unit_snapshot": {
                    "id": "history-unit",
                    "workspace_id": "research-ws",
                    "data_config": {"symbol": "IF2609"},
                    "unit_settings": {"initial_cash": 100000.0, "commission": 0.001},
                    "optimization_config": {},
                    "gateway_config": {},
                },
                "task_id": "task-history",
                "run_status": "completed",
                "metrics": {"sharpe_ratio": 0.72, "total_trades": 4},
                "sharpe_ratio": 0.72,
                "total_trades": 4,
                "quality_score": 72.0,
                "quality_gate_failures": ["Sharpe 0.720 below target 1.000"],
            }
        ],
    }
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={"settings": {"ai_research": {"runs": [record]}}}
    )
    strategy_service = FakeStrategyService(
        workspace_service,
        [{"sharpe_ratio": 1.18, "total_trades": 7, "max_drawdown": -4.0}],
        strategies={seed_strategy.id: seed_strategy},
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
            prompt="继续股指期货策略投研",
            symbol="IF2609",
            target_sharpe=1.0,
            continue_from_run_id="previous-handoff-run",
            start_paper_trading=False,
            out_of_sample_validation=False,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )

    backtest_request = strategy_service.submitted_backtest_requests[0]
    contract_metadata = backtest_request.data_config["contract_metadata"]["IF2609"]
    unit_metadata = backtest_request.unit_settings["contract_metadata"]["IF2609"]
    assert contract_metadata["source"] == "paper_handoff_exchange_specs"
    assert unit_metadata["commission_rate"] == pytest.approx(0.000023)
    assert backtest_request.unit_settings["initial_cash"] == pytest.approx(250000.0)
    assert backtest_request.unit_settings["commission"] == pytest.approx(0.000023)
    assert backtest_request.unit_settings["annual_days"] == 244
    assert backtest_request.unit_settings["calc_method"] == "log"
    assert backtest_request.unit_settings["weight_mode"] == "value"
    assert backtest_request.unit_settings["multiplier"] == 300
    assert backtest_request.unit_settings["margin"] == pytest.approx(0.1)
    assert backtest_request.unit_settings["asset_spec_source"] == "paper_handoff_exchange_specs"
    backtest_payload = json.dumps(backtest_request.model_dump(mode="python"), ensure_ascii=False)
    assert "api_key" not in backtest_payload
    assert "secret_key" not in backtest_payload
    assert "passphrase" not in backtest_payload
    assert "***" not in backtest_payload
    assert result.run_record is not None
    assert result.run_record.commission == pytest.approx(0.000023)
    assert result.run_record.asset_specs["IF2609"]["source"] == "paper_handoff_exchange_specs"
    assert result.run_record.backtest_environment["commission"] == pytest.approx(0.000023)


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

    result = await service.run(
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
    assert stages[:4] == ["initializing", "workspace_ready", "drafting", "backtesting"]
    assert "evaluating" in stages
    assert events[0]["run_id"] == result.run_id
    workspace_ready = next(item for item in events if item["current_stage"] == "workspace_ready")
    assert workspace_ready["research_workspace_id"] == result.research_workspace.id
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
            "closed_trades": 20,
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
    assert review.live_readiness_expires_at
    reviewed_at = datetime.fromisoformat(review.reviewed_at)
    expires_at = datetime.fromisoformat(review.live_readiness_expires_at)
    assert expires_at - reviewed_at == timedelta(days=7)
    assert review.live_handoff is not None
    assert review.live_handoff.status == "ready_for_approval"
    assert review.live_handoff.ready_for_live is True
    assert review.pipeline["current_stage"] == "live_handoff"
    assert review.pipeline["ready_for_live"] is True
    assert review.pipeline["live_handoff_status"] == "ready_for_approval"
    assert review.pipeline["live_handoff_ready_for_live"] is True
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
    assert review.live_readiness_checklist[0]["key"] == "paper_monitoring_passed"
    checklist_by_key = {item["key"]: item for item in review.live_readiness_checklist}
    assert checklist_by_key["execution_costs_confirmed"]["status"] == "passed"
    assert "成交成本偏离" in checklist_by_key["execution_costs_confirmed"]["evidence"]
    assert "unit_status.metrics_snapshot" in checklist_by_key["execution_costs_confirmed"][
        "evidence"
    ]
    assert checklist_by_key["risk_budget_confirmed"]["status"] == "passed"
    assert "模拟交易最大回撤" in checklist_by_key["risk_budget_confirmed"]["evidence"]
    assert review.live_readiness_checklist[-1]["key"] == "human_approval_required"
    assert review.live_readiness_checklist[-1]["status"] == "pending_manual_confirmation"
    assert "实盘交接包已生成" in review.next_actions[0]
    updated_run = workspace_service.workspaces["research-ws"].settings["ai_research"]["runs"][0]
    assert updated_run["run_id"] == result.run_id
    assert updated_run["paper_review_status"] == "ready_for_live_candidate"
    assert updated_run["paper_review_ready_for_live"] is True
    assert updated_run["paper_reviewed_at"] == review.reviewed_at
    assert updated_run["live_readiness_expires_at"] == review.live_readiness_expires_at
    assert updated_run["paper_review_evaluations"][0]["key"] == "rolling_sharpe"
    assert "实盘候选" in updated_run["paper_review_next_actions"][0]
    assert "实盘交接包已生成" in updated_run["next_actions"][0]
    assert updated_run["live_readiness_checklist"] == review.live_readiness_checklist
    assert updated_run["live_handoff"]["status"] == "ready_for_approval"
    assert updated_run["live_handoff"]["ready_for_live"] is True
    gateway_config = updated_run["live_handoff"]["handoff"].get("gateway_config", {})
    assert gateway_config.get("api_key") in {None, "***"}
    assert (
        updated_run["paper_handoff"]["live_readiness_checklist"]
        == review.live_readiness_checklist
    )
    assert (
        updated_run["paper_handoff"]["live_readiness_expires_at"]
        == review.live_readiness_expires_at
    )
    assert updated_run["pipeline"]["current_stage"] == "live_handoff"
    assert updated_run["pipeline"]["ready_for_live"] is True
    assert updated_run["pipeline"]["live_handoff_status"] == "ready_for_approval"
    assert updated_run["pipeline"]["live_handoff_ready_for_live"] is True
    assert updated_run["pipeline"]["live_readiness_checklist"] == review.live_readiness_checklist
    assert updated_run["pipeline"]["live_readiness_expires_at"] == review.live_readiness_expires_at


@pytest.mark.asyncio
async def test_build_live_handoff_package_redacts_secrets_and_keeps_asset_context():
    workspace_service = FakeWorkspaceService()
    live_readiness_checklist = [
        {
            "key": "paper_monitoring_passed",
            "label": "模拟监控通过",
            "status": "passed",
            "evidence": "模拟交易滚动 Sharpe 0.8 / 0.6。",
            "action": "继续监控同一组指标。",
        },
        {
            "key": "human_approval_required",
            "label": "人工实盘审批",
            "status": "pending_manual_confirmation",
            "evidence": "模拟复核已达到实盘候选状态。",
            "action": "确认账户权限和上线窗口后再切换实盘。",
        },
    ]
    run = {
        **_run_record(
            "live-handoff-run",
            workspace_id="research-ws",
            completed_at="2026-01-02T00:00:00+00:00",
        ),
        "symbol": "IF2609",
        "asset_specs": {
            "IF2609": {
                "symbol": "IF2609",
                "asset_class": "future",
                "multiplier": 300,
                "margin_rate": 0.1,
                "commission_rate": 0.000023,
                "source": "exchange",
            }
        },
        "backtest_environment": {
            "initial_cash": 1000000,
            "commission": 0.000023,
            "contract_multiplier": 300,
            "margin_rate": 0.1,
            "asset_spec_source": "exchange",
        },
        "paper_review_status": "ready_for_live_candidate",
        "paper_review_ready_for_live": True,
        "paper_reviewed_at": "2026-01-02T00:00:00+00:00",
        "paper_review_evaluations": [
            {
                "key": "rolling_sharpe",
                "label": "模拟交易滚动 Sharpe",
                "metric": "rolling_sharpe",
                "window": "30 trading days",
                "direction": "min",
                "threshold": 0.6,
                "actual": 0.8,
                "source": "unit_status.metrics_snapshot",
                "status": "passed",
                "passed": True,
                "action": "继续观察",
            }
        ],
        "paper_review_next_actions": ["模拟交易监控计划已全部通过，可作为实盘候选进入人工复核。"],
        "live_readiness_checklist": live_readiness_checklist,
        "live_readiness_expires_at": "2999-01-08T00:00:00+00:00",
        "paper_handoff": {
            "run_id": "live-handoff-run",
            "gateway_config": {
                "api_key": "real-api-key",
                "params": {
                    "secret_key": "real-secret",
                    "passphrase": "real-passphrase",
                    "exchange": "sim",
                },
            },
            "asset_specs": {
                "IF2609": {
                    "multiplier": 300,
                    "margin_rate": 0.1,
                    "commission_rate": 0.000023,
                }
            },
        },
        "pipeline": {
            "current_stage": "live_candidate",
            "status": "achieved",
            "progress": 100,
            "ready_for_live": True,
            "live_readiness_checklist": live_readiness_checklist,
            "live_readiness_expires_at": "2999-01-08T00:00:00+00:00",
            "steps": [],
        },
    }
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={"settings": {"ai_research": {"runs": [run]}}},
    )
    service = AIStrategyResearchService(
        strategy_service=FakeStrategyService(workspace_service, []),
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )

    package = await service.build_live_handoff_package(
        "user-1",
        "live-handoff-run",
        research_workspace_id="research-ws",
    )

    assert package.ready_for_live is True
    assert package.status == "ready_for_approval"
    assert package.approval_required is True
    assert package.deployment_blockers == []
    assert package.approvals_required[0]["key"] == "human_approval_required"
    assert package.asset_specs["IF2609"]["multiplier"] == 300
    assert package.backtest_environment["contract_multiplier"] == 300
    assert package.handoff["gateway_config"]["api_key"] == "***"
    assert package.handoff["gateway_config"]["params"]["secret_key"] == "***"
    assert package.handoff["gateway_config"]["params"]["passphrase"] == "***"
    assert package.handoff["gateway_config"]["params"]["exchange"] == "sim"
    assert package.pipeline["current_stage"] == "live_handoff"
    assert package.pipeline["steps"][-1]["key"] == "live_handoff"
    assert package.pipeline["steps"][-1]["status"] == "running"
    persisted_run = workspace_service.workspaces["research-ws"].settings["ai_research"]["runs"][0]
    assert persisted_run["live_handoff"]["status"] == "ready_for_approval"
    assert persisted_run["live_handoff"]["ready_for_live"] is True
    assert persisted_run["live_handoff"]["handoff"]["gateway_config"]["api_key"] == "***"
    assert persisted_run["pipeline"]["current_stage"] == "live_handoff"
    assert persisted_run["pipeline"]["live_handoff_status"] == "ready_for_approval"
    assert persisted_run["pipeline"]["live_handoff_ready_for_live"] is True
    assert persisted_run["pipeline"]["steps"][-1]["status"] == "running"
    assert "等待人工审批" in persisted_run["next_actions"][0]


@pytest.mark.asyncio
async def test_record_live_handoff_approval_persists_manual_decision():
    workspace_service = FakeWorkspaceService()
    live_readiness_checklist = [
        {
            "key": "paper_monitoring_passed",
            "label": "模拟监控通过",
            "status": "passed",
            "evidence": "模拟交易滚动 Sharpe 0.8 / 0.6。",
            "action": "继续监控同一组指标。",
        },
        {
            "key": "human_approval_required",
            "label": "人工实盘审批",
            "status": "pending_manual_confirmation",
            "evidence": "模拟复核已达到实盘候选状态。",
            "action": "确认账户权限和上线窗口后再切换实盘。",
        },
    ]
    run = {
        **_run_record(
            "live-approval-run",
            workspace_id="research-ws",
            completed_at="2026-01-02T00:00:00+00:00",
        ),
        "paper_review_status": "ready_for_live_candidate",
        "paper_review_ready_for_live": True,
        "paper_reviewed_at": "2026-01-02T00:00:00+00:00",
        "paper_review_evaluations": [
            {
                "key": "rolling_sharpe",
                "label": "模拟交易滚动 Sharpe",
                "metric": "rolling_sharpe",
                "window": "30 trading days",
                "direction": "min",
                "threshold": 0.6,
                "actual": 0.8,
                "source": "unit_status.metrics_snapshot",
                "status": "passed",
                "passed": True,
                "action": "继续观察",
            }
        ],
        "paper_review_next_actions": ["模拟交易监控计划已全部通过，可作为实盘候选进入人工复核。"],
        "live_readiness_checklist": live_readiness_checklist,
        "live_readiness_expires_at": "2999-01-08T00:00:00+00:00",
        "paper_handoff": {
            "run_id": "live-approval-run",
            "gateway_config": {"name": "paper_gateway", "params": {"exchange": "sim"}},
        },
        "pipeline": {
            "current_stage": "live_candidate",
            "status": "achieved",
            "progress": 100,
            "ready_for_live": True,
            "live_readiness_checklist": live_readiness_checklist,
            "live_readiness_expires_at": "2999-01-08T00:00:00+00:00",
            "steps": [],
        },
    }
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={"settings": {"ai_research": {"runs": [run]}}},
    )
    service = AIStrategyResearchService(
        strategy_service=FakeStrategyService(workspace_service, []),
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )

    package = await service.record_live_handoff_approval(
        "user-1",
        "live-approval-run",
        AIStrategyLiveHandoffApprovalRequest(
            decision="approved",
            approver="risk-manager",
            comment="账户和风控已确认",
            account_confirmed=True,
            risk_limit_confirmed=True,
            deployment_window="2026-01-03 09:30",
        ),
        research_workspace_id="research-ws",
    )

    assert package.status == "approved_for_live"
    assert package.approval_status == "approved"
    assert package.approval is not None
    assert package.approval.approved is True
    assert package.approval.decided_by == "risk-manager"
    assert package.approval.deployment_window == "2026-01-03 09:30"
    persisted_run = workspace_service.workspaces["research-ws"].settings["ai_research"]["runs"][0]
    assert persisted_run["live_handoff"]["status"] == "approved_for_live"
    assert persisted_run["live_handoff_approval"]["decision"] == "approved"
    assert persisted_run["pipeline"]["current_stage"] == "live_handoff"
    assert persisted_run["pipeline"]["live_handoff_approval_status"] == "approved"
    assert persisted_run["pipeline"]["live_handoff_approved"] is True
    assert persisted_run["pipeline"]["steps"][-1]["key"] == "live_handoff"
    assert persisted_run["pipeline"]["steps"][-1]["status"] == "completed"
    assert "通过人工审批" in persisted_run["next_actions"][0]


@pytest.mark.asyncio
async def test_prepare_live_trading_from_approved_handoff_creates_locked_live_unit():
    workspace_service = FakeWorkspaceService()
    workspace_service.workspaces["live-ws"] = _workspace("live-ws", "trading")
    live_readiness_checklist = [
        {
            "key": "paper_monitoring_passed",
            "label": "模拟监控通过",
            "status": "passed",
            "evidence": "模拟交易滚动 Sharpe 0.8 / 0.6。",
            "action": "继续监控同一组指标。",
        },
        {
            "key": "human_approval_required",
            "label": "人工实盘审批",
            "status": "pending_manual_confirmation",
            "evidence": "模拟复核已达到实盘候选状态。",
            "action": "确认账户权限和上线窗口后再切换实盘。",
        },
    ]
    run = {
        **_run_record(
            "live-prepare-run",
            workspace_id="research-ws",
            completed_at="2026-01-02T00:00:00+00:00",
        ),
        "asset_specs": {
            "000001.SZ": {
                "symbol": "000001.SZ",
                "source": "exchange",
                "multiplier": 1,
                "commission_rate": 0.0003,
            }
        },
        "backtest_environment": {
            "initial_cash": 100000,
            "commission": 0.0003,
            "asset_spec_source": "exchange",
        },
        "paper_review_status": "ready_for_live_candidate",
        "paper_review_ready_for_live": True,
        "paper_reviewed_at": "2026-01-02T00:00:00+00:00",
        "paper_review_evaluations": [
            {
                "key": "rolling_sharpe",
                "label": "模拟交易滚动 Sharpe",
                "metric": "rolling_sharpe",
                "window": "30 trading days",
                "direction": "min",
                "threshold": 0.6,
                "actual": 0.8,
                "source": "unit_status.metrics_snapshot",
                "status": "passed",
                "passed": True,
                "action": "继续观察",
            }
        ],
        "paper_review_next_actions": ["模拟交易监控计划已全部通过，可作为实盘候选进入人工复核。"],
        "live_readiness_checklist": live_readiness_checklist,
        "live_readiness_expires_at": "2999-01-08T00:00:00+00:00",
        "paper_handoff": {
            "run_id": "live-prepare-run",
            "gateway_config": {"name": "paper_gateway", "params": {"exchange": "sim"}},
        },
        "pipeline": {
            "current_stage": "live_candidate",
            "status": "achieved",
            "progress": 100,
            "ready_for_live": True,
            "live_readiness_checklist": live_readiness_checklist,
            "live_readiness_expires_at": "2999-01-08T00:00:00+00:00",
            "steps": [],
        },
    }
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={"settings": {"ai_research": {"runs": [run]}}},
    )
    strategy = _strategy("strategy-2", build_ai_strategy_draft("生成趋势策略"))
    service = AIStrategyResearchService(
        strategy_service=FakeStrategyService(
            workspace_service,
            [],
            strategies={strategy.id: strategy},
        ),
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )
    await service.record_live_handoff_approval(
        "user-1",
        "live-prepare-run",
        AIStrategyLiveHandoffApprovalRequest(
            decision="approved",
            approver="risk-manager",
            comment="账户和风控已确认",
            account_confirmed=True,
            risk_limit_confirmed=True,
            deployment_window="2026-01-03 09:30",
        ),
        research_workspace_id="research-ws",
    )

    prepared = await service.prepare_live_trading_from_run(
        "user-1",
        "live-prepare-run",
        AIStrategyLiveTradingPrepareRequest(
            research_workspace_id="research-ws",
            trading_workspace_id="live-ws",
            gateway_config={"name": "ctp_live", "params": {"broker_id": "sim"}},
        ),
    )

    assert prepared.prepared is True
    assert prepared.workspace.id == "live-ws"
    assert prepared.unit.id == "live-unit"
    assert prepared.unit.trading_mode == "live"
    assert prepared.unit.lock_trading is True
    assert prepared.unit.lock_running is True
    assert prepared.unit.gateway_config["name"] == "ctp_live"
    assert prepared.unit.unit_settings["ai_research_live_handoff"]["run_id"] == "live-prepare-run"
    assert prepared.unit.unit_settings["asset_spec_source"] == "exchange"
    assert "锁定的实盘交易单元" in prepared.next_actions[0]

    persisted_run = workspace_service.workspaces["research-ws"].settings["ai_research"]["runs"][0]
    assert persisted_run["live_workspace_id"] == "live-ws"
    assert persisted_run["live_unit_id"] == "live-unit"
    assert persisted_run["live_trading_prepared"] is True
    assert persisted_run["pipeline"]["current_stage"] == "live_trading_prepare"
    assert persisted_run["pipeline"]["live_trading_prepared"] is True
    assert persisted_run["pipeline"]["live_unit_locked"] is True
    assert persisted_run["pipeline"]["steps"][-1]["key"] == "live_trading_prepare"
    assert persisted_run["pipeline"]["steps"][-1]["status"] == "completed"
    assert persisted_run["live_handoff"]["handoff"]["live_trading_prepare"][
        "live_unit_id"
    ] == "live-unit"
    live_handoff = workspace_service.workspaces["live-ws"].settings["ai_research_live_handoff"]
    assert live_handoff["last_handoff"]["live_unit_id"] == "live-unit"


@pytest.mark.asyncio
async def test_prepare_live_trading_requires_approved_live_handoff():
    workspace_service = FakeWorkspaceService()
    workspace_service.workspaces["live-ws"] = _workspace("live-ws", "trading")
    run = {
        **_run_record(
            "unapproved-live-prepare-run",
            workspace_id="research-ws",
            completed_at="2026-01-02T00:00:00+00:00",
        ),
        "paper_review_status": "ready_for_live_candidate",
        "paper_review_ready_for_live": True,
        "live_readiness_expires_at": "2999-01-08T00:00:00+00:00",
        "live_readiness_checklist": [
            {
                "key": "human_approval_required",
                "label": "人工实盘审批",
                "status": "pending_manual_confirmation",
                "evidence": "模拟复核已达到实盘候选状态。",
                "action": "确认账户权限和上线窗口后再切换实盘。",
            }
        ],
    }
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={"settings": {"ai_research": {"runs": [run]}}},
    )
    strategy = _strategy("strategy-2", build_ai_strategy_draft("生成趋势策略"))
    service = AIStrategyResearchService(
        strategy_service=FakeStrategyService(
            workspace_service,
            [],
            strategies={strategy.id: strategy},
        ),
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )

    with pytest.raises(ValueError, match="not been approved"):
        await service.prepare_live_trading_from_run(
            "user-1",
            "unapproved-live-prepare-run",
            AIStrategyLiveTradingPrepareRequest(
                research_workspace_id="research-ws",
                trading_workspace_id="live-ws",
            ),
        )


@pytest.mark.asyncio
async def test_build_live_handoff_package_blocks_expired_candidate():
    workspace_service = FakeWorkspaceService()
    run = {
        **_run_record(
            "expired-live-handoff-run",
            workspace_id="research-ws",
            completed_at="2026-01-02T00:00:00+00:00",
        ),
        "paper_review_status": "ready_for_live_candidate",
        "paper_review_ready_for_live": True,
        "paper_reviewed_at": "2000-01-01T00:00:00+00:00",
        "paper_review_evaluations": [
            {
                "key": "rolling_sharpe",
                "label": "模拟交易滚动 Sharpe",
                "metric": "rolling_sharpe",
                "window": "30 trading days",
                "direction": "min",
                "threshold": 0.6,
                "actual": 0.8,
                "source": "unit_status.metrics_snapshot",
                "status": "passed",
                "passed": True,
                "action": "继续观察",
            }
        ],
        "live_readiness_checklist": [
            {
                "key": "human_approval_required",
                "label": "人工实盘审批",
                "status": "pending_manual_confirmation",
                "evidence": "模拟复核已达到实盘候选状态。",
                "action": "确认账户权限和上线窗口后再切换实盘。",
            }
        ],
        "live_readiness_expires_at": "2000-01-08T00:00:00+00:00",
        "pipeline": {
            "current_stage": "live_candidate",
            "status": "achieved",
            "progress": 100,
            "ready_for_live": True,
            "live_readiness_expires_at": "2000-01-08T00:00:00+00:00",
            "steps": [],
        },
    }
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={"settings": {"ai_research": {"runs": [run]}}},
    )
    service = AIStrategyResearchService(
        strategy_service=FakeStrategyService(workspace_service, []),
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )

    package = await service.build_live_handoff_package(
        "user-1",
        "expired-live-handoff-run",
        research_workspace_id="research-ws",
    )

    assert package.ready_for_live is False
    assert package.status == "blocked"
    assert package.paper_review_status == "live_readiness_expired"
    assert any("过期" in blocker for blocker in package.deployment_blockers)
    assert package.live_readiness_checklist[-1]["status"] == "expired"
    persisted_run = workspace_service.workspaces["research-ws"].settings["ai_research"]["runs"][0]
    assert persisted_run["live_handoff"]["status"] == "blocked"
    assert persisted_run["pipeline"]["current_stage"] == "live_handoff"
    assert persisted_run["pipeline"]["live_handoff_status"] == "blocked"
    assert persisted_run["pipeline"]["live_handoff_ready_for_live"] is False
    assert persisted_run["pipeline"]["steps"][-1]["status"] == "failed"
    assert "阻塞项" in persisted_run["next_actions"][0]


@pytest.mark.asyncio
async def test_record_live_handoff_approval_rejects_blocked_package():
    workspace_service = FakeWorkspaceService()
    run = {
        **_run_record(
            "blocked-live-approval-run",
            workspace_id="research-ws",
            completed_at="2026-01-02T00:00:00+00:00",
        ),
        "paper_review_status": "monitoring",
        "paper_review_ready_for_live": False,
        "paper_reviewed_at": "2026-01-02T00:00:00+00:00",
        "paper_review_evaluations": [],
        "live_readiness_checklist": [],
        "pipeline": {
            "current_stage": "paper_review",
            "status": "achieved",
            "progress": 92,
            "ready_for_live": False,
            "steps": [],
        },
    }
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={"settings": {"ai_research": {"runs": [run]}}},
    )
    service = AIStrategyResearchService(
        strategy_service=FakeStrategyService(workspace_service, []),
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )

    with pytest.raises(ValueError, match="Cannot approve blocked live handoff"):
        await service.record_live_handoff_approval(
            "user-1",
            "blocked-live-approval-run",
            AIStrategyLiveHandoffApprovalRequest(
                decision="approved",
                approver="risk-manager",
                account_confirmed=True,
                risk_limit_confirmed=True,
            ),
            research_workspace_id="research-ws",
        )


@pytest.mark.asyncio
async def test_review_paper_trading_waits_for_minimum_paper_trade_sample():
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

    trade_sample = next(item for item in review.evaluations if item.key == "trade_sample")
    assert trade_sample.threshold == 20.0
    assert trade_sample.actual == 3.0
    assert trade_sample.status == "pending"
    assert review.status == "monitoring"
    assert review.ready_for_live is False
    assert review.live_handoff is None
    assert "继续收集模拟交易数据" in review.next_actions[0]
    updated_run = workspace_service.workspaces["research-ws"].settings["ai_research"]["runs"][0]
    assert updated_run["paper_review_status"] == "monitoring"
    assert updated_run.get("live_handoff") is None
    assert updated_run["pipeline"]["current_stage"] == "paper_review"
    assert updated_run["pipeline"]["ready_for_live"] is False


@pytest.mark.asyncio
async def test_review_paper_trading_normalizes_negative_drawdown_before_live_candidate():
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
            "max_drawdown": -18.0,
            "closed_trades": 20,
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

    drawdown = next(item for item in review.evaluations if item.key == "drawdown_guard")
    assert drawdown.actual == pytest.approx(18.0)
    assert drawdown.threshold == pytest.approx(5.0)
    assert drawdown.status == "failed"
    assert review.status == "needs_research_review"
    assert review.ready_for_live is False
    assert review.unit is not None
    assert review.unit.lock_trading is True
    assert review.unit.lock_running is True
    assert review.pipeline["paper_unit_locked"] is True
    assert review.pipeline["paper_unit_stopped"] is True
    assert review.pipeline["paper_review_lock"]["paper_unit_id"] == "paper-unit"
    assert review.pipeline["paper_review_lock"]["stop_results"][0]["cancelled"] is True
    assert "锁定状态" in review.next_actions[-1]
    assert workspace_service.stopped_units == [("paper-ws", ["paper-unit"])]
    assert workspace_service.updated_units[-1].lock_trading is True
    assert workspace_service.updated_units[-1].lock_running is True
    assert workspace_service.updated_units[-1].unit_settings["ai_research_review_lock"][
        "status"
    ] == "needs_research_review"
    assert workspace_service.updated_units[-1].unit_settings["ai_research_review_lock"][
        "stop_results"
    ][0]["cancelled"] is True
    persisted_run = workspace_service.workspaces["research-ws"].settings["ai_research"][
        "runs"
    ][0]
    assert persisted_run["paper_handoff"]["paper_review_lock"]["status"] == (
        "needs_research_review"
    )
    assert persisted_run["paper_handoff"]["paper_review_lock"]["paper_unit_id"] == "paper-unit"
    assert persisted_run["pipeline"]["paper_unit_locked"] is True
    assert persisted_run["pipeline"]["paper_unit_stopped"] is True
    assert persisted_run["pipeline"]["paper_review_lock"]["stop_results"][0]["cancelled"] is True


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
            "closed_trades": 20,
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
    assert result.paper_trading.handoff["asset_specs"]["IF2609"]["multiplier"] == 300
    assert result.paper_trading.handoff["asset_specs"]["IF2609"]["commission_rate"] == pytest.approx(
        0.002
    )
    assert result.run_record is not None
    assert result.run_record.asset_specs["IF2609"]["margin_rate"] == pytest.approx(0.1)
    assert result.run_record.paper_handoff["asset_specs"]["IF2609"]["source"] == (
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
            "closed_trades": 20,
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
        "backtest_timeout_seconds": 1800,
        "poll_interval_seconds": 4,
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
    assert result.run_record.backtest_timeout_seconds == pytest.approx(1800)
    assert result.run_record.poll_interval_seconds == pytest.approx(4)


@pytest.mark.asyncio
async def test_research_loop_can_continue_from_strategy_snapshot_when_seed_missing():
    workspace_service = FakeWorkspaceService()
    seed_draft = build_ai_strategy_draft("请生成一个均线趋势策略").model_copy(
        update={"name": "历史快照策略"}
    )
    snapshot_strategy = _strategy("snapshot-strategy", seed_draft)
    previous_record = {
        **_run_record(
            "snapshot-run",
            workspace_id="research-ws",
            completed_at="2026-01-01T00:01:00+00:00",
        ),
        "best_strategy_id": "snapshot-strategy",
        "best_strategy_name": "历史快照策略",
        "iterations": [
            {
                "iteration": 2,
                "strategy_id": "snapshot-strategy",
                "strategy_name": "历史快照策略",
                "strategy_snapshot": {
                    "id": snapshot_strategy.id,
                    "name": snapshot_strategy.name,
                    "description": snapshot_strategy.description,
                    "code": snapshot_strategy.code,
                    "params": {
                        key: value.model_dump(mode="json")
                        for key, value in snapshot_strategy.params.items()
                    },
                    "category": snapshot_strategy.category,
                    "created_at": snapshot_strategy.created_at.isoformat(),
                    "updated_at": snapshot_strategy.updated_at.isoformat(),
                },
                "unit_id": "unit-2",
                "task_id": "task-2",
                "run_status": "completed",
                "metrics": {"sharpe_ratio": 0.88, "total_trades": 4},
                "sharpe_ratio": 0.88,
                "total_trades": 4,
                "quality_score": 88.0,
                "quality_gate_evaluations": [],
                "passed": False,
                "quality_gate_failures": ["Sharpe 0.880 below target 1.000"],
                "improvement_notes": [],
                "next_actions": [],
            }
        ],
    }
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={"settings": {"ai_research": {"runs": [previous_record]}}}
    )
    strategy_service = FakeStrategyService(
        workspace_service,
        [{"sharpe_ratio": 1.14, "total_trades": 7}],
        strategies={},
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
            prompt="继续历史快照投研",
            symbol="000001.SZ",
            target_sharpe=1.0,
            continue_from_run_id="snapshot-run",
            start_paper_trading=False,
            out_of_sample_validation=False,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is True
    assert strategy_service.generated == 0
    assert strategy_service.submitted_drafts[0].name == "历史快照策略"
    assert strategy_service.submitted_drafts[0].code.strip() == snapshot_strategy.code.strip()
    assert result.run_record is not None
    assert result.run_record.seed_strategy_id == "snapshot-strategy"
    assert result.run_record.continued_from_run_id == "snapshot-run"


@pytest.mark.asyncio
async def test_research_loop_can_continue_from_code_snapshot_without_strategy_id():
    workspace_service = FakeWorkspaceService()
    seed_draft = build_ai_strategy_draft("请生成一个均线趋势策略").model_copy(
        update={"name": "无ID历史快照策略"}
    )
    snapshot_strategy = _strategy("ignored-snapshot-id", seed_draft)
    previous_record = {
        **_run_record(
            "snapshot-no-id-run",
            workspace_id="research-ws",
            completed_at="2026-01-01T00:01:00+00:00",
        ),
        "best_strategy_id": None,
        "best_strategy_name": "无ID历史快照策略",
        "iterations": [
            {
                "iteration": 1,
                "strategy_name": "无ID历史快照策略",
                "strategy_snapshot": {
                    "name": snapshot_strategy.name,
                    "description": snapshot_strategy.description,
                    "code": snapshot_strategy.code,
                    "params": {
                        key: value.model_dump(mode="json")
                        for key, value in snapshot_strategy.params.items()
                    },
                    "category": snapshot_strategy.category,
                    "created_at": snapshot_strategy.created_at.isoformat(),
                    "updated_at": snapshot_strategy.updated_at.isoformat(),
                },
                "metrics": {"sharpe_ratio": 0.72, "total_trades": 3},
                "sharpe_ratio": 0.72,
                "total_trades": 3,
                "quality_score": 72.0,
                "passed": False,
                "quality_gate_failures": ["Sharpe 0.720 below target 1.000"],
            }
        ],
    }
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={"settings": {"ai_research": {"runs": [previous_record]}}}
    )
    strategy_service = FakeStrategyService(
        workspace_service,
        [{"sharpe_ratio": 1.13, "total_trades": 6}],
        strategies={},
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
            prompt="继续无ID历史快照投研",
            symbol="000001.SZ",
            target_sharpe=1.0,
            continue_from_run_id="snapshot-no-id-run",
            start_paper_trading=False,
            out_of_sample_validation=False,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is True
    assert strategy_service.generated == 0
    assert strategy_service.submitted_drafts[0].name == "无ID历史快照策略"
    assert strategy_service.submitted_drafts[0].code.strip() == snapshot_strategy.code.strip()
    assert result.run_record is not None
    assert result.run_record.seed_strategy_id == "snapshot-no-id-run-strategy"
    assert result.run_record.continued_from_run_id == "snapshot-no-id-run"


@pytest.mark.asyncio
async def test_research_loop_uses_highest_quality_snapshot_when_best_iteration_missing():
    workspace_service = FakeWorkspaceService()
    weak_draft = build_ai_strategy_draft("请生成一个均线趋势策略").model_copy(
        update={"name": "低质量快照策略"}
    )
    strong_draft = build_ai_strategy_draft("请生成一个均线趋势策略").model_copy(
        update={"name": "高质量快照策略"}
    )
    weak_strategy = _strategy("snapshot-weak", weak_draft)
    strong_strategy = _strategy("snapshot-strong", strong_draft)
    previous_record = {
        **_run_record(
            "snapshot-run",
            workspace_id="research-ws",
            completed_at="2026-01-01T00:01:00+00:00",
        ),
        "best_iteration": None,
        "best_strategy_id": None,
        "best_strategy_name": None,
        "best_sharpe": 0.74,
        "best_quality_score": 74.0,
        "iterations": [
            {
                "iteration": 1,
                "strategy_id": "snapshot-weak",
                "strategy_name": "低质量快照策略",
                "strategy_snapshot": {
                    "id": weak_strategy.id,
                    "name": weak_strategy.name,
                    "description": weak_strategy.description,
                    "code": weak_strategy.code,
                    "params": {
                        key: value.model_dump(mode="json")
                        for key, value in weak_strategy.params.items()
                    },
                    "category": weak_strategy.category,
                    "created_at": weak_strategy.created_at.isoformat(),
                    "updated_at": weak_strategy.updated_at.isoformat(),
                },
                "metrics": {"sharpe_ratio": 0.25, "total_trades": 1},
                "sharpe_ratio": 0.25,
                "total_trades": 1,
                "quality_score": 25.0,
                "passed": False,
                "quality_gate_failures": ["Sharpe 0.250 below target 1.000"],
            },
            {
                "iteration": 2,
                "strategy_id": "snapshot-strong",
                "strategy_name": "高质量快照策略",
                "strategy_snapshot": {
                    "id": strong_strategy.id,
                    "name": strong_strategy.name,
                    "description": strong_strategy.description,
                    "code": strong_strategy.code,
                    "params": {
                        key: value.model_dump(mode="json")
                        for key, value in strong_strategy.params.items()
                    },
                    "category": strong_strategy.category,
                    "created_at": strong_strategy.created_at.isoformat(),
                    "updated_at": strong_strategy.updated_at.isoformat(),
                },
                "metrics": {"sharpe_ratio": 0.74, "total_trades": 5},
                "sharpe_ratio": 0.74,
                "total_trades": 5,
                "quality_score": 74.0,
                "passed": False,
                "quality_gate_failures": ["Sharpe 0.740 below target 1.000"],
            },
        ],
    }
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={"settings": {"ai_research": {"runs": [previous_record]}}}
    )
    strategy_service = FakeStrategyService(
        workspace_service,
        [{"sharpe_ratio": 1.12, "total_trades": 6}],
        strategies={},
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
            prompt="继续历史快照投研",
            symbol="000001.SZ",
            target_sharpe=1.0,
            continue_from_run_id="snapshot-run",
            start_paper_trading=False,
            out_of_sample_validation=False,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is True
    assert strategy_service.generated == 0
    assert strategy_service.submitted_drafts[0].name == "高质量快照策略"
    assert strategy_service.submitted_drafts[0].code.strip() == strong_strategy.code.strip()
    assert result.run_record is not None
    assert result.run_record.seed_strategy_id == "snapshot-strong"
    assert result.run_record.continued_from_run_id == "snapshot-run"


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
async def test_research_loop_continuation_improves_cancelled_research_before_backtest():
    workspace_service = FakeWorkspaceService()
    previous_record = {
        **_run_record(
            "cancelled-research-run",
            workspace_id="research-ws",
            completed_at="2026-01-01T00:01:00+00:00",
        ),
        "status": "cancelled",
        "achieved": False,
        "best_iteration": 1,
        "best_sharpe": 0.42,
        "best_metrics": {"sharpe_ratio": 0.42, "total_trades": 2, "max_drawdown": -10.0},
        "next_actions": ["AI投研任务已取消，已保存取消前完成的回测迭代。"],
        "pipeline": {"current_stage": "cancelled", "status": "cancelled", "steps": []},
        "iterations": [
            {
                "iteration": 1,
                "strategy_id": "strategy-2",
                "strategy_name": "取消前策略",
                "unit_id": "unit-1",
                "task_id": "task-1",
                "run_status": "completed",
                "metrics": {"sharpe_ratio": 0.42, "total_trades": 2, "max_drawdown": -10.0},
                "sharpe_ratio": 0.42,
                "total_trades": 2,
                "quality_score": 42.0,
                "quality_gate_evaluations": [],
                "passed": False,
                "failure_reason": "Sharpe 0.420 below target 1.000",
                "quality_gate_failures": ["Sharpe 0.420 below target 1.000"],
                "improvement_plan": ["取消后继续时先降低噪声交易并收紧出场。"],
                "improvement_notes": [],
                "next_actions": [],
            }
        ],
    }
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={"settings": {"ai_research": {"runs": [previous_record]}}}
    )
    seed_draft = build_ai_strategy_draft("请生成一个均线趋势策略").model_copy(
        update={"name": "取消前策略"}
    )
    seed_strategy = _strategy("strategy-2", seed_draft)
    strategy_service = FakeStrategyService(
        workspace_service,
        [{"sharpe_ratio": 1.08, "total_trades": 5, "max_drawdown": -5.0}],
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
            prompt="继续取消前投研",
            symbol="000001.SZ",
            target_sharpe=1.0,
            continue_from_run_id="cancelled-research-run",
            start_paper_trading=False,
            out_of_sample_validation=False,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is True
    assert strategy_service.generated == 0
    assert strategy_service.submitted_drafts[0].name == "取消前策略 v1"
    assert "基于上一轮取消前已完成迭代" in result.iterations[0].improvement_notes[0]
    assert any(
        "Sharpe 0.420 below target 1.000" in note
        for note in result.iterations[0].improvement_notes
    )
    assert result.run_record is not None
    assert result.run_record.continued_from_run_id == "cancelled-research-run"


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
    improver = RecordingImprover()
    service = AIStrategyResearchService(
        strategy_service=strategy_service,
        workspace_service=workspace_service,
        improver=improver,
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
    assert len(improver.calls) == 1
    continuation_metrics = improver.calls[0]["metrics"]
    assert continuation_metrics["max_drawdown"] == pytest.approx(18.0)
    assert "drawdown" in continuation_metrics["failure_categories"]
    assert continuation_metrics["research_feedback"]["source"] == "paper_review"
    assert continuation_metrics["research_feedback"]["paper_review_status"] == (
        "needs_research_review"
    )
    assert continuation_metrics["research_feedback"]["paper_review_evaluations"][0]["key"] == (
        "drawdown_guard"
    )
    assert any("收紧风控" in item for item in continuation_metrics["improvement_plan"])
    assert "基于上一轮模拟交易复核结果" in result.iterations[0].improvement_notes[0]
    assert any("止损" in note or "风控" in note for note in result.iterations[0].improvement_notes)
    assert result.run_record is not None
    assert result.run_record.continued_from_run_id == "paper-failed-run"


@pytest.mark.asyncio
async def test_research_loop_continuation_uses_live_handoff_rejection_before_backtest():
    workspace_service = FakeWorkspaceService()
    record = {
        **_run_record(
            "live-rejected-run",
            workspace_id="research-ws",
            completed_at="2026-01-01T00:01:00+00:00",
        ),
        "paper_review_status": "ready_for_live_candidate",
        "paper_review_ready_for_live": True,
        "paper_reviewed_at": "2026-01-02T00:00:00+00:00",
        "paper_review_evaluations": [
            {
                "key": "rolling_sharpe",
                "label": "模拟交易滚动 Sharpe",
                "metric": "rolling_sharpe",
                "window": "30 trading days",
                "direction": "min",
                "threshold": 0.6,
                "actual": 0.82,
                "source": "unit_status.metrics_snapshot",
                "status": "passed",
                "passed": True,
                "action": "继续观察",
            }
        ],
        "live_handoff": {
            "run_id": "live-rejected-run",
            "research_workspace_id": "research-ws",
            "generated_at": "2026-01-02T00:01:00+00:00",
            "ready_for_live": True,
            "status": "approval_rejected",
            "approval_required": True,
            "paper_workspace_id": "paper-ws",
            "paper_unit_id": "paper-unit",
            "best_strategy_id": "strategy-2",
            "best_strategy_name": "AI趋势策略",
            "symbol": "000001.SZ",
            "symbol_name": "平安银行",
            "timeframe": "1d",
            "timeframe_n": 1,
            "target_sharpe": 1.0,
            "best_sharpe": 1.21,
            "best_metrics": {"sharpe_ratio": 1.21, "total_trades": 5},
            "asset_specs": {},
            "backtest_environment": {"initial_cash": 100000.0, "commission": 0.001},
            "paper_review_status": "ready_for_live_candidate",
            "paper_reviewed_at": "2026-01-02T00:00:00+00:00",
            "paper_review_evaluations": [],
            "paper_monitoring_plan": [],
            "live_readiness_checklist": [],
            "approvals_required": [],
            "deployment_blockers": [],
            "approval_status": "rejected",
            "handoff": {},
            "pipeline": {
                "current_stage": "live_handoff",
                "status": "approval_rejected",
                "progress": 100,
                "ready_for_live": True,
                "live_handoff_status": "approval_rejected",
                "steps": [],
            },
            "next_actions": [
                "实盘交接包已被人工驳回，需处理审批意见后重新进入模拟复核或继续投研。",
            ],
        },
        "live_handoff_approval": {
            "run_id": "live-rejected-run",
            "research_workspace_id": "research-ws",
            "decision": "rejected",
            "approved": False,
            "decided_at": "2026-01-02T00:02:00+00:00",
            "decided_by": "risk-manager",
            "comment": "单笔风险过高，先降低仓位并重新观察模拟成交成本。",
            "account_confirmed": False,
            "risk_limit_confirmed": False,
            "handoff_status_at_decision": "ready_for_approval",
            "blockers": [],
        },
        "pipeline": {
            "current_stage": "live_handoff",
            "status": "approval_rejected",
            "progress": 100,
            "ready_for_live": True,
            "live_handoff_status": "approval_rejected",
            "live_handoff_approval_status": "rejected",
            "steps": [],
        },
        "next_actions": [
            "实盘交接包已被人工驳回，需处理审批意见后重新进入模拟复核或继续投研。",
            "驳回意见：单笔风险过高，先降低仓位并重新观察模拟成交成本。",
        ],
    }
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={"settings": {"ai_research": {"runs": [record]}}}
    )
    seed_draft = build_ai_strategy_draft("请生成一个均线趋势策略").model_copy(
        update={"name": "实盘驳回策略"}
    )
    seed_strategy = _strategy("strategy-2", seed_draft)
    strategy_service = FakeStrategyService(
        workspace_service,
        [{"sharpe_ratio": 1.16, "total_trades": 8, "max_drawdown": -6.0}],
        strategies={"strategy-2": seed_strategy},
    )
    improver = RecordingImprover()
    service = AIStrategyResearchService(
        strategy_service=strategy_service,
        workspace_service=workspace_service,
        improver=improver,
        sleep=_noop_sleep,
    )

    result = await service.run(
        "user-1",
        AIStrategyResearchRunRequest(
            prompt="继续实盘交接驳回后的策略投研",
            symbol="000001.SZ",
            target_sharpe=1.0,
            continue_from_run_id="live-rejected-run",
            start_paper_trading=False,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is True
    assert strategy_service.generated == 0
    assert strategy_service.submitted_drafts[0].name == "实盘驳回策略 v1"
    assert len(improver.calls) == 1
    continuation_metrics = improver.calls[0]["metrics"]
    assert "live_handoff_rejected" in continuation_metrics["failure_categories"]
    assert continuation_metrics["research_feedback"]["source"] == "live_handoff_rejected"
    assert continuation_metrics["research_feedback"]["live_handoff_approval"]["decision"] == (
        "rejected"
    )
    assert "单笔风险过高" in continuation_metrics["research_feedback"][
        "live_handoff_approval"
    ]["comment"]
    assert any("实盘交接驳回" in item for item in continuation_metrics["improvement_plan"])
    assert "基于上一轮实盘交接驳回意见" in result.iterations[0].improvement_notes[0]
    assert any("实盘交接人工审批未通过" in note for note in result.iterations[0].improvement_notes)
    assert result.run_record is not None
    assert result.run_record.continued_from_run_id == "live-rejected-run"


@pytest.mark.asyncio
async def test_research_loop_continuation_from_failed_paper_review_restarts_paper_trading():
    workspace_service = FakeWorkspaceService()
    record = {
        **_run_record(
            "paper-review-loop-run",
            workspace_id="research-ws",
            completed_at="2026-01-01T00:01:00+00:00",
        ),
        "paper_workspace_id": "old-paper-ws",
        "paper_workspace_name": "旧模拟工作区",
        "paper_unit_id": "old-paper-unit",
        "paper_trading_started": True,
        "paper_review_status": "needs_research_review",
        "paper_review_ready_for_live": False,
        "paper_reviewed_at": "2026-01-02T00:00:00+00:00",
        "paper_review_evaluations": [
            {
                "key": "rolling_sharpe",
                "label": "模拟交易滚动 Sharpe",
                "metric": "rolling_sharpe",
                "window": "30 trading days",
                "direction": "min",
                "threshold": 0.6,
                "actual": 0.18,
                "source": "unit_status.metrics_snapshot",
                "status": "failed",
                "passed": False,
                "action": "回到研究工作区降低过拟合并收紧风险预算。",
            }
        ],
        "paper_review_next_actions": ["回到研究工作区降低过拟合并收紧风险预算。"],
        "paper_handoff": {
            "gateway_config": {"name": "paper_gateway", "params": {"exchange": "sim"}},
            "backtest_environment": {"initial_cash": 100000.0, "commission": 0.001},
        },
    }
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={"settings": {"ai_research": {"runs": [record]}}}
    )
    seed_draft = build_ai_strategy_draft("请生成一个均线趋势策略").model_copy(
        update={"name": "模拟复核失败策略"}
    )
    seed_strategy = _strategy("strategy-2", seed_draft)
    strategy_service = FakeStrategyService(
        workspace_service,
        [{"sharpe_ratio": 1.22, "total_trades": 8, "max_drawdown": -5.0}],
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
            prompt="继续模拟复核失败后的策略投研",
            symbol="000001.SZ",
            target_sharpe=1.0,
            continue_from_run_id="paper-review-loop-run",
            paper_workspace_name="AI模拟-修复版",
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is True
    assert result.status == "achieved"
    assert result.paper_trading is not None
    assert result.paper_trading.started is True
    assert result.paper_trading.workspace.name == "AI模拟-修复版"
    assert result.paper_trading.handoff is not None
    assert result.paper_trading.handoff["continued_from_run_id"] == "paper-review-loop-run"
    assert result.paper_trading.handoff["paper_task_id"] == "paper-task"
    assert result.paper_trading.handoff["gateway_config"]["name"] == "paper_gateway"
    assert workspace_service.started_units == [("paper-ws", ["paper-unit"])]
    assert strategy_service.generated == 0
    assert strategy_service.submitted_drafts[0].name == "模拟复核失败策略 v1"
    assert "基于上一轮模拟交易复核结果" in result.iterations[0].improvement_notes[0]
    assert any("rolling_sharpe" in note or "滚动 Sharpe" in note for note in result.iterations[0].improvement_notes)
    assert result.run_record is not None
    assert result.run_record.continued_from_run_id == "paper-review-loop-run"
    assert result.run_record.paper_trading_started is True
    assert result.run_record.paper_workspace_name == "AI模拟-修复版"
    assert result.run_record.paper_handoff["continued_from_run_id"] == "paper-review-loop-run"
    assert result.run_record.pipeline["current_stage"] == "paper_review"


@pytest.mark.asyncio
async def test_research_loop_continuation_uses_expired_live_candidate_before_backtest():
    workspace_service = FakeWorkspaceService()
    record = {
        **_run_record(
            "expired-live-run",
            workspace_id="research-ws",
            completed_at="2026-01-01T00:01:00+00:00",
        ),
        "paper_trading_started": True,
        "paper_review_status": "live_readiness_expired",
        "paper_review_ready_for_live": False,
        "paper_reviewed_at": "2026-01-02T00:00:00+00:00",
        "paper_review_evaluations": [
            {
                "key": "rolling_sharpe",
                "label": "模拟交易滚动 Sharpe",
                "metric": "rolling_sharpe",
                "window": "30 trading days",
                "direction": "min",
                "threshold": 0.6,
                "actual": 0.82,
                "source": "unit_status.metrics_snapshot",
                "status": "passed",
                "passed": True,
                "action": "继续监控。",
            }
        ],
        "paper_review_next_actions": ["实盘候选复核已过期，重新复核模拟交易指标后再进入实盘审批。"],
        "live_readiness_checklist": [
            {
                "key": "live_candidate_expired",
                "label": "候选有效期",
                "status": "expired",
                "evidence": "实盘候选有效期已截止。",
                "action": "重新复核模拟交易。",
            }
        ],
    }
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={"settings": {"ai_research": {"runs": [record]}}}
    )
    seed_draft = build_ai_strategy_draft("请生成一个均线趋势策略").model_copy(
        update={"name": "过期候选策略"}
    )
    seed_strategy = _strategy("strategy-2", seed_draft)
    strategy_service = FakeStrategyService(
        workspace_service,
        [{"sharpe_ratio": 1.16, "total_trades": 6, "max_drawdown": -8.0}],
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
            prompt="继续过期实盘候选的策略投研",
            symbol="000001.SZ",
            target_sharpe=1.0,
            continue_from_run_id="expired-live-run",
            start_paper_trading=False,
            max_iterations=1,
            poll_interval_seconds=0.1,
        ),
    )

    assert result.achieved is True
    assert strategy_service.generated == 0
    assert strategy_service.submitted_drafts[0].name == "过期候选策略 v1"
    assert "基于上一轮模拟交易复核结果" in result.iterations[0].improvement_notes[0]
    assert any("实盘候选复核已过期" in note for note in result.iterations[0].improvement_notes)
    assert result.run_record is not None
    assert result.run_record.continued_from_run_id == "expired-live-run"


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
async def test_research_loop_falls_back_when_initial_generated_strategy_fails_sandbox():
    workspace_service = FakeWorkspaceService()
    strategy_service = FakeRuntimeInvalidDraftStrategyService(workspace_service)
    service = AIStrategyResearchService(
        strategy_service=strategy_service,
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )

    result = await service.run(
        "user-1",
        AIStrategyResearchRunRequest(
            prompt="请生成一个运行时无效策略",
            symbol="000001.SZ",
            max_iterations=1,
            poll_interval_seconds=0.1,
            start_paper_trading=False,
        ),
    )

    assert result.achieved is True
    assert strategy_service.backtest_called is True
    assert strategy_service.submitted_drafts
    assert "missing_research_runtime_name" not in strategy_service.submitted_drafts[0].code
    assert "class AIGeneratedStrategy" in strategy_service.submitted_drafts[0].code
    assert result.iterations[0].improvement_notes[0].startswith("AI初始策略代码不可运行")
    assert "sandbox validation failed" in result.iterations[0].improvement_notes[0]


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
            paper_workspace_name="AI模拟-质量通过",
        ),
    )

    assert result.achieved is True
    assert result.paper_trading is not None
    assert result.paper_trading.workspace.name == "AI模拟-质量通过"
    assert result.iterations[0].quality_gate_failures == []
    assert result.run_record is not None
    assert result.run_record.paper_workspace_name == "AI模拟-质量通过"
    assert result.run_record.quality_gates["max_drawdown_limit"] == 10.0
    assert result.paper_trading.handoff is not None
    assert result.paper_trading.handoff["paper_workspace_name"] == "AI模拟-质量通过"
    assert result.paper_trading.handoff["quality_gates"] == result.run_record.quality_gates
    assert result.run_record.paper_handoff["paper_workspace_name"] == "AI模拟-质量通过"


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
        "paper_workspace_name": "AI模拟-历史最佳",
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
    assert result.workspace.name == "AI模拟-历史最佳"
    assert result.handoff is not None
    assert result.handoff["run_id"] == "previous-run"
    assert result.handoff["paper_workspace_name"] == "AI模拟-历史最佳"
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
    assert updated_run["paper_workspace_name"] == "AI模拟-历史最佳"
    assert updated_run["paper_unit_id"] == "paper-unit"
    assert updated_run["paper_monitoring_plan"][0]["key"] == "rolling_sharpe"
    assert updated_run["paper_handoff"]["paper_task_id"] == "paper-task"
    assert updated_run["paper_handoff"]["paper_workspace_name"] == "AI模拟-历史最佳"
    assert updated_run["paper_review_status"] == "monitoring"
    assert updated_run["paper_review_evaluations"][0]["status"] == "pending"
    assert updated_run["pipeline"]["current_stage"] == "paper_review"


@pytest.mark.asyncio
async def test_start_paper_trading_from_achieved_run_without_iteration_snapshot():
    workspace_service = FakeWorkspaceService()
    seed_draft = build_ai_strategy_draft("请生成一个股指期货趋势策略").model_copy(
        update={"name": "历史达标期货策略"}
    )
    strategy = _strategy("strategy-history-best", seed_draft)
    record = {
        **_run_record(
            "compact-achieved-run",
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
        "best_metrics": {"sharpe_ratio": 1.21, "total_trades": 5, "total_pnl": 3200.0},
        "asset_specs": {
            "IF2609": {
                "symbol": "IF2609",
                "source": "stale_local_defaults",
                "multiplier": 200,
                "margin_rate": 0.2,
                "commission_rate": 0.001,
            }
        },
        "backtest_environment": {
            "initial_cash": 100000.0,
            "commission": 0.001,
            "annual_days": 252,
            "calc_method": "simple",
            "weight_mode": "equal",
            "multiplier": 200,
            "margin": 0.2,
            "asset_spec_source": "stale_local_defaults",
        },
        "paper_handoff": {
            "asset_specs": {
                "IF2609": {
                    "symbol": "IF2609",
                    "source": "paper_handoff_exchange_specs",
                    "multiplier": 300,
                    "margin_rate": 0.1,
                    "commission_rate": 0.000023,
                }
            },
            "backtest_environment": {
                "initial_cash": 250000.0,
                "commission": 0.000023,
                "annual_days": 244,
                "calc_method": "log",
                "weight_mode": "value",
                "multiplier": 300,
                "margin": 0.1,
                "asset_spec_source": "paper_handoff_exchange_specs",
            },
            "gateway_config": {
                "name": "paper_gateway",
                "params": {"exchange": "CFFEX", "asset_type": "future"},
            },
        },
        "paper_workspace_id": None,
        "paper_workspace_name": "AI模拟-紧凑历史",
        "paper_unit_id": None,
        "paper_trading_started": False,
        "iterations": [],
    }
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={"settings": {"ai_research": {"runs": [record]}}}
    )
    service = AIStrategyResearchService(
        strategy_service=FakeStrategyService(
            workspace_service,
            [],
            strategies={strategy.id: strategy},
        ),
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )

    result = await service.start_paper_trading_from_run(
        "user-1",
        "compact-achieved-run",
        AIStrategyPaperTradingStartRequest(research_workspace_id="research-ws"),
    )

    assert result.started is True
    assert result.workspace.name == "AI模拟-紧凑历史"
    created_unit = workspace_service.created_units[-1]
    assert created_unit.strategy_id == strategy.id
    assert created_unit.data_config["symbol"] == "IF2609"
    assert created_unit.data_config["contract_metadata"]["IF2609"]["multiplier"] == 300
    assert created_unit.data_config["contract_metadata"]["IF2609"]["source"] == (
        "paper_handoff_exchange_specs"
    )
    assert created_unit.unit_settings["commission"] == pytest.approx(0.000023)
    assert created_unit.unit_settings["annual_days"] == 244
    assert created_unit.unit_settings["calc_method"] == "log"
    assert created_unit.gateway_config["params"]["exchange"] == "CFFEX"
    assert result.handoff["research_unit_id"] == "compact-achieved-run-unit"
    assert result.handoff["best_metrics"]["sharpe_ratio"] == pytest.approx(1.21)
    assert result.handoff["best_metrics"]["total_pnl"] == pytest.approx(3200.0)
    assert result.handoff["asset_specs"]["IF2609"]["source"] == (
        "paper_handoff_exchange_specs"
    )
    assert result.handoff["gateway_config"]["params"]["exchange"] == "CFFEX"
    updated_run = workspace_service.workspaces["research-ws"].settings["ai_research"]["runs"][0]
    assert updated_run["paper_trading_started"] is True
    assert updated_run["paper_unit_id"] == "paper-unit"
    assert updated_run["pipeline"]["current_stage"] == "paper_review"


@pytest.mark.asyncio
async def test_start_paper_trading_from_history_rejects_duplicate_active_paper():
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
    paper_unit = _unit("paper-unit", "paper-ws", strategy)
    workspace_service.units[research_unit.id] = research_unit
    workspace_service.units[paper_unit.id] = paper_unit
    workspace_service.workspaces["paper-ws"] = _workspace("paper-ws", "trading")
    record = {
        **_run_record(
            "previous-run",
            workspace_id="research-ws",
            completed_at="2026-01-01T00:01:00+00:00",
        ),
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

    with pytest.raises(ValueError, match="already started paper trading"):
        await service.start_paper_trading_from_run(
            "user-1",
            "previous-run",
            AIStrategyPaperTradingStartRequest(research_workspace_id="research-ws"),
        )

    assert workspace_service.started_units == []


@pytest.mark.asyncio
async def test_start_paper_trading_from_history_restarts_missing_paper_unit():
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
    workspace_service.workspaces["paper-ws"] = _workspace("paper-ws", "trading")
    record = {
        **_run_record(
            "previous-run",
            workspace_id="research-ws",
            completed_at="2026-01-01T00:01:00+00:00",
        ),
        "paper_unit_id": "deleted-paper-unit",
        "paper_review_status": "paper_unit_missing",
        "paper_review_ready_for_live": False,
        "paper_review_next_actions": [
            "未找到模拟交易单元，检查是否被删除，必要时重新从投研结果启动模拟交易。",
        ],
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

    result = await service.start_paper_trading_from_run(
        "user-1",
        "previous-run",
        AIStrategyPaperTradingStartRequest(research_workspace_id="research-ws"),
    )

    assert result.started is True
    assert result.workspace.id == "paper-ws"
    assert result.unit.id == "paper-unit"
    assert workspace_service.started_units == [("paper-ws", ["paper-unit"])]
    updated_run = workspace_service.workspaces["research-ws"].settings["ai_research"]["runs"][0]
    assert updated_run["paper_trading_started"] is True
    assert updated_run["paper_workspace_id"] == "paper-ws"
    assert updated_run["paper_unit_id"] == "paper-unit"
    assert updated_run["paper_handoff"]["paper_task_id"] == "paper-task"
    assert updated_run["paper_review_status"] == "monitoring"
    assert updated_run["paper_review_evaluations"][0]["status"] == "pending"
    assert updated_run["pipeline"]["current_stage"] == "paper_review"


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
                "strategy_snapshot": {
                    "id": strategy.id,
                    "name": strategy.name,
                    "description": strategy.description,
                    "code": strategy.code,
                    "params": {
                        key: value.model_dump(mode="json")
                        for key, value in strategy.params.items()
                    },
                    "category": strategy.category,
                    "created_at": strategy.created_at.isoformat(),
                    "updated_at": strategy.updated_at.isoformat(),
                },
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
        strategies={},
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
    assert created_unit.strategy_id == strategy.id
    assert created_unit.strategy_name == strategy.name
    assert created_unit.data_config["contract_metadata"]["IF2609"]["multiplier"] == 300
    assert created_unit.unit_settings["commission"] == pytest.approx(0.000023)
    assert created_unit.unit_settings["multiplier"] == 300
    assert created_unit.unit_settings["margin"] == pytest.approx(0.1)
    assert created_unit.unit_settings["asset_spec_source"] == "local_futures_commission"
    assert created_unit.optimization_config == {"enabled": False}
    assert created_unit.gateway_config == {"name": "paper_gateway", "params": {}}
    assert result.handoff["gateway_config"] == {"name": "paper_gateway"}
    assert result.handoff["backtest_environment"]["commission"] == pytest.approx(0.000023)
    assert result.handoff["backtest_environment"]["multiplier"] == 300
    assert result.handoff["backtest_environment"]["asset_spec_source"] == (
        "local_futures_commission"
    )
    assert result.handoff["asset_specs"]["IF2609"]["multiplier"] == 300
    assert result.handoff["asset_specs"]["IF2609"]["commission"] == pytest.approx(0.000023)
    assert result.handoff["asset_specs"]["IF2609"]["asset_spec_source"] == (
        "local_futures_commission"
    )


@pytest.mark.asyncio
async def test_start_paper_trading_from_history_uses_code_snapshot_without_strategy_id():
    workspace_service = FakeWorkspaceService()
    seed_draft = build_ai_strategy_draft("请生成一个均线趋势策略").model_copy(
        update={"name": "无ID历史快照策略"}
    )
    snapshot_strategy = _strategy("ignored-snapshot-id", seed_draft)
    record = {
        **_run_record(
            "paper-snapshot-no-id-run",
            workspace_id="research-ws",
            completed_at="2026-01-01T00:01:00+00:00",
        ),
        "best_strategy_id": None,
        "best_strategy_name": "无ID历史快照策略",
        "paper_workspace_id": None,
        "paper_unit_id": None,
        "paper_trading_started": False,
        "iterations": [
            {
                "iteration": 1,
                "strategy_name": "无ID历史快照策略",
                "strategy_snapshot": {
                    "name": snapshot_strategy.name,
                    "description": snapshot_strategy.description,
                    "code": snapshot_strategy.code,
                    "params": {
                        key: value.model_dump(mode="json")
                        for key, value in snapshot_strategy.params.items()
                    },
                    "category": snapshot_strategy.category,
                    "created_at": snapshot_strategy.created_at.isoformat(),
                    "updated_at": snapshot_strategy.updated_at.isoformat(),
                },
                "unit_id": "snapshot-unit",
                "unit_snapshot": {
                    "id": "snapshot-unit",
                    "workspace_id": "research-ws",
                    "group_name": "无ID历史快照策略",
                    "symbol": "000001.SZ",
                    "symbol_name": "平安银行",
                    "timeframe": "1d",
                    "timeframe_n": 1,
                    "category": snapshot_strategy.category,
                    "data_config": {"symbol": "000001.SZ"},
                    "unit_settings": {"initial_cash": 100000.0, "commission": 0.001},
                    "params": {},
                    "optimization_config": {},
                    "gateway_config": {},
                    "trading_mode": "paper",
                },
                "task_id": "task-snapshot",
                "run_status": "completed",
                "metrics": {"sharpe_ratio": 1.21, "total_trades": 5},
                "sharpe_ratio": 1.21,
                "total_trades": 5,
                "quality_score": 100.0,
                "passed": True,
                "quality_gate_failures": [],
            }
        ],
    }
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={"settings": {"ai_research": {"runs": [record]}}}
    )
    service = AIStrategyResearchService(
        strategy_service=FakeStrategyService(workspace_service, [], strategies={}),
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )

    result = await service.start_paper_trading_from_run(
        "user-1",
        "paper-snapshot-no-id-run",
        AIStrategyPaperTradingStartRequest(research_workspace_id="research-ws"),
    )

    assert result.started is True
    created_unit = workspace_service.created_units[-1]
    assert created_unit.strategy_id == "paper-snapshot-no-id-run-strategy"
    assert created_unit.strategy_name == "无ID历史快照策略"
    assert result.handoff["seed_strategy_id"] == "paper-snapshot-no-id-run-strategy"
    assert result.handoff["research_strategy_id"] == "paper-snapshot-no-id-run-strategy"


@pytest.mark.asyncio
async def test_start_paper_trading_from_history_restores_paper_handoff_runtime_metadata():
    workspace_service = FakeWorkspaceService()
    seed_draft = build_ai_strategy_draft("请生成一个股指期货趋势策略").model_copy(
        update={"name": "历史期货策略"}
    )
    strategy = _strategy("strategy-2", seed_draft)
    record = {
        **_run_record(
            "previous-handoff-run",
            workspace_id="research-ws",
            completed_at="2026-01-01T00:01:00+00:00",
        ),
        "symbol": "IF2609",
        "symbol_name": "沪深300股指期货",
        "initial_cash": 100000.0,
        "commission": 0.001,
        "annual_days": 252,
        "calc_method": "simple",
        "weight_mode": "equal",
        "best_strategy_id": strategy.id,
        "best_strategy_name": strategy.name,
        "asset_specs": {},
        "backtest_environment": {},
        "paper_workspace_id": None,
        "paper_unit_id": None,
        "paper_trading_started": False,
        "paper_handoff": {
            "asset_specs": {
                "IF2609": {
                    "symbol": "IF2609",
                    "source": "paper_handoff_exchange_specs",
                    "multiplier": 300,
                    "margin_rate": 0.1,
                    "commission_rate": 0.000023,
                }
            },
            "backtest_environment": {
                "initial_cash": 250000.0,
                "commission": 0.000023,
                "annual_days": 244,
                "calc_method": "log",
                "weight_mode": "value",
                "multiplier": 300,
                "margin": 0.1,
                "asset_spec_source": "paper_handoff_exchange_specs",
            },
            "gateway_config": {
                "name": "paper_gateway",
                "params": {"exchange": "CFFEX", "asset_type": "future"},
            },
        },
        "iterations": [
            {
                "iteration": 2,
                "strategy_id": strategy.id,
                "strategy_name": strategy.name,
                "strategy_snapshot": {
                    "id": strategy.id,
                    "name": strategy.name,
                    "description": strategy.description,
                    "code": strategy.code,
                    "params": {
                        key: value.model_dump(mode="json")
                        for key, value in strategy.params.items()
                    },
                    "category": strategy.category,
                    "created_at": strategy.created_at.isoformat(),
                    "updated_at": strategy.updated_at.isoformat(),
                },
                "unit_id": "missing-research-unit",
                "unit_snapshot": {
                    "id": "missing-research-unit",
                    "workspace_id": "research-ws",
                    "data_config": {"symbol": "IF2609"},
                    "unit_settings": {"initial_cash": 100000.0, "commission": 0.001},
                    "optimization_config": {},
                    "gateway_config": {},
                },
                "task_id": "task-2",
                "run_status": "completed",
                "metrics": {"sharpe_ratio": 1.21, "total_trades": 5},
                "sharpe_ratio": 1.21,
                "total_trades": 5,
                "quality_score": 100.0,
                "passed": True,
                "quality_gate_failures": [],
            }
        ],
    }
    workspace_service.workspaces["research-ws"] = _workspace("research-ws", "research").model_copy(
        update={"settings": {"ai_research": {"runs": [record]}}}
    )
    service = AIStrategyResearchService(
        strategy_service=FakeStrategyService(workspace_service, [], strategies={}),
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )

    result = await service.start_paper_trading_from_run(
        "user-1",
        "previous-handoff-run",
        AIStrategyPaperTradingStartRequest(research_workspace_id="research-ws"),
    )

    assert result.started is True
    created_unit = workspace_service.created_units[-1]
    assert created_unit.data_config["contract_metadata"]["IF2609"]["source"] == (
        "paper_handoff_exchange_specs"
    )
    assert created_unit.unit_settings["contract_metadata"]["IF2609"]["commission_rate"] == (
        pytest.approx(0.000023)
    )
    assert created_unit.unit_settings["initial_cash"] == pytest.approx(250000.0)
    assert created_unit.unit_settings["commission"] == pytest.approx(0.000023)
    assert created_unit.unit_settings["annual_days"] == 244
    assert created_unit.unit_settings["calc_method"] == "log"
    assert created_unit.unit_settings["weight_mode"] == "value"
    assert created_unit.unit_settings["multiplier"] == 300
    assert created_unit.unit_settings["margin"] == pytest.approx(0.1)
    assert created_unit.unit_settings["asset_spec_source"] == "paper_handoff_exchange_specs"
    assert created_unit.gateway_config == {
        "name": "paper_gateway",
        "params": {"exchange": "CFFEX", "asset_type": "future"},
    }
    assert result.handoff["backtest_environment"]["commission"] == pytest.approx(0.000023)
    assert result.handoff["asset_specs"]["IF2609"]["source"] == "paper_handoff_exchange_specs"
    assert result.handoff["gateway_config"]["params"]["exchange"] == "CFFEX"


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


@pytest.mark.asyncio
async def test_list_research_run_records_marks_expired_live_candidate_for_review():
    workspace_service = FakeWorkspaceService()
    expired_run = {
        **_run_record(
            "expired-live-run",
            workspace_id="research-expired",
            completed_at="2026-01-02T00:00:00+00:00",
        ),
        "paper_review_status": "ready_for_live_candidate",
        "paper_review_ready_for_live": True,
        "paper_reviewed_at": "2000-01-01T00:00:00+00:00",
        "paper_review_evaluations": [
            {
                "key": "rolling_sharpe",
                "label": "模拟交易滚动 Sharpe",
                "metric": "rolling_sharpe",
                "window": "30 trading days",
                "direction": "min",
                "threshold": 0.6,
                "actual": 0.8,
                "source": "unit_status.metrics_snapshot",
                "status": "passed",
                "passed": True,
                "action": "继续观察",
            }
        ],
        "paper_review_next_actions": ["模拟交易监控计划已全部通过，可作为实盘候选进入人工复核。"],
        "live_readiness_checklist": [
            {
                "key": "human_approval_required",
                "label": "人工实盘审批",
                "status": "pending_manual_confirmation",
                "evidence": "模拟复核已达到实盘候选状态。",
                "action": "确认账户权限和上线窗口后再切换实盘。",
            }
        ],
        "live_readiness_expires_at": "2000-01-08T00:00:00+00:00",
        "pipeline": {
            "current_stage": "live_candidate",
            "status": "achieved",
            "progress": 100,
            "ready_for_live": True,
            "live_readiness_expires_at": "2000-01-08T00:00:00+00:00",
            "steps": [],
        },
    }
    workspace_service.workspaces["research-expired"] = _workspace(
        "research-expired",
        "research",
    ).model_copy(
        update={"settings": {"ai_research": {"runs": [expired_run]}}},
    )
    service = AIStrategyResearchService(
        strategy_service=FakeStrategyService(workspace_service, []),
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )

    result = await service.list_run_records("user-1", limit=20)

    record = result.items[0]
    assert record.run_id == "expired-live-run"
    assert record.paper_review_status == "live_readiness_expired"
    assert record.paper_review_ready_for_live is False
    assert record.pipeline["current_stage"] == "paper_review"
    assert record.pipeline["ready_for_live"] is False
    assert record.pipeline["live_readiness_expires_at"] == "2000-01-08T00:00:00+00:00"
    assert record.live_readiness_checklist[-1]["key"] == "live_candidate_expired"
    assert record.live_readiness_checklist[-1]["status"] == "expired"
    assert "重新复核模拟交易" in record.next_actions[0]

    persisted_run = workspace_service.workspaces["research-expired"].settings["ai_research"][
        "runs"
    ][0]
    assert persisted_run["paper_review_status"] == "live_readiness_expired"
    assert persisted_run["paper_review_ready_for_live"] is False
    assert persisted_run["pipeline"]["current_stage"] == "paper_review"
    assert persisted_run["pipeline"]["ready_for_live"] is False
    assert persisted_run["live_readiness_checklist"][-1]["key"] == "live_candidate_expired"
    assert "重新复核模拟交易" in persisted_run["next_actions"][0]


@pytest.mark.asyncio
async def test_list_research_run_records_auto_refreshes_paper_review_from_current_status():
    workspace_service = FakeWorkspaceService()
    seed_draft = build_ai_strategy_draft("生成趋势策略").model_copy(
        update={"name": "自动刷新 paper 策略"}
    )
    strategy = _strategy("strategy-auto-paper", seed_draft)
    record = {
        **_run_record(
            "auto-paper-review-run",
            workspace_id="research-auto-paper",
            completed_at="2026-01-02T00:00:00+00:00",
        ),
        "best_strategy_id": strategy.id,
        "paper_workspace_id": "paper-auto",
        "paper_workspace_name": "AI模拟自动刷新",
        "paper_unit_id": "paper-auto-unit",
        "paper_trading_started": True,
        "paper_review_status": "monitoring",
        "paper_review_ready_for_live": False,
        "paper_reviewed_at": "2026-01-02T00:00:00+00:00",
        "paper_review_evaluations": [
            {
                "key": "rolling_sharpe",
                "label": "模拟交易滚动 Sharpe",
                "metric": "rolling_sharpe",
                "window": "30 trading days",
                "direction": "min",
                "threshold": 0.6,
                "actual": None,
                "source": None,
                "status": "pending",
                "passed": False,
                "action": "继续观察",
            }
        ],
        "paper_review_next_actions": ["继续收集模拟交易数据"],
        "pipeline": {
            "current_stage": "paper_review",
            "status": "achieved",
            "progress": 80.0,
            "ready_for_live": False,
            "steps": [],
        },
    }
    workspace_service.workspaces["research-auto-paper"] = _workspace(
        "research-auto-paper",
        "research",
    ).model_copy(update={"settings": {"ai_research": {"runs": [record]}}})
    workspace_service.workspaces["paper-auto"] = _workspace("paper-auto", "trading")
    unit = _unit("paper-auto-unit", "paper-auto", strategy).model_copy(
        update={"trading_snapshot": {"valuation_status": "confirmed"}}
    )
    workspace_service.units[unit.id] = unit
    workspace_service.statuses[unit.id] = UnitStatusResponse(
        id=unit.id,
        run_status="running",
        last_task_id="paper-auto-task",
        metrics_snapshot={
            "rolling_sharpe": 0.82,
            "max_drawdown": -4.2,
            "closed_trades": 24,
            "slippage_and_commission_delta": 0.0004,
        },
        run_count=1,
        trading_snapshot={"valuation_status": "confirmed"},
        trading_mode="paper",
    )
    service = AIStrategyResearchService(
        strategy_service=FakeStrategyService(
            workspace_service,
            [],
            strategies={strategy.id: strategy},
        ),
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )

    result = await service.list_run_records("user-1", limit=20)

    refreshed = result.items[0]
    assert refreshed.run_id == "auto-paper-review-run"
    assert refreshed.paper_review_status == "ready_for_live_candidate"
    assert refreshed.paper_review_ready_for_live is True
    assert refreshed.paper_monitoring_plan[0]["key"] == "rolling_sharpe"
    assert all(item["passed"] for item in refreshed.paper_review_evaluations)
    assert refreshed.live_readiness_checklist[0]["key"] == "paper_monitoring_passed"
    assert refreshed.live_handoff is not None
    assert refreshed.live_handoff.ready_for_live is True
    assert refreshed.live_handoff.status == "ready_for_approval"
    assert refreshed.pipeline["current_stage"] == "live_handoff"
    assert refreshed.pipeline["live_handoff_ready_for_live"] is True
    assert "实盘候选有效期至" in refreshed.paper_review_next_actions[-1]

    persisted_run = workspace_service.workspaces["research-auto-paper"].settings["ai_research"][
        "runs"
    ][0]
    assert persisted_run["paper_review_status"] == "ready_for_live_candidate"
    assert persisted_run["paper_review_ready_for_live"] is True
    assert persisted_run["paper_review_evaluations"][0]["actual"] == pytest.approx(0.82)
    assert persisted_run["live_handoff"]["status"] == "ready_for_approval"
    assert persisted_run["pipeline"]["current_stage"] == "live_handoff"


@pytest.mark.asyncio
async def test_list_research_run_records_auto_locks_failed_paper_review_unit():
    workspace_service = FakeWorkspaceService()
    seed_draft = build_ai_strategy_draft("生成回撤控制策略").model_copy(
        update={"name": "自动锁定 paper 策略"}
    )
    strategy = _strategy("strategy-auto-lock", seed_draft)
    record = {
        **_run_record(
            "auto-paper-lock-run",
            workspace_id="research-auto-lock",
            completed_at="2026-01-02T00:00:00+00:00",
        ),
        "best_strategy_id": strategy.id,
        "paper_workspace_id": "paper-lock",
        "paper_workspace_name": "AI模拟自动锁定",
        "paper_unit_id": "paper-lock-unit",
        "paper_trading_started": True,
        "paper_review_status": "monitoring",
        "paper_review_ready_for_live": False,
        "pipeline": {
            "current_stage": "paper_review",
            "status": "achieved",
            "progress": 80.0,
            "ready_for_live": False,
            "steps": [],
        },
    }
    workspace_service.workspaces["research-auto-lock"] = _workspace(
        "research-auto-lock",
        "research",
    ).model_copy(update={"settings": {"ai_research": {"runs": [record]}}})
    workspace_service.workspaces["paper-lock"] = _workspace("paper-lock", "trading")
    unit = _unit("paper-lock-unit", "paper-lock", strategy).model_copy(
        update={"trading_snapshot": {"valuation_status": "confirmed"}}
    )
    workspace_service.units[unit.id] = unit
    workspace_service.statuses[unit.id] = UnitStatusResponse(
        id=unit.id,
        run_status="running",
        last_task_id="paper-lock-task",
        metrics_snapshot={
            "rolling_sharpe": 0.8,
            "max_drawdown": -22.0,
            "closed_trades": 25,
            "slippage_and_commission_delta": 0.0002,
        },
        run_count=1,
        trading_snapshot={"valuation_status": "confirmed"},
        trading_mode="paper",
    )
    service = AIStrategyResearchService(
        strategy_service=FakeStrategyService(
            workspace_service,
            [],
            strategies={strategy.id: strategy},
        ),
        workspace_service=workspace_service,
        improver=LocalStrategyImprover(),
        sleep=_noop_sleep,
    )

    result = await service.list_run_records("user-1", limit=20)

    refreshed = result.items[0]
    assert refreshed.run_id == "auto-paper-lock-run"
    assert refreshed.paper_review_status == "needs_research_review"
    assert refreshed.paper_review_ready_for_live is False
    assert refreshed.pipeline["current_stage"] == "paper_review"
    assert refreshed.pipeline["paper_unit_locked"] is True
    assert refreshed.pipeline["paper_unit_stopped"] is True
    assert refreshed.pipeline["paper_review_lock"]["paper_workspace_id"] == "paper-lock"
    assert refreshed.paper_handoff["paper_review_lock"]["paper_unit_id"] == "paper-lock-unit"
    assert "已自动停止并锁定模拟交易单元" in refreshed.next_actions[-1]
    assert workspace_service.stopped_units == [("paper-lock", ["paper-lock-unit"])]
    assert workspace_service.updated_units[-1].id == "paper-lock-unit"
    assert workspace_service.updated_units[-1].lock_trading is True
    assert workspace_service.updated_units[-1].lock_running is True
    assert workspace_service.updated_units[-1].unit_settings["ai_research_review_lock"][
        "status"
    ] == "needs_research_review"
    assert workspace_service.updated_units[-1].unit_settings["ai_research_review_lock"][
        "stop_results"
    ][0]["unit_id"] == "paper-lock-unit"

    persisted_run = workspace_service.workspaces["research-auto-lock"].settings["ai_research"][
        "runs"
    ][0]
    assert persisted_run["paper_review_status"] == "needs_research_review"
    assert persisted_run["paper_review_evaluations"][1]["key"] == "drawdown_guard"
    assert persisted_run["paper_review_evaluations"][1]["status"] == "failed"
    assert persisted_run["paper_handoff"]["paper_review_lock"]["paper_unit_id"] == (
        "paper-lock-unit"
    )
    assert persisted_run["pipeline"]["paper_unit_locked"] is True
    assert persisted_run["pipeline"]["paper_review_lock"]["stop_results"][0]["unit_id"] == (
        "paper-lock-unit"
    )
    assert "已自动停止并锁定模拟交易单元" in persisted_run["next_actions"][-1]


class FakeResearchAPIService:
    async def run(
        self,
        user_id: str,
        request: AIStrategyResearchRunRequest,
        *,
        progress_callback=None,
    ):
        workspace = _workspace("research-api-ws", "research")
        draft = build_ai_strategy_draft(request.prompt)
        strategy = _strategy("strategy-api", draft)
        unit = _unit(
            "unit-api",
            workspace.id,
            strategy,
            metrics={"sharpe_ratio": 1.05, "total_trades": 4},
        )
        if progress_callback is not None:
            await progress_callback(
                {
                    "run_id": "api-run",
                    "research_workspace_id": workspace.id,
                    "current_stage": "workspace_ready",
                    "progress": 4.0,
                    "iteration_count": 0,
                    "max_iterations": request.max_iterations,
                    "message": "fake research workspace ready",
                }
            )
        return AIStrategyResearchRunResponse(
            run_id="api-run",
            status="achieved",
            achieved=True,
            target_sharpe=request.target_sharpe,
            started_at="2026-01-01T00:00:00+00:00",
            completed_at="2026-01-01T00:01:00+00:00",
            best_iteration=1,
            best_quality_score=100.0,
            best_quality_gate_evaluations=[
                {
                    "key": "sharpe",
                    "label": "Sharpe",
                    "actual": 1.05,
                    "target": request.target_sharpe,
                    "direction": "min",
                    "passed": True,
                    "score": 1.0,
                }
            ],
            best_diagnostics={
                "summary": "第 1 轮已通过全部质量门槛，可进入模拟交易候选。",
                "promotion_ready": True,
                "improvement_plan": ["进入模拟交易后优先验证成交、滑点和费用。"],
            },
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
            live_readiness_expires_at="2026-01-08T00:02:00+00:00",
            live_readiness_checklist=[
                {
                    "key": "paper_monitoring_passed",
                    "label": "模拟监控通过",
                    "status": "passed",
                    "evidence": "模拟交易滚动 Sharpe 0.8 / 0.6，来源 unit_status.metrics_snapshot",
                    "action": "继续监控同一组指标。",
                },
                {
                    "key": "human_approval_required",
                    "label": "人工实盘审批",
                    "status": "pending_manual_confirmation",
                    "evidence": "模拟复核已达到实盘候选状态。",
                    "action": "确认账户权限和上线窗口后再切换实盘。",
                },
            ],
            pipeline={
                "current_stage": "live_candidate",
                "status": "achieved",
                "progress": 100,
                "ready_for_live": True,
                "live_readiness_checklist": [
                    {
                        "key": "paper_monitoring_passed",
                        "label": "模拟监控通过",
                        "status": "passed",
                        "evidence": "模拟交易滚动 Sharpe 0.8 / 0.6，来源 unit_status.metrics_snapshot",
                        "action": "继续监控同一组指标。",
                    },
                ],
                "live_readiness_expires_at": "2026-01-08T00:02:00+00:00",
                "steps": [],
            },
            next_actions=["模拟交易监控计划已全部通过，可作为实盘候选进入人工复核。"],
        )

    async def build_live_handoff_package(
        self,
        user_id: str,
        run_id: str,
        *,
        research_workspace_id: str | None = None,
    ):
        live_readiness_checklist = [
            {
                "key": "paper_monitoring_passed",
                "label": "模拟监控通过",
                "status": "passed",
                "evidence": "模拟交易滚动 Sharpe 0.8 / 0.6，来源 unit_status.metrics_snapshot",
                "action": "继续监控同一组指标。",
            },
            {
                "key": "human_approval_required",
                "label": "人工实盘审批",
                "status": "pending_manual_confirmation",
                "evidence": "模拟复核已达到实盘候选状态。",
                "action": "确认账户权限和上线窗口后再切换实盘。",
            },
        ]
        return AIStrategyLiveHandoffPackage(
            run_id=run_id,
            research_workspace_id=research_workspace_id or "research-api-ws",
            generated_at="2026-01-01T00:03:00+00:00",
            ready_for_live=True,
            status="ready_for_approval",
            approval_required=True,
            expires_at="2026-01-08T00:02:00+00:00",
            paper_workspace_id="paper-api-ws",
            paper_unit_id="paper-api-unit",
            best_strategy_id="strategy-api",
            best_strategy_name="AI趋势策略",
            symbol="000001.SZ",
            symbol_name="平安银行",
            timeframe="1d",
            timeframe_n=1,
            target_sharpe=1.0,
            best_sharpe=1.05,
            best_metrics={"sharpe_ratio": 1.05, "total_trades": 4},
            asset_specs={
                "000001.SZ": {
                    "symbol": "000001.SZ",
                    "asset_class": "stock",
                    "multiplier": 1,
                    "commission_rate": 0.001,
                }
            },
            backtest_environment={"initial_cash": 100000, "commission": 0.001},
            paper_review_status="ready_for_live_candidate",
            paper_reviewed_at="2026-01-01T00:02:00+00:00",
            paper_review_evaluations=[
                {
                    "key": "rolling_sharpe",
                    "label": "模拟交易滚动 Sharpe",
                    "metric": "rolling_sharpe",
                    "window": "30 trading days",
                    "direction": "min",
                    "threshold": 0.6,
                    "actual": 0.8,
                    "source": "unit_status.metrics_snapshot",
                    "status": "passed",
                    "passed": True,
                    "action": "继续观察",
                }
            ],
            paper_monitoring_plan=[
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
            live_readiness_checklist=live_readiness_checklist,
            approvals_required=[live_readiness_checklist[-1]],
            deployment_blockers=[],
            handoff={
                "run_id": run_id,
                "gateway_config": {
                    "api_key": "***",
                    "params": {"secret_key": "***", "exchange": "sim"},
                },
            },
            pipeline={
                "current_stage": "live_handoff",
                "status": "ready_for_approval",
                "progress": 100,
                "ready_for_live": True,
                "live_handoff_status": "ready_for_approval",
                "live_handoff_ready_for_live": True,
                "live_handoff_approval_required": True,
                "live_handoff_blocker_count": 0,
                "live_readiness_checklist": live_readiness_checklist,
                "live_readiness_expires_at": "2026-01-08T00:02:00+00:00",
                "steps": [
                    {
                        "key": "live_handoff",
                        "label": "实盘交接",
                        "status": "running",
                        "handoff_status": "ready_for_approval",
                    }
                ],
            },
            next_actions=["提交人工实盘审批，审批通过后再切换实盘账户。"],
        )

    async def record_live_handoff_approval(
        self,
        user_id: str,
        run_id: str,
        request: AIStrategyLiveHandoffApprovalRequest,
        *,
        research_workspace_id: str | None = None,
    ):
        base = await self.build_live_handoff_package(
            user_id,
            run_id,
            research_workspace_id=research_workspace_id,
        )
        approved = request.decision == "approved"
        approval = AIStrategyLiveHandoffApprovalRecord(
            run_id=run_id,
            research_workspace_id=research_workspace_id or "research-api-ws",
            decision=request.decision,
            approved=approved,
            decided_at="2026-01-01T00:04:00+00:00",
            decided_by=request.approver or user_id,
            comment=request.comment,
            account_confirmed=request.account_confirmed,
            risk_limit_confirmed=request.risk_limit_confirmed,
            deployment_window=request.deployment_window,
            handoff_status_at_decision=base.status,
            blockers=[],
        )
        return base.model_copy(
            update={
                "status": "approved_for_live" if approved else "approval_rejected",
                "approval_status": request.decision,
                "approval": approval,
                "approvals_required": [],
                "pipeline": {
                    **dict(base.pipeline or {}),
                    "current_stage": "live_handoff",
                    "status": "approved_for_live" if approved else "approval_rejected",
                    "live_handoff_status": "approved_for_live"
                    if approved
                    else "approval_rejected",
                    "live_handoff_approval_status": request.decision,
                    "live_handoff_approved": approved,
                    "live_handoff_approved_at": approval.decided_at if approved else None,
                    "live_handoff_rejected_at": None if approved else approval.decided_at,
                    "steps": [
                        {
                            "key": "live_handoff",
                            "label": "实盘交接",
                            "status": "completed" if approved else "failed",
                            "handoff_status": "approved_for_live"
                            if approved
                            else "approval_rejected",
                            "approval_status": request.decision,
                        }
                    ],
                },
                "next_actions": [
                    "实盘交接包已通过人工审批，可在上线窗口内执行实盘切换前检查。"
                ]
                if approved
                else ["实盘交接包已被人工驳回，需处理审批意见后重新进入模拟复核或继续投研。"],
            }
        )


class FakeResearchAPIPaperService(FakeResearchAPIService):
    async def run(
        self,
        user_id: str,
        request: AIStrategyResearchRunRequest,
        *,
        progress_callback=None,
    ):
        result = await super().run(user_id, request, progress_callback=progress_callback)
        paper_workspace = _workspace("paper-api-ws", "trading")
        paper_unit = _unit("paper-api-unit", paper_workspace.id, result.best_strategy)
        asset_specs = {
            request.symbol: {
                "symbol": request.symbol,
                "source": "task_summary_exchange_specs",
                "multiplier": 300,
                "margin_rate": 0.1,
                "commission_rate": 0.000023,
            }
        }
        backtest_environment = {
            "initial_cash": request.initial_cash,
            "commission": 0.000023,
            "annual_days": request.annual_days,
            "calc_method": request.calc_method,
            "weight_mode": request.weight_mode,
            "multiplier": 300,
            "margin": 0.1,
            "asset_spec_source": "task_summary_exchange_specs",
        }
        monitoring_plan = [
            {
                "key": "rolling_sharpe",
                "label": "模拟交易滚动 Sharpe",
                "metric": "rolling_sharpe",
                "window": "30 trading days",
                "direction": "min",
                "threshold": 0.6,
                "action": "继续观察",
            }
        ]
        review_evaluations = [
            {
                "key": "rolling_sharpe",
                "label": "模拟交易滚动 Sharpe",
                "metric": "rolling_sharpe",
                "window": "30 trading days",
                "direction": "min",
                "threshold": 0.6,
                "actual": None,
                "source": None,
                "status": "pending",
                "passed": False,
                "action": "继续观察",
            }
        ]
        handoff = {
            "run_id": result.run_id,
            "research_workspace_id": result.research_workspace.id,
            "paper_workspace_id": paper_workspace.id,
            "paper_unit_id": paper_unit.id,
            "paper_task_id": "paper-api-task",
            "asset_specs": asset_specs,
            "backtest_environment": backtest_environment,
            "gateway_config": {
                "name": "paper_gateway",
                "api_key": "paper-secret-key",
                "params": {
                    "exchange": "sim",
                    "broker_id": "9999",
                    "secret_key": "paper-secret",
                    "passphrase": "paper-passphrase",
                },
            },
            "paper_monitoring_plan": monitoring_plan,
        }
        pipeline = {
            "current_stage": "paper_review",
            "status": "monitoring",
            "progress": 96,
            "ready_for_live": False,
            "paper_trading_error": None,
            "steps": [
                {"key": "draft", "label": "生成策略脚本", "status": "completed"},
                {"key": "backtest", "label": "自动回测", "status": "completed"},
                {"key": "paper_trading", "label": "模拟交易", "status": "completed"},
                {
                    "key": "paper_review",
                    "label": "模拟复核",
                    "status": "running",
                    "review_status": "monitoring",
                },
            ],
        }
        run_record = AIStrategyResearchRunRecord.model_validate(
            {
                **_run_record(
                    result.run_id,
                    workspace_id=result.research_workspace.id,
                    completed_at=result.completed_at,
                ),
                "paper_workspace_id": paper_workspace.id,
                "paper_workspace_name": paper_workspace.name,
                "paper_unit_id": paper_unit.id,
                "paper_trading_started": True,
                "paper_monitoring_plan": monitoring_plan,
                "paper_handoff": handoff,
                "asset_specs": asset_specs,
                "backtest_environment": backtest_environment,
                "paper_review_status": "monitoring",
                "paper_review_ready_for_live": False,
                "paper_reviewed_at": "2026-01-01T00:02:00+00:00",
                "paper_review_evaluations": review_evaluations,
                "paper_review_next_actions": ["继续收集模拟交易数据"],
                "pipeline": pipeline,
                "next_actions": ["继续跟踪模拟交易"],
            }
        )
        return result.model_copy(
            update={
                "paper_trading": AIStrategyPaperTradingStart(
                    workspace=paper_workspace,
                    unit=paper_unit,
                    run_result=StrategyCopilotRunResult(
                        unit_id=paper_unit.id,
                        task_id="paper-api-task",
                        status="running",
                    ),
                    started=True,
                    handoff=handoff,
                ),
                "paper_monitoring_plan": monitoring_plan,
                "pipeline": pipeline,
                "run_record": run_record,
                "next_actions": ["继续跟踪模拟交易"],
                "message": "Target Sharpe achieved and paper trading started",
            }
        )


class FakeResearchAPIExpiredLiveCandidateService(FakeResearchAPIPaperService):
    async def run(
        self,
        user_id: str,
        request: AIStrategyResearchRunRequest,
        *,
        progress_callback=None,
    ):
        result = await super().run(user_id, request, progress_callback=progress_callback)
        record = result.run_record
        assert record is not None
        live_readiness_checklist = [
            {
                "key": "human_approval_required",
                "label": "人工实盘审批",
                "status": "pending_manual_confirmation",
                "evidence": "模拟复核已达到实盘候选状态。",
                "action": "确认账户权限和上线窗口后再切换实盘。",
            }
        ]
        live_readiness_expires_at = "2000-01-08T00:00:00+00:00"
        paper_handoff = {
            **dict(record.paper_handoff or {}),
            "live_readiness_checklist": live_readiness_checklist,
            "live_readiness_expires_at": live_readiness_expires_at,
        }
        pipeline = {
            "current_stage": "live_candidate",
            "status": "achieved",
            "progress": 100,
            "ready_for_live": True,
            "live_readiness_checklist": live_readiness_checklist,
            "live_readiness_expires_at": live_readiness_expires_at,
            "steps": [],
        }
        record = record.model_copy(
            update={
                "paper_review_status": "ready_for_live_candidate",
                "paper_review_ready_for_live": True,
                "paper_reviewed_at": "2000-01-01T00:00:00+00:00",
                "paper_review_evaluations": [
                    {
                        "key": "rolling_sharpe",
                        "label": "模拟交易滚动 Sharpe",
                        "metric": "rolling_sharpe",
                        "window": "30 trading days",
                        "direction": "min",
                        "threshold": 0.6,
                        "actual": 0.8,
                        "source": "unit_status.metrics_snapshot",
                        "status": "passed",
                        "passed": True,
                        "action": "继续观察",
                    }
                ],
                "paper_review_next_actions": [
                    "模拟交易监控计划已全部通过，可作为实盘候选进入人工复核。"
                ],
                "live_readiness_checklist": live_readiness_checklist,
                "live_readiness_expires_at": live_readiness_expires_at,
                "paper_handoff": paper_handoff,
                "pipeline": pipeline,
                "next_actions": [
                    "模拟交易监控计划已全部通过，可作为实盘候选进入人工复核。"
                ],
            }
        )
        return result.model_copy(
            update={
                "run_record": record,
                "pipeline": pipeline,
                "next_actions": record.next_actions,
            }
        )


class FakeResearchAPILiveHandoffService(FakeResearchAPIPaperService):
    async def run(
        self,
        user_id: str,
        request: AIStrategyResearchRunRequest,
        *,
        progress_callback=None,
    ):
        result = await super().run(user_id, request, progress_callback=progress_callback)
        record = result.run_record
        assert record is not None
        live_readiness_checklist = [
            {
                "key": "human_approval_required",
                "label": "人工实盘审批",
                "status": "passed",
                "evidence": "模拟交易复核和人工审批均通过。",
                "action": "按审批窗口执行实盘切换前检查。",
            }
        ]
        approval = AIStrategyLiveHandoffApprovalRecord(
            run_id=result.run_id,
            research_workspace_id=result.research_workspace.id,
            decision="approved",
            approved=True,
            decided_at="2099-01-01T00:04:00+00:00",
            decided_by="risk-manager",
            comment="批准小资金实盘验证",
            account_confirmed=True,
            risk_limit_confirmed=True,
            deployment_window="2099-01-02 09:00-10:00",
            handoff_status_at_decision="ready_for_approval",
            blockers=[],
        )
        live_handoff = AIStrategyLiveHandoffPackage(
            run_id=result.run_id,
            research_workspace_id=result.research_workspace.id,
            generated_at="2099-01-01T00:03:00+00:00",
            ready_for_live=True,
            status="approved_for_live",
            approval_required=True,
            expires_at="2099-01-08T00:02:00+00:00",
            paper_workspace_id=record.paper_workspace_id,
            paper_unit_id=record.paper_unit_id,
            best_strategy_id=record.best_strategy_id,
            best_strategy_name=record.best_strategy_name,
            symbol=record.symbol,
            symbol_name=record.symbol_name,
            timeframe=record.timeframe,
            timeframe_n=record.timeframe_n,
            target_sharpe=record.target_sharpe,
            best_sharpe=record.best_sharpe,
            best_metrics=record.best_metrics,
            asset_specs=record.asset_specs,
            backtest_environment=record.backtest_environment,
            paper_review_status="ready_for_live_candidate",
            paper_reviewed_at="2099-01-01T00:02:00+00:00",
            paper_review_evaluations=[
                {
                    "key": "rolling_sharpe",
                    "label": "模拟交易滚动 Sharpe",
                    "metric": "rolling_sharpe",
                    "window": "30 trading days",
                    "direction": "min",
                    "threshold": 0.6,
                    "actual": 0.8,
                    "source": "unit_status.metrics_snapshot",
                    "status": "passed",
                    "passed": True,
                    "action": "继续观察",
                }
            ],
            paper_monitoring_plan=record.paper_monitoring_plan,
            live_readiness_checklist=live_readiness_checklist,
            approvals_required=[],
            deployment_blockers=[],
            approval_status="approved",
            approval=approval,
            handoff={
                "run_id": result.run_id,
                "gateway_config": {
                    "api_key": "live-secret-key",
                    "params": {
                        "secret_key": "live-secret",
                        "passphrase": "live-passphrase",
                        "exchange": "sim-live",
                    },
                },
            },
            pipeline={
                "current_stage": "live_handoff",
                "status": "approved_for_live",
                "progress": 100,
                "ready_for_live": True,
                "live_handoff_status": "approved_for_live",
                "live_handoff_generated_at": "2099-01-01T00:03:00+00:00",
                "live_handoff_ready_for_live": True,
                "live_handoff_approval_required": True,
                "live_handoff_blocker_count": 0,
                "live_handoff_approval_status": "approved",
                "live_handoff_approved": True,
                "live_handoff_approved_at": "2099-01-01T00:04:00+00:00",
                "steps": [],
            },
            next_actions=["实盘交接包已通过人工审批，可在上线窗口内执行实盘切换前检查。"],
        )
        pipeline = dict(live_handoff.pipeline)
        record = record.model_copy(
            update={
                "paper_review_status": "ready_for_live_candidate",
                "paper_review_ready_for_live": True,
                "paper_reviewed_at": "2099-01-01T00:02:00+00:00",
                "paper_review_evaluations": list(live_handoff.paper_review_evaluations),
                "paper_review_next_actions": [
                    "模拟交易监控计划已全部通过，可作为实盘候选进入人工复核。"
                ],
                "live_readiness_checklist": live_readiness_checklist,
                "live_readiness_expires_at": "2099-01-08T00:02:00+00:00",
                "live_handoff": live_handoff,
                "live_handoff_approval": approval,
                "pipeline": pipeline,
                "next_actions": live_handoff.next_actions,
            }
        )
        return result.model_copy(
            update={
                "run_record": record,
                "pipeline": pipeline,
                "next_actions": record.next_actions,
            }
        )


class FakeResearchAPILivePreparedService(FakeResearchAPILiveHandoffService):
    async def run(
        self,
        user_id: str,
        request: AIStrategyResearchRunRequest,
        *,
        progress_callback=None,
    ):
        result = await super().run(user_id, request, progress_callback=progress_callback)
        record = result.run_record
        assert record is not None
        assert result.best_strategy is not None
        live_workspace = _workspace("live-api-ws", "trading").model_copy(
            update={"name": "AI实盘准备"}
        )
        live_unit = _unit("live-api-unit", live_workspace.id, result.best_strategy).model_copy(
            update={
                "trading_mode": "live",
                "lock_trading": True,
                "lock_running": True,
            }
        )
        prepared_at = "2099-01-01T00:05:00+00:00"
        pipeline = {
            **dict(record.pipeline or {}),
            "current_stage": "live_trading_prepare",
            "live_trading_prepared": True,
            "live_trading_prepared_at": prepared_at,
            "live_workspace_id": live_workspace.id,
            "live_unit_id": live_unit.id,
            "live_unit_locked": True,
            "steps": [
                {
                    "key": "live_handoff",
                    "label": "实盘交接",
                    "status": "completed",
                    "handoff_status": "approved_for_live",
                },
                {
                    "key": "live_trading_prepare",
                    "label": "实盘准备",
                    "status": "completed",
                    "live_trading_prepared": True,
                    "live_workspace_id": live_workspace.id,
                    "live_unit_id": live_unit.id,
                    "live_unit_locked": True,
                    "prepared_at": prepared_at,
                },
            ],
        }
        record = record.model_copy(
            update={
                "live_workspace_id": live_workspace.id,
                "live_workspace_name": live_workspace.name,
                "live_unit_id": live_unit.id,
                "live_trading_prepared": True,
                "live_trading_prepared_at": prepared_at,
                "pipeline": pipeline,
                "next_actions": [
                    "已创建锁定的实盘交易单元，需人工核对网关凭据、账户权限和风控限额后再解锁运行。",
                    "实盘单元 live-api-unit 当前默认锁定交易/运行，不会自动下单。",
                ],
            }
        )
        return result.model_copy(
            update={
                "run_record": record,
                "pipeline": pipeline,
                "next_actions": record.next_actions,
            }
        )


class FakeResearchAPIPipelineOnlyLivePreparedService(FakeResearchAPILivePreparedService):
    async def run(
        self,
        user_id: str,
        request: AIStrategyResearchRunRequest,
        *,
        progress_callback=None,
    ):
        result = await super().run(user_id, request, progress_callback=progress_callback)
        record = result.run_record
        assert record is not None
        record = record.model_copy(
            update={
                "live_workspace_id": None,
                "live_workspace_name": None,
                "live_unit_id": None,
                "live_trading_prepared": False,
                "live_trading_prepared_at": None,
            }
        )
        return result.model_copy(update={"run_record": record})


class FakeResearchAPITimeoutCancelService(FakeResearchAPIService):
    async def run(
        self,
        user_id: str,
        request: AIStrategyResearchRunRequest,
        *,
        progress_callback=None,
    ):
        result = await super().run(user_id, request, progress_callback=progress_callback)
        iteration = result.iterations[0]
        unit_status = iteration.unit_status
        assert unit_status is not None
        timed_out_status = unit_status.model_copy(
            update={
                "run_status": "timeout",
                "last_task_id": "timeout-backtest-task",
                "trading_snapshot": {
                    "backtest_timeout_task_id": "timeout-backtest-task",
                    "backtest_timeout_cancel_requested": True,
                },
            }
        )
        timed_out_iteration = iteration.model_copy(
            update={
                "unit_status": timed_out_status,
                "passed": False,
                "failure_reason": "Backtest timed out",
                "quality_gate_failures": ["Backtest timed out"],
            }
        )
        return result.model_copy(
            update={
                "status": "timeout",
                "achieved": False,
                "iterations": [timed_out_iteration],
                "message": "Backtest timed out",
            }
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
                    "run_id": "slow-run",
                    "research_workspace_id": "slow-research-ws",
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


class CleanupOnCancelResearchAPIService:
    def __init__(self) -> None:
        self.cleanup_started = asyncio.Event()
        self.cleanup_done = asyncio.Event()

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
                    "run_id": "cleanup-run",
                    "research_workspace_id": "cleanup-research-ws",
                    "current_stage": "backtesting",
                    "progress": 25.0,
                    "current_iteration": 1,
                    "iteration_count": 0,
                    "max_iterations": request.max_iterations,
                    "current_backtest_task_id": "child-backtest-task",
                    "message": "cleanup fake backtest",
                }
            )
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            self.cleanup_started.set()
            await asyncio.sleep(0.01)
            self.cleanup_done.set()
            raise


class CancelResistantResearchAPIService:
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
                    "run_id": "race-run",
                    "research_workspace_id": "race-research-ws",
                    "current_stage": "backtesting",
                    "progress": 25.0,
                    "current_iteration": 1,
                    "iteration_count": 0,
                    "max_iterations": request.max_iterations,
                    "current_backtest_task_id": "child-backtest-task",
                    "message": "cancel-resistant fake backtest",
                }
            )
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            pass
        return await FakeResearchAPIService().run(user_id, request)


class FakeBacktestCancelService:
    def __init__(self) -> None:
        self.cancelled: list[tuple[str, str]] = []

    async def cancel_task(self, task_id: str, user_id: str) -> bool:
        self.cancelled.append((task_id, user_id))
        return True


@pytest.mark.asyncio
async def test_wait_for_unit_status_cancels_backtest_task_on_timeout():
    workspace_service = FakeWorkspaceService()
    cancel_service = FakeBacktestCancelService()
    service = AIStrategyResearchService(
        workspace_service=workspace_service,
        backtest_service=cancel_service,
    )
    initial_status = UnitStatusResponse(
        id="unit-timeout",
        run_status="running",
        last_task_id="backtest-task-1",
        metrics_snapshot={"sharpe_ratio": 0.2},
        run_count=0,
        trading_snapshot={"source": "poll"},
        trading_mode="paper",
    )

    status, reason = await service._wait_for_unit_status(
        "research-ws",
        "user-1",
        "unit-timeout",
        initial_status=initial_status,
        timeout_seconds=0,
        poll_interval_seconds=0,
    )

    assert reason == "Backtest timed out"
    assert status is not None
    assert status.run_status == "timeout"
    assert status.last_task_id == "backtest-task-1"
    assert cancel_service.cancelled == [("backtest-task-1", "user-1")]
    assert status.trading_snapshot["source"] == "poll"
    assert status.trading_snapshot["backtest_timeout_task_id"] == "backtest-task-1"
    assert status.trading_snapshot["backtest_timeout_cancel_requested"] is True


@pytest.mark.asyncio
async def test_ai_strategy_research_task_manager_runs_task_and_scopes_user():
    manager = AIStrategyResearchTaskManager()
    request = AIStrategyResearchRunRequest(
        prompt="生成趋势策略",
        symbol="000001.SZ",
        symbol_name="平安银行",
        timeframe="1h",
        start_date="2024-01-01",
        end_date="2024-06-30",
        knowledge_base_id="kb-quant",
        gateway_config={
            "name": "paper_gateway",
            "api_key": "secret-key",
            "params": {
                "password": "secret-password",
                "passphrase": "secret-passphrase",
                "auth_code": "secret-auth",
                "access_key": "secret-access",
                "exchange": "sim",
            },
        },
    )

    submitted = await manager.submit(
        "user-1",
        request,
        service=FakeResearchAPIService(),
    )

    assert submitted.status == "pending"
    assert submitted.request_snapshot["prompt"] == "生成趋势策略"
    assert submitted.request_snapshot["symbol"] == "000001.SZ"
    assert submitted.request_snapshot["symbol_name"] == "平安银行"
    assert submitted.request_snapshot["timeframe"] == "1h"
    assert submitted.request_snapshot["start_date"] == "2024-01-01"
    assert submitted.request_snapshot["knowledge_base_id"] == "kb-quant"
    assert submitted.request_snapshot["gateway_config"]["api_key"] == "***"
    assert submitted.request_snapshot["gateway_config"]["params"]["password"] == "***"
    assert submitted.request_snapshot["gateway_config"]["params"]["passphrase"] == "***"
    assert submitted.request_snapshot["gateway_config"]["params"]["auth_code"] == "***"
    assert submitted.request_snapshot["gateway_config"]["params"]["access_key"] == "***"
    assert submitted.request_snapshot["gateway_config"]["params"]["exchange"] == "sim"
    task = None
    for _ in range(20):
        task = await manager.get_task("user-1", submitted.task_id)
        if task is not None and task.status == "completed":
            break
        await asyncio.sleep(0.01)

    assert task is not None
    assert task.status == "completed"
    assert task.run_id == "api-run"
    assert task.research_workspace_id == "research-api-ws"
    assert task.progress == 100.0
    assert task.current_stage == "completed"
    assert task.request_snapshot["prompt"] == "生成趋势策略"
    assert task.request_snapshot["symbol"] == "000001.SZ"
    assert task.request_snapshot["gateway_config"]["api_key"] == "***"
    assert task.iteration_count == 1
    assert task.max_iterations == 3
    assert task.run_status == "achieved"
    assert task.achieved is True
    assert task.target_sharpe == pytest.approx(1.0)
    assert task.best_iteration == 1
    assert task.best_sharpe == pytest.approx(1.05)
    assert task.best_quality_score == pytest.approx(100.0)
    assert task.best_quality_gate_evaluations[0]["key"] == "sharpe"
    assert task.best_quality_gate_evaluations[0]["passed"] is True
    assert task.best_diagnostics["promotion_ready"] is True
    assert "进入模拟交易" in task.best_diagnostics["improvement_plan"][0]
    assert task.best_metrics["sharpe_ratio"] == pytest.approx(1.05)
    assert task.best_strategy_id == "strategy-api"
    assert task.latest_iteration is not None
    assert task.latest_iteration["iteration"] == 1
    assert task.result is not None
    assert task.result.achieved is True
    assert await manager.get_task("other-user", submitted.task_id) is None

    tasks = await manager.list_tasks("user-1")
    assert [item.task_id for item in tasks] == [submitted.task_id]
    assert await manager.list_tasks("user-1", active_only=True) == []


@pytest.mark.asyncio
async def test_ai_strategy_research_task_manager_exposes_timeout_cancelled_backtest():
    manager = AIStrategyResearchTaskManager()

    submitted = await manager.submit(
        "user-1",
        AIStrategyResearchRunRequest(prompt="生成趋势策略", symbol="000001.SZ"),
        service=FakeResearchAPITimeoutCancelService(),
    )

    task = None
    for _ in range(20):
        task = await manager.get_task("user-1", submitted.task_id)
        if task is not None and task.status == "completed":
            break
        await asyncio.sleep(0.01)

    assert task is not None
    assert task.status == "completed"
    assert task.run_status == "timeout"
    assert task.achieved is False
    assert task.cancelled_backtest_task_id == "timeout-backtest-task"
    assert task.child_cancelled is True
    assert task.latest_iteration is not None
    assert (
        task.latest_iteration["unit_status"]["trading_snapshot"]["backtest_timeout_task_id"]
        == "timeout-backtest-task"
    )


@pytest.mark.asyncio
async def test_ai_strategy_research_task_manager_exposes_runtime_context_while_running(
    monkeypatch,
):
    def fake_resolve_asset_specs(instance, strategy_dir, gateway=None, symbols=None):
        return {
            "IF2409.CFE": {
                "symbol": "IF2409.CFE",
                "source": "running_task_exchange_specs",
                "asset_type": "FUTURE",
                "multiplier": 300,
                "margin_rate": 0.1,
                "commission_rate": 0.000023,
            }
        }

    monkeypatch.setattr(
        "app.services.ai_strategy_research_service.resolve_asset_specs",
        fake_resolve_asset_specs,
    )
    manager = AIStrategyResearchTaskManager()

    submitted = await manager.submit(
        "user-1",
        AIStrategyResearchRunRequest(
            prompt="生成股指期货趋势策略",
            symbol="IF2409.CFE",
            target_sharpe=1.0,
            max_iterations=3,
        ),
        service=SlowResearchAPIService(),
    )
    assert submitted.asset_specs["IF2409.CFE"]["multiplier"] == 300
    assert submitted.backtest_environment["commission"] == pytest.approx(0.000023)
    assert submitted.backtest_environment["commission_source"] == "asset_specs_or_default"
    assert submitted.backtest_environment["asset_spec_source"] == "running_task_exchange_specs"

    task = None
    for _ in range(20):
        task = await manager.get_task("user-1", submitted.task_id)
        if task is not None and task.current_stage == "backtesting":
            break
        await asyncio.sleep(0.01)

    assert task is not None
    assert task.status == "running"
    assert task.current_stage == "backtesting"
    assert task.asset_specs["IF2409.CFE"]["asset_type"] == "FUTURE"
    assert task.asset_specs["IF2409.CFE"]["margin_rate"] == pytest.approx(0.1)
    assert task.backtest_environment["commission"] == pytest.approx(0.000023)
    assert task.backtest_environment["multiplier"] == 300
    assert task.backtest_environment["margin"] == pytest.approx(0.1)
    assert task.backtest_environment["asset_spec_source"] == "running_task_exchange_specs"

    await manager.cancel_task("user-1", submitted.task_id)


@pytest.mark.asyncio
async def test_ai_strategy_research_task_manager_exposes_paper_handoff_summary():
    manager = AIStrategyResearchTaskManager()

    submitted = await manager.submit(
        "user-1",
        AIStrategyResearchRunRequest(prompt="生成趋势策略", symbol="IF2409.CFE"),
        service=FakeResearchAPIPaperService(),
    )

    task = None
    for _ in range(20):
        task = await manager.get_task("user-1", submitted.task_id)
        if task is not None and task.status == "completed":
            break
        await asyncio.sleep(0.01)

    assert task is not None
    assert task.status == "completed"
    assert task.current_stage == "paper_review"
    assert task.run_status == "achieved"
    assert task.achieved is True
    assert task.target_sharpe == pytest.approx(1.0)
    assert task.best_iteration == 2
    assert task.best_sharpe == pytest.approx(1.21)
    assert task.best_strategy_id == "strategy-2"
    assert task.asset_specs["IF2409.CFE"]["multiplier"] == 300
    assert task.asset_specs["IF2409.CFE"]["source"] == "task_summary_exchange_specs"
    assert task.backtest_environment["commission"] == pytest.approx(0.000023)
    assert task.backtest_environment["multiplier"] == 300
    assert task.backtest_environment["asset_spec_source"] == "task_summary_exchange_specs"
    assert task.paper_trading_started is True
    assert task.paper_workspace_id == "paper-api-ws"
    assert task.paper_workspace_name == "paper-api-ws"
    assert task.paper_unit_id == "paper-api-unit"
    assert task.paper_handoff["paper_task_id"] == "paper-api-task"
    assert task.paper_handoff["gateway_config"]["api_key"] == "***"
    assert task.paper_handoff["gateway_config"]["params"]["secret_key"] == "***"
    assert task.paper_handoff["gateway_config"]["params"]["passphrase"] == "***"
    assert task.paper_handoff["gateway_config"]["params"]["exchange"] == "sim"
    assert task.paper_handoff["gateway_config"]["params"]["broker_id"] == "9999"
    assert task.paper_monitoring_plan[0]["key"] == "rolling_sharpe"
    assert task.paper_review_status == "monitoring"
    assert task.paper_review_ready_for_live is False
    assert task.paper_reviewed_at == "2026-01-01T00:02:00+00:00"
    assert task.paper_review_evaluations[0]["status"] == "pending"
    assert task.paper_review_next_actions == ["继续收集模拟交易数据"]
    assert task.pipeline["current_stage"] == "paper_review"
    assert task.next_actions == ["继续跟踪模拟交易"]
    assert task.result is not None
    assert task.result.paper_trading is not None
    assert task.result.paper_trading.handoff["gateway_config"]["api_key"] == "***"
    assert task.result.run_record is not None
    assert (
        task.result.run_record.paper_handoff["gateway_config"]["params"]["secret_key"]
        == "***"
    )


@pytest.mark.asyncio
async def test_ai_strategy_research_task_manager_exposes_live_handoff_summary():
    manager = AIStrategyResearchTaskManager()

    submitted = await manager.submit(
        "user-1",
        AIStrategyResearchRunRequest(prompt="生成趋势策略", symbol="IF2409.CFE"),
        service=FakeResearchAPILiveHandoffService(),
    )

    task = None
    for _ in range(20):
        task = await manager.get_task("user-1", submitted.task_id)
        if task is not None and task.status == "completed":
            break
        await asyncio.sleep(0.01)

    assert task is not None
    assert task.status == "completed"
    assert task.current_stage == "live_handoff"
    assert task.paper_review_status == "ready_for_live_candidate"
    assert task.paper_review_ready_for_live is True
    assert task.live_handoff is not None
    assert task.live_handoff.status == "approved_for_live"
    assert task.live_handoff.ready_for_live is True
    assert task.live_handoff.approval_status == "approved"
    assert task.live_handoff.approval is not None
    assert task.live_handoff.approval.approved is True
    assert task.live_handoff_approval is not None
    assert task.live_handoff_approval.approved is True
    assert task.live_handoff.handoff["gateway_config"]["api_key"] == "***"
    assert task.live_handoff.handoff["gateway_config"]["params"]["secret_key"] == "***"
    assert task.live_handoff.handoff["gateway_config"]["params"]["passphrase"] == "***"
    assert task.live_handoff.handoff["gateway_config"]["params"]["exchange"] == "sim-live"
    assert task.pipeline["current_stage"] == "live_handoff"
    assert task.pipeline["live_handoff_approved"] is True
    assert task.next_actions == ["实盘交接包已通过人工审批，可在上线窗口内执行实盘切换前检查。"]
    assert task.result is not None
    assert task.result.run_record is not None
    assert task.result.run_record.live_handoff is not None
    assert task.result.run_record.live_handoff.handoff["gateway_config"]["api_key"] == "***"

    listed = await manager.list_tasks("user-1", active_only=False)
    assert listed[0].live_handoff is not None
    assert listed[0].live_handoff.status == "approved_for_live"
    assert listed[0].live_handoff_approval is not None
    assert listed[0].live_handoff_approval.decision == "approved"


@pytest.mark.asyncio
async def test_ai_strategy_research_task_manager_exposes_live_prepared_summary():
    manager = AIStrategyResearchTaskManager()

    submitted = await manager.submit(
        "user-1",
        AIStrategyResearchRunRequest(prompt="生成趋势策略", symbol="IF2409.CFE"),
        service=FakeResearchAPILivePreparedService(),
    )

    task = None
    for _ in range(20):
        task = await manager.get_task("user-1", submitted.task_id)
        if task is not None and task.status == "completed":
            break
        await asyncio.sleep(0.01)

    assert task is not None
    assert task.status == "completed"
    assert task.current_stage == "live_trading_prepare"
    assert task.live_workspace_id == "live-api-ws"
    assert task.live_workspace_name == "AI实盘准备"
    assert task.live_unit_id == "live-api-unit"
    assert task.live_trading_prepared is True
    assert task.live_trading_prepared_at == "2099-01-01T00:05:00+00:00"
    assert task.pipeline["current_stage"] == "live_trading_prepare"
    assert task.pipeline["live_trading_prepared"] is True
    assert task.pipeline["live_unit_locked"] is True
    assert task.pipeline["steps"][-1]["key"] == "live_trading_prepare"
    assert task.pipeline["steps"][-1]["status"] == "completed"
    assert task.next_actions[0].startswith("已创建锁定的实盘交易单元")
    assert task.result is not None
    assert task.result.run_record is not None
    assert task.result.run_record.live_workspace_id == "live-api-ws"
    assert task.result.run_record.pipeline["steps"][-1]["key"] == "live_trading_prepare"

    listed = await manager.list_tasks("user-1", active_only=False)
    assert listed[0].live_trading_prepared is True
    assert listed[0].pipeline["current_stage"] == "live_trading_prepare"


@pytest.mark.asyncio
async def test_ai_strategy_research_task_manager_fills_live_summary_from_pipeline():
    manager = AIStrategyResearchTaskManager()

    submitted = await manager.submit(
        "user-1",
        AIStrategyResearchRunRequest(prompt="生成趋势策略", symbol="IF2409.CFE"),
        service=FakeResearchAPIPipelineOnlyLivePreparedService(),
    )

    task = None
    for _ in range(20):
        task = await manager.get_task("user-1", submitted.task_id)
        if task is not None and task.status == "completed":
            break
        await asyncio.sleep(0.01)

    assert task is not None
    assert task.status == "completed"
    assert task.current_stage == "live_trading_prepare"
    assert task.live_workspace_id == "live-api-ws"
    assert task.live_workspace_name is None
    assert task.live_unit_id == "live-api-unit"
    assert task.live_trading_prepared is True
    assert task.live_trading_prepared_at == "2099-01-01T00:05:00+00:00"
    assert task.result is not None
    assert task.result.run_record is not None
    assert task.result.run_record.live_workspace_id is None
    assert task.result.pipeline["live_workspace_id"] == "live-api-ws"

    listed = await manager.list_tasks("user-1", active_only=False)
    assert listed[0].live_workspace_id == "live-api-ws"
    assert listed[0].live_unit_id == "live-api-unit"
    assert listed[0].live_trading_prepared is True


@pytest.mark.asyncio
async def test_ai_strategy_research_task_manager_expires_stale_live_candidate_summary():
    manager = AIStrategyResearchTaskManager()

    submitted = await manager.submit(
        "user-1",
        AIStrategyResearchRunRequest(prompt="生成趋势策略", symbol="IF2409.CFE"),
        service=FakeResearchAPIExpiredLiveCandidateService(),
    )

    task = None
    for _ in range(20):
        task = await manager.get_task("user-1", submitted.task_id)
        if task is not None and task.status == "completed":
            break
        await asyncio.sleep(0.01)

    assert task is not None
    assert task.status == "completed"
    assert task.current_stage == "paper_review"
    assert task.paper_review_status == "live_readiness_expired"
    assert task.paper_review_ready_for_live is False
    assert task.live_readiness_expires_at == "2000-01-08T00:00:00+00:00"
    assert task.live_readiness_checklist[-1]["key"] == "live_candidate_expired"
    assert task.live_readiness_checklist[-1]["status"] == "expired"
    assert task.pipeline["current_stage"] == "paper_review"
    assert task.pipeline["ready_for_live"] is False
    assert task.next_actions[0].startswith("实盘候选复核已过期")
    assert task.result is not None
    assert task.result.pipeline["current_stage"] == "paper_review"
    assert task.result.run_record is not None
    assert task.result.run_record.paper_review_status == "live_readiness_expired"
    assert task.result.run_record.paper_review_ready_for_live is False

    listed = await manager.list_tasks("user-1", active_only=False)
    assert listed[0].task_id == submitted.task_id
    assert listed[0].paper_review_status == "live_readiness_expired"
    assert listed[0].pipeline["current_stage"] == "paper_review"


@pytest.mark.asyncio
async def test_ai_strategy_research_task_manager_prunes_old_terminal_tasks():
    manager = AIStrategyResearchTaskManager(max_terminal_tasks_per_user=2)

    submitted = []
    for _ in range(4):
        item = await manager.submit(
            "user-1",
            AIStrategyResearchRunRequest(prompt="生成趋势策略", symbol="000001.SZ"),
            service=FakeResearchAPIService(),
        )
        submitted.append(item)
        completed = None
        for _ in range(20):
            completed = await manager.get_task("user-1", item.task_id)
            if completed is not None and completed.status == "completed":
                break
            await asyncio.sleep(0.01)
        assert completed is not None
        assert completed.status == "completed"

    tasks = []
    for _ in range(20):
        tasks = await manager.list_tasks("user-1", limit=10)
        if len(tasks) == 2:
            break
        await asyncio.sleep(0.01)

    assert {item.task_id for item in tasks} == {
        submitted[-1].task_id,
        submitted[-2].task_id,
    }
    assert await manager.get_task("user-1", submitted[0].task_id) is None
    assert await manager.get_task("user-1", submitted[1].task_id) is None
    assert await manager.get_task("user-1", submitted[2].task_id) is not None
    assert await manager.get_task("user-1", submitted[3].task_id) is not None


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
    assert running.run_id == "slow-run"
    assert running.research_workspace_id == "slow-research-ws"
    assert running.progress == pytest.approx(25.0)
    assert running.current_backtest_task_id == "child-backtest-task"
    assert running.pipeline["current_stage"] == "backtesting"
    assert running.pipeline["progress"] == pytest.approx(25.0)
    assert running.pipeline["steps"][0]["key"] == "draft"
    assert running.pipeline["steps"][0]["status"] == "completed"
    assert running.pipeline["steps"][1]["key"] == "backtest_loop"
    assert running.pipeline["steps"][1]["status"] == "running"
    assert running.pipeline["steps"][1]["current_iteration"] == 1
    assert running.pipeline["steps"][1]["max_iterations"] == 3
    assert running.pipeline["steps"][2]["key"] == "quality_gate"
    assert running.pipeline["steps"][2]["status"] == "running"

    cancelled = await manager.cancel_task("user-1", submitted.task_id)
    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert cancelled.run_id == "slow-run"
    assert cancelled.research_workspace_id == "slow-research-ws"
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
async def test_ai_strategy_research_task_cancel_waits_for_runner_cleanup():
    backtest_service = FakeBacktestCancelService()
    research_service = CleanupOnCancelResearchAPIService()
    manager = AIStrategyResearchTaskManager(backtest_service_factory=lambda: backtest_service)
    submitted = await manager.submit(
        "user-1",
        AIStrategyResearchRunRequest(prompt="生成趋势策略", symbol="000001.SZ"),
        service=research_service,
    )

    running = None
    for _ in range(20):
        running = await manager.get_task("user-1", submitted.task_id)
        if running is not None and running.current_stage == "backtesting":
            break
        await asyncio.sleep(0.01)

    assert running is not None
    assert running.run_id == "cleanup-run"

    cancelled = await manager.cancel_task("user-1", submitted.task_id)

    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert cancelled.run_id == "cleanup-run"
    assert cancelled.research_workspace_id == "cleanup-research-ws"
    assert cancelled.cancelled_backtest_task_id == "child-backtest-task"
    assert research_service.cleanup_started.is_set()
    assert research_service.cleanup_done.is_set()
    assert backtest_service.cancelled == [("child-backtest-task", "user-1")]


@pytest.mark.asyncio
async def test_ai_strategy_research_task_manager_keeps_cancelled_terminal_state():
    backtest_service = FakeBacktestCancelService()
    manager = AIStrategyResearchTaskManager(backtest_service_factory=lambda: backtest_service)
    submitted = await manager.submit(
        "user-1",
        AIStrategyResearchRunRequest(prompt="生成趋势策略", symbol="000001.SZ"),
        service=CancelResistantResearchAPIService(),
    )

    running = None
    for _ in range(20):
        running = await manager.get_task("user-1", submitted.task_id)
        if running is not None and running.current_stage == "backtesting":
            break
        await asyncio.sleep(0.01)

    assert running is not None
    assert running.status == "running"
    assert running.run_id == "race-run"

    cancelled = await manager.cancel_task("user-1", submitted.task_id)
    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert cancelled.cancelled_backtest_task_id == "child-backtest-task"
    assert cancelled.child_cancelled is True

    background_task = manager._tasks[submitted.task_id].background_task
    assert background_task is not None
    for _ in range(20):
        if background_task.done():
            break
        await asyncio.sleep(0.01)
    assert background_task.done()

    final = None
    for _ in range(20):
        final = await manager.get_task("user-1", submitted.task_id)
        if final is not None and final.status == "completed":
            break
        await asyncio.sleep(0.01)

    assert final is not None
    assert final.status == "cancelled"
    assert final.run_id == "race-run"
    assert final.cancelled_backtest_task_id == "child-backtest-task"
    assert final.child_cancelled is True
    assert final.result is None


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
                "gateway_config": {
                    "name": "paper_gateway",
                    "params": {"exchange": "sim", "api_key": "secret-key"},
                },
            },
        )
        assert response.status_code == 202
        task_id = response.json()["task_id"]
        assert response.json()["request_snapshot"]["prompt"] == "生成一个均线策略并优化到夏普率 1.0"
        assert response.json()["request_snapshot"]["gateway_config"]["params"]["api_key"] == "***"
        list_response = await client.get(
            "/api/v1/strategy/ai-research/tasks",
            headers=auth_headers,
            params={"active_only": False, "limit": 5},
        )
        assert list_response.status_code == 200
        list_payload = list_response.json()
        assert list_payload["total"] == 1
        assert list_payload["items"][0]["task_id"] == task_id
        assert list_payload["items"][0]["request_snapshot"]["symbol"] == "000001.SZ"
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
    assert payload["research_workspace_id"] == "research-api-ws"
    assert payload["request_snapshot"]["gateway_config"]["params"]["api_key"] == "***"
    assert payload["progress"] == 100.0
    assert payload["current_stage"] == "completed"
    assert payload["iteration_count"] == 1
    assert payload["max_iterations"] == 2
    assert payload["latest_iteration"]["iteration"] == 1
    assert payload["best_quality_score"] == 100.0
    assert payload["best_quality_gate_evaluations"][0]["key"] == "sharpe"
    assert payload["best_quality_gate_evaluations"][0]["passed"] is True
    assert payload["best_diagnostics"]["promotion_ready"] is True
    assert payload["result"]["achieved"] is True
    assert payload["result"]["research_workspace"]["id"] == "research-api-ws"


@pytest.mark.asyncio
async def test_ai_strategy_research_task_api_returns_paper_pipeline_summary(
    client: AsyncClient,
    auth_headers: dict,
):
    task_manager = AIStrategyResearchTaskManager()
    app.dependency_overrides[get_ai_strategy_research_service] = lambda: FakeResearchAPIPaperService()
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
                "timeframe": "1h",
                "start_date": "2024-01-01",
            },
        )
        assert response.status_code == 202
        task_id = response.json()["task_id"]
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
    assert payload["request_snapshot"]["prompt"] == "生成一个均线策略并优化到夏普率 1.0"
    assert payload["request_snapshot"]["timeframe"] == "1h"
    assert payload["request_snapshot"]["start_date"] == "2024-01-01"
    assert payload["current_stage"] == "paper_review"
    assert payload["run_status"] == "achieved"
    assert payload["achieved"] is True
    assert payload["target_sharpe"] == 1.0
    assert payload["best_iteration"] == 2
    assert payload["best_sharpe"] == 1.21
    assert payload["best_strategy_id"] == "strategy-2"
    assert payload["paper_trading_started"] is True
    assert payload["paper_workspace_id"] == "paper-api-ws"
    assert payload["paper_workspace_name"] == "paper-api-ws"
    assert payload["paper_unit_id"] == "paper-api-unit"
    assert payload["paper_handoff"]["paper_task_id"] == "paper-api-task"
    assert payload["paper_handoff"]["gateway_config"]["api_key"] == "***"
    assert payload["paper_handoff"]["gateway_config"]["params"]["secret_key"] == "***"
    assert payload["paper_handoff"]["gateway_config"]["params"]["exchange"] == "sim"
    assert payload["paper_monitoring_plan"][0]["key"] == "rolling_sharpe"
    assert payload["paper_review_status"] == "monitoring"
    assert payload["paper_review_ready_for_live"] is False
    assert payload["paper_reviewed_at"] == "2026-01-01T00:02:00+00:00"
    assert payload["paper_review_evaluations"][0]["key"] == "rolling_sharpe"
    assert payload["paper_review_evaluations"][0]["status"] == "pending"
    assert payload["paper_review_next_actions"] == ["继续收集模拟交易数据"]
    assert payload["pipeline"]["current_stage"] == "paper_review"
    assert payload["next_actions"] == ["继续跟踪模拟交易"]
    assert payload["result"]["run_record"]["paper_handoff"]["paper_task_id"] == "paper-api-task"
    assert (
        payload["result"]["run_record"]["paper_handoff"]["gateway_config"]["params"][
            "passphrase"
        ]
        == "***"
    )
    assert payload["result"]["paper_trading"]["handoff"]["gateway_config"]["api_key"] == "***"


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
    assert payload["run_id"] == "slow-run"
    assert payload["research_workspace_id"] == "slow-research-ws"
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
    assert payload["live_readiness_checklist"][0]["key"] == "paper_monitoring_passed"
    assert payload["live_readiness_checklist"][-1]["status"] == "pending_manual_confirmation"
    assert payload["live_readiness_expires_at"] == "2026-01-08T00:02:00+00:00"


@pytest.mark.asyncio
async def test_ai_strategy_research_live_handoff_endpoint(
    client: AsyncClient,
    auth_headers: dict,
):
    app.dependency_overrides[get_ai_strategy_research_service] = lambda: FakeResearchAPIService()
    try:
        response = await client.get(
            "/api/v1/strategy/ai-research/runs/api-history-run/live-handoff",
            headers=auth_headers,
            params={"research_workspace_id": "research-api-ws"},
        )
    finally:
        app.dependency_overrides.pop(get_ai_strategy_research_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready_for_approval"
    assert payload["ready_for_live"] is True
    assert payload["approval_required"] is True
    assert payload["approvals_required"][0]["key"] == "human_approval_required"
    assert payload["deployment_blockers"] == []
    assert payload["asset_specs"]["000001.SZ"]["multiplier"] == 1
    assert payload["handoff"]["gateway_config"]["api_key"] == "***"
    assert payload["handoff"]["gateway_config"]["params"]["secret_key"] == "***"
    assert payload["handoff"]["gateway_config"]["params"]["exchange"] == "sim"
    assert payload["pipeline"]["current_stage"] == "live_handoff"
    assert payload["pipeline"]["steps"][-1]["key"] == "live_handoff"
    assert payload["pipeline"]["steps"][-1]["status"] == "running"


@pytest.mark.asyncio
async def test_ai_strategy_research_live_handoff_approval_endpoint(
    client: AsyncClient,
    auth_headers: dict,
):
    app.dependency_overrides[get_ai_strategy_research_service] = lambda: FakeResearchAPIService()
    try:
        response = await client.post(
            "/api/v1/strategy/ai-research/runs/api-history-run/live-handoff/approval",
            headers=auth_headers,
            params={"research_workspace_id": "research-api-ws"},
            json={
                "decision": "approved",
                "approver": "risk-manager",
                "comment": "账户权限和风险限额已核对",
                "account_confirmed": True,
                "risk_limit_confirmed": True,
                "deployment_window": "2026-01-03 09:30",
            },
        )
    finally:
        app.dependency_overrides.pop(get_ai_strategy_research_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "approved_for_live"
    assert payload["approval_status"] == "approved"
    assert payload["approval"]["approved"] is True
    assert payload["approval"]["decided_by"] == "risk-manager"
    assert payload["pipeline"]["current_stage"] == "live_handoff"
    assert payload["pipeline"]["steps"][-1]["key"] == "live_handoff"
    assert payload["pipeline"]["steps"][-1]["status"] == "completed"
    assert payload["approval"]["deployment_window"] == "2026-01-03 09:30"
    assert payload["handoff"]["gateway_config"]["api_key"] == "***"
