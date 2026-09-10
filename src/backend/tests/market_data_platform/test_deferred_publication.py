"""Deferred publication contracts for the controlled legacy-import seam.

These tests intentionally use only the normalized local store.  They prove
that a candidate can be made durable without being visible to ordinary readers
or generic recovery, and that only the explicit attestation path can seal it.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import async_session_maker
from app.models.market_data_platform import (
    MdPublication,
    MdPublicationReleaseHold,
    MdSourceSnapshot,
)
from app.services.market_data.publication import (
    PUBLICATION_RELEASE_HOLD_STATE_DEFERRED,
    PUBLICATION_RELEASE_HOLD_STATE_PROMOTED,
    PUBLICATION_RELEASE_HOLD_STATE_QUARANTINED,
    MarketDataDeferredPublicationIntent,
    MarketDataPublicationError,
    MarketDataPublicationManager,
)
from app.services.market_data.store import (
    UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
    DeferredProviderFetch,
    MarketDataStore,
    MarketDataStoreError,
)
from tests.market_data_platform.test_store import (
    _at,
    _context,
    _observation,
    _result,
    _seed_dataset_and_provider,
    _sha,
)

UTC = timezone.utc


def _stored_utc(value: datetime) -> datetime:
    """Normalize SQLite's naive UTC round-trip for receipt assertions."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def _stage_candidate(
    db: AsyncSession,
    *,
    source_revision: str,
) -> tuple[MarketDataStore, DeferredProviderFetch]:
    """Write one valid source receipt into the explicit deferred state."""
    context = _context()
    store = MarketDataStore(db, clock=lambda: _at(14))
    staged = await store.stage_provider_result_for_deferred_release(
        context,
        _result(
            retrieved_at=_at(13),
            source_revision=source_revision,
            context=context,
            observations=(
                _observation(
                    event_at=_at(10),
                    available_at=_at(12),
                    fields={"close": "10.50"},
                ),
            ),
        ),
        received_at=_at(14),
        unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        deferred_intent=MarketDataDeferredPublicationIntent(
            workflow_kind="legacy_stock_daily_import",
            intent_sha256=_sha(f"intent:{source_revision}"),
        ),
    )
    assert isinstance(staged, DeferredProviderFetch)
    return store, staged


async def _hold_for_publication(
    db: AsyncSession,
    publication_id: str,
) -> MdPublicationReleaseHold | None:
    """Load the hold through its receipt binding rather than its unrelated UUID."""
    return await db.scalar(
        select(MdPublicationReleaseHold).where(
            MdPublicationReleaseHold.publication_id == publication_id
        )
    )


@pytest.mark.asyncio
async def test_deferred_candidate_is_durable_hidden_and_immune_to_generic_release() -> None:
    """An active hold excludes the candidate from reads, recovery, and generic sealing."""
    context = _context()

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store, staged = await _stage_candidate(db, source_revision="deferred-hidden-v1")

        receipt = await db.get(MdPublication, staged.publication_id)
        hold = await _hold_for_publication(db, staged.publication_id)
        assert receipt is not None
        assert hold is not None
        assert receipt.entity_id == staged.source_snapshot_id
        assert receipt.published_at is None
        assert receipt.visibility_sequence is None
        assert hold.source_snapshot_id == staged.source_snapshot_id
        assert hold.state == PUBLICATION_RELEASE_HOLD_STATE_DEFERRED
        assert hold.intent_sha256 == staged.intent.intent_sha256
        await db.rollback()

        recovered_ids = await MarketDataPublicationManager(
            db, clock=lambda: _at(15)
        ).recover_pending()
        assert recovered_ids == ()

        with pytest.raises(MarketDataPublicationError) as generic_release:
            await MarketDataPublicationManager(db, clock=lambda: _at(15)).publish_staged(
                (staged.publication_id,)
            )
        assert generic_release.value.code == "PUBLICATION_DEFERRED_RELEASE_REQUIRED"

        assert await store.read_observations(context, knowledge_cutoff=_at(20)) == ()


