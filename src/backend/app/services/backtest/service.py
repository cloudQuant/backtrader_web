"""
Backtest service.

Encapsulates Backtrader backtest execution and persistence.
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import update

from app.db.cache import get_cache
from app.db.database import async_session_maker
from app.db.sql_repository import SQLRepository
from app.models.backtest import BacktestResultModel, BacktestTask
from app.schemas.backtest import (
    BacktestListResponse,
    BacktestRequest,
    BacktestResponse,
    BacktestResult,
    TaskStatus,
    TradeRecord,
)
from app.schemas.backtest_enhanced import (
    BacktestCancelledEvent,
    BacktestCompletedEvent,
    BacktestFailedEvent,
    BacktestProgressEvent,
)
from app.schemas.backtest_summary import BacktestSummaryResponse, CanonicalMetrics
from app.schemas.market_data_trust import DataPrecheckRequest
from app.services.backtest.manager import BacktestExecutionManager
from app.services.backtest.runner import BacktestExecutionRunner
from app.services.backtest.sanitize import (
    coerce_float as _coerce_float,
)
from app.services.backtest.sanitize import (
    coerce_int as _coerce_int,
)
from app.services.backtest.sanitize import (
    normalize_trade_date as _normalize_trade_date,
)
from app.services.backtest.sanitize import (
    normalize_trade_type as _normalize_trade_type,
)
from app.services.backtest.sanitize import (
    sanitize_cached_result_payload as _sanitize_cached_result_payload,
)
from app.services.backtest.sanitize import (
    sanitize_trades as _sanitize_trades,
)
from app.services.backtest.workspace_setup import (
    copy_log_artifacts as _copy_log_artifacts,
)
from app.services.backtest.workspace_setup import (
    has_custom_params as _has_custom_params,
)
from app.services.backtest.workspace_setup import (
    normalize_trade_logger_params as _normalize_trade_logger_params,
)
from app.services.backtest.workspace_setup import (
    setup_workspace as _setup_workspace,
)
from app.services.backtest.workspace_setup import (
    strip_asserts as _strip_asserts,
)
from app.services.backtest.workspace_setup import (
    write_temp_config as _write_temp_config,
)
from app.services.market_data_precheck_service import get_market_data_precheck_service
from app.services.metrics_service import get_metrics_service
from app.services.robustness_validation_service import get_robustness_validation_service
from app.services.strategy.runtime_support import has_log_artifacts
from app.utils.response_cache import invalidate_cache
from app.websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)

_RUNTIME_DIR_CLIENT_FORBIDDEN = "BACKTEST_RUNTIME_DIR_CLIENT_FORBIDDEN"
_WORKSPACE_RUNTIME_PATH_INVALID = "BACKTEST_WORKSPACE_RUNTIME_PATH_INVALID"
_WORKSPACE_RUNTIME_PATH_MISMATCH = "BACKTEST_WORKSPACE_RUNTIME_PATH_MISMATCH"
_WORKSPACE_RUNTIME_UNAVAILABLE = "BACKTEST_WORKSPACE_RUNTIME_UNAVAILABLE"

WorkspaceRuntimePreflight = Callable[[], Awaitable[Path]]
WorkspaceRuntimeClaimPromoter = Callable[[str], Awaitable[bool]]
WorkspaceRuntimeClaimFinalizer = Callable[[TaskStatus], Awaitable[None]]


@dataclass(frozen=True)
class _WorkspaceRuntimeExecution:
    """Server-only runtime capability retained by the scheduled coroutine.

    It is intentionally not part of :class:`BacktestRequest`, so it is never
    supplied by a client or persisted as request data.  WorkspaceService owns
    the callback and replays its authorization checks before execution.
    """

    workspace_id: str
    unit_id: str
    expected_runtime_dir: Path
    preflight: WorkspaceRuntimePreflight
    claim_promoter: WorkspaceRuntimeClaimPromoter | None = None
    claim_finalizer: WorkspaceRuntimeClaimFinalizer | None = None


class BacktestService:
    """Service for managing backtest operations.

    This service handles:
    1. Asynchronous execution of backtest tasks
    2. Backtest result storage and retrieval
    3. Backtest task lifecycle management
    """

    def __init__(
        self,
        task_manager: BacktestExecutionManager | None = None,
        task_runner: BacktestExecutionRunner | None = None,
    ) -> None:
        """Initialize the BacktestService.

        Attributes:
            task_repo: Repository for backtest task CRUD operations.
            result_repo: Repository for backtest result CRUD operations.
            cache: Cache instance for storing frequently accessed results.
            task_manager: BacktestExecutionManager for database-backed task state.
            task_runner: Process-local execution runner used by the current API worker.
        """
        self.task_repo = SQLRepository(BacktestTask)
        self.result_repo = SQLRepository(BacktestResultModel)
        self.cache = get_cache()
        self.task_manager = task_manager or BacktestExecutionManager()
        self.task_runner = task_runner or BacktestExecutionRunner()

    @staticmethod
    def _get_request_data(task: BacktestTask) -> dict[str, object]:
        request_data = task.request_data
        if isinstance(request_data, dict):
            return request_data
        if isinstance(request_data, str):
            try:
                parsed = json.loads(request_data)
            except json.JSONDecodeError:
                return {}
            if isinstance(parsed, dict):
                return parsed
        return {}

    @staticmethod
    def _get_request_date(task: BacktestTask, key: str) -> datetime | str:
        request_data = BacktestService._get_request_data(task)
        value = request_data.get(key)
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value.strip():
            return value
        return cast(datetime, task.created_at) or datetime.now()

    @staticmethod
    def _normalize_trade_date(value: Any) -> str | None:
        return _normalize_trade_date(value)

    @staticmethod
    def _normalize_trade_type(value: Any) -> str | None:
        return _normalize_trade_type(value)

    @classmethod
    def _sanitize_trades(cls, trades: Any) -> list[dict[str, Any]]:
        return _sanitize_trades(trades)

    @staticmethod
    def _coerce_float(value: Any, default: float = 0.0) -> float:
        return _coerce_float(value, default)

    @staticmethod
    def _coerce_int(value: Any, default: int = 0) -> int:
        return _coerce_int(value, default)

    @classmethod
    def _sanitize_cached_result_payload(cls, payload: dict[str, Any]) -> dict[str, Any]:
        return _sanitize_cached_result_payload(payload)

    @staticmethod
    def _build_backtest_result(
        task: BacktestTask, result_model: BacktestResultModel | None
    ) -> BacktestResult:
        request_data = BacktestService._get_request_data(task)
        standard_metrics = (
            dict(getattr(result_model, "standard_metrics", None) or {}) if result_model else {}
        )
        if not standard_metrics and result_model is not None:
            standard_metrics = get_metrics_service().normalize(
                {
                    "total_return": result_model.total_return,
                    "annual_return": result_model.annual_return,
                    "sharpe_ratio": result_model.sharpe_ratio,
                    "max_drawdown": result_model.max_drawdown,
                    "win_rate": result_model.win_rate,
                    "total_trades": result_model.total_trades,
                    "profitable_trades": result_model.profitable_trades,
                    "losing_trades": result_model.losing_trades,
                    "avg_holding_bars": getattr(result_model, "average_holding_bars", 0.0),
                    "max_consecutive_wins": getattr(result_model, "max_consecutive_wins", 0),
                    "max_consecutive_losses": getattr(result_model, "max_consecutive_losses", 0),
                    "profit_loss_ratio": getattr(result_model, "profit_loss_ratio", 0.0),
                    "metrics_source": getattr(result_model, "metrics_source", "manual"),
                },
                trades=getattr(result_model, "trades", []),
            )
        result_summary = (
            dict(getattr(result_model, "result_summary", None) or {}) if result_model else {}
        )
        if not result_summary:
            result_summary = get_metrics_service().result_summary(
                task_id=cast(str, task.id),
                strategy_id=cast(str, task.strategy_id),
                symbol=cast(str, task.symbol),
                status=str(task.status),
                metrics=standard_metrics,
                data_precheck=dict(request_data.get("data_precheck") or {}),
            )
        return BacktestResult(
            task_id=cast(str, task.id),
            strategy_id=cast(str, task.strategy_id),
            symbol=cast(str, task.symbol),
            start_date=cast(datetime, BacktestService._get_request_date(task, "start_date")),
            end_date=cast(datetime, BacktestService._get_request_date(task, "end_date")),
            status=TaskStatus(task.status),
            total_return=BacktestService._coerce_float(
                result_model.total_return if result_model else None,
                0.0,
            ),
            annual_return=BacktestService._coerce_float(
                result_model.annual_return if result_model else None,
                0.0,
            ),
            sharpe_ratio=BacktestService._coerce_float(
                result_model.sharpe_ratio if result_model else None,
                0.0,
            ),
            max_drawdown=BacktestService._coerce_float(
                result_model.max_drawdown if result_model else None,
                0.0,
            ),
            win_rate=BacktestService._coerce_float(
                result_model.win_rate if result_model else None,
                0.0,
            ),
            metrics_source=getattr(result_model, "metrics_source", None) or "manual",
            average_holding_bars=BacktestService._coerce_float(
                getattr(result_model, "average_holding_bars", None) if result_model else None,
                float(standard_metrics.get("avg_holding_bars") or 0.0),
            ),
            max_consecutive_wins=BacktestService._coerce_int(
                getattr(result_model, "max_consecutive_wins", None) if result_model else None,
                int(standard_metrics.get("max_consecutive_wins") or 0),
            ),
            max_consecutive_losses=BacktestService._coerce_int(
                getattr(result_model, "max_consecutive_losses", None) if result_model else None,
                int(standard_metrics.get("max_consecutive_losses") or 0),
            ),
            profit_loss_ratio=BacktestService._coerce_float(
                getattr(result_model, "profit_loss_ratio", None) if result_model else None,
                float(standard_metrics.get("profit_loss_ratio") or 0.0),
            ),
            standard_metrics=standard_metrics,
            result_summary=result_summary,
            data_precheck=dict(request_data.get("data_precheck") or {}),
            robustness=None,
            total_trades=BacktestService._coerce_int(
                result_model.total_trades if result_model else None,
                0,
            ),
            profitable_trades=BacktestService._coerce_int(
                result_model.profitable_trades if result_model else None,
                0,
            ),
            losing_trades=BacktestService._coerce_int(
                result_model.losing_trades if result_model else None,
                0,
            ),
            equity_curve=cast("list[float]", result_model.equity_curve if result_model else []),
            equity_dates=cast("list[str]", result_model.equity_dates if result_model else []),
            drawdown_curve=cast("list[float]", result_model.drawdown_curve if result_model else []),
            trades=cast(
                "list[TradeRecord]",
                BacktestService._sanitize_trades(result_model.trades if result_model else []),
            ),
            created_at=cast(datetime, task.created_at),
            error_message=cast("str | None", task.error_message),
        )

    @staticmethod
    def _reject_client_runtime_dir(request: Any) -> None:
        """Reject the deprecated public runtime path on every generic entrypoint."""
        if getattr(request, "runtime_dir", None) is not None:
            raise ValueError(
                f"{_RUNTIME_DIR_CLIENT_FORBIDDEN}: "
                "runtime_dir is available only through WorkspaceService"
            )

    @staticmethod
    def _expected_workspace_runtime_dir(workspace_id: str, unit_id: str) -> Path:
        """Return a deterministic, non-escaping workspace runtime directory."""
        from app.services import workspace_unit_runtime

        workspace_id = str(workspace_id or "").strip()
        unit_id = str(unit_id or "").strip()
        if not workspace_id or not unit_id:
            raise ValueError(f"{_WORKSPACE_RUNTIME_PATH_INVALID}: workspace and unit are required")
        if any(
            value in {".", ".."} or "/" in value or "\\" in value
            for value in (workspace_id, unit_id)
        ):
            raise ValueError(
                f"{_WORKSPACE_RUNTIME_PATH_INVALID}: workspace and unit must be path components"
            )

        root = workspace_unit_runtime.workspace_dir("").resolve()
        expected = workspace_unit_runtime.unit_dir(workspace_id, unit_id)
        try:
            expected.resolve().relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"{_WORKSPACE_RUNTIME_PATH_INVALID}: runtime path escapes workspace root"
            ) from exc
        return expected

    @staticmethod
    async def _run_workspace_runtime_preflight(
        runtime: _WorkspaceRuntimeExecution,
    ) -> Path:
        """Replay WorkspaceService authorization and require its exact runtime path."""
        runtime_dir = Path(await runtime.preflight()).expanduser()
        if runtime_dir.resolve() != runtime.expected_runtime_dir.resolve():
            raise ValueError(
                f"{_WORKSPACE_RUNTIME_PATH_MISMATCH}: "
                "workspace preflight returned an unexpected runtime directory"
            )
        if not runtime_dir.is_dir():
            raise ValueError(
                f"{_WORKSPACE_RUNTIME_UNAVAILABLE}: "
                "workspace preflight did not create the runtime directory"
            )
        return runtime.expected_runtime_dir

    @staticmethod
    def _discard_workspace_runtime_after_failed_preflight(
        runtime: _WorkspaceRuntimeExecution,
    ) -> None:
        """Keep a rejected deterministic directory unreachable from execution.

        A workspace runtime is executable only through the private preflight
        capability retained in ``_WorkspaceRuntimeExecution``.  Generic API
        callers cannot select this directory, and every scheduled execution
        replays that capability immediately before spawning.  Deleting the
        shared deterministic directory here would race a newer lease that has
        already fenced and materialized the same unit, so preserve inert files
        until a later trusted preflight overwrites them.
        """
        logger.info(
            "Rejected workspace runtime for unit %s remains inaccessible without a fresh preflight",
            runtime.unit_id,
        )

    async def run_backtest(self, user_id: str, request: BacktestRequest) -> BacktestResponse:
        """Run a generic backtest without a client-controlled runtime directory."""
        self._reject_client_runtime_dir(request)
        return await self._submit_backtest(user_id, request)

    async def run_workspace_unit_backtest(
        self,
        user_id: str,
        request: BacktestRequest,
        *,
        workspace_id: str,
        unit_id: str,
        runtime_preflight: WorkspaceRuntimePreflight,
        claim_promoter: WorkspaceRuntimeClaimPromoter | None = None,
        claim_finalizer: WorkspaceRuntimeClaimFinalizer | None = None,
    ) -> BacktestResponse:
        """Submit a WorkspaceService-authorized unit backtest.

        ``runtime_preflight`` is an in-process capability created by
        WorkspaceService.  It must reload the unit, replay any strict market
        data binding checks, write the runtime, and return its deterministic
        workspace/unit directory.  The callback is replayed again immediately
        before the subprocess starts so a revoked grant cannot survive a queue
        wait.  A bound caller also supplies ``claim_promoter``: it atomically
        converts its queued unit lease into the newly-created task id before
        this service schedules any subprocess work.  Its optional finalizer
        runs only after the execution coroutine reaches a terminal persistent
        task state, so WorkspaceService can release its runtime fence without
        trusting a delayed observer.
        """
        self._reject_client_runtime_dir(request)
        if not callable(runtime_preflight):
            raise ValueError(
                f"{_WORKSPACE_RUNTIME_PATH_INVALID}: runtime_preflight must be callable"
            )
        if claim_promoter is not None and not callable(claim_promoter):
            raise ValueError(
                f"{_WORKSPACE_RUNTIME_PATH_INVALID}: claim_promoter must be callable"
            )
        if claim_finalizer is not None and not callable(claim_finalizer):
            raise ValueError(
                f"{_WORKSPACE_RUNTIME_PATH_INVALID}: claim_finalizer must be callable"
            )

        runtime = _WorkspaceRuntimeExecution(
            workspace_id=str(workspace_id or "").strip(),
            unit_id=str(unit_id or "").strip(),
            expected_runtime_dir=self._expected_workspace_runtime_dir(workspace_id, unit_id),
            preflight=runtime_preflight,
            claim_promoter=claim_promoter,
            claim_finalizer=claim_finalizer,
        )
        # Reject revoked/invalid bindings before a persistent task is created.
        try:
            await self._run_workspace_runtime_preflight(runtime)
        except Exception:
            self._discard_workspace_runtime_after_failed_preflight(runtime)
            raise
        return await self._submit_backtest(user_id, request, workspace_runtime=runtime)

    async def _submit_backtest(
        self,
        user_id: str,
        request: BacktestRequest,
        *,
        workspace_runtime: _WorkspaceRuntimeExecution | None = None,
    ) -> BacktestResponse:
        """Create and schedule a validated generic or workspace backtest task."""
        self._reject_client_runtime_dir(request)
        precheck = await get_market_data_precheck_service().precheck(
            DataPrecheckRequest(
                asset_type=getattr(request, "asset_type", None),
                symbol=request.symbol,
                timeframe=getattr(request, "timeframe", "1d") or "1d",
                provider=getattr(request, "data_provider", None),
                start_date=str(request.start_date.date())
                if isinstance(request.start_date, datetime)
                else str(request.start_date),
                end_date=str(request.end_date.date())
                if isinstance(request.end_date, datetime)
                else str(request.end_date),
            )
        )
        if getattr(request, "require_data_precheck", False) and not precheck.passed:
            raise ValueError("Backtest data precheck failed: " + "; ".join(precheck.reasons))
        if hasattr(request, "model_copy"):
            request = request.model_copy(update={"data_precheck": precheck.model_dump(mode="json")})

        # Use BacktestExecutionManager for database-backed task creation
        task = await self.task_manager.create_task(user_id, request)

        if workspace_runtime is not None and workspace_runtime.claim_promoter is not None:
            # A backtest task is persistent before it can be scheduled.  Give
            # WorkspaceService one server-only compare-and-swap point here so
            # a stop that revoked the queued lease cannot race ahead of a
            # newly-created task and leave an executable subprocess behind.
            try:
                claim_promoted = await workspace_runtime.claim_promoter(str(task.id))
            except asyncio.CancelledError:
                # ``CancelledError`` inherits from BaseException.  The task
                # was already persisted, so shield its terminal transition
                # before re-raising; otherwise a cancelled request leaks a
                # PENDING slot and WorkspaceService may release its lease.
                try:
                    await asyncio.shield(
                        self.task_manager.update_task_status(
                            str(task.id),
                            TaskStatus.CANCELLED,
                            error_message="Workspace unit run claim promotion was cancelled",
                        )
                    )
                    await self._finalize_workspace_runtime(
                        workspace_runtime,
                        TaskStatus.CANCELLED,
                    )
                except Exception:
                    logger.warning(
                        "Unable to cancel workspace task %s after promoter cancellation",
                        task.id,
                        exc_info=True,
                    )
                raise
            except Exception:
                await self.task_manager.update_task_status(
                    str(task.id),
                    TaskStatus.CANCELLED,
                    error_message="Workspace unit run claim could not be promoted",
                )
                await self._finalize_workspace_runtime(workspace_runtime, TaskStatus.CANCELLED)
                raise
            if not claim_promoted:
                await self.task_manager.update_task_status(
                    str(task.id),
                    TaskStatus.CANCELLED,
                    error_message="Workspace unit run claim was revoked before scheduling",
                )
                await self._finalize_workspace_runtime(workspace_runtime, TaskStatus.CANCELLED)
                raise ValueError("WORKSPACE_UNIT_RUN_CLAIM_LOST")

        # Execution is still owned by the current API process. The database stores
        # task state, while the runner keeps process-local cancellation handles.
        execution = self._execute_backtest(
            str(task.id),
            user_id,
            request,
            workspace_runtime=workspace_runtime,
        )
        try:
            self.task_runner.schedule(str(task.id), execution)
        except Exception:
            execution.close()
            if workspace_runtime is not None and workspace_runtime.claim_promoter is not None:
                await self.task_manager.update_task_status(
                    str(task.id),
                    TaskStatus.CANCELLED,
                    error_message="Workspace unit task could not be scheduled",
                )
                await self._finalize_workspace_runtime(workspace_runtime, TaskStatus.CANCELLED)
            raise

        await invalidate_cache("backtests")

        return BacktestResponse(
            task_id=str(task.id),
            status=TaskStatus.PENDING,
            message="Backtest task created",
        )

    @staticmethod
    async def _finalize_workspace_runtime(
        runtime: _WorkspaceRuntimeExecution | None,
        status: TaskStatus,
    ) -> None:
        """Invoke the private WorkspaceService completion fence, if supplied."""
        if runtime is None or runtime.claim_finalizer is None:
            return
        try:
            await runtime.claim_finalizer(status)
        except Exception:
            # The task itself is already terminal.  Do not turn a best-effort
            # unit-status notification into a task resurrection; the bound
            # unit remains fail-closed until its next authoritative repair.
            logger.warning(
                "Unable to finalize workspace runtime fence for unit %s",
                runtime.unit_id,
                exc_info=True,
            )

    @staticmethod
    async def _claim_task_execution_start(task_id: str) -> bool:
        """Atomically claim a persisted PENDING task for local execution.

        A stop request may mark a newly-created task cancelled in the narrow
        interval after schedule but before this coroutine starts.  A plain ORM
        assignment to RUNNING would resurrect that cancelled task.  The
        conditional transition works across API processes and all supported
        SQL dialects.
        """
        async with async_session_maker() as session:
            result = await session.execute(
                update(BacktestTask)
                .where(
                    BacktestTask.id == task_id,
                    BacktestTask.status == TaskStatus.PENDING,
                )
                .values(status=TaskStatus.RUNNING)
            )
            await session.commit()
        return int(getattr(result, "rowcount", 0) or 0) == 1

    async def _execute_backtest(
        self,
        task_id: str,
        user_id: str,
        request: BacktestRequest,
        *,
        workspace_runtime: _WorkspaceRuntimeExecution | None = None,
    ) -> None:
        """Execute a backtest task by calling the strategy directory's run.py.

        Args:
            task_id: The unique identifier for the backtest task.
            user_id: The ID of the user who requested the backtest.
            request: The backtest request parameters.
        """
        tmp_base = None
        workspace_preflight_failed = False
        terminal_status: TaskStatus | None = None
        try:
            # This also protects callers that try to invoke the execution
            # coroutine directly instead of going through run_backtest().
            self._reject_client_runtime_dir(request)
            if not await self._claim_task_execution_start(task_id):
                # A stop can persist CANCELLED after the runner accepted this
                # coroutine but before it receives CPU time.  Never revive a
                # terminal task by blindly writing RUNNING here.
                task = await self.task_manager.get_task(task_id, user_id=user_id)
                if task is not None:
                    observed = TaskStatus(task.status)
                    if observed in {
                        TaskStatus.COMPLETED,
                        TaskStatus.FAILED,
                        TaskStatus.CANCELLED,
                    }:
                        terminal_status = observed
                return
            await self._notify_progress(task_id, 10, "Task started")

            from app.services.strategy.core import get_strategy_dir

            strategy_dir = get_strategy_dir(request.strategy_id)
            use_runtime_dir = workspace_runtime is not None
            if workspace_runtime is not None:
                try:
                    task_work_dir = await self._run_workspace_runtime_preflight(workspace_runtime)
                except Exception:
                    workspace_preflight_failed = True
                    raise
                if not (task_work_dir / "run.py").is_file():
                    raise ValueError(f"Unit runtime run.py not found: {task_work_dir}")
                await self._notify_progress(task_id, 20, "Preparing unit runtime configuration...")
            else:
                if not (strategy_dir / "run.py").is_file():
                    raise ValueError(f"Strategy {request.strategy_id} run.py not found")

                tmp_base, task_work_dir = self._setup_workspace(
                    task_id, request.strategy_id, strategy_dir
                )
                await self._notify_progress(task_id, 20, "Writing configuration parameters...")

                config_path = task_work_dir / "config.yaml"
                if self._has_custom_params(request):
                    original_text = (
                        config_path.read_text(encoding="utf-8") if config_path.is_file() else None
                    )
                    self._write_temp_config(config_path, request, original_text)

            await self._notify_progress(task_id, 30, "Running backtest...")
            if workspace_runtime is not None:
                # Queue time can be arbitrarily long.  Replay the trusted
                # WorkspaceService preflight at the last safe point, before a
                # process observes the generated runtime files.
                try:
                    task_work_dir = await self._run_workspace_runtime_preflight(workspace_runtime)
                except Exception:
                    workspace_preflight_failed = True
                    raise
                if not (task_work_dir / "run.py").is_file():
                    raise ValueError(f"Unit runtime run.py not found: {task_work_dir}")
            await self._run_strategy_subprocess(task_work_dir, str(strategy_dir), task_id)

            await self._notify_progress(task_id, 80, "Parsing logs...")
            await self._persist_results(
                task_id,
                user_id,
                task_work_dir,
                strategy_dir,
                persist_in_runtime_dir=use_runtime_dir,
            )
            terminal_status = TaskStatus.COMPLETED

        except asyncio.CancelledError:
            logger.info(f"Backtest cancelled: {task_id}")
            await self.task_manager.update_task_status(
                task_id,
                TaskStatus.CANCELLED,
                error_message="User cancelled task",
            )
            await ws_manager.send_to_task(
                task_id,
                BacktestCancelledEvent(task_id=task_id).model_dump(mode="python"),
            )
            terminal_status = TaskStatus.CANCELLED
        except Exception as e:
            logger.error(f"Backtest failed: {task_id}, {e}")
            if workspace_runtime is not None and workspace_preflight_failed:
                self._discard_workspace_runtime_after_failed_preflight(workspace_runtime)
            await self.task_manager.update_task_status(
                task_id,
                TaskStatus.FAILED,
                error_message=str(e),
            )
            await ws_manager.send_to_task(
                task_id,
                BacktestFailedEvent(task_id=task_id, message=str(e), error=str(e)).model_dump(
                    mode="python"
                ),
            )
            terminal_status = TaskStatus.FAILED
        finally:
            if terminal_status is not None:
                await self._finalize_workspace_runtime(workspace_runtime, terminal_status)
            if tmp_base and tmp_base.is_dir():
                try:
                    shutil.rmtree(tmp_base, ignore_errors=True)
                except Exception as e:
                    logger.debug("Cleanup dir failed (ignored): %s", e)

    # ------------------------------------------------------------------
    # _execute_backtest helpers
    # ------------------------------------------------------------------

    def _setup_workspace(
        self,
        task_id: str,
        strategy_id: str,
        strategy_dir: Path,
    ) -> tuple[Path, Path]:
        return _setup_workspace(task_id, strategy_id, strategy_dir)

    @staticmethod
    def _copy_log_artifacts(source_dir: Path, target_dir: Path) -> None:
        _copy_log_artifacts(source_dir, target_dir)

    async def _persist_results(
        self,
        task_id: str,
        user_id: str,
        task_work_dir: Path,
        strategy_dir: Path,
        persist_in_runtime_dir: bool = False,
    ) -> None:
        """Parse logs, calculate metrics, persist results and notify completion."""
        from app.services.log_parser_service import parse_all_logs, parse_log_dir

        task_log_dir = task_work_dir / "logs" / f"task_{task_id}"
        if has_log_artifacts(task_log_dir):
            log_result = parse_log_dir(task_log_dir, strategy_dir=task_work_dir)
        else:
            log_result = parse_all_logs(task_work_dir)
        if not log_result:
            raise ValueError("Backtest completed but no log file found")

        metrics = get_metrics_service().calculate_from_log_data(log_result, use_fincore=True)

        persist_log_dir = (
            task_work_dir / "logs" / f"task_{task_id}"
            if persist_in_runtime_dir
            else strategy_dir / "logs" / f"task_{task_id}"
        )
        tmp_log_dir = log_result.get("log_dir")
        if tmp_log_dir and Path(tmp_log_dir).is_dir() and Path(tmp_log_dir) != persist_log_dir:
            self._copy_log_artifacts(Path(tmp_log_dir), persist_log_dir)

        await self.task_manager.create_result(
            task_id=task_id,
            metrics=metrics,
            equity_curve=log_result.get("equity_curve", []),
            equity_dates=log_result.get("equity_dates", []),
            drawdown_curve=log_result.get("drawdown_curve", []),
            trades=log_result.get("trades", []),
            metrics_source=metrics.get("metrics_source", "manual"),
            standard_metrics=metrics,
        )
        await self.task_manager.update_task_status(
            task_id,
            TaskStatus.COMPLETED,
            log_dir=str(persist_log_dir),
        )

        completed_result = await self.get_result(task_id, user_id=user_id)
        await ws_manager.send_to_task(
            task_id,
            BacktestCompletedEvent(
                task_id=task_id,
                message="Backtest completed",
                result=completed_result.model_dump(mode="json") if completed_result else None,
            ).model_dump(mode="python"),
        )
        logger.info(f"Backtest completed: {task_id}, return: {log_result.get('total_return', 0)}%")

    async def _notify_progress(self, task_id: str, progress: int, message: str) -> None:
        """Send a backtest progress event via WebSocket."""
        await self.task_manager.update_task_progress(task_id, progress, message)
        await ws_manager.send_to_task(
            task_id,
            BacktestProgressEvent(task_id=task_id, progress=progress, message=message).model_dump(
                mode="python"
            ),
        )

    def _has_custom_params(self, request: BacktestRequest) -> bool:
        """Check if there are custom parameters to override config.yaml."""
        return _has_custom_params(request)

    def _write_temp_config(
        self, config_path: Path, request: BacktestRequest, original_text: str | None
    ) -> None:
        """Write custom parameters from frontend to temporary config.yaml."""
        _write_temp_config(config_path, request, original_text)

    @staticmethod
    def _strip_asserts(run_py: Path) -> None:
        """Remove assert statements from run.py to prevent assertion failures."""
        _strip_asserts(run_py)

    @staticmethod
    def _normalize_trade_logger_params(run_py: Path) -> None:
        """Rewrite legacy TradeLogger kwargs in run.py so the real observer works."""
        _normalize_trade_logger_params(run_py)

    async def _run_strategy_subprocess(
        self,
        work_dir: Path,
        original_strategy_dir: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, str]:
        """Run the strategy's run.py via subprocess with PID tracking for cancellation.

        Args:
            work_dir: Working directory for the subprocess.
            original_strategy_dir: Original strategy directory path.
            task_id: Task ID for tracking the subprocess.

        Returns:
            Dictionary containing stdout and stderr from the subprocess.

        Raises:
            RuntimeError: If the run.py execution fails.
        """
        python_exec = sys.executable
        run_py = work_dir / "run.py"
        # Normalize legacy TradeLogger param names so the real observer works
        self._normalize_trade_logger_params(run_py)

        # Prepare environment variables
        from app.services.strategy.core import STRATEGIES_DIR

        project_root = STRATEGIES_DIR.parent
        env = dict(os.environ)
        env["BACKTRADER_DATA_DIR"] = str(project_root / "datas")
        orig_dir = original_strategy_dir or str(work_dir)
        env["PYTHONPATH"] = os.pathsep.join([orig_dir, str(work_dir), env.get("PYTHONPATH", "")])
        if task_id:
            env["BACKTRADER_LOG_DIR"] = str(work_dir / "logs" / f"task_{task_id}")

        def _run() -> tuple[int | None, str, str]:
            proc = subprocess.Popen(
                [python_exec, "-O", str(run_py)],
                cwd=str(work_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            # Record PID for cancellation
            if task_id:
                self.task_runner.register_process(task_id, proc)
            from app.config import get_settings

            try:
                stdout, stderr = proc.communicate(timeout=get_settings().BACKTEST_TIMEOUT)
                return proc.returncode, stdout, stderr
            finally:
                if task_id:
                    self.task_runner.unregister_process(task_id)

        returncode, stdout, stderr = await asyncio.get_event_loop().run_in_executor(None, _run)

        if returncode != 0:
            err_msg = stderr.strip().split("\n")[-1] if stderr else "Unknown error"
            raise RuntimeError(f"run.py execution failed: {err_msg}")

        return {"stdout": stdout, "stderr": stderr}

    async def get_result(self, task_id: str, user_id: str | None = None) -> BacktestResult | None:
        """Get backtest result by task ID with optional user authorization.

        Args:
            task_id: The unique identifier for the backtest task.
            user_id: Optional user ID for authorization check (B002).

        Returns:
            BacktestResult if found and authorized, None otherwise.
        """
        # Query task (validate user ownership first, then check cache to prevent bypass)
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            return None

        # B002: Validate user ownership
        if user_id and task.user_id != user_id:
            return None

        # After authorization, check cache
        cache_key = f"backtest:result:{task_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            cached_payload = self._sanitize_cached_result_payload(dict(cached))
            if not (
                task.status == TaskStatus.COMPLETED
                and task.log_dir
                and (not cached_payload.get("equity_curve") and not cached_payload.get("trades"))
            ):
                return await self._attach_latest_robustness(
                    BacktestResult(**cached_payload),
                    user_id=user_id,
                )

        # Query result
        results = await self.result_repo.list(filters={"task_id": task_id}, limit=1)
        result_model = results[0] if results else None

        if (
            task.status == TaskStatus.COMPLETED
            and task.log_dir
            and (
                result_model is None
                or (
                    not getattr(result_model, "equity_curve", None)
                    and not getattr(result_model, "trades", None)
                )
            )
        ):
            from app.services.log_parser_service import parse_log_dir

            persisted_log_dir = Path(task.log_dir)
            if persisted_log_dir.is_dir():
                log_result = parse_log_dir(persisted_log_dir)
                if log_result:
                    metrics = get_metrics_service().calculate_from_log_data(
                        log_result,
                        use_fincore=True,
                    )
                    request_data = BacktestService._get_request_data(task)
                    result = BacktestResult(
                        task_id=cast(str, task.id),
                        strategy_id=cast(str, task.strategy_id),
                        symbol=cast(str, task.symbol),
                        start_date=cast(
                            datetime, BacktestService._get_request_date(task, "start_date")
                        ),
                        end_date=cast(
                            datetime, BacktestService._get_request_date(task, "end_date")
                        ),
                        status=TaskStatus(task.status),
                        total_return=BacktestService._coerce_float(
                            metrics.get("total_return"), 0.0
                        ),
                        annual_return=BacktestService._coerce_float(
                            metrics.get("annual_return"), 0.0
                        ),
                        sharpe_ratio=BacktestService._coerce_float(
                            metrics.get("sharpe_ratio"), 0.0
                        ),
                        max_drawdown=BacktestService._coerce_float(
                            metrics.get("max_drawdown"), 0.0
                        ),
                        win_rate=BacktestService._coerce_float(metrics.get("win_rate"), 0.0),
                        metrics_source=str(metrics.get("metrics_source") or "manual"),
                        average_holding_bars=BacktestService._coerce_float(
                            metrics.get("avg_holding_bars"),
                            0.0,
                        ),
                        max_consecutive_wins=BacktestService._coerce_int(
                            metrics.get("max_consecutive_wins"),
                            0,
                        ),
                        max_consecutive_losses=BacktestService._coerce_int(
                            metrics.get("max_consecutive_losses"),
                            0,
                        ),
                        profit_loss_ratio=BacktestService._coerce_float(
                            metrics.get("profit_loss_ratio"),
                            0.0,
                        ),
                        standard_metrics=metrics,
                        result_summary=get_metrics_service().result_summary(
                            task_id=cast(str, task.id),
                            strategy_id=cast(str, task.strategy_id),
                            symbol=cast(str, task.symbol),
                            status=TaskStatus(task.status).value,
                            metrics=metrics,
                            data_precheck=dict(request_data.get("data_precheck") or {}),
                        ),
                        data_precheck=dict(request_data.get("data_precheck") or {}),
                        robustness=None,
                        total_trades=BacktestService._coerce_int(metrics.get("total_trades"), 0),
                        profitable_trades=BacktestService._coerce_int(
                            metrics.get("profitable_trades"),
                            0,
                        ),
                        losing_trades=BacktestService._coerce_int(metrics.get("losing_trades"), 0),
                        equity_curve=log_result.get("equity_curve", []),
                        equity_dates=log_result.get("equity_dates", []),
                        drawdown_curve=log_result.get("drawdown_curve", []),
                        trades=cast(
                            "list[TradeRecord]",
                            BacktestService._sanitize_trades(log_result.get("trades", [])),
                        ),
                        created_at=cast(datetime, task.created_at),
                        error_message=cast("str | None", task.error_message),
                    )
                    await self.cache.set(cache_key, result.model_dump(mode="json"), ttl=3600)
                    return await self._attach_latest_robustness(result, user_id=user_id)

        # Use unified result builder to avoid code duplication
        result = self._build_backtest_result(task, result_model)

        # Cache result
        if task.status == TaskStatus.COMPLETED:
            await self.cache.set(cache_key, result.model_dump(mode="json"), ttl=3600)

        return await self._attach_latest_robustness(result, user_id=user_id)

    async def _attach_latest_robustness(
        self,
        result: BacktestResult,
        *,
        user_id: str | None,
    ) -> BacktestResult:
        if user_id is None:
            return result
        latest = await get_robustness_validation_service().get_latest(
            backtest_id=result.task_id,
            user_id=user_id,
        )
        if latest is None:
            return result
        robustness_payload = latest.model_dump(mode="json")
        summary = dict(result.result_summary or {})
        summary["robustness"] = robustness_payload
        return result.model_copy(
            update={
                "robustness": robustness_payload,
                "result_summary": summary,
            }
        )

    async def get_result_summary(
        self,
        task_id: str,
        *,
        user_id: str | None = None,
    ) -> BacktestSummaryResponse | None:
        """Return a compact canonical summary without loading result curves or trades."""
        task = await self.task_repo.get_by_id(task_id)
        if task is None or (user_id is not None and task.user_id != user_id):
            return None
        result_model = await self.result_repo.get_by_field("task_id", task_id)
        request_data = self._get_request_data(task)
        standard_metrics = dict(getattr(result_model, "standard_metrics", None) or {})
        if not standard_metrics and result_model is not None:
            standard_metrics = get_metrics_service().normalize(
                {
                    "total_return": result_model.total_return,
                    "annual_return": result_model.annual_return,
                    "sharpe_ratio": result_model.sharpe_ratio,
                    "max_drawdown": result_model.max_drawdown,
                    "win_rate": result_model.win_rate,
                    "total_trades": result_model.total_trades,
                    "profit_loss_ratio": getattr(result_model, "profit_loss_ratio", 0.0),
                    "max_consecutive_wins": getattr(result_model, "max_consecutive_wins", 0),
                    "max_consecutive_losses": getattr(result_model, "max_consecutive_losses", 0),
                    "avg_holding_bars": getattr(result_model, "average_holding_bars", 0.0),
                },
                trades=None,
            )
        summary = dict(getattr(result_model, "result_summary", None) or {})
        robustness = dict(summary.get("robustness") or {})
        if user_id is not None:
            latest = await get_robustness_validation_service().get_latest(
                backtest_id=task_id,
                user_id=user_id,
            )
            if latest is not None:
                robustness = latest.model_dump(mode="json")
        return BacktestSummaryResponse(
            task_id=str(task.id),
            strategy_id=str(task.strategy_id),
            symbol=str(task.symbol),
            status=TaskStatus(task.status),
            metrics=CanonicalMetrics.model_validate(standard_metrics),
            data_precheck=dict(request_data.get("data_precheck") or {}),
            robustness=robustness,
        )

    async def cancel_task(self, task_id: str, user_id: str) -> bool:
        """Cancel a running backtest task.

        Cancellation is only supported for execution handles owned by the current
        API process. Persistent status lives in the database, but actual process
        termination is still process-local in the current architecture.

        Args:
            task_id: The unique identifier for the backtest task.
            user_id: The ID of the user requesting cancellation.

        Returns:
            True if cancellation succeeded, False otherwise.
        """
        task = await self.task_repo.get_by_id(task_id)
        if not task or task.user_id != user_id:
            return False

        if task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
            return False

        cancelled_locally = self.task_runner.cancel_local_execution(task_id)
        if task.status == TaskStatus.RUNNING and not cancelled_locally:
            logger.warning(
                "Cannot cancel running backtest %s: no local execution handle in this process",
                task_id,
            )
            return False

        # Update task status using task_manager
        await self.task_manager.update_task_status(
            task_id,
            TaskStatus.CANCELLED,
            error_message="User cancelled task",
        )
        await invalidate_cache("backtests")
        return True

    async def get_task_status(self, task_id: str, user_id: str | None = None) -> TaskStatus | None:
        """Get task status with optional user authorization.

        Args:
            task_id: The unique identifier for the backtest task.
            user_id: Optional user ID for authorization check (B002).

        Returns:
            TaskStatus if found and authorized, None otherwise.
        """
        task = await self.task_repo.get_by_id(task_id)
        if not task:
            return None
        if user_id and task.user_id != user_id:
            return None
        return TaskStatus(task.status)

    async def list_results(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_desc: bool = True,
    ) -> BacktestListResponse:
        """List backtest results with sorting support.

        Optimization: Uses batch queries to avoid N+1 query problems.

        Args:
            user_id: The ID of the user to list results for.
            limit: Maximum number of results to return.
            offset: Number of results to skip.
            sort_by: Field to sort by (e.g., "created_at", "strategy_id", "symbol").
            sort_desc: Whether to sort in descending order.

        Returns:
            BacktestListResponse containing total count and list of results.
        """
        tasks = await self.task_repo.list(
            filters={"user_id": user_id},
            skip=offset,
            limit=limit,
            order_by=sort_by,
            order_desc=sort_desc,
        )
        total = await self.task_repo.count(filters={"user_id": user_id})

        task_ids = [str(task.id) for task in tasks]
        result_models = (
            await self.result_repo.list(filters={"task_id": task_ids}, limit=len(task_ids) or 1)
            if task_ids
            else []
        )
        result_by_task_id = {str(r.task_id): r for r in result_models}

        items = [
            self._build_backtest_result(task, result_by_task_id.get(str(task.id))) for task in tasks
        ]
        items = [await self._attach_latest_robustness(item, user_id=user_id) for item in items]

        return BacktestListResponse(total=total, items=items)

    async def delete_result(self, task_id: str, user_id: str) -> bool:
        """Delete a backtest result and associated files.

        Args:
            task_id: The unique identifier for backtest task.
            user_id: The ID of the user requesting deletion.

        Returns:
            True if deletion succeeded, False otherwise.
        """
        # Keep the log path until the database deletion has committed. This
        # prevents losing diagnostics when a database constraint rejects the
        # deletion.
        log_path: Path | None = None
        task = await self.task_repo.get_by_id(task_id)
        if task and task.user_id == user_id:
            if getattr(task, "log_dir", None):
                log_path = Path(task.log_dir)

        # Delete task and result using task_manager
        success = await self.task_manager.delete_task_and_result(task_id, user_id)

        # Clear cache
        if success:
            if log_path and log_path.is_dir():
                try:
                    shutil.rmtree(log_path, ignore_errors=True)
                except Exception as e:
                    # Log deletion failure is non-critical; log and continue.
                    logger.debug("Log dir deletion failed (ignored): %s", e)
            await self.cache.delete(f"backtest:result:{task_id}")
            await invalidate_cache("backtests")

        return success
