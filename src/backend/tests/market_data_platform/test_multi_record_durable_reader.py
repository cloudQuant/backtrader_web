"""Durable B2 receipt lookup contracts for the strict local-only reader."""

from __future__ import annotations

import pytest
from sqlalchemy import delete, update

from app.db.database import async_session_maker
from app.models.market_data_platform import (
    MdB2CompletenessReceipt,
    MdObservationRevision,
    MdPublication,
)
from app.services.market_data.multi_record_evidence import (
    B2CompletenessEvidenceIssuer,
    B2CompletenessEvidenceRequest,
)
from app.services.market_data.multi_record_query_service import (
    MultiRecordLocalAccessBinding,
    MultiRecordLocalQueryService,
    MultiRecordLocalReadRequest,
)
from app.services.market_data.publication import (
    PUBLICATION_SOURCE_SNAPSHOT,
    MarketDataPublicationManager,
)
from app.services.market_data.store import MarketDataStore, MarketDataStoreError
from tests.market_data_platform.test_multi_record_evidence import _option_dimensions
from tests.market_data_platform.test_multi_record_store import _record_observation
from tests.market_data_platform.test_store import (
    _at,
    _context,
    _result,
    _seed_dataset_and_provider,
    _seed_source_registry,
    _source_authorization,
)

_ALLOWED_SOURCES = frozenset({"akshare:stock"})
_CURSOR_SIGNING_KEY = "b2-local-only-test-cursor-key-material-0000000000000000000001"


def _strict_context():
    """Build an internal-only B2 context without enabling a public family route."""
    return _context(
        family_id="option.derivative",
        family_contract_version="market-data-family-v1",
        consistency="strict",
        mode="local_only",
        knowledge_cutoff=_at(16),
    )


async def _persist_authorized_b2_source(db):
    """Persist one verified B2 source snapshot and its already-visible facts."""
    context = _strict_context()
    await _seed_dataset_and_provider(db)
    await _seed_source_registry(db)
    persisted = await MarketDataStore(db, clock=lambda: _at(14)).persist_provider_result(
        context,
        _result(
            context=context,
            retrieved_at=_at(12),
            observations=(
                _record_observation(
                    event_at=_at(10),
                    available_at=_at(11),
                    contract="instrument:option:cn:IF2610C100",
                    close="10.00",
                ),
            ),
        ),
        received_at=_at(12),
        source_authorization=_source_authorization(),
    )
    return context, persisted


def _request(*, series_id: str, source_snapshot_id: str, event_at=None):
    return B2CompletenessEvidenceRequest(
        series_id=series_id,
        source_snapshot_id=source_snapshot_id,
        family_id="option.derivative",
        family_contract_version="market-data-family-v1",
        event_at=event_at or _at(10),
        selector_dimensions={
            "underlying_canonical_id": "instrument:futures:cn:IF",
            "expiry": "2026-10-30",
        },
        expected_record_dimensions=(_option_dimensions(),) if event_at is None else (),
        zero_record_evidence=(
            {"attestation": "no contracts reported"} if event_at is not None else None
        ),
    )


@pytest.mark.asyncio
async def test_store_reads_a_durable_b2_manifest_only_when_both_receipts_share_anchor() -> None:
    """Receipt/source publication and current source authorization all gate a B2 read."""
    async with async_session_maker() as db:
        context, persisted = await _persist_authorized_b2_source(db)
        store = MarketDataStore(db, clock=lambda: _at(14))
        staged = await B2CompletenessEvidenceIssuer(db).stage(
            _request(
                series_id=persisted.series_id,
                source_snapshot_id=persisted.source_snapshot_id,
            )
        )
        await db.commit()
        await MarketDataPublicationManager(db, clock=lambda: _at(15)).publish_staged(
            (staged.publication_id,)
        )
        anchor = await store.resolve_visibility_anchor(knowledge_cutoff=_at(16))
        evidence = await store.read_b2_completeness_evidence(
            context,
            selector=staged.selector,
            event_at=_at(10),
            knowledge_cutoff=_at(16),
            visibility_anchor=anchor,
            allowed_source_registry_ids=_ALLOWED_SOURCES,
        )
        revisions = await store.read_observation_revisions(
            context,
            knowledge_cutoff=_at(16),
            visibility_anchor=anchor,
            allowed_source_registry_ids=_ALLOWED_SOURCES,
            exact_event_at=_at(10),
            exact_source_snapshot_id=persisted.source_snapshot_id,
        )

    assert evidence is not None
    assert evidence.receipt_id == staged.receipt_id
    assert evidence.source_snapshot_id == persisted.source_snapshot_id
    assert evidence.selector == staged.selector
    assert evidence.zero_record_certificate is None
    assert [revision.source_snapshot_id for revision in revisions] == [persisted.source_snapshot_id]


