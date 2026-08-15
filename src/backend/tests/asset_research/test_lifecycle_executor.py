"""Approved tombstone execution contracts for asset-research lifecycle facts."""

from datetime import datetime, timedelta, timezone

import pytest

from app.db.database import async_session_maker
from app.models.asset_research import AssetInstrument
from app.services.asset_research.lifecycle_executor import AssetResearchRetentionExecutor


def _instrument(*, suffix: str, expires_at: datetime, legal_hold: bool = False) -> AssetInstrument:
    return AssetInstrument(
        canonical_id=f"futures:CFFEX:IF2609:CNY:{suffix}",
        asset_type="futures",
        identity_level="CONTRACT",
        venue="CFFEX",
        currency="CNY",
        product_type="FUTURE",
        identity_json={"fixture": suffix},
        metadata_version="lifecycle-fixture-v1",
        retention_expires_at=expires_at,
        legal_hold=legal_hold,
    )


@pytest.mark.asyncio
async def test_lifecycle_executor_requires_an_approval_reference() -> None:
    async with async_session_maker() as db:
        executor = AssetResearchRetentionExecutor(db)
        with pytest.raises(ValueError, match="RETENTION_APPROVAL_REQUIRED"):
            await executor.execute(
                as_of=datetime(2026, 8, 1, tzinfo=timezone.utc),
                approval_reference="   ",
                table_names={"asset_instruments"},
            )


@pytest.mark.asyncio
async def test_lifecycle_executor_dry_run_does_not_tombstone() -> None:
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    async with async_session_maker() as db:
        due = _instrument(suffix="due", expires_at=now - timedelta(days=1))
        db.add(due)
        await db.flush()
        await db.commit()
        due_id = due.id

        report = await AssetResearchRetentionExecutor(db).execute(
            as_of=now,
            approval_reference="TEST-DRY-RUN",
            table_names={"asset_instruments"},
        )

    assert report.action_count == 1
    assert report.dry_run is True
    async with async_session_maker() as db:
        row = await db.get(AssetInstrument, due_id)
        assert row is not None
        assert row.tombstoned_at is None


@pytest.mark.asyncio
async def test_lifecycle_executor_tombstones_only_eligible_and_respects_legal_hold() -> None:
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    async with async_session_maker() as db:
        due = _instrument(suffix="due", expires_at=now - timedelta(days=1))
        held = _instrument(
            suffix="held",
            expires_at=now - timedelta(days=1),
            legal_hold=True,
        )
        db.add_all([due, held])
        await db.flush()
        await db.commit()
        due_id = due.id
        held_id = held.id

        report = await AssetResearchRetentionExecutor(db).execute(
            as_of=now,
            approval_reference="TEST-APPROVED-1",
            table_names={"asset_instruments"},
            dry_run=False,
        )

    assert report.action_count == 1
    assert report.actions[0].record_id == due_id
    async with async_session_maker() as db:
        due_row = await db.get(AssetInstrument, due_id)
        held_row = await db.get(AssetInstrument, held_id)
        assert due_row is not None
        assert due_row.tombstoned_at is not None
        assert held_row is not None
        assert held_row.tombstoned_at is None


@pytest.mark.asyncio
async def test_lifecycle_executor_does_not_tombstone_twice() -> None:
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    async with async_session_maker() as db:
        due = _instrument(suffix="due", expires_at=now - timedelta(days=1))
        db.add(due)
        await db.flush()
        await db.commit()
        due_id = due.id

        executor = AssetResearchRetentionExecutor(db)
        await executor.execute(
            as_of=now,
            approval_reference="TEST-APPROVED-2",
            table_names={"asset_instruments"},
            dry_run=False,
        )
        second = await executor.execute(
            as_of=now,
            approval_reference="TEST-APPROVED-2",
            table_names={"asset_instruments"},
            dry_run=False,
        )

    assert second.action_count == 0
    async with async_session_maker() as db:
        row = await db.get(AssetInstrument, due_id)
        assert row is not None
        assert row.tombstoned_at is not None
