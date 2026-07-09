"""Strategy version persistence for AI research runs."""

from __future__ import annotations

import difflib
from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from app.db.database import async_session_maker
from app.models.ai_research import (
    AIStrategyResearchVersion,
    AIStrategyResearchVersionComparison,
)
from app.schemas.ai_strategy_research import (
    AIStrategyResearchIteration,
    AIStrategyResearchRunRecord,
    AIStrategyResearchVersionCompareResponse,
    AIStrategyResearchVersionListResponse,
    AIStrategyResearchVersionResponse,
)


class AIStrategyResearchVersionService:
    """Create, query, and compare AI research strategy versions."""

    async def create_from_iteration(
        self,
        *,
        user_id: str,
        run_id: str,
        workspace_id: str | None,
        mandate_id: str | None,
        iteration: AIStrategyResearchIteration,
    ) -> AIStrategyResearchVersionResponse:
        version_no, parent_version_id = await self._next_version_context(user_id, run_id)
        review = {
            "diagnostics": iteration.diagnostics or {},
            "improvement_plan": iteration.improvement_plan or [],
            "next_actions": iteration.next_actions or [],
            "failure_reason": iteration.failure_reason,
            "validation_status": iteration.validation_status,
            "validation_failures": iteration.validation_failures,
        }
        model = AIStrategyResearchVersion(
            user_id=user_id,
            run_id=run_id,
            workspace_id=workspace_id,
            mandate_id=mandate_id,
            strategy_id=iteration.strategy.id,
            unit_id=iteration.unit.id,
            backtest_task_id=iteration.run_result.task_id,
            version_no=version_no,
            version_name=f"v{version_no}",
            parent_version_id=parent_version_id,
            strategy_name=iteration.strategy.name,
            code=iteration.strategy.code or "",
            params=_params_payload(iteration.strategy.params),
            ai_rationale=_ai_rationale(iteration),
            change_summary=_change_summary(iteration),
            backtest_metrics=dict(iteration.metrics or {}),
            quality_gate_evaluations=list(iteration.quality_gate_evaluations or []),
            quality_gate_status="passed" if iteration.passed else "failed",
            review=review,
        )
        async with async_session_maker() as session:
            session.add(model)
            await session.commit()
            await session.refresh(model)
        return self._to_response(model)

    async def list_versions(
        self,
        user_id: str,
        run_id: str,
    ) -> AIStrategyResearchVersionListResponse:
        async with async_session_maker() as session:
            result = await session.execute(
                select(AIStrategyResearchVersion)
                .where(
                    AIStrategyResearchVersion.user_id == user_id,
                    AIStrategyResearchVersion.run_id == run_id,
                )
                .order_by(AIStrategyResearchVersion.version_no.asc())
            )
            items = [self._to_response(model) for model in result.scalars().all()]
        return AIStrategyResearchVersionListResponse(run_id=run_id, total=len(items), items=items)

    async def get_version(
        self,
        user_id: str,
        version_id: str,
    ) -> AIStrategyResearchVersionResponse | None:
        model = await self._get_model(user_id, version_id)
        return self._to_response(model) if model is not None else None

    async def compare_versions(
        self,
        user_id: str,
        left_id: str,
        right_id: str,
    ) -> AIStrategyResearchVersionCompareResponse | None:
        left = await self._get_model(user_id, left_id)
        right = await self._get_model(user_id, right_id)
        if left is None or right is None:
            return None
        if left.run_id != right.run_id:
            raise ValueError("AI research versions belong to different runs")

        metric_deltas = _metric_deltas(left.backtest_metrics, right.backtest_metrics)
        gate_deltas = {
            "left_status": left.quality_gate_status,
            "right_status": right.quality_gate_status,
            "improved": right.quality_gate_status == "passed"
            and left.quality_gate_status != "passed",
        }
        code_diff = _code_diff(left, right)
        verdict, summary = _comparison_summary(left, right, metric_deltas, gate_deltas)
        comparison = AIStrategyResearchVersionComparison(
            user_id=user_id,
            run_id=left.run_id,
            left_version_id=left.id,
            right_version_id=right.id,
            metric_deltas=metric_deltas,
            gate_deltas=gate_deltas,
            code_diff=code_diff,
            verdict=verdict,
            summary=summary,
        )
        async with async_session_maker() as session:
            session.add(comparison)
            await session.commit()

        return AIStrategyResearchVersionCompareResponse(
            run_id=left.run_id,
            left=self._to_response(left),
            right=self._to_response(right),
            metric_deltas=metric_deltas,
            gate_deltas=gate_deltas,
            code_diff=code_diff,
            verdict=verdict,
            summary=summary,
        )

    def synthesize_from_run_record(
        self,
        record: AIStrategyResearchRunRecord,
    ) -> AIStrategyResearchVersionListResponse:
        items: list[AIStrategyResearchVersionResponse] = []
        for index, payload in enumerate(record.iterations or [], start=1):
            if not isinstance(payload, dict):
                continue
            strategy = payload.get("strategy_snapshot")
            if not isinstance(strategy, dict):
                strategy = payload.get("strategy") if isinstance(payload.get("strategy"), dict) else {}
            unit = payload.get("unit_snapshot")
            if not isinstance(unit, dict):
                unit = payload.get("unit") if isinstance(payload.get("unit"), dict) else {}
            diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
            version_no = int(payload.get("iteration") or index)
            items.append(
                AIStrategyResearchVersionResponse(
                    id=f"synthetic-{record.run_id}-{version_no}",
                    run_id=record.run_id,
                    workspace_id=record.research_workspace_id,
                    mandate_id=record.mandate_id,
                    strategy_id=_optional_text(strategy.get("id") or payload.get("strategy_id")),
                    unit_id=_optional_text(unit.get("id") or payload.get("unit_id")),
                    backtest_task_id=_optional_text(payload.get("task_id")),
                    version_no=version_no,
                    version_name=f"v{version_no}",
                    parent_version_id=None,
                    strategy_name=_optional_text(
                        strategy.get("name") or payload.get("strategy_name")
                    ),
                    code=str(strategy.get("code") or payload.get("strategy_code") or ""),
                    params=dict(strategy.get("params") or {}),
                    ai_rationale=_rationale_from_payload(payload),
                    change_summary=str(diagnostics.get("summary") or ""),
                    backtest_metrics=dict(payload.get("metrics") or {}),
                    quality_gate_evaluations=list(payload.get("quality_gate_evaluations") or []),
                    quality_gate_status="passed" if payload.get("passed") else "failed",
                    review=dict(diagnostics or {}),
                    created_at=record.completed_at,
                    updated_at=record.completed_at,
                )
            )
        return AIStrategyResearchVersionListResponse(
            run_id=record.run_id,
            total=len(items),
            items=items,
        )

    async def _next_version_context(self, user_id: str, run_id: str) -> tuple[int, str | None]:
        async with async_session_maker() as session:
            max_result = await session.execute(
                select(func.max(AIStrategyResearchVersion.version_no)).where(
                    AIStrategyResearchVersion.user_id == user_id,
                    AIStrategyResearchVersion.run_id == run_id,
                )
            )
            current_max = max_result.scalar_one_or_none() or 0
            parent_id = None
            if current_max:
                parent_result = await session.execute(
                    select(AIStrategyResearchVersion.id).where(
                        AIStrategyResearchVersion.user_id == user_id,
                        AIStrategyResearchVersion.run_id == run_id,
                        AIStrategyResearchVersion.version_no == current_max,
                    )
                )
                parent_id = parent_result.scalar_one_or_none()
        return int(current_max) + 1, parent_id

    async def _get_model(
        self,
        user_id: str,
        version_id: str,
    ) -> AIStrategyResearchVersion | None:
        async with async_session_maker() as session:
            result = await session.execute(
                select(AIStrategyResearchVersion).where(
                    AIStrategyResearchVersion.user_id == user_id,
                    AIStrategyResearchVersion.id == version_id,
                )
            )
            return result.scalar_one_or_none()

    def _to_response(self, model: AIStrategyResearchVersion) -> AIStrategyResearchVersionResponse:
        return AIStrategyResearchVersionResponse(
            id=model.id,
            run_id=model.run_id,
            workspace_id=model.workspace_id,
            mandate_id=model.mandate_id,
            strategy_id=model.strategy_id,
            unit_id=model.unit_id,
            backtest_task_id=model.backtest_task_id,
            version_no=model.version_no,
            version_name=model.version_name,
            parent_version_id=model.parent_version_id,
            strategy_name=model.strategy_name,
            code=model.code,
            params=dict(model.params or {}),
            ai_rationale=model.ai_rationale,
            change_summary=model.change_summary,
            backtest_metrics=dict(model.backtest_metrics or {}),
            quality_gate_evaluations=list(model.quality_gate_evaluations or []),
            quality_gate_status=model.quality_gate_status,
            review=dict(model.review or {}),
            created_at=_iso(model.created_at),
            updated_at=_iso(model.updated_at),
        )


