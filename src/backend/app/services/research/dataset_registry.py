"""Data-partition registry for v2 research identity and access boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import database
from app.models.ai_research_v2 import ResearchDatasetSnapshot
from app.services.research.canonical import content_hash
from app.services.research.dataset_integrity import (
    DatasetObjectAttestation,
    DatasetObjectResolver,
    normalize_object_attestation,
    object_attestation_receipt_hash,
)


@dataclass(frozen=True, slots=True)
class ExplorerDatasetSnapshot:
    """Safe Explorer read model that deliberately omits controlled storage URI."""

    id: str
    dataset_policy_version: str
    partition_kind: str
    instrument_manifest: dict[str, Any]
    split_manifest: dict[str, Any]
    source_manifest: dict[str, Any]
    execution_policy: dict[str, Any]
    point_in_time_cutoff: datetime
    content_hash: str


class DatasetRegistry:
    """Persist point-in-time datasets and enforce Explorer partition scope."""

    def __init__(self, *, object_resolver: DatasetObjectResolver | None = None) -> None:
        """Keep legacy metadata creation available while requiring a server resolver for trust."""

        self._object_resolver = object_resolver

    async def create_snapshot(
        self,
        *,
        user_id: str,
        dataset_policy_version: str,
        partition_kind: str,
        instrument_manifest: dict[str, Any],
        split_manifest: dict[str, Any],
        source_manifest: dict[str, Any],
        execution_policy: dict[str, Any],
        point_in_time_cutoff: datetime,
        storage_uri: str,
        license_tags: list[str] | None = None,
        candidate_frozen_at: datetime | None = None,
    ) -> ResearchDatasetSnapshot:
        """Create one immutable snapshot reference after policy validation."""

        cutoff = _validate_snapshot_request(
            partition_kind=partition_kind,
            point_in_time_cutoff=point_in_time_cutoff,
            candidate_frozen_at=candidate_frozen_at,
        )
        _validate_storage_reference(partition_kind, storage_uri)

        model = ResearchDatasetSnapshot(
            user_id=user_id,
            dataset_policy_version=dataset_policy_version,
            partition_kind=partition_kind,
            instrument_manifest=instrument_manifest,
            split_manifest=split_manifest,
            source_manifest=source_manifest,
            execution_policy=execution_policy,
            point_in_time_cutoff=cutoff,
            content_hash=snapshot_content_hash(
                dataset_policy_version=dataset_policy_version,
                partition_kind=partition_kind,
                instrument_manifest=instrument_manifest,
                split_manifest=split_manifest,
                source_manifest=source_manifest,
                execution_policy=execution_policy,
                point_in_time_cutoff=cutoff,
                license_tags=license_tags or [],
            ),
            storage_uri=storage_uri,
            storage_reference_hash=storage_reference_hash(partition_kind, storage_uri),
            integrity_status="LEGACY_UNVERIFIED",
            license_tags=license_tags or [],
        )
        async with database.async_session_maker() as session:
            session.add(model)
            await session.commit()
            await session.refresh(model)
        return model

    async def create_attested_snapshot(
        self,
        *,
        user_id: str,
        object_receipt_id: str,
        dataset_policy_version: str,
        partition_kind: str,
        instrument_manifest: dict[str, Any],
        split_manifest: dict[str, Any],
        source_manifest: dict[str, Any],
        execution_policy: dict[str, Any],
        point_in_time_cutoff: datetime,
        license_tags: list[str] | None = None,
        candidate_frozen_at: datetime | None = None,
    ) -> ResearchDatasetSnapshot:
        """Create a verified snapshot using only a server-resolved opaque receipt.

        The caller deliberately cannot provide a URI, object version, content
        digest, or byte size.  Those fields are copied only from the
        deployment-owned ``DatasetObjectResolver`` response.
        """

        async with database.async_session_maker() as session:
            model = await self.create_attested_snapshot_in_session(
                session,
                user_id=user_id,
                object_receipt_id=object_receipt_id,
                dataset_policy_version=dataset_policy_version,
                partition_kind=partition_kind,
                instrument_manifest=instrument_manifest,
                split_manifest=split_manifest,
                source_manifest=source_manifest,
                execution_policy=execution_policy,
                point_in_time_cutoff=point_in_time_cutoff,
                license_tags=license_tags,
                candidate_frozen_at=candidate_frozen_at,
            )
            await session.commit()
            await session.refresh(model)
        return model

    async def create_attested_snapshot_in_session(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        object_receipt_id: str,
        dataset_policy_version: str,
        partition_kind: str,
        instrument_manifest: dict[str, Any],
        split_manifest: dict[str, Any],
        source_manifest: dict[str, Any],
        execution_policy: dict[str, Any],
        point_in_time_cutoff: datetime,
        license_tags: list[str] | None = None,
        candidate_frozen_at: datetime | None = None,
    ) -> ResearchDatasetSnapshot:
        """Add a verified snapshot to the caller-owned transaction without committing it."""

        if not isinstance(object_receipt_id, str) or not object_receipt_id.strip():
            raise ValueError("DATASET_OBJECT_RECEIPT_REQUIRED")
        resolver = self._require_object_resolver()
        attestation = normalize_object_attestation(
            await resolver.resolve_receipt(user_id=user_id, receipt_id=object_receipt_id),
            expected_user_id=user_id,
        )
        if attestation.receipt_id != object_receipt_id:
            raise ValueError("DATASET_OBJECT_ATTESTATION_RECEIPT_MISMATCH")
        cutoff = _validate_snapshot_request(
            partition_kind=partition_kind,
            point_in_time_cutoff=point_in_time_cutoff,
            candidate_frozen_at=candidate_frozen_at,
        )
        _validate_storage_reference(partition_kind, attestation.storage_uri)
        normalized_license_tags = list(license_tags or [])
        metadata_hash = snapshot_content_hash(
            dataset_policy_version=dataset_policy_version,
            partition_kind=partition_kind,
            instrument_manifest=instrument_manifest,
            split_manifest=split_manifest,
            source_manifest=source_manifest,
            execution_policy=execution_policy,
            point_in_time_cutoff=cutoff,
            license_tags=normalized_license_tags,
        )
        reference_hash = storage_reference_hash(partition_kind, attestation.storage_uri)
        receipt_hash = object_attestation_receipt_hash(attestation)
        model = ResearchDatasetSnapshot(
            user_id=user_id,
            dataset_policy_version=dataset_policy_version,
            partition_kind=partition_kind,
            instrument_manifest=instrument_manifest,
            split_manifest=split_manifest,
            source_manifest=source_manifest,
            execution_policy=execution_policy,
            point_in_time_cutoff=cutoff,
            content_hash=metadata_hash,
            storage_uri=attestation.storage_uri,
            storage_reference_hash=reference_hash,
            object_receipt_id=attestation.receipt_id,
            object_logical_id=attestation.logical_object_id,
            object_version=attestation.object_version,
            object_digest=attestation.object_digest,
            object_size_bytes=attestation.object_size_bytes,
            integrity_status="VERIFIED",
            integrity_checked_at=attestation.attested_at,
            integrity_receipt_hash=receipt_hash,
            snapshot_identity_hash=snapshot_identity_hash(
                user_id=user_id,
                metadata_content_hash=metadata_hash,
                storage_reference_hash=reference_hash,
                object_receipt_id=attestation.receipt_id,
                object_logical_id=attestation.logical_object_id,
                object_version=attestation.object_version,
                object_digest=attestation.object_digest,
                object_size_bytes=attestation.object_size_bytes,
                integrity_receipt_hash=receipt_hash,
            ),
            license_tags=normalized_license_tags,
        )
        session.add(model)
        await session.flush()
        return model

    async def revalidate_snapshot(
        self,
        user_id: str,
        snapshot_id: str,
    ) -> ResearchDatasetSnapshot:
        """Re-attest the stored logical object and fail closed if it drifted."""

        async with database.async_session_maker() as session:
            snapshot = await session.scalar(
                select(ResearchDatasetSnapshot)
                .where(
                    ResearchDatasetSnapshot.id == snapshot_id,
                    ResearchDatasetSnapshot.user_id == user_id,
                )
                .with_for_update()
            )
            if snapshot is None:
                raise ValueError("DATASET_SNAPSHOT_NOT_FOUND")
            try:
                model = await self.revalidate_snapshot_in_session(session, snapshot=snapshot)
            except ValueError:
                if snapshot.integrity_status == "FAILED":
                    await session.commit()
                else:
                    await session.rollback()
                raise
            await session.commit()
            await session.refresh(model)
            return model

    async def persist_failed_snapshot(
        self,
        *,
        user_id: str,
        snapshot_id: str,
        expected_snapshot_identity_hash: str,
        checked_at: datetime,
    ) -> ResearchDatasetSnapshot:
        """Persist a failed attestation only for the exact identity just observed.

        This transaction is intentionally independent from a caller's command
        transaction, which must already have rolled back before invoking it.
        """

        async with database.async_session_maker() as session:
            snapshot = await session.scalar(
                select(ResearchDatasetSnapshot)
                .where(
                    ResearchDatasetSnapshot.id == snapshot_id,
                    ResearchDatasetSnapshot.user_id == user_id,
                    ResearchDatasetSnapshot.snapshot_identity_hash
                    == expected_snapshot_identity_hash,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if snapshot is None:
                raise ValueError("DATASET_SNAPSHOT_FAILURE_BINDING_MISMATCH")
            _verify_attested_snapshot_identity(snapshot)
            snapshot.integrity_status = "FAILED"
            snapshot.integrity_checked_at = _as_utc(checked_at)
            await session.commit()
            return snapshot

    async def revalidate_snapshot_in_session(
        self,
        session: AsyncSession,
        *,
        snapshot: ResearchDatasetSnapshot,
    ) -> ResearchDatasetSnapshot:
        """Revalidate one locked snapshot without committing the caller's transaction.

        The caller supplies the ambient transaction used for the precheck or
        task-creation gate.  Any ``FAILED`` state is flushed into that same
        transaction; this method never commits or rolls it back.
        """

        resolver = self._require_object_resolver()
        model = await session.scalar(
            select(ResearchDatasetSnapshot)
            .where(
                ResearchDatasetSnapshot.id == snapshot.id,
                ResearchDatasetSnapshot.user_id == snapshot.user_id,
            )
            .with_for_update()
        )
        if model is None:
            raise ValueError("DATASET_SNAPSHOT_NOT_FOUND")
        _verify_attested_snapshot_identity(model)
        if model.object_logical_id is None:
            raise ValueError("DATASET_SNAPSHOT_ATTESTATION_REQUIRED")
        try:
            current_attestation = normalize_object_attestation(
                await resolver.resolve_current(
                    user_id=model.user_id,
                    logical_object_id=model.object_logical_id,
                ),
                expected_user_id=model.user_id,
            )
        except ValueError:
            model.integrity_status = "FAILED"
            model.integrity_checked_at = _now()
            await session.flush()
            raise ValueError("DATASET_OBJECT_REVALIDATION_UNAVAILABLE") from None

        _validate_storage_reference(model.partition_kind, current_attestation.storage_uri)
        model.integrity_checked_at = current_attestation.attested_at
        if not _matches_attested_object(model, current_attestation):
            model.integrity_status = "FAILED"
            await session.flush()
            raise ValueError("DATASET_OBJECT_ATTESTATION_MISMATCH")
        model.integrity_status = "VERIFIED"
        await session.flush()
        return model

    def _require_object_resolver(self) -> DatasetObjectResolver:
        if self._object_resolver is None:
            raise ValueError("DATASET_OBJECT_RESOLVER_REQUIRED")
        return self._object_resolver

    async def get_for_explorer(
        self,
        user_id: str,
        snapshot_id: str,
    ) -> ExplorerDatasetSnapshot:
        """Return an owner-scoped non-sealed read model for Explorer work."""

        async with database.async_session_maker() as session:
            result = await session.execute(
                select(ResearchDatasetSnapshot).where(
                    ResearchDatasetSnapshot.id == snapshot_id,
                    ResearchDatasetSnapshot.user_id == user_id,
                )
            )
            model = result.scalar_one_or_none()
        if model is None:
            raise ValueError("DATASET_SNAPSHOT_NOT_FOUND")
        if model.partition_kind == "SEALED_HOLDOUT":
            raise ValueError("SEALED_DATA_ACCESS_DENIED")
        verify_snapshot_integrity(model)
        return ExplorerDatasetSnapshot(
            id=model.id,
            dataset_policy_version=model.dataset_policy_version,
            partition_kind=model.partition_kind,
            instrument_manifest=dict(model.instrument_manifest or {}),
            split_manifest=dict(model.split_manifest or {}),
            source_manifest=dict(model.source_manifest or {}),
            execution_policy=dict(model.execution_policy or {}),
            point_in_time_cutoff=model.point_in_time_cutoff,
            content_hash=model.content_hash,
        )


def snapshot_content_hash(
    *,
    dataset_policy_version: str,
    partition_kind: str,
    instrument_manifest: dict[str, Any],
    split_manifest: dict[str, Any],
    source_manifest: dict[str, Any],
    execution_policy: dict[str, Any],
    point_in_time_cutoff: datetime,
    license_tags: list[str],
) -> str:
    """Return the canonical immutable metadata identity for one snapshot."""

    return content_hash(
        {
            "dataset_policy_version": dataset_policy_version,
            "partition_kind": partition_kind,
            "instrument_manifest": instrument_manifest,
            "split_manifest": split_manifest,
            "source_manifest": source_manifest,
            "execution_policy": execution_policy,
            "point_in_time_cutoff": _stored_utc(point_in_time_cutoff),
            "license_tags": license_tags,
        }
    )


def snapshot_identity_hash(
    *,
    user_id: str,
    metadata_content_hash: str,
    storage_reference_hash: str,
    object_receipt_id: str,
    object_logical_id: str,
    object_version: str,
    object_digest: str,
    object_size_bytes: int,
    integrity_receipt_hash: str,
) -> str:
    """Return immutable metadata and the complete original server attestation identity."""

    return content_hash(
        {
            "schema_version": "dataset-snapshot-identity-v1",
            "user_id": user_id,
            "metadata_content_hash": metadata_content_hash,
            "storage_reference_hash": storage_reference_hash,
            "object_receipt_id": object_receipt_id,
            "object_logical_id": object_logical_id,
            "object_version": object_version,
            "object_digest": object_digest,
            "object_size_bytes": object_size_bytes,
            "integrity_receipt_hash": integrity_receipt_hash,
        }
    )


def verify_snapshot_integrity(snapshot: ResearchDatasetSnapshot) -> None:
    """Verify metadata integrity and reject any attested snapshot marked failed.

    ``LEGACY_UNVERIFIED`` snapshots retain the historic metadata-only behavior
    until their callers move to ``require_verified_snapshot_integrity``.
    """

    _verify_snapshot_metadata_integrity(snapshot)
    if snapshot.integrity_status == "FAILED":
        raise ValueError("DATASET_SNAPSHOT_INTEGRITY_FAILED")
    if snapshot.integrity_status == "VERIFIED":
        _verify_attested_snapshot_identity(snapshot)
    elif snapshot.integrity_status != "LEGACY_UNVERIFIED":
        raise ValueError("DATASET_SNAPSHOT_INTEGRITY_STATUS_INVALID")


def require_verified_snapshot_integrity(snapshot: ResearchDatasetSnapshot) -> None:
    """Require a valid server-attested object identity for executable use."""

    verify_snapshot_integrity(snapshot)
    if snapshot.integrity_status == "LEGACY_UNVERIFIED":
        raise ValueError("DATASET_SNAPSHOT_LEGACY_UNVERIFIED")
    if snapshot.integrity_status != "VERIFIED":
        raise ValueError("DATASET_SNAPSHOT_INTEGRITY_NOT_VERIFIED")


def _verify_snapshot_metadata_integrity(snapshot: ResearchDatasetSnapshot) -> None:
    """Ensure persisted metadata and its opaque controlled reference still agree."""

    if snapshot.storage_uri is None:
        raise ValueError("DATASET_STORAGE_REFERENCE_REQUIRED")
    _validate_storage_reference(snapshot.partition_kind, snapshot.storage_uri)
    if snapshot.storage_reference_hash != storage_reference_hash(
        snapshot.partition_kind, snapshot.storage_uri
    ):
        raise ValueError("DATASET_STORAGE_REFERENCE_HASH_MISMATCH")
    expected_hash = snapshot_content_hash(
        dataset_policy_version=snapshot.dataset_policy_version,
        partition_kind=snapshot.partition_kind,
        instrument_manifest=dict(snapshot.instrument_manifest or {}),
        split_manifest=dict(snapshot.split_manifest or {}),
        source_manifest=dict(snapshot.source_manifest or {}),
        execution_policy=dict(snapshot.execution_policy or {}),
        point_in_time_cutoff=snapshot.point_in_time_cutoff,
        license_tags=list(snapshot.license_tags or []),
    )
    if snapshot.content_hash != expected_hash:
        raise ValueError("DATASET_SNAPSHOT_CONTENT_HASH_MISMATCH")


def _verify_attested_snapshot_identity(snapshot: ResearchDatasetSnapshot) -> None:
    """Verify immutable object facts and the identity digest without resolving I/O."""

    _verify_snapshot_metadata_integrity(snapshot)
    if snapshot.integrity_status == "LEGACY_UNVERIFIED":
        raise ValueError("DATASET_SNAPSHOT_LEGACY_UNVERIFIED")
    if snapshot.integrity_status not in {"VERIFIED", "FAILED"}:
        raise ValueError("DATASET_SNAPSHOT_INTEGRITY_STATUS_INVALID")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (
            snapshot.object_receipt_id,
            snapshot.object_logical_id,
            snapshot.object_version,
            snapshot.object_digest,
            snapshot.integrity_receipt_hash,
            snapshot.snapshot_identity_hash,
        )
    ):
        raise ValueError("DATASET_SNAPSHOT_ATTESTATION_REQUIRED")
    if (
        type(snapshot.object_size_bytes) is not int
        or snapshot.object_size_bytes < 0
        or snapshot.integrity_checked_at is None
    ):
        raise ValueError("DATASET_SNAPSHOT_ATTESTATION_REQUIRED")
    _stored_utc(snapshot.integrity_checked_at)
    expected_identity_hash = snapshot_identity_hash(
        user_id=snapshot.user_id,
        metadata_content_hash=snapshot.content_hash,
        storage_reference_hash=snapshot.storage_reference_hash,
        object_receipt_id=snapshot.object_receipt_id,
        object_logical_id=snapshot.object_logical_id,
        object_version=snapshot.object_version,
        object_digest=snapshot.object_digest,
        object_size_bytes=snapshot.object_size_bytes,
        integrity_receipt_hash=snapshot.integrity_receipt_hash,
    )
    if snapshot.snapshot_identity_hash != expected_identity_hash:
        raise ValueError("DATASET_SNAPSHOT_IDENTITY_HASH_MISMATCH")


def _matches_attested_object(
    snapshot: ResearchDatasetSnapshot,
    attestation: DatasetObjectAttestation,
) -> bool:
    """Compare a fresh server observation to immutable snapshot object facts."""

    return (
        snapshot.object_logical_id == attestation.logical_object_id
        and snapshot.object_version == attestation.object_version
        and snapshot.object_digest == attestation.object_digest
        and snapshot.object_size_bytes == attestation.object_size_bytes
        and snapshot.storage_uri == attestation.storage_uri
    )


def storage_reference_hash(partition_kind: str, storage_uri: str) -> str:
    """Return the opaque, immutable identity for a partition storage reference."""

    return content_hash(
        {
            "partition_kind": partition_kind,
            "storage_uri": storage_uri,
        }
    )


def _validate_snapshot_request(
    *,
    partition_kind: str,
    point_in_time_cutoff: datetime,
    candidate_frozen_at: datetime | None,
) -> datetime:
    if partition_kind not in {
        "DISCOVERY",
        "ITERATION_VALIDATION",
        "SEALED_HOLDOUT",
        "FORWARD_OBSERVATION",
    }:
        raise ValueError("DATASET_PARTITION_INVALID")
    cutoff = _as_utc(point_in_time_cutoff)
    if partition_kind == "FORWARD_OBSERVATION":
        if candidate_frozen_at is None:
            raise ValueError("FORWARD_SNAPSHOT_REQUIRES_CANDIDATE_FREEZE")
        if cutoff <= _as_utc(candidate_frozen_at):
            raise ValueError("FORWARD_SNAPSHOT_BEFORE_CANDIDATE_FREEZE")
    return cutoff


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("DATASET_TIMESTAMP_TIMEZONE_REQUIRED")
    return value.astimezone(timezone.utc)


def _stored_utc(value: datetime) -> datetime:
    """Normalize timezone-less SQLite readbacks without accepting naive input."""

    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _validate_storage_reference(partition_kind: str, storage_uri: str) -> None:
    """Allow only opaque references in the partition's controlled namespace."""

    if not storage_uri.strip():
        raise ValueError("DATASET_STORAGE_REFERENCE_REQUIRED")
    parsed = urlsplit(storage_uri)
    expected_scheme = "sealed" if partition_kind == "SEALED_HOLDOUT" else "controlled"
    path_parts = tuple(part for part in parsed.path.split("/") if part)
    if (
        parsed.scheme != expected_scheme
        or not parsed.netloc
        or parsed.query
        or parsed.fragment
        or any(part in {".", ".."} or "\\" in part for part in path_parts)
    ):
        raise ValueError("DATASET_STORAGE_REFERENCE_INVALID")


def validate_storage_reference(partition_kind: str, storage_uri: str) -> None:
    """Public validation boundary for services that bypass registry creation."""

    _validate_storage_reference(partition_kind, storage_uri)