@pytest.mark.asyncio
async def test_store_hides_a_pending_b2_receipt_even_when_its_source_is_visible() -> None:
    """Durable-but-pending evidence never becomes a strict local selector."""
    async with async_session_maker() as db:
        context, persisted = await _persist_authorized_b2_source(db)
        store = MarketDataStore(db, clock=lambda: _at(14))
        staged = await B2CompletenessEvidenceIssuer(db).stage(
            _request(
                series_id=persisted.series_id,
                source_snapshot_id=persisted.source_snapshot_id,
            )
        )
        await db.commit()
        anchor = await store.resolve_visibility_anchor(knowledge_cutoff=_at(16))
        evidence = await store.read_b2_completeness_evidence(
            context,
            selector=staged.selector,
            event_at=_at(10),
            knowledge_cutoff=_at(16),
            visibility_anchor=anchor,
            allowed_source_registry_ids=_ALLOWED_SOURCES,
        )

    assert evidence is None


@pytest.mark.asyncio
async def test_store_hides_a_b2_receipt_when_its_linked_source_receipt_is_not_visible() -> None:
    """A B2 publication alone cannot make its source snapshot eligible for a read."""
    async with async_session_maker() as db:
        context, persisted = await _persist_authorized_b2_source(db)
        store = MarketDataStore(db, clock=lambda: _at(14))
        staged = await B2CompletenessEvidenceIssuer(db).stage(
            _request(
                series_id=persisted.series_id,
                source_snapshot_id=persisted.source_snapshot_id,
            )
        )
        await db.commit()
        await MarketDataPublicationManager(db, clock=lambda: _at(15)).publish_staged(
            (staged.publication_id,)
        )
        await db.execute(
            update(MdPublication)
            .where(
                MdPublication.entity_type == PUBLICATION_SOURCE_SNAPSHOT,
                MdPublication.entity_id == persisted.source_snapshot_id,
            )
            .values(published_at=None, visibility_sequence=None)
        )
        await db.commit()
        anchor = await store.resolve_visibility_anchor(knowledge_cutoff=_at(16))
        evidence = await store.read_b2_completeness_evidence(
            context,
            selector=staged.selector,
            event_at=_at(10),
            knowledge_cutoff=_at(16),
            visibility_anchor=anchor,
            allowed_source_registry_ids=_ALLOWED_SOURCES,
        )

    assert evidence is None


@pytest.mark.asyncio
async def test_store_rejects_published_b2_evidence_when_source_event_is_raw_sql_tampered() -> None:
    """A published receipt is still rechecked before a strict reader uses it."""
    async with async_session_maker() as db:
        context, persisted = await _persist_authorized_b2_source(db)
        store = MarketDataStore(db, clock=lambda: _at(14))
        staged = await B2CompletenessEvidenceIssuer(db).stage(
            _request(
                series_id=persisted.series_id,
                source_snapshot_id=persisted.source_snapshot_id,
            )
        )
        await db.commit()
        await MarketDataPublicationManager(db, clock=lambda: _at(15)).publish_staged(
            (staged.publication_id,)
        )
        await db.execute(
            delete(MdObservationRevision).where(
                MdObservationRevision.series_id == persisted.series_id,
                MdObservationRevision.source_snapshot_id == persisted.source_snapshot_id,
                MdObservationRevision.event_time == _at(10),
            )
        )
        await db.commit()
        anchor = await store.resolve_visibility_anchor(knowledge_cutoff=_at(16))

        with pytest.raises(MarketDataStoreError) as rejected:
            await store.read_b2_completeness_evidence(
                context,
                selector=staged.selector,
                event_at=_at(10),
                knowledge_cutoff=_at(16),
                visibility_anchor=anchor,
                allowed_source_registry_ids=_ALLOWED_SOURCES,
            )

    assert rejected.value.code == "B2_COMPLETENESS_EVIDENCE_INTEGRITY"