@pytest.mark.asyncio
async def test_stale_pending_receipt_cannot_receive_a_late_deferred_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Receipt locking prevents a stale ORM object from splitting hold and visibility state."""
    context = _context()

    async def interrupt_normal_publication(*_args: object, **_kwargs: object) -> datetime:
        raise MarketDataPublicationError("PUBLICATION_TEST_INTERRUPTED")

    async with async_session_maker() as stale_db, async_session_maker() as current_db:
        await _seed_dataset_and_provider(stale_db)
        stale_store = MarketDataStore(stale_db, clock=lambda: _at(14))
        monkeypatch.setattr(
            stale_store._publications,
            "publish_staged",
            interrupt_normal_publication,
        )
        with pytest.raises(MarketDataStoreError) as interrupted:
            await stale_store.persist_provider_result(
                context,
                _result(
                    retrieved_at=_at(14),
                    source_revision="late-hold-race-v1",
                    context=context,
                    observations=(
                        _observation(
                            event_at=_at(10),
                            available_at=_at(12),
                            fields={"close": "10.50"},
                        ),
                    ),
                ),
                received_at=_at(14),
                unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
            )

        stale_receipt = await stale_db.scalar(select(MdPublication))
        source_snapshot = await stale_db.scalar(select(MdSourceSnapshot))
        assert stale_receipt is not None
        assert source_snapshot is not None
        assert stale_receipt.published_at is None
        assert stale_receipt.visibility_sequence is None
        stale_receipt_id = stale_receipt.id
        source_snapshot_id = source_snapshot.id
        # Keep this receipt object loaded in the first session. A second
        # session seals it before the stale caller attempts to add the hold.
        await stale_db.commit()

        await MarketDataPublicationManager(current_db, clock=lambda: _at(15)).publish_staged(
            (stale_receipt_id,),
            not_before=_at(14),
        )

        with pytest.raises(MarketDataPublicationError) as late_hold_rejected:
            await MarketDataPublicationManager(
                stale_db, clock=lambda: _at(15)
            ).hold_staged_source_snapshot(
                publication=stale_receipt,
                source_snapshot_id=source_snapshot_id,
                intent=MarketDataDeferredPublicationIntent(
                    workflow_kind="legacy_stock_daily_import",
                    intent_sha256=_sha("intent:late-hold-race-v1"),
                ),
            )
        assert late_hold_rejected.value.code == "PUBLICATION_DEFERRED_RECEIPT_INVALID"
        await stale_db.rollback()

        sealed_receipt = await current_db.scalar(
            select(MdPublication)
            .where(MdPublication.id == stale_receipt_id)
            .execution_options(populate_existing=True)
        )
        late_hold = await _hold_for_publication(current_db, stale_receipt_id)

    assert interrupted.value.code == "OBSERVATION_PUBLICATION_FAILED"
    assert sealed_receipt is not None
    assert sealed_receipt.published_at is not None
    assert sealed_receipt.visibility_sequence is not None
    assert late_hold is None


@pytest.mark.asyncio
async def test_recovery_rechecks_for_a_hold_after_selecting_pending_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recovery cannot seal a candidate if a hold appears after its first selection."""
    context = _context()

    async def interrupt_normal_publication(*_args: object, **_kwargs: object) -> datetime:
        raise MarketDataPublicationError("PUBLICATION_TEST_INTERRUPTED")

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db, clock=lambda: _at(14))
        monkeypatch.setattr(
            store._publications,
            "publish_staged",
            interrupt_normal_publication,
        )
        with pytest.raises(MarketDataStoreError) as interrupted:
            await store.persist_provider_result(
                context,
                _result(
                    retrieved_at=_at(14),
                    source_revision="recovery-late-hold-v1",
                    context=context,
                    observations=(
                        _observation(
                            event_at=_at(10),
                            available_at=_at(12),
                            fields={"close": "10.50"},
                        ),
                    ),
                ),
                received_at=_at(14),
                unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
            )

        receipt = await db.scalar(select(MdPublication))
        assert receipt is not None
        assert receipt.published_at is None
        assert receipt.visibility_sequence is None
        receipt_id = receipt.id
        source_snapshot_id = receipt.entity_id
        await db.commit()

        recovery = MarketDataPublicationManager(db, clock=lambda: _at(15))
        original_hold_check = recovery._assert_no_active_release_holds

        async def add_hold_after_selection(rows: list[MdPublication]) -> None:
            assert len(rows) == 1
            await recovery.hold_staged_source_snapshot(
                publication=rows[0],
                source_snapshot_id=source_snapshot_id,
                intent=MarketDataDeferredPublicationIntent(
                    workflow_kind="legacy_stock_daily_import",
                    intent_sha256=_sha("intent:recovery-late-hold-v1"),
                ),
            )
            await original_hold_check(rows)

        monkeypatch.setattr(recovery, "_assert_no_active_release_holds", add_hold_after_selection)
        with pytest.raises(MarketDataPublicationError) as recovery_rejected:
            await recovery.recover_pending()
        assert recovery_rejected.value.code == "PUBLICATION_DEFERRED_RELEASE_REQUIRED"
        assert interrupted.value.code == "OBSERVATION_PUBLICATION_FAILED"

        receipt_after = await db.scalar(
            select(MdPublication)
            .where(MdPublication.id == receipt_id)
            .execution_options(populate_existing=True)
        )
        late_hold = await _hold_for_publication(db, receipt_id)

    assert receipt_after is not None
    assert receipt_after.published_at is None
    assert receipt_after.visibility_sequence is None
    # The injected hold shared recovery's transaction. Its rollback proves the
    # post-selection recheck happened before the receipt could be sealed.
    assert late_hold is None


