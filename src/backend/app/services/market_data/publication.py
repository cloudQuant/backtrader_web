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

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data_platform import (
    MdB2CompletenessManifestEntry,
    MdB2CompletenessReceipt,
    MdCalendarSnapshot,
    MdInstrumentIdentityRevision,
    MdPublication,
    MdPublicationReleaseHold,
    MdSourceSnapshot,
    MdVisibilitySequenceAllocator,
)
from app.services.market_data.fetch_lease import (
    MarketDataFetchLeaseHandle,
    assert_fetch_lease_held_in_transaction,
)
from app.services.market_data.multi_record_evidence import (
    B2CompletenessEvidenceError,
    assert_b2_completeness_receipt_integrity,
)

UTC = timezone.utc

PUBLICATION_SOURCE_SNAPSHOT = "source_snapshot"
PUBLICATION_CALENDAR_SNAPSHOT = "calendar_snapshot"
PUBLICATION_INSTRUMENT_IDENTITY = "instrument_identity_revision"
PUBLICATION_B2_COMPLETENESS_RECEIPT = "b2_completeness_receipt"
PUBLICATION_RELEASE_HOLD_WORKFLOW_LEGACY_STOCK_DAILY_IMPORT = "legacy_stock_daily_import"
PUBLICATION_RELEASE_HOLD_STATE_DEFERRED = "DEFERRED"
PUBLICATION_RELEASE_HOLD_STATE_QUARANTINED = "QUARANTINED"
PUBLICATION_RELEASE_HOLD_STATE_PROMOTED = "PROMOTED"
_ENTITY_TYPES = frozenset(
    {
        PUBLICATION_SOURCE_SNAPSHOT,
        PUBLICATION_CALENDAR_SNAPSHOT,
        PUBLICATION_INSTRUMENT_IDENTITY,
        PUBLICATION_B2_COMPLETENESS_RECEIPT,
    }
)
_RELEASE_HOLD_WORKFLOWS = frozenset({PUBLICATION_RELEASE_HOLD_WORKFLOW_LEGACY_STOCK_DAILY_IMPORT})
_ACTIVE_RELEASE_HOLD_STATES = frozenset(
    {PUBLICATION_RELEASE_HOLD_STATE_DEFERRED, PUBLICATION_RELEASE_HOLD_STATE_QUARANTINED}
)


