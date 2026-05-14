"""Additional API integration tests for strategy endpoints."""

import pytest
from httpx import AsyncClient

from tests.conftest import register_and_login

SAMPLE_CODE = "import backtrader as bt\nclass TestStrategy(bt.Strategy): pass"


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