@pytest.mark.asyncio
async def test_deferred_candidate_reaches_unfiltered_local_store_only_after_attestation() -> None:
    """Promotion seals the receipt and marks its hold before a raw local store read sees it."""
    context = _context()
    guard_calls: list[str] = []

    async def attestation_guard() -> None:
        guard_calls.append("checked")

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store, staged = await _stage_candidate(db, source_revision="deferred-promoted-v1")

        promoted = await store.promote_deferred_provider_result(
            staged,
            promotion_evidence_sha256=_sha("promotion:deferred-promoted-v1"),
            pre_publish_guard=attestation_guard,
        )

        rows = await store.read_observations(context, knowledge_cutoff=_at(20))
        receipt = await db.get(MdPublication, staged.publication_id)
        hold = await db.scalar(
            select(MdPublicationReleaseHold).where(
                MdPublicationReleaseHold.publication_id == staged.publication_id
            )
        )

    assert guard_calls == ["checked"]
    assert promoted.series_id == staged.series_id
    assert promoted.source_snapshot_id == staged.source_snapshot_id
    assert promoted.observation_revision_ids == staged.observation_revision_ids
    assert promoted.received_at > staged.local_received_at
    assert len(rows) == 1
    assert rows[0].event_key.event_at == _at(10)
    assert rows[0].fields["close"] == "10.50"
    assert receipt is not None
    assert receipt.published_at is not None
    assert _stored_utc(receipt.published_at) == promoted.received_at
    assert receipt.visibility_sequence is not None
    assert hold is not None
    assert hold.state == PUBLICATION_RELEASE_HOLD_STATE_PROMOTED
    assert hold.promotion_evidence_sha256 == _sha("promotion:deferred-promoted-v1")
    assert hold.promoted_at is not None
    assert _stored_utc(hold.promoted_at) == promoted.received_at


@pytest.mark.asyncio
async def test_failed_deferred_attestation_leaves_the_candidate_hidden() -> None:
    """A rejected pre-publish guard rolls back without creating a partial promotion."""
    context = _context()

    async def reject_attestation() -> None:
        raise RuntimeError("attestation rejected")

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store, staged = await _stage_candidate(db, source_revision="deferred-rejected-v1")

        with pytest.raises(RuntimeError, match="attestation rejected"):
            await store.promote_deferred_provider_result(
                staged,
                promotion_evidence_sha256=_sha("promotion:deferred-rejected-v1"),
                pre_publish_guard=reject_attestation,
            )

        receipt = await db.get(MdPublication, staged.publication_id)
        hold = await _hold_for_publication(db, staged.publication_id)
        assert receipt is not None
        assert hold is not None
        assert receipt.published_at is None
        assert receipt.visibility_sequence is None
        assert hold.state == PUBLICATION_RELEASE_HOLD_STATE_DEFERRED
        assert hold.promotion_evidence_sha256 is None
        assert hold.promoted_at is None
        await db.rollback()

        assert await store.read_observations(context, knowledge_cutoff=_at(20)) == ()


