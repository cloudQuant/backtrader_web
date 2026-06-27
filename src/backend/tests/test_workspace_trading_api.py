import json
from pathlib import Path

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
        self.gateway_instances: set[str] = set()
        self.gateway_positions: dict[str, list[dict]] = {}
        self.gateway_asset_specs: dict[str, dict[str, dict]] = {}
        self.gateway_trades: dict[str, list[dict]] = {}

    def get_instance(self, instance_id: str, user_id: str | None = None):
        return self.instances.get(instance_id)

    def has_instance_gateway(self, instance_id: str) -> bool:
        return instance_id in self.gateway_instances

    def query_instance_gateway_positions(self, instance_id: str):
        return self.gateway_positions.get(instance_id, [])

    def query_instance_asset_specs(self, instance_id: str, symbols: list[str]):
        specs = self.gateway_asset_specs.get(instance_id, {})
        return {symbol: specs.get(symbol, {}) for symbol in symbols}

    def query_instance_gateway_trades(
        self,
        instance_id: str,
        *,
        symbol: str | None = None,
        limit: int = 100,
    ):
        rows = self.gateway_trades.get(instance_id, [])
        if symbol:
            rows = [row for row in rows if row.get("symbol") == symbol]
        return rows[-limit:]

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


def test_trading_workspace_position_open_size_honors_explicit_zero():
    from app.services.trading_workspace_service import TradingWorkspaceService

    assert (
        TradingWorkspaceService._position_row_open_size(
            {"size": 0, "long_position": 1, "short_position": 0}
        )
        == 0.0
    )
    assert (
        TradingWorkspaceService._position_row_open_size({"long_position": 1, "short_position": 0})
        == 1.0
    )


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
    (log_dir / "position.log").write_text(
        json.dumps(
            {
                "datetime": "2026-04-13 09:32:00",
                "data_name": "au000",
                "size": 2,
                "price": 100,
                "value": 204,
            }
        )
        + "\n",
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
    assert positions_payload["positions"][0]["updated_at"] == "2026-04-13 09:32:00"

    daily_summary_response = await client.get(
        f"/api/v1/workspace/{workspace_id}/trading/daily-summary",
        headers=auth_headers,
    )
    assert daily_summary_response.status_code == 200
    daily_summary_payload = daily_summary_response.json()
    assert daily_summary_payload["summaries"][-1]["trading_date"] == "2026-04-13"
    assert daily_summary_payload["summaries"][-1]["trade_count"] >= 1


@pytest.mark.asyncio
async def test_trading_workspace_positions_hide_idle_units_by_default(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    """Idle workspaces should not surface stale position logs as current holdings."""
    from app.db.database import async_session_maker
    from app.models.workspace import StrategyUnit
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
        json={"name": "空闲持仓测试", "workspace_type": "trading"},
    )
    workspace_id = workspace_response.json()["id"]

    unit_response = await client.post(
        f"/api/v1/workspace/{workspace_id}/units",
        headers=auth_headers,
        json={
            "group_name": "交易组",
            "strategy_id": "simulate/gateway_dual_ma",
            "strategy_name": "Stopped Strategy",
            "symbol": "rb000",
            "symbol_name": "螺纹",
            "trading_mode": "paper",
        },
    )
    unit_id = unit_response.json()["id"]

    log_dir = tmp_path / "stopped_logs"
    log_dir.mkdir()
    (log_dir / "position.log").write_text(
        json.dumps(
            {
                "datetime": "2026-04-13 09:32:00",
                "data_name": "rb000",
                "size": 3,
                "price": 3200,
                "value": 9600,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manager.instances["stopped-001"] = {
        "id": "stopped-001",
        "strategy_id": "simulate/gateway_dual_ma",
        "strategy_name": "Stopped Strategy",
        "status": "stopped",
        "error": None,
        "params": {},
        "created_at": "2026-04-13 10:00:00",
        "started_at": "2026-04-13 10:01:00",
        "stopped_at": "2026-04-13 10:02:00",
        "log_dir": str(log_dir),
        "runtime_dir": str(tmp_path),
    }
    async with async_session_maker() as session:
        unit = await session.get(StrategyUnit, unit_id)
        assert unit is not None
        unit.trading_instance_id = "stopped-001"
        unit.run_status = "idle"
        await session.commit()

    default_response = await client.get(
        f"/api/v1/workspace/{workspace_id}/trading/positions",
        headers=auth_headers,
    )
    assert default_response.status_code == 200
    default_payload = default_response.json()
    assert default_payload["positions"] == []
    assert default_payload["total_long_value"] == 0.0

    explicit_response = await client.get(
        f"/api/v1/workspace/{workspace_id}/trading/positions",
        headers=auth_headers,
        params={"unit_ids": unit_id},
    )
    assert explicit_response.status_code == 200
    explicit_payload = explicit_response.json()
    assert explicit_payload["positions"][0]["unit_id"] == unit_id
    assert explicit_payload["positions"][0]["long_position"] == 3.0
    assert explicit_payload["positions"][0]["updated_at"] == "2026-04-13 09:32:00"


@pytest.mark.asyncio
async def test_trading_workspace_positions_value_live_futures_hedged_gateway_rows(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
):
    from app.db.database import async_session_maker
    from app.models.workspace import StrategyUnit
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
        json={"name": "期货双向持仓测试", "workspace_type": "trading"},
    )
    workspace_id = workspace_response.json()["id"]

    unit_response = await client.post(
        f"/api/v1/workspace/{workspace_id}/units",
        headers=auth_headers,
        json={
            "group_name": "交易组",
            "strategy_id": "simulate/gateway_dual_ma",
            "strategy_name": "IF Hedge Strategy",
            "symbol": "IF2609",
            "symbol_name": "沪深300期货",
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
        },
    )
    unit_id = unit_response.json()["id"]

    instance_id = "inst-if-hedge"
    manager.instances[instance_id] = {
        "id": instance_id,
        "strategy_id": "simulate/gateway_dual_ma",
        "strategy_name": "IF Hedge Strategy",
        "status": "running",
        "error": None,
        "params": {"symbol": "IF2609", "trading_mode": "live"},
        "created_at": "2026-04-13 10:00:00",
        "started_at": "2026-04-13 10:01:00",
        "stopped_at": None,
        "log_dir": None,
        "runtime_dir": None,
    }
    manager.gateway_instances.add(instance_id)
    manager.gateway_positions[instance_id] = [
        {
            "InstrumentID": "IF2609",
            "long_position": 1,
            "short_position": 1,
            "avgPrice": 5000,
            "LastPrice": 5010,
            "updated_at": "2026-04-13 10:05:00",
        },
        {
            "InstrumentID": "IF2609",
            "long_position": 0,
            "short_position": 0,
            "avgPrice": 5000,
            "LastPrice": 5010,
        },
    ]
    manager.gateway_asset_specs[instance_id] = {
        "IF2609": {
            "symbol": "IF2609",
            "multiplier": 300,
            "margin_rate": 0.1,
            "open_commission_rate": 0.000023,
            "quote_asset": "CNY",
            "fee_currency": "CNY",
            "source": "gateway.query_instrument",
        }
    }
    manager.gateway_trades[instance_id] = [
        {
            "symbol": "IF2609",
            "side": "buy",
            "position_side": "long",
            "size": 1,
            "price": 5000,
            "fee": 34.5,
            "fee_currency": "CNY",
            "trade_time": 1,
        },
        {
            "symbol": "IF2609",
            "side": "sell",
            "position_side": "short",
            "size": 1,
            "price": 5000,
            "fee": 34.5,
            "fee_currency": "CNY",
            "trade_time": 2,
        },
    ]

    async with async_session_maker() as session:
        unit = await session.get(StrategyUnit, unit_id)
        assert unit is not None
        unit.trading_instance_id = instance_id
        unit.run_status = "running"
        unit.trading_mode = "live"
        await session.commit()

    response = await client.get(
        f"/api/v1/workspace/{workspace_id}/trading/positions",
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()

    assert len(payload["positions"]) == 1
    position = payload["positions"][0]
    assert position["unit_id"] == unit_id
    assert position["long_position"] == 1.0
    assert position["short_position"] == 1.0
    assert position["long_market_value"] == 1503000.0
    assert position["short_market_value"] == 1503000.0
    assert position["margin_value"] == 300600.0
    assert position["multiplier"] == 300.0
    assert position["margin_rate"] == 0.1
    assert position["commission"] == 69.0
    assert position["commission_source"] == "gateway.trades"
    assert position["gross_pnl"] == 0.0
    assert position["position_pnl"] == -69.0
    assert position["position_source"] == "gateway"
    assert position["asset_spec_source"] == "gateway.query_instrument"
    assert position["valuation_status"] == "confirmed"
    assert payload["total_pnl"] == -69.0


@pytest.mark.asyncio
async def test_trading_workspace_positions_recalculate_live_futures_generic_pnl(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
):
    from app.db.database import async_session_maker
    from app.models.workspace import StrategyUnit
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
        json={"name": "期货盈亏重估测试", "workspace_type": "trading"},
    )
    workspace_id = workspace_response.json()["id"]

    unit_response = await client.post(
        f"/api/v1/workspace/{workspace_id}/units",
        headers=auth_headers,
        json={
            "group_name": "交易组",
            "strategy_id": "simulate/gateway_dual_ma",
            "strategy_name": "IF PnL Strategy",
            "symbol": "IF2609",
            "symbol_name": "沪深300期货",
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
        },
    )
    unit_id = unit_response.json()["id"]

    instance_id = "inst-if-pnl"
    manager.instances[instance_id] = {
        "id": instance_id,
        "strategy_id": "simulate/gateway_dual_ma",
        "strategy_name": "IF PnL Strategy",
        "status": "running",
        "error": None,
        "params": {"symbol": "IF2609", "trading_mode": "live"},
        "created_at": "2026-04-13 10:00:00",
        "started_at": "2026-04-13 10:01:00",
        "stopped_at": None,
        "log_dir": None,
        "runtime_dir": None,
    }
    manager.gateway_instances.add(instance_id)
    manager.gateway_positions[instance_id] = [
        {
            "InstrumentID": "IF2609",
            "Position": 1,
            "PosiDirection": "2",
            "Price": 5000,
            "LastPrice": 5010,
            "position_pnl": 10,
            "updated_at": "2026-04-13 10:05:00",
        },
        {
            "InstrumentID": "IF2609",
            "Position": 0,
            "PosiDirection": "2",
            "Price": 5000,
            "LastPrice": 5010,
        },
    ]
    manager.gateway_asset_specs[instance_id] = {
        "IF2609": {
            "symbol": "IF2609",
            "multiplier": 300,
            "margin_rate": 0.1,
            "open_commission_rate": 0.000023,
            "quote_asset": "CNY",
            "fee_currency": "CNY",
            "source": "gateway.query_instrument",
        }
    }
    manager.gateway_trades[instance_id] = [
        {
            "symbol": "IF2609",
            "side": "buy",
            "position_side": "long",
            "size": 1,
            "price": 5000,
            "fee": 34.5,
            "fee_currency": "CNY",
            "trade_time": 1,
        },
    ]

    async with async_session_maker() as session:
        unit = await session.get(StrategyUnit, unit_id)
        assert unit is not None
        unit.trading_instance_id = instance_id
        unit.run_status = "running"
        unit.trading_mode = "live"
        await session.commit()

    response = await client.get(
        f"/api/v1/workspace/{workspace_id}/trading/positions",
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()

    assert len(payload["positions"]) == 1
    position = payload["positions"][0]
    assert position["unit_id"] == unit_id
    assert position["long_position"] == 1.0
    assert position["short_position"] == 0.0
    assert position["long_market_value"] == 1503000.0
    assert position["margin_value"] == 150300.0
    assert position["gross_pnl"] == 3000.0
    assert position["commission"] == 34.5
    assert position["commission_source"] == "gateway.trades"
    assert position["position_pnl"] == 2965.5
    assert position["valuation_status"] == "confirmed"
    assert payload["total_pnl"] == 2965.5


@pytest.mark.asyncio
async def test_trading_workspace_positions_complete_partial_gateway_asset_specs(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
):
    """Gateway fee-only specs should be completed from saved runtime contract metadata."""
    from app.db.database import async_session_maker
    from app.models.workspace import StrategyUnit
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
        json={"name": "期货规格补全测试", "workspace_type": "trading"},
    )
    workspace_id = workspace_response.json()["id"]

    unit_response = await client.post(
        f"/api/v1/workspace/{workspace_id}/units",
        headers=auth_headers,
        json={
            "group_name": "交易组",
            "strategy_id": "simulate/gateway_dual_ma",
            "strategy_name": "IF Partial Spec Strategy",
            "symbol": "IF2609",
            "symbol_name": "沪深300期货",
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
        },
    )
    unit_id = unit_response.json()["id"]

    instance_id = "inst-if-partial-spec"
    manager.instances[instance_id] = {
        "id": instance_id,
        "strategy_id": "simulate/gateway_dual_ma",
        "strategy_name": "IF Partial Spec Strategy",
        "status": "running",
        "error": None,
        "params": {"symbol": "IF2609", "trading_mode": "live"},
        "created_at": "2026-04-13 10:00:00",
        "started_at": "2026-04-13 10:01:00",
        "stopped_at": None,
        "log_dir": None,
        "runtime_dir": None,
    }
    manager.gateway_instances.add(instance_id)
    manager.gateway_positions[instance_id] = [
        {
            "InstrumentID": "IF2609",
            "Position": 1,
            "PosiDirection": "2",
            "Price": 5000,
            "LastPrice": 5010,
            "PositionProfit": 10,
            "updated_at": "2026-04-13 10:05:00",
        }
    ]
    manager.gateway_asset_specs[instance_id] = {
        "IF2609": {
            "symbol": "IF2609",
            "OpenRatioByMoney": 0.23,
            "quote_asset": "CNY",
            "fee_currency": "CNY",
            "source": "gateway.fee_only",
        }
    }

    async with async_session_maker() as session:
        unit = await session.get(StrategyUnit, unit_id)
        assert unit is not None
        unit.trading_instance_id = instance_id
        unit.run_status = "running"
        unit.trading_mode = "live"
        unit.params = {
            **(unit.params or {}),
            "contract_metadata": {
                "IF2609": {
                    "symbol": "IF2609",
                    "VolumeMultiple": 300,
                    "LongMarginRatioByMoney": 0.1,
                    "source": "runtime_contract",
                }
            },
        }
        await session.commit()

    response = await client.get(
        f"/api/v1/workspace/{workspace_id}/trading/positions",
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()

    assert len(payload["positions"]) == 1
    position = payload["positions"][0]
    assert position["multiplier"] == 300.0
    assert position["margin_value"] == 150300.0
    assert position["gross_pnl"] == 3000.0
    assert position["commission"] == 34.5
    assert position["position_pnl"] == 2965.5
    assert "gateway.fee_only" in position["asset_spec_source"]
    assert "runtime_contract" in position["asset_spec_source"]


@pytest.mark.asyncio
async def test_trading_workspace_runtime_endpoints_expose_runtime_files(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    import shutil

    from app.services import workspace_unit_runtime
    from app.services.strategy_service import get_strategy_dir

    # The strategy template tree (src/strategies/) is developer-local and not
    # tracked in git, so provision a minimal template on disk for this
    # integration test (and clean it up afterwards) instead of depending on a
    # checkout-specific directory.
    template_dir = get_strategy_dir("simulate/gateway_dual_ma")
    created_template = not template_dir.exists()
    template_dir.mkdir(parents=True, exist_ok=True)
    run_py = template_dir / "run.py"
    strategy_py = template_dir / "strategy_gateway_dual_ma.py"
    created_run = not run_py.exists()
    created_strategy = not strategy_py.exists()
    if created_run:
        run_py.write_text("# runtime entrypoint\n", encoding="utf-8")
    if created_strategy:
        strategy_py.write_text(
            "import backtrader as bt\n\n\nclass S(bt.Strategy):\n    pass\n",
            encoding="utf-8",
        )

    try:
        workspace_response = await client.post(
            "/api/v1/workspace/",
            headers=auth_headers,
            json={"name": "运行文件测试", "workspace_type": "trading"},
        )
        assert workspace_response.status_code == 201
        workspace_id = workspace_response.json()["id"]

        unit_response = await client.post(
            f"/api/v1/workspace/{workspace_id}/units",
            headers=auth_headers,
            json={
                "group_name": "交易组",
                "strategy_id": "simulate/gateway_dual_ma",
                "strategy_name": "Runtime Unit",
                "symbol": "XAUUSD",
                "symbol_name": "黄金/美元",
                "timeframe": "1m",
                "category": "外汇",
                "trading_mode": "paper",
            },
        )
        assert unit_response.status_code == 201
        unit_id = unit_response.json()["id"]

        runtime_dir = workspace_unit_runtime.unit_dir(workspace_id, unit_id)
        assert runtime_dir.is_dir()
        log_dir = runtime_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "system.log").write_text("line-1\nline-2\n", encoding="utf-8")

        info_response = await client.get(
            f"/api/v1/workspace/{workspace_id}/units/{unit_id}/runtime",
            headers=auth_headers,
        )
        assert info_response.status_code == 200
        payload = info_response.json()
        assert Path(payload["runtime_dir"]) == runtime_dir
        assert Path(payload["log_dir"]) == log_dir
        relative_paths = {item["relative_path"] for item in payload["files"]}
        assert "config.yaml" in relative_paths
        assert "run.py" in relative_paths
        assert "logs/system.log" in relative_paths

        log_response = await client.get(
            f"/api/v1/workspace/{workspace_id}/units/{unit_id}/runtime/files/logs/system.log",
            headers=auth_headers,
            params={"tail": 1},
        )
        assert log_response.status_code == 200
        assert log_response.text == "line-2"
    finally:
        # Clean up only what we created so we don't disturb a real local tree.
        if created_run and run_py.exists():
            run_py.unlink()
        if created_strategy and strategy_py.exists():
            strategy_py.unlink()
        if created_template and template_dir.exists():
            shutil.rmtree(template_dir, ignore_errors=True)
