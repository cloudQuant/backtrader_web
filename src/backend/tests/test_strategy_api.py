"""Additional API integration tests for strategy endpoints."""

from copy import deepcopy

import pytest
from httpx import AsyncClient

from app.api.strategy.base import (
    get_ai_strategy_research_service,
    get_ai_strategy_research_tasks,
)
from app.schemas.ai_strategy_research import AIStrategyResearchTaskResponse
from tests.conftest import app, register_and_login

SAMPLE_CODE = "import backtrader as bt\nclass TestStrategy(bt.Strategy): pass"


def _strategy_payload(strategy_id: str = "ai-strategy-1") -> dict:
    return {
        "id": strategy_id,
        "user_id": "user-1",
        "name": "AI 趋势策略",
        "description": "AI generated strategy",
        "code": SAMPLE_CODE,
        "params": {},
        "category": "trend",
        "created_at": "2026-06-28T00:00:00Z",
        "updated_at": "2026-06-28T00:00:00Z",
    }


def _workspace_payload(workspace_id: str, name: str, workspace_type: str = "research") -> dict:
    return {
        "id": workspace_id,
        "user_id": "user-1",
        "name": name,
        "description": None,
        "workspace_type": workspace_type,
        "settings": {},
        "trading_config": {},
        "unit_count": 1,
        "completed_count": 1,
        "status": "idle",
        "created_at": "2026-06-28T00:00:00Z",
        "updated_at": "2026-06-28T00:00:00Z",
    }


def _unit_payload(unit_id: str, workspace_id: str, *, trading_mode: str = "paper") -> dict:
    return {
        "id": unit_id,
        "workspace_id": workspace_id,
        "group_name": "AI 投研分组",
        "strategy_id": "ai-strategy-1",
        "strategy_name": "AI 趋势策略",
        "symbol": "IF2409.CFE",
        "symbol_name": "沪深300股指期货",
        "timeframe": "1h",
        "timeframe_n": 1,
        "category": "trend",
        "sort_order": 0,
        "data_config": {
            "ai_research_run_id": "run-1",
            "asset_specs": {
                "IF2409.CFE": {
                    "multiplier": 300,
                    "margin_rate": 0.1,
                    "commission_rate": 0.000023,
                    "source": "exchange",
                }
            },
        },
        "unit_settings": {
            "commission": 0.000023,
            "asset_spec_source": "exchange",
        },
        "params": {},
        "optimization_config": {},
        "trading_mode": trading_mode,
        "gateway_config": {"api_key": "unit-secret", "params": {"secret_key": "unit-secret"}},
        "lock_trading": trading_mode == "live",
        "lock_running": trading_mode == "live",
        "trading_instance_id": None,
        "trading_snapshot": {},
        "run_status": "completed",
        "run_count": 1,
        "last_run_time": None,
        "last_task_id": "paper-task-1",
        "last_optimization_task_id": None,
        "bar_count": 100,
        "metrics_snapshot": {"sharpe_ratio": 1.18},
        "opt_status": None,
        "opt_total": None,
        "opt_completed": None,
        "opt_progress": None,
        "opt_elapsed_time": None,
        "opt_remaining_time": None,
        "created_at": "2026-06-28T00:00:00Z",
        "updated_at": "2026-06-28T00:00:00Z",
    }


