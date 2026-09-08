"""Maintain the materialized exact-key projection of versioned master data.

``asset_instruments`` remains the authority for identity facts.  This module
only maintains the bounded `(asset_type, market, symbol)` projection used by
the local-first market-data path.  It is deliberately called from the same
transaction that persists an identity, and it can backfill pre-Iteration-197
rows without guessing aliases or normalising a provider symbol.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_research import AssetInstrument
from app.models.market_data_platform import MdInstrumentLookupKey
from app.schemas.asset_research import InstrumentIdentity
from app.services.market_data.identity_projection import (
    MarketDataIdentityProjectionError,
    MarketDataIdentityProjectionWriter,
)


class MarketDataLookupKeyError(ValueError):
    """Stable failure code for an unsafe materialized identity-key operation."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class MarketDataIdentityWriteError(ValueError):
    """Stable failure code for the operator-only market-data identity writer."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class LookupKeyBackfillResult:
    """One bounded backfill batch's observable outcome."""

    processed: int
    created: int
    synchronized: int
    next_after_id: str | None


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite's timezone-less reads to their stored UTC instant."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class MarketDataLookupKeyMaterializer:
    """Synchronize exact lookup keys without making them a second authority."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._projections = MarketDataIdentityProjectionWriter(db)

    @property
    def staged_publication_ids(self) -> tuple[str, ...]:
        """Return backfill receipts that need publishing after a batch commit."""
        return self._projections.staged_publication_ids

    async def publish_staged(self) -> None:
        """Publish backfilled identity projections after the caller commits."""
        await self._projections.publish_staged()

    async def sync_instrument(self, record: AssetInstrument) -> bool:
        """Create or synchronize the exact key for one authoritative record.

        Returns whether a key was created.  Instruments without a venue cannot
        be selected by the public triple contract, so they intentionally do
        not receive a fabricated market key and remain canonical-ID-only.
        """
        identity = self._validated_identity(record)
        if identity.venue is None:
            return False

        keys = list(
            (
                await self._db.execute(
                    select(MdInstrumentLookupKey)
                    .where(MdInstrumentLookupKey.instrument_id == record.id)
                    .order_by(MdInstrumentLookupKey.id)
                )
            )
            .scalars()
            .all()
        )
        if len(keys) > 1:
            raise MarketDataLookupKeyError("LOOKUP_KEY_INTEGRITY")

        is_active = self._is_currently_registered(record)
        if is_active:
            conflicts = list(
                (
                    await self._db.execute(
                        select(MdInstrumentLookupKey).where(
                            MdInstrumentLookupKey.asset_type == identity.asset_type,
                            MdInstrumentLookupKey.market == identity.venue,
                            MdInstrumentLookupKey.symbol == identity.display_symbol,
                            MdInstrumentLookupKey.is_active.is_(True),
                            MdInstrumentLookupKey.instrument_id != record.id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            if conflicts:
                raise MarketDataLookupKeyError("LOOKUP_KEY_ACTIVE_CONFLICT")

        if not keys:
            self._db.add(
                MdInstrumentLookupKey(
                    asset_type=identity.asset_type,
                    market=identity.venue,
                    symbol=identity.display_symbol,
                    instrument_id=record.id,
                    canonical_id=identity.canonical_id,
                    metadata_version=identity.metadata_version,
                    is_active=is_active,
                    valid_from=record.valid_from,
                    valid_to=record.valid_to,
                )
            )
            return True

        key = keys[0]
        # A key that points to different identity facts has already been used
        # as a query index, so rewriting it would silently redirect history.
        if (
            key.asset_type != identity.asset_type
            or key.market != identity.venue
            or key.symbol != identity.display_symbol
            or key.canonical_id != identity.canonical_id
            or key.metadata_version != identity.metadata_version
            or key.instrument_id != record.id
            or _as_utc(key.valid_from) != _as_utc(record.valid_from)
        ):
            raise MarketDataLookupKeyError("LOOKUP_KEY_INTEGRITY")

        # Validity and active state are lifecycle attributes of the authority,
        # and are the only projection fields this method is permitted to move.
        key.valid_to = record.valid_to
        key.is_active = is_active
        return False

    async def retire_instrument(self, record: AssetInstrument, *, valid_to: datetime) -> None:
        """Close an old authoritative version and retire its projected key."""
        close_at = _as_utc(valid_to)
        if close_at <= _as_utc(record.valid_from):
            raise MarketDataLookupKeyError("LOOKUP_KEY_INVALID_VALIDITY_WINDOW")
        record.valid_to = close_at
        # Calling the common synchronizer also creates a historical inactive
        # projection for a pre-197 record that did not have one yet.
        await self.sync_instrument(record)

    async def backfill_batch(
        self,
        *,
        after_id: str | None = None,
        limit: int = 500,
    ) -> LookupKeyBackfillResult:
        """Synchronize a deterministic bounded batch of pre-existing identities."""
        if limit < 1 or limit > 10_000:
            raise ValueError("limit must be between 1 and 10000")
        statement = select(AssetInstrument).order_by(AssetInstrument.id).limit(limit)
        if after_id is not None:
            statement = statement.where(AssetInstrument.id > after_id)
        rows = list((await self._db.execute(statement)).scalars().all())
        created = 0
        synchronized = 0
        for record in rows:
            if await self.sync_instrument(record):
                created += 1
            else:
                synchronized += 1
        try:
            # The bounded recovery path must make an identity queryable by the
            # normalized v2 resolver as well as rebuild its legacy exact key.
            # ``project_records`` only stages receipts here; the operator
            # publishes them after the batch transaction commits.
            await self._projections.project_records(rows)
        except MarketDataIdentityProjectionError as exc:
            raise MarketDataLookupKeyError("IDENTITY_PROJECTION_WRITE_CONFLICT") from exc
        return LookupKeyBackfillResult(
            processed=len(rows),
            created=created,
            synchronized=synchronized,
            next_after_id=rows[-1].id if rows else None,
        )

    @staticmethod
    def _is_currently_registered(record: AssetInstrument) -> bool:
        return (
            record.lifecycle_status == "ACTIVE"
            and record.tombstoned_at is None
            and record.valid_to is None
        )

    @staticmethod
    def _validated_identity(record: AssetInstrument) -> InstrumentIdentity:
        try:
            identity = InstrumentIdentity.model_validate(record.identity_json)
        except ValidationError as exc:
            raise MarketDataLookupKeyError("LOOKUP_KEY_IDENTITY_INTEGRITY") from exc
        if (
            identity.canonical_id != record.canonical_id
            or identity.asset_type != record.asset_type
            or identity.identity_level != record.identity_level
            or identity.venue != record.venue
            or identity.currency != record.currency
            or identity.product_type != record.product_type
            or identity.metadata_version != record.metadata_version
        ):
            raise MarketDataLookupKeyError("LOOKUP_KEY_IDENTITY_INTEGRITY")
        return identity


class MarketDataIdentityWriter:
    """Persist approved identity versions without changing generic research writes.

    The Iteration 197 import path owns this writer.  It intentionally does not
    hook ``AssetResearchOrchestrator.persist_identity``: Iteration 196 and
    pre-migration environments must remain able to create their authoritative
    identities without requiring the new ``md_*`` tables.  The operator runs
    this writer only after the 197 migrations and catalog bootstrap are ready.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._materializer = MarketDataLookupKeyMaterializer(db)
        self._projections = MarketDataIdentityProjectionWriter(db)

    @property
    def staged_publication_ids(self) -> tuple[str, ...]:
        """Return v2 identity receipts that need post-commit publication."""
        return self._projections.staged_publication_ids

    async def publish_staged(self) -> None:
        """Publish this writer's frozen identities after its transaction commits."""
        await self._projections.publish_staged()

    async def persist_identity(
        self,
        identity: InstrumentIdentity,
        *,
        valid_from: datetime | None = None,
    ) -> AssetInstrument:
        """Append one approved identity version and materialize its exact key.

        Reusing the same canonical ID and metadata version is allowed only for
        the exact frozen identity already present.  A new version retires a
        prior active version inside the same savepoint before its active key
        is inserted, preserving portable exact-key uniqueness on every
        supported database.
        """
        if not isinstance(identity, InstrumentIdentity):
            raise TypeError("identity must be an InstrumentIdentity")
        existing_rows = list(
            (
                await self._db.execute(
                    select(AssetInstrument).where(
                        AssetInstrument.canonical_id == identity.canonical_id,
                        AssetInstrument.metadata_version == identity.metadata_version,
                    )
                )
            )
            .scalars()
            .all()
        )
        if len(existing_rows) > 1:
            raise MarketDataIdentityWriteError("MARKET_DATA_IDENTITY_VERSION_INTEGRITY")
        if existing_rows:
            existing = existing_rows[0]
            if not _record_matches_identity(existing, identity):
                raise MarketDataIdentityWriteError("MARKET_DATA_IDENTITY_VERSION_CONFLICT")
            try:
                async with self._db.begin_nested():
                    await self._materializer.sync_instrument(existing)
                    await self._db.flush()
            except MarketDataLookupKeyError as exc:
                raise MarketDataIdentityWriteError(exc.code) from exc
            except IntegrityError as exc:
                raise MarketDataIdentityWriteError("LOOKUP_KEY_WRITE_CONFLICT") from exc
            try:
                await self._projections.project(existing)
            except MarketDataIdentityProjectionError as exc:
                raise MarketDataIdentityWriteError(exc.code) from exc
            return existing

        effective_from = (
            _as_utc(valid_from) if valid_from is not None else datetime.now(timezone.utc)
        )
        projection_records: list[AssetInstrument] = []
        try:
            async with self._db.begin_nested():
                prior_versions = list(
                    (
                        await self._db.execute(
                            select(AssetInstrument)
                            .where(
                                AssetInstrument.canonical_id == identity.canonical_id,
                                AssetInstrument.metadata_version != identity.metadata_version,
                            )
                            .order_by(AssetInstrument.valid_from)
                        )
                    )
                    .scalars()
                    .all()
                )
                for prior in prior_versions:
                    prior_from = _as_utc(prior.valid_from)
                    prior_to = _as_utc(prior.valid_to) if prior.valid_to is not None else None
                    if prior_from >= effective_from:
                        raise MarketDataIdentityWriteError("IDENTITY_VERSION_START_CONFLICT")
                    if prior_to is None:
                        await self._materializer.retire_instrument(prior, valid_to=effective_from)
                        projection_records.append(prior)
                    elif prior_to > effective_from:
                        raise MarketDataIdentityWriteError("IDENTITY_VERSION_WINDOW_OVERLAP")
                    else:
                        # A closed pre-197 version may not have a projection
                        # yet. Retain its historical queryability without
                        # creating aliases or rewriting identity facts.
                        await self._materializer.sync_instrument(prior)
                        projection_records.append(prior)
                await self._db.flush()
                record = AssetInstrument(
                    canonical_id=identity.canonical_id,
                    asset_type=identity.asset_type,
                    identity_level=identity.identity_level,
                    venue=identity.venue,
                    currency=identity.currency,
                    product_type=identity.product_type,
                    identity_json=identity.model_dump(mode="json"),
                    metadata_version=identity.metadata_version,
                    lifecycle_status="ACTIVE",
                    valid_from=effective_from,
                )
                self._db.add(record)
                await self._db.flush()
                await self._materializer.sync_instrument(record)
                await self._db.flush()
        except MarketDataLookupKeyError as exc:
            raise MarketDataIdentityWriteError(exc.code) from exc
        except IntegrityError as exc:
            raise MarketDataIdentityWriteError("LOOKUP_KEY_WRITE_CONFLICT") from exc
        try:
            await self._projections.project_records((*projection_records, record))
        except MarketDataIdentityProjectionError as exc:
            raise MarketDataIdentityWriteError(exc.code) from exc
        return record


def _record_matches_identity(record: AssetInstrument, identity: InstrumentIdentity) -> bool:
    """Reject a reused canonical/version label that points to different facts."""
    try:
        stored = InstrumentIdentity.model_validate(record.identity_json)
    except ValidationError:
        return False
    return (
        stored.matches_frozen_identity(identity)
        and record.asset_type == identity.asset_type
        and record.identity_level == identity.identity_level
        and record.venue == identity.venue
        and record.currency == identity.currency
        and record.product_type == identity.product_type
        and record.metadata_version == identity.metadata_version
    )
