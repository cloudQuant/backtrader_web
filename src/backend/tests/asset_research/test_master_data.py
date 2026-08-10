"""Contracts for the read-only approved multi-asset master-data catalog."""

from datetime import datetime, timedelta, timezone

import pytest

from app.db.database import async_session_maker
from app.models.asset_research import AssetInstrument
from app.schemas.asset_research import (
    FuturesIdentityDetails,
    InstrumentIdentity,
    InstrumentResolveRequest,
)
from app.services.asset_research.identity import InstrumentResolutionError, InstrumentResolver
from app.services.asset_research.master_data import ApprovedInstrumentCatalog


def _identity(*, version: str = "master-v1") -> InstrumentIdentity:
    return InstrumentIdentity(
        asset_type="futures",
        identity_level="CONTRACT",
        canonical_id="futures:CFFEX:IF2609:CNY",
        display_symbol="IF2609",
        name="沪深300股指期货2609",
        venue="CFFEX",
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="CONTRACT_CODE",
        identifier_value="IF2609",
        product_type="FUTURE",
        metadata_version=version,
        details=FuturesIdentityDetails(
            product_code="IF",
            contract_month="2609",
            expiry_at="2026-09-18T07:15:00+00:00",
            contract_multiplier="300",
            trading_calendar_id="CFFEX",
        ),
    )


def _record(
    identity: InstrumentIdentity,
    *,
    valid_from: datetime,
    valid_to: datetime | None = None,
) -> AssetInstrument:
    return AssetInstrument(
        canonical_id=identity.canonical_id,
        asset_type=identity.asset_type,
        identity_level=identity.identity_level,
        venue=identity.venue,
        currency=identity.currency,
        product_type=identity.product_type,
        identity_json=identity.model_dump(mode="json"),
        metadata_version=identity.metadata_version,
        lifecycle_status="ACTIVE",
        valid_from=valid_from,
        valid_to=valid_to,
    )


@pytest.mark.asyncio
async def test_catalog_returns_only_a_validated_current_master_identity() -> None:
    now = datetime(2026, 8, 2, tzinfo=timezone.utc)
    old = _identity(version="master-v1")
    current = _identity(version="master-v2")
    async with async_session_maker() as db:
        db.add_all(
            [
                _record(old, valid_from=now - timedelta(days=30), valid_to=now - timedelta(seconds=1)),
                _record(current, valid_from=now - timedelta(days=1)),
            ]
        )
        await db.commit()

        catalog = ApprovedInstrumentCatalog(db, now=lambda: now)
        payload = await catalog.list_instruments(asset_type="futures", search="IF2609")
        resolved = await InstrumentResolver(catalog).resolve(
            InstrumentResolveRequest(asset_type="futures", query="IF2609", venue="CFFEX")
        )
        active_asset_types = await catalog.active_asset_types()

    assert [item["metadata_version"] for item in payload["items"]] == ["master-v2"]
    assert payload["items"][0]["identity_level"] == "CONTRACT"
    assert resolved.metadata_version == "master-v2"
    assert resolved.matches_frozen_identity(current)
    assert active_asset_types == {"futures"}


@pytest.mark.asyncio
async def test_catalog_excludes_invalid_or_ambiguous_persisted_master_rows() -> None:
    now = datetime(2026, 8, 2, tzinfo=timezone.utc)
    identity = _identity(version="master-v1")
    malformed = _record(identity, valid_from=now - timedelta(days=2))
    malformed.identity_json = {"asset_type": "futures"}
    tied = _record(_identity(version="master-v2"), valid_from=now - timedelta(days=1))
    tied_second = _record(_identity(version="master-v3"), valid_from=now - timedelta(days=1))
    async with async_session_maker() as db:
        db.add_all([malformed, tied, tied_second])
        await db.commit()

        catalog = ApprovedInstrumentCatalog(db, now=lambda: now)
        payload = await catalog.list_instruments(asset_type="futures", search="IF2609")
        with pytest.raises(InstrumentResolutionError, match="INSTRUMENT_UNSUPPORTED"):
            await InstrumentResolver(catalog).resolve(
                InstrumentResolveRequest(asset_type="futures", query="IF2609", venue="CFFEX")
            )
        active_asset_types = await catalog.active_asset_types()

    assert payload["items"] == []
    assert active_asset_types == set()
