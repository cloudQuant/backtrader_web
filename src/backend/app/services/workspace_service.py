"""
Workspace service.

Handles workspace and strategy unit CRUD, bulk operations,
and workspace-level run orchestration (Phase 3).
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import async_session_maker
from app.models.backtest import BacktestTask
from app.models.optimization import OptimizationTask
from app.models.workspace import StrategyUnit, Workspace
from app.schemas.backtest import BacktestRequest, TaskStatus
from app.schemas.workspace import (
    ApplyBestParamsRequest,
    GroupRenameRequest,
    StrategyUnitCreate,
    StrategyUnitUpdate,
    UnitOptimizationRequest,
    UnitRenameRequest,
    UnitStatusResponse,
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from app.services import workspace_unit_runtime
from app.services.fincore_metrics_helper import calculate_extended_metrics
from app.services.optimization_execution_manager import get_optimization_execution_manager
from app.services.optimization_task_state import (
    build_results_response,
    estimate_remaining_seconds,
    get_runtime_task,
)
from app.services.param_optimization_service import (
    get_optimization_progress,
    get_optimization_results,
    submit_optimization,
)

logger = logging.getLogger(__name__)

_DEFAULT_UNIT_START_DATE = datetime(2020, 1, 1, tzinfo=timezone.utc)
_ACTIVE_OPTIMIZATION_STATUSES = {"pending", "queued", "running"}
_TERMINAL_OPTIMIZATION_STATUSES = {
    TaskStatus.COMPLETED.value,
    TaskStatus.FAILED.value,
    TaskStatus.CANCELLED.value,
}


def _default_workspace_settings() -> dict[str, Any]:
    return {
        "data_source": {
            "type": "csv",
            "csv": {
                "directory_path": "",
                "delimiter": ",",
                "encoding": "utf-8",
                "has_header": True,
            },
            "mysql": {
                "host": "127.0.0.1",
                "port": 3306,
                "database": "",
                "username": "",
                "password": "",
                "table": "",
            },
            "postgresql": {
                "host": "127.0.0.1",
                "port": 5432,
                "database": "",
                "schema": "public",
                "username": "",
                "password": "",
                "table": "",
            },
            "mongodb": {
                "uri": "mongodb://127.0.0.1:27017",
                "database": "",
                "collection": "",
                "username": "",
                "password": "",
                "auth_source": "admin",
            },
        }
    }


def _normalize_workspace_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _default_workspace_settings()
    if not isinstance(settings, dict):
        return normalized

    for key, value in settings.items():
        if key != "data_source":
            normalized[key] = value

    data_source = settings.get("data_source")
    if isinstance(data_source, dict):
        merged_data_source = dict(normalized["data_source"])
        for key, value in data_source.items():
            if key in {"csv", "mysql", "postgresql", "mongodb"} and isinstance(value, dict):
                section = dict(merged_data_source[key])
                if key == "csv" and "directory_path" not in value and isinstance(value.get("file_path"), str):
                    section["directory_path"] = value["file_path"]
                for section_key, section_value in value.items():
                    if key == "csv" and section_key == "file_path":
                        continue
                    section[section_key] = section_value
                merged_data_source[key] = section
            else:
                merged_data_source[key] = value
        normalized["data_source"] = merged_data_source

    return normalized


def _aggregate_workspace_status(units: list[StrategyUnit]) -> str:
    """Compute workspace status from child unit statuses."""
    if not units:
        return "idle"
    statuses = {u.run_status for u in units}
    if statuses & {"running", "queued"}:
        return "running"
    if all(s == "completed" for s in statuses):
        return "completed"
    if "failed" in statuses and not (statuses & {"running", "queued"}):
        return "error"
    return "idle"


def _workspace_settings_dict(ws: Workspace) -> dict[str, Any]:
    raw_settings = ws.__dict__.get("settings")
    if isinstance(raw_settings, dict):
        return _normalize_workspace_settings(raw_settings)
    return _normalize_workspace_settings(None)


def _default_unit_start_date_iso() -> str:
    return _DEFAULT_UNIT_START_DATE.isoformat()


def _default_unit_end_date_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _normalize_unit_data_config(data_config: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(data_config or {})
    range_type = str(normalized.get("range_type") or "date").strip().lower()
    normalized["range_type"] = range_type if range_type in {"date", "sample"} else "date"
    if normalized["range_type"] == "date":
        if not str(normalized.get("start_date") or "").strip():
            normalized["start_date"] = _default_unit_start_date_iso()
        normalized["use_end_date"] = normalized.get("use_end_date") is not False
        if normalized["use_end_date"] and not str(normalized.get("end_date") or "").strip():
            normalized["end_date"] = _default_unit_end_date_iso()
        normalized.pop("sample_count", None)
        normalized.pop("bar_count", None)
    else:
        if normalized.get("sample_count") in (None, "", 0):
            normalized["sample_count"] = 1000
    return normalized


def _workspace_to_response(ws: Workspace) -> WorkspaceResponse:
    """Convert a Workspace ORM object to a WorkspaceResponse, including aggregated fields."""
    units = ws.strategy_units or []
    completed_count = sum(1 for u in units if u.run_status == "completed")
    return WorkspaceResponse(
        id=ws.id,
        user_id=ws.user_id,
        name=ws.name,
        description=ws.description,
        settings=_normalize_workspace_settings(ws.settings),
        unit_count=len(units),
        completed_count=completed_count,
        status=_aggregate_workspace_status(units),
        created_at=ws.created_at,
        updated_at=ws.updated_at,
    )


class WorkspaceService:
    """Service for workspace and strategy unit management."""

    @staticmethod
    def _requested_bar_count(unit: StrategyUnit) -> int | None:
        data_cfg = _normalize_unit_data_config(unit.data_config)
        value = data_cfg.get("bar_count")
        try:
            bar_count = int(value) if value is not None else 0
        except (TypeError, ValueError):
            return None
        return bar_count if bar_count > 0 else None

    @staticmethod
    async def _resolve_unit_log_dir(
        backtest_service: "BacktestService",  # noqa: F821
        task_id: str,
        user_id: str | None,
    ) -> Path | None:
        task = await backtest_service.task_manager.get_task(task_id, user_id=user_id)
        if not task or not task.log_dir:
            return None

        try:
            from app.api.analytics import _resolve_log_dir

            strategy_id = str(getattr(task, "strategy_id", "") or "").strip()
            if strategy_id:
                resolved = await _resolve_log_dir(task_id, strategy_id)
                if resolved and resolved.is_dir():
                    return resolved
        except Exception as exc:
            logger.debug("Failed to resolve unit log dir for task %s: %s", task_id, exc)

        persisted_log_dir = Path(task.log_dir)
        return persisted_log_dir if persisted_log_dir.is_dir() else None

    @staticmethod
    def _db_task_elapsed_seconds(task: BacktestTask | OptimizationTask | None) -> float | None:
        if task is None or task.created_at is None:
            return None
        end_time = task.updated_at
        if str(getattr(task, "status", "") or "") in {
            TaskStatus.RUNNING.value,
            "pending",
            "queued",
            "running",
        }:
            end_time = datetime.now(timezone.utc)
        if end_time is None:
            return None
        elapsed = (end_time - task.created_at).total_seconds()
        if elapsed < 0:
            return None
        return round(elapsed, 2)

    @staticmethod
    def _task_elapsed_seconds(task: BacktestTask | None) -> float | None:
        return WorkspaceService._db_task_elapsed_seconds(task)

    @staticmethod
    def _runtime_optimization_elapsed_seconds(task: dict[str, Any] | None) -> float | None:
        if not task:
            return None
        created_at = WorkspaceService._parse_runtime_datetime(task.get("created_at"))
        if created_at is None:
            return None
        status = str(task.get("status") or "")
        if not status or status in _ACTIVE_OPTIMIZATION_STATUSES:
            end_time = datetime.now(timezone.utc)
        else:
            end_time = WorkspaceService._parse_runtime_datetime(task.get("updated_at")) or created_at
        elapsed = (end_time - created_at).total_seconds()
        if elapsed < 0:
            return None
        return round(elapsed, 2)

    @staticmethod
    def _parse_runtime_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            resolved = datetime.fromisoformat(str(value))
        except ValueError:
            return None
        if resolved.tzinfo is None:
            resolved = resolved.replace(tzinfo=timezone.utc)
        return resolved

    @staticmethod
    def _build_runtime_optimization_progress(task: dict[str, Any] | None) -> dict[str, Any] | None:
        if not task:
            return None
        total_c = int(task.get("total") or 0)
        completed_c = int(task.get("completed") or 0) + int(task.get("failed") or 0)
        pct = round(completed_c / total_c * 100, 1) if total_c > 0 else 0
        elapsed_seconds = WorkspaceService._runtime_optimization_elapsed_seconds(task)
        status = str(task.get("status") or "")
        return {
            "opt_status": task.get("status"),
            "opt_total": total_c,
            "opt_completed": completed_c,
            "opt_progress": pct,
            "opt_elapsed_time": elapsed_seconds if elapsed_seconds is not None else 0.0,
            "opt_remaining_time": estimate_remaining_seconds(
                total=total_c,
                finished=completed_c,
                n_workers=int(task.get("n_workers") or 1),
                elapsed_time=elapsed_seconds,
                status=status,
                task=task,
            ),
        }

    @staticmethod
    def _build_db_optimization_progress(task: OptimizationTask | None) -> dict[str, Any] | None:
        if task is None:
            return None
        total_c = int(task.total or 0)
        completed_c = int(task.completed or 0) + int(task.failed or 0)
        pct = round(completed_c / total_c * 100, 1) if total_c > 0 else 0
        elapsed_seconds = WorkspaceService._db_task_elapsed_seconds(task)
        status = str(task.status or "")
        return {
            "opt_status": task.status,
            "opt_total": total_c,
            "opt_completed": completed_c,
            "opt_progress": pct,
            "opt_elapsed_time": elapsed_seconds if elapsed_seconds is not None else 0.0,
            "opt_remaining_time": estimate_remaining_seconds(
                total=total_c,
                finished=completed_c,
                n_workers=int(task.n_workers or 1),
                elapsed_time=elapsed_seconds,
                status=status,
            ),
        }

    @staticmethod
    def _resolve_optimization_progress(
        runtime_task: dict[str, Any] | None,
        db_task: OptimizationTask | None,
    ) -> dict[str, Any] | None:
        runtime_progress = WorkspaceService._build_runtime_optimization_progress(runtime_task)
        db_progress = WorkspaceService._build_db_optimization_progress(db_task)

        db_status = str((db_progress or {}).get("opt_status") or "")
        if db_progress and db_status in _TERMINAL_OPTIMIZATION_STATUSES:
            return db_progress

        runtime_status = str((runtime_progress or {}).get("opt_status") or "")
        if runtime_progress and runtime_status in _TERMINAL_OPTIMIZATION_STATUSES:
            return runtime_progress

        return runtime_progress or db_progress

    @staticmethod
    def _optimization_progress_response_to_opt_info(
        progress: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not progress:
            return None
        completed = int(progress.get("completed") or 0) + int(progress.get("failed") or 0)
        return {
            "opt_status": progress.get("status"),
            "opt_total": int(progress.get("total") or 0),
            "opt_completed": completed,
            "opt_progress": float(progress.get("progress") or 0.0),
            "opt_elapsed_time": float(progress.get("elapsed_time") or 0.0),
            "opt_remaining_time": float(progress.get("remaining_time") or 0.0),
        }

    @staticmethod
    async def _resolve_unit_bar_count(
        backtest_service: "BacktestService",  # noqa: F821
        task_id: str,
        user_id: str | None,
        bt_result: Any | None = None,
    ) -> int:
        resolved_log_dir = await WorkspaceService._resolve_unit_log_dir(
            backtest_service,
            task_id,
            user_id,
        )
        if resolved_log_dir:
            from app.services.log_parser_service import parse_log_dir

            log_result = parse_log_dir(resolved_log_dir)
            if log_result:
                kline = log_result.get("kline")
                if isinstance(kline, dict):
                    dates = kline.get("dates")
                    if isinstance(dates, list) and dates:
                        return len(dates)

        if bt_result is not None:
            equity_dates = getattr(bt_result, "equity_dates", None) or []
            if equity_dates:
                return len(equity_dates)
            equity_curve = getattr(bt_result, "equity_curve", None) or []
            if equity_curve:
                return len(equity_curve)

        return 0

    @staticmethod
    def _resolve_optimization_artifact_log_dir(result_entry: dict[str, Any]) -> Path | None:
        artifact_path = Path(str(result_entry.get("artifact_path") or "")).expanduser()
        if not artifact_path.is_dir():
            return None
        logs_dir = artifact_path / "logs"
        if logs_dir.is_dir():
            return logs_dir
        return artifact_path

    @staticmethod
    def _build_optimization_artifact_metadata(
        task_id: str,
        result_index: int,
        result_entry: dict[str, Any],
    ) -> dict[str, Any]:
        artifact_path = str(result_entry.get("artifact_path") or "")
        artifact_dir = Path(artifact_path).expanduser() if artifact_path else None
        manifest_path = artifact_dir.parent / "manifest.json" if artifact_dir else None
        summary_path = artifact_dir.parent / "summary.json" if artifact_dir else None
        is_success = bool(result_entry.get("success")) or bool(result_entry.get("metrics"))
        return {
            "artifact_path": artifact_path or None,
            "artifact_manifest_path": str(manifest_path) if manifest_path and manifest_path.is_file() else None,
            "artifact_summary_path": str(summary_path) if summary_path and summary_path.is_file() else None,
            "artifact_status": "success" if is_success else "failed",
            "artifact_error": result_entry.get("error"),
            "optimization_task_id": task_id,
            "optimization_result_index": result_index,
            "trial_index": result_entry.get("trial_index"),
        }

    @staticmethod
    def _build_optimization_trial_payload(
        task_id: str,
        result_index: int,
        unit: StrategyUnit,
        log_result: dict[str, Any],
        created_at: str,
        result_entry: dict[str, Any],
    ) -> dict[str, Any]:
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
        start_date = str(data_config.get("start_date") or (equity_dates[0] if equity_dates else ""))[:10]
        end_date = str(data_config.get("end_date") or (equity_dates[-1] if equity_dates else ""))[:10]
        strategy_name = str(unit.strategy_name or unit.strategy_id or "Unknown")
        artifact_metadata = WorkspaceService._build_optimization_artifact_metadata(
            task_id,
            result_index,
            result_entry,
        )

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
        self,
        workspace_id: str,
        user_id: str,
        unit_id: str,
        result_index: int,
    ) -> dict[str, Any] | None:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None
            unit = await self._get_unit(session, workspace_id, unit_id)
            if unit is None or not unit.last_optimization_task_id:
                return None

            task_id = unit.last_optimization_task_id
            mgr = get_optimization_execution_manager()
            db_task = await mgr.get_task(task_id, user_id=user_id)
            if not db_task or not db_task.results or result_index < 0 or result_index >= len(db_task.results):
                return None

            result_entry = cast(dict[str, Any], db_task.results[result_index] or {})
            return self._build_optimization_artifact_metadata(task_id, result_index, result_entry)

    async def get_unit_optimization_result_payload(
        self,
        workspace_id: str,
        user_id: str,
        unit_id: str,
        result_index: int,
    ) -> dict[str, Any] | None:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None
            unit = await self._get_unit(session, workspace_id, unit_id)
            if unit is None or not unit.last_optimization_task_id:
                return None

            task_id = unit.last_optimization_task_id
            mgr = get_optimization_execution_manager()
            db_task = await mgr.get_task(task_id, user_id=user_id)
            if not db_task or not db_task.results or result_index < 0 or result_index >= len(db_task.results):
                return None

            result_entry = cast(dict[str, Any], db_task.results[result_index] or {})
            log_dir = self._resolve_optimization_artifact_log_dir(result_entry)
            if log_dir is None:
                return None

            from app.services.log_parser_service import parse_log_dir

            strategy_root = log_dir.parent if log_dir.name == "logs" else log_dir
            log_result = parse_log_dir(log_dir, strategy_dir=strategy_root)
            if not log_result:
                return None

            created_at = db_task.created_at.isoformat() if db_task.created_at else ""
            return self._build_optimization_trial_payload(
                task_id,
                result_index,
                unit,
                log_result,
                created_at,
                result_entry,
            )

    async def reconcile_orphaned_run_statuses(self) -> int:
        async with async_session_maker() as session:
            result = await session.execute(
                select(StrategyUnit).where(StrategyUnit.run_status.in_(["queued", "running"]))
            )
            units = list(result.scalars().all())
            if not units:
                return 0

            task_ids = [str(unit.last_task_id) for unit in units if unit.last_task_id]
            task_by_id: dict[str, BacktestTask] = {}
            if task_ids:
                task_result = await session.execute(
                    select(BacktestTask).where(BacktestTask.id.in_(task_ids))
                )
                task_by_id = {str(task.id): task for task in task_result.scalars().all()}

            changed = 0
            for unit in units:
                last_task_id = str(unit.last_task_id or "").strip()
                if not last_task_id:
                    next_status = "idle"
                else:
                    task = task_by_id.get(last_task_id)
                    if task is None:
                        next_status = "failed"
                    else:
                        task_status = str(task.status)
                        if task_status == TaskStatus.COMPLETED.value:
                            next_status = "completed"
                        elif task_status == TaskStatus.CANCELLED.value:
                            next_status = "cancelled"
                        elif task_status == TaskStatus.FAILED.value:
                            next_status = "failed"
                        else:
                            continue

                if str(unit.run_status or "") != next_status:
                    unit.run_status = next_status
                    changed += 1

            if changed:
                await session.commit()
            return changed

    async def reconcile_completed_bar_counts(self) -> int:
        from app.services.backtest_service import BacktestService

        backtest_service = BacktestService()
        async with async_session_maker() as session:
            result = await session.execute(
                select(StrategyUnit).where(
                    StrategyUnit.run_status == "completed",
                    StrategyUnit.last_task_id.is_not(None),
                )
            )
            units = list(result.scalars().all())
            changed = 0
            for unit in units:
                unit_obj = cast(Any, unit)
                task_id = str(unit_obj.last_task_id or "").strip()
                if not task_id:
                    continue
                resolved_bar_count = await self._resolve_unit_bar_count(
                    backtest_service,
                    task_id,
                    None,
                )
                if resolved_bar_count > 0 and int(unit_obj.bar_count or 0) != resolved_bar_count:
                    unit_obj.bar_count = resolved_bar_count
                    changed += 1

            if changed:
                await session.commit()
            return changed

    # ------------------------------------------------------------------
    # Workspace CRUD
    # ------------------------------------------------------------------

    async def create_workspace(self, user_id: str, data: WorkspaceCreate) -> WorkspaceResponse:
        async with async_session_maker() as session:
            ws = Workspace(
                user_id=user_id,
                name=data.name,
                description=data.description,
                settings=_normalize_workspace_settings(data.settings),
            )
            session.add(ws)
            await session.commit()
            await session.refresh(ws, attribute_names=["strategy_units"])
            workspace_unit_runtime.ensure_workspace_dir(ws.id)
            return _workspace_to_response(ws)

    async def get_workspace(self, workspace_id: str, user_id: str) -> WorkspaceResponse | None:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id)
            if ws is None:
                return None
            return _workspace_to_response(ws)

    async def list_workspaces(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[int, list[WorkspaceResponse]]:
        async with async_session_maker() as session:
            # Count
            count_q = select(func.count()).select_from(Workspace).where(Workspace.user_id == user_id)
            total = (await session.execute(count_q)).scalar() or 0

            # Fetch with units eagerly loaded
            q = (
                select(Workspace)
                .where(Workspace.user_id == user_id)
                .options(selectinload(Workspace.strategy_units))
                .order_by(Workspace.updated_at.desc())
                .offset(skip)
                .limit(limit)
            )
            result = await session.execute(q)
            workspaces = list(result.scalars().unique().all())
            return total, [_workspace_to_response(ws) for ws in workspaces]

    async def update_workspace(
        self, workspace_id: str, user_id: str, data: WorkspaceUpdate
    ) -> WorkspaceResponse | None:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id)
            if ws is None:
                return None
            update_data = data.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                if key == "settings" and isinstance(value, dict):
                    existing = _normalize_workspace_settings(ws.settings)
                    for settings_key, settings_value in value.items():
                        if settings_key != "data_source":
                            existing[settings_key] = settings_value
                    if isinstance(value.get("data_source"), dict):
                        merged_data_source = dict(existing.get("data_source") or {})
                        for source_key, source_value in value["data_source"].items():
                            if source_key in {"csv", "mysql", "postgresql", "mongodb"} and isinstance(source_value, dict):
                                current_section = dict(merged_data_source.get(source_key) or {})
                                current_section.update(source_value)
                                merged_data_source[source_key] = current_section
                            else:
                                merged_data_source[source_key] = source_value
                        existing["data_source"] = merged_data_source
                    ws.settings = existing
                else:
                    setattr(ws, key, value)
            await session.commit()
            await session.refresh(ws, attribute_names=["strategy_units"])
            for unit in ws.strategy_units or []:
                workspace_unit_runtime.sync_unit_runtime(unit, ws.settings or {})
            return _workspace_to_response(ws)

    async def delete_workspace(self, workspace_id: str, user_id: str) -> bool:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return False
            await session.delete(ws)
            await session.commit()
            workspace_unit_runtime.remove_workspace_dir(workspace_id)
            return True

    # ------------------------------------------------------------------
    # Strategy Unit CRUD
    # ------------------------------------------------------------------

    async def create_unit(
        self, workspace_id: str, user_id: str, data: StrategyUnitCreate
    ) -> dict[str, Any] | None:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None

            # Determine next sort_order
            max_order_q = (
                select(func.coalesce(func.max(StrategyUnit.sort_order), -1))
                .where(StrategyUnit.workspace_id == workspace_id)
            )
            max_order = (await session.execute(max_order_q)).scalar() or 0

            unit = StrategyUnit(
                workspace_id=workspace_id,
                group_name=data.group_name,
                strategy_id=data.strategy_id,
                strategy_name=data.strategy_name,
                symbol=data.symbol,
                symbol_name=data.symbol_name,
                timeframe=data.timeframe,
                timeframe_n=data.timeframe_n,
                category=data.category,
                sort_order=max_order + 1,
                data_config=_normalize_unit_data_config(data.data_config),
                unit_settings=data.unit_settings,
                params=data.params,
                optimization_config=data.optimization_config,
            )
            session.add(unit)
            await session.commit()
            await session.refresh(unit)
            workspace_unit_runtime.sync_unit_runtime(unit, ws.settings or {})
            return self._unit_to_dict(unit)

    async def batch_create_units(
        self, workspace_id: str, user_id: str, units_data: list[StrategyUnitCreate]
    ) -> list[dict[str, Any]] | None:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None

            max_order_q = (
                select(func.coalesce(func.max(StrategyUnit.sort_order), -1))
                .where(StrategyUnit.workspace_id == workspace_id)
            )
            max_order = (await session.execute(max_order_q)).scalar() or 0

            created = []
            for i, data in enumerate(units_data):
                unit = StrategyUnit(
                    workspace_id=workspace_id,
                    group_name=data.group_name,
                    strategy_id=data.strategy_id,
                    strategy_name=data.strategy_name,
                    symbol=data.symbol,
                    symbol_name=data.symbol_name,
                    timeframe=data.timeframe,
                    timeframe_n=data.timeframe_n,
                    category=data.category,
                    sort_order=max_order + 1 + i,
                    data_config=_normalize_unit_data_config(data.data_config),
                    unit_settings=data.unit_settings,
                    params=data.params,
                    optimization_config=data.optimization_config,
                )
                session.add(unit)
                created.append(unit)

            await session.commit()
            for u in created:
                await session.refresh(u)
                workspace_unit_runtime.sync_unit_runtime(u, ws.settings or {})
            return [self._unit_to_dict(u) for u in created]

    async def list_units(
        self, workspace_id: str, user_id: str
    ) -> list[dict[str, Any]] | None:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None

            q = (
                select(StrategyUnit)
                .where(StrategyUnit.workspace_id == workspace_id)
                .order_by(StrategyUnit.sort_order)
            )
            result = await session.execute(q)
            units = list(result.scalars().all())

            task_ids = [str(cast(Any, unit).last_task_id) for unit in units if cast(Any, unit).last_task_id]
            task_by_id: dict[str, BacktestTask] = {}
            if task_ids:
                task_result = await session.execute(
                    select(BacktestTask).where(BacktestTask.id.in_(task_ids))
                )
                task_by_id = {str(task.id): task for task in task_result.scalars().all()}

            changed = False
            backtest_service = None
            for unit in units:
                unit_obj = cast(Any, unit)
                last_task_id = str(unit_obj.last_task_id or "").strip()
                if not last_task_id:
                    continue

                task = task_by_id.get(last_task_id)
                elapsed_seconds = self._task_elapsed_seconds(task)
                if elapsed_seconds is not None and unit_obj.last_run_time != elapsed_seconds:
                    unit_obj.last_run_time = elapsed_seconds
                    changed = True

                if str(unit_obj.run_status or "") != "completed":
                    continue

                if backtest_service is None:
                    from app.services.backtest_service import BacktestService

                    backtest_service = BacktestService()

                resolved_bar_count = await self._resolve_unit_bar_count(
                    backtest_service,
                    last_task_id,
                    user_id,
                )
                if resolved_bar_count > 0 and int(unit_obj.bar_count or 0) != resolved_bar_count:
                    unit_obj.bar_count = resolved_bar_count
                    changed = True

            if changed:
                await session.commit()

            opt_progress_map: dict[str, dict[str, Any]] = {}
            opt_task_ids = {
                str(cast(Any, u).last_optimization_task_id)
                for u in units
                if cast(Any, u).last_optimization_task_id
            }
            if opt_task_ids:
                for tid in opt_task_ids:
                    try:
                        progress = get_optimization_progress(tid, user_id=user_id, use_db=True)
                        opt_info = self._optimization_progress_response_to_opt_info(progress)
                        if opt_info:
                            opt_progress_map[tid] = opt_info
                    except Exception:
                        pass

            return [
                self._unit_to_dict(
                    u,
                    opt_progress_map.get(
                        str(cast(Any, u).last_optimization_task_id),
                        {},
                    )
                    if cast(Any, u).last_optimization_task_id
                    else {},
                )
                for u in units
            ]

    async def get_unit(
        self, workspace_id: str, unit_id: str, user_id: str
    ) -> dict[str, Any] | None:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None
            unit = await self._get_unit(session, workspace_id, unit_id)
            if unit is None:
                return None
            return self._unit_to_dict(unit)

    async def update_unit(
        self, workspace_id: str, unit_id: str, user_id: str, data: StrategyUnitUpdate
    ) -> dict[str, Any] | None:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None
            unit = await self._get_unit(session, workspace_id, unit_id)
            if unit is None:
                return None
            update_data = data.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                if key == "data_config":
                    value = _normalize_unit_data_config(cast(dict[str, Any] | None, value))
                setattr(unit, key, value)
            await session.commit()
            await session.refresh(unit)
            workspace_unit_runtime.sync_unit_runtime(unit, ws.settings or {})
            return self._unit_to_dict(unit)

    async def delete_unit(
        self, workspace_id: str, unit_id: str, user_id: str
    ) -> bool:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return False
            unit = await self._get_unit(session, workspace_id, unit_id)
            if unit is None:
                return False
            await session.delete(unit)
            await session.commit()
            workspace_unit_runtime.remove_unit_dir(workspace_id, unit_id)
            return True

    async def bulk_delete_units(
        self, workspace_id: str, user_id: str, unit_ids: list[str]
    ) -> int:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return 0
            from sqlalchemy import delete as sa_delete

            result = await session.execute(
                sa_delete(StrategyUnit).where(
                    StrategyUnit.workspace_id == workspace_id,
                    StrategyUnit.id.in_(unit_ids),
                )
            )
            await session.commit()
            for unit_id in unit_ids:
                workspace_unit_runtime.remove_unit_dir(workspace_id, unit_id)
            return result.rowcount or 0

    # ------------------------------------------------------------------
    # Reorder
    # ------------------------------------------------------------------

    async def reorder_units(
        self, workspace_id: str, user_id: str, unit_ids: list[str]
    ) -> bool:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return False
            for idx, uid in enumerate(unit_ids):
                unit = await self._get_unit(session, workspace_id, uid)
                if unit:
                    unit.sort_order = idx
            await session.commit()
            return True

    # ------------------------------------------------------------------
    # Group rename / Unit rename
    # ------------------------------------------------------------------

    async def rename_group(
        self, workspace_id: str, user_id: str, req: GroupRenameRequest
    ) -> bool:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return False

            q = (
                select(StrategyUnit)
                .where(
                    StrategyUnit.workspace_id == workspace_id,
                    StrategyUnit.id.in_(req.unit_ids),
                )
            )
            result = await session.execute(q)
            units = list(result.scalars().all())

            for unit in units:
                unit.group_name = self._compute_rename(unit, req.mode, req.value, req.search, req.replace)

            await session.commit()
            return True

    async def rename_unit(
        self, workspace_id: str, user_id: str, req: UnitRenameRequest
    ) -> bool:
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return False
            unit = await self._get_unit(session, workspace_id, req.unit_id)
            if unit is None:
                return False
            unit.strategy_name = self._compute_rename(
                unit, req.mode, req.value, req.search, req.replace
            )
            await session.commit()
            return True

    # ------------------------------------------------------------------
    # Run orchestration (Phase 3)
    # ------------------------------------------------------------------

    async def run_units(
        self, workspace_id: str, user_id: str, unit_ids: list[str], parallel: bool = False
    ) -> list[dict[str, Any]]:
        """Run backtest for selected strategy units.

        Delegates to the existing BacktestService for each unit.
        Sequential by default; parallel if requested.

        Returns list of {unit_id, task_id, status} dicts.
        """
        from app.services.backtest_service import BacktestService

        backtest_service = BacktestService()
        results: list[dict[str, Any]] = []

        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return []

            q = (
                select(StrategyUnit)
                .where(
                    StrategyUnit.workspace_id == workspace_id,
                    StrategyUnit.id.in_(unit_ids),
                )
            )
            db_result = await session.execute(q)
            units = list(db_result.scalars().all())

            if not units:
                return []

            # Mark all as queued
            for unit in units:
                unit.run_status = "queued"
            await session.commit()

            # Submit backtest for each unit, write back task_id immediately
            async def _submit_single(unit: StrategyUnit) -> dict[str, Any]:
                try:
                    workspace_settings = cast(dict[str, Any], _workspace_settings_dict(ws))
                    workspace_unit_runtime.sync_unit_runtime(unit, workspace_settings)
                    bt_request = self._build_backtest_request(unit)
                    response = None
                    deadline = time.monotonic() + 1800
                    while response is None:
                        try:
                            response = await backtest_service.run_backtest(user_id, bt_request)
                        except ValueError as exc:
                            if "concurrent task limit" not in str(exc).lower():
                                raise
                            if time.monotonic() >= deadline:
                                raise TimeoutError(
                                    "Timed out waiting for an available backtest execution slot"
                                ) from exc
                            await asyncio.sleep(2)
                    task_id = response.task_id

                    # Immediately write task_id and set running (Bug-2 fix)
                    async with async_session_maker() as s2:
                        u = await self._get_unit(s2, workspace_id, unit.id)
                        if u:
                            u.last_task_id = task_id
                            u.run_status = "running"
                            await s2.commit()

                    return {"unit_id": unit.id, "task_id": task_id, "status": "running"}

                except Exception as e:
                    logger.error("Unit %s submit failed: %s", unit.id, e)
                    async with async_session_maker() as s_err:
                        u_err = await self._get_unit(s_err, workspace_id, unit.id)
                        if u_err:
                            u_err.run_status = "failed"
                            u_err.run_count = (u_err.run_count or 0) + 1
                            await s_err.commit()
                    return {"unit_id": unit.id, "task_id": None, "status": "failed", "error": str(e)}

            if parallel:
                results = list(await asyncio.gather(*[_submit_single(u) for u in units]))
            else:
                for unit in units:
                    results.append(await _submit_single(unit))

        # Fire-and-forget background polling for completion (Bug-1 fix)
        submitted = [(r["unit_id"], r["task_id"]) for r in results if r.get("task_id")]
        if submitted:
            asyncio.create_task(
                self._background_poll_units(
                    workspace_id, user_id, submitted, backtest_service
                )
            )

        return results

    async def stop_units(
        self, workspace_id: str, user_id: str, unit_ids: list[str]
    ) -> list[dict[str, Any]]:
        """Stop running units by cancelling their associated backtest tasks."""
        from app.services.backtest_service import BacktestService

        backtest_service = BacktestService()
        results: list[dict[str, Any]] = []

        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return []

            q = (
                select(StrategyUnit)
                .where(
                    StrategyUnit.workspace_id == workspace_id,
                    StrategyUnit.id.in_(unit_ids),
                    StrategyUnit.run_status.in_(["running", "queued"]),
                )
            )
            db_result = await session.execute(q)
            units = list(db_result.scalars().all())

            for unit in units:
                cancelled = False
                if unit.last_task_id:
                    cancelled = await backtest_service.cancel_task(unit.last_task_id, user_id)
                unit.run_status = "cancelled" if cancelled else "idle"
                results.append({"unit_id": unit.id, "cancelled": cancelled})

            await session.commit()

        return results

    async def get_units_status(
        self, workspace_id: str, user_id: str
    ) -> list[UnitStatusResponse] | None:
        """Get run status of all units (polling endpoint)."""
        from app.services.backtest_service import BacktestService

        backtest_service = BacktestService()

        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None

            q = (
                select(StrategyUnit)
                .where(StrategyUnit.workspace_id == workspace_id)
                .order_by(StrategyUnit.sort_order)
            )
            result = await session.execute(q)
            units = list(result.scalars().all())

            task_ids = [str(cast(Any, unit).last_task_id) for unit in units if cast(Any, unit).last_task_id]
            task_by_id: dict[str, BacktestTask] = {}
            if task_ids:
                task_result = await session.execute(
                    select(BacktestTask).where(BacktestTask.id.in_(task_ids))
                )
                task_by_id = {str(task.id): task for task in task_result.scalars().all()}

            changed = False
            for unit in units:
                unit_obj = cast(Any, unit)
                metrics_snapshot = cast(dict[str, Any], unit_obj.metrics_snapshot or {})
                last_task_id = str(unit_obj.last_task_id or "").strip()
                run_status = str(unit_obj.run_status or "")
                bar_count = int(unit_obj.bar_count or 0)
                task = task_by_id.get(last_task_id) if last_task_id else None
                if task is not None:
                    elapsed_seconds = self._task_elapsed_seconds(task)
                    if elapsed_seconds is not None and unit_obj.last_run_time != elapsed_seconds:
                        unit_obj.last_run_time = elapsed_seconds
                if run_status in {"queued", "running"}:
                    if not last_task_id:
                        unit_obj.run_status = "idle"
                        run_status = "idle"
                        changed = True
                    else:
                        task_status = await backtest_service.get_task_status(last_task_id, user_id)
                        if task_status == TaskStatus.COMPLETED:
                            unit_obj.run_status = "completed"
                            run_status = "completed"
                            changed = True
                        elif task_status == TaskStatus.CANCELLED:
                            unit_obj.run_status = "cancelled"
                            run_status = "cancelled"
                            changed = True
                        elif task_status == TaskStatus.FAILED or task_status is None:
                            unit_obj.run_status = "failed"
                            run_status = "failed"
                            changed = True
                if (
                    run_status == "completed"
                    and last_task_id
                    and (
                        bar_count == 0
                        or not metrics_snapshot.get("total_trades")
                    )
                ):
                    bt_result = await backtest_service.get_result(last_task_id, user_id)
                    if bt_result and (bt_result.equity_curve or bt_result.trades):
                        log_data = {
                            "equity_curve": bt_result.equity_curve or [],
                            "equity_dates": bt_result.equity_dates or [],
                            "trades": [
                                t.model_dump() if hasattr(t, "model_dump") else t
                                for t in (bt_result.trades or [])
                            ],
                        }
                        try:
                            metrics = calculate_extended_metrics(log_data)
                            unit_obj.metrics_snapshot = metrics
                        except Exception:
                            unit_obj.metrics_snapshot = {
                                "total_return": bt_result.total_return,
                                "annual_return": bt_result.annual_return,
                                "sharpe_ratio": bt_result.sharpe_ratio,
                                "max_drawdown": bt_result.max_drawdown,
                                "win_rate": bt_result.win_rate,
                                "total_trades": bt_result.total_trades,
                                "profitable_trades": bt_result.profitable_trades,
                                "losing_trades": bt_result.losing_trades,
                                "initial_cash": 100000.0,
                                "final_value": (bt_result.equity_curve or [100000.0])[-1]
                                if (bt_result.equity_curve or [])
                                else 100000.0,
                            }
                        unit_obj.bar_count = await self._resolve_unit_bar_count(
                            backtest_service,
                            last_task_id,
                            user_id,
                            bt_result,
                        )
                        changed = True

            if changed:
                await session.commit()

            # Collect optimization progress for units with active tasks
            opt_progress_map: dict[str, dict[str, Any]] = {}
            opt_task_ids = {
                str(cast(Any, u).last_optimization_task_id)
                for u in units
                if cast(Any, u).last_optimization_task_id
            }
            if opt_task_ids:
                for tid in opt_task_ids:
                    try:
                        progress = get_optimization_progress(tid, user_id=user_id, use_db=True)
                        opt_info = self._optimization_progress_response_to_opt_info(progress)
                        if opt_info:
                            opt_progress_map[tid] = opt_info
                    except Exception:
                        pass

            responses: list[UnitStatusResponse] = []
            for u in units:
                u_obj = cast(Any, u)
                opt_tid = str(u_obj.last_optimization_task_id) if u_obj.last_optimization_task_id else None
                opt_info = opt_progress_map.get(opt_tid, {}) if opt_tid else {}
                responses.append(
                    UnitStatusResponse(
                        id=str(u_obj.id),
                        run_status=str(u_obj.run_status or "idle"),
                        last_task_id=str(u_obj.last_task_id) if u_obj.last_task_id else None,
                        metrics_snapshot=cast(dict[str, Any], u_obj.metrics_snapshot or {}),
                        run_count=int(u_obj.run_count or 0),
                        last_run_time=(
                            float(u_obj.last_run_time)
                            if u_obj.last_run_time is not None
                            else None
                        ),
                        bar_count=(
                            int(u_obj.bar_count)
                            if u_obj.bar_count is not None
                            else None
                        ),
                        opt_status=opt_info.get("opt_status"),
                        opt_total=opt_info.get("opt_total"),
                        opt_completed=opt_info.get("opt_completed"),
                        opt_progress=opt_info.get("opt_progress"),
                        opt_elapsed_time=opt_info.get("opt_elapsed_time"),
                        opt_remaining_time=opt_info.get("opt_remaining_time"),
                    )
                )
            return responses

    # ------------------------------------------------------------------
    # Optimization orchestration (Phase 4)
    # ------------------------------------------------------------------

    async def submit_unit_optimization(
        self, workspace_id: str, user_id: str, req: UnitOptimizationRequest
    ) -> dict[str, Any] | None:
        """Submit optimization for a strategy unit. Delegates to existing optimization service."""
        from app.services.param_optimization_service import generate_param_grid

        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None
            unit = await self._get_unit(session, workspace_id, req.unit_id)
            if unit is None:
                return None

            # Build param_ranges dict
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

            # Sync unit runtime dir so optimization uses unit's symbol/data config
            workspace_settings = cast(dict[str, Any], _workspace_settings_dict(ws))
            unit_runtime_dir = workspace_unit_runtime.sync_unit_runtime(
                unit, workspace_settings
            )

            # Create persisted task in DB
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

            # Update unit with optimization task id — merge into existing config
            unit.last_optimization_task_id = task_id
            existing_oc = dict(unit.optimization_config or {})
            existing_oc.update({
                "param_ranges": param_ranges,
                "n_workers": req.n_workers,
                "artifact_root": str(artifact_root),
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            })
            unit.optimization_config = existing_oc
            await session.commit()

            return {
                "task_id": task_id,
                "unit_id": req.unit_id,
                "total_combinations": len(grid),
                "n_workers": req.n_workers,
            }

    async def get_unit_optimization_progress(
        self, workspace_id: str, user_id: str, unit_id: str
    ) -> dict[str, Any] | None:
        """Get optimization progress for a unit."""
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None
            unit = await self._get_unit(session, workspace_id, unit_id)
            if unit is None or not unit.last_optimization_task_id:
                return None

            progress = get_optimization_progress(
                unit.last_optimization_task_id, user_id=user_id, use_db=True
            )
            return progress

    async def get_unit_optimization_results(
        self, workspace_id: str, user_id: str, unit_id: str
    ) -> dict[str, Any] | None:
        """Get optimization results for a unit.

        The results are sorted by the unit's configured ``objective``
        (from ``optimization_config.objective``), defaulting to
        ``annual_return`` if not set.
        """
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None
            unit = await self._get_unit(session, workspace_id, unit_id)
            if unit is None or not unit.last_optimization_task_id:
                return None

            task_id = unit.last_optimization_task_id
            # Read user-configured objective from optimization_config
            oc = unit.optimization_config or {}
            objective_key = oc.get("objective", "sharpe_max") or "sharpe_max"
            objective_map = {
                "sharpe_max": "sharpe_ratio",
                "max_return": "annual_return",
                "min_drawdown": "max_drawdown",
            }
            objective = objective_map.get(str(objective_key), str(objective_key))
            reverse_sort = objective != "max_drawdown"

            # Try DB first
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
        self, workspace_id: str, user_id: str, unit_id: str
    ) -> dict[str, Any] | None:
        """Cancel a running optimization task for a strategy unit."""
        from app.services.optimization_execution_manager import get_optimization_execution_manager

        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None
            unit = await self._get_unit(session, workspace_id, unit_id)
            if unit is None or not unit.last_optimization_task_id:
                return {"error": "No optimization task found for this unit"}

            task_id = unit.last_optimization_task_id
            mgr = get_optimization_execution_manager()
            cancelled = await mgr.set_cancelled(task_id, user_id=user_id)
            return {"task_id": task_id, "cancelled": cancelled}

    async def apply_best_params(
        self, workspace_id: str, user_id: str, req: ApplyBestParamsRequest
    ) -> dict[str, Any] | None:
        """Apply best params from optimization result to a strategy unit."""
        from app.services.optimization_execution_manager import get_optimization_execution_manager

        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None
            unit = await self._get_unit(session, workspace_id, req.unit_id)
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

            # Merge into unit params
            current_params = unit.params or {}
            current_params.update(best_params)
            unit.params = current_params
            await session.commit()

            return {
                "unit_id": req.unit_id,
                "applied_params": best_params,
                "metrics": {k: v for k, v in best.items() if k != "params"},
            }

    # ------------------------------------------------------------------
    # Combined report (Phase 5)
    # ------------------------------------------------------------------

    async def get_workspace_report(
        self,
        workspace_id: str,
        user_id: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        max_cash: float | None = None,
        calc_method: str = "simple",
        annual_days: int = 252,
        weight_mode: str = "equal",
        weights: dict[str, float] | None = None,
    ) -> dict[str, Any] | None:
        """Generate a combined report aggregating metrics across all units.

        Accepts optional config parameters (Bug-10 fix) so front-end settings
        actually influence the calculation.
        """
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=True)
            if ws is None:
                return None

            units = ws.strategy_units or []

            # --- Filter by date range (Bug-6 fix) ---
            def _unit_in_range(u: StrategyUnit) -> bool:
                """Return True if unit's data period overlaps the requested range."""
                dc = u.data_config or {}
                u_start = dc.get("start_date", "")
                u_end = dc.get("end_date", "")
                if start_date and u_end and u_end < start_date:
                    return False
                if end_date and u_start and u_start > end_date:
                    return False
                return True

            filtered_units = [u for u in units if _unit_in_range(u)]
            completed_units = [u for u in filtered_units if u.metrics_snapshot]

            # Extended metric keys for Iteration 124 report columns
            _ext_keys = [
                "total_return", "annual_return", "sharpe_ratio", "max_drawdown",
                "win_rate", "total_trades", "profitable_trades", "losing_trades",
                "initial_cash", "final_value", "net_value", "net_profit",
                "max_leverage", "max_market_value", "max_drawdown_value",
                "adjusted_return_risk", "avg_profit", "avg_profit_rate",
                "total_win_amount", "total_loss_amount", "profit_loss_ratio",
                "profit_factor", "profit_rate_factor", "profit_loss_rate_ratio",
                "odds", "daily_avg_return", "daily_max_loss", "daily_max_profit",
                "weekly_avg_return", "weekly_max_loss", "weekly_max_profit",
                "monthly_avg_return", "monthly_max_loss", "monthly_max_profit",
                "trading_cost", "trading_days",
            ]

            # --- Build weight map (Bug-8 fix) ---
            # If weight_mode == "custom" but no explicit weights, auto-generate
            # from each unit's initial_cash proportion.
            _weights = weights or {}
            if weight_mode == "custom" and not _weights and completed_units:
                total_cash = sum(
                    (u.metrics_snapshot or {}).get("initial_cash", 0)
                    for u in completed_units
                )
                if total_cash > 0:
                    _weights = {
                        u.id: (u.metrics_snapshot or {}).get("initial_cash", 0) / total_cash
                        for u in completed_units
                    }

            # --- Helper: recalculate annual_return using provided annual_days
            #     and calc_method (Bug-7 fix) ---
            def _recalc_annual(m: dict[str, Any]) -> float | None:
                """Recalculate annual_return from total_return + trading_days."""
                tr = m.get("total_return")
                td = m.get("trading_days")
                if tr is None or not td or td <= 0:
                    return m.get("annual_return")
                if calc_method == "compound":
                    # compound: (1 + total_return)^(annual_days/trading_days) - 1
                    try:
                        return round(((1 + tr) ** (annual_days / td) - 1), 6)
                    except (OverflowError, ValueError):
                        return m.get("annual_return")
                else:
                    # simple: total_return * (annual_days / trading_days)
                    return round(tr * (annual_days / td), 6)

            # Per-unit metrics rows
            rows: list[dict[str, Any]] = []
            for u in filtered_units:
                m = u.metrics_snapshot or {}
                dc = u.data_config or {}
                row: dict[str, Any] = {
                    "id": u.id,
                    "strategy_name": u.strategy_name or u.strategy_id or "",
                    "symbol": u.symbol or "",
                    "symbol_name": u.symbol_name or "",
                    "timeframe": u.timeframe or "",
                    "group_name": u.group_name or "",
                    "category": u.category or "",
                    "run_status": u.run_status or "idle",
                    "run_count": u.run_count or 0,
                    "last_run_time": u.last_run_time,
                    "last_task_id": u.last_task_id,
                    "start_date": dc.get("start_date"),
                    "data_source": f"{u.symbol or ''}_{u.timeframe or ''}",
                }

                # Apply max_cash override
                if max_cash is not None and m:
                    row["initial_cash"] = max_cash
                else:
                    row["initial_cash"] = m.get("initial_cash")

                for k in _ext_keys:
                    if k == "initial_cash":
                        continue  # already handled above
                    row[k] = m.get(k)

                # Recalculate annual_return with user config
                if m:
                    row["annual_return"] = _recalc_annual(m)

                rows.append(row)

            # Weighted average helper
            def _weighted_avg(key: str) -> float | None:
                vals: list[tuple[float, float]] = []
                for u in completed_units:
                    m = u.metrics_snapshot or {}
                    if key == "annual_return":
                        v = _recalc_annual(m)
                    else:
                        v = m.get(key)
                    if v is None:
                        continue
                    w = _weights.get(u.id, 1.0) if weight_mode == "custom" and _weights else 1.0
                    vals.append((v, w))
                if not vals:
                    return None
                total_w = sum(w for _, w in vals)
                if total_w == 0:
                    return None
                return round(sum(v * w for v, w in vals) / total_w, 4)

            def _safe_sum(key: str) -> int | None:
                vals = [m.get(key) for u in completed_units if (m := u.metrics_snapshot) and m.get(key) is not None]
                return sum(vals) if vals else None

            summary = {
                "total_units": len(units),
                "completed_units": len(completed_units),
                "avg_total_return": _weighted_avg("total_return"),
                "avg_annual_return": _weighted_avg("annual_return"),
                "avg_sharpe_ratio": _weighted_avg("sharpe_ratio"),
                "avg_max_drawdown": _weighted_avg("max_drawdown"),
                "avg_win_rate": _weighted_avg("win_rate"),
                "total_trades": _safe_sum("total_trades"),
                "best_return_unit": max(
                    completed_units,
                    key=lambda u: (u.metrics_snapshot or {}).get("total_return", float("-inf")),
                    default=None,
                ),
                "worst_drawdown_unit": max(
                    completed_units,
                    key=lambda u: abs((u.metrics_snapshot or {}).get("max_drawdown", 0)),
                    default=None,
                ),
                # Echo config so frontend knows what was used
                "config": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "max_cash": max_cash,
                    "calc_method": calc_method,
                    "annual_days": annual_days,
                    "weight_mode": weight_mode,
                },
            }
            # Serialize unit references in summary
            for key in ("best_return_unit", "worst_drawdown_unit"):
                u = summary[key]
                if u is not None:
                    summary[key] = {
                        "id": u.id,
                        "strategy_name": u.strategy_name or u.strategy_id or "",
                        "symbol": u.symbol or "",
                        "symbol_name": u.symbol_name or "",
                        "timeframe": u.timeframe or "",
                        "group_name": u.group_name or "",
                        "category": u.category or "",
                        "run_status": u.run_status or "idle",
                        "run_count": u.run_count or 0,
                        "last_run_time": u.last_run_time,
                        "last_task_id": u.last_task_id,
                        "start_date": (u.data_config or {}).get("start_date"),
                        "data_source": f"{u.symbol or ''}_{u.timeframe or ''}",
                        "value": (u.metrics_snapshot or {}).get(
                            "total_return" if key == "best_return_unit" else "max_drawdown"
                        ),
                    }

            return {
                "workspace_id": workspace_id,
                "workspace_name": ws.name,
                "summary": summary,
                "units": rows,
            }

    async def delete_workspace_report(
        self, workspace_id: str, user_id: str
    ) -> dict[str, Any] | None:
        """Clear cached report config on the workspace.

        NOTE: This no longer wipes unit ``metrics_snapshot`` (which are run
        results, not report artefacts).  It only resets the saved report
        configuration stored in ``workspace.settings.report_config`` so that
        the next GET /report returns a fresh default-config aggregation.
        """
        async with async_session_maker() as session:
            ws = await self._load_workspace(session, workspace_id, user_id, load_units=False)
            if ws is None:
                return None
            settings = dict(ws.settings or {})
            had_config = "report_config" in settings
            settings.pop("report_config", None)
            ws.settings = settings
            await session.commit()
            return {
                "workspace_id": workspace_id,
                "cleared": had_config,
                "message": "报告缓存配置已清除，单元运行指标未受影响",
            }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_backtest_request(unit: StrategyUnit) -> BacktestRequest:
        """Build a BacktestRequest from a strategy unit's configuration."""
        settings = unit.unit_settings or {}
        data_cfg = _normalize_unit_data_config(unit.data_config)
        params = unit.params or {}

        return BacktestRequest(
            strategy_id=unit.strategy_id or "",
            runtime_dir=str(workspace_unit_runtime.unit_dir(unit.workspace_id, unit.id)),
            symbol=unit.symbol or data_cfg.get("symbol", ""),
            start_date=data_cfg.get("start_date", _default_unit_start_date_iso()),
            end_date=data_cfg.get("end_date", _default_unit_end_date_iso()),
            initial_cash=settings.get("initial_cash", 100000),
            commission=settings.get("commission", 0.001),
            timeframe=unit.timeframe or "1d",
            timeframe_n=unit.timeframe_n or 1,
            bar_count=WorkspaceService._requested_bar_count(unit),
            params=params,
        )

    async def _background_poll_units(
        self,
        workspace_id: str,
        user_id: str,
        submitted: list[tuple[str, str]],
        backtest_service: "BacktestService",  # noqa: F821
    ) -> None:
        """Background task: poll all submitted units **in parallel**, then update metrics."""
        await asyncio.gather(
            *(
                self._poll_single_unit(workspace_id, user_id, unit_id, task_id, backtest_service)
                for unit_id, task_id in submitted
            ),
            return_exceptions=True,
        )

    async def _poll_single_unit(
        self,
        workspace_id: str,
        user_id: str,
        unit_id: str,
        task_id: str,
        backtest_service: "BacktestService",  # noqa: F821
    ) -> None:
        """Poll a single unit's backtest task until completion, then update metrics."""
        start_ts = time.monotonic()
        try:
            final_status = await self._poll_task_completion(
                backtest_service, task_id, user_id
            )
            task = await backtest_service.task_manager.get_task(task_id, user_id=user_id)
            elapsed = self._task_elapsed_seconds(task)
            if elapsed is None:
                elapsed = round(time.monotonic() - start_ts, 2)

            async with async_session_maker() as s:
                u = await self._get_unit(s, workspace_id, unit_id)
                if u:
                    unit_obj = cast(Any, u)
                    unit_obj.run_count = (unit_obj.run_count or 0) + 1
                    unit_obj.last_run_time = elapsed
                    if final_status == TaskStatus.COMPLETED:
                        unit_obj.run_status = "completed"
                        bt_result = await backtest_service.get_result(task_id, user_id)
                        if bt_result:
                            log_data = {
                                "equity_curve": bt_result.equity_curve or [],
                                "equity_dates": bt_result.equity_dates or [],
                                "trades": [
                                    t.model_dump() if hasattr(t, "model_dump") else t
                                    for t in (bt_result.trades or [])
                                ],
                            }
                            try:
                                metrics = calculate_extended_metrics(log_data)
                                unit_obj.metrics_snapshot = metrics
                            except Exception as me:
                                logger.warning("Extended metrics failed for unit %s: %s", unit_id, me)
                                unit_obj.metrics_snapshot = {
                                    "total_return": bt_result.total_return,
                                    "annual_return": bt_result.annual_return,
                                    "sharpe_ratio": bt_result.sharpe_ratio,
                                    "max_drawdown": bt_result.max_drawdown,
                                    "win_rate": bt_result.win_rate,
                                    "total_trades": bt_result.total_trades,
                                }
                            unit_obj.bar_count = await self._resolve_unit_bar_count(
                                backtest_service,
                                task_id,
                                user_id,
                                bt_result,
                            )
                    elif final_status == TaskStatus.CANCELLED:
                        unit_obj.run_status = "cancelled"
                    else:
                        unit_obj.run_status = "failed"
                    await s.commit()

        except Exception as e:
            logger.error("Background poll failed for unit %s: %s", unit_id, e)
            try:
                async with async_session_maker() as s_err:
                    u_err = await self._get_unit(s_err, workspace_id, unit_id)
                    if u_err:
                        u_err.run_status = "failed"
                        u_err.run_count = (u_err.run_count or 0) + 1
                        u_err.last_run_time = round(time.monotonic() - start_ts, 2)
                        await s_err.commit()
            except Exception:
                logger.exception("Failed to update unit %s status after error", unit_id)

    @staticmethod
    async def _poll_task_completion(
        backtest_service: "BacktestService",  # noqa: F821
        task_id: str,
        user_id: str,
        timeout: float = 600,
        interval: float = 2.0,
    ) -> TaskStatus:
        """Poll backtest task status until terminal state or timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = await backtest_service.get_task_status(task_id, user_id)
            if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return status
            await asyncio.sleep(interval)
        return TaskStatus.FAILED

    @staticmethod
    async def _load_workspace(
        session: AsyncSession,
        workspace_id: str,
        user_id: str,
        load_units: bool = True,
    ) -> Workspace | None:
        q = select(Workspace).where(Workspace.id == workspace_id, Workspace.user_id == user_id)
        if load_units:
            q = q.options(selectinload(Workspace.strategy_units))
        result = await session.execute(q)
        return result.scalar_one_or_none()

    @staticmethod
    async def _get_unit(
        session: AsyncSession, workspace_id: str, unit_id: str
    ) -> StrategyUnit | None:
        q = select(StrategyUnit).where(
            StrategyUnit.id == unit_id,
            StrategyUnit.workspace_id == workspace_id,
        )
        result = await session.execute(q)
        return result.scalar_one_or_none()

    @staticmethod
    def _unit_to_dict(unit: StrategyUnit, opt_info: dict[str, Any] | None = None) -> dict[str, Any]:
        opt_info = opt_info or {}
        return {
            "id": unit.id,
            "workspace_id": unit.workspace_id,
            "group_name": unit.group_name or "",
            "strategy_id": unit.strategy_id,
            "strategy_name": unit.strategy_name or "",
            "symbol": unit.symbol or "",
            "symbol_name": unit.symbol_name or "",
            "timeframe": unit.timeframe or "1d",
            "timeframe_n": unit.timeframe_n or 1,
            "category": unit.category or "",
            "sort_order": unit.sort_order or 0,
            "data_config": _normalize_unit_data_config(unit.data_config),
            "unit_settings": unit.unit_settings or {},
            "params": unit.params or {},
            "optimization_config": unit.optimization_config or {},
            "run_status": unit.run_status or "idle",
            "run_count": unit.run_count or 0,
            "last_run_time": unit.last_run_time,
            "last_task_id": unit.last_task_id,
            "last_optimization_task_id": unit.last_optimization_task_id,
            "bar_count": unit.bar_count,
            "metrics_snapshot": unit.metrics_snapshot or {},
            "opt_status": opt_info.get("opt_status"),
            "opt_total": opt_info.get("opt_total"),
            "opt_completed": opt_info.get("opt_completed"),
            "opt_progress": opt_info.get("opt_progress"),
            "opt_elapsed_time": opt_info.get("opt_elapsed_time"),
            "opt_remaining_time": opt_info.get("opt_remaining_time"),
            "created_at": unit.created_at,
            "updated_at": unit.updated_at,
        }

    @staticmethod
    def _compute_rename(
        unit: StrategyUnit,
        mode: str,
        value: str,
        search: str,
        replace: str,
    ) -> str:
        if mode == "custom":
            return value
        elif mode == "strategy":
            return unit.strategy_name or ""
        elif mode == "symbol":
            return unit.symbol or ""
        elif mode == "symbol_name":
            return unit.symbol_name or ""
        elif mode == "category":
            return unit.category or ""
        elif mode == "replace":
            current = unit.group_name or ""
            return current.replace(search, replace) if search else current
        return value
