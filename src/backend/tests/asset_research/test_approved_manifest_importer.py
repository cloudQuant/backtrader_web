"""Dry-run and audit contracts for approved manifest imports."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.asset_research import AssetDataSourceRegistry, AssetInstrument
from app.schemas.asset_research import (
    ApprovedScheduleManifestCreateRequest,
    ApprovedScheduleManifestEntry,
    AssetSignalScheduleCreateRequest,
    FuturesIdentityDetails,
    InstrumentIdentity,
)
from app.services.asset_research.importers.approved_manifest_importer import (
    ApprovedManifestImporter,
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
        metadata_version="pilot-v1",
        details=FuturesIdentityDetails(
            product_code="IF",
            contract_month="2609",
            expiry_at=datetime(2026, 9, 18, 7, 15, tzinfo=timezone.utc),
            contract_multiplier="300",
            trading_calendar_id="CFFEX",
        ),
    )


def _payload() -> dict:
    return {
        "source_registry": [
            {
                "source_id": "akshare_data",
                "asset_types": ["futures"],
                "jurisdictions": ["GLOBAL"],
                "license_status": "APPROVED",
                "allowed_uses": ["RESEARCH_ONLY"],
                "redistribution_policy": "NO_REDISTRIBUTION",
                "derived_data_policy": "ALLOWED",
                "retention_policy": "research-v1",
                "effective_from": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "freshness_sla": {},
                "enabled": True,
            }
        ],
        "instruments": [_identity().model_dump(mode="json")],
        "manifests": [
            ApprovedScheduleManifestCreateRequest(
                manifest_key="pilot-futures",
                manifest_version="v1",
                owner_scope="PUBLIC_SHADOW",
                approval_reference="IMPORT-TEST-ONLY",
                evidence_uri="evidence://test/pilot-futures",
                evidence_content_hash="a" * 64,
                entries=[
                    ApprovedScheduleManifestEntry(
                        entry_key="if2609",
                        schedule=AssetSignalScheduleCreateRequest(
                            asset_type="futures",
                            canonical_id=_identity().canonical_id,
                            cron_expression="10 19 * * 1-5",
                            timezone="Asia/Shanghai",
                            cutoff_policy="futures-complete-session-v1",
                        ),
                    )
                ],
            ).model_dump(mode="json")
        ],
    }


@pytest.mark.asyncio
async def test_approved_manifest_import_dry_run_does_not_persist() -> None:
    async with async_session_maker() as db:
        report = await ApprovedManifestImporter(db).import_payload(
            payload=_payload(),
            dry_run=True,
        )

    assert report.passed is True
    assert report.dry_run is True
    async with async_session_maker() as db:
        assert (await db.execute(select(AssetInstrument))).scalars().all() == []
        assert (await db.execute(select(AssetDataSourceRegistry))).scalars().all() == []


@pytest.mark.asyncio
async def test_approved_manifest_import_persists_evidence_bound_facts() -> None:
    async with async_session_maker() as db:
        report = await ApprovedManifestImporter(db).import_payload(
            payload=_payload(),
            dry_run=False,
            valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    assert report.passed is True
    async with async_session_maker() as db:
        instruments = list((await db.execute(select(AssetInstrument))).scalars())
        sources = list((await db.execute(select(AssetDataSourceRegistry))).scalars())
        assert len(instruments) == 1
        assert instruments[0].canonical_id == "futures:CFFEX:IF2609:CNY"
        assert len(sources) == 1
        assert sources[0].enabled is True
