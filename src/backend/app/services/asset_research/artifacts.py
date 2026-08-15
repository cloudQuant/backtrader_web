"""Authorized export and publication of public multi-asset research reports."""

from __future__ import annotations

import asyncio
import hashlib
import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.metrics import (
    record_asset_research_export,
    record_asset_research_publication,
)
from app.models.asset_research import (
    AssetAnalysisExport,
    AssetAnalysisReport,
    AssetAnalysisTask,
    AssetReportPublication,
)
from app.models.knowledge_base import KBDocument, KnowledgeBase
from app.models.workspace import Workspace
from app.services.asset_research.citation_verifier import verify_public_payload
from app.services.asset_research.data import canonical_json_hash
from app.services.asset_research.redaction import redact_sensitive_data
from app.services.asset_research.reports import render_markdown


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AssetResearchArtifactError(ValueError):
    """Stable, client-safe errors for report artifact operations."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class AssetResearchReportArtifactsService:
    """Creates only artifacts derived from a report's published decision.

    Candidate decisions are never read by this service.  The database report
    belongs to the task owner, and every target is re-authorized in the same
    transaction before content is written.
    """

    def __init__(self, db: AsyncSession, *, storage_root: Path | None = None) -> None:
        self.db = db
        self._storage_root = (storage_root or Path.cwd() / "data" / "exports").resolve()

    async def get_report(self, *, user_id: str, report_id: str) -> AssetAnalysisReport | None:
        return (
            await self.db.execute(
                select(AssetAnalysisReport)
                .join(AssetAnalysisTask, AssetAnalysisTask.id == AssetAnalysisReport.task_id)
                .where(
                    AssetAnalysisReport.id == report_id,
                    AssetAnalysisTask.owner_scope == "USER",
                    AssetAnalysisTask.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

    async def get_latest_report(
        self, *, user_id: str, asset_type: str, canonical_id: str
    ) -> AssetAnalysisReport | None:
        return (
            await self.db.execute(
                select(AssetAnalysisReport)
                .join(AssetAnalysisTask, AssetAnalysisTask.id == AssetAnalysisReport.task_id)
                .where(
                    AssetAnalysisTask.owner_scope == "USER",
                    AssetAnalysisTask.user_id == user_id,
                    AssetAnalysisTask.asset_type == asset_type,
                    AssetAnalysisTask.canonical_id == canonical_id,
                    AssetAnalysisTask.status == "SUCCEEDED",
                )
                .order_by(desc(AssetAnalysisReport.created_at), desc(AssetAnalysisReport.id))
                .limit(1)
            )
        ).scalar_one_or_none()

    async def request_export(
        self,
        *,
        user_id: str,
        report_id: str,
        export_format: Literal["MARKDOWN", "PDF"],
        idempotency_key: str | None = None,
    ) -> AssetAnalysisExport:
        """Synchronously materialize a safe artifact and persist its audit record."""
        report = await self.get_report(user_id=user_id, report_id=report_id)
        if report is None:
            raise AssetResearchArtifactError("REPORT_NOT_FOUND")
        key = self._normalize_idempotency_key(idempotency_key)
        request_hash = canonical_json_hash({"report_id": report_id, "format": export_format})
        if key is not None:
            existing = await self._export_by_idempotency_key(user_id=user_id, idempotency_key=key)
            if existing is not None:
                if existing.idempotency_request_hash != request_hash:
                    raise AssetResearchArtifactError("IDEMPOTENCY_CONFLICT")
                return existing

        export = AssetAnalysisExport(
            report_id=report.id,
            format=export_format,
            status="QUEUED",
            requested_by=user_id,
            idempotency_key=key,
            idempotency_request_hash=request_hash if key is not None else None,
        )
        self.db.add(export)
        await self.db.flush()
        try:
            content = self._render_public_export(report, export_format)
            relative_path = (
                Path("asset-research")
                / user_id
                / report.id
                / f"{export.id}.{self._extension(export_format)}"
            )
            output_path = self._safe_output_path(relative_path)
            await asyncio.to_thread(output_path.parent.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(output_path.write_bytes, content)
            export.storage_uri = str(relative_path)
            export.content_hash = hashlib.sha256(content).hexdigest()
            export.status = "SUCCEEDED"
            export.completed_at = _now()
        except Exception as exc:  # pragma: no cover - exercised by optional PDF runtime failures
            export.status = "FAILED"
            export.error_code = type(exc).__name__
            export.completed_at = _now()
        record_asset_research_export(export_format=export_format, status=export.status)
        await self.db.flush()
        return export

    async def get_export(self, *, user_id: str, export_id: str) -> AssetAnalysisExport | None:
        return (
            await self.db.execute(
                select(AssetAnalysisExport)
                .join(AssetAnalysisReport, AssetAnalysisReport.id == AssetAnalysisExport.report_id)
                .join(AssetAnalysisTask, AssetAnalysisTask.id == AssetAnalysisReport.task_id)
                .where(
                    AssetAnalysisExport.id == export_id,
                    AssetAnalysisExport.requested_by == user_id,
                    AssetAnalysisTask.owner_scope == "USER",
                    AssetAnalysisTask.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

    async def read_export(
        self, *, user_id: str, export_id: str
    ) -> tuple[AssetAnalysisExport, bytes] | None:
        export = await self.get_export(user_id=user_id, export_id=export_id)
        if export is None or export.status != "SUCCEEDED" or not export.storage_uri:
            return None
        path = self._safe_output_path(Path(export.storage_uri))
        if not path.is_file():
            return None
        return export, await asyncio.to_thread(path.read_bytes)

    async def publish(
        self,
        *,
        user_id: str,
        report_id: str,
        target_type: Literal["KNOWLEDGE_BASE", "WORKSPACE"],
        target_ref: str,
        title: str | None = None,
        idempotency_key: str | None = None,
    ) -> AssetReportPublication:
        """Save a public report to an authorized knowledge base or research workspace."""
        report = await self.get_report(user_id=user_id, report_id=report_id)
        if report is None:
            raise AssetResearchArtifactError("REPORT_NOT_FOUND")
        key = self._normalize_idempotency_key(idempotency_key)
        request_hash = canonical_json_hash(
            {
                "report_id": report_id,
                "target_type": target_type,
                "target_ref": target_ref,
                "title": title,
            }
        )
        if key is not None:
            existing = await self._publication_by_idempotency_key(
                user_id=user_id, idempotency_key=key
            )
            if existing is not None:
                if existing.idempotency_request_hash != request_hash:
                    raise AssetResearchArtifactError("IDEMPOTENCY_CONFLICT")
                return existing
        publication = AssetReportPublication(
            report_id=report.id,
            target_type=target_type,
            target_ref=target_ref,
            status="QUEUED",
            requested_by=user_id,
            idempotency_key=key,
            idempotency_request_hash=request_hash if key is not None else None,
        )
        self.db.add(publication)
        await self.db.flush()
        public_payload = self.public_report_payload(report)
        if not verify_public_payload(public_payload).passed:
            raise AssetResearchArtifactError("REPORT_CITATION_INVALID")
        markdown = render_markdown(public_payload)
        try:
            if target_type == "KNOWLEDGE_BASE":
                external_ref = await self._publish_to_knowledge_base(
                    user_id=user_id,
                    target_ref=target_ref,
                    report=report,
                    markdown=markdown,
                    title=title,
                )
            else:
                external_ref = await self._publish_to_workspace(
                    user_id=user_id,
                    target_ref=target_ref,
                    report=report,
                    public_payload=public_payload,
                    title=title,
                )
            publication.external_ref = external_ref
            publication.content_hash = canonical_json_hash(public_payload)
            publication.status = "SUCCEEDED"
            publication.completed_at = _now()
        except AssetResearchArtifactError:
            raise
        except (
            Exception
        ) as exc:  # pragma: no cover - protects audit status for unexpected persistence errors
            publication.status = "FAILED"
            publication.error_code = type(exc).__name__
            publication.completed_at = _now()
        record_asset_research_publication(target_type=target_type, status=publication.status)
        await self.db.flush()
        return publication

    async def get_publication(
        self, *, user_id: str, publication_id: str
    ) -> AssetReportPublication | None:
        return (
            await self.db.execute(
                select(AssetReportPublication)
                .join(
                    AssetAnalysisReport, AssetAnalysisReport.id == AssetReportPublication.report_id
                )
                .join(AssetAnalysisTask, AssetAnalysisTask.id == AssetAnalysisReport.task_id)
                .where(
                    AssetReportPublication.id == publication_id,
                    AssetReportPublication.requested_by == user_id,
                    AssetAnalysisTask.owner_scope == "USER",
                    AssetAnalysisTask.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    def public_report_payload(report: AssetAnalysisReport) -> dict[str, Any]:
        """Defensively remove shadow and credential fields from legacy report rows."""
        payload = redact_sensitive_data(report.sections_json or {})
        if not isinstance(payload, dict):
            return {}
        payload.pop("candidate_decision", None)
        payload.pop("candidate_decision_json", None)
        return payload

    async def _publish_to_knowledge_base(
        self,
        *,
        user_id: str,
        target_ref: str,
        report: AssetAnalysisReport,
        markdown: str,
        title: str | None,
    ) -> str:
        knowledge_base = (
            await self.db.execute(
                select(KnowledgeBase).where(
                    KnowledgeBase.id == target_ref,
                    KnowledgeBase.owner_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if knowledge_base is None:
            raise AssetResearchArtifactError("PUBLICATION_TARGET_NOT_FOUND")
        document = KBDocument(
            knowledge_base_id=knowledge_base.id,
            title=title or "多资产研究报告",
            content=markdown,
            content_type="markdown",
            is_folder=False,
            status="draft",
            index_status="not_indexed",
            metadata_json={
                "source": "asset_research_report",
                "asset_research_report_id": report.id,
            },
        )
        self.db.add(document)
        knowledge_base.document_count = int(knowledge_base.document_count or 0) + 1
        await self.db.flush()
        return document.id

    async def _publish_to_workspace(
        self,
        *,
        user_id: str,
        target_ref: str,
        report: AssetAnalysisReport,
        public_payload: dict[str, Any],
        title: str | None,
    ) -> str:
        workspace = (
            await self.db.execute(
                select(Workspace).where(Workspace.id == target_ref, Workspace.user_id == user_id)
            )
        ).scalar_one_or_none()
        if workspace is None or workspace.workspace_type != "research":
            raise AssetResearchArtifactError("PUBLICATION_TARGET_NOT_FOUND")
        meta = public_payload.get("meta") or {}
        decision = public_payload.get("published_decision") or {}
        settings = dict(workspace.settings or {})
        entries = settings.get("asset_research_reports")
        if not isinstance(entries, list):
            entries = []
        entries = [
            entry
            for entry in entries
            if not isinstance(entry, dict) or entry.get("report_id") != report.id
        ]
        entries.append(
            {
                "report_id": report.id,
                "title": title or meta.get("name") or "多资产研究报告",
                "asset_type": meta.get("asset_type"),
                "canonical_id": meta.get("canonical_id"),
                "recommendation": decision.get("recommendation"),
                "actionability": decision.get("actionability"),
                "saved_at": _now().isoformat(),
                "source": "asset_research_report",
            }
        )
        settings["asset_research_reports"] = entries[-50:]
        workspace.settings = settings
        workspace.updated_at = _now()
        await self.db.flush()
        return workspace.id

    async def _export_by_idempotency_key(
        self, *, user_id: str, idempotency_key: str
    ) -> AssetAnalysisExport | None:
        return (
            await self.db.execute(
                select(AssetAnalysisExport).where(
                    AssetAnalysisExport.requested_by == user_id,
                    AssetAnalysisExport.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()

    async def _publication_by_idempotency_key(
        self, *, user_id: str, idempotency_key: str
    ) -> AssetReportPublication | None:
        return (
            await self.db.execute(
                select(AssetReportPublication).where(
                    AssetReportPublication.requested_by == user_id,
                    AssetReportPublication.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()

    def _safe_output_path(self, relative_path: Path) -> Path:
        root = self._storage_root
        output = (root / relative_path).resolve()
        if root != output and root not in output.parents:
            raise AssetResearchArtifactError("EXPORT_PATH_INVALID")
        return output

    @staticmethod
    def _normalize_idempotency_key(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized or len(normalized) > 128:
            raise AssetResearchArtifactError("IDEMPOTENCY_KEY_INVALID")
        return normalized

    @staticmethod
    def _extension(export_format: str) -> str:
        return {"MARKDOWN": "md", "PDF": "pdf"}[export_format]

    def _render_public_export(self, report: AssetAnalysisReport, export_format: str) -> bytes:
        payload = self.public_report_payload(report)
        if not verify_public_payload(payload).passed:
            raise AssetResearchArtifactError("REPORT_CITATION_INVALID")
        markdown = render_markdown(payload)
        if export_format == "MARKDOWN":
            return markdown.encode("utf-8")
        if export_format == "PDF":
            try:
                from weasyprint import HTML
            except ImportError as exc:
                raise AssetResearchArtifactError("EXPORT_FORMAT_UNAVAILABLE") from exc
            document = (
                '<!doctype html><meta charset="utf-8"><style>'
                "body{font-family:sans-serif;white-space:pre-wrap;line-height:1.6}"
                "</style><body>"
                f"{html.escape(markdown)}"
                "</body>"
            )
            return HTML(string=document).write_pdf()
        raise AssetResearchArtifactError("EXPORT_FORMAT_UNSUPPORTED")
