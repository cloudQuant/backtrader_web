"""Pipeline event persistence for AI research runs."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.db import database
from app.models.ai_research import ResearchPipelineEvent
from app.schemas.ai_strategy_research import (
    AIStrategyResearchRunRecord,
    ResearchPipelineEventResponse,
    ResearchTimelineResponse,
)

logger = logging.getLogger(__name__)


class ResearchPipelineEventService:
    """Persist and query auditable AI research timeline events."""

    async def create_event(
        self,
        *,
        user_id: str,
        run_id: str,
        stage: str,
        status: str,
        workspace_id: str | None = None,
        mandate_id: str | None = None,
        iteration: int | None = None,
        summary: str | None = None,
        input_payload: dict[str, Any] | None = None,
        output_payload: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ResearchPipelineEventResponse:
        model = ResearchPipelineEvent(
            user_id=user_id,
            run_id=run_id,
            workspace_id=workspace_id,
            mandate_id=mandate_id,
            stage=stage,
            status=status,
            iteration=iteration,
            summary=summary,
            input_payload=_json_dict(input_payload),
            output_payload=_json_dict(output_payload),
            metrics=_json_dict(metrics),
            error=error,
        )
        async with database.async_session_maker() as session:
            session.add(model)
            await session.commit()
            await session.refresh(model)
        return self._to_response(model)

    async def safe_create_event(self, **kwargs: Any) -> ResearchPipelineEventResponse | None:
        try:
            return await self.create_event(**kwargs)
        except Exception:
            logger.debug("Failed to persist AI research pipeline event", exc_info=True)
            return None

    async def list_events(
        self,
        user_id: str,
        run_id: str,
        *,
        workspace_id: str | None = None,
    ) -> ResearchTimelineResponse:
        filters = [
            ResearchPipelineEvent.user_id == user_id,
            ResearchPipelineEvent.run_id == run_id,
        ]
        if workspace_id:
            filters.append(ResearchPipelineEvent.workspace_id == workspace_id)
        async with database.async_session_maker() as session:
            result = await session.execute(
                select(ResearchPipelineEvent)
                .where(*filters)
                .order_by(ResearchPipelineEvent.created_at.asc(), ResearchPipelineEvent.id.asc())
            )
            items = [self._to_response(model) for model in result.scalars().all()]
        return ResearchTimelineResponse(run_id=run_id, total=len(items), items=items)

    def synthesize_from_run_record(
        self,
        record: AIStrategyResearchRunRecord,
    ) -> ResearchTimelineResponse:
        """Build a read-only timeline for legacy runs that predate event persistence."""
        items: list[ResearchPipelineEventResponse] = [
            _synthetic_event(
                run_id=record.run_id,
                workspace_id=record.research_workspace_id,
                mandate_id=record.mandate_id,
                stage="initializing",
                status="completed",
                summary="投研记录已从历史运行摘要恢复。",
                created_at=record.started_at,
            )
        ]
        for payload in record.iterations:
            if not isinstance(payload, dict):
                continue
            iteration = _optional_int(payload.get("iteration"))
            metrics = (
                dict(payload.get("metrics") or {})
                if isinstance(payload.get("metrics"), dict)
                else {}
            )
            failure = str(payload.get("failure_reason") or "").strip() or None
            items.append(
                _synthetic_event(
                    run_id=record.run_id,
                    workspace_id=record.research_workspace_id,
                    mandate_id=record.mandate_id,
                    stage="backtesting",
                    status="failed" if failure else "completed",
                    iteration=iteration,
                    summary=f"第 {iteration or len(items)} 轮回测完成。",
                    metrics=metrics,
                    error=failure,
                    created_at=record.completed_at,
                )
            )
            diagnostics = payload.get("diagnostics") if isinstance(payload, dict) else {}
            summary = (
                str(diagnostics.get("summary") or "").strip()
                if isinstance(diagnostics, dict)
                else ""
            )
            items.append(
                _synthetic_event(
                    run_id=record.run_id,
                    workspace_id=record.research_workspace_id,
                    mandate_id=record.mandate_id,
                    stage="strategy_review",
                    status="completed",
                    iteration=iteration,
                    summary=summary or "策略审查已记录在历史摘要中。",
                    output_payload=dict(diagnostics or {}) if isinstance(diagnostics, dict) else {},
                    created_at=record.completed_at,
                )
            )
        items.append(
            _synthetic_event(
                run_id=record.run_id,
                workspace_id=record.research_workspace_id,
                mandate_id=record.mandate_id,
                stage=record.pipeline.get("current_stage") or record.status,
                status="completed" if record.achieved else record.status,
                summary=record.next_actions[0] if record.next_actions else "AI投研运行已完成。",
                metrics=dict(record.best_metrics or {}),
                created_at=record.completed_at,
            )
        )
        return ResearchTimelineResponse(run_id=record.run_id, total=len(items), items=items)

    def _to_response(self, model: ResearchPipelineEvent) -> ResearchPipelineEventResponse:
        return ResearchPipelineEventResponse(
            id=model.id,
            run_id=model.run_id,
            workspace_id=model.workspace_id,
            mandate_id=model.mandate_id,
            stage=model.stage,
            status=model.status,
            iteration=model.iteration,
            summary=model.summary,
            input_payload=dict(model.input_payload or {}),
            output_payload=dict(model.output_payload or {}),
            metrics=dict(model.metrics or {}),
            error=model.error,
            created_at=_iso(model.created_at),
        )


def _json_dict(value: dict[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


def _iso(value: Any) -> str:
    return value.isoformat() if isinstance(value, datetime) else ""


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _synthetic_event(
    *,
    run_id: str,
    stage: str,
    status: str,
    workspace_id: str | None = None,
    mandate_id: str | None = None,
    iteration: int | None = None,
    summary: str | None = None,
    input_payload: dict[str, Any] | None = None,
    output_payload: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    error: str | None = None,
    created_at: str = "",
) -> ResearchPipelineEventResponse:
    return ResearchPipelineEventResponse(
        id=f"synthetic-{run_id}-{stage}-{iteration or 0}-{len(summary or '')}",
        run_id=run_id,
        workspace_id=workspace_id,
        mandate_id=mandate_id,
        stage=stage,
        status=status,
        iteration=iteration,
        summary=summary,
        input_payload=_json_dict(input_payload),
        output_payload=_json_dict(output_payload),
        metrics=_json_dict(metrics),
        error=error,
        created_at=created_at,
    )
