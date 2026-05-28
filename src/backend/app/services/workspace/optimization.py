"""Workspace optimization query operations.

Handles progress, results, cancel, apply-best-params, and artifact-metadata
lookups for unit-level optimization tasks. The heavy ``submit_unit_optimization``
and ``get_unit_optimization_result_payload`` remain on
:class:`app.services.workspace_service.WorkspaceService` because they depend on
``_build_optimization_trial_payload`` (150-line static method) and runtime-dir
sync logic.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, cast

from app.db.database import async_session_maker
from app.models.workspace import StrategyUnit
from app.schemas.workspace import ApplyBestParamsRequest
from app.services.optimization.execution_manager import get_optimization_execution_manager
from app.services.optimization.task_state import build_results_response
from app.services.param_optimization_service import (
    get_optimization_progress,
    get_optimization_results,
)
from app.services.workspace._helpers import build_optimization_artifact_metadata

logger = logging.getLogger(__name__)


def build_optimization_trial_payload(
    task_id: str,
    result_index: int,
    unit: StrategyUnit,
    log_result: dict[str, Any],
    created_at: str,
    result_entry: dict[str, Any],
) -> dict[str, Any]:
    from app.services.workspace_service import _normalize_unit_data_config

    equity_values = [float(v or 0.0) for v in (log_result.get("equity_curve") or [])]
    equity_dates = [str(v or "") for v in (log_result.get("equity_dates") or [])]
    cash_values = [float(v or 0.0) for v in (log_result.get("cash_curve") or [])]
    raw_trades = list(log_result.get("trades") or [])
    kline = cast(dict[str, Any], log_result.get("kline") or {})
    kline_dates = [str(v or "") for v in (kline.get("dates") or [])]
    kline_ohlc = list(kline.get("ohlc") or [])
    kline_volumes = list(kline.get("volumes") or [])
    log_indicators = cast(dict[str, list[float | None]], kline.get("indicators") or {})

    equity_curve: list[dict[str, Any]] = []
    drawdown_curve: list[dict[str, Any]] = []
    peak = 0.0
    for index, value in enumerate(equity_values):
        if value > peak:
            peak = value
        date = (equity_dates[index] if index < len(equity_dates) else "")[:10]
        cash = cash_values[index] if index < len(cash_values) else value
        position_value = value - cash
        drawdown = ((value - peak) / peak) if peak > 0 else 0.0
        equity_curve.append(
            {
                "date": date,
                "total_assets": round(value, 2),
                "cash": round(cash, 2),
                "position_value": round(position_value, 2),
            }
        )
        drawdown_curve.append(
            {
                "date": date,
                "drawdown": round(drawdown, 6),
                "peak": round(peak, 2),
                "trough": round(value, 2),
            }
        )

    klines: list[dict[str, Any]] = []
    kline_close_map: dict[str, float] = {}
    for index, date in enumerate(kline_dates):
        normalized_date = date[:10]
        ohlc = kline_ohlc[index] if index < len(kline_ohlc) else [0.0, 0.0, 0.0, 0.0]
        open_price = float(ohlc[0]) if len(ohlc) > 0 else 0.0
        close_price = float(ohlc[1]) if len(ohlc) > 1 else 0.0
        low_price = float(ohlc[2]) if len(ohlc) > 2 else 0.0
        high_price = float(ohlc[3]) if len(ohlc) > 3 else 0.0
        klines.append(
            {
                "date": normalized_date,
                "open": round(open_price, 4),
                "high": round(high_price, 4),
                "low": round(low_price, 4),
                "close": round(close_price, 4),
                "volume": kline_volumes[index] if index < len(kline_volumes) else 0,
            }
        )
        if normalized_date:
            kline_close_map[normalized_date] = round(close_price, 4)

    trades: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []
    symbol = str(unit.symbol or unit.symbol_name or unit.strategy_name or "Unknown")
    for index, trade in enumerate(raw_trades):
        trade_data = dict(trade or {})
        pnl = trade_data.get("pnl")
        if pnl is None:
            pnl = trade_data.get("pnlcomm")
        open_price = float(trade_data.get("price", 0) or 0)
        size = float(trade_data.get("size", 0) or 0)
        direction = str(trade_data.get("direction", "buy") or "buy")
        dtopen = str(trade_data.get("dtopen", "") or "")[:10]
        dtclose = str(trade_data.get("dtclose", trade_data.get("datetime", "")) or "")[:10]

        trade_payload = {
            "id": index + 1,
            "datetime": str(trade_data.get("datetime", dtclose) or dtclose)[:10],
            "dtopen": dtopen,
            "dtclose": dtclose,
            "symbol": symbol,
            "direction": direction,
            "price": open_price,
            "close_price": trade_data.get("close_price"),
            "size": size,
            "value": float(trade_data.get("value", 0) or 0),
            "commission": float(trade_data.get("commission", 0) or 0),
            "pnl": pnl,
            "barlen": trade_data.get("barlen"),
        }
        trades.append(trade_payload)

        is_long = direction == "buy"
        if dtopen:
            signals.append(
                {
                    "date": dtopen,
                    "type": "buy" if is_long else "sell",
                    "price": kline_close_map.get(dtopen, open_price),
                    "size": abs(size),
                }
            )
        if dtclose:
            signals.append(
                {
                    "date": dtclose,
                    "type": "sell" if is_long else "buy",
                    "price": kline_close_map.get(dtclose, open_price),
                    "size": abs(size),
                }
            )

    monthly_returns: dict[tuple[int, int], float] = {}
    if equity_dates and equity_values:
        month_start_value = equity_values[0]
        current_month: tuple[int, int] | None = None
        for date_text, value in zip(equity_dates, equity_values, strict=False):
            try:
                dt = datetime.strptime(str(date_text)[:10], "%Y-%m-%d")
            except ValueError:
                continue
            month_key = (dt.year, dt.month)
            if current_month != month_key:
                if current_month and month_start_value > 0:
                    monthly_returns[current_month] = round(
                        (value - month_start_value) / month_start_value,
                        6,
                    )
                month_start_value = value
                current_month = month_key
        if current_month and month_start_value > 0:
            monthly_returns[current_month] = round(
                (equity_values[-1] - month_start_value) / month_start_value,
                6,
            )

    data_config = _normalize_unit_data_config(unit.data_config)
    start_date = str(data_config.get("start_date") or (equity_dates[0] if equity_dates else ""))[
        :10
    ]
    end_date = str(data_config.get("end_date") or (equity_dates[-1] if equity_dates else ""))[:10]
    strategy_name = str(unit.strategy_name or unit.strategy_id or "Unknown")
    artifact_metadata = build_optimization_artifact_metadata(task_id, result_index, result_entry)

    return {
        "task_id": f"{task_id}:{result_index}",
        "strategy_name": strategy_name,
        "symbol": symbol,
        "start_date": start_date,
        "end_date": end_date,
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "trades": trades,
        "signals": signals,
        "klines": klines,
        "log_indicators": log_indicators,
        "monthly_returns": monthly_returns,
        "created_at": created_at,
        **artifact_metadata,
    }


async def get_unit_optimization_result_artifact_metadata(
    workspace_id: str,
    user_id: str,
    unit_id: str,
    result_index: int,
) -> dict[str, Any] | None:
    """Return artifact metadata for a specific optimization result row."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return None
        unit = await WorkspaceService._get_unit(session, workspace_id, unit_id)
        if unit is None or not unit.last_optimization_task_id:
            return None

        task_id = unit.last_optimization_task_id
        mgr = get_optimization_execution_manager()
        db_task = await mgr.get_task(task_id, user_id=user_id)
        if (
            not db_task
            or not db_task.results
            or result_index < 0
            or result_index >= len(db_task.results)
        ):
            return None

        result_entry = cast(dict[str, Any], db_task.results[result_index] or {})
        return build_optimization_artifact_metadata(task_id, result_index, result_entry)


