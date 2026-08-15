"""Optional LLM report generation with citation and budget guardrails."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.middleware.metrics import (
    record_asset_research_llm_fallback,
    record_asset_research_llm_tokens,
)
from app.schemas.asset_research import ReportSection
from app.services.asset_research.citation_verifier import verify_section_citations
from app.services.asset_research.llm_guardrails import (
    LlmBudgetLimits,
    check_token_budget,
)


class AssetResearchLlmError(ValueError):
    """Stable error for LLM report generation and citation failures."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class LlmReportRequest:
    """One bounded report-generation request with immutable public inputs."""

    asset_type: str
    canonical_id: str
    published_decision: Mapping[str, Any]
    source_evidence_ids: tuple[str, ...]
    outline: tuple[tuple[str, str], ...]
    model_tier: str = "DEFAULT"


LlmCall = Callable[[str], Awaitable[str]]


async def generate_llm_report_sections(
    request: LlmReportRequest,
    *,
    call_llm: LlmCall,
    budget_limits: LlmBudgetLimits,
    allowed_evidence_ids: Sequence[str],
) -> list[ReportSection]:
    """Generate and verify LLM report sections before they can enter exports.

    The returned sections are only trusted after every section has a known
    evidence ID.  Budget checks happen before the call and after parsing so a
    malformed or overlong response cannot bypass the cost guard.
    """
    prompt = _build_prompt(request)
    estimated_tokens = max(1, len(prompt) // 4)
    token_decision = check_token_budget(
        used_tokens=0,
        requested_tokens=estimated_tokens,
        limits=budget_limits,
    )
    if not token_decision.allowed:
        record_asset_research_llm_fallback(
            asset_type=request.asset_type,
            fallback_stage="REPORT",
            reason=token_decision.fallback_reason or "BUDGET",
        )
        raise AssetResearchLlmError("LLM_REPORT_BUDGET_EXCEEDED")

    try:
        raw_output = await call_llm(prompt)
    except Exception as exc:
        reason = _fallback_reason(exc)
        record_asset_research_llm_fallback(
            asset_type=request.asset_type,
            fallback_stage="REPORT",
            reason=reason,
        )
        raise AssetResearchLlmError("LLM_REPORT_GENERATION_FAILED") from exc

    record_asset_research_llm_tokens(
        asset_type=request.asset_type,
        stage="REPORT",
        model_tier=request.model_tier,
        tokens=estimated_tokens,
    )
    sections = _parse_sections(raw_output)
    verification = verify_section_citations(sections, allowed_evidence_ids=allowed_evidence_ids)
    if not verification.passed:
        record_asset_research_llm_fallback(
            asset_type=request.asset_type,
            fallback_stage="REPORT",
            reason="OUTPUT_INVALID",
        )
        raise AssetResearchLlmError("REPORT_CITATION_INVALID")
    return sections


def _build_prompt(request: LlmReportRequest) -> str:
    return json.dumps(
        {
            "task": "generate_public_report_sections",
            "asset_type": request.asset_type,
            "canonical_id": request.canonical_id,
            "published_decision": dict(request.published_decision),
            "source_evidence_ids": request.source_evidence_ids,
            "outline": request.outline,
            "constraints": [
                "只输出 JSON sections",
                "每个 section 必须引用已知 evidence_id",
                "不得改写已发布决策",
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _parse_sections(raw_output: str) -> list[ReportSection]:
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise AssetResearchLlmError("LLM_REPORT_OUTPUT_INVALID") from exc
    sections = payload.get("sections") if isinstance(payload, dict) else None
    if not isinstance(sections, list):
        raise AssetResearchLlmError("LLM_REPORT_OUTPUT_INVALID")
    try:
        return [ReportSection.model_validate(item) for item in sections if isinstance(item, dict)]
    except Exception as exc:
        raise AssetResearchLlmError("LLM_REPORT_OUTPUT_INVALID") from exc


def _fallback_reason(error: BaseException) -> str:
    message = str(error).upper()
    if any(token in message for token in ("429", "RATE_LIMIT")):
        return "RATE_LIMIT"
    if "TIMEOUT" in message:
        return "TIMEOUT"
    return "MODEL_UNAVAILABLE"
