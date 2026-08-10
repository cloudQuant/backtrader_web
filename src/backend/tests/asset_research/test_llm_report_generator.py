"""LLM report generation contracts with citation and budget enforcement."""

import pytest

from app.schemas.asset_research import ReportSection
from app.services.asset_research.llm_guardrails import LlmBudgetLimits
from app.services.asset_research.llm_report_generator import (
    AssetResearchLlmError,
    LlmReportRequest,
    generate_llm_report_sections,
)


def _request() -> LlmReportRequest:
    return LlmReportRequest(
        asset_type="futures",
        canonical_id="futures:CFFEX:IF2609:CNY",
        published_decision={"recommendation": "HOLD", "actionability": "RESEARCH_ONLY"},
        source_evidence_ids=("source:known",),
        outline=(("public_decision", "公开建议"),),
    )


def _limits() -> LlmBudgetLimits:
    return LlmBudgetLimits(
        per_task_tokens=1000,
        daily_tokens=5000,
        monthly_tokens=20000,
        per_task_cost_usd=0.1,
        daily_cost_usd=0.5,
        monthly_cost_usd=2.0,
    )


@pytest.mark.asyncio
async def test_generate_llm_report_sections_requires_known_citations() -> None:
    async def fake_llm(_prompt: str) -> str:
        return '{"sections":[{"section_id":"public_decision","title":"公开建议","markdown":"HOLD","evidence_ids":["source:known"]}]}'

    sections = await generate_llm_report_sections(
        _request(),
        call_llm=fake_llm,
        budget_limits=_limits(),
        allowed_evidence_ids=["source:known"],
    )

    assert sections == [
        ReportSection(
            section_id="public_decision",
            title="公开建议",
            markdown="HOLD",
            evidence_ids=["source:known"],
        )
    ]


@pytest.mark.asyncio
async def test_generate_llm_report_sections_rejects_uncited_output() -> None:
    async def fake_llm(_prompt: str) -> str:
        return '{"sections":[{"section_id":"public_decision","title":"公开建议","markdown":"HOLD","evidence_ids":[]}]}'

    with pytest.raises(AssetResearchLlmError, match="REPORT_CITATION_INVALID"):
        await generate_llm_report_sections(
            _request(),
            call_llm=fake_llm,
            budget_limits=_limits(),
            allowed_evidence_ids=["source:known"],
        )


@pytest.mark.asyncio
async def test_generate_llm_report_sections_handles_call_failure() -> None:
    async def fake_llm(_prompt: str) -> str:
        raise TimeoutError("timeout")

    with pytest.raises(AssetResearchLlmError, match="LLM_REPORT_GENERATION_FAILED"):
        await generate_llm_report_sections(
            _request(),
            call_llm=fake_llm,
            budget_limits=_limits(),
            allowed_evidence_ids=["source:known"],
        )


@pytest.mark.asyncio
async def test_generate_llm_report_sections_enforces_budget() -> None:
    async def fake_llm(_prompt: str) -> str:
        return "{}"

    with pytest.raises(AssetResearchLlmError, match="LLM_REPORT_BUDGET_EXCEEDED"):
        await generate_llm_report_sections(
            _request(),
            call_llm=fake_llm,
            budget_limits=LlmBudgetLimits(
                per_task_tokens=1,
                daily_tokens=1,
                monthly_tokens=1,
                per_task_cost_usd=0.0,
                daily_cost_usd=0.0,
                monthly_cost_usd=0.0,
            ),
            allowed_evidence_ids=["source:known"],
        )

