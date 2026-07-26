"""Task service for native stock analysis."""

from __future__ import annotations

import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import async_session_maker
from app.models.ai_call_log import AICallLog
from app.models.knowledge_base import ChatMessage, KBDocument, KnowledgeBase
from app.models.stock_analysis import (
    StockAnalysisExportModel,
    StockAnalysisReportModel,
    StockAnalysisTaskModel,
)
from app.models.workspace import Workspace
from app.schemas.ai_observability import AICallStatus
from app.schemas.stock_analysis import StockAnalysisParams
from app.services.ai_observability.cost_calculator import calculate_estimated_cost_usd
from app.services.ai_observability.logger import hash_prompt
from app.services.stock_analysis.analysis_engine import StockAnalysisEngine
from app.services.stock_analysis.data_collector import StockAnalysisDataCollector
from app.services.stock_analysis.exporter import StockAnalysisExporter
from app.services.stock_analysis.pipeline import StockAnalysisPipeline
from app.services.stock_analysis.report_builder import StockAnalysisReportBuilder


class StockAnalysisCancelled(RuntimeError):
    """Raised internally when a stock analysis task has been cancelled."""


class StockAnalysisConcurrencyLimitExceeded(RuntimeError):
    """Raised when a user already has too many active stock analysis tasks."""

    def __init__(self, *, active_count: int, limit: int) -> None:
        self.active_count = active_count
        self.limit = limit
        super().__init__(f"stock analysis active task limit exceeded: {active_count}/{limit}")