@pytest.mark.asyncio
async def test_deferred_promotion_rejects_a_guard_that_restarts_its_transaction() -> None:
    """A guard cannot commit locked rows and then open a new transaction before promotion."""
    context = _context()

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store, staged = await _stage_candidate(db, source_revision="deferred-guard-transaction-v1")

        async def transaction_restarting_guard() -> None:
            await db.commit()
            await db.execute(select(MdPublication).where(MdPublication.id == staged.publication_id))

        with pytest.raises(MarketDataStoreError) as rejected:
            await store.promote_deferred_provider_result(
                staged,
                promotion_evidence_sha256=_sha("promotion:deferred-guard-transaction-v1"),
                pre_publish_guard=transaction_restarting_guard,
            )
        assert rejected.value.code == "PUBLICATION_DEFERRED_GUARD_TRANSACTION_LOST"

        receipt = await db.get(MdPublication, staged.publication_id)
        hold = await _hold_for_publication(db, staged.publication_id)
        assert receipt is not None
        assert hold is not None
        assert receipt.published_at is None
        assert receipt.visibility_sequence is None
        assert hold.state == PUBLICATION_RELEASE_HOLD_STATE_DEFERRED
        await db.rollback()

        assert await store.read_observations(context, knowledge_cutoff=_at(20)) == ()


@pytest.mark.asyncio
async def test_deferred_promotion_reloads_hold_after_guard_raw_sql() -> None:
    """Raw-SQL guard changes cannot be hidden by the session identity map."""
    context = _context()

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store, staged = await _stage_candidate(db, source_revision="deferred-raw-sql-v1")

        async def raw_sql_quarantine_guard() -> None:
            await db.execute(
                text(
                    "UPDATE md_publication_release_holds "
                    "SET state = :state, quarantine_code = :quarantine_code, "
                    "quarantined_at = :quarantined_at "
                    "WHERE publication_id = :publication_id"
                ),
                {
                    "state": PUBLICATION_RELEASE_HOLD_STATE_QUARANTINED,
                    "quarantine_code": "GUARD_RAW_SQL_REJECTED",
                    "quarantined_at": _at(15).isoformat(),
                    "publication_id": staged.publication_id,
                },
            )

        with pytest.raises(MarketDataStoreError) as rejected:
            await store.promote_deferred_provider_result(
                staged,
                promotion_evidence_sha256=_sha("promotion:deferred-raw-sql-v1"),
                pre_publish_guard=raw_sql_quarantine_guard,
            )
        assert rejected.value.code == "PUBLICATION_DEFERRED_QUARANTINED"

        receipt = await db.get(MdPublication, staged.publication_id)
        hold = await _hold_for_publication(db, staged.publication_id)
        assert receipt is not None
        assert hold is not None
        assert receipt.published_at is None
        assert receipt.visibility_sequence is None
        # The raw guard update shares the rejected promotion transaction, so
        # it rolls back rather than becoming an untracked durable quarantine.
        assert hold.state == PUBLICATION_RELEASE_HOLD_STATE_DEFERRED
        await db.rollback()

        assert await store.read_observations(context, knowledge_cutoff=_at(20)) == ()


@pytest.mark.asyncio
async def test_quarantined_deferred_candidate_cannot_be_promoted_or_read() -> None:
    """Quarantine is durable, fail-closed, and cannot be bypassed through promotion."""
    context = _context()

    async def attestation_guard() -> None:
        return None

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store, staged = await _stage_candidate(db, source_revision="deferred-quarantined-v1")
        await store.quarantine_deferred_provider_result(
            staged,
            quarantine_code="LEGACY_SOURCE_WINDOW_MISMATCH",
        )

        with pytest.raises(MarketDataStoreError) as promotion_rejected:
            await store.promote_deferred_provider_result(
                staged,
                promotion_evidence_sha256=_sha("promotion:deferred-quarantined-v1"),
                pre_publish_guard=attestation_guard,
            )
        assert promotion_rejected.value.code == "PUBLICATION_DEFERRED_QUARANTINED"

        hold = await _hold_for_publication(db, staged.publication_id)
        receipt = await db.get(MdPublication, staged.publication_id)
        assert hold is not None
        assert receipt is not None
        assert hold.state == PUBLICATION_RELEASE_HOLD_STATE_QUARANTINED
        assert hold.quarantine_code == "LEGACY_SOURCE_WINDOW_MISMATCH"
        assert hold.quarantined_at is not None
        assert receipt.published_at is None
        assert receipt.visibility_sequence is None
        await db.rollback()

        assert await store.read_observations(context, knowledge_cutoff=_at(20)) == ()
