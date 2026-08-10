"""Non-destructive lifecycle planning contracts for asset research."""

from datetime import datetime, timedelta, timezone

import pytest

from app.db.database import async_session_maker
from app.models.asset_research import ASSET_RESEARCH_TABLES, AssetInstrument, AssetScheduleManifest
from app.services.asset_research import retention as retention_module
from app.services.asset_research.retention import AssetResearchRetentionService


def _instrument(*, suffix: str, expires_at: datetime, legal_hold: bool = False) -> AssetInstrument:
    return AssetInstrument(
        canonical_id=f"futures:CFFEX:IF2609:CNY:{suffix}",
        asset_type="futures",
        identity_level="CONTRACT",
        venue="CFFEX",
        currency="CNY",
        product_type="FUTURE",
        identity_json={"fixture": suffix},
        metadata_version="retention-fixture-v1",
        retention_expires_at=expires_at,
        legal_hold=legal_hold,
    )


def _schedule_manifest(*, suffix: str, expires_at: datetime) -> AssetScheduleManifest:
    return AssetScheduleManifest(
        manifest_key=f"retention-manifest-{suffix}",
        manifest_version="v1",
        owner_scope="ADMIN_EVAL",
        approval_reference="RETENTION-TEST-ONLY",
        evidence_uri=f"evidence://retention/{suffix}",
        evidence_content_hash="a" * 64,
        content_hash="b" * 64,
        approved_by="retention-fixture-admin",
        approved_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        retention_expires_at=expires_at,
    )


def test_retention_dry_run_covers_every_asset_research_table() -> None:
    """A new immutable asset fact must not silently fall outside lifecycle preflight."""
    assert set(retention_module._RETENTION_MODELS_BY_TABLE) == ASSET_RESEARCH_TABLES


@pytest.mark.asyncio
async def test_retention_dry_run_only_lists_due_non_held_non_tombstoned_facts() -> None:
    """A lifecycle preview must not select records that cannot be cleaned safely."""
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    async with async_session_maker() as db:
        eligible = _instrument(suffix="eligible", expires_at=now - timedelta(days=1))
        held = _instrument(
            suffix="held", expires_at=now - timedelta(days=1), legal_hold=True
        )
        future = _instrument(suffix="future", expires_at=now + timedelta(days=1))
        tombstoned = _instrument(suffix="tombstoned", expires_at=now - timedelta(days=1))
        tombstoned.tombstoned_at = now - timedelta(hours=1)
        db.add_all([eligible, held, future, tombstoned])
        await db.flush()

        report = await AssetResearchRetentionService(db).plan_dry_run(
            as_of=now,
            table_names={"asset_instruments"},
        )

    assert report.eligible_count == 1
    assert report.legal_hold_count == 1
    assert report.already_tombstoned_count == 1
    assert report.candidates[0].table_name == "asset_instruments"
    assert report.candidates[0].record_id == eligible.id


@pytest.mark.asyncio
async def test_retention_dry_run_includes_due_approved_schedule_manifests() -> None:
    """Approval evidence is an asset-research fact and cannot bypass lifecycle planning."""
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    async with async_session_maker() as db:
        manifest = _schedule_manifest(suffix="due", expires_at=now - timedelta(days=1))
        db.add(manifest)
        await db.flush()

        report = await AssetResearchRetentionService(db).plan_dry_run(
            as_of=now,
            table_names={"asset_schedule_manifests"},
        )

    assert report.eligible_count == 1
    assert report.candidates[0].table_name == "asset_schedule_manifests"
    assert report.candidates[0].record_id == manifest.id


@pytest.mark.asyncio
async def test_retention_dry_run_emits_aggregated_bounded_lifecycle_metrics(monkeypatch) -> None:
    """A dry-run publishes classifications, not record IDs, into the metric registry."""
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        retention_module,
        "record_asset_research_lifecycle",
        lambda **event: events.append(event),
    )
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    async with async_session_maker() as db:
        held = _instrument(
            suffix="metric-held", expires_at=now - timedelta(days=1), legal_hold=True
        )
        tombstoned = _instrument(suffix="metric-tombstoned", expires_at=now - timedelta(days=1))
        tombstoned.tombstoned_at = now - timedelta(hours=1)
        db.add_all(
            [
                _instrument(suffix="metric-eligible", expires_at=now - timedelta(days=1)),
                held,
                tombstoned,
            ]
        )
        await db.flush()

        await AssetResearchRetentionService(db).plan_dry_run(
            as_of=now,
            table_names={"asset_instruments"},
        )

    assert events == [
        {"retention_class": "research-v1", "result": "ELIGIBLE", "amount": 1},
        {"retention_class": "research-v1", "result": "HELD", "amount": 1},
        {"retention_class": "research-v1", "result": "TOMBSTONED", "amount": 1},
    ]
