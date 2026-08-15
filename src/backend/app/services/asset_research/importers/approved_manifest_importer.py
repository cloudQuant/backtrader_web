"""Dry-run-first importer for approved source, identity and schedule manifests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_research import AssetDataSourceRegistry
from app.schemas.asset_research import (
    ApprovedScheduleManifestCreateRequest,
    InstrumentIdentity,
    RawAssetSnapshot,
)
from app.services.asset_research.orchestrator import AssetResearchOrchestrator


@dataclass(frozen=True, slots=True)
class ApprovedManifestImportReport:
    """Audit summary for one approved manifest import."""

    dry_run: bool
    source_count: int
    instrument_count: int
    manifest_count: int
    errors: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.errors


class ApprovedManifestImporter:
    """Import only evidenced source/instrument/schedule configuration."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def import_payload(
        self,
        *,
        payload: Mapping[str, Any],
        dry_run: bool = True,
        valid_from: datetime | None = None,
    ) -> ApprovedManifestImportReport:
        """Validate and optionally persist one approved static manifest set."""
        errors: list[str] = []
        sources = self._sources(payload)
        identities = self._identities(payload)
        manifests = self._manifests(payload)

        if not sources:
            errors.append("SOURCE_REGISTRY_EMPTY")
        if not identities:
            errors.append("INSTRUMENTS_EMPTY")
        if not manifests:
            errors.append("MANIFEST_EMPTY")

        canonical_ids = {identity.canonical_id for identity in identities}
        for manifest in manifests:
            for entry in manifest.entries:
                if entry.schedule.canonical_id not in canonical_ids:
                    errors.append(f"MANIFEST_CANONICAL_UNKNOWN:{entry.schedule.canonical_id}")

        if dry_run:
            return ApprovedManifestImportReport(
                dry_run=True,
                source_count=len(sources),
                instrument_count=len(identities),
                manifest_count=len(manifests),
                errors=tuple(errors),
            )

        if errors:
            return ApprovedManifestImportReport(
                dry_run=False,
                source_count=len(sources),
                instrument_count=len(identities),
                manifest_count=len(manifests),
                errors=tuple(errors),
            )

        try:
            await self._upsert_sources(sources)
            declared_source_ids = tuple(
                dict.fromkeys(
                    str(item.get("source_id", "")).strip()
                    for item in sources
                    if str(item.get("source_id", "")).strip()
                )
            )
            orchestrator = AssetResearchOrchestrator(
                self.db,
                data_adapter=_DeclaredSourceAdapter(declared_source_ids),
            )
            for identity in identities:
                await orchestrator.persist_identity(identity, valid_from=valid_from)
            for manifest in manifests:
                await orchestrator.create_approved_schedule_manifest(
                    actor_id="manifest-importer",
                    request=manifest,
                )
            await self.db.commit()
        except Exception as exc:
            await self.db.rollback()
            errors.append(str(getattr(exc, "code", type(exc).__name__)))

        return ApprovedManifestImportReport(
            dry_run=False,
            source_count=len(sources),
            instrument_count=len(identities),
            manifest_count=len(manifests),
            errors=tuple(errors),
        )

    @staticmethod
    def _sources(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
        raw = payload.get("source_registry")
        if not isinstance(raw, Sequence):
            return []
        result: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                result.append(item)
        return result

    @staticmethod
    def _identities(payload: Mapping[str, Any]) -> list[InstrumentIdentity]:
        raw = payload.get("instruments")
        if not isinstance(raw, Sequence):
            return []
        identities: list[InstrumentIdentity] = []
        for item in raw:
            if isinstance(item, InstrumentIdentity):
                identities.append(item)
            elif isinstance(item, Mapping):
                identities.append(InstrumentIdentity.model_validate(item))
        return identities

    @staticmethod
    def _manifests(payload: Mapping[str, Any]) -> list[ApprovedScheduleManifestCreateRequest]:
        raw = payload.get("manifests")
        if not isinstance(raw, Sequence):
            return []
        manifests: list[ApprovedScheduleManifestCreateRequest] = []
        for item in raw:
            if isinstance(item, ApprovedScheduleManifestCreateRequest):
                manifests.append(item)
            elif isinstance(item, Mapping):
                manifests.append(ApprovedScheduleManifestCreateRequest.model_validate(item))
        return manifests

    async def _upsert_sources(self, sources: Sequence[Mapping[str, Any]]) -> None:
        for raw_source in sources:
            source_id = str(raw_source["source_id"])
            existing = await self.db.get(AssetDataSourceRegistry, source_id)
            effective_from = self._utc_datetime(raw_source.get("effective_from"))
            effective_to = self._utc_datetime(raw_source.get("effective_to"))
            values = {
                "asset_types": raw_source.get("asset_types") or [],
                "jurisdictions": raw_source.get("jurisdictions") or [],
                "license_status": str(raw_source.get("license_status") or "UNKNOWN"),
                "allowed_uses": raw_source.get("allowed_uses") or [],
                "attribution_text": raw_source.get("attribution_text"),
                "redistribution_policy": str(raw_source.get("redistribution_policy") or "UNKNOWN"),
                "derived_data_policy": str(raw_source.get("derived_data_policy") or "UNKNOWN"),
                "retention_policy": str(raw_source.get("retention_policy") or "research-v1"),
                "effective_from": effective_from or datetime.now(timezone.utc),
                "effective_to": effective_to,
                "freshness_sla": raw_source.get("freshness_sla") or {},
                "enabled": bool(raw_source.get("enabled", False)),
            }
            if existing is None:
                self.db.add(AssetDataSourceRegistry(source_id=source_id, **values))
            else:
                for field, value in values.items():
                    setattr(existing, field, value)

    @staticmethod
    def _utc_datetime(value: object) -> datetime | None:
        if value is None or isinstance(value, datetime):
            return value
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


class _DeclaredSourceAdapter:
    """Import-only adapter that declares the manifest's approved source IDs."""

    declared_source_ids: tuple[str, ...]

    def __init__(self, source_ids: tuple[str, ...]) -> None:
        self.declared_source_ids = source_ids

    async def collect(
        self,
        identity: InstrumentIdentity,
        *,
        cutoff_at: datetime,
    ) -> RawAssetSnapshot:
        del identity, cutoff_at
        raise NotImplementedError("import-only adapter must not collect market data")