@pytest.mark.asyncio
async def test_store_rejects_published_b2_evidence_when_receipt_payload_is_raw_sql_tampered() -> (
    None
):
    """A prior publication does not let a changed parent receipt bypass revalidation."""
    async with async_session_maker() as db:
        context, persisted = await _persist_authorized_b2_source(db)
        store = MarketDataStore(db, clock=lambda: _at(14))
        staged = await B2CompletenessEvidenceIssuer(db).stage(
            _request(
                series_id=persisted.series_id,
                source_snapshot_id=persisted.source_snapshot_id,
            )
        )
        await db.commit()
        await MarketDataPublicationManager(db, clock=lambda: _at(15)).publish_staged(
            (staged.publication_id,)
        )
        await db.execute(
            update(MdB2CompletenessReceipt)
            .where(MdB2CompletenessReceipt.id == staged.receipt_id)
            .values(
                selector_dimensions_json={
                    "underlying_canonical_id": "instrument:futures:cn:OTHER",
                    "expiry": "2026-10-30",
                }
            )
        )
        await db.commit()
        anchor = await store.resolve_visibility_anchor(knowledge_cutoff=_at(16))

        with pytest.raises(MarketDataStoreError) as rejected:
            await store.read_b2_completeness_evidence(
                context,
                selector=staged.selector,
                event_at=_at(10),
                knowledge_cutoff=_at(16),
                visibility_anchor=anchor,
                allowed_source_registry_ids=_ALLOWED_SOURCES,
            )

    assert rejected.value.code == "B2_COMPLETENESS_EVIDENCE_INTEGRITY"


@pytest.mark.asyncio
async def test_store_rebuilds_a_durable_zero_certificate_from_a_published_receipt() -> None:
    """An empty event needs the persisted zero digest and cannot use caller state."""
    async with async_session_maker() as db:
        context, persisted = await _persist_authorized_b2_source(db)
        store = MarketDataStore(db, clock=lambda: _at(14))
        staged = await B2CompletenessEvidenceIssuer(db).stage(
            _request(
                series_id=persisted.series_id,
                source_snapshot_id=persisted.source_snapshot_id,
                event_at=_at(11),
            )
        )
        await db.commit()
        await MarketDataPublicationManager(db, clock=lambda: _at(15)).publish_staged(
            (staged.publication_id,)
        )
        anchor = await store.resolve_visibility_anchor(knowledge_cutoff=_at(16))
        evidence = await store.read_b2_completeness_evidence(
            context,
            selector=staged.selector,
            event_at=_at(11),
            knowledge_cutoff=_at(16),
            visibility_anchor=anchor,
            allowed_source_registry_ids=_ALLOWED_SOURCES,
        )

    assert evidence is not None
    assert evidence.zero_record_certificate is not None
    assert evidence.zero_record_certificate.selector_digest == staged.selector.selector_digest
    assert evidence.zero_record_certificate.event_at == _at(11)


@pytest.mark.asyncio
async def test_strict_reader_uses_the_published_durable_manifest_not_request_memory() -> None:
    """The end-to-end internal reader gets its selector and source scope from Store."""
    async with async_session_maker() as db:
        context, persisted = await _persist_authorized_b2_source(db)
        store = MarketDataStore(db, clock=lambda: _at(14))
        staged = await B2CompletenessEvidenceIssuer(db).stage(
            _request(
                series_id=persisted.series_id,
                source_snapshot_id=persisted.source_snapshot_id,
            )
        )
        await db.commit()
        await MarketDataPublicationManager(db, clock=lambda: _at(15)).publish_staged(
            (staged.publication_id,)
        )
        execution = await MultiRecordLocalQueryService(
            store,
            cursor_signing_key=_CURSOR_SIGNING_KEY,
            clock=lambda: _at(16),
        ).execute(
            MultiRecordLocalReadRequest(
                context=context,
                selector=staged.selector,
                event_at=_at(10),
                knowledge_cutoff=_at(16),
                access_binding=MultiRecordLocalAccessBinding(
                    principal_scope="principal-a",
                    tenant_scope="tenant-a",
                    entitlement_revision="entitlement-v1",
                    allowed_source_registry_ids=_ALLOWED_SOURCES,
                ),
            )
        )

    assert execution.completeness.is_complete
    assert execution.selector_digest == staged.selector.selector_digest
    assert [item.source_snapshot_id for item in execution.observations] == [
        persisted.source_snapshot_id
    ]
