"""Contract tests for strict Iteration 197 master-data identity resolution."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.db.database import async_session_maker
from app.models.asset_research import AssetInstrument
from app.models.market_data_platform import (
    MdInstrumentIdentityRevision,
    MdInstrumentLookupKey,
    MdPublication,
)
from app.schemas.asset_research import (
    FuturesIdentityDetails,
    InstrumentIdentity,
    StockIdentityDetails,
)
from app.schemas.market_data_platform import QueryIdentity
from app.services.market_data.identity import (
    MarketDataIdentityResolutionError,
    MarketDataIdentityResolver,
)
from app.services.market_data.identity_projection import MarketDataIdentityProjectionWriter
from app.services.market_data.publication import (
    PUBLICATION_INSTRUMENT_IDENTITY,
    MarketDataPublicationManager,
)

NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)


def _stock_identity(
    *,
    canonical_id: str = "instrument:stock:CN-SSE:600000",
    venue: str = "CN-SSE",
    version: str = "stock-v1",
) -> InstrumentIdentity:
    return InstrumentIdentity(
        asset_type="stock",
        identity_level="ASSET",
        canonical_id=canonical_id,
        display_symbol="600000",
        name="浦发银行",
        venue=venue,
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="EXCHANGE_SYMBOL",
        identifier_value="600000",
        product_type="EQUITY",
        metadata_version=version,
        details=StockIdentityDetails(exchange_symbol="600000.SH"),
    )


def _futures_identity(*, version: str = "futures-v1") -> InstrumentIdentity:
    return InstrumentIdentity(
        asset_type="futures",
        identity_level="CONTRACT",
        canonical_id="instrument:futures:CFFEX:IF2609",
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
    valid_from: datetime = NOW - timedelta(days=1),
    valid_to: datetime | None = None,
    created_at: datetime = NOW - timedelta(days=1),
) -> AssetInstrument:
    return AssetInstrument(
        id=str(uuid4()),
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
        created_at=created_at,
    )


def _lookup(
    identity: InstrumentIdentity,
    record: AssetInstrument,
    *,
    is_active: bool = True,
) -> MdInstrumentLookupKey:
    """Materialize the exact triple alongside its authoritative version row."""
    return MdInstrumentLookupKey(
        asset_type=identity.asset_type,
        market=identity.venue or "",
        symbol=identity.display_symbol,
        instrument_id=record.id,
        canonical_id=identity.canonical_id,
        metadata_version=identity.metadata_version,
        is_active=is_active,
        valid_from=record.valid_from,
        valid_to=record.valid_to,
    )


def _published_projection(
    record: AssetInstrument,
    *,
    published_at: datetime | None = None,
) -> tuple[MdInstrumentIdentityRevision, MdPublication]:
    """Create an explicit immutable projection fixture with a visibility receipt.

    Test setup writes the two committed facts directly so that resolver tests
    can control historical cutoffs.  Production paths use
    ``MarketDataIdentityProjectionWriter`` to stage the same pair across two
    transactions.
    """
    revision_id = str(uuid4())
    digest = hashlib.sha256(f"projection:{revision_id}".encode()).hexdigest()
    visible_at = published_at or record.created_at
    revision = MdInstrumentIdentityRevision(
        id=revision_id,
        instrument_id=record.id,
        canonical_id=record.canonical_id,
        asset_type=record.asset_type,
        market=record.venue,
        symbol=(
            record.identity_json.get("display_symbol")
            if isinstance(record.identity_json, dict)
            else ""
        )
        or "",
        metadata_version=record.metadata_version,
        identity_json=record.identity_json,
        valid_from=record.valid_from,
        valid_to=record.valid_to,
        revision_number=1,
        revision_sha256=digest,
        created_at=record.created_at,
    )
    receipt = MdPublication(
        entity_type=PUBLICATION_INSTRUMENT_IDENTITY,
        entity_id=revision_id,
        entity_sha256=digest,
        published_at=visible_at,
        created_at=visible_at,
    )
    return revision, receipt


@pytest.mark.asyncio
async def test_resolver_binds_stock_and_futures_to_validated_master_versions() -> None:
    """All seven types share one strict resolver, including legacy stock."""
    stock = _stock_identity()
    future = _futures_identity()
    stock_record = _record(stock)
    future_record = _record(future)
    async with async_session_maker() as db:
        db.add_all(
            [
                stock_record,
                future_record,
                _lookup(future, future_record),
                *_published_projection(stock_record),
                *_published_projection(future_record),
            ]
        )
        await db.commit()

        resolver = MarketDataIdentityResolver(db)
        resolved_stock = await resolver.resolve(
            QueryIdentity(canonical_id=stock.canonical_id), effective_at=NOW
        )
        resolved_future = await resolver.resolve(
            QueryIdentity(asset_type="futures", symbol="IF2609", market="CFFEX"),
            effective_at=NOW,
        )

    assert resolved_stock.canonical_id == stock.canonical_id
    assert resolved_stock.metadata_version == "stock-v1"
    assert resolved_stock.identity == stock
    assert resolved_future.canonical_id == future.canonical_id
    assert resolved_future.identity.details.kind == "FUTURES"


@pytest.mark.asyncio
async def test_resolver_uses_the_complete_exact_tuple_and_never_substitutes_nearby_symbols() -> (
    None
):
    """A provider-like alias, case-folded venue, or duplicate match cannot resolve."""
    primary = _stock_identity(canonical_id="instrument:stock:CN-SSE:600000", venue="CN-SSE")
    other_venue = _stock_identity(canonical_id="instrument:stock:CN-SZSE:600000", venue="CN-SZSE")
    duplicate = _stock_identity(
        canonical_id="instrument:stock:CN-SSE:600001",
        venue="CN-SSE",
        version="stock-v2",
    )
    primary_record = _record(primary)
    other_venue_record = _record(other_venue)

    async with async_session_maker() as db:
        db.add_all(
            [
                primary_record,
                other_venue_record,
                _lookup(primary, primary_record),
                _lookup(other_venue, other_venue_record),
                *_published_projection(primary_record),
                *_published_projection(other_venue_record),
            ]
        )
        await db.commit()
        resolver = MarketDataIdentityResolver(db)

        exact = await resolver.resolve(
            QueryIdentity(asset_type="stock", symbol="600000", market="CN-SZSE"),
            effective_at=NOW,
        )
        with pytest.raises(MarketDataIdentityResolutionError) as missing:
            await resolver.resolve(
                QueryIdentity(asset_type="stock", symbol="600000", market="cn-szse"),
                effective_at=NOW,
            )

        duplicate_record = _record(duplicate)
        # The portable database rule prevents two active mappings.  Retaining
        # a second currently-valid inactive history row is still a corrupt
        # exact mapping, and resolution must reject it rather than pick one.
        db.add_all(
            [
                duplicate_record,
                _lookup(duplicate, duplicate_record, is_active=False),
                *_published_projection(duplicate_record),
            ]
        )
        await db.commit()
        with pytest.raises(MarketDataIdentityResolutionError) as ambiguous:
            await resolver.resolve(
                QueryIdentity(asset_type="stock", symbol="600000", market="CN-SSE"),
                effective_at=NOW,
            )

    assert exact.canonical_id == other_venue.canonical_id
    assert missing.value.code == "IDENTITY_NOT_FOUND"
    assert ambiguous.value.code == "IDENTITY_AMBIGUOUS"


@pytest.mark.asyncio
async def test_resolver_selects_the_latest_valid_version_and_freezes_its_metadata_version() -> None:
    """A latest master version has one stable identity used by downstream fingerprints."""
    old = _futures_identity(version="futures-v1")
    current = _futures_identity(version="futures-v2")
    current_from = NOW - timedelta(days=1)
    old_record = _record(old, valid_from=NOW - timedelta(days=30), valid_to=current_from)
    current_record = _record(current, valid_from=current_from)
    async with async_session_maker() as db:
        db.add_all(
            [
                old_record,
                current_record,
                _lookup(old, old_record, is_active=False),
                _lookup(current, current_record),
                *_published_projection(old_record),
                *_published_projection(current_record),
            ]
        )
        await db.commit()

        resolved = await MarketDataIdentityResolver(db).resolve(
            QueryIdentity(asset_type="futures", symbol="IF2609", market="CFFEX"), effective_at=NOW
        )
        historical = await MarketDataIdentityResolver(db).resolve(
            QueryIdentity(asset_type="futures", symbol="IF2609", market="CFFEX"),
            effective_at=NOW - timedelta(days=5),
        )

    assert resolved.metadata_version == "futures-v2"
    assert resolved.identity == current
    assert resolved.valid_from == current_from
    assert historical.metadata_version == "futures-v1"


@pytest.mark.asyncio
async def test_strict_cutoff_rejects_a_master_identity_backfilled_after_the_cutoff() -> None:
    """Market-effective validity cannot make a later local identity import retroactive."""
    identity = _stock_identity()
    late_record = _record(
        identity,
        valid_from=NOW - timedelta(days=30),
        created_at=NOW + timedelta(days=1),
    )
    async with async_session_maker() as db:
        db.add_all([late_record, *_published_projection(late_record)])
        await db.commit()

        with pytest.raises(MarketDataIdentityResolutionError) as hidden:
            await MarketDataIdentityResolver(db).resolve(
                QueryIdentity(canonical_id=identity.canonical_id),
                effective_at=NOW,
                knowledge_cutoff=NOW,
            )
        resolved = await MarketDataIdentityResolver(db).resolve(
            QueryIdentity(canonical_id=identity.canonical_id),
            effective_at=NOW,
            knowledge_cutoff=NOW + timedelta(days=2),
        )

    assert hidden.value.code == "IDENTITY_NOT_KNOWN_AT_CUTOFF"
    assert resolved.canonical_id == identity.canonical_id


@pytest.mark.asyncio
async def test_identity_projection_stays_hidden_between_transaction_a_and_publication() -> None:
    """A committed projection has no PIT visibility until transaction B records it."""
    identity = _stock_identity()
    record = _record(identity, valid_from=NOW - timedelta(days=30))
    published_at = NOW + timedelta(hours=1)

    async with async_session_maker() as db:
        db.add(record)
        await db.flush()
        projections = MarketDataIdentityProjectionWriter(db, clock=lambda: published_at)
        await projections.project(record)
        await db.commit()  # transaction A: authoritative row, frozen projection, pending receipt

        with pytest.raises(MarketDataIdentityResolutionError) as pending:
            await MarketDataIdentityResolver(db).resolve(
                QueryIdentity(canonical_id=identity.canonical_id),
                effective_at=NOW,
                knowledge_cutoff=published_at + timedelta(hours=1),
            )

        await db.rollback()
        recovery = MarketDataPublicationManager(db, clock=lambda: published_at)
        dry_run_ids = await recovery.recover_pending(dry_run=True)

        with pytest.raises(MarketDataIdentityResolutionError) as after_dry_run:
            await MarketDataIdentityResolver(db).resolve(
                QueryIdentity(canonical_id=identity.canonical_id),
                effective_at=NOW,
                knowledge_cutoff=published_at + timedelta(hours=1),
            )

        await db.rollback()
        applied_ids = await recovery.recover_pending(dry_run=False)  # recovery transaction B

        with pytest.raises(MarketDataIdentityResolutionError) as before_publication:
            await MarketDataIdentityResolver(db).resolve(
                QueryIdentity(canonical_id=identity.canonical_id),
                effective_at=NOW,
                knowledge_cutoff=published_at - timedelta(microseconds=1),
            )
        resolved = await MarketDataIdentityResolver(db).resolve(
            QueryIdentity(canonical_id=identity.canonical_id),
            effective_at=NOW,
            knowledge_cutoff=published_at,
        )

    assert pending.value.code == "IDENTITY_NOT_FOUND"
    assert dry_run_ids == applied_ids
    assert len(applied_ids) == 1
    assert after_dry_run.value.code == "IDENTITY_NOT_FOUND"
    assert before_publication.value.code == "IDENTITY_NOT_KNOWN_AT_CUTOFF"
    assert resolved.known_at == published_at


@pytest.mark.asyncio
async def test_resolver_fails_closed_on_malformed_or_column_mismatched_authoritative_records() -> (
    None
):
    """Invalid persisted JSON must not be skipped in favour of a guessed fallback."""
    malformed = _stock_identity()
    mismatch = _futures_identity()
    malformed_record = _record(malformed)
    malformed_record.identity_json = {"asset_type": "stock"}
    mismatch_record = _record(mismatch)
    mismatch_record.venue = "SHFE"

    async with async_session_maker() as db:
        db.add_all(
            [
                malformed_record,
                mismatch_record,
                *_published_projection(malformed_record),
                *_published_projection(mismatch_record),
            ]
        )
        await db.commit()
        resolver = MarketDataIdentityResolver(db)

        with pytest.raises(MarketDataIdentityResolutionError) as malformed_error:
            await resolver.resolve(
                QueryIdentity(canonical_id=malformed.canonical_id), effective_at=NOW
            )
        with pytest.raises(MarketDataIdentityResolutionError) as mismatch_error:
            await resolver.resolve(
                QueryIdentity(canonical_id=mismatch.canonical_id), effective_at=NOW
            )

    assert malformed_error.value.code == "IDENTITY_INTEGRITY"
    assert mismatch_error.value.code == "IDENTITY_INTEGRITY"


@pytest.mark.asyncio
async def test_resolver_rejects_naive_effective_time_tied_versions_and_expired_records() -> None:
    """Temporal identity selection is UTC, half-open, and ambiguous ties fail closed."""
    tied_first = _stock_identity(version="tied-v1")
    tied_second = _stock_identity(version="tied-v2")
    expired = _futures_identity()
    async with async_session_maker() as db:
        tied_first_record = _record(tied_first)
        tied_second_record = _record(tied_second)
        expired_record = _record(expired, valid_to=NOW)
        db.add_all(
            [
                tied_first_record,
                tied_second_record,
                expired_record,
                *_published_projection(tied_first_record),
                *_published_projection(tied_second_record),
                *_published_projection(expired_record),
            ]
        )
        await db.commit()
        resolver = MarketDataIdentityResolver(db)

        with pytest.raises(MarketDataIdentityResolutionError) as naive:
            await resolver.resolve(
                QueryIdentity(canonical_id=tied_first.canonical_id),
                effective_at=NOW.replace(tzinfo=None),
            )
        with pytest.raises(MarketDataIdentityResolutionError) as tied:
            await resolver.resolve(
                QueryIdentity(canonical_id=tied_first.canonical_id), effective_at=NOW
            )
        with pytest.raises(MarketDataIdentityResolutionError) as expired_error:
            await resolver.resolve(
                QueryIdentity(canonical_id=expired.canonical_id), effective_at=NOW
            )

    assert naive.value.code == "IDENTITY_EFFECTIVE_AT_INVALID"
    assert tied.value.code == "IDENTITY_AMBIGUOUS"
    assert expired_error.value.code == "IDENTITY_NOT_FOUND"


@pytest.mark.asyncio
async def test_resolver_rejects_overlapping_identity_version_windows() -> None:
    """A later valid_from cannot silently supersede an open-ended prior record."""
    first = _stock_identity(version="overlap-v1")
    second = _stock_identity(version="overlap-v2")
    async with async_session_maker() as db:
        first_record = _record(first, valid_from=NOW - timedelta(days=2))
        second_record = _record(second, valid_from=NOW - timedelta(days=1))
        db.add_all(
            [
                first_record,
                second_record,
                *_published_projection(first_record),
                *_published_projection(second_record),
            ]
        )
        await db.commit()

        with pytest.raises(MarketDataIdentityResolutionError) as overlap:
            await MarketDataIdentityResolver(db).resolve(
                QueryIdentity(canonical_id=first.canonical_id), effective_at=NOW
            )

    assert overlap.value.code == "IDENTITY_VERSION_OVERLAP"


@pytest.mark.asyncio
async def test_resolver_fails_closed_when_an_exact_tuple_candidate_scan_exceeds_its_cap() -> None:
    """High-cardinality discovery cannot turn a data lookup into an unbounded scan."""

    class _TooManyRows:
        def all(self):
            return [(object(), object())] * 129

    class _Session:
        async def execute(self, _statement):
            return _TooManyRows()

    resolver = MarketDataIdentityResolver(_Session())
    with pytest.raises(MarketDataIdentityResolutionError) as capped:
        await resolver._load_candidate_rows(
            QueryIdentity(asset_type="stock", symbol="600000", market="CN-SSE")
        )

    assert capped.value.code == "IDENTITY_CANDIDATE_LIMIT_EXCEEDED"


@pytest.mark.asyncio
async def test_exact_lookup_avoids_a_high_cardinality_market_wide_candidate_cap() -> None:
    """An exact tuple resolves even when the venue contains hundreds of other rows."""
    target = _stock_identity()
    target_record = _record(target)
    irrelevant_rows = [
        AssetInstrument(
            id=str(uuid4()),
            canonical_id=f"instrument:stock:CN-SSE:{number:06d}",
            asset_type="stock",
            identity_level="ASSET",
            venue="CN-SSE",
            currency="CNY",
            product_type="EQUITY",
            identity_json={},
            metadata_version="seed-v1",
            lifecycle_status="ACTIVE",
            valid_from=NOW - timedelta(days=1),
        )
        for number in range(1, 502)
    ]

    async with async_session_maker() as db:
        db.add_all(
            [
                *irrelevant_rows,
                target_record,
                _lookup(target, target_record),
                *_published_projection(target_record),
            ]
        )
        await db.commit()

        resolved = await MarketDataIdentityResolver(db).resolve(
            QueryIdentity(asset_type="stock", symbol="600000", market="CN-SSE"),
            effective_at=NOW,
        )

    assert resolved.canonical_id == target.canonical_id