async def get_unit_optimization_progress(
    workspace_id: str, user_id: str, unit_id: str
) -> dict[str, Any] | None:
    """Get optimization progress for a unit."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return None
        unit = await WorkspaceService._get_unit(session, workspace_id, unit_id)
        if unit is None or not unit.last_optimization_task_id:
            return None

        return get_optimization_progress(
            unit.last_optimization_task_id, user_id=user_id, use_db=True
        )


async def get_unit_optimization_results(
    workspace_id: str, user_id: str, unit_id: str
) -> dict[str, Any] | None:
    """Get optimization results for a unit, sorted by configured objective."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return None
        unit = await WorkspaceService._get_unit(session, workspace_id, unit_id)
        if unit is None or not unit.last_optimization_task_id:
            return None

        task_id = unit.last_optimization_task_id
        oc = unit.optimization_config or {}
        objective_key = oc.get("objective", "sharpe_max") or "sharpe_max"
        objective_map = {
            "sharpe_max": "sharpe_ratio",
            "max_return": "annual_return",
            "min_drawdown": "max_drawdown",
        }
        objective = objective_map.get(str(objective_key), str(objective_key))
        reverse_sort = objective != "max_drawdown"

        mgr = get_optimization_execution_manager()
        db_task = await mgr.get_task(task_id, user_id=user_id)
        if db_task and db_task.results is not None:
            task_dict = {
                "status": db_task.status,
                "strategy_id": db_task.strategy_id,
                "param_names": list((db_task.param_ranges or {}).keys()),
                "total": db_task.total,
                "completed": db_task.completed,
                "failed": db_task.failed,
                "results": db_task.results,
            }
            results_response = build_results_response(task_id, task_dict)
            rows = list(results_response.get("rows") or [])
            rows.sort(
                key=lambda row: row.get(objective, 999999 if not reverse_sort else -999999),
                reverse=reverse_sort,
            )
            results_response["rows"] = rows
            results_response["best"] = rows[0] if rows else None
            results_response["objective"] = objective
            return results_response

        results_response = get_optimization_results(task_id, user_id=user_id, use_db=False)
        if results_response:
            rows = list(results_response.get("rows") or [])
            rows.sort(
                key=lambda row: row.get(objective, 999999 if not reverse_sort else -999999),
                reverse=reverse_sort,
            )
            results_response["rows"] = rows
            results_response["best"] = rows[0] if rows else None
            results_response["objective"] = objective
        return results_response