def _params_payload(params: Any) -> dict[str, Any]:
    if not isinstance(params, dict):
        return {}
    return {
        key: value.model_dump(mode="json") if hasattr(value, "model_dump") else value
        for key, value in params.items()
    }


def _ai_rationale(iteration: AIStrategyResearchIteration) -> str:
    notes = [str(item).strip() for item in iteration.improvement_notes if str(item or "").strip()]
    if notes:
        return "；".join(notes)
    diagnostics = iteration.diagnostics or {}
    generation = diagnostics.get("strategy_generation") if isinstance(diagnostics, dict) else None
    if isinstance(generation, dict):
        source = str(generation.get("source") or generation.get("phase") or "").strip()
        if source:
            return f"AI生成来源：{source}"
    return "首轮策略生成版本。"


def _change_summary(iteration: AIStrategyResearchIteration) -> str:
    diagnostics = iteration.diagnostics or {}
    summary = str(diagnostics.get("summary") or "").strip() if isinstance(diagnostics, dict) else ""
    if summary:
        return summary
    if iteration.failure_reason:
        return iteration.failure_reason
    return "策略版本已完成回测并记录指标。"


def _metric_deltas(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    left_metrics = dict(left or {})
    right_metrics = dict(right or {})
    keys = sorted(set(left_metrics) | set(right_metrics))
    result: dict[str, Any] = {}
    for key in keys:
        left_value = _optional_number(left_metrics.get(key))
        right_value = _optional_number(right_metrics.get(key))
        if left_value is None and right_value is None:
            continue
        result[key] = {
            "left": left_value,
            "right": right_value,
            "delta": None if left_value is None or right_value is None else right_value - left_value,
        }
    return result


def _code_diff(left: AIStrategyResearchVersion, right: AIStrategyResearchVersion) -> str:
    return "\n".join(
        difflib.unified_diff(
            (left.code or "").splitlines(),
            (right.code or "").splitlines(),
            fromfile=left.version_name,
            tofile=right.version_name,
            lineterm="",
        )
    )


def _comparison_summary(
    left: AIStrategyResearchVersion,
    right: AIStrategyResearchVersion,
    metric_deltas: dict[str, Any],
    gate_deltas: dict[str, Any],
) -> tuple[str, str]:
    sharpe_delta = _delta_for(metric_deltas, "sharpe_ratio", "sharpe")
    return_delta = _delta_for(metric_deltas, "annual_return", "total_return")
    drawdown_delta = _delta_for(metric_deltas, "max_drawdown")
    if gate_deltas.get("improved") or (sharpe_delta is not None and sharpe_delta > 0):
        verdict = "improved"
    elif sharpe_delta is not None and sharpe_delta < 0:
        verdict = "regressed"
    else:
        verdict = "mixed"
    parts = [f"{left.version_name} -> {right.version_name}: {verdict}"]
    if sharpe_delta is not None:
        parts.append(f"Sharpe变化 {sharpe_delta:+.4f}")
    if return_delta is not None:
        parts.append(f"收益变化 {return_delta:+.4f}")
    if drawdown_delta is not None:
        parts.append(f"回撤变化 {drawdown_delta:+.4f}")
    if right.quality_gate_status == "passed":
        parts.append("右侧版本通过质量门槛")
    return verdict, "；".join(parts)


def _delta_for(metric_deltas: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        payload = metric_deltas.get(key)
        if isinstance(payload, dict):
            value = _optional_number(payload.get("delta"))
            if value is not None:
                return value
    return None


def _optional_number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _rationale_from_payload(payload: dict[str, Any]) -> str:
    notes = payload.get("improvement_notes")
    if isinstance(notes, list):
        joined = "；".join(str(item).strip() for item in notes if str(item or "").strip())
        if joined:
            return joined
    return "历史投研摘要恢复版本。"


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""
