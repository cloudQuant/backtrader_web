from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import update

from app.db.database import async_session_maker
from app.models.ai_research_v2 import ResearchDatasetSnapshot
from app.services.research.dataset_registry import DatasetRegistry, verify_snapshot_integrity


@pytest.mark.asyncio
async def test_explorer_cannot_read_sealed_snapshot_or_storage_uri(auth_user) -> None:
    user_id = await _user_id(auth_user)
    registry = DatasetRegistry()
    sealed = await registry.create_snapshot(
        user_id=user_id,
        dataset_policy_version="policy-v1",
        partition_kind="SEALED_HOLDOUT",
        instrument_manifest={"symbols": ["RB0"]},
        split_manifest={"start": "2024-01-01", "end": "2024-12-31"},
        source_manifest={"provider": "fixture"},
        execution_policy={"fill": "next_bar_open"},
        point_in_time_cutoff=datetime(2025, 1, 1, tzinfo=timezone.utc),
        storage_uri="sealed://bucket/holdout.parquet",
    )

    with pytest.raises(ValueError, match="SEALED_DATA_ACCESS_DENIED"):
        await registry.get_for_explorer(user_id, sealed.id)


@pytest.mark.asyncio
async def test_explorer_read_model_never_serializes_storage_uri(auth_user) -> None:
    user_id = await _user_id(auth_user)
    registry = DatasetRegistry()
    discovery = await registry.create_snapshot(
        user_id=user_id,
        dataset_policy_version="policy-v1",
        partition_kind="DISCOVERY",
        instrument_manifest={"symbols": ["RB0"]},
        split_manifest={"start": "2022-01-01", "end": "2023-12-31"},
        source_manifest={"provider": "fixture"},
        execution_policy={"fill": "next_bar_open"},
        point_in_time_cutoff=datetime(2024, 1, 1, tzinfo=timezone.utc),
        storage_uri="controlled://discovery.parquet",
    )

    visible = await registry.get_for_explorer(user_id, discovery.id)

    assert visible.id == discovery.id
    assert visible.partition_kind == "DISCOVERY"
    assert not hasattr(visible, "storage_uri")


@pytest.mark.asyncio
async def test_forward_snapshot_requires_candidate_freeze_proof(auth_user) -> None:
    user_id = await _user_id(auth_user)
    registry = DatasetRegistry()

    with pytest.raises(ValueError, match="FORWARD_SNAPSHOT_REQUIRES_CANDIDATE_FREEZE"):
        await registry.create_snapshot(
            user_id=user_id,
            dataset_policy_version="policy-v1",
            partition_kind="FORWARD_OBSERVATION",
            instrument_manifest={"symbols": ["RB0"]},
            split_manifest={"start": "2025-01-01", "end": "2025-02-01"},
            source_manifest={"provider": "fixture"},
            execution_policy={"fill": "next_bar_open"},
            point_in_time_cutoff=datetime(2025, 2, 1, tzinfo=timezone.utc),
            storage_uri="controlled://forward.parquet",
        )


@pytest.mark.asyncio
async def test_snapshot_rejects_uncontrolled_storage_and_detects_metadata_tampering(
    auth_user,
) -> None:
    user_id = await _user_id(auth_user)
    registry = DatasetRegistry()

    with pytest.raises(ValueError, match="DATASET_STORAGE_REFERENCE_INVALID"):
        await registry.create_snapshot(
            user_id=user_id,
            dataset_policy_version="policy-v1",
            partition_kind="DISCOVERY",
            instrument_manifest={"symbols": ["RB0"]},
            split_manifest={"start": "2022-01-01", "end": "2023-12-31"},
            source_manifest={"provider": "fixture"},
            execution_policy={"fill": "next_bar_open"},
            point_in_time_cutoff=datetime(2024, 1, 1, tzinfo=timezone.utc),
            storage_uri="file:///tmp/discovery.parquet",
        )

    snapshot = await registry.create_snapshot(
        user_id=user_id,
        dataset_policy_version="policy-v1",
        partition_kind="DISCOVERY",
        instrument_manifest={"symbols": ["RB0"]},
        split_manifest={"start": "2022-01-01", "end": "2023-12-31"},
        source_manifest={"provider": "fixture"},
        execution_policy={"fill": "next_bar_open"},
        point_in_time_cutoff=datetime(2024, 1, 1, tzinfo=timezone.utc),
        storage_uri="controlled://research-input/discovery.parquet",
    )
    async with async_session_maker() as session:
        await session.execute(
            update(ResearchDatasetSnapshot)
            .where(ResearchDatasetSnapshot.id == snapshot.id)
            .values(source_manifest={"provider": "tampered"})
        )
        await session.commit()
    async with async_session_maker() as session:
        stored = await session.get(ResearchDatasetSnapshot, snapshot.id)

    assert stored is not None
    with pytest.raises(ValueError, match="DATASET_SNAPSHOT_CONTENT_HASH_MISMATCH"):
        verify_snapshot_integrity(stored)


@pytest.mark.asyncio
async def test_snapshot_integrity_binds_the_controlled_storage_reference(auth_user) -> None:
    """A valid namespace alone cannot substitute a snapshot's original object."""

    user_id = await _user_id(auth_user)
    registry = DatasetRegistry()
    snapshot = await registry.create_snapshot(
        user_id=user_id,
        dataset_policy_version="policy-v1",
        partition_kind="DISCOVERY",
        instrument_manifest={"symbols": ["RB0"]},
        split_manifest={"start": "2022-01-01", "end": "2023-12-31"},
        source_manifest={"provider": "fixture"},
        execution_policy={"fill": "next_bar_open"},
        point_in_time_cutoff=datetime(2024, 1, 1, tzinfo=timezone.utc),
        storage_uri="controlled://research-input/original.parquet",
    )
    assert snapshot.storage_reference_hash

    async with async_session_maker() as session:
        await session.execute(
            update(ResearchDatasetSnapshot)
            .where(ResearchDatasetSnapshot.id == snapshot.id)
            .values(storage_uri="controlled://research-input/replaced.parquet")
        )
        await session.commit()
    async with async_session_maker() as session:
        stored = await session.get(ResearchDatasetSnapshot, snapshot.id)

    assert stored is not None
    with pytest.raises(ValueError, match="DATASET_STORAGE_REFERENCE_HASH_MISMATCH"):
        verify_snapshot_integrity(stored)
    with pytest.raises(ValueError, match="DATASET_STORAGE_REFERENCE_HASH_MISMATCH"):
        await registry.get_for_explorer(user_id, snapshot.id)


async def _user_id(auth_user) -> str:
    user, _headers = auth_user
    from sqlalchemy import select

    from app.db.database import async_session_maker
    from app.models.user import User

    async with async_session_maker() as session:
        result = await session.execute(select(User.id).where(User.username == user["username"]))
        return str(result.scalar_one())