class MarketDataPublicationError(ValueError):
    """Stable failure code for an unsafe publication transition."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class MarketDataDeferredPublicationIntent:
    """Immutable binding for evidence that cannot become visible automatically.

    The concrete legacy adapter owns construction of ``intent_sha256`` from its
    sealed batch, scope, target, authorization and lease evidence.  This
    generic publication layer only preserves and compares the digest; it never
    treats an arbitrary digest as authorization.
    """

    workflow_kind: str
    intent_sha256: str

    def __post_init__(self) -> None:
        if self.workflow_kind not in _RELEASE_HOLD_WORKFLOWS:
            raise ValueError("deferred publication workflow is not supported")
        if not _is_sha256(self.intent_sha256):
            raise ValueError("deferred publication intent must be a sha256")


@dataclass(frozen=True, slots=True)
class MarketDataDeferredPublicationPromotion:
    """The explicit, post-verification request that can seal one held receipt."""

    publication_id: str
    source_snapshot_id: str
    workflow_kind: str
    intent_sha256: str
    promotion_evidence_sha256: str

    def __post_init__(self) -> None:
        for field_name in ("publication_id", "source_snapshot_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"deferred publication {field_name} is invalid")
        if self.workflow_kind not in _RELEASE_HOLD_WORKFLOWS:
            raise ValueError("deferred publication workflow is not supported")
        if not _is_sha256(self.intent_sha256):
            raise ValueError("deferred publication intent must be a sha256")
        if not _is_sha256(self.promotion_evidence_sha256):
            raise ValueError("deferred publication evidence must be a sha256")


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
        fetch_lease_clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._db = db
        self._clock = clock or _utc_now
        # Publication timestamps may intentionally use a deterministic test
        # clock. Lease ownership must not inherit that clock in production:
        # cross-worker fencing always needs the database UTC source unless a
        # test explicitly supplies this separate seam.
        self._fetch_lease_clock = fetch_lease_clock

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

    async def hold_staged_source_snapshot(
        self,
        *,
        publication: MdPublication,
        source_snapshot_id: str,
        intent: MarketDataDeferredPublicationIntent,
    ) -> MdPublicationReleaseHold:
        """Attach a durable release hold inside the still-uncommitted fact transaction.

        A hold is deliberately a separate child record instead of another
        ``MdPublication`` state.  This keeps normal pending-receipt recovery
        semantics intact while making every generic publisher prove it is not
        releasing a candidate that still needs legacy-import verification.
        """
        if not isinstance(publication, MdPublication):
            raise TypeError("publication must be an MdPublication")
        if not isinstance(source_snapshot_id, str) or not source_snapshot_id.strip():
            raise MarketDataPublicationError("PUBLICATION_DEFERRED_SOURCE_INVALID")
        if not isinstance(intent, MarketDataDeferredPublicationIntent):
            raise TypeError("intent must be a MarketDataDeferredPublicationIntent")

        # The caller normally supplies the receipt it just staged in this
        # fact transaction. It may also hold an old ORM instance, so never
        # trust its in-memory pending fields. A late hold on a receipt another
        # session already published would violate the active-hold invariant.
        locked_publication = await self._db.scalar(
            select(MdPublication)
            .where(MdPublication.id == publication.id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if locked_publication is None:
            raise MarketDataPublicationError("PUBLICATION_DEFERRED_RECEIPT_INVALID")
        if (
            locked_publication.entity_type != PUBLICATION_SOURCE_SNAPSHOT
            or locked_publication.entity_id != source_snapshot_id
            or locked_publication.published_at is not None
            or locked_publication.visibility_sequence is not None
        ):
            raise MarketDataPublicationError("PUBLICATION_DEFERRED_RECEIPT_INVALID")

        locked_source_snapshot_id = await self._db.scalar(
            select(MdSourceSnapshot.id)
            .where(MdSourceSnapshot.id == source_snapshot_id)
            .with_for_update()
        )
        if locked_source_snapshot_id is None:
            raise MarketDataPublicationError("PUBLICATION_DEFERRED_SOURCE_INVALID")

        existing = await self._db.scalar(
            select(MdPublicationReleaseHold).where(
                MdPublicationReleaseHold.publication_id == locked_publication.id
            )
        )
        if existing is not None:
            if (
                existing.source_snapshot_id != source_snapshot_id
                or existing.workflow_kind != intent.workflow_kind
                or existing.intent_sha256 != intent.intent_sha256
            ):
                raise MarketDataPublicationError("PUBLICATION_DEFERRED_HOLD_CONFLICT")
            return existing

        hold = MdPublicationReleaseHold(
            publication_id=locked_publication.id,
            source_snapshot_id=source_snapshot_id,
            workflow_kind=intent.workflow_kind,
            state=PUBLICATION_RELEASE_HOLD_STATE_DEFERRED,
            intent_sha256=intent.intent_sha256,
        )
        self._db.add(hold)
        try:
            await self._db.flush()
        except IntegrityError as exc:
            raise MarketDataPublicationError("PUBLICATION_DEFERRED_HOLD_WRITE_CONFLICT") from exc
        return hold

    async def publish_staged(
        self,
        publication_ids: Iterable[str],
        *,
        not_before: datetime | None = None,
        pre_publish_guard: Callable[[], Awaitable[None]] | None = None,
        fetch_lease: MarketDataFetchLeaseHandle | None = None,
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
        if pre_publish_guard is not None and not callable(pre_publish_guard):
            raise TypeError("pre_publish_guard must be callable")
        if fetch_lease is not None and not _is_fetch_lease_handle(fetch_lease):
            raise TypeError("fetch_lease must be a MarketDataFetchLeaseHandle")
        await self._db.begin()
        try:
            # Run optional caller checks first. The durable owner/fence update
            # must be the final guard before receipt locks and allocation: a
            # callback is free to reject work, but cannot invalidate a fence
            # after it has already been checked and still publish the row.
            if pre_publish_guard is not None:
                await pre_publish_guard()
            if fetch_lease is not None:
                await assert_fetch_lease_held_in_transaction(
                    self._db,
                    fetch_lease,
                    clock=self._fetch_lease_clock,
                )
            rows = list(
                (
                    await self._db.execute(
                        select(MdPublication)
                        .where(MdPublication.id.in_(ids))
                        .execution_options(populate_existing=True)
                        .with_for_update()
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
            await self._assert_no_active_release_holds(rows)
            await self._assert_publish_fence_binding(
                rows,
                fetch_lease=fetch_lease,
                pre_publish_guard=pre_publish_guard,
            )
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
        Fetch-fenced source receipts are deliberately excluded: generic
        recovery has no owner token to renew in the publication transaction,
        while calendar, master-data and non-fenced source receipts retain the
        original recovery behavior.
        """
        if not isinstance(limit, int) or not 1 <= limit <= 10_000:
            raise ValueError("limit must be between 1 and 10000")
        if not isinstance(dry_run, bool):
            raise TypeError("dry_run must be a bool")
        if self._db.in_transaction():
            raise MarketDataPublicationError("PUBLICATION_REQUIRES_COMMITTED_TRANSACTION")

        fenced_source_receipt = (
            select(MdSourceSnapshot.id)
            .where(
                MdSourceSnapshot.id == MdPublication.entity_id,
                or_(
                    MdSourceSnapshot.fetch_lease_key_sha256.is_not(None),
                    MdSourceSnapshot.fetch_lease_fence_token.is_not(None),
                ),
            )
            .correlate(MdPublication)
            .exists()
        )
        release_hold_exists = (
            select(MdPublicationReleaseHold.publication_id)
            .where(MdPublicationReleaseHold.publication_id == MdPublication.id)
            .correlate(MdPublication)
            .exists()
        )
        await self._db.begin()
        try:
            rows = list(
                (
                    await self._db.execute(
                        select(MdPublication)
                        .where(
                            MdPublication.published_at.is_(None),
                            ~release_hold_exists,
                            or_(
                                MdPublication.entity_type != PUBLICATION_SOURCE_SNAPSHOT,
                                ~fenced_source_receipt,
                            ),
                        )
                        .order_by(MdPublication.created_at, MdPublication.id)
                        .limit(limit)
                        .execution_options(populate_existing=True)
                        .with_for_update()
                    )
                )
                .scalars()
                .all()
            )
            # The anti-join above avoids taking candidate rows that already
            # have a hold. Recheck it first under the receipt lock before
            # fetching source evidence, returning a dry-run result, or
            # allocating visibility: another transaction may have committed a
            # hold after the selection snapshot was taken. This retains the
            # common publication lock order (receipt, hold, source).
            await self._assert_no_active_release_holds(rows)
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

    async def promote_deferred_after_attestation(
        self,
        promotions: Iterable[MarketDataDeferredPublicationPromotion],
        *,
        not_before: datetime,
        pre_publish_guard: Callable[[], Awaitable[None]],
        fetch_lease: MarketDataFetchLeaseHandle | None = None,
    ) -> datetime:
        """Seal held source receipts only after an adapter proves its candidate.

        A generic publisher cannot call this method without supplying an async
        guard.  The concrete adapter will use that guard to reauthorize the
        exact route and recheck its source-batch/permit evidence while this
        transaction still owns the receipt, hold, source snapshot and lease
        fence.  The hold is marked ``PROMOTED`` in the same transaction as the
        visibility receipt, so a crash cannot create a visible-but-unpromoted
        candidate or a promotable generic pending receipt.
        """
        items = tuple(promotions)
        if not items:
            raise MarketDataPublicationError("PUBLICATION_DEFERRED_PROMOTIONS_EMPTY")
        if not all(isinstance(item, MarketDataDeferredPublicationPromotion) for item in items):
            raise TypeError("promotions must contain MarketDataDeferredPublicationPromotion values")
        ids = tuple(item.publication_id for item in items)
        if len(set(ids)) != len(ids):
            raise MarketDataPublicationError("PUBLICATION_DEFERRED_PROMOTION_DUPLICATE")
        if self._db.in_transaction():
            raise MarketDataPublicationError("PUBLICATION_REQUIRES_COMMITTED_TRANSACTION")
        if not callable(pre_publish_guard):
            raise TypeError("pre_publish_guard must be callable")
        if fetch_lease is not None and not _is_fetch_lease_handle(fetch_lease):
            raise TypeError("fetch_lease must be a MarketDataFetchLeaseHandle")
        lower_bound = _as_utc(not_before, field_name="deferred publication not_before")

        publication_transaction = await self._db.begin()
        try:
            rows = list(
                (
                    await self._db.execute(
                        select(MdPublication)
                        .where(MdPublication.id.in_(ids))
                        .execution_options(populate_existing=True)
                        .with_for_update()
                    )
                )
                .scalars()
                .all()
            )
            if len(rows) != len(ids):
                raise MarketDataPublicationError("PUBLICATION_NOT_FOUND")
            holds = list(
                (
                    await self._db.execute(
                        select(MdPublicationReleaseHold)
                        .where(MdPublicationReleaseHold.publication_id.in_(ids))
                        .execution_options(populate_existing=True)
                        .with_for_update()
                    )
                )
                .scalars()
                .all()
            )
            self._assert_deferred_promotion_integrity(rows=rows, holds=holds, promotions=items)
            await self._assert_pending_entity_integrity(rows)
            await self._assert_publish_fence_binding(
                rows,
                fetch_lease=fetch_lease,
                pre_publish_guard=pre_publish_guard,
            )
            # The concrete adapter's private authorization and provenance
            # proof runs only after this transaction owns the receipt, hold,
            # and source evidence. Revalidate afterwards because the callback
            # is application code and must not be allowed to invalidate the
            # state that this publication transaction is about to seal.
            await pre_publish_guard()
            current_transaction = self._db.get_transaction()
            if (
                current_transaction is None
                or current_transaction.sync_transaction
                is not publication_transaction.sync_transaction
                or not publication_transaction.is_active
            ):
                raise MarketDataPublicationError("PUBLICATION_DEFERRED_GUARD_TRANSACTION_LOST")
            # A trusted guard may inspect evidence through raw SQL. Never
            # revalidate ORM identities captured before that callback: a raw
            # UPDATE does not necessarily synchronize the session identity
            # map, and could otherwise be overwritten by this promotion.
            rows = list(
                (
                    await self._db.execute(
                        select(MdPublication)
                        .where(MdPublication.id.in_(ids))
                        .execution_options(populate_existing=True)
                        .with_for_update()
                    )
                )
                .scalars()
                .all()
            )
            if len(rows) != len(ids):
                raise MarketDataPublicationError("PUBLICATION_NOT_FOUND")
            holds = list(
                (
                    await self._db.execute(
                        select(MdPublicationReleaseHold)
                        .where(MdPublicationReleaseHold.publication_id.in_(ids))
                        .execution_options(populate_existing=True)
                        .with_for_update()
                    )
                )
                .scalars()
                .all()
            )
            self._assert_deferred_promotion_integrity(rows=rows, holds=holds, promotions=items)
            await self._assert_pending_entity_integrity(rows)
            await self._assert_publish_fence_binding(
                rows,
                fetch_lease=fetch_lease,
                pre_publish_guard=pre_publish_guard,
            )
            if fetch_lease is not None:
                await assert_fetch_lease_held_in_transaction(
                    self._db,
                    fetch_lease,
                    clock=self._fetch_lease_clock,
                )
            published_at = await self._publish_locked_rows(rows, lower_bound=lower_bound)
            promotions_by_id = {item.publication_id: item for item in items}
            for hold in holds:
                promotion = promotions_by_id[hold.publication_id]
                hold.state = PUBLICATION_RELEASE_HOLD_STATE_PROMOTED
                hold.promotion_evidence_sha256 = promotion.promotion_evidence_sha256
                hold.promoted_at = published_at
            await self._db.flush()
            await self._db.commit()
            return published_at
        except Exception:
            if self._db.in_transaction():
                await self._db.rollback()
            raise

    async def quarantine_deferred(
        self,
        *,
        publication_id: str,
        source_snapshot_id: str,
        intent: MarketDataDeferredPublicationIntent,
        quarantine_code: str,
    ) -> None:
        """Make a rejected held candidate permanently non-promotable and hidden."""
        if not isinstance(publication_id, str) or not publication_id.strip():
            raise MarketDataPublicationError("PUBLICATION_DEFERRED_RECEIPT_INVALID")
        if not isinstance(source_snapshot_id, str) or not source_snapshot_id.strip():
            raise MarketDataPublicationError("PUBLICATION_DEFERRED_SOURCE_INVALID")
        if not isinstance(intent, MarketDataDeferredPublicationIntent):
            raise TypeError("intent must be a MarketDataDeferredPublicationIntent")
        if (
            not isinstance(quarantine_code, str)
            or not quarantine_code.strip()
            or len(quarantine_code) > 128
        ):
            raise MarketDataPublicationError("PUBLICATION_DEFERRED_QUARANTINE_CODE_INVALID")
        if self._db.in_transaction():
            raise MarketDataPublicationError("PUBLICATION_REQUIRES_COMMITTED_TRANSACTION")

        await self._db.begin()
        try:
            publication = await self._db.scalar(
                select(MdPublication)
                .where(MdPublication.id == publication_id)
                .execution_options(populate_existing=True)
                .with_for_update()
            )
            hold = await self._db.scalar(
                select(MdPublicationReleaseHold)
                .where(MdPublicationReleaseHold.publication_id == publication_id)
                .execution_options(populate_existing=True)
                .with_for_update()
            )
            if publication is None or hold is None:
                raise MarketDataPublicationError("PUBLICATION_DEFERRED_NOT_FOUND")
            self._assert_deferred_hold_matches(
                publication=publication,
                hold=hold,
                publication_id=publication_id,
                source_snapshot_id=source_snapshot_id,
                intent=intent,
            )
            if hold.state == PUBLICATION_RELEASE_HOLD_STATE_QUARANTINED:
                if hold.quarantine_code != quarantine_code:
                    raise MarketDataPublicationError("PUBLICATION_DEFERRED_QUARANTINE_CONFLICT")
                await self._db.commit()
                return
            if hold.state != PUBLICATION_RELEASE_HOLD_STATE_DEFERRED:
                raise MarketDataPublicationError("PUBLICATION_DEFERRED_STATE_INVALID")
            if publication.published_at is not None or publication.visibility_sequence is not None:
                raise MarketDataPublicationError("PUBLICATION_DEFERRED_RECEIPT_INVALID")
            hold.state = PUBLICATION_RELEASE_HOLD_STATE_QUARANTINED
            hold.quarantine_code = quarantine_code
            hold.quarantined_at = _as_utc(self._clock(), field_name="deferred quarantine clock")
            await self._db.flush()
            await self._db.commit()
        except Exception:
            if self._db.in_transaction():
                await self._db.rollback()
            raise

    async def _assert_no_active_release_holds(self, rows: Iterable[MdPublication]) -> None:
        """Reject generic publication when any receipt still has an active hold."""
        materialized = tuple(rows)
        if not materialized:
            return
        ids = tuple(row.id for row in materialized)
        publications_by_id = {row.id: row for row in materialized}
        holds = list(
            (
                await self._db.execute(
                    select(MdPublicationReleaseHold)
                    .where(MdPublicationReleaseHold.publication_id.in_(ids))
                    .execution_options(populate_existing=True)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        for hold in holds:
            publication = publications_by_id.get(hold.publication_id)
            if publication is None:
                raise MarketDataPublicationError("PUBLICATION_DEFERRED_HOLD_INTEGRITY")
            if hold.state in _ACTIVE_RELEASE_HOLD_STATES:
                raise MarketDataPublicationError("PUBLICATION_DEFERRED_RELEASE_REQUIRED")
            if hold.state != PUBLICATION_RELEASE_HOLD_STATE_PROMOTED:
                raise MarketDataPublicationError("PUBLICATION_DEFERRED_HOLD_INTEGRITY")
            if (
                publication.published_at is None
                or not _is_visibility_sequence(publication.visibility_sequence)
                or hold.promoted_at is None
                or not _is_sha256(hold.promotion_evidence_sha256)
            ):
                raise MarketDataPublicationError("PUBLICATION_DEFERRED_HOLD_INTEGRITY")

    def _assert_deferred_promotion_integrity(
        self,
        *,
        rows: Iterable[MdPublication],
        holds: Iterable[MdPublicationReleaseHold],
        promotions: Iterable[MarketDataDeferredPublicationPromotion],
    ) -> None:
        """Bind every explicit promotion to exactly one still-held source receipt."""
        rows_by_id = {row.id: row for row in rows}
        holds_by_publication_id = {hold.publication_id: hold for hold in holds}
        promotions_by_id = {item.publication_id: item for item in promotions}
        if (
            len(rows_by_id) != len(promotions_by_id)
            or len(holds_by_publication_id) != len(promotions_by_id)
            or set(rows_by_id) != set(promotions_by_id)
            or set(holds_by_publication_id) != set(promotions_by_id)
        ):
            raise MarketDataPublicationError("PUBLICATION_DEFERRED_NOT_FOUND")
        for publication_id, promotion in promotions_by_id.items():
            publication = rows_by_id[publication_id]
            hold = holds_by_publication_id[publication_id]
            intent = MarketDataDeferredPublicationIntent(
                workflow_kind=promotion.workflow_kind,
                intent_sha256=promotion.intent_sha256,
            )
            self._assert_deferred_hold_matches(
                publication=publication,
                hold=hold,
                publication_id=promotion.publication_id,
                source_snapshot_id=promotion.source_snapshot_id,
                intent=intent,
            )
            if hold.state == PUBLICATION_RELEASE_HOLD_STATE_QUARANTINED:
                raise MarketDataPublicationError("PUBLICATION_DEFERRED_QUARANTINED")
            if hold.state != PUBLICATION_RELEASE_HOLD_STATE_DEFERRED:
                raise MarketDataPublicationError("PUBLICATION_DEFERRED_STATE_INVALID")
            if (
                publication.published_at is not None
                or publication.visibility_sequence is not None
                or hold.quarantine_code is not None
                or hold.quarantined_at is not None
                or hold.promotion_evidence_sha256 is not None
                or hold.promoted_at is not None
            ):
                raise MarketDataPublicationError("PUBLICATION_DEFERRED_HOLD_INTEGRITY")

    @staticmethod
    def _assert_deferred_hold_matches(
        *,
        publication: MdPublication,
        hold: MdPublicationReleaseHold,
        publication_id: str,
        source_snapshot_id: str,
        intent: MarketDataDeferredPublicationIntent,
    ) -> None:
        """Check the immutable receipt, source, workflow and intent bindings."""
        if (
            publication.id != publication_id
            or publication.entity_type != PUBLICATION_SOURCE_SNAPSHOT
            or publication.entity_id != source_snapshot_id
            or hold.publication_id != publication_id
            or hold.source_snapshot_id != source_snapshot_id
            or hold.workflow_kind != intent.workflow_kind
            or hold.intent_sha256 != intent.intent_sha256
        ):
            raise MarketDataPublicationError("PUBLICATION_DEFERRED_HOLD_CONFLICT")

    async def _assert_publish_fence_binding(
        self,
        rows: Iterable[MdPublication],
        *,
        fetch_lease: MarketDataFetchLeaseHandle | None,
        pre_publish_guard: Callable[[], Awaitable[None]] | None,
    ) -> None:
        """Require an exact owner guard before sealing fenced source evidence.

        Calendar and master-data publication rows have no fetch lease and keep
        the original default behavior. A source receipt that was staged by a
        local-first fetch is different: its immutable binding says precisely
        which lease generation was allowed to materialize it, so a later owner
        must not seal it by passing a different or absent guard.
        """
        source_rows = tuple(row for row in rows if row.entity_type == PUBLICATION_SOURCE_SNAPSHOT)
        if not source_rows:
            if fetch_lease is not None:
                raise MarketDataPublicationError("PUBLICATION_FETCH_LEASE_MISMATCH")
            return
        generations = await self._source_receipt_fetch_lease_generations(source_rows)
        if not generations:
            if fetch_lease is not None:
                raise MarketDataPublicationError("PUBLICATION_FETCH_LEASE_MISMATCH")
            return
        if fetch_lease is None:
            raise MarketDataPublicationError("PUBLICATION_FETCH_LEASE_REQUIRED")
        if len(generations) != len(source_rows) or any(
            lease_key_sha256 != fetch_lease.lease_key_sha256
            or fence_token != fetch_lease.fence_token
            for _, lease_key_sha256, fence_token in generations
        ):
            raise MarketDataPublicationError("PUBLICATION_FETCH_LEASE_MISMATCH")

    async def _source_receipt_fetch_lease_generations(
        self,
        rows: Iterable[MdPublication],
    ) -> tuple[tuple[str, str, int], ...]:
        """Return valid immutable lease bindings for source-publication rows."""
        source_rows = tuple(rows)
        if not source_rows:
            return ()
        source_ids = tuple(row.entity_id for row in source_rows)
        snapshots = {
            snapshot_id: (lease_key_sha256, fence_token)
            for snapshot_id, lease_key_sha256, fence_token in (
                await self._db.execute(
                    select(
                        MdSourceSnapshot.id,
                        MdSourceSnapshot.fetch_lease_key_sha256,
                        MdSourceSnapshot.fetch_lease_fence_token,
                    ).where(MdSourceSnapshot.id.in_(source_ids))
                )
            ).all()
        }
        if len(snapshots) != len(source_ids):
            raise MarketDataPublicationError("PUBLICATION_ENTITY_INTEGRITY")
        generations: list[tuple[str, str, int]] = []
        for row in source_rows:
            lease_key_sha256, fence_token = snapshots[row.entity_id]
            if lease_key_sha256 is None and fence_token is None:
                continue
            if not _is_sha256(lease_key_sha256) or not _is_positive_fence_token(fence_token):
                raise MarketDataPublicationError("PUBLICATION_FETCH_LEASE_BINDING_INTEGRITY")
            generations.append((row.id, lease_key_sha256, fence_token))
        return tuple(generations)

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
                    next_visibility_sequence=(
                        int(max_sequence) + 1 if max_sequence is not None else 1
                    ),
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
            PUBLICATION_B2_COMPLETENESS_RECEIPT: (
                MdB2CompletenessReceipt,
                MdB2CompletenessReceipt.receipt_sha256,
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
            if entity_type == PUBLICATION_B2_COMPLETENESS_RECEIPT:
                await self._assert_pending_b2_completeness_receipt_integrity(entity_ids)

    async def _assert_pending_b2_completeness_receipt_integrity(
        self,
        receipt_ids: tuple[str, ...],
    ) -> None:
        """Bind every B2 publication hash to its immutable child manifest rows."""
        evidence_rows = list(
            (
                await self._db.execute(
                    select(MdB2CompletenessReceipt)
                    .where(MdB2CompletenessReceipt.id.in_(receipt_ids))
                    .execution_options(populate_existing=True)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        if len(evidence_rows) != len(receipt_ids):
            raise MarketDataPublicationError("PUBLICATION_ENTITY_INTEGRITY")
        entry_rows = list(
            await self._db.execute(
                select(
                    MdB2CompletenessManifestEntry.receipt_id,
                    MdB2CompletenessManifestEntry.semantic_record_key_sha256,
                )
                .where(MdB2CompletenessManifestEntry.receipt_id.in_(receipt_ids))
                .order_by(
                    MdB2CompletenessManifestEntry.receipt_id,
                    MdB2CompletenessManifestEntry.semantic_record_key_sha256,
                )
                .with_for_update()
            )
        )
        entries_by_receipt: dict[str, list[str]] = {receipt_id: [] for receipt_id in receipt_ids}
        for receipt_id, semantic_record_key_sha256 in entry_rows:
            if receipt_id not in entries_by_receipt:
                raise MarketDataPublicationError("PUBLICATION_ENTITY_INTEGRITY")
            entries_by_receipt[receipt_id].append(semantic_record_key_sha256)
        try:
            for receipt in evidence_rows:
                assert_b2_completeness_receipt_integrity(
                    receipt,
                    entries_by_receipt[receipt.id],
                )
        except (B2CompletenessEvidenceError, TypeError, ValueError) as exc:
            raise MarketDataPublicationError("PUBLICATION_ENTITY_INTEGRITY") from exc


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_positive_fence_token(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _is_fetch_lease_handle(value: object) -> bool:
    """Avoid importing the lease manager into identity/publication import paths."""
    return (
        _is_sha256(getattr(value, "lease_key_sha256", None))
        and _is_positive_fence_token(getattr(value, "fence_token", None))
        and isinstance(getattr(value, "owner_token", None), str)
        and bool(getattr(value, "owner_token", "").strip())
    )


def _is_visibility_sequence(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _stored_utc(value: datetime) -> datetime:
    """Normalize a UTC timestamp read back from a portable database column."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
