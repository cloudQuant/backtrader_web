"""Public reports can be exported or published without carrying a candidate decision."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.asset_research import AssetAnalysisReport, AssetDataSourceRegistry
from app.models.knowledge_base import KBDocument, KnowledgeBase
from app.models.user import User
from app.schemas.asset_research import (
    AssetAnalysisCreateRequest,
    FuturesIdentityDetails,
    InstrumentIdentity,
    RawAssetSnapshot,
)
from app.services.asset_research import artifacts as artifacts_module
from app.services.asset_research.artifacts import (
    AssetResearchArtifactError,
    AssetResearchReportArtifactsService,
)
from app.services.asset_research.orchestrator import AssetResearchOrchestrator


class _Data:
    async def collect(
        self, identity: InstrumentIdentity, *, cutoff_at: datetime
    ) -> RawAssetSnapshot:
        return RawAssetSnapshot(
            identity=identity,
            cutoff_at=cutoff_at,
            retrieved_at=cutoff_at,
            raw_schema_version="fixture-v1",
            raw_fields={"snapshot": {"price": 101}},
            history_rows=[
                {"date": "2026-07-31", "close": 100},
                {"date": "2026-08-01", "close": 101},
            ],
            source_manifest={
                "provider": "artifact-fixture",
                "capabilities": ["price", "contract_calendar"],
            },
            license_tags=[],
            content_hash="f" * 64,
        )


@pytest.mark.parametrize(
    "relative_path",
    [Path("../outside.md"), Path("/tmp/asset-research-outside.md")],
)
def test_report_export_rejects_paths_outside_its_storage_root(tmp_path, relative_path: Path) -> None:
    """Stored export URIs cannot escape the configured artifact root."""
    artifacts = AssetResearchReportArtifactsService(None, storage_root=tmp_path)  # type: ignore[arg-type]

    with pytest.raises(AssetResearchArtifactError, match="EXPORT_PATH_INVALID"):
        artifacts._safe_output_path(relative_path)


def test_pdf_export_escapes_html_and_redacts_candidate_decisions(monkeypatch, tmp_path) -> None:
    """PDF generation must not turn report text into executable markup or export shadow data."""

    class _FakeHtml:
        rendered_html = ""

        def __init__(self, *, string: str) -> None:
            type(self).rendered_html = string

        def write_pdf(self) -> bytes:
            return b"%PDF-fixture"

    monkeypatch.setattr("weasyprint.HTML", _FakeHtml)
    report = SimpleNamespace(
        sections_json={
            "meta": {
                "name": "期货研究",
                "display_symbol": "IF2609",
                "asset_type": "futures",
                "canonical_id": "futures:CFFEX:IF2609:CNY",
            },
            "published_decision": {"recommendation": "HOLD", "actionability": "RESEARCH_ONLY"},
            "candidate_decision": {"private_note": "candidate-secret"},
            "sections": [
                {
                    "section_id": "public_decision",
                    "title": "公开建议",
                    "markdown": "<script>alert('xss')</script>",
                    "evidence_ids": ["source:known"],
                }
            ],
            "disclaimer": "仅供研究。",
        }
    )
    artifacts = AssetResearchReportArtifactsService(None, storage_root=tmp_path)  # type: ignore[arg-type]

    assert artifacts._render_public_export(report, "PDF") == b"%PDF-fixture"
    assert "<script" not in _FakeHtml.rendered_html
    assert "&lt;script&gt;" in _FakeHtml.rendered_html
    assert "candidate-secret" not in _FakeHtml.rendered_html


def test_public_report_export_rejects_sections_without_evidence(tmp_path) -> None:
    """LLM content without citations must not be exported as a public report."""
    report = SimpleNamespace(
        sections_json={
            "meta": {"name": "期货研究", "asset_type": "futures"},
            "published_decision": {"recommendation": "HOLD", "actionability": "RESEARCH_ONLY"},
            "sections": [
                {
                    "section_id": "public_decision",
                    "title": "公开建议",
                    "markdown": "HOLD",
                    "evidence_ids": [],
                }
            ],
            "disclaimer": "仅供研究。",
        }
    )
    artifacts = AssetResearchReportArtifactsService(None, storage_root=tmp_path)  # type: ignore[arg-type]

    with pytest.raises(AssetResearchArtifactError, match="REPORT_CITATION_INVALID"):
        artifacts._render_public_export(report, "MARKDOWN")


def test_public_report_payload_redacts_credentials_from_a_corrupt_legacy_row(tmp_path) -> None:
    """A defensive public read must remove credentials beyond candidate fields."""
    report = SimpleNamespace(
        sections_json={
            "meta": {
                "name": "期货研究",
                "display_symbol": "IF2609",
                "asset_type": "futures",
                "canonical_id": "futures:CFFEX:IF2609:CNY",
                "api_key": "legacy-api-secret",
            },
            "published_decision": {"recommendation": "HOLD", "actionability": "RESEARCH_ONLY"},
            "sections": [
                {
                    "section_id": "source_quality",
                    "title": "来源",
                    "markdown": "Authorization: Bearer legacy-bearer-secret",
                }
            ],
            "disclaimer": "仅供研究。",
        }
    )
    artifacts = AssetResearchReportArtifactsService(None, storage_root=tmp_path)  # type: ignore[arg-type]

    payload = artifacts.public_report_payload(report)
    serialized = json.dumps(payload, ensure_ascii=False)

    assert "legacy-api-secret" not in serialized
    assert "legacy-bearer-secret" not in serialized
    assert payload["meta"]["api_key"] == "[REDACTED]"
    assert "[REDACTED]" in payload["sections"][0]["markdown"]


def _identity() -> InstrumentIdentity:
    return InstrumentIdentity(
        asset_type="futures",
        identity_level="CONTRACT",
        canonical_id="futures:CFFEX:IF2609:CNY",
        display_symbol="IF2609",
        name="沪深300期货2609",
        venue="CFFEX",
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="CONTRACT_CODE",
        identifier_value="IF2609",
        product_type="FUTURE",
        metadata_version="fixture-v1",
        details=FuturesIdentityDetails(
            product_code="IF",
            contract_month="2609",
            expiry_at="2026-09-18T07:15:00+00:00",
            contract_multiplier="300",
            trading_calendar_id="CFFEX",
        ),
    )


@pytest.mark.asyncio
async def test_public_report_export_and_knowledge_base_publish_are_owner_scoped(
    monkeypatch, tmp_path
) -> None:
    export_events: list[dict[str, str]] = []
    publication_events: list[dict[str, str]] = []
    monkeypatch.setattr(
        artifacts_module,
        "record_asset_research_export",
        lambda **event: export_events.append(event),
        raising=False,
    )
    monkeypatch.setattr(
        artifacts_module,
        "record_asset_research_publication",
        lambda **event: publication_events.append(event),
        raising=False,
    )
    async with async_session_maker() as db:
        user = User(username="artifact_user", email="artifact@example.test", hashed_password="hash")
        db.add(user)
        db.add(
            AssetDataSourceRegistry(
                source_id="artifact-fixture",
                asset_types=["futures"],
                jurisdictions=["GLOBAL"],
                license_status="APPROVED",
                allowed_uses=["RESEARCH_ONLY"],
                redistribution_policy="NO_REDISTRIBUTION",
                derived_data_policy="ALLOWED",
                retention_policy="research-v1",
                effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
                freshness_sla={},
                enabled=True,
            )
        )
        await db.flush()
        orchestrator = AssetResearchOrchestrator(db, data_adapter=_Data())
        await orchestrator.persist_identity(
            _identity(), valid_from=datetime(2000, 1, 1, tzinfo=timezone.utc)
        )
        task = await orchestrator.create_and_run(
            user_id=user.id,
            request=AssetAnalysisCreateRequest(
                asset_type="futures", canonical_id="futures:CFFEX:IF2609:CNY"
            ),
            # Iteration 193 Task J (T1): dynamic cutoff so the report is always
            # reproducible regardless of the real wall clock.
            cutoff_at=datetime.now(timezone.utc) - timedelta(days=10),
        )
        result = await orchestrator.get_result(user_id=user.id, task_id=task.id)
        assert result is not None and result.report_id is not None
        report = await db.get(AssetAnalysisReport, result.report_id)
        assert report is not None
        report.sections_json = {
            **report.sections_json,
            "candidate_decision": {"private_note": "candidate-secret"},
        }
        await db.flush()
        kb = KnowledgeBase(owner_id=user.id, name="研究知识库")
        db.add(kb)
        await db.flush()
        artifacts = AssetResearchReportArtifactsService(db, storage_root=tmp_path)
        exported = await artifacts.request_export(
            user_id=user.id,
            report_id=result.report_id,
            export_format="MARKDOWN",
            idempotency_key="asset-export-1",
        )
        exported_pdf = await artifacts.request_export(
            user_id=user.id,
            report_id=result.report_id,
            export_format="PDF",
            idempotency_key="asset-export-pdf-1",
        )
        published = await artifacts.publish(
            user_id=user.id,
            report_id=result.report_id,
            target_type="KNOWLEDGE_BASE",
            target_ref=kb.id,
            title="期货研究报告",
            idempotency_key="asset-publication-1",
        )
        knowledge_base_document = (
            await db.execute(select(KBDocument).where(KBDocument.id == published.external_ref))
        ).scalar_one()
        knowledge_base_document_content = knowledge_base_document.content or ""

    assert exported.status == "SUCCEEDED"
    assert exported.storage_uri is not None
    assert (tmp_path / exported.storage_uri).is_file()
    assert "candidate-secret" not in (tmp_path / exported.storage_uri).read_text()
    assert exported_pdf.status == "SUCCEEDED"
    assert exported_pdf.storage_uri is not None
    assert (tmp_path / exported_pdf.storage_uri).read_bytes().startswith(b"%PDF")
    assert published.status == "SUCCEEDED"
    assert published.external_ref is not None
    assert "candidate-secret" not in knowledge_base_document_content
    assert export_events == [
        {"export_format": "MARKDOWN", "status": "SUCCEEDED"},
        {"export_format": "PDF", "status": "SUCCEEDED"},
    ]
    assert publication_events == [
        {"target_type": "KNOWLEDGE_BASE", "status": "SUCCEEDED"},
    ]
