"""Focused contracts for server-attested protocol-v2 dataset identities."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select, update

from app.db.database import async_session_maker
from app.models.ai_research_v2 import ResearchDatasetSnapshot
from app.models.user import User
from app.services.research.dataset_integrity import (
    DatasetObjectAttestation,
    InMemoryDatasetObjectResolver,
    object_attestation_receipt_hash,
)
from app.services.research.dataset_registry import (
    DatasetRegistry,
    require_verified_snapshot_integrity,
)


@pytest.mark.asyncio
async def test_attested_snapshot_binds_server_resolved_object_identity(auth_user) -> None:
    """A client supplies only a receipt; all object facts come from the resolver."""

    user_id = await _user_id(auth_user)
    resolver = InMemoryDatasetObjectResolver()
    attestation = resolver.register(
        DatasetObjectAttestation(
            receipt_id="ingestion-receipt-discovery-v1",
            user_id=user_id,
            logical_object_id="registered-object-discovery",
            object_version="version-20260905-001",
            object_digest="a" * 64,
            object_size_bytes=4096,
            storage_uri="controlled://registered-objects/discovery.parquet",
            attested_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
        )
    )
    registry = DatasetRegistry(object_resolver=resolver)

    snapshot = await registry.create_attested_snapshot(
        user_id=user_id,
        object_receipt_id=attestation.receipt_id,
        **_snapshot_metadata(),
    )

    assert snapshot.integrity_status == "VERIFIED"
    assert snapshot.object_receipt_id == attestation.receipt_id
    assert snapshot.object_logical_id == attestation.logical_object_id
    assert snapshot.object_version == attestation.object_version
    assert snapshot.object_digest == attestation.object_digest
    assert snapshot.object_size_bytes == attestation.object_size_bytes
    assert snapshot.integrity_checked_at is not None
    assert snapshot.integrity_receipt_hash == object_attestation_receipt_hash(attestation)
    assert snapshot.snapshot_identity_hash is not None
    require_verified_snapshot_integrity(snapshot)

    visible = await registry.get_for_explorer(user_id, snapshot.id)
    assert visible.id == snapshot.id
    assert not hasattr(visible, "storage_uri")


@pytest.mark.asyncio
async def test_attested_snapshot_rejects_unknown_receipt_without_persisting_snapshot(
    auth_user,
) -> None:
    """An opaque receipt is accepted only if a server resolver attests to it."""

    user_id = await _user_id(auth_user)
    registry = DatasetRegistry(object_resolver=InMemoryDatasetObjectResolver())

    with pytest.raises(ValueError, match="DATASET_OBJECT_RECEIPT_NOT_FOUND"):
        await registry.create_attested_snapshot(
            user_id=user_id,
            object_receipt_id="unknown-receipt",
            **_snapshot_metadata(),
        )

    async with async_session_maker() as session:
        count = await session.scalar(
            select(func.count(ResearchDatasetSnapshot.id)).where(
                ResearchDatasetSnapshot.user_id == user_id
            )
        )
    assert count == 0


@pytest.mark.asyncio
async def test_revalidation_detects_a_changed_logical_object_and_fails_closed(auth_user) -> None:
    """A new version or digest at the same registered object invalidates the snapshot."""

    user_id = await _user_id(auth_user)
    resolver = InMemoryDatasetObjectResolver()
    initial = resolver.register(
        DatasetObjectAttestation(
            receipt_id="ingestion-receipt-mutable-v1",
            user_id=user_id,
            logical_object_id="registered-object-mutable",
            object_version="version-1",
            object_digest="b" * 64,
            object_size_bytes=1024,
            storage_uri="controlled://registered-objects/mutable.parquet",
            attested_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
        )
    )
    registry = DatasetRegistry(object_resolver=resolver)
    snapshot = await registry.create_attested_snapshot(
        user_id=user_id,
        object_receipt_id=initial.receipt_id,
        **_snapshot_metadata(),
    )
    resolver.register(
        DatasetObjectAttestation(
            receipt_id="ingestion-receipt-mutable-v2",
            user_id=user_id,
            logical_object_id=initial.logical_object_id,
            object_version="version-2",
            object_digest="c" * 64,
            object_size_bytes=2048,
            storage_uri=initial.storage_uri,
            attested_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
        )
    )

    with pytest.raises(ValueError, match="DATASET_OBJECT_ATTESTATION_MISMATCH"):
        await registry.revalidate_snapshot(user_id, snapshot.id)

    async with async_session_maker() as session:
        stored = await session.get(ResearchDatasetSnapshot, snapshot.id)
    assert stored is not None
    assert stored.integrity_status == "FAILED"
    assert stored.integrity_checked_at is not None
    assert stored.integrity_receipt_hash == object_attestation_receipt_hash(initial)
    with pytest.raises(ValueError, match="DATASET_SNAPSHOT_INTEGRITY_FAILED"):
        require_verified_snapshot_integrity(stored)


@pytest.mark.asyncio
async def test_session_bound_revalidation_never_commits_its_failure_state(auth_user) -> None:
    """An owning precheck/task transaction controls persistence of a failed revalidation."""

    user_id = await _user_id(auth_user)
    resolver = InMemoryDatasetObjectResolver()
    initial = resolver.register(
        DatasetObjectAttestation(
            receipt_id="ingestion-receipt-session-v1",
            user_id=user_id,
            logical_object_id="registered-object-session",
            object_version="version-1",
            object_digest="f" * 64,
            object_size_bytes=256,
            storage_uri="controlled://registered-objects/session.parquet",
            attested_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
        )
    )
    registry = DatasetRegistry(object_resolver=resolver)
    snapshot = await registry.create_attested_snapshot(
        user_id=user_id,
        object_receipt_id=initial.receipt_id,
        **_snapshot_metadata(),
    )
    resolver.register(
        DatasetObjectAttestation(
            receipt_id="ingestion-receipt-session-v2",
            user_id=user_id,
            logical_object_id=initial.logical_object_id,
            object_version="version-2",
            object_digest="0" * 64,
            object_size_bytes=512,
            storage_uri=initial.storage_uri,
            attested_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
        )
    )

    async with async_session_maker() as session:
        locked = await session.scalar(
            select(ResearchDatasetSnapshot)
            .where(ResearchDatasetSnapshot.id == snapshot.id)
            .with_for_update()
        )
        assert locked is not None
        with pytest.raises(ValueError, match="DATASET_OBJECT_ATTESTATION_MISMATCH"):
            await registry.revalidate_snapshot_in_session(session, snapshot=locked)
        assert locked.integrity_status == "FAILED"
        await session.rollback()

    async with async_session_maker() as session:
        stored = await session.get(ResearchDatasetSnapshot, snapshot.id)
    assert stored is not None
    assert stored.integrity_status == "VERIFIED"


@pytest.mark.asyncio
async def test_verified_snapshot_identity_hash_binds_the_complete_attestation(auth_user) -> None:
    """A receipt-audit hash cannot be altered independently of snapshot identity."""

    user_id = await _user_id(auth_user)
    resolver = InMemoryDatasetObjectResolver()
    attestation = resolver.register(
        DatasetObjectAttestation(
            receipt_id="ingestion-receipt-identity-v1",
            user_id=user_id,
            logical_object_id="registered-object-identity",
            object_version="version-1",
            object_digest="d" * 64,
            object_size_bytes=512,
            storage_uri="controlled://registered-objects/identity.parquet",
            attested_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
        )
    )
    snapshot = await DatasetRegistry(object_resolver=resolver).create_attested_snapshot(
        user_id=user_id,
        object_receipt_id=attestation.receipt_id,
        **_snapshot_metadata(),
    )

    async with async_session_maker() as session:
        await session.execute(
            update(ResearchDatasetSnapshot)
            .where(ResearchDatasetSnapshot.id == snapshot.id)
            .values(integrity_receipt_hash="e" * 64)
        )
        await session.commit()
    async with async_session_maker() as session:
        stored = await session.get(ResearchDatasetSnapshot, snapshot.id)

    assert stored is not None
    with pytest.raises(ValueError, match="DATASET_SNAPSHOT_IDENTITY_HASH_MISMATCH"):
        require_verified_snapshot_integrity(stored)


@pytest.mark.asyncio
async def test_legacy_create_path_remains_explicitly_unverified(auth_user) -> None:
    """Compatibility creation never fabricates object facts or verified identity."""

    user_id = await _user_id(auth_user)
    snapshot = await DatasetRegistry().create_snapshot(
        user_id=user_id,
        storage_uri="controlled://legacy-fixture/discovery.parquet",
        **_snapshot_metadata(),
    )

    assert snapshot.integrity_status == "LEGACY_UNVERIFIED"
    assert snapshot.object_receipt_id is None
    assert snapshot.object_logical_id is None
    assert snapshot.object_version is None
    assert snapshot.object_digest is None
    assert snapshot.object_size_bytes is None
    assert snapshot.integrity_checked_at is None
    assert snapshot.integrity_receipt_hash is None
    assert snapshot.snapshot_identity_hash is None
    with pytest.raises(ValueError, match="DATASET_SNAPSHOT_LEGACY_UNVERIFIED"):
        require_verified_snapshot_integrity(snapshot)


def _snapshot_metadata() -> dict[str, object]:
    return {
        "dataset_policy_version": "policy-v1",
        "partition_kind": "DISCOVERY",
        "instrument_manifest": {"symbols": ["RB0"]},
        "split_manifest": {"start": "2022-01-01", "end": "2023-12-31"},
        "source_manifest": {"provider": "fixture"},
        "execution_policy": {"fill": "next_bar_open"},
        "point_in_time_cutoff": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "license_tags": ["fixture-license"],
    }


async def _user_id(auth_user) -> str:
    user, _headers = auth_user
    async with async_session_maker() as session:
        return str(await session.scalar(select(User.id).where(User.username == user["username"])))
