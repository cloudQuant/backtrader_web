"""Post-commit visibility receipts for Iteration 197 market-data evidence.

Writing a market-data fact and making it visible to a point-in-time query are
two different events.  A database row can be flushed before the surrounding
transaction commits, so a Python ``created_at`` value is not proof that a
strict replay was able to observe it.  This module implements the small,
shared publication protocol used by observations, calendar snapshots and
market-data master-data projections:

1. write the immutable business entity and a pending ``MdPublication`` in one
   transaction;
2. commit that transaction;
3. in a new transaction, append the trusted post-commit visibility instant.

Readers require the publication receipt.  If the process dies between steps 2
and 3, the entity is deliberately durable-but-hidden rather than being visible
at an unjustified historical cutoff.  Operators can safely resume publication
of that pending receipt later.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data_platform import (
    MdCalendarSnapshot,
    MdInstrumentIdentityRevision,
    MdPublication,
    MdSourceSnapshot,
    MdVisibilitySequenceAllocator,
)

UTC = timezone.utc

PUBLICATION_SOURCE_SNAPSHOT = "source_snapshot"
PUBLICATION_CALENDAR_SNAPSHOT = "calendar_snapshot"
PUBLICATION_INSTRUMENT_IDENTITY = "instrument_identity_revision"
_ENTITY_TYPES = frozenset(
    {
        PUBLICATION_SOURCE_SNAPSHOT,
        PUBLICATION_CALENDAR_SNAPSHOT,
        PUBLICATION_INSTRUMENT_IDENTITY,
    }
)


class MarketDataPublicationError(ValueError):
    """Stable failure code for an unsafe publication transition."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class MarketDataVisibilityAnchor:
    """The complete, server-frozen boundary for one strict local replay.

    Timestamps alone cannot distinguish receipts sealed in the same database
    timestamp tick.  The canonical sequence supplies that missing order.  A
    zero maximum is valid and represents a cutoff before any sealed receipt.
    """

    visible_at: datetime
    max_visibility_sequence: int

    def __post_init__(self) -> None:
        if self.visible_at.tzinfo is None or self.visible_at.utcoffset() is None:
            raise ValueError("visibility anchor visible_at must be timezone-aware")
        if (
            not isinstance(self.max_visibility_sequence, int)
            or isinstance(self.max_visibility_sequence, bool)
            or self.max_visibility_sequence < 0
        ):
            raise ValueError("visibility anchor sequence must be a non-negative integer")
        object.__setattr__(self, "visible_at", self.visible_at.astimezone(UTC))

    def permits(self, *, visible_at: datetime, visibility_sequence: int) -> bool:
        """Return whether one sealed receipt belongs to this immutable replay."""
        if (
            not isinstance(visibility_sequence, int)
            or isinstance(visibility_sequence, bool)
            or visibility_sequence < 1
        ):
            raise ValueError("visibility sequence must be a positive integer")
        if visible_at.tzinfo is None or visible_at.utcoffset() is None:
            raise ValueError("receipt visible_at must be timezone-aware")
        # Both components are independently required.  A strict request may
        # deliberately name a future availability cutoff.  A receipt sealed
        # *after* the anchor can still have a visibility timestamp below that
        # cutoff (for example because a writer's clock was held at an earlier
        # representable instant).  A purely lexicographic comparison would
        # then leak its larger global sequence into the frozen replay.
        return (
            visible_at.astimezone(UTC) <= self.visible_at
            and visibility_sequence <= self.max_visibility_sequence
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise MarketDataPublicationError(f"{field_name}_INVALID")
    return value.astimezone(UTC)


class MarketDataPublicationManager:
    """Stage and publish immutable entities without trusting pre-commit clocks."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._db = db
        self._clock = clock or _utc_now

    async def stage(
        self,
        *,
        entity_type: str,
        entity_id: str,
        entity_sha256: str,
    ) -> MdPublication:
        """Add a pending receipt in the caller's still-uncommitted transaction."""
        if entity_type not in _ENTITY_TYPES:
            raise MarketDataPublicationError("PUBLICATION_ENTITY_TYPE_INVALID")
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise MarketDataPublicationError("PUBLICATION_ENTITY_ID_INVALID")
        if not _is_sha256(entity_sha256):
            raise MarketDataPublicationError("PUBLICATION_ENTITY_HASH_INVALID")

        existing = await self._db.scalar(
            select(MdPublication).where(
                MdPublication.entity_type == entity_type,
                MdPublication.entity_id == entity_id,
            )
        )
        if existing is not None:
            if existing.entity_sha256 != entity_sha256:
                raise MarketDataPublicationError("PUBLICATION_ENTITY_CONFLICT")
            return existing

        receipt = MdPublication(
            entity_type=entity_type,
            entity_id=entity_id,
            entity_sha256=entity_sha256,
        )
        self._db.add(receipt)
        try:
            await self._db.flush()
        except IntegrityError as exc:
            raise MarketDataPublicationError("PUBLICATION_WRITE_CONFLICT") from exc
        return receipt

    async def publish_staged(
        self,
        publication_ids: Iterable[str],
        *,
        not_before: datetime | None = None,
    ) -> datetime:
        """Publish pending receipts only after the business transaction committed.

        The caller must commit the transaction that created the entities before
        calling this method.  The timestamp is sampled only after that commit,
        then persisted in a new transaction.  Consequently every visible
        receipt is conservative: its entity was committed before its visibility
        timestamp, even if the database's timestamp precision is coarse.
        """
        ids = tuple(dict.fromkeys(publication_ids))
        if not ids:
            raise MarketDataPublicationError("PUBLICATION_IDS_EMPTY")
        if self._db.in_transaction():
            raise MarketDataPublicationError("PUBLICATION_REQUIRES_COMMITTED_TRANSACTION")
        lower_bound = (
            _as_utc(not_before, field_name="publication not_before")
            if not_before is not None
            else None
        )
        await self._db.begin()
        try:
            rows = list(
                (
                    await self._db.execute(
                        select(MdPublication).where(MdPublication.id.in_(ids)).with_for_update()
                    )
                )
                .scalars()
                .all()
            )
            if len(rows) != len(ids):
                raise MarketDataPublicationError("PUBLICATION_NOT_FOUND")
            by_id = {row.id: row for row in rows}
            if set(by_id) != set(ids):
                raise MarketDataPublicationError("PUBLICATION_NOT_FOUND")
            published_at = await self._publish_locked_rows(rows, lower_bound=lower_bound)
            await self._db.commit()
            return published_at
        except Exception:
            if self._db.in_transaction():
                await self._db.rollback()
            raise

    async def publication_for_entity(
        self,
        *,
        entity_type: str,
        entity_id: str,
    ) -> MdPublication | None:
        """Return a receipt for recovery tooling without changing its state."""
        return await self._db.scalar(
            select(MdPublication).where(
                MdPublication.entity_type == entity_type,
                MdPublication.entity_id == entity_id,
            )
        )

    async def recover_pending(
        self,
        *,
        limit: int = 100,
        dry_run: bool = False,
    ) -> tuple[str, ...]:
        """Validate and optionally publish a bounded set of stranded receipts.

        This is the operator recovery path for a process failure after the
        immutable entity transaction (A) committed but before the visibility
        receipt transaction (B) completed.  It never guesses an entity: every
        pending receipt is joined to its declared immutable entity and digest
        before it can become visible.  ``dry_run`` validates the same bounded
        candidates and rolls its transaction back without changing visibility.
        """
        if not isinstance(limit, int) or not 1 <= limit <= 10_000:
            raise ValueError("limit must be between 1 and 10000")
        if not isinstance(dry_run, bool):
            raise TypeError("dry_run must be a bool")
        if self._db.in_transaction():
            raise MarketDataPublicationError("PUBLICATION_REQUIRES_COMMITTED_TRANSACTION")

        await self._db.begin()
        try:
            rows = list(
                (
                    await self._db.execute(
                        select(MdPublication)
                        .where(MdPublication.published_at.is_(None))
                        .order_by(MdPublication.created_at, MdPublication.id)
                        .limit(limit)
                        .with_for_update()
                    )
                )
                .scalars()
                .all()
            )
            await self._assert_pending_entity_integrity(rows)
            ids = tuple(row.id for row in rows)
            if dry_run:
                await self._db.rollback()
                return ids
            if rows:
                await self._publish_locked_rows(rows, lower_bound=None)
            await self._db.commit()
            return ids
        except Exception:
            if self._db.in_transaction():
                await self._db.rollback()
            raise

    async def _publish_locked_rows(
        self,
        rows: Iterable[MdPublication],
        *,
        lower_bound: datetime | None,
    ) -> datetime:
        """Transition only pending locked rows, preserving already-published ones.

        A batch may deliberately contain an idempotently reused entity and a
        newly staged entity.  The reused receipt is immutable evidence of a
        previous publication and must not prevent the newly pending receipt
        from becoming visible.  Treating that mixed batch as corrupt made
        incremental master-data imports unrecoverably hide their new revision.
        """
        materialized = tuple(rows)
        if not materialized:
            raise MarketDataPublicationError("PUBLICATION_IDS_EMPTY")
        existing_times = []
        pending_rows: list[MdPublication] = []
        for row in materialized:
            if row.published_at is None:
                if row.visibility_sequence is not None:
                    raise MarketDataPublicationError("PUBLICATION_VISIBILITY_INTEGRITY")
                pending_rows.append(row)
                continue
            if not _is_visibility_sequence(row.visibility_sequence):
                raise MarketDataPublicationError("PUBLICATION_VISIBILITY_INTEGRITY")
            existing_times.append(_stored_utc(row.published_at))
        pending_ids = tuple(row.id for row in pending_rows)
        if not pending_ids:
            return max(existing_times)

        published_at = _as_utc(self._clock(), field_name="publication clock")
        if lower_bound is not None and published_at <= lower_bound:
            # Equal timestamps are ambiguous in a strict ``<=`` replay.
            # Move one representable instant forward to remain conservative.
            published_at = lower_bound + timedelta(microseconds=1)
        allocator = await self._locked_visibility_allocator()
        prior_visible_at = (
            _stored_utc(allocator.last_visible_at)
            if allocator.last_visible_at is not None
            else None
        )
        # The sequence is the authoritative tie-breaker, so equal visible_at
        # values are allowed.  A local clock regression may never move the
        # logical boundary backwards relative to an earlier seal.
        if prior_visible_at is not None and published_at < prior_visible_at:
            published_at = prior_visible_at
        first_sequence = allocator.next_visibility_sequence
        if not _is_visibility_sequence(first_sequence):
            raise MarketDataPublicationError("PUBLICATION_VISIBILITY_ALLOCATOR_INTEGRITY")
        ordered_pending = tuple(sorted(pending_rows, key=lambda row: row.id))
        allocator.next_visibility_sequence = first_sequence + len(ordered_pending)
        allocator.last_visible_at = published_at
        await self._db.flush()

        # Use guarded SQL transitions rather than mutating immutable evidence
        # objects.  A concurrent second publisher cannot rewrite an existing
        # receipt, and the allocator lock makes every assigned value global.
        for offset, row in enumerate(ordered_pending):
            result = await self._db.execute(
                update(MdPublication)
                .where(
                    MdPublication.id == row.id,
                    MdPublication.published_at.is_(None),
                    MdPublication.visibility_sequence.is_(None),
                )
                .values(
                    published_at=published_at,
                    visibility_sequence=first_sequence + offset,
                )
            )
            if result.rowcount != 1:
                raise MarketDataPublicationError("PUBLICATION_WRITE_CONFLICT")
        return max((*existing_times, published_at))

    async def _locked_visibility_allocator(self) -> MdVisibilitySequenceAllocator:
        """Return the durable singleton that serializes global receipt order."""
        try:
            allocator = await self._db.scalar(
                select(MdVisibilitySequenceAllocator)
                .where(MdVisibilitySequenceAllocator.singleton_id == 1)
                .with_for_update()
            )
            if allocator is None:
                max_sequence = await self._db.scalar(
                    select(func.max(MdPublication.visibility_sequence)).where(
                        MdPublication.visibility_sequence.is_not(None)
                    )
                )
                latest_visible_at = await self._db.scalar(
                    select(func.max(MdPublication.published_at)).where(
                        MdPublication.published_at.is_not(None)
                    )
                )
                candidate = MdVisibilitySequenceAllocator(
                    singleton_id=1,
                    next_visibility_sequence=(int(max_sequence) + 1 if max_sequence is not None else 1),
                    last_visible_at=latest_visible_at,
                )
                try:
                    async with self._db.begin_nested():
                        self._db.add(candidate)
                        await self._db.flush()
                except IntegrityError:
                    # Another worker created the sentinel. Re-read it under
                    # the same row-lock protocol before allocating anything.
                    pass
                allocator = await self._db.scalar(
                    select(MdVisibilitySequenceAllocator)
                    .where(MdVisibilitySequenceAllocator.singleton_id == 1)
                    .with_for_update()
                )
        except IntegrityError as exc:
            raise MarketDataPublicationError("PUBLICATION_VISIBILITY_ALLOCATOR_CONFLICT") from exc
        if allocator is None or not _is_visibility_sequence(allocator.next_visibility_sequence):
            raise MarketDataPublicationError("PUBLICATION_VISIBILITY_ALLOCATOR_INTEGRITY")

        max_sequence = await self._db.scalar(
            select(func.max(MdPublication.visibility_sequence)).where(
                MdPublication.visibility_sequence.is_not(None)
            )
        )
        if max_sequence is not None and allocator.next_visibility_sequence <= int(max_sequence):
            raise MarketDataPublicationError("PUBLICATION_VISIBILITY_ALLOCATOR_INTEGRITY")
        return allocator

    async def _assert_pending_entity_integrity(
        self,
        rows: Iterable[MdPublication],
    ) -> None:
        """Prove every recovery receipt still names the immutable entity it seals."""
        by_type: dict[str, list[MdPublication]] = {}
        for row in rows:
            if row.entity_type not in _ENTITY_TYPES:
                raise MarketDataPublicationError("PUBLICATION_ENTITY_TYPE_INVALID")
            by_type.setdefault(row.entity_type, []).append(row)

        entity_specs = {
            PUBLICATION_SOURCE_SNAPSHOT: (MdSourceSnapshot, MdSourceSnapshot.payload_sha256),
            PUBLICATION_CALENDAR_SNAPSHOT: (MdCalendarSnapshot, MdCalendarSnapshot.snapshot_sha256),
            PUBLICATION_INSTRUMENT_IDENTITY: (
                MdInstrumentIdentityRevision,
                MdInstrumentIdentityRevision.revision_sha256,
            ),
        }
        for entity_type, receipts in by_type.items():
            model, digest_column = entity_specs[entity_type]
            entity_ids = tuple(receipt.entity_id for receipt in receipts)
            found = dict(
                (
                    await self._db.execute(
                        select(model.id, digest_column)
                        .where(model.id.in_(entity_ids))
                        .with_for_update()
                    )
                ).all()
            )
            if len(found) != len(entity_ids) or any(
                found.get(receipt.entity_id) != receipt.entity_sha256 for receipt in receipts
            ):
                raise MarketDataPublicationError("PUBLICATION_ENTITY_INTEGRITY")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_visibility_sequence(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _stored_utc(value: datetime) -> datetime:
    """Normalize a UTC timestamp read back from a portable database column."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
