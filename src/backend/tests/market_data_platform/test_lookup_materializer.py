"""Regression contracts for exact-key materialization and historical closure."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.database import async_session_maker
from app.models.asset_research import AssetInstrument
from app.models.market_data_platform import MdInstrumentLookupKey
from app.schemas.asset_research import FuturesIdentityDetails, InstrumentIdentity
from app.schemas.market_data_platform import QueryIdentity
from app.services.market_data.identity import MarketDataIdentityResolver
from app.services.market_data.master_data import (
    MarketDataIdentityWriteError,
    MarketDataIdentityWriter,
    MarketDataLookupKeyMaterializer,
)

NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)


def _identity(
    *,
    version: str = "futures-v1",
    canonical_id: str = "instrument:futures:CFFEX:IF2609",
    symbol: str = "IF2609",
) -> InstrumentIdentity:
    return InstrumentIdentity(
        asset_type="futures",
        identity_level="CONTRACT",
        canonical_id=canonical_id,
        display_symbol=symbol,
        name="沪深300股指期货2609",
        venue="CFFEX",
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="CONTRACT_CODE",
        identifier_value=symbol,
        product_type="FUTURE",
        metadata_version=version,
        details=FuturesIdentityDetails(
            product_code=symbol[:2],
            contract_month="2609",
            expiry_at="2026-09-18T07:15:00+00:00",
            contract_multiplier="300",
            trading_calendar_id="CFFEX",
        ),
    )


@pytest.mark.asyncio
async def test_operator_identity_writer_materializes_exact_key_and_retires_prior_version() -> None:
    """The 197-only operator writer keeps triple resolution operational."""
    first_identity = _identity()
    second_identity = _identity(version="futures-v2")
    first_start = NOW - timedelta(days=30)
    second_start = NOW - timedelta(days=1)

    async with async_session_maker() as db:
        writer = MarketDataIdentityWriter(db)
        first = await writer.persist_identity(first_identity, valid_from=first_start)
        second = await writer.persist_identity(second_identity, valid_from=second_start)
        await db.commit()
        await writer.publish_staged()

        keys = list(
            (
                await db.execute(
                    select(MdInstrumentLookupKey)
                    .where(MdInstrumentLookupKey.instrument_id.in_([first.id, second.id]))
                    .order_by(MdInstrumentLookupKey.metadata_version)
                )
            )
            .scalars()
            .all()
        )
        historical = await MarketDataIdentityResolver(db).resolve(
            QueryIdentity(asset_type="futures", symbol="IF2609", market="CFFEX"),
            effective_at=NOW - timedelta(days=5),
        )
        current = await MarketDataIdentityResolver(db).resolve(
            QueryIdentity(asset_type="futures", symbol="IF2609", market="CFFEX"),
            effective_at=NOW,
        )

    assert len(keys) == 2
    assert keys[0].is_active is False
    assert keys[0].valid_to is not None
    assert keys[0].valid_to.replace(tzinfo=timezone.utc) == second_start
    assert keys[1].is_active is True
    assert historical.metadata_version == "futures-v1"
    assert current.metadata_version == "futures-v2"


@pytest.mark.asyncio
async def test_backfill_creates_a_missing_projection_for_an_existing_persisted_identity() -> None:
    """A bounded backfill can make pre-197 master data visible to triple lookup."""
    identity = _identity()
    async with async_session_maker() as db:
        writer = MarketDataIdentityWriter(db)
        record = await writer.persist_identity(identity, valid_from=NOW - timedelta(days=1))
        await db.flush()

        # Remove the just-created key in the same test transaction to model a
        # pre-197 row, then backfill it through the public bounded operation.
        keys = list(
            (
                await db.execute(
                    select(MdInstrumentLookupKey).where(
                        MdInstrumentLookupKey.instrument_id == record.id
                    )
                )
            )
            .scalars()
            .all()
        )
        for existing_key in keys:
            await db.delete(existing_key)
        await db.flush()

        materializer = MarketDataLookupKeyMaterializer(db)
        result = await materializer.backfill_batch(limit=100)
        await db.commit()
        await materializer.publish_staged()
        resolved = await MarketDataIdentityResolver(db).resolve(
            QueryIdentity(asset_type="futures", symbol="IF2609", market="CFFEX"),
            effective_at=NOW,
        )

    assert result.processed == 1
    assert result.created == 1
    assert resolved.canonical_id == identity.canonical_id


@pytest.mark.asyncio
async def test_backfill_allows_historical_reuse_of_an_exact_code_and_metadata_version() -> None:
    """A venue can reuse a code after the older canonical instrument has ended."""
    first_identity = _identity(canonical_id="instrument:futures:CFFEX:IF2609-old")
    second_identity = _identity(canonical_id="instrument:futures:CFFEX:IF2609-new")
    first = AssetInstrument(
        canonical_id=first_identity.canonical_id,
        asset_type=first_identity.asset_type,
        identity_level=first_identity.identity_level,
        venue=first_identity.venue,
        currency=first_identity.currency,
        product_type=first_identity.product_type,
        identity_json=first_identity.model_dump(mode="json"),
        metadata_version=first_identity.metadata_version,
        lifecycle_status="ACTIVE",
        valid_from=NOW - timedelta(days=30),
        valid_to=NOW - timedelta(days=1),
    )
    second = AssetInstrument(
        canonical_id=second_identity.canonical_id,
        asset_type=second_identity.asset_type,
        identity_level=second_identity.identity_level,
        venue=second_identity.venue,
        currency=second_identity.currency,
        product_type=second_identity.product_type,
        identity_json=second_identity.model_dump(mode="json"),
        metadata_version=second_identity.metadata_version,
        lifecycle_status="ACTIVE",
        valid_from=NOW - timedelta(days=1),
    )
    async with async_session_maker() as db:
        db.add_all([first, second])
        await db.flush()
        materializer = MarketDataLookupKeyMaterializer(db)
        result = await materializer.backfill_batch(limit=100)
        await db.commit()
        await materializer.publish_staged()
        historical = await MarketDataIdentityResolver(db).resolve(
            QueryIdentity(asset_type="futures", symbol="IF2609", market="CFFEX"),
            effective_at=NOW - timedelta(days=5),
        )
        current = await MarketDataIdentityResolver(db).resolve(
            QueryIdentity(asset_type="futures", symbol="IF2609", market="CFFEX"),
            effective_at=NOW,
        )

    assert result.created == 2
    assert historical.canonical_id == first_identity.canonical_id
    assert current.canonical_id == second_identity.canonical_id


@pytest.mark.asyncio
async def test_failed_key_conflict_rolls_back_the_entire_version_transition() -> None:
    """A caught write conflict cannot leave a closed old version or orphan new row."""
    first_identity = _identity(canonical_id="instrument:futures:CFFEX:IF2609")
    conflict_identity = _identity(
        canonical_id="instrument:futures:CFFEX:IH2609",
        symbol="IH2609",
    )
    replacement = _identity(version="futures-v2", symbol="IH2609")
    first_start = NOW - timedelta(days=30)
    replacement_start = NOW - timedelta(days=1)

    async with async_session_maker() as db:
        writer = MarketDataIdentityWriter(db)
        first = await writer.persist_identity(first_identity, valid_from=first_start)
        await writer.persist_identity(conflict_identity, valid_from=first_start)
        await db.commit()

        with pytest.raises(MarketDataIdentityWriteError) as conflict:
            await writer.persist_identity(replacement, valid_from=replacement_start)
        await db.commit()
        await db.refresh(first)
        versions = list(
            (
                await db.execute(
                    select(AssetInstrument)
                    .where(AssetInstrument.canonical_id == first_identity.canonical_id)
                    .order_by(AssetInstrument.metadata_version)
                )
            )
            .scalars()
            .all()
        )
        keys = list(
            (
                await db.execute(
                    select(MdInstrumentLookupKey).where(
                        MdInstrumentLookupKey.instrument_id == first.id
                    )
                )
            )
            .scalars()
            .all()
        )

    assert conflict.value.code == "LOOKUP_KEY_ACTIVE_CONFLICT"
    assert first.valid_to is None
    assert len(versions) == 1
    assert len(keys) == 1
    assert keys[0].is_active is True
