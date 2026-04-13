import json

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_workspace_list_supports_workspace_type_filter(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    research_response = await client.post(
        "/api/v1/workspace/",
        headers=auth_headers,
        json={
            "name": "研究工作区",
            "workspace_type": "research",
        },
    )
    assert research_response.status_code == 201

    trading_response = await client.post(
        "/api/v1/workspace/",
        headers=auth_headers,
        json={
            "name": "交易工作区",
            "workspace_type": "trading",
        },
    )
    assert trading_response.status_code == 201

    list_response = await client.get(
        "/api/v1/workspace/",
        headers=auth_headers,
        params={"workspace_type": "trading"},
    )
    assert list_response.status_code == 200

    payload = list_response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["workspace_type"] == "trading"
    assert payload["items"][0]["name"] == "交易工作区"


@pytest.mark.asyncio
async def test_trading_workspace_unit_roundtrip_exposes_trading_fields(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    workspace_response = await client.post(
        "/api/v1/workspace/",
        headers=auth_headers,
        json={
            "name": "策略交易",
            "workspace_type": "trading",
        },
    )
    workspace_id = workspace_response.json()["id"]

    create_response = await client.post(
        f"/api/v1/workspace/{workspace_id}/units",
        headers=auth_headers,
        json={
            "group_name": "交易组",
            "strategy_id": "simulate/gateway_dual_ma",
            "strategy_name": "Demo Strategy",
            "symbol": "au000",
            "symbol_name": "黄金",
            "timeframe": "1m",
            "category": "期货",
            "trading_mode": "live",
            "gateway_config": {
                "preset_id": "ctp_futures_gateway",
                "name": "CTP Futures Gateway",
                "params": {
                    "gateway": {
                        "enabled": True,
                        "exchange_type": "CTP",
                        "asset_type": "FUTURE",
                        "account_id": "SIM001",
                    }
                },
            },
            "lock_trading": True,
        },
    )
    assert create_response.status_code == 201

    payload = create_response.json()
    assert payload["trading_mode"] == "live"
    assert payload["gateway_config"]["preset_id"] == "ctp_futures_gateway"
    assert payload["lock_trading"] is True
    assert payload["lock_running"] is False


class _FakeTradingManager:
    def __init__(self) -> None:
        self.instances: dict[str, dict] = {}

    def get_instance(self, instance_id: str, user_id: str | None = None):
        return self.instances.get(instance_id)

    def add_instance(
        self,
        strategy_id: str,
        params: dict | None = None,
        user_id: str | None = None,
        runtime_dir: str | None = None,
    ):
        instance = {
            "id": "inst-001",
            "strategy_id": strategy_id,
            "strategy_name": "Demo Strategy",
            "status": "stopped",
            "error": None,
            "params": params or {},
            "created_at": "2026-04-13 10:00:00",
            "started_at": None,
            "stopped_at": None,
            "log_dir": None,
            "runtime_dir": runtime_dir,
        }
        self.instances[instance["id"]] = instance
        return instance

    async def start_instance(self, instance_id: str):
        instance = self.instances[instance_id]
        instance["status"] = "running"
        instance["started_at"] = "2026-04-13 10:01:00"
        return instance

    async def stop_instance(self, instance_id: str):
        instance = self.instances[instance_id]
        instance["status"] = "stopped"
        instance["stopped_at"] = "2026-04-13 10:02:00"
        return instance


class _FakeAutoTradingScheduler:
    def __init__(self) -> None:
        self.config = {
            "enabled": False,
            "buffer_minutes": 15,
            "sessions": [
                {"name": "day", "open": "09:00", "close": "15:00"},
                {"name": "night", "open": "21:00", "close": "23:00"},
            ],
            "scope": "all",
        }

    def get_config(self):
        return dict(self.config)

    def update_config(self, **kwargs):
        for key, value in kwargs.items():
            if value is not None:
                self.config[key] = value
        return self.get_config()

    def get_schedule(self):
        return [
            {"session": "day", "start": "08:45", "stop": "15:15"},
            {"session": "night", "start": "20:45", "stop": "23:15"},
        ]


@pytest.mark.asyncio
async def test_trading_workspace_run_and_status_use_trading_runtime_branch(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services import trading_workspace_service

    manager = _FakeTradingManager()
    monkeypatch.setattr(
        trading_workspace_service,
        "get_live_trading_manager",
        lambda: manager,
    )

    workspace_response = await client.post(
        "/api/v1/workspace/",
        headers=auth_headers,
        json={
            "name": "运行测试",
            "workspace_type": "trading",
        },
    )
    workspace_id = workspace_response.json()["id"]

    unit_response = await client.post(
        f"/api/v1/workspace/{workspace_id}/units",
        headers=auth_headers,
        json={
            "group_name": "交易组",
            "strategy_id": "simulate/gateway_dual_ma",
            "strategy_name": "Demo Strategy",
            "symbol": "au000",
            "symbol_name": "黄金",
            "trading_mode": "paper",
        },
    )
    unit_id = unit_response.json()["id"]

    run_response = await client.post(
        f"/api/v1/workspace/{workspace_id}/run",
        headers=auth_headers,
        json={"unit_ids": [unit_id], "parallel": False},
    )
    assert run_response.status_code == 200
    run_payload = run_response.json()
    assert run_payload["results"][0]["status"] == "running"
    assert run_payload["results"][0]["task_id"] == "inst-001"

    status_response = await client.get(
        f"/api/v1/workspace/{workspace_id}/status",
        headers=auth_headers,
    )
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload[0]["run_status"] == "running"
    assert status_payload[0]["trading_instance_id"] == "inst-001"
    assert status_payload[0]["trading_snapshot"]["instance_status"] == "running"


@pytest.mark.asyncio
async def test_trading_workspace_auto_config_and_schedule_endpoints(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
):
    from app.services import trading_workspace_service

    scheduler = _FakeAutoTradingScheduler()
    monkeypatch.setattr(
        trading_workspace_service,
        "get_auto_trading_scheduler",
        lambda: scheduler,
    )

    workspace_response = await client.post(
        "/api/v1/workspace/",
        headers=auth_headers,
        json={"name": "自动交易测试", "workspace_type": "trading"},
    )
    workspace_id = workspace_response.json()["id"]

    get_config_response = await client.get(
        f"/api/v1/workspace/{workspace_id}/trading/auto-config",
        headers=auth_headers,
    )
    assert get_config_response.status_code == 200
    assert get_config_response.json()["enabled"] is False

    update_config_response = await client.put(
        f"/api/v1/workspace/{workspace_id}/trading/auto-config",
        headers=auth_headers,
        json={
            "enabled": True,
            "buffer_minutes": 10,
            "sessions": [{"name": "day", "open": "09:00", "close": "15:00"}],
            "scope": "live",
        },
    )
    assert update_config_response.status_code == 200
    update_payload = update_config_response.json()
    assert update_payload["enabled"] is True
    assert update_payload["buffer_minutes"] == 10
    assert update_payload["scope"] == "live"

    schedule_response = await client.get(
        f"/api/v1/workspace/{workspace_id}/trading/auto-schedule",
        headers=auth_headers,
    )
    assert schedule_response.status_code == 200
    assert schedule_response.json()[0]["session"] == "day"


@pytest.mark.asyncio
async def test_trading_workspace_positions_and_daily_summary_endpoints(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    from app.services import trading_workspace_service

    manager = _FakeTradingManager()
    monkeypatch.setattr(
        trading_workspace_service,
        "get_live_trading_manager",
        lambda: manager,
    )

    workspace_response = await client.post(
        "/api/v1/workspace/",
        headers=auth_headers,
        json={"name": "交易汇总测试", "workspace_type": "trading"},
    )
    workspace_id = workspace_response.json()["id"]

    unit_response = await client.post(
        f"/api/v1/workspace/{workspace_id}/units",
        headers=auth_headers,
        json={
            "group_name": "交易组",
            "strategy_id": "simulate/gateway_dual_ma",
            "strategy_name": "Demo Strategy",
            "symbol": "au000",
            "symbol_name": "黄金",
            "trading_mode": "paper",
        },
    )
    unit_id = unit_response.json()["id"]

    run_response = await client.post(
        f"/api/v1/workspace/{workspace_id}/run",
        headers=auth_headers,
        json={"unit_ids": [unit_id], "parallel": False},
    )
    assert run_response.status_code == 200

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "value.log").write_text(
        "dt\tvalue\tcash\n2026-04-12\t100000\t100000\n2026-04-13\t101500\t101500\n",
        encoding="utf-8",
    )
    (log_dir / "trade.log").write_text(
        "isclosed\tref\tdtopen\tdtclose\tdata_name\tlong\tsize\tprice\tvalue\tcommission\tpnl\tpnlcomm\tbarlen\n"
        "1\t1\t2026-04-12\t2026-04-13\tau000\t1\t2\t100\t200\t1\t1500\t1499\t1\n",
        encoding="utf-8",
    )
    (log_dir / "current_position.json").write_text(
        json.dumps(
            [
                {
                    "data_name": "au000",
                    "size": 2,
                    "price": 100,
                    "market_value": 204,
                }
            ]
        ),
        encoding="utf-8",
    )
    manager.instances["inst-001"]["log_dir"] = str(log_dir)

    positions_response = await client.get(
        f"/api/v1/workspace/{workspace_id}/trading/positions",
        headers=auth_headers,
    )
    assert positions_response.status_code == 200
    positions_payload = positions_response.json()
    assert positions_payload["positions"][0]["unit_id"] == unit_id
    assert positions_payload["positions"][0]["long_position"] == 2.0

    daily_summary_response = await client.get(
        f"/api/v1/workspace/{workspace_id}/trading/daily-summary",
        headers=auth_headers,
    )
    assert daily_summary_response.status_code == 200
    daily_summary_payload = daily_summary_response.json()
    assert daily_summary_payload["summaries"][-1]["trading_date"] == "2026-04-13"
    assert daily_summary_payload["summaries"][-1]["trade_count"] >= 1
