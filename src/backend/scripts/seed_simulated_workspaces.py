#!/usr/bin/env python
"""Seed the three simulated trading workspaces with paper strategy units."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.database import async_session_maker  # noqa: E402
from app.models.workspace import StrategyUnit, Workspace  # noqa: E402
from app.schemas.workspace import StrategyUnitCreate, StrategyUnitUpdate  # noqa: E402
from app.services.workspace_service import WorkspaceService  # noqa: E402

DEFAULT_SYMBOLS_PATH = BACKEND_DIR / "config" / "default_symbols.yaml"
MANUAL_GATEWAYS_PATH = BACKEND_DIR / "data" / "manual_gateways.json"

WORKSPACE_NAMES = {
    "futures": "期货模拟工作区",
    "ib": "IB模拟工作区",
    "mt5": "MT5模拟工作区",
}

MA_PARAM_SETS = [
    {"fast_period": 3, "slow_period": 8},
    {"fast_period": 5, "slow_period": 13},
    {"fast_period": 6, "slow_period": 15},
    {"fast_period": 8, "slow_period": 21},
    {"fast_period": 10, "slow_period": 30},
]

BOLL_PARAM_SETS = [
    {"boll_period": 12, "boll_dev": 1.8},
    {"boll_period": 16, "boll_dev": 2.0},
    {"boll_period": 20, "boll_dev": 2.1},
    {"boll_period": 24, "boll_dev": 2.2},
    {"boll_period": 30, "boll_dev": 2.4},
]


def load_default_symbols() -> dict[str, list[dict[str, Any]]]:
    config = yaml.safe_load(DEFAULT_SYMBOLS_PATH.read_text("utf-8")) or {}
    symbols = config.get("symbols") or {}
    return {
        "futures": list(symbols.get("CTP") or []),
        "ib": list(symbols.get("IB_WEB") or []),
        "mt5": list(symbols.get("MT5") or []),
    }


def load_manual_gateways() -> dict[str, dict[str, Any]]:
    if not MANUAL_GATEWAYS_PATH.exists():
        return {}
    data = json.loads(MANUAL_GATEWAYS_PATH.read_text("utf-8"))
    result: dict[str, dict[str, Any]] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        exchange_type = str(item.get("exchange_type") or "").strip().upper()
        credentials = item.get("credentials")
        if exchange_type and isinstance(credentials, dict):
            result[exchange_type] = credentials
    return result


def build_ctp_gateway_config(credentials: dict[str, Any]) -> dict[str, Any]:
    user_id = str(credentials.get("user_id") or "").strip()
    return {
        "preset_id": "ctp_futures_gateway",
        "name": "CTP Futures Gateway",
        "params": {
            "gateway": {
                "enabled": True,
                "provider": "ctp_gateway",
                "exchange_type": "CTP",
                "asset_type": "FUTURE",
                "account_id": user_id,
            },
            "ctp": {
                "broker_id": str(credentials.get("broker_id") or "").strip(),
                "investor_id": user_id,
                "user_id": user_id,
                "password": str(credentials.get("password") or "").strip(),
                "app_id": str(credentials.get("app_id") or "simnow_client_test").strip(),
                "auth_code": str(credentials.get("auth_code") or "0000000000000000").strip(),
                "fronts": {
                    "telecom": {
                        "td_address": str(credentials.get("td_front") or "").strip(),
                        "md_address": str(credentials.get("md_front") or "").strip(),
                    }
                },
            },
        },
    }


def build_ib_gateway_config(credentials: dict[str, Any]) -> dict[str, Any]:
    account_id = str(credentials.get("account_id") or "").strip()
    return {
        "preset_id": "ib_web_stock_gateway",
        "name": "IB Web Stock Gateway",
        "params": {
            "gateway": {
                "enabled": True,
                "provider": "gateway",
                "exchange_type": "IB_WEB",
                "asset_type": "STK",
                "account_id": account_id,
                "base_url": str(credentials.get("base_url") or "https://localhost:5000").strip(),
                "verify_ssl": bool(credentials.get("verify_ssl", False)),
                "access_token": str(credentials.get("access_token") or "").strip(),
                "cookie_source": str(credentials.get("cookie_source") or "").strip(),
                "cookie_browser": str(credentials.get("cookie_browser") or "chrome").strip(),
                "cookie_path": str(credentials.get("cookie_path") or "/sso").strip(),
                "timeout": float(credentials.get("timeout") or 10),
            },
            "ib_web": {
                "account_id": account_id,
                "base_url": str(credentials.get("base_url") or "https://localhost:5000").strip(),
                "verify_ssl": bool(credentials.get("verify_ssl", False)),
                "timeout": float(credentials.get("timeout") or 10),
                "access_token": str(credentials.get("access_token") or "").strip(),
                "cookie_source": str(credentials.get("cookie_source") or "").strip(),
                "cookie_browser": str(credentials.get("cookie_browser") or "chrome").strip(),
                "cookie_path": str(credentials.get("cookie_path") or "/sso").strip(),
            },
        },
    }


def build_mt5_gateway_config(credentials: dict[str, Any]) -> dict[str, Any]:
    login = str(credentials.get("login") or "").strip()
    return {
        "preset_id": "mt5_forex_gateway",
        "name": "MT5 Forex Gateway",
        "params": {
            "gateway": {
                "enabled": True,
                "provider": "mt5_gateway",
                "exchange_type": "MT5",
                "asset_type": "OTC",
                "account_id": login,
                "login": login,
                "password": str(credentials.get("password") or "").strip(),
                "ws_uri": str(credentials.get("ws_uri") or "wss://web.metatrader.app/terminal").strip(),
                "symbol_suffix": str(credentials.get("symbol_suffix") or "").strip(),
            },
            "mt5": {
                "login": login,
                "password": str(credentials.get("password") or "").strip(),
                "ws_uri": str(credentials.get("ws_uri") or "wss://web.metatrader.app/terminal").strip(),
                "symbol_suffix": str(credentials.get("symbol_suffix") or "").strip(),
            },
        },
    }


def build_workspace_specs() -> dict[str, list[dict[str, Any]]]:
    symbols = load_default_symbols()
    gateways = load_manual_gateways()

    futures_gateway = build_ctp_gateway_config(gateways.get("CTP") or {})
    ib_gateway = build_ib_gateway_config(gateways.get("IB_WEB") or {})
    mt5_gateway = build_mt5_gateway_config(gateways.get("MT5") or {})

    futures_ma_symbols = symbols["futures"][:5]
    futures_boll_symbols = symbols["futures"][5:10]
    ib_ma_symbols = [
        symbols["ib"][0],
        symbols["ib"][1],
        symbols["ib"][5],
        symbols["ib"][7],
        symbols["ib"][8],
    ]
    ib_boll_symbols = [
        symbols["ib"][2],
        symbols["ib"][3],
        symbols["ib"][4],
        symbols["ib"][6],
        symbols["ib"][7],
    ]
    mt5_ma_symbols = symbols["mt5"][:5]
    mt5_boll_symbols = symbols["mt5"][5:10]

    result: dict[str, list[dict[str, Any]]] = {"futures": [], "ib": [], "mt5": []}

    for index, symbol in enumerate(futures_ma_symbols):
        params = dict(MA_PARAM_SETS[index], position_size=1, allow_short=True)
        result["futures"].append(
            {
                "group_name": "均线金叉",
                "strategy_id": "simulate/gateway_dual_ma",
                "strategy_name": f"期货均线金叉{index + 1:02d}-{symbol['symbol']}-1m",
                "symbol": symbol["symbol"],
                "symbol_name": symbol["name"],
                "timeframe": "1m",
                "timeframe_n": 1,
                "category": "future",
                "params": params,
                "unit_settings": {
                    "initial_cash": 1000000,
                    "commission": 0.0001,
                    "slippage": 0.00005,
                    "duration_seconds": 7200,
                    "session_timeout": 7260,
                },
                "gateway_config": futures_gateway,
            }
        )
    for index, symbol in enumerate(futures_boll_symbols):
        params = dict(BOLL_PARAM_SETS[index], position_size=1, allow_short=True)
        result["futures"].append(
            {
                "group_name": "布林突破",
                "strategy_id": "simulate/gateway_boll_breakout",
                "strategy_name": f"期货布林突破{index + 1:02d}-{symbol['symbol']}-1m",
                "symbol": symbol["symbol"],
                "symbol_name": symbol["name"],
                "timeframe": "1m",
                "timeframe_n": 1,
                "category": "future",
                "params": params,
                "unit_settings": {
                    "initial_cash": 1000000,
                    "commission": 0.0001,
                    "slippage": 0.00005,
                    "duration_seconds": 7200,
                    "session_timeout": 7260,
                },
                "gateway_config": futures_gateway,
            }
        )

    for index, symbol in enumerate(ib_ma_symbols):
        params = dict(MA_PARAM_SETS[index], position_size=1, allow_short=True)
        result["ib"].append(
            {
                "group_name": "均线金叉",
                "strategy_id": "simulate/gateway_dual_ma",
                "strategy_name": f"IB均线金叉{index + 1:02d}-{symbol['symbol']}-1m",
                "symbol": symbol["symbol"],
                "symbol_name": symbol["name"],
                "timeframe": "1m",
                "timeframe_n": 1,
                "category": "stock",
                "params": params,
                "unit_settings": {
                    "initial_cash": 100000,
                    "commission": 0.0005,
                    "slippage": 0.0001,
                    "duration_seconds": 7200,
                    "session_timeout": 7260,
                },
                "gateway_config": ib_gateway,
            }
        )
    for index, symbol in enumerate(ib_boll_symbols):
        params = dict(BOLL_PARAM_SETS[index], position_size=1, allow_short=True)
        result["ib"].append(
            {
                "group_name": "布林突破",
                "strategy_id": "simulate/gateway_boll_breakout",
                "strategy_name": f"IB布林突破{index + 1:02d}-{symbol['symbol']}-1m",
                "symbol": symbol["symbol"],
                "symbol_name": symbol["name"],
                "timeframe": "1m",
                "timeframe_n": 1,
                "category": "stock",
                "params": params,
                "unit_settings": {
                    "initial_cash": 100000,
                    "commission": 0.0005,
                    "slippage": 0.0001,
                    "duration_seconds": 7200,
                    "session_timeout": 7260,
                },
                "gateway_config": ib_gateway,
            }
        )

    for index, symbol in enumerate(mt5_ma_symbols):
        params = dict(MA_PARAM_SETS[index], position_size=0.01, allow_short=True)
        result["mt5"].append(
            {
                "group_name": "均线金叉",
                "strategy_id": "simulate/gateway_dual_ma",
                "strategy_name": f"MT5均线金叉{index + 1:02d}-{symbol['symbol']}-1m",
                "symbol": symbol["symbol"],
                "symbol_name": symbol["name"],
                "timeframe": "1m",
                "timeframe_n": 1,
                "category": "forex",
                "params": params,
                "unit_settings": {
                    "initial_cash": 10000,
                    "commission": 0.00007,
                    "slippage": 0.00002,
                    "duration_seconds": 7200,
                    "session_timeout": 7260,
                },
                "gateway_config": mt5_gateway,
            }
        )
    for index, symbol in enumerate(mt5_boll_symbols):
        params = dict(BOLL_PARAM_SETS[index], position_size=0.01, allow_short=True)
        result["mt5"].append(
            {
                "group_name": "布林突破",
                "strategy_id": "simulate/gateway_boll_breakout",
                "strategy_name": f"MT5布林突破{index + 1:02d}-{symbol['symbol']}-1m",
                "symbol": symbol["symbol"],
                "symbol_name": symbol["name"],
                "timeframe": "1m",
                "timeframe_n": 1,
                "category": "forex",
                "params": params,
                "unit_settings": {
                    "initial_cash": 10000,
                    "commission": 0.00007,
                    "slippage": 0.00002,
                    "duration_seconds": 7200,
                    "session_timeout": 7260,
                },
                "gateway_config": mt5_gateway,
            }
        )

    return result


async def load_workspaces() -> dict[str, Workspace]:
    async with async_session_maker() as session:
        result = await session.execute(
            select(Workspace).where(Workspace.name.in_(list(WORKSPACE_NAMES.values())))
        )
        items = list(result.scalars().all())
    workspaces = {workspace.name: workspace for workspace in items}
    missing = [name for name in WORKSPACE_NAMES.values() if name not in workspaces]
    if missing:
        raise RuntimeError(f"未找到目标工作区: {', '.join(missing)}")
    return workspaces


async def load_existing_units(workspace_id: str) -> dict[str, str]:
    async with async_session_maker() as session:
        result = await session.execute(
            select(StrategyUnit.id, StrategyUnit.strategy_name).where(
                StrategyUnit.workspace_id == workspace_id
            )
        )
        return {name: unit_id for unit_id, name in result.all()}


async def seed_workspace(
    service: WorkspaceService,
    workspace: Workspace,
    unit_specs: list[dict[str, Any]],
) -> tuple[int, int]:
    existing = await load_existing_units(workspace.id)
    created = 0
    updated = 0
    for spec in unit_specs:
        create_payload = StrategyUnitCreate(
            group_name=spec["group_name"],
            strategy_id=spec["strategy_id"],
            strategy_name=spec["strategy_name"],
            symbol=spec["symbol"],
            symbol_name=spec["symbol_name"],
            timeframe=spec["timeframe"],
            timeframe_n=spec["timeframe_n"],
            category=spec["category"],
            params=spec["params"],
            unit_settings=spec["unit_settings"],
            data_config={"range_type": "sample", "sample_count": 300},
            optimization_config={},
            trading_mode="paper",
            gateway_config=spec["gateway_config"],
            lock_trading=False,
            lock_running=False,
        )
        existing_unit_id = existing.get(spec["strategy_name"])
        if existing_unit_id:
            await service.update_unit(
                workspace.id,
                existing_unit_id,
                workspace.user_id,
                StrategyUnitUpdate(**create_payload.model_dump()),
            )
            updated += 1
        else:
            await service.create_unit(workspace.id, workspace.user_id, create_payload)
            created += 1
    return created, updated


async def main() -> None:
    service = WorkspaceService()
    workspaces = await load_workspaces()
    specs = build_workspace_specs()

    summary: list[str] = []
    for workspace_key, workspace_name in WORKSPACE_NAMES.items():
        workspace = workspaces[workspace_name]
        created, updated = await seed_workspace(service, workspace, specs[workspace_key])
        summary.append(f"{workspace_name}: created={created}, updated={updated}")

    print("\n".join(summary))


if __name__ == "__main__":
    asyncio.run(main())