class StockAnalysisTaskService:
    """Create, run, read, and export stock analysis tasks."""

    MAX_ACTIVE_TASKS_PER_USER = 3
    ACTIVE_STATUSES = {"pending", "running"}
    MAX_EXPORT_RECORDS_PER_REPORT_FORMAT = 5

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.collector = StockAnalysisDataCollector(db)
        self.pipeline = StockAnalysisPipeline()
        self.analysis_engine = StockAnalysisEngine(db)
        self.report_builder = StockAnalysisReportBuilder()
        self.exporter = StockAnalysisExporter()

    async def create_and_run(
        self,
        *,
        user_id: str,
        params: StockAnalysisParams,
        request_text: str = "",
        conversation_id: str | None = None,
        assistant_message_id: str | None = None,
    ) -> tuple[StockAnalysisTaskModel, StockAnalysisReportModel | None]:
        analysis_date = params.analysis_date or date.today()
        started = time.perf_counter()
        task = await self.create_pending(
            user_id=user_id,
            params=params,
            request_text=request_text,
            conversation_id=conversation_id,
            assistant_message_id=assistant_message_id,
        )
        try:
            report = await self._run_task(task, params, analysis_date)
            await self.db.commit()
            await self.db.refresh(task)
            if report is not None:
                await self.db.refresh(report)
            return task, report
        except Exception as exc:
            await self._record_ai_observability(
                task=task,
                params=params,
                status=AICallStatus.FAILED,
                latency_ms=self._elapsed_ms(started),
                error=exc,
            )
            task.status = "failed"
            task.progress = 100
            task.current_step = "failed"
            task.message = "股票分析失败"
            task.error_message = str(exc)
            task.completed_at = self._now()
            await self.db.commit()
            return task, None

    async def create_pending(
        self,
        *,
        user_id: str,
        params: StockAnalysisParams,
        request_text: str = "",
        conversation_id: str | None = None,
        assistant_message_id: str | None = None,
    ) -> StockAnalysisTaskModel:
        active_count = await self.count_active_tasks(user_id=user_id)
        if active_count >= self.MAX_ACTIVE_TASKS_PER_USER:
            raise StockAnalysisConcurrencyLimitExceeded(
                active_count=active_count,
                limit=self.MAX_ACTIVE_TASKS_PER_USER,
            )
        analysis_date = params.analysis_date or date.today()
        task = StockAnalysisTaskModel(
            user_id=user_id,
            conversation_id=conversation_id,
            assistant_message_id=assistant_message_id,
            symbol=params.symbol,
            market_type=params.market_type,
            analysis_date=analysis_date.isoformat(),
            research_depth=params.research_depth,
            selected_modules=list(params.selected_modules),
            request_text=request_text,
            parameters_json=params.model_dump(mode="json"),
            step_events_json=[],
            data_quality_json={},
            status="pending",
            progress=0,
            current_step="created",
            message="股票分析任务已创建",
        )
        self.db.add(task)
        await self.db.flush()
        return task

    async def count_active_tasks(self, *, user_id: str) -> int:
        return int(
            (
                await self.db.execute(
                    select(func.count())
                    .select_from(StockAnalysisTaskModel)
                    .where(
                        StockAnalysisTaskModel.user_id == user_id,
                        StockAnalysisTaskModel.status.in_(self.ACTIVE_STATUSES),
                    )
                )
            ).scalar_one()
            or 0
        )

    @classmethod
    async def run_pending_task(cls, *, task_id: str, user_id: str) -> None:
        async with async_session_maker() as session:
            service = cls(session)
            task = await service.get_task(user_id=user_id, task_id=task_id)
            if task is None or task.status != "pending":
                return
            params = StockAnalysisParams.model_validate(task.parameters_json or {})
            started = time.perf_counter()
            try:
                report = await service._run_task(
                    task,
                    params,
                    date.fromisoformat(task.analysis_date),
                    commit_progress=True,
                )
                await service._sync_assistant_message_metadata(task, report)
                await session.commit()
            except StockAnalysisCancelled:
                await service._sync_assistant_message_metadata(task, None)
                await session.commit()
            except Exception as exc:
                await service._record_ai_observability(
                    task=task,
                    params=params,
                    status=AICallStatus.FAILED,
                    latency_ms=service._elapsed_ms(started),
                    error=exc,
                )
                task.status = "failed"
                task.progress = 100
                task.current_step = "failed"
                task.message = "股票分析失败"
                task.error_message = str(exc)
                task.completed_at = service._now()
                await service._sync_assistant_message_metadata(task, None)
                await session.commit()

    async def _sync_assistant_message_metadata(
        self, task: StockAnalysisTaskModel, report: StockAnalysisReportModel | None
    ) -> None:
        if not task.assistant_message_id:
            return
        message = (
            await self.db.execute(
                select(ChatMessage).where(
                    ChatMessage.id == task.assistant_message_id,
                    ChatMessage.conversation_id == task.conversation_id,
                )
            )
        ).scalar_one_or_none()
        if message is None:
            return
        metadata = dict(message.metadata_json or {})
        metadata["stock_analysis_task"] = self.task_to_card(task)
        metadata["stock_analysis_report"] = self.report_to_card(report)
        message.metadata_json = metadata

    async def _commit_progress(self) -> None:
        await self.db.commit()

    async def _stop_if_cancelled(self, task: StockAnalysisTaskModel) -> None:
        await self.db.refresh(task)
        if task.status == "cancelled":
            raise StockAnalysisCancelled("stock analysis task cancelled")

    async def _run_task(
        self,
        task: StockAnalysisTaskModel,
        params: StockAnalysisParams,
        analysis_date: date,
        *,
        commit_progress: bool = False,
    ) -> StockAnalysisReportModel:
        run_started = time.perf_counter()
        self._mark(task, 5, "running", "data_collection", "正在采集股票研究数据")
        if commit_progress:
            await self._commit_progress()
            await self._stop_if_cancelled(task)
        snapshot = await self.collector.collect(
            user_id=task.user_id,
            symbol=task.symbol,
            market_type=task.market_type,
            analysis_date=analysis_date,
        )
        task.symbol_name = (snapshot.get("info") or {}).get("name") or task.symbol
        task.data_quality_json = snapshot.get("data_quality") or {}

        if commit_progress:
            await self._stop_if_cancelled(task)
        self._mark(task, 35, "running", "compat_pipeline", "正在执行兼容分析流水线")
        if commit_progress:
            await self._commit_progress()
            await self._stop_if_cancelled(task)
        pipeline_output = await self.pipeline.run(
            symbol=task.symbol,
            market_type=task.market_type,
            research_depth=task.research_depth,
            selected_modules=list(task.selected_modules or []),
            snapshot=snapshot,
        )
        if params.model_id and await self.analysis_engine.can_generate(
            user_id=task.user_id,
            model_id=params.model_id,
        ):
            if commit_progress:
                await self._stop_if_cancelled(task)
            self._mark(task, 60, "running", "ai_stage_generation", "正在执行 AI 阶段增强")
            if commit_progress:
                await self._commit_progress()
                await self._stop_if_cancelled(task)
            pipeline_output = await self.analysis_engine.enhance(
                task_id=task.id,
                user_id=task.user_id,
                model_id=params.model_id,
                symbol=task.symbol,
                market_type=task.market_type,
                research_depth=task.research_depth,
                selected_modules=list(task.selected_modules or []),
                snapshot=snapshot,
                pipeline_output=pipeline_output,
            )

        if commit_progress:
            await self._stop_if_cancelled(task)
        self._mark(task, 75, "running", "report_normalization", "正在生成规范化报告")
        if commit_progress:
            await self._commit_progress()
            await self._stop_if_cancelled(task)
        payload = self.report_builder.build(
            symbol=task.symbol,
            symbol_name=task.symbol_name or task.symbol,
            market_type=task.market_type,
            analysis_date=task.analysis_date,
            research_depth=task.research_depth,
            snapshot=snapshot,
            pipeline_output=pipeline_output,
        )
        markdown_content = self.exporter.render_markdown(payload)
        html_content = self.exporter.render_html(payload)
        decision = payload.get("decision") or {}
        scores = pipeline_output.get("scores") or {}
        report = StockAnalysisReportModel(
            task_id=task.id,
            user_id=task.user_id,
            symbol=task.symbol,
            market_type=task.market_type,
            analysis_date=task.analysis_date,
            title=f"{task.symbol} 股票分析报告",
            summary=payload.get("executive_summary") or "",
            recommendation_label=decision.get("label", "持有"),
            confidence_score=decision.get("confidence_score"),
            risk_level=decision.get("risk_level", "中等"),
            technical_score=scores.get("technical_score"),
            fundamental_score=scores.get("fundamental_score"),
            news_score=scores.get("news_score"),
            risk_score=scores.get("risk_score"),
            source_snapshot_json=snapshot,
            data_quality_json=snapshot.get("data_quality") or {},
            report_json=payload,
            markdown_content=markdown_content,
            html_content=html_content,
        )
        self.db.add(report)
        await self.db.flush()

        if commit_progress:
            await self._stop_if_cancelled(task)
        # Publish the report and its compatibility-pipeline audit event before
        # exposing a completed task. Background callers persist progress in a
        # separate session, so consumers can otherwise observe a completed
        # task before either record is queryable.
        await self._record_ai_observability(
            task=task,
            params=params,
            status=AICallStatus.SUCCESS,
            latency_ms=self._elapsed_ms(run_started),
            response_chars=len(payload.get("executive_summary") or ""),
        )
        await self.db.flush()
        if commit_progress:
            await self._commit_progress()
            await self._stop_if_cancelled(task)

        self._mark(task, 100, "completed", "completed", "股票分析已完成")
        task.report_id = report.id
        task.completed_at = self._now()
        return report

    async def _record_ai_observability(
        self,
        *,
        task: StockAnalysisTaskModel,
        params: StockAnalysisParams,
        status: AICallStatus,
        latency_ms: int | None = None,
        response_chars: int = 0,
        error: BaseException | None = None,
    ) -> None:
        model_name = params.model_id or "native-rule-engine"
        self.db.add(
            AICallLog(
                user_id=task.user_id,
                request_id=task.id,
                service_name="stock_analysis",
                mode="compat_pipeline",
                model_name=model_name,
                provider="native",
                prompt_template_id="stock_analysis.compat_pipeline",
                prompt_template_version="v1",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                estimated_cost_usd=calculate_estimated_cost_usd(model_name, 0, 0),
                latency_ms=latency_ms or 0,
                status=status.value,
                error_code=type(error).__name__ if error else None,
                error_message=str(error)[:1000] if error else None,
                response_chars=response_chars,
                prompt_hash=hash_prompt(task.request_text or task.symbol),
            )
        )

    async def cancel_task(self, *, user_id: str, task_id: str) -> StockAnalysisTaskModel | None:
        task = await self.get_task(user_id=user_id, task_id=task_id)
        if task is None:
            return None
        if task.status in {"completed", "failed", "cancelled"}:
            return task
        task.status = "cancelled"
        task.current_step = "cancelled"
        task.message = "股票分析已取消"
        task.progress = 100
        task.completed_at = self._now()
        task.updated_at = self._now()
        events = list(task.step_events_json or [])
        events.append(
            {
                "progress": task.progress,
                "status": task.status,
                "step": task.current_step,
                "message": task.message,
                "timestamp": self._now().isoformat(),
            }
        )
        task.step_events_json = events
        await self._sync_assistant_message_metadata(task, None)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def retry_task(self, *, user_id: str, task_id: str) -> StockAnalysisTaskModel | None:
        task = await self.get_task(user_id=user_id, task_id=task_id)
        if task is None:
            return None
        if task.status != "failed":
            raise ValueError("only_failed_stock_analysis_tasks_can_be_retried")
        params = StockAnalysisParams.model_validate(task.parameters_json or {})
        retry = await self.create_pending(
            user_id=user_id,
            params=params,
            request_text=task.request_text or "",
            conversation_id=task.conversation_id,
        )
        await self.db.commit()
        await self.db.refresh(retry)
        return retry

    async def get_task(self, *, user_id: str, task_id: str) -> StockAnalysisTaskModel | None:
        return (
            await self.db.execute(
                select(StockAnalysisTaskModel).where(
                    StockAnalysisTaskModel.id == task_id,
                    StockAnalysisTaskModel.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

    async def get_report_by_task(
        self, *, user_id: str, task_id: str
    ) -> StockAnalysisReportModel | None:
        return (
            await self.db.execute(
                select(StockAnalysisReportModel).where(
                    StockAnalysisReportModel.task_id == task_id,
                    StockAnalysisReportModel.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

    async def get_report(self, *, user_id: str, report_id: str) -> StockAnalysisReportModel | None:
        return (
            await self.db.execute(
                select(StockAnalysisReportModel).where(
                    StockAnalysisReportModel.id == report_id,
                    StockAnalysisReportModel.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

    async def export_report(
        self, *, user_id: str, report_id: str, export_format: str
    ) -> tuple[StockAnalysisExportModel, bytes] | None:
        report = await self.get_report(user_id=user_id, report_id=report_id)
        if report is None:
            return None
        payload = dict(report.report_json or {})
        content = self.exporter.render(payload, export_format)
        file_name = self.exporter.build_file_name(payload, export_format)
        file_path = self.exporter.save(
            content,
            user_id=user_id,
            report_id=report_id,
            file_name=file_name,
        )
        export = StockAnalysisExportModel(
            report_id=report_id,
            user_id=user_id,
            format=export_format,
            file_name=file_name,
            file_path=str(file_path),
            content_type=self.exporter.CONTENT_TYPES[export_format],
            file_size=len(content),
            status="completed",
        )
        self.db.add(export)
        await self.db.flush()
        await self._prune_export_records(
            user_id=user_id,
            report_id=report_id,
            export_format=export_format,
        )
        await self.db.commit()
        await self.db.refresh(export)
        return export, content

    async def _prune_export_records(
        self,
        *,
        user_id: str,
        report_id: str,
        export_format: str,
    ) -> None:
        exports = (
            (
                await self.db.execute(
                    select(StockAnalysisExportModel)
                    .where(
                        StockAnalysisExportModel.user_id == user_id,
                        StockAnalysisExportModel.report_id == report_id,
                        StockAnalysisExportModel.format == export_format,
                    )
                    .order_by(
                        StockAnalysisExportModel.created_at.desc(),
                        StockAnalysisExportModel.id.desc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        stale_exports = list(exports[self.MAX_EXPORT_RECORDS_PER_REPORT_FORMAT :])
        if not stale_exports:
            return

        kept_paths = {
            self._export_path(row.file_path)
            for row in exports[: self.MAX_EXPORT_RECORDS_PER_REPORT_FORMAT]
        }
        for stale in stale_exports:
            stale_path = self._export_path(stale.file_path)
            if stale_path not in kept_paths:
                try:
                    stale_path.unlink(missing_ok=True)
                except OSError:
                    pass
            await self.db.delete(stale)

    @staticmethod
    def _export_path(file_path: str) -> Path:
        path = Path(file_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve(strict=False)

    async def save_report_to_knowledge_base(
        self,
        *,
        user_id: str,
        report_id: str,
        knowledge_base_id: str,
        title: str | None = None,
        parent_id: str | None = None,
    ) -> KBDocument | None:
        report = await self.get_report(user_id=user_id, report_id=report_id)
        if report is None:
            return None
        kb = (
            await self.db.execute(
                select(KnowledgeBase).where(
                    KnowledgeBase.id == knowledge_base_id,
                    KnowledgeBase.owner_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if kb is None:
            return None
        if parent_id is not None:
            parent = (
                await self.db.execute(
                    select(KBDocument).where(
                        KBDocument.id == parent_id,
                        KBDocument.knowledge_base_id == knowledge_base_id,
                    )
                )
            ).scalar_one_or_none()
            if parent is None:
                raise ValueError("Document parent not found")

        payload = dict(report.report_json or {})
        content = report.markdown_content or self.exporter.render_markdown(payload)
        document = KBDocument(
            knowledge_base_id=knowledge_base_id,
            title=title or report.title,
            content=content,
            content_type="markdown",
            parent_id=parent_id,
            is_folder=False,
            status="draft",
            index_status="not_indexed",
            metadata_json={
                "source": "stock_analysis_report",
                "stock_analysis_report_id": report.id,
                "stock_analysis_task_id": report.task_id,
                "symbol": report.symbol,
                "market_type": report.market_type,
                "analysis_date": report.analysis_date,
                "decision_label": report.recommendation_label,
            },
        )
        self.db.add(document)
        kb.document_count = int(getattr(kb, "document_count", 0) or 0) + 1
        await self.db.commit()
        await self.db.refresh(document)
        return document

    async def save_report_to_workspace(
        self,
        *,
        user_id: str,
        report_id: str,
        workspace_id: str,
        title: str | None = None,
    ) -> dict[str, Any] | None:
        report = await self.get_report(user_id=user_id, report_id=report_id)
        if report is None:
            return None
        workspace = (
            await self.db.execute(
                select(Workspace).where(
                    Workspace.id == workspace_id,
                    Workspace.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if workspace is None:
            return None
        if workspace.workspace_type != "research":
            raise ValueError("workspace_must_be_research")

        saved_at = self._now()
        entry = {
            "report_id": report.id,
            "task_id": report.task_id,
            "title": title or report.title,
            "symbol": report.symbol,
            "market_type": report.market_type,
            "analysis_date": report.analysis_date,
            "summary": report.summary,
            "decision_label": report.recommendation_label,
            "risk_level": report.risk_level,
            "confidence_score": report.confidence_score,
            "saved_at": saved_at.isoformat(),
            "source": "stock_analysis_report",
        }
        settings = dict(workspace.settings or {})
        raw_reports = settings.get("stock_analysis_reports", [])
        if not isinstance(raw_reports, list):
            raw_reports = []
        existing_reports = [
            item
            for item in raw_reports
            if isinstance(item, dict) and item.get("report_id") != report.id
        ]
        existing_reports.append(entry)
        settings["stock_analysis_reports"] = existing_reports[-50:]
        workspace.settings = settings
        workspace.updated_at = saved_at
        await self.db.commit()
        return entry

    def task_to_card(self, task: StockAnalysisTaskModel) -> dict[str, Any]:
        return {
            "task_id": task.id,
            "symbol": task.symbol,
            "status": task.status,
            "progress": int(task.progress or 0),
            "current_step": task.current_step,
            "message": task.message,
        }

    def report_to_card(self, report: StockAnalysisReportModel | None) -> dict[str, Any] | None:
        if report is None:
            return None
        return {
            "report_id": report.id,
            "symbol": report.symbol,
            "summary": report.summary,
            "decision_label": report.recommendation_label,
            "risk_level": report.risk_level,
            "confidence_score": report.confidence_score,
            "export_formats": ["markdown", "html", "docx", "pdf"],
        }

    @staticmethod
    def parse_params_from_question(question: str) -> StockAnalysisParams:
        text = str(question or "").strip()
        symbol = "000001.SZ"
        match = re.search(r"\b(\d{6}\.(?:SZ|SH)|\d{6}|[A-Z]{1,6})\b", text.upper())
        if match:
            symbol = match.group(1)
        if re.fullmatch(r"\d{6}", symbol):
            symbol = f"{symbol}.SZ" if not symbol.startswith("6") else f"{symbol}.SH"
        market_type = "A股"
        if "美股" in text or re.fullmatch(r"[A-Z]{1,6}", symbol):
            market_type = "美股"
        if "港股" in text:
            market_type = "港股"
        depth = "标准"
        for candidate in ("快速", "基础", "标准", "深度", "全面"):
            if candidate in text:
                depth = candidate
                break
        return StockAnalysisParams(
            symbol=symbol,
            market_type=market_type,
            research_depth=depth,
            selected_modules=["market", "social", "news", "fundamentals", "risk"],
        )

    def _mark(
        self,
        task: StockAnalysisTaskModel,
        progress: int,
        status: str,
        step: str,
        message: str,
    ) -> None:
        task.progress = progress
        task.status = status
        task.current_step = step
        task.message = message
        task.updated_at = self._now()
        if status == "running" and task.started_at is None:
            task.started_at = self._now()
        events = list(task.step_events_json or [])
        events.append(
            {
                "progress": progress,
                "status": status,
                "step": step,
                "message": message,
                "timestamp": self._now().isoformat(),
            }
        )
        task.step_events_json = events

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, int((time.perf_counter() - started) * 1000))
