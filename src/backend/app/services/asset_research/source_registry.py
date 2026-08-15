"""Server-owned data-source permission checks for multi-asset research."""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_research import AssetDataSourceRegistry
from app.schemas.asset_research import RawAssetSnapshot


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite's naive timestamps and aware production timestamps."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class AssetSourceRegistryPolicy:
    """Only the server registry may attest research permission for a source.

    Provider payloads may describe observed fields and capabilities, but their
    claimed licence is not trusted.  The returned snapshot remains immutable;
    it contains the registry decision frozen at collection time.
    """

    _RESEARCH_USES = {"RESEARCH", "RESEARCH_ONLY", "DERIVED_RESEARCH"}
    _APPROVED_LICENSES = {"APPROVED", "RESEARCH_APPROVED"}

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def authorize(self, snapshot: RawAssetSnapshot) -> RawAssetSnapshot:
        """Freeze the current source-registry decision into a raw snapshot."""
        manifest = dict(snapshot.source_manifest)
        source_id = str(manifest.get("source_id") or manifest.get("provider") or "").strip()
        if not source_id:
            return self._with_registry_result(snapshot, manifest, status="UNREGISTERED")
        registry = await self._db.get(AssetDataSourceRegistry, source_id)
        if registry is None:
            return self._with_registry_result(snapshot, manifest, status="UNREGISTERED")

        allowed = self._registry_allows(
            registry,
            asset_type=snapshot.identity.asset_type,
            at=snapshot.retrieved_at,
        )
        return self._with_registry_result(
            snapshot,
            manifest,
            status="ACTIVE" if allowed else "BLOCKED",
            registry=registry,
        )

    async def is_research_authorized(
        self,
        *,
        source_id: str | None,
        asset_type: str,
        at: datetime,
    ) -> bool:
        """Check a known source before an adapter is allowed to collect.

        This is deliberately separate from :meth:`authorize`, which freezes a
        decision into an already-collected snapshot.  Background outcome
        evaluation knows the source that produced the immutable entry
        prediction and must not fetch a new vintage after that source has
        expired or been disabled.
        """
        normalized_source_id = str(source_id or "").strip()
        if not normalized_source_id:
            return False
        registry = await self._db.get(AssetDataSourceRegistry, normalized_source_id)
        return registry is not None and self._registry_allows(
            registry,
            asset_type=asset_type,
            at=at,
        )

    async def enabled_asset_types(
        self,
        *,
        at: datetime | None = None,
        source_ids: Collection[str] | None = None,
    ) -> set[str]:
        """Return asset types that have an active, research-approved source.

        This powers the public capability surface.  It deliberately shares the
        same permission/effective-date rules as snapshot authorization so a UI
        cannot advertise research as enabled when the eventual task will be
        blocked at collection time.  When an adapter declares source IDs, an
        approval for a different provider cannot make that adapter available.
        """
        effective_at = at or datetime.now(timezone.utc)
        allowed_source_ids = (
            {str(source_id).strip() for source_id in source_ids if str(source_id).strip()}
            if source_ids is not None
            else None
        )
        if allowed_source_ids == set():
            return set()
        result = await self._db.execute(
            select(AssetDataSourceRegistry).where(AssetDataSourceRegistry.enabled.is_(True))
        )
        enabled_types: set[str] = set()
        for registry in result.scalars():
            if allowed_source_ids is not None and registry.source_id not in allowed_source_ids:
                continue
            for asset_type in {str(value).lower() for value in (registry.asset_types or [])}:
                if self._registry_allows(registry, asset_type=asset_type, at=effective_at):
                    enabled_types.add(asset_type)
        return enabled_types

    def _registry_allows(
        self,
        registry: AssetDataSourceRegistry,
        *,
        asset_type: str,
        at: datetime,
    ) -> bool:
        effective_at = _as_utc(at)
        effective_from = _as_utc(registry.effective_from)
        effective_to = _as_utc(registry.effective_to) if registry.effective_to is not None else None
        asset_types = {str(value).lower() for value in (registry.asset_types or [])}
        allowed_uses = {str(value).upper() for value in (registry.allowed_uses or [])}
        return (
            registry.enabled
            and asset_type.lower() in asset_types
            and registry.license_status in self._APPROVED_LICENSES
            and bool(self._RESEARCH_USES & allowed_uses)
            and effective_from <= effective_at
            and (effective_to is None or effective_at <= effective_to)
        )

    @staticmethod
    def _with_registry_result(
        snapshot: RawAssetSnapshot,
        manifest: dict[str, object],
        *,
        status: str,
        registry: AssetDataSourceRegistry | None = None,
    ) -> RawAssetSnapshot:
        frozen_manifest = {
            **manifest,
            "source_id": registry.source_id
            if registry is not None
            else manifest.get("source_id") or manifest.get("provider"),
            "source_registry_status": status,
            "license_status": registry.license_status
            if status == "ACTIVE" and registry is not None
            else "UNKNOWN",
            "allowed_uses": list(registry.allowed_uses or [])
            if status == "ACTIVE" and registry is not None
            else [],
            "jurisdictions": list(registry.jurisdictions or [])
            if status == "ACTIVE" and registry is not None
            else [],
            "registry_effective_from": (
                _as_utc(registry.effective_from).isoformat() if registry is not None else None
            ),
            "registry_effective_to": (
                _as_utc(registry.effective_to).isoformat()
                if registry is not None and registry.effective_to is not None
                else None
            ),
        }
        license_tags = list(
            dict.fromkeys([*snapshot.license_tags, str(frozen_manifest["license_status"])])
        )
        return snapshot.model_copy(
            update={"source_manifest": frozen_manifest, "license_tags": license_tags}
        )