async def cancel_unit_optimization(
    workspace_id: str, user_id: str, unit_id: str
) -> dict[str, Any] | None:
    """Cancel a running optimization task for a strategy unit."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return None
        unit = await WorkspaceService._get_unit(session, workspace_id, unit_id)
        if unit is None or not unit.last_optimization_task_id:
            return {"error": "No optimization task found for this unit"}

        task_id = unit.last_optimization_task_id
        mgr = get_optimization_execution_manager()
        cancelled = await mgr.set_cancelled(task_id, user_id=user_id)
        return {"task_id": task_id, "cancelled": cancelled}


async def apply_best_params(
    workspace_id: str, user_id: str, req: ApplyBestParamsRequest
) -> dict[str, Any] | None:
    """Apply best params from optimization result to a strategy unit."""
    from app.services.workspace_service import WorkspaceService

    async with async_session_maker() as session:
        ws = await WorkspaceService._load_workspace(
            session, workspace_id, user_id, load_units=False
        )
        if ws is None:
            return None
        unit = await WorkspaceService._get_unit(session, workspace_id, req.unit_id)
        if unit is None:
            return None

        mgr = get_optimization_execution_manager()
        db_task = await mgr.get_task(req.optimization_task_id, user_id=user_id)
        if not db_task or not db_task.results:
            return {"error": "Optimization results not found"}

        results = db_task.results
        if req.result_index >= len(results):
            return {"error": f"Result index {req.result_index} out of range"}

        best = results[req.result_index]
        best_params = best.get("params", {})

        current_params = unit.params or {}
        current_params.update(best_params)
        unit.params = current_params
        await session.commit()

        return {
            "unit_id": req.unit_id,
            "applied_params": best_params,
            "metrics": {k: v for k, v in best.items() if k != "params"},
        }


async def submit_unit_optimization(
    workspace_id: str,
    user_id: str,
    req: "UnitOptimizationRequest",
    load_workspace,
    get_unit,
) -> dict[str, Any] | None:
    """Submit optimization for a strategy unit."""
    from typing import cast

    from app.services.param_optimization_service import generate_param_grid

    from app.db.database import async_session_maker
    from app.models.workspace import StrategyUnit
    from app.services.workspace.config import _workspace_settings_dict, _write_json_file
    from app.services.workspace import units as workspace_unit_runtime_mod

    try:
        from app.services import workspace_unit_runtime
    except ImportError:
        workspace_unit_runtime = workspace_unit_runtime_mod

    from app.services.optimization.submission import submit_optimization
    from app.services.optimization.execution_manager import get_optimization_execution_manager
    from datetime import datetime, timezone

    async with async_session_maker() as session:
        ws = await load_workspace(session, workspace_id, user_id, load_units=False)
        if ws is None:
            return None
        unit = await get_unit(session, workspace_id, req.unit_id)
        if unit is None:
            return None

        param_ranges = {}
        for name, spec in req.param_ranges.items():
            param_ranges[name] = {
                "start": spec.start,
                "end": spec.end,
                "step": spec.step,
                "type": spec.type,
            }

        grid = generate_param_grid(param_ranges)
        if not grid:
            return {"error": "Parameter grid is empty"}

        strategy_id = unit.strategy_id or ""
        workspace_settings = cast(dict[str, Any], _workspace_settings_dict(ws))
        unit_runtime_dir = workspace_unit_runtime.sync_unit_runtime(unit, workspace_settings)

        mgr = get_optimization_execution_manager()
        db_task = await mgr.create_task(
            user_id=user_id,
            strategy_id=strategy_id,
            total=len(grid),
            param_ranges=param_ranges,
            n_workers=req.n_workers,
        )
        task_id = db_task.id
        artifact_root = unit_runtime_dir / "optimization_runs" / task_id
        artifact_root.mkdir(parents=True, exist_ok=True)
        _write_json_file(
            artifact_root / "manifest.json",
            {
                "task_id": task_id,
                "workspace_id": workspace_id,
                "unit_id": unit.id,
                "strategy_id": strategy_id,
                "param_names": list(param_ranges.keys()),
                "param_ranges": param_ranges,
                "n_workers": req.n_workers,
                "created_at": db_task.created_at.isoformat() if db_task.created_at else "",
            },
        )

        submit_optimization(
            strategy_id=strategy_id,
            param_ranges=param_ranges,
            n_workers=req.n_workers,
            task_id=task_id,
            persist_to_db=True,
            strategy_dir=str(unit_runtime_dir),
            artifact_root=str(artifact_root),
        )

        unit.last_optimization_task_id = task_id
        existing_oc = dict(unit.optimization_config or {})
        existing_oc.update(
            {
                "param_ranges": param_ranges,
                "n_workers": req.n_workers,
                "artifact_root": str(artifact_root),
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        unit.optimization_config = existing_oc
        await session.commit()

        return {
            "task_id": task_id,
            "unit_id": req.unit_id,
            "total_combinations": len(grid),
            "n_workers": req.n_workers,
        }
