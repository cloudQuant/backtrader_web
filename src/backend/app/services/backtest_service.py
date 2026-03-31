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
import tempfile
from datetime import datetime
from pathlib import Path

from app.db.cache import get_cache
from app.db.sql_repository import SQLRepository
from app.models.backtest import BacktestResultModel, BacktestTask
from app.schemas.backtest import (
    BacktestListResponse,
    BacktestRequest,
    BacktestResponse,
    BacktestResult,
    TaskStatus,
)
from app.schemas.backtest_enhanced import (
    BacktestCancelledEvent,
    BacktestCompletedEvent,
    BacktestFailedEvent,
    BacktestProgressEvent,
)
from app.services.backtest_manager import BacktestExecutionManager
from app.services.backtest_runner import BacktestExecutionRunner
from app.websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)


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
        return task.created_at or datetime.now()

    @staticmethod
    def _build_backtest_result(
        task: BacktestTask, result_model: BacktestResultModel | None
    ) -> BacktestResult:
        return BacktestResult(
            task_id=task.id,
            strategy_id=task.strategy_id,
            symbol=task.symbol,
            start_date=BacktestService._get_request_date(task, "start_date"),
            end_date=BacktestService._get_request_date(task, "end_date"),
            status=TaskStatus(task.status),
            total_return=result_model.total_return if result_model else 0,
            annual_return=result_model.annual_return if result_model else 0,
            sharpe_ratio=result_model.sharpe_ratio if result_model else 0,
            max_drawdown=result_model.max_drawdown if result_model else 0,
            win_rate=result_model.win_rate if result_model else 0,
            metrics_source=getattr(result_model, "metrics_source", None) or "manual",
            total_trades=result_model.total_trades if result_model else 0,
            profitable_trades=result_model.profitable_trades if result_model else 0,
            losing_trades=result_model.losing_trades if result_model else 0,
            equity_curve=result_model.equity_curve if result_model else [],
            equity_dates=result_model.equity_dates if result_model else [],
            drawdown_curve=result_model.drawdown_curve if result_model else [],
            trades=result_model.trades if result_model else [],
            created_at=task.created_at,
            error_message=task.error_message,
        )

    async def run_backtest(self, user_id: str, request: BacktestRequest) -> BacktestResponse:
        """Run a backtest asynchronously.

        Args:
            user_id: The ID of the user requesting the backtest.
            request: The backtest request containing strategy and parameters.

        Returns:
            BacktestResponse: Response containing the task_id and initial status.

        Raises:
            ValueError: If global or user concurrent task limits are exceeded.
        """
        # Use BacktestExecutionManager for database-backed task creation
        task = await self.task_manager.create_task(user_id, request)

        # Execution is still owned by the current API process. The database stores
        # task state, while the runner keeps process-local cancellation handles.
        self.task_runner.schedule(
            str(task.id), self._execute_backtest(str(task.id), user_id, request)
        )

        return BacktestResponse(
            task_id=str(task.id),
            status=TaskStatus.PENDING,
            message="Backtest task created",
        )

    async def _execute_backtest(self, task_id: str, user_id: str, request: BacktestRequest) -> None:
        """Execute a backtest task by calling the strategy directory's run.py.

        Args:
            task_id: The unique identifier for the backtest task.
            user_id: The ID of the user who requested the backtest.
            request: The backtest request parameters.
        """
        tmp_base = None
        try:
            await self.task_manager.update_task_status(task_id, TaskStatus.RUNNING)
            await self._notify_progress(task_id, 10, "Task started")

            from app.services.strategy_service import get_strategy_dir

            strategy_dir = get_strategy_dir(request.strategy_id)
            if not (strategy_dir / "run.py").is_file():
                raise ValueError(f"Strategy {request.strategy_id} run.py not found")

            tmp_base, task_work_dir = self._setup_workspace(task_id, request.strategy_id, strategy_dir)
            await self._notify_progress(task_id, 20, "Writing configuration parameters...")

            config_path = task_work_dir / "config.yaml"
            if self._has_custom_params(request):
                original_text = config_path.read_text(encoding="utf-8") if config_path.is_file() else None
                self._write_temp_config(config_path, request, original_text)

            await self._notify_progress(task_id, 30, "Running backtest...")
            await self._run_strategy_subprocess(task_work_dir, str(strategy_dir), task_id)

            await self._notify_progress(task_id, 80, "Parsing logs...")
            await self._persist_results(task_id, user_id, task_work_dir, strategy_dir)

        except asyncio.CancelledError:
            logger.info(f"Backtest cancelled: {task_id}")
            await self.task_manager.update_task_status(
                task_id, TaskStatus.CANCELLED, error_message="User cancelled task",
            )
            await ws_manager.send_to_task(
                task_id, BacktestCancelledEvent(task_id=task_id).model_dump(mode="python"),
            )
        except Exception as e:
            logger.error(f"Backtest failed: {task_id}, {e}")
            await self.task_manager.update_task_status(
                task_id, TaskStatus.FAILED, error_message=str(e),
            )
            await ws_manager.send_to_task(
                task_id,
                BacktestFailedEvent(task_id=task_id, message=str(e), error=str(e)).model_dump(mode="python"),
            )
        finally:
            if tmp_base and tmp_base.is_dir():
                try:
                    shutil.rmtree(tmp_base, ignore_errors=True)
                except Exception as e:
                    logger.debug("Cleanup dir failed (ignored): %s", e)

    # ------------------------------------------------------------------
    # _execute_backtest helpers
    # ------------------------------------------------------------------

    def _setup_workspace(
        self, task_id: str, strategy_id: str, strategy_dir: Path,
    ) -> tuple[Path, Path]:
        """Create an isolated temp workspace for a backtest run.

        Returns:
            (tmp_base, task_work_dir) – the root temp directory and the
            strategy-specific working directory inside it.
        """
        from app.services.strategy_service import STRATEGIES_DIR

        tmp_base = Path(tempfile.mkdtemp(prefix=f"bt_{task_id}_"))
        task_work_dir = tmp_base / "strategies" / strategy_id
        task_work_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(strategy_dir, task_work_dir, dirs_exist_ok=True)

        # Symlink shared data directory
        project_root = STRATEGIES_DIR.parent
        datas_src = project_root / "datas"
        datas_link = tmp_base / "datas"
        if datas_src.is_dir() and not datas_link.exists():
            os.symlink(str(datas_src), str(datas_link))

        # Clear temp directory logs to avoid stale output
        tmp_logs = task_work_dir / "logs"
        if tmp_logs.is_dir():
            shutil.rmtree(tmp_logs)

        return tmp_base, task_work_dir

    async def _persist_results(
        self, task_id: str, user_id: str, task_work_dir: Path, strategy_dir: Path,
    ) -> None:
        """Parse logs, calculate metrics, persist results and notify completion."""
        from app.services.fincore_metrics_helper import calculate_metrics_from_log_data
        from app.services.log_parser_service import parse_all_logs

        log_result = parse_all_logs(task_work_dir)
        if not log_result:
            raise ValueError("Backtest completed but no log file found")

        metrics = calculate_metrics_from_log_data(log_result, use_fincore=True)

        # Copy temp logs back to strategy directory for persistence
        persist_log_dir = strategy_dir / "logs" / f"task_{task_id}"
        tmp_log_dir = log_result.get("log_dir")
        if tmp_log_dir and Path(tmp_log_dir).is_dir():
            shutil.copytree(tmp_log_dir, persist_log_dir, dirs_exist_ok=True)

        await self.task_manager.create_result(
            task_id=task_id,
            metrics=metrics,
            equity_curve=log_result.get("equity_curve", []),
            equity_dates=log_result.get("equity_dates", []),
            drawdown_curve=log_result.get("drawdown_curve", []),
            trades=log_result.get("trades", []),
            metrics_source=metrics.get("metrics_source", "manual"),
        )
        await self.task_manager.update_task_status(
            task_id, TaskStatus.COMPLETED, log_dir=str(persist_log_dir),
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
        await ws_manager.send_to_task(
            task_id,
            BacktestProgressEvent(task_id=task_id, progress=progress, message=message).model_dump(mode="python"),
        )

    def _has_custom_params(self, request: BacktestRequest) -> bool:
        """Check if there are custom parameters to override config.yaml.

        Args:
            request: The backtest request to check.

        Returns:
            True if custom parameters exist, False otherwise.
        """
        return bool(request.params) or request.initial_cash != 100000 or request.commission != 0.001

    def _write_temp_config(
        self, config_path: Path, request: BacktestRequest, original_text: str | None
    ) -> None:
        """Write custom parameters from frontend to temporary config.yaml.

        Args:
            config_path: Path to the config.yaml file.
            request: The backtest request containing custom parameters.
            original_text: Original config file content if exists.
        """
        import yaml

        config = {}
        if original_text:
            config = yaml.safe_load(original_text) or {}

        # Override strategy parameters
        if request.params:
            if "params" not in config:
                config["params"] = {}
            config["params"].update(request.params)

        # Override backtest configuration
        if "backtest" not in config:
            config["backtest"] = {}
        config["backtest"]["initial_cash"] = request.initial_cash
        config["backtest"]["commission"] = request.commission

        # Override data configuration
        if "data" not in config:
            config["data"] = {}
        if request.symbol:
            config["data"]["symbol"] = request.symbol
        # Write timeframe / timeframe_n / bar_count into data config so the
        # strategy runner picks them up (Bug-2 v2 fix).
        if request.timeframe:
            config["data"]["timeframe"] = request.timeframe
        if request.timeframe_n is not None:
            config["data"]["timeframe_n"] = request.timeframe_n
        if request.bar_count is not None:
            config["data"]["bar_count"] = request.bar_count

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

    @staticmethod
    def _strip_asserts(run_py: Path) -> None:
        """Remove assert statements from run.py to prevent assertion failures.

        [B005] This prevents assert failures when parameters change.

        Args:
            run_py: Path to the run.py file to process.
        """
        if not run_py.is_file():
            return
        code = run_py.read_text(encoding="utf-8")
        lines = code.split("\n")
        cleaned = []
        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith("assert ") or stripped.startswith("assert("):
                cleaned.append(line.replace(stripped, "pass  # assert removed for web backtest"))
            else:
                cleaned.append(line)
        run_py.write_text("\n".join(cleaned), encoding="utf-8")

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

        # Prepare environment variables
        from app.services.strategy_service import STRATEGIES_DIR

        project_root = STRATEGIES_DIR.parent
        env = dict(os.environ)
        env["BACKTRADER_DATA_DIR"] = str(project_root / "datas")
        orig_dir = original_strategy_dir or str(work_dir)
        env["PYTHONPATH"] = os.pathsep.join([orig_dir, str(work_dir), env.get("PYTHONPATH", "")])

        def _run():
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
            return BacktestResult(**cached)

        # Query result
        results = await self.result_repo.list(filters={"task_id": task_id}, limit=1)
        result_model = results[0] if results else None

        # Use unified result builder to avoid code duplication
        result = self._build_backtest_result(task, result_model)

        # Cache result
        if task.status == TaskStatus.COMPLETED:
            await self.cache.set(cache_key, result.model_dump(mode="json"), ttl=3600)

        return result

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

        return BacktestListResponse(total=total, items=items)

    async def delete_result(self, task_id: str, user_id: str) -> bool:
        """Delete a backtest result and associated files.

        Args:
            task_id: The unique identifier for backtest task.
            user_id: The ID of the user requesting deletion.

        Returns:
            True if deletion succeeded, False otherwise.
        """
        # Get task to check log directory
        task = await self.task_repo.get_by_id(task_id)
        if task and task.user_id == user_id:
            # Delete persisted log directory (OPT-14: prevent disk accumulation)
            if getattr(task, "log_dir", None):
                log_path = Path(task.log_dir)
                if log_path.is_dir():
                    try:
                        shutil.rmtree(log_path, ignore_errors=True)
                    except Exception as e:
                        # Log deletion failure is non-critical; log and continue
                        logger.debug("Log dir deletion failed (ignored): %s", e)

        # Delete task and result using task_manager
        success = await self.task_manager.delete_task_and_result(task_id, user_id)

        # Clear cache
        if success:
            await self.cache.delete(f"backtest:result:{task_id}")

        return success
