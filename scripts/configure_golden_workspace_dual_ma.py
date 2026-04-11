import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "src" / "backend"
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{(BACKEND_ROOT / 'backtrader.db').resolve()}")
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.database import async_session_maker
from app.models.workspace import StrategyUnit
from app.schemas.workspace import StrategyUnitCreate, StrategyUnitUpdate, WorkspaceUpdate
from sqlalchemy import select

from app.services import workspace_unit_runtime
from app.services.workspace_service import WorkspaceService

WORKSPACE_ID = "5e5ca26f-dbc6-47cd-9016-20c3024cdc51"
USER_ID = "50b591ae-4bf9-4f83-a26c-b3663afc5a9b"
STRATEGY_ID = "backtest/097_dema_crossover"
GROUP_NAME = "黄金工作区-双均线日线组"
DATA_ROOT = REPO_ROOT / "datas"
DATA_DIR = DATA_ROOT / "forex" / "D1"
TARGET_SYMBOLS = [
    "AAPL",
    "ABBV",
    "ABNB",
    "ACN",
    "ABT",
    "AAL",
    "AAON",
    "AAXJ",
    "AAT",
    "ACHR",
]
LEGACY_STRATEGY_ID = "backtest/002_dual_ma"


async def main() -> None:
    if not DATA_DIR.is_dir():
        raise RuntimeError(f"数据目录不存在: {DATA_DIR}")

    existing_files = {path.stem.replace("_D1", "") for path in DATA_DIR.glob("*.csv")}
    missing = [symbol for symbol in TARGET_SYMBOLS if symbol not in existing_files]
    if missing:
        raise RuntimeError(f"缺少目标数据文件: {missing}")

    service = WorkspaceService()
    await service.update_workspace(
        WORKSPACE_ID,
        USER_ID,
        WorkspaceUpdate(
            settings={
                "data_source": {
                    "type": "csv",
                    "csv": {"directory_path": str(DATA_ROOT)},
                }
            }
        ),
    )

    units = await service.list_units(WORKSPACE_ID, USER_ID) or []
    existing_symbols = {
        str(item.get("symbol") or "").strip().upper()
        for item in units
        if str(item.get("strategy_id") or "").strip() == STRATEGY_ID
    }
    legacy_units = [
        item for item in units if str(item.get("strategy_id") or "").strip() == LEGACY_STRATEGY_ID
    ]

    for item in legacy_units:
        symbol = str(item.get("symbol") or "").strip().upper()
        if symbol not in TARGET_SYMBOLS:
            continue
        await service.update_unit(
            WORKSPACE_ID,
            item["id"],
            USER_ID,
            StrategyUnitUpdate(
                strategy_id=STRATEGY_ID,
                strategy_name=f"DEMA双均线-{symbol}",
                params={"fast_period": 5, "slow_period": 21, "stake": 10},
                unit_settings={"initial_cash": 100000, "commission": 0.0002},
                data_config={
                    "range_type": "sample",
                    "sample_count": 1500,
                    "bar_count": 1500,
                    "use_end_date": True,
                },
            ),
        )
        existing_symbols.add(symbol)

    payload: list[StrategyUnitCreate] = []
    for symbol in TARGET_SYMBOLS:
        if symbol in existing_symbols:
            continue
        payload.append(
            StrategyUnitCreate(
                group_name=GROUP_NAME,
                strategy_id=STRATEGY_ID,
                strategy_name=f"DEMA双均线-{symbol}",
                symbol=symbol,
                symbol_name=symbol,
                timeframe="1d",
                timeframe_n=1,
                category="外汇",
                data_config={
                    "range_type": "sample",
                    "sample_count": 1500,
                    "bar_count": 1500,
                    "use_end_date": True,
                },
                unit_settings={
                    "initial_cash": 100000,
                    "commission": 0.0002,
                },
                params={
                    "fast_period": 5,
                    "slow_period": 21,
                    "stake": 10,
                },
                optimization_config={},
            )
        )

    if payload:
        await service.batch_create_units(WORKSPACE_ID, USER_ID, payload)

    async with async_session_maker() as session:
        result = await session.execute(
            select(StrategyUnit).where(
                StrategyUnit.workspace_id == WORKSPACE_ID,
                StrategyUnit.symbol.in_(TARGET_SYMBOLS),
            )
        )
        models = list(result.scalars().all())
        for unit in models:
            if str(unit.strategy_id or "").strip() != STRATEGY_ID:
                continue
            unit.run_status = "idle"
            unit.last_task_id = None
            unit.last_run_time = None
            unit.metrics_snapshot = {}
            unit.bar_count = None
        await session.commit()
        for unit in models:
            if str(unit.strategy_id or "").strip() != STRATEGY_ID:
                continue
            await session.refresh(unit)
            workspace_unit_runtime.sync_unit_runtime(unit, {"data_source": {"type": "csv", "csv": {"directory_path": str(DATA_ROOT)}}})
            runtime_dir = workspace_unit_runtime.unit_dir(WORKSPACE_ID, unit.id)
            (runtime_dir / "logs").mkdir(parents=True, exist_ok=True)

    final_units = await service.list_units(WORKSPACE_ID, USER_ID) or []
    dual_ma_units = [
        unit for unit in final_units if str(unit.get("strategy_id") or "").strip() == STRATEGY_ID
    ]
    print(f"workspace_id={WORKSPACE_ID}")
    print(f"configured_symbols={TARGET_SYMBOLS}")
    print(f"created_count={len(payload)}")
    print(f"dual_ma_total={len(dual_ma_units)}")
    for unit in dual_ma_units:
        runtime_dir = workspace_unit_runtime.unit_dir(WORKSPACE_ID, unit["id"])
        print(f"{unit['id']} {unit['symbol']} {runtime_dir}")


if __name__ == "__main__":
    asyncio.run(main())
