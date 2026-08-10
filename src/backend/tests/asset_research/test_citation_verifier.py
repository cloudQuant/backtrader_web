"""Citation and candidate-leak verification contracts for LLM reports."""

from app.schemas.asset_research import ReportSection
from app.services.asset_research.citation_verifier import (
    verify_public_payload,
    verify_section_citations,
)


def test_section_citations_require_known_evidence_ids() -> None:
    sections = [
        ReportSection(
            section_id="public_decision",
            title="公开建议",
            markdown="公开建议：HOLD",
            evidence_ids=["decision:known"],
        ),
        ReportSection(
            section_id="source_quality",
            title="来源质量",
            markdown="来源：fixture",
            evidence_ids=["source:unknown"],
        ),
        ReportSection(
            section_id="history",
            title="历史",
            markdown="无历史",
            evidence_ids=[],
        ),
    ]

    result = verify_section_citations(
        sections,
        allowed_evidence_ids={"decision:known", "source:known"},
    )

    assert result.passed is False
    assert result.missing_evidence_ids == ("source:unknown",)
    assert result.sections_without_evidence == ("history",)


def test_public_payload_rejects_candidate_only_fields() -> None:
    payload = {
        "published_decision": {
            "recommendation": "HOLD",
            "actionability": "RESEARCH_ONLY",
        },
        "candidate_decision_json": {"recommendation": "BUY"},
        "sections": [
            {
                "section_id": "public_decision",
                "title": "公开建议",
                "markdown": "HOLD",
                "evidence_ids": ["decision:known"],
            }
        ],
    }

    result = verify_public_payload(payload)

    assert result.passed is False
    assert result.candidate_fields_exposed == ("candidate_decision_json",)


def test_public_payload_passes_with_known_citations() -> None:
    payload = {
        "published_decision": {"recommendation": "HOLD"},
        "sections": [
            {
                "section_id": "public_decision",
                "title": "公开建议",
                "markdown": "HOLD",
                "evidence_ids": ["decision:known"],
            }
        ],
    }

    result = verify_public_payload(payload)

    assert result.passed is True

