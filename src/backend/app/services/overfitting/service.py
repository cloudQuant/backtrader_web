from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from functools import lru_cache

from app.db.sql_repository import SQLRepository
from app.models.backtest import BacktestTask
from app.models.overfitting_result import OverfittingResultModel
from app.schemas.backtest import BacktestRequest, BacktestResult
from app.schemas.overfitting import (
    OverfittingAnalysisRequest,
    OverfittingMethod,
    OverfittingMethodResult,
    OverfittingRiskLevel,
    OverfittingTaskResult,
    OverfittingTaskSubmission,
)
from app.services.backtest_service import BacktestService
from app.services.overfitting.monte_carlo import run_monte_carlo_analysis
from app.services.overfitting.out_of_sample import run_out_of_sample_analysis
from app.services.overfitting.walk_forward import run_walk_forward_analysis
from app.websocket_manager import MessageType
from app.websocket_manager import manager as ws_manager

_PENDING_SUMMARY = "过拟合检测任务已提交，等待执行。"
AnalysisProgressCallback = Callable[[int, str], Awaitable[None]]


def _overfitting_ws_channel(task_id: str) -> str:
    return f"overfitting:{task_id}"


class OverfittingService:
    def __init__(self, backtest_service: BacktestService | None = None) -> None:
        self.backtest_service = backtest_service or BacktestService()
        self.backtest_task_repo = SQLRepository(BacktestTask)
        self.repo = SQLRepository(OverfittingResultModel)
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def schedule_analysis(
        self,
        *,
        backtest_id: str,
        user_id: str,
        request: OverfittingAnalysisRequest,
    ) -> OverfittingTaskSubmission:
        backtest_result = await self.backtest_service.get_result(backtest_id, user_id=user_id)
        if backtest_result is None:
            raise ValueError("Backtest result not found")

        task_id = str(uuid.uuid4())
        await self.repo.create(
            OverfittingResultModel(
                task_id=task_id,
                backtest_id=backtest_id,
                user_id=user_id,
                status="pending",
                requested_methods=[item.value for item in request.methods],
                overall_level=OverfittingRiskLevel.MEDIUM.value,
                robustness_score=50.0,
                summary=_PENDING_SUMMARY,
                methods=[],
            )
        )
        task = asyncio.create_task(self._run_task(task_id, backtest_result, request))
        self._tasks[task_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(task_id, None))
        return OverfittingTaskSubmission(
            task_id=task_id,
            backtest_id=backtest_id,
            status="pending",
            methods=request.methods,
        )

    async def get_task_result(
        self,
        task_id: str,
        *,
        user_id: str,
    ) -> OverfittingTaskResult | None:
        model = await self.repo.get_by_field("task_id", task_id)
        if model is None or str(model.user_id) != str(user_id):
            return None
        return self._to_result(model)

    async def get_cached_analysis(
        self,
        backtest_id: str,
        *,
        user_id: str | None = None,
    ) -> OverfittingTaskResult | None:
        models = await self.repo.get_by_fields({"backtest_id": backtest_id}, limit=50)
        if not models:
            return None
        ordered = sorted(models, key=lambda item: item.updated_at or item.created_at, reverse=True)
        for model in ordered:
            if user_id is not None and str(model.user_id) != str(user_id):
                continue
            return self._to_result(model)

    async def _load_backtest_request(
        self, backtest_id: str, user_id: str
    ) -> BacktestRequest | None:
        task = await self.backtest_task_repo.get_by_id(backtest_id)
        if task is None or str(task.user_id) != str(user_id):
            return None
        request_data = self.backtest_service._get_request_data(task)
        if not request_data:
            return None
        normalized = dict(request_data)
        for key in ("start_date", "end_date"):
            value = normalized.get(key)
            if isinstance(value, str):
                normalized[key] = self._parse_datetime(value)
        try:
            return BacktestRequest.model_validate(normalized)
        except Exception:
            return None

    async def _execute_slice_backtest(
        self, user_id: str, request: BacktestRequest
    ) -> BacktestResult:
        response = await self.backtest_service.run_backtest(user_id, request)
        return await self._wait_for_result(response.task_id, user_id)

    async def _wait_for_result(self, task_id: str, user_id: str) -> BacktestResult:
        for _ in range(240):
            result = await self.backtest_service.get_result(task_id, user_id=user_id)
            if result is None:
                await asyncio.sleep(0.5)
                continue
            if result.status.value == "completed":
                return result
            if result.status.value in {"failed", "cancelled"}:
                raise ValueError(result.error_message or f"Backtest slice {task_id} failed")
            await asyncio.sleep(0.5)
        raise TimeoutError(f"Timed out waiting for backtest slice {task_id}")

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        candidate = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
                try:
                    return datetime.strptime(value.strip(), fmt)
                except ValueError:
                    continue
        raise ValueError(f"Unsupported datetime value: {value}")

    @staticmethod
    def _degraded_placeholder(method: OverfittingMethod) -> OverfittingMethodResult:
        return OverfittingMethodResult(
            method=method,
            status="completed",
            risk_level=OverfittingRiskLevel.MEDIUM,
            score=50.0,
            explanation=f"{method.value} 尚未接入真实检测，暂按中位分处理。",
            metrics={"status": "pending_implementation"},
            degraded=True,
        )

    async def calculate_analysis(
        self,
        backtest_result: BacktestResult,
        request: OverfittingAnalysisRequest,
        *,
        base_request: BacktestRequest | None = None,
        user_id: str | None = None,
        progress_callback: AnalysisProgressCallback | None = None,
    ) -> OverfittingTaskResult:
        methods: list[OverfittingMethodResult] = []
        resolved_base_request = base_request
        if resolved_base_request is None and user_id is not None:
            resolved_base_request = await self._load_backtest_request(
                backtest_result.task_id, user_id
            )
        total_methods = max(len(request.methods), 1)
        for index, method in enumerate(request.methods, start=1):
            if progress_callback is not None:
                await progress_callback(
                    10 + int(((index - 1) / total_methods) * 70),
                    f"正在执行 {method.value} 检测...",
                )
            if method is OverfittingMethod.MONTE_CARLO:
                methods.append(
                    run_monte_carlo_analysis(
                        backtest_result,
                        iterations=request.monte_carlo_iterations,
                        random_seed=request.random_seed,
                    )
                )
            elif method is OverfittingMethod.WALK_FORWARD:
                if resolved_base_request is None or user_id is None:
                    methods.append(self._degraded_placeholder(method))
                else:
                    method_start = 10 + int(((index - 1) / total_methods) * 70)
                    method_end = 10 + int((index / total_methods) * 70)
                    method_span = max(1, method_end - method_start)

                    async def walk_forward_progress(
                        completed: int,
                        total: int,
                        *,
                        bound_start: int = method_start,
                        bound_end: int = method_end,
                        bound_span: int = method_span,
                    ) -> None:
                        if progress_callback is None:
                            return
                        progress = bound_start + int((completed / max(total, 1)) * bound_span)
                        await progress_callback(
                            min(progress, bound_end),
                            f"Walk-forward 窗口 {completed}/{total} 完成",
                        )

                    methods.append(
                        await run_walk_forward_analysis(
                            resolved_base_request,
                            execute_slice=lambda slice_request: self._execute_slice_backtest(
                                user_id,
                                slice_request,
                            ),
                            train_days=request.walk_forward_train_days,
                            test_days=request.walk_forward_test_days,
                            step_days=request.walk_forward_step_days,
                            max_concurrency=request.walk_forward_max_concurrency,
                            progress_callback=walk_forward_progress,
                        )
                    )
            elif method is OverfittingMethod.OUT_OF_SAMPLE:
                if resolved_base_request is None or user_id is None:
                    methods.append(self._degraded_placeholder(method))
                else:
                    methods.append(
                        await run_out_of_sample_analysis(
                            resolved_base_request,
                            execute_slice=lambda slice_request: self._execute_slice_backtest(
                                user_id,
                                slice_request,
                            ),
                            out_of_sample_ratio=request.out_of_sample_ratio,
                        )
                    )
            else:
                methods.append(self._degraded_placeholder(method))
            if progress_callback is not None:
                await progress_callback(
                    10 + int((index / total_methods) * 70),
                    f"{method.value} 检测完成",
                )

        robustness_score = (
            round(sum(item.score for item in methods) / len(methods), 2) if methods else 50.0
        )
        overall_level = self._aggregate_risk_level(methods, robustness_score)
        summary = self._build_summary(methods, overall_level, robustness_score)
        return OverfittingTaskResult(
            task_id="inline-analysis",
            backtest_id=backtest_result.task_id,
            status="completed",
            overall_level=overall_level,
            robustness_score=robustness_score,
            summary=summary,
            methods=methods,
            error_message=None,
        )

    async def _run_task(
        self,
        task_id: str,
        backtest_result: BacktestResult,
        request: OverfittingAnalysisRequest,
    ) -> None:
        model = await self.repo.get_by_field("task_id", task_id)
        if model is None:
            return
        await self.repo.update(
            model.id, {"status": "running", "summary": "过拟合检测执行中。"}, refresh=False
        )
        await self._emit_progress(task_id, 5, "过拟合检测执行中。")
        try:
            result = await self.calculate_analysis(
                backtest_result,
                request,
                user_id=str(model.user_id),
                progress_callback=lambda progress, message: self._emit_progress(
                    task_id,
                    progress,
                    message,
                ),
            )
            payload = {
                "status": "completed",
                "overall_level": result.overall_level.value,
                "robustness_score": result.robustness_score,
                "summary": result.summary,
                "methods": [item.model_dump(mode="json") for item in result.methods],
                "error_message": None,
            }
            await self.repo.update(model.id, payload, refresh=False)
            await ws_manager.send_to_task(
                _overfitting_ws_channel(task_id),
                {
                    "type": MessageType.COMPLETED,
                    "task_id": task_id,
                    "progress": 100,
                    "message": result.summary,
                    "result": result.model_dump(mode="python"),
                },
            )
        except Exception as exc:
            await self.repo.update(
                model.id,
                {
                    "status": "failed",
                    "summary": "过拟合检测执行失败。",
                    "error_message": str(exc),
                },
                refresh=False,
            )
            await ws_manager.send_to_task(
                _overfitting_ws_channel(task_id),
                {
                    "type": MessageType.FAILED,
                    "task_id": task_id,
                    "message": "过拟合检测执行失败。",
                    "error": str(exc),
                },
            )

    async def _emit_progress(self, task_id: str, progress: int, message: str) -> None:
        await ws_manager.send_to_task(
            _overfitting_ws_channel(task_id),
            {
                "type": MessageType.PROGRESS,
                "task_id": task_id,
                "progress": progress,
                "message": message,
                "data": {},
            },
        )

    @staticmethod
    def _aggregate_risk_level(
        methods: list[OverfittingMethodResult],
        robustness_score: float,
    ) -> OverfittingRiskLevel:
        if any(item.risk_level is OverfittingRiskLevel.HIGH for item in methods):
            return OverfittingRiskLevel.HIGH
        if robustness_score >= 75:
            return OverfittingRiskLevel.LOW
        if robustness_score >= 55:
            return OverfittingRiskLevel.MEDIUM
        return OverfittingRiskLevel.HIGH

    @staticmethod
    def _build_summary(
        methods: list[OverfittingMethodResult],
        overall_level: OverfittingRiskLevel,
        robustness_score: float,
    ) -> str:
        if not methods:
            return "未执行任何过拟合检测方法。"
        completed_names = ", ".join(item.method.value for item in methods)
        return (
            f"已完成 {completed_names} 检测；总体风险为 {overall_level.value}，"
            f"稳健性得分 {robustness_score:.2f}。"
        )

    @staticmethod
    def _to_result(model: OverfittingResultModel) -> OverfittingTaskResult:
        return OverfittingTaskResult(
            task_id=str(model.task_id),
            backtest_id=str(model.backtest_id),
            status=str(model.status),
            overall_level=OverfittingRiskLevel(
                str(model.overall_level or OverfittingRiskLevel.MEDIUM.value)
            ),
            robustness_score=round(float(model.robustness_score or 0.0), 2),
            summary=str(model.summary or ""),
            methods=list(model.methods or []),
            error_message=model.error_message,
        )


@lru_cache
def get_overfitting_service() -> OverfittingService:
    return OverfittingService()