def _run_record_payload() -> dict:
    return {
        "run_id": "run-1",
        "prompt": "生成一个趋势策略",
        "symbol": "IF2409.CFE",
        "symbol_name": "沪深300股指期货",
        "timeframe": "1h",
        "timeframe_n": 1,
        "initial_cash": 200000,
        "commission": 0.000023,
        "annual_days": 244,
        "calc_method": "log",
        "weight_mode": "value",
        "group_name": "AI 投研分组",
        "asset_specs": {
            "IF2409.CFE": {
                "multiplier": 300,
                "margin_rate": 0.1,
                "commission_rate": 0.000023,
                "source": "exchange",
            }
        },
        "backtest_environment": {
            "commission": 0.000023,
            "multiplier": 300,
            "margin": 0.1,
            "asset_spec_source": "exchange",
        },
        "status": "achieved",
        "achieved": True,
        "target_sharpe": 1.0,
        "quality_gates": {"target_sharpe": 1.0, "min_total_trades": 4},
        "min_total_trades": 4,
        "max_iterations": 3,
        "iteration_count": 2,
        "best_iteration": 2,
        "best_sharpe": 1.18,
        "best_quality_score": 100,
        "best_quality_gate_evaluations": [
            {
                "key": "sharpe",
                "label": "Sharpe",
                "actual": 1.18,
                "target": 1.0,
                "direction": "min",
                "passed": True,
                "score": 1,
            }
        ],
        "best_diagnostics": {"promotion_ready": True},
        "best_metrics": {"sharpe_ratio": 1.18, "total_trades": 9},
        "best_strategy_id": "ai-strategy-1",
        "best_strategy_name": "AI 趋势策略",
        "research_workspace_id": "research-ws",
        "paper_workspace_id": "paper-ws",
        "paper_workspace_name": "AI 模拟交易",
        "paper_unit_id": "paper-unit",
        "paper_trading_started": True,
        "paper_monitoring_plan": [
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
        "paper_handoff": {
            "gateway_config": {
                "api_key": "***",
                "params": {"secret_key": "***", "exchange": "sim"},
            }
        },
        "paper_review_status": "ready_for_live_candidate",
        "paper_review_ready_for_live": True,
        "paper_reviewed_at": "2026-06-28T00:10:00Z",
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
        "paper_review_next_actions": ["模拟交易监控已通过。"],
        "live_readiness_checklist": [
            {
                "key": "paper_monitoring_passed",
                "label": "模拟监控通过",
                "status": "passed",
                "evidence": "rolling Sharpe 0.82",
                "action": "继续监控。",
            }
        ],
        "pipeline": {
            "current_stage": "live_candidate",
            "status": "achieved",
            "progress": 100,
            "ready_for_live": True,
            "steps": [],
        },
        "next_actions": ["进入实盘交接审批。"],
        "started_at": "2026-06-28T00:00:00Z",
        "completed_at": "2026-06-28T00:20:00Z",
        "iterations": [],
    }


def _paper_start_payload() -> dict:
    return {
        "workspace": _workspace_payload("paper-ws", "AI 模拟交易", "trading"),
        "unit": _unit_payload("paper-unit", "paper-ws"),
        "run_result": {"unit_id": "paper-unit", "task_id": "paper-task-1", "status": "running"},
        "started": True,
        "handoff": {
            "gateway_config": {
                "api_key": "real-paper-key",
                "params": {"secret_key": "real-paper-secret", "exchange": "sim"},
            },
            "backtest_environment": {"commission": 0.000023, "multiplier": 300},
        },
        "run_record": _run_record_payload(),
    }


def _live_handoff_payload(status: str = "ready_for_approval") -> dict:
    return {
        "run_id": "run-1",
        "research_workspace_id": "research-ws",
        "generated_at": "2026-06-28T00:30:00Z",
        "ready_for_live": True,
        "status": status,
        "approval_required": True,
        "paper_workspace_id": "paper-ws",
        "paper_unit_id": "paper-unit",
        "best_strategy_id": "ai-strategy-1",
        "best_strategy_name": "AI 趋势策略",
        "symbol": "IF2409.CFE",
        "symbol_name": "沪深300股指期货",
        "timeframe": "1h",
        "timeframe_n": 1,
        "target_sharpe": 1.0,
        "best_sharpe": 1.18,
        "best_metrics": {"sharpe_ratio": 1.18},
        "asset_specs": _run_record_payload()["asset_specs"],
        "backtest_environment": _run_record_payload()["backtest_environment"],
        "paper_review_status": "ready_for_live_candidate",
        "paper_reviewed_at": "2026-06-28T00:10:00Z",
        "paper_review_evaluations": _run_record_payload()["paper_review_evaluations"],
        "paper_monitoring_plan": _run_record_payload()["paper_monitoring_plan"],
        "live_readiness_checklist": _run_record_payload()["live_readiness_checklist"],
        "approvals_required": [],
        "deployment_blockers": [],
        "approval_status": "approved" if status == "approved_for_live" else None,
        "handoff": {
            "gateway_config": {
                "api_key": "live-key",
                "params": {"secret_key": "live-secret", "broker_id": "9999"},
            }
        },
        "pipeline": {"current_stage": "live_handoff", "status": status, "progress": 90},
        "next_actions": ["等待人工审批。"],
    }


def _review_payload() -> dict:
    return {
        "run_id": "run-1",
        "research_workspace_id": "research-ws",
        "paper_workspace_id": "paper-ws",
        "paper_unit_id": "paper-unit",
        "paper_trading_started": True,
        "workspace": _workspace_payload("paper-ws", "AI 模拟交易", "trading"),
        "unit": _unit_payload("paper-unit", "paper-ws"),
        "monitoring_plan": _run_record_payload()["paper_monitoring_plan"],
        "evaluations": _run_record_payload()["paper_review_evaluations"],
        "ready_for_live": True,
        "status": "ready_for_live_candidate",
        "reviewed_at": "2026-06-28T00:10:00Z",
        "live_readiness_checklist": _run_record_payload()["live_readiness_checklist"],
        "pipeline": {"current_stage": "live_candidate", "ready_for_live": True},
        "next_actions": ["进入实盘交接审批。"],
        "live_handoff": _live_handoff_payload(),
    }


def _prepare_payload() -> dict:
    return {
        "workspace": _workspace_payload("live-ws", "AI 实盘交易", "trading"),
        "unit": _unit_payload("live-unit", "live-ws", trading_mode="live"),
        "prepared": True,
        "handoff": _live_handoff_payload("approved_for_live"),
        "next_actions": ["已创建锁定实盘单元。"],
    }


def _run_response_payload() -> dict:
    return {
        "run_id": "run-1",
        "status": "achieved",
        "achieved": True,
        "target_sharpe": 1.0,
        "started_at": "2026-06-28T00:00:00Z",
        "completed_at": "2026-06-28T00:20:00Z",
        "best_iteration": 2,
        "best_quality_score": 100,
        "best_quality_gate_evaluations": _run_record_payload()[
            "best_quality_gate_evaluations"
        ],
        "best_diagnostics": {"promotion_ready": True},
        "best_metrics": {"sharpe_ratio": 1.18, "total_trades": 9},
        "research_workspace": _workspace_payload("research-ws", "AI 投研工作区"),
        "iterations": [],
        "best_strategy": _strategy_payload(),
        "paper_trading": _paper_start_payload(),
        "paper_monitoring_plan": _run_record_payload()["paper_monitoring_plan"],
        "pipeline": {"current_stage": "paper_review", "status": "achieved", "progress": 100},
        "promotion_audit": [{"key": "quality_gate", "status": "completed"}],
        "run_record": _run_record_payload(),
        "next_actions": ["进入模拟交易监控。"],
        "message": "AI research target achieved",
    }


class _FakeAIResearchService:
    def __init__(self):
        self.calls: list[tuple[str, str, object]] = []

    async def run(self, user_id, data):
        self.calls.append(("run", user_id, data))
        return deepcopy(_run_response_payload())

    async def list_run_records(self, user_id, *, research_workspace_id=None, limit=20):
        self.calls.append(("list_run_records", user_id, research_workspace_id))
        return {"total": 1, "items": [deepcopy(_run_record_payload())]}

    async def get_run_record(self, user_id, run_id, *, research_workspace_id=None):
        self.calls.append(("get_run_record", user_id, run_id))
        return deepcopy(_run_record_payload()) if run_id == "run-1" else None

    async def start_paper_trading_from_run(self, user_id, run_id, data):
        self.calls.append(("start_paper_trading_from_run", user_id, data))
        return deepcopy(_paper_start_payload())

    async def review_paper_trading_run(self, user_id, run_id, *, research_workspace_id=None):
        self.calls.append(("review_paper_trading_run", user_id, research_workspace_id))
        return deepcopy(_review_payload())

    async def build_live_handoff_package(self, user_id, run_id, *, research_workspace_id=None):
        self.calls.append(("build_live_handoff_package", user_id, research_workspace_id))
        return deepcopy(_live_handoff_payload())

    async def record_live_handoff_approval(self, user_id, run_id, data, *, research_workspace_id=None):
        self.calls.append(("record_live_handoff_approval", user_id, data))
        payload = _live_handoff_payload("approved_for_live")
        payload["approval"] = {
            "run_id": "run-1",
            "research_workspace_id": "research-ws",
            "decision": data.decision,
            "approved": data.decision == "approved",
            "decided_at": "2026-06-28T00:40:00Z",
            "decided_by": data.approver or "tester",
            "comment": data.comment,
            "account_confirmed": data.account_confirmed,
            "risk_limit_confirmed": data.risk_limit_confirmed,
            "deployment_window": data.deployment_window,
            "handoff_status_at_decision": "ready_for_approval",
            "blockers": [],
        }
        return payload

    async def prepare_live_trading_from_run(self, user_id, run_id, data):
        self.calls.append(("prepare_live_trading_from_run", user_id, data))
        return deepcopy(_prepare_payload())


class _FakeAIResearchTaskManager:
    def __init__(self):
        self.task = AIStrategyResearchTaskResponse(
            task_id="task-1",
            status="running",
            submitted_at="2026-06-28T00:00:00Z",
            research_workspace_id="research-ws",
            request_snapshot={},
            current_stage="backtesting",
            progress=35,
            max_iterations=3,
            message="running",
        )

    async def submit(self, user_id, request, *, service=None):
        self.task = self.task.model_copy(
            update={
                "request_snapshot": request.model_dump(mode="python"),
                "target_sharpe": request.target_sharpe,
            }
        )
        return self.task

    async def list_tasks(self, user_id, *, active_only=False, limit=20):
        return [self.task]

    async def get_task(self, user_id, task_id):
        return self.task if task_id == self.task.task_id else None

    async def cancel_task(self, user_id, task_id):
        if task_id != self.task.task_id:
            return None
        self.task = self.task.model_copy(
            update={
                "status": "cancelled",
                "completed_at": "2026-06-28T00:01:00Z",
                "current_stage": "cancelled",
                "message": "cancelled",
            }
        )
        return self.task


class TestStrategyAPI:
    """Test strategy API endpoints."""

    @pytest.mark.asyncio
    async def test_create_strategy(self, client: AsyncClient, auth_headers: dict):
        """Test creating a strategy."""
        response = await client.post(
            "/api/v1/strategy/",
            json={
                "name": "Test Strategy",
                "description": "A test strategy",
                "code": SAMPLE_CODE,
                "params": {"param1": {"type": "int", "default": 10}},
                "category": "custom",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Strategy"
        assert data["description"] == "A test strategy"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_list_strategies(self, client: AsyncClient, auth_headers: dict):
        """Test listing strategies."""
        # Create a strategy first
        await client.post(
            "/api/v1/strategy/",
            json={
                "name": "List Test Strategy",
                "description": "Test",
                "code": SAMPLE_CODE,
                "category": "custom",
            },
            headers=auth_headers,
        )

        # List strategies
        response = await client.get("/api/v1/strategy/", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_get_strategy(self, client: AsyncClient, auth_headers: dict):
        """Test getting a specific strategy."""
        # Create a strategy
        create_response = await client.post(
            "/api/v1/strategy/",
            json={
                "name": "Get Test Strategy",
                "description": "Test",
                "code": SAMPLE_CODE,
                "category": "custom",
            },
            headers=auth_headers,
        )

        strategy_id = create_response.json()["id"]

        # Get the strategy
        response = await client.get(f"/api/v1/strategy/{strategy_id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == strategy_id
        assert data["name"] == "Get Test Strategy"

    @pytest.mark.asyncio
    async def test_get_strategy_blocks_cross_user_access(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test that users cannot read strategies owned by another user."""
        create_response = await client.post(
            "/api/v1/strategy/",
            json={
                "name": "Private Strategy",
                "description": "Owner only",
                "code": SAMPLE_CODE,
                "category": "custom",
            },
            headers=auth_headers,
        )
        strategy_id = create_response.json()["id"]

        _, other_headers = await register_and_login(client, username="other_reader")
        response = await client.get(f"/api/v1/strategy/{strategy_id}", headers=other_headers)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_strategy(self, client: AsyncClient, auth_headers: dict):
        """Test updating a strategy."""
        # Create a strategy
        create_response = await client.post(
            "/api/v1/strategy/",
            json={
                "name": "Update Test Strategy",
                "description": "Original",
                "code": SAMPLE_CODE,
                "category": "custom",
            },
            headers=auth_headers,
        )

        strategy_id = create_response.json()["id"]

        # Update the strategy
        response = await client.put(
            f"/api/v1/strategy/{strategy_id}",
            json={
                "name": "Updated Strategy",
                "description": "Updated description",
                "code": SAMPLE_CODE,
                "category": "trend",
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Strategy"
        assert data["description"] == "Updated description"

    @pytest.mark.asyncio
    async def test_delete_strategy(self, client: AsyncClient, auth_headers: dict):
        """Test deleting a strategy."""
        # Create a strategy
        create_response = await client.post(
            "/api/v1/strategy/",
            json={
                "name": "Delete Test Strategy",
                "description": "Test",
                "code": SAMPLE_CODE,
                "category": "custom",
            },
            headers=auth_headers,
        )

        strategy_id = create_response.json()["id"]

        # Delete the strategy
        response = await client.delete(f"/api/v1/strategy/{strategy_id}", headers=auth_headers)

        assert response.status_code == 200

        # Verify it's deleted
        get_response = await client.get(f"/api/v1/strategy/{strategy_id}", headers=auth_headers)

        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_generate_strategy_copilot_draft(self, client: AsyncClient, auth_headers: dict):
        """Test generating a strategy draft from the dedicated copilot API."""
        response = await client.post(
            "/api/v1/strategy/copilot/draft",
            json={
                "prompt": "请生成一个双均线趋势跟踪策略，使用日线并带 ATR 止损",
                "thinking_mode": False,
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["answer"]
        assert data["strategy_draft"]["name"].startswith("AI策略 - ")
        assert "class" in data["strategy_draft"]["code"]
        assert data["strategy_draft"]["params"]
        assert data["strategy_draft"]["assumptions"]
        assert data["strategy_draft"]["risk_points"]
        assert data["strategy_draft"]["data_source"]["type"] == "csv"
        assert data["strategy_draft"]["data_source"]["timeframe"]
        assert data["strategy_draft"]["backtest_defaults"]["initial_cash"] == 100000.0
        assert data["strategy_draft"]["execution_plan"]["workspace_type"] == "research"

    @pytest.mark.asyncio
    async def test_add_strategy_copilot_draft_to_workspace(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test persisting a copilot draft and adding it to a research workspace."""
        workspace_response = await client.post(
            "/api/v1/workspace/",
            json={"name": "AI研究工作区", "workspace_type": "research"},
            headers=auth_headers,
        )
        assert workspace_response.status_code == 201
        workspace_id = workspace_response.json()["id"]

        draft_response = await client.post(
            "/api/v1/strategy/copilot/draft",
            json={"prompt": "请生成一个 RSI 超卖反弹策略"},
            headers=auth_headers,
        )
        assert draft_response.status_code == 200
        strategy_draft = draft_response.json()["strategy_draft"]

        response = await client.post(
            f"/api/v1/strategy/copilot/workspaces/{workspace_id}/units",
            json={
                "strategy_draft": strategy_draft,
                "symbol": "600519.SH",
                "symbol_name": "贵州茅台",
                "timeframe": "1d",
                "group_name": "AI草稿单元",
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["workspace_id"] == workspace_id
        assert data["created_strategy"] is True
        assert data["strategy"]["name"] == strategy_draft["name"]
        assert data["unit"]["workspace_id"] == workspace_id
        assert data["unit"]["symbol"] == "600519.SH"
        assert data["unit"]["strategy_id"] == data["strategy"]["id"]

    @pytest.mark.asyncio
    async def test_backtest_strategy_copilot_draft_from_workspace(
        self, client: AsyncClient, auth_headers: dict, monkeypatch
    ):
        """Test dedicated copilot orchestration endpoint for add + backtest."""
        seen: dict[str, str | None] = {"unit_id": None}

        async def fake_run_units(self, workspace_id, user_id, unit_ids, parallel=False):
            seen["unit_id"] = unit_ids[0]
            return [{"unit_id": unit_ids[0], "task_id": "task-1", "status": "running"}]

        async def fake_get_units_status(self, workspace_id, user_id):
            return (
                [
                    {
                        "id": seen["unit_id"],
                        "run_status": "running",
                        "last_task_id": "task-1",
                        "metrics_snapshot": {},
                        "run_count": 0,
                        "last_run_time": None,
                        "bar_count": None,
                        "trading_instance_id": None,
                        "trading_snapshot": {},
                        "trading_mode": "paper",
                        "lock_trading": False,
                        "lock_running": False,
                        "opt_status": None,
                        "opt_total": None,
                        "opt_completed": None,
                        "opt_progress": None,
                        "opt_elapsed_time": None,
                        "opt_remaining_time": None,
                    }
                ]
                if seen["unit_id"]
                else []
            )

        monkeypatch.setattr(
            "app.services.workspace_service.WorkspaceService.run_units",
            fake_run_units,
        )
        monkeypatch.setattr(
            "app.services.workspace_service.WorkspaceService.get_units_status",
            fake_get_units_status,
        )

        workspace_response = await client.post(
            "/api/v1/workspace/",
            json={"name": "AI闭环工作区", "workspace_type": "research"},
            headers=auth_headers,
        )
        assert workspace_response.status_code == 201
        workspace_id = workspace_response.json()["id"]

        draft_response = await client.post(
            "/api/v1/strategy/copilot/draft",
            json={"prompt": "请生成一个双均线策略"},
            headers=auth_headers,
        )
        assert draft_response.status_code == 200
        strategy_draft = draft_response.json()["strategy_draft"]

        response = await client.post(
            f"/api/v1/strategy/copilot/workspaces/{workspace_id}/backtest",
            json={
                "strategy_draft": strategy_draft,
                "symbol": "000001.SZ",
                "symbol_name": "平安银行",
                "timeframe": "1d",
                "group_name": "AI闭环单元",
                "parallel": False,
                "report_config": {
                    "calc_method": "simple",
                    "annual_days": 252,
                    "weight_mode": "equal",
                },
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["workspace_id"] == workspace_id
        assert data["created_strategy"] is True
        assert data["unit"]["symbol"] == "000001.SZ"
        assert data["run_result"]["task_id"] == "task-1"
        assert data["run_result"]["status"] == "running"
        assert data["unit_status"]["run_status"] == "running"
        assert data["report_ready"] is False
        assert data["report"] is None

    @pytest.mark.asyncio
    async def test_ai_research_run_api_returns_full_loop_result_and_redacts_gateway_secrets(
        self, client: AsyncClient, auth_headers: dict
    ):
        """The HTTP route should expose the generate/backtest/improve/paper result safely."""
        service = _FakeAIResearchService()
        app.dependency_overrides[get_ai_strategy_research_service] = lambda: service
        try:
            response = await client.post(
                "/api/v1/strategy/ai-research/run",
                json={
                    "prompt": "生成一个趋势策略，目标夏普率达到 1.0",
                    "symbol": "IF2409.CFE",
                    "symbol_name": "沪深300股指期货",
                    "timeframe": "1h",
                    "target_sharpe": 1.0,
                    "min_total_trades": 4,
                    "max_iterations": 3,
                    "initial_cash": 200000,
                    "commission": 0.000023,
                    "start_paper_trading": True,
                    "gateway_config": {
                        "api_key": "paper-key",
                        "params": {"secret_key": "paper-secret", "exchange": "sim"},
                    },
                },
                headers=auth_headers,
            )
        finally:
            app.dependency_overrides.pop(get_ai_strategy_research_service, None)

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "achieved"
        assert data["achieved"] is True
        assert data["best_metrics"]["sharpe_ratio"] == pytest.approx(1.18)
        assert data["paper_trading"]["started"] is True
        assert data["paper_trading"]["handoff"]["gateway_config"]["api_key"] == "***"
        assert data["paper_trading"]["handoff"]["gateway_config"]["params"]["secret_key"] == "***"
        assert data["run_record"]["paper_handoff"]["gateway_config"]["api_key"] == "***"
        assert data["run_record"]["backtest_environment"]["multiplier"] == 300
        assert service.calls[0][0] == "run"
        assert service.calls[0][2].target_sharpe == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_ai_research_task_api_lifecycle(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Async task routes should submit, list, fetch and cancel a research loop task."""
        service = _FakeAIResearchService()
        task_manager = _FakeAIResearchTaskManager()
        app.dependency_overrides[get_ai_strategy_research_service] = lambda: service
        app.dependency_overrides[get_ai_strategy_research_tasks] = lambda: task_manager
        try:
            submit_response = await client.post(
                "/api/v1/strategy/ai-research/tasks",
                json={
                    "prompt": "自动生成并改进策略",
                    "symbol": "000001.SZ",
                    "target_sharpe": 1.0,
                    "max_iterations": 3,
                },
                headers=auth_headers,
            )
            list_response = await client.get(
                "/api/v1/strategy/ai-research/tasks?active_only=true&limit=5",
                headers=auth_headers,
            )
            get_response = await client.get(
                "/api/v1/strategy/ai-research/tasks/task-1",
                headers=auth_headers,
            )
            cancel_response = await client.post(
                "/api/v1/strategy/ai-research/tasks/task-1/cancel",
                headers=auth_headers,
            )
            missing_response = await client.get(
                "/api/v1/strategy/ai-research/tasks/missing",
                headers=auth_headers,
            )
        finally:
            app.dependency_overrides.pop(get_ai_strategy_research_service, None)
            app.dependency_overrides.pop(get_ai_strategy_research_tasks, None)

        assert submit_response.status_code == 202, submit_response.text
        submitted = submit_response.json()
        assert submitted["task_id"] == "task-1"
        assert submitted["request_snapshot"]["prompt"] == "自动生成并改进策略"
        assert submitted["request_snapshot"]["target_sharpe"] == pytest.approx(1.0)

        assert list_response.status_code == 200, list_response.text
        assert list_response.json()["total"] == 1
        assert get_response.status_code == 200, get_response.text
        assert get_response.json()["current_stage"] == "backtesting"
        assert cancel_response.status_code == 200, cancel_response.text
        assert cancel_response.json()["status"] == "cancelled"
        assert missing_response.status_code == 404

    @pytest.mark.asyncio
    async def test_ai_research_history_paper_and_live_api_wiring(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Persisted run, paper review, live handoff and live preparation routes stay wired."""
        service = _FakeAIResearchService()
        app.dependency_overrides[get_ai_strategy_research_service] = lambda: service
        try:
            list_response = await client.get(
                "/api/v1/strategy/ai-research/runs?research_workspace_id=research-ws&limit=5",
                headers=auth_headers,
            )
            detail_response = await client.get(
                "/api/v1/strategy/ai-research/runs/run-1?research_workspace_id=research-ws",
                headers=auth_headers,
            )
            missing_response = await client.get(
                "/api/v1/strategy/ai-research/runs/missing?research_workspace_id=research-ws",
                headers=auth_headers,
            )
            paper_response = await client.post(
                "/api/v1/strategy/ai-research/runs/run-1/paper-trading",
                json={
                    "research_workspace_id": "research-ws",
                    "paper_workspace_name": "AI 模拟交易",
                    "gateway_config": {
                        "api_key": "paper-key",
                        "params": {"secret_key": "paper-secret", "exchange": "sim"},
                    },
                },
                headers=auth_headers,
            )
            review_response = await client.get(
                "/api/v1/strategy/ai-research/runs/run-1/paper-trading/review"
                "?research_workspace_id=research-ws",
                headers=auth_headers,
            )
            handoff_response = await client.get(
                "/api/v1/strategy/ai-research/runs/run-1/live-handoff"
                "?research_workspace_id=research-ws",
                headers=auth_headers,
            )
            approval_response = await client.post(
                "/api/v1/strategy/ai-research/runs/run-1/live-handoff/approval"
                "?research_workspace_id=research-ws",
                json={
                    "decision": "approved",
                    "approver": "risk-manager",
                    "comment": "通过",
                    "account_confirmed": True,
                    "risk_limit_confirmed": True,
                    "deployment_window": "next session",
                },
                headers=auth_headers,
            )
            prepare_response = await client.post(
                "/api/v1/strategy/ai-research/runs/run-1/live-trading/prepare",
                json={
                    "research_workspace_id": "research-ws",
                    "live_workspace_name": "AI 实盘交易",
                    "gateway_config": {
                        "api_key": "live-key",
                        "params": {"secret_key": "live-secret", "broker_id": "9999"},
                    },
                },
                headers=auth_headers,
            )
        finally:
            app.dependency_overrides.pop(get_ai_strategy_research_service, None)

        assert list_response.status_code == 200, list_response.text
        assert list_response.json()["items"][0]["run_id"] == "run-1"
        assert detail_response.status_code == 200, detail_response.text
        assert detail_response.json()["paper_review_ready_for_live"] is True
        assert missing_response.status_code == 404

        assert paper_response.status_code == 200, paper_response.text
        assert paper_response.json()["handoff"]["gateway_config"]["api_key"] == "***"
        assert review_response.status_code == 200, review_response.text
        assert review_response.json()["ready_for_live"] is True
        assert handoff_response.status_code == 200, handoff_response.text
        assert handoff_response.json()["handoff"]["gateway_config"]["api_key"] == "***"
        assert approval_response.status_code == 200, approval_response.text
        assert approval_response.json()["approval"]["approved"] is True
        assert prepare_response.status_code == 200, prepare_response.text
        prepared = prepare_response.json()
        assert prepared["prepared"] is True
        assert prepared["unit"]["trading_mode"] == "live"
        assert prepared["unit"]["gateway_config"]["api_key"] == "***"
        called_methods = [item[0] for item in service.calls]
        assert called_methods == [
            "list_run_records",
            "get_run_record",
            "get_run_record",
            "start_paper_trading_from_run",
            "review_paper_trading_run",
            "build_live_handoff_package",
            "record_live_handoff_approval",
            "prepare_live_trading_from_run",
        ]
