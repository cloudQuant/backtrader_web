#!/usr/bin/env python
"""Seed simulated trading workspaces with paper strategy units.

The CTP and MT5 workspaces include a fixed 50-unit stress set each.  The unit
names are stable so repeated runs update the same rows instead of duplicating
them.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings  # noqa: E402
from app.db.database import (
    async_session_maker,  # noqa: E402
    create_default_admin,  # noqa: E402
)
from app.models.user import User  # noqa: E402
from app.models.workspace import StrategyUnit, Workspace  # noqa: E402
from app.schemas.workspace import (  # noqa: E402
    StrategyUnitCreate,
    StrategyUnitUpdate,
    WorkspaceCreate,
)
from app.services.workspace_service import WorkspaceService  # noqa: E402

DEFAULT_SYMBOLS_PATH = BACKEND_DIR / "config" / "default_symbols.yaml"
MANUAL_GATEWAYS_PATH = BACKEND_DIR / "data" / "manual_gateways.json"
STRESS_UNITS_PER_EXCHANGE = 50
STRESS_LIVE_QCHECK_SECONDS = 0.5
DEFAULT_STRESS_DURATION_SECONDS = 7 * 24 * 60 * 60
STRESS_UNIT_PREFIXES = {
    "futures": "CTP压测",
    "mt5": "MT5压测",
}
STRESS_SUITE_ID = "dual_exchange_simulation"
CONTRACT_SYMBOL_RE = re.compile(r"^([A-Za-z]+)(\d{2})(\d{2})$")


def stress_duration_seconds() -> int:
    raw = str(os.getenv("SIM_STRESS_DURATION_SECONDS") or "").strip()
    if raw:
        try:
            value = int(raw)
        except ValueError:
            value = DEFAULT_STRESS_DURATION_SECONDS
        else:
            if value > 0:
                return value
    return DEFAULT_STRESS_DURATION_SECONDS

WORKSPACE_NAMES = {
    "futures": "期货模拟工作区",
    "ib": "IB模拟工作区",
    "mt5": "MT5模拟工作区",
}

WORKSPACE_DESCRIPTIONS = {
    "futures": "CTP 期货模拟交易压测工作区",
    "ib": "IB Web 模拟交易工作区",
    "mt5": "MT5 外汇/贵金属模拟交易压测工作区",
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

STRESS_VARIANTS = [
    {
        "group_name": "压测-短周期均线",
        "strategy_id": "simulate/gateway_dual_ma",
        "display_name": "短周期均线",
        "params": MA_PARAM_SETS[0],
    },
    {
        "group_name": "压测-中周期均线",
        "strategy_id": "simulate/gateway_dual_ma",
        "display_name": "中周期均线",
        "params": MA_PARAM_SETS[1],
    },
    {
        "group_name": "压测-趋势均线",
        "strategy_id": "simulate/gateway_dual_ma",
        "display_name": "趋势均线",
        "params": MA_PARAM_SETS[3],
    },
    {
        "group_name": "压测-布林突破",
        "strategy_id": "simulate/gateway_boll_breakout",
        "display_name": "布林突破",
        "params": BOLL_PARAM_SETS[1],
    },
    {
        "group_name": "压测-宽带布林",
        "strategy_id": "simulate/gateway_boll_breakout",
        "display_name": "宽带布林",
        "params": BOLL_PARAM_SETS[3],
    },
]


def _add_months(year: int, month: int, offset: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + offset
    return total // 12, total % 12 + 1


def roll_expired_ctp_contract_symbol(symbol: str, now: datetime | None = None) -> str:
    """Roll CTP YYMM contract codes that are already in the current/past month."""
    text = str(symbol or "").strip()
    match = CONTRACT_SYMBOL_RE.match(text)
    if not match:
        return text

    prefix, year_text, month_text = match.groups()
    year = 2000 + int(year_text)
    month = int(month_text)
    current = now or datetime.now()
    if (year, month) > (current.year, current.month):
        return text

    target_year, target_month = _add_months(current.year, current.month, 2)
    return f"{prefix}{target_year % 100:02d}{target_month:02d}"


def _stress_slot(workspace_key: str, index: int) -> str:
    return f"{workspace_key}-{index + 1:02d}"


def _stress_slot_from_name(name: Any) -> str | None:
    text = str(name or "")
    for workspace_key, prefix in STRESS_UNIT_PREFIXES.items():
        if not text.startswith(prefix):
            continue
        match = re.search(r"(\d{2})(?=\D|$)", text[len(prefix) :])
        if match:
            return _stress_slot(workspace_key, int(match.group(1)) - 1)
    return None


def _normalize_stress_symbol(workspace_key: str, symbol: dict[str, Any]) -> dict[str, Any]:
    item = dict(symbol)
    if workspace_key == "futures":
        item["symbol"] = roll_expired_ctp_contract_symbol(str(item.get("symbol") or ""))
    return item


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
    settings = get_settings()
    account_id = str(
        credentials.get("account_id") or settings.IB_WEB_ACCOUNT_ID or settings.IB_ACCOUNT_ID or ""
    ).strip()
    base_url = str(
        credentials.get("base_url")
        or settings.IB_WEB_BASE_URL
        or settings.IB_BASE_URL
        or "https://localhost:5000"
    ).strip()
    verify_ssl = bool(
        credentials.get(
            "verify_ssl",
            settings.IB_WEB_VERIFY_SSL if settings.IB_WEB_BASE_URL else settings.IB_VERIFY_SSL,
        )
    )
    timeout = float(
        credentials.get("timeout")
        or settings.IB_WEB_TIMEOUT
        or settings.IB_TIMEOUT
        or 10
    )
    cookie_source = str(
        credentials.get("cookie_source")
        or settings.IB_WEB_COOKIE_SOURCE
        or settings.IB_COOKIE_SOURCE
        or ""
    ).strip()
    cookie_browser = str(
        credentials.get("cookie_browser")
        or settings.IB_WEB_COOKIE_BROWSER
        or settings.IB_COOKIE_BROWSER
        or "chrome"
    ).strip()
    cookie_path = str(
        credentials.get("cookie_path")
        or settings.IB_WEB_COOKIE_PATH
        or settings.IB_COOKIE_PATH
        or "/sso"
    ).strip()
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
                "base_url": base_url,
                "verify_ssl": verify_ssl,
                "cookie_source": cookie_source,
                "cookie_browser": cookie_browser,
                "cookie_path": cookie_path,
                "timeout": timeout,
            },
            "ib_web": {
                "account_id": account_id,
                "base_url": base_url,
                "verify_ssl": verify_ssl,
                "timeout": timeout,
                "cookie_source": cookie_source,
                "cookie_browser": cookie_browser,
                "cookie_path": cookie_path,
            },
        },
    }


def build_mt5_gateway_config(credentials: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    login = str(
        credentials.get("login")
        or settings.MT5_LOGIN
        or settings.MT5_DEMO_LOGIN
        or ""
    ).strip()
    ws_uri = str(
        credentials.get("ws_uri")
        or settings.MT5_WS_URI
        or settings.MT5_DEMO_WS_URI
        or "wss://web.metatrader.app/terminal"
    ).strip()
    server = str(
        credentials.get("server")
        or settings.MT5_SERVER
        or settings.MT5_DEMO_SERVER
        or ""
    ).strip()
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
                "ws_uri": ws_uri,
                "server": server,
                "symbol_suffix": str(credentials.get("symbol_suffix") or "").strip(),
            },
            "mt5": {
                "login": login,
                "ws_uri": ws_uri,
                "server": server,
                "symbol_suffix": str(credentials.get("symbol_suffix") or "").strip(),
            },
        },
    }


def build_stress_unit_specs(
    *,
    workspace_key: str,
    symbols: list[dict[str, Any]],
    gateway_config: dict[str, Any],
    category: str,
    initial_cash: float,
    commission: float,
    slippage: float,
    position_size: float,
) -> list[dict[str, Any]]:
    """Build a stable 50-unit simulated trading stress set for one exchange."""
    if not symbols:
        return []

    prefix = STRESS_UNIT_PREFIXES[workspace_key]
    specs: list[dict[str, Any]] = []
    duration_seconds = stress_duration_seconds()
    for index in range(STRESS_UNITS_PER_EXCHANGE):
        symbol = _normalize_stress_symbol(workspace_key, symbols[index % len(symbols)])
        variant = STRESS_VARIANTS[(index // len(symbols)) % len(STRESS_VARIANTS)]
        symbol_code = str(symbol.get("symbol") or "").strip()
        slot = _stress_slot(workspace_key, index)
        params = dict(variant["params"])
        params.update(position_size=position_size, allow_short=True)
        specs.append(
            {
                "stress_slot": slot,
                "group_name": str(variant["group_name"]),
                "strategy_id": str(variant["strategy_id"]),
                "strategy_name": f"{prefix}{index + 1:02d}-{variant['display_name']}-1m",
                "symbol": symbol_code,
                "symbol_name": str(symbol.get("name") or symbol_code),
                "timeframe": "1m",
                "timeframe_n": 1,
                "category": category,
                "params": params,
                "unit_settings": {
                    "initial_cash": initial_cash,
                    "commission": commission,
                    "slippage": slippage,
                    "duration_seconds": duration_seconds,
                    "session_timeout": duration_seconds + 60,
                    "qcheck": STRESS_LIVE_QCHECK_SECONDS,
                    "log_ticks": False,
                    "log_positions": True,
                    "log_indicators": False,
                    "log_signals": True,
                    "dispatch_ticks": False,
                    "exactbars": True,
                    "stdstats": False,
                },
                "gateway_config": gateway_config,
            }
        )
    return specs


def build_workspace_specs() -> dict[str, list[dict[str, Any]]]:
    symbols = load_default_symbols()
    gateways = load_manual_gateways()
    duration_seconds = stress_duration_seconds()

    futures_gateway = build_ctp_gateway_config(gateways.get("CTP") or {})
    ib_gateway = build_ib_gateway_config(gateways.get("IB_WEB") or {})
    mt5_gateway = build_mt5_gateway_config(gateways.get("MT5") or {})

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

    result: dict[str, list[dict[str, Any]]] = {"futures": [], "ib": [], "mt5": []}

    result["futures"] = build_stress_unit_specs(
        workspace_key="futures",
        symbols=symbols["futures"],
        gateway_config=futures_gateway,
        category="future",
        initial_cash=1000000,
        commission=0.0001,
        slippage=0.00005,
        position_size=1,
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
                    "duration_seconds": duration_seconds,
                    "session_timeout": duration_seconds + 60,
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
                    "duration_seconds": duration_seconds,
                    "session_timeout": duration_seconds + 60,
                },
                "gateway_config": ib_gateway,
            }
        )

    result["mt5"] = build_stress_unit_specs(
        workspace_key="mt5",
        symbols=symbols["mt5"],
        gateway_config=mt5_gateway,
        category="forex",
        initial_cash=10000,
        commission=0.00007,
        slippage=0.00002,
        position_size=0.01,
    )

    return result


async def load_seed_user_id() -> str:
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.username == "admin"))
        user = result.scalar_one_or_none()
        if user is not None:
            return str(user.id)

        result = await session.execute(select(User).order_by(User.created_at.asc()).limit(1))
        user = result.scalar_one_or_none()
        if user is not None:
            return str(user.id)

    await create_default_admin()

    async with async_session_maker() as session:
        result = await session.execute(select(User).order_by(User.created_at.asc()).limit(1))
        user = result.scalar_one_or_none()
        if user is None:
            raise RuntimeError("未找到用户，且无法创建默认管理员用户。")
        return str(user.id)


async def load_workspaces() -> dict[str, Workspace]:
    async with async_session_maker() as session:
        result = await session.execute(
            select(Workspace).where(Workspace.name.in_(list(WORKSPACE_NAMES.values())))
        )
        items = list(result.scalars().all())
        changed = False
        for workspace in items:
            if str(workspace.workspace_type or "").strip().lower() != "trading":
                workspace.workspace_type = "trading"
                changed = True
        if changed:
            await session.commit()
    workspaces = {workspace.name: workspace for workspace in items}
    missing = [name for name in WORKSPACE_NAMES.values() if name not in workspaces]
    if missing:
        user_id = await load_seed_user_id()
        service = WorkspaceService()
        for workspace_key, workspace_name in WORKSPACE_NAMES.items():
            if workspace_name not in missing:
                continue
            await service.create_workspace(
                user_id,
                WorkspaceCreate(
                    name=workspace_name,
                    description=WORKSPACE_DESCRIPTIONS.get(workspace_key),
                    workspace_type="trading",
                ),
            )
        return await load_workspaces()
    return workspaces


async def load_existing_units(workspace_id: str) -> tuple[dict[str, str], dict[str, str]]:
    async with async_session_maker() as session:
        result = await session.execute(
            select(StrategyUnit.id, StrategyUnit.strategy_name, StrategyUnit.data_config).where(
                StrategyUnit.workspace_id == workspace_id
            )
        )
        by_name: dict[str, str] = {}
        by_slot: dict[str, str] = {}
        for unit_id, name, data_config in result.all():
            unit_id_text = str(unit_id)
            name_text = str(name or "")
            if name_text:
                by_name[name_text] = unit_id_text
            slot = None
            if isinstance(data_config, dict) and data_config.get("stress_suite") == STRESS_SUITE_ID:
                slot = str(data_config.get("stress_slot") or "").strip() or None
            if slot is None:
                slot = _stress_slot_from_name(name_text)
            if slot:
                by_slot.setdefault(slot, unit_id_text)
        return by_name, by_slot


async def seed_workspace(
    service: WorkspaceService,
    workspace: Workspace,
    unit_specs: list[dict[str, Any]],
) -> tuple[int, int]:
    existing_by_name, existing_by_slot = await load_existing_units(workspace.id)
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
            data_config={
                "range_type": "sample",
                "sample_count": 300,
                "stress_suite": STRESS_SUITE_ID,
                "stress_slot": spec.get("stress_slot"),
            },
            optimization_config={},
            trading_mode="paper",
            gateway_config=spec["gateway_config"],
            lock_trading=False,
            lock_running=False,
        )
        existing_unit_id = existing_by_name.get(spec["strategy_name"]) or existing_by_slot.get(
            str(spec.get("stress_slot") or "")
        )
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
