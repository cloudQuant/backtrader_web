"""Approved static schedule manifests are auditable configuration, not market scans."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.asset_research import (
    AssetDataSourceRegistry,
    AssetScheduleManifest,
    AssetSignalSchedule,
)
from app.schemas.asset_research import (
    ApprovedScheduleManifestCreateRequest,
    ApprovedScheduleManifestEntry,
    AssetSignalScheduleCreateRequest,
    FuturesIdentityDetails,
    InstrumentIdentity,
)
from app.services.asset_research.data import DEFAULT_ASSET_RESEARCH_SOURCE_ID
from app.services.asset_research.orchestrator import (
    AssetResearchOrchestrationError,
    AssetResearchOrchestrator,
)


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


def _manifest_request(*, version: str = "v1") -> ApprovedScheduleManifestCreateRequest:
    return ApprovedScheduleManifestCreateRequest(
        manifest_key="approved-futures-shadow",
        manifest_version=version,
        owner_scope="PUBLIC_SHADOW",
        approval_reference="CAB-191-001",
        evidence_uri="evidence://change/CAB-191-001",
        evidence_content_hash="a" * 64,
        entries=[
            ApprovedScheduleManifestEntry(
                entry_key="if2609-standard",
                schedule=AssetSignalScheduleCreateRequest(
                    asset_type="futures",
                    canonical_id="futures:CFFEX:IF2609:CNY",
                    horizon_code="standard",
                    cron_expression="10 19 * * 1-5",
                    timezone="Asia/Shanghai",
                    cutoff_policy="futures-complete-session-v1",
                ),
            )
        ],
    )


async def _seed_authorized_target(service: AssetResearchOrchestrator) -> None:
    service.db.add(
        AssetDataSourceRegistry(
            source_id=DEFAULT_ASSET_RESEARCH_SOURCE_ID,
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
    await service.persist_identity(_identity())


@pytest.mark.asyncio
async def test_approved_manifest_expands_one_exact_system_schedule_idempotently() -> None:
    async with async_session_maker() as db:
        service = AssetResearchOrchestrator(db)
        await _seed_authorized_target(service)
        request = _manifest_request()

        created = await service.create_approved_schedule_manifest(
            actor_id="admin-fixture",
            request=request,
        )
        repeated = await service.create_approved_schedule_manifest(
            actor_id="admin-fixture",
            request=request,
        )
        schedules = list(
            (
                await db.execute(
                    select(AssetSignalSchedule).where(
                        AssetSignalSchedule.approved_manifest_id == created.id
                    )
                )
            ).scalars()
        )

    assert created.id == repeated.id
    assert created.owner_scope == "PUBLIC_SHADOW"
    assert created.status == "ACTIVE"
    assert len(schedules) == 1
    schedule = schedules[0]
    assert schedule.owner_scope == "PUBLIC_SHADOW"
    assert schedule.user_id is None
    assert schedule.canonical_id == "futures:CFFEX:IF2609:CNY"
    assert schedule.identity_version == "fixture-v1"
    assert schedule.manifest_entry_key == "if2609-standard"
    assert schedule.manifest_content_hash == created.content_hash
    assert schedule.system_target_key is not None


@pytest.mark.asyncio
async def test_manifest_refuses_unapproved_capability_without_creating_config_rows() -> None:
    async with async_session_maker() as db:
        service = AssetResearchOrchestrator(db)

        with pytest.raises(AssetResearchOrchestrationError, match="SOURCE_CAPABILITY_UNAVAILABLE"):
            await service.create_approved_schedule_manifest(
                actor_id="admin-fixture",
                request=_manifest_request(),
            )

        assert list((await db.execute(select(AssetScheduleManifest))).scalars()) == []
        assert list((await db.execute(select(AssetSignalSchedule))).scalars()) == []


@pytest.mark.asyncio
async def test_retiring_a_manifest_disables_its_schedule_and_allows_a_new_version() -> None:
    async with async_session_maker() as db:
        service = AssetResearchOrchestrator(db)
        await _seed_authorized_target(service)
        first = await service.create_approved_schedule_manifest(
            actor_id="admin-fixture",
            request=_manifest_request(version="v1"),
        )
        retired = await service.retire_approved_schedule_manifest(
            actor_id="admin-fixture",
            manifest_id=first.id,
            reason_codes=["SCHEDULE.MANIFEST_REPLACED"],
        )
        second = await service.create_approved_schedule_manifest(
            actor_id="admin-fixture",
            request=_manifest_request(version="v2"),
        )
        first_schedule = (
            await db.execute(
                select(AssetSignalSchedule).where(
                    AssetSignalSchedule.approved_manifest_id == first.id
                )
            )
        ).scalar_one()

    assert retired.status == "RETIRED"
    assert retired.retired_by == "admin-fixture"
    assert first_schedule.enabled is False
    assert first_schedule.system_target_key is None
    assert second.id != first.id
