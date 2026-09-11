"""Local-only B2 selector, PIT, and cursor contracts."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.services.market_data.coverage import ObservationQuality
from app.services.market_data.multi_record import (
    B2SliceSelector,
    CompletenessStatus,
    ZeroRecordCertificate,
    normalize_semantic_record_key,
)
from app.services.market_data.multi_record_evidence import DurableB2CompletenessEvidence
from app.services.market_data.multi_record_query_service import (
    MultiRecordLocalAccessBinding,
    MultiRecordLocalQueryService,
    MultiRecordLocalQueryServiceError,
    MultiRecordLocalReadRequest,
    _dimensions_match_selector,
)
from app.services.market_data.publication import MarketDataVisibilityAnchor
from app.services.market_data.store import LocalObservationRevision
from tests.market_data_platform.test_store import _at, _context

_CURSOR_SIGNING_KEY = "b2-local-only-test-cursor-key-material-0000000000000000000001"
_DEFAULT_EVIDENCE = object()


class _LocalOnlyStore:
    """A Store double that exposes no provider, lease, or resolver capability."""

    def __init__(
        self,
        *,
        revisions: tuple[LocalObservationRevision, ...],
        anchor: MarketDataVisibilityAnchor,
        evidence: DurableB2CompletenessEvidence | None | object = _DEFAULT_EVIDENCE,
    ) -> None:
        self.revisions = revisions
        self.anchor = anchor
        self.resolve_cutoffs: list[datetime] = []
        self.evidence = evidence
        self.evidence_calls: list[
            tuple[datetime, MarketDataVisibilityAnchor, frozenset[str], datetime, str]
        ] = []
        self.read_calls: list[
            tuple[
                datetime,
                MarketDataVisibilityAnchor,
                frozenset[str] | None,
                datetime | None,
                str | None,
            ]
        ] = []

    async def resolve_visibility_anchor(
        self,
        *,
        knowledge_cutoff: datetime,
    ) -> MarketDataVisibilityAnchor:
        self.resolve_cutoffs.append(knowledge_cutoff)
        return self.anchor

    async def read_b2_completeness_evidence(
        self,
        context,
        *,
        selector: B2SliceSelector,
        event_at: datetime,
        knowledge_cutoff: datetime,
        visibility_anchor: MarketDataVisibilityAnchor,
        allowed_source_registry_ids: frozenset[str],
    ) -> DurableB2CompletenessEvidence | None:
        self.evidence_calls.append(
            (
                knowledge_cutoff,
                visibility_anchor,
                allowed_source_registry_ids,
                event_at,
                selector.selector_digest,
            )
        )
        if self.evidence is None:
            return None
        if isinstance(self.evidence, DurableB2CompletenessEvidence):
            return self.evidence
        source_snapshot_id = (
            self.revisions[0].source_snapshot_id if self.revisions else "source-b2-evidence"
        )
        certificate = (
            ZeroRecordCertificate(
                selector_digest=selector.selector_digest,
                event_at=event_at,
                evidence_sha256="e" * 64,
            )
            if not selector.expected_record_key_sha256s
            else None
        )
        return DurableB2CompletenessEvidence(
            receipt_id="receipt-b2-evidence",
            receipt_sha256="d" * 64,
            source_snapshot_id=source_snapshot_id,
            event_at=event_at,
            selector=selector,
            zero_record_certificate=certificate,
        )

    async def read_observation_revisions(
        self,
        context,
        *,
        knowledge_cutoff: datetime,
        visibility_anchor: MarketDataVisibilityAnchor,
        include_unusable_for_coverage: bool = False,
        allowed_source_registry_ids: frozenset[str] | None = None,
        exact_event_at: datetime | None = None,
        exact_source_snapshot_id: str | None = None,
    ) -> tuple[LocalObservationRevision, ...]:
        assert include_unusable_for_coverage is False
        self.read_calls.append(
            (
                knowledge_cutoff,
                visibility_anchor,
                allowed_source_registry_ids,
                exact_event_at,
                exact_source_snapshot_id,
            )
        )
        return tuple(
            item
            for item in self.revisions
            if exact_source_snapshot_id is None
            or item.source_snapshot_id == exact_source_snapshot_id
        )


def _local_context(*, mode: str = "local_only"):
    return _context(
        family_id="option.derivative",
        family_contract_version="market-data-family-v1",
        consistency="strict",
        mode=mode,
        knowledge_cutoff=_at(14),
    )


def _access() -> MultiRecordLocalAccessBinding:
    return MultiRecordLocalAccessBinding(
        principal_scope="principal-a",
        tenant_scope="tenant-a",
        entitlement_revision="entitlement-v1",
        allowed_source_registry_ids=frozenset({"akshare:stock"}),
    )


@pytest.mark.parametrize("allowed_source_registry_ids", [None, frozenset()])
def test_local_b2_access_binding_requires_a_nonempty_current_source_allowlist(
    allowed_source_registry_ids: object,
) -> None:
    """No internal B2 request can ask Store to perform an unfiltered local read."""
    with pytest.raises((TypeError, ValueError)):
        MultiRecordLocalAccessBinding(
            principal_scope="principal-a",
            tenant_scope="tenant-a",
            entitlement_revision="entitlement-v1",
            allowed_source_registry_ids=allowed_source_registry_ids,  # type: ignore[arg-type]
        )


def _revision(
    contract: str,
    *,
    event_at: datetime | None = None,
    revision_number: int = 1,
    visibility_sequence: int = 7,
    close: str = "10.00",
    family_id: str = "option.derivative",
    source_snapshot_id: str = "source-b2-evidence",
) -> LocalObservationRevision:
    semantic_key = normalize_semantic_record_key(
        family_id=family_id,
        family_contract_version="market-data-family-v1",
        dimensions={
            "underlying_canonical_id": "IF",
            "expiry": "2026-10-30",
            "contract_canonical_id": contract,
            "right": "call",
            "strike": contract.rsplit("C", maxsplit=1)[-1],
        },
    )
    return LocalObservationRevision(
        revision_id=f"revision-{contract}-{revision_number}",
        source_snapshot_id=source_snapshot_id,
        event_at=event_at or _at(10),
        available_at=_at(12),
        committed_at=_at(12),
        visible_at=_at(12),
        visibility_sequence=visibility_sequence,
        revision_number=revision_number,
        quality=ObservationQuality.PASS,
        fields={"close": close},
        source_available_at=_at(11),
        semantic_record_key=semantic_key.canonical_json,
        semantic_record_key_sha256=semantic_key.sha256,
    )


def _selector(*revisions: LocalObservationRevision) -> B2SliceSelector:
    return B2SliceSelector(
        family_id="option.derivative",
        family_contract_version="market-data-family-v1",
        selector_dimensions={"underlying_canonical_id": "IF", "expiry": "2026-10-30"},
        expected_record_key_sha256s=frozenset(
            revision.semantic_record_key_sha256 for revision in revisions
        ),
    )


def _request(
    *,
    context,
    selector: B2SliceSelector,
    page_size: int = 500,
    cursor: str | None = None,
) -> MultiRecordLocalReadRequest:
    return MultiRecordLocalReadRequest(
        context=context,
        selector=selector,
        event_at=_at(10),
        knowledge_cutoff=_at(14),
        access_binding=_access(),
        page_size=page_size,
        cursor=cursor,
    )


def _service(store: _LocalOnlyStore) -> MultiRecordLocalQueryService:
    return MultiRecordLocalQueryService(
        store,
        cursor_signing_key=_CURSOR_SIGNING_KEY,
        clock=lambda: _at(14),
    )


@pytest.mark.asyncio
async def test_local_b2_service_reads_only_store_revisions_and_returns_complete_slice() -> None:
    """The internal service has no provider fallback and retains stable key order."""
    first = _revision("IF2610C100")
    second = _revision("IF2610C105")
    anchor = MarketDataVisibilityAnchor(visible_at=_at(14), max_visibility_sequence=7)
    store = _LocalOnlyStore(revisions=(second, first), anchor=anchor)

    execution = await _service(store).execute(
        _request(context=_local_context(), selector=_selector(first, second))
    )

    assert execution.completeness.status is CompletenessStatus.COMPLETE
    assert [item.semantic_record_key for item in execution.observations] == sorted(
        item.semantic_record_key for item in (first, second)
    )
    assert execution.next_cursor is None
    assert store.resolve_cutoffs == [_at(14)]
    assert store.read_calls == [
        (_at(14), anchor, frozenset({"akshare:stock"}), _at(10), "source-b2-evidence")
    ]
    assert store.evidence_calls == [
        (
            _at(14),
            anchor,
            frozenset({"akshare:stock"}),
            _at(10),
            _selector(first, second).selector_digest,
        )
    ]
    assert not hasattr(store, "providers")
    assert not hasattr(store, "fetch_lease_manager")


@pytest.mark.asyncio
async def test_incomplete_slice_returns_no_partial_observations_or_cursor() -> None:
    """A missing option contract stays a completeness result, never a partial page."""
    present = _revision("IF2610C100")
    missing = _revision("IF2610C105")
    store = _LocalOnlyStore(
        revisions=(present,),
        anchor=MarketDataVisibilityAnchor(visible_at=_at(14), max_visibility_sequence=7),
    )

    execution = await _service(store).execute(
        _request(context=_local_context(), selector=_selector(present, missing))
    )

    assert execution.completeness.status is CompletenessStatus.INCOMPLETE
    assert execution.completeness.reason_codes == ("MISSING_RECORD_KEY",)
    assert execution.observations == ()
    assert execution.next_cursor is None


@pytest.mark.asyncio
async def test_empty_expected_manifest_without_durable_zero_receipt_stays_incomplete() -> None:
    """A bare local empty set cannot become a complete zero-record B2 response."""
    selector = B2SliceSelector(
        family_id="option.derivative",
        family_contract_version="market-data-family-v1",
        selector_dimensions={"underlying_canonical_id": "IF", "expiry": "2026-10-30"},
        expected_record_key_sha256s=frozenset(),
    )
    store = _LocalOnlyStore(
        revisions=(),
        anchor=MarketDataVisibilityAnchor(visible_at=_at(14), max_visibility_sequence=7),
        evidence=None,
    )

    execution = await _service(store).execute(_request(context=_local_context(), selector=selector))

    assert execution.completeness.status is CompletenessStatus.INCOMPLETE
    assert execution.completeness.reason_codes == ("DURABLE_SELECTOR_EVIDENCE_MISSING",)
    assert execution.observations == ()
    assert store.read_calls == []


@pytest.mark.asyncio
async def test_durable_zero_receipt_allows_only_its_exact_empty_selector_event() -> None:
    """A Store-derived zero certificate can complete the matching empty B2 read."""
    selector = B2SliceSelector(
        family_id="option.derivative",
        family_contract_version="market-data-family-v1",
        selector_dimensions={"underlying_canonical_id": "IF", "expiry": "2026-10-30"},
        expected_record_key_sha256s=frozenset(),
    )
    store = _LocalOnlyStore(
        revisions=(),
        anchor=MarketDataVisibilityAnchor(visible_at=_at(14), max_visibility_sequence=7),
    )

    execution = await _service(store).execute(_request(context=_local_context(), selector=selector))

    assert execution.completeness.status is CompletenessStatus.COMPLETE
    assert execution.completeness.zero_record_certificate_used is True
    assert execution.observations == ()
    assert store.read_calls == [
        (_at(14), store.anchor, frozenset({"akshare:stock"}), _at(10), "source-b2-evidence")
    ]


@pytest.mark.asyncio
async def test_reader_rejects_a_store_evidence_selector_mismatch_before_fact_read() -> None:
    """A buggy Store double cannot replace the requested durable manifest."""
    first = _revision("IF2610C100")
    requested = _selector(first)
    mismatched = B2SliceSelector(
        family_id="option.derivative",
        family_contract_version="market-data-family-v1",
        selector_dimensions={"underlying_canonical_id": "IF", "expiry": "2026-10-30"},
        expected_record_key_sha256s=frozenset({"f" * 64}),
    )
    store = _LocalOnlyStore(
        revisions=(first,),
        anchor=MarketDataVisibilityAnchor(visible_at=_at(14), max_visibility_sequence=7),
        evidence=DurableB2CompletenessEvidence(
            receipt_id="receipt-b2-evidence",
            receipt_sha256="d" * 64,
            source_snapshot_id="source-b2-evidence",
            event_at=_at(10),
            selector=mismatched,
            zero_record_certificate=None,
        ),
    )

    with pytest.raises(MultiRecordLocalQueryServiceError) as rejected:
        await _service(store).execute(_request(context=_local_context(), selector=requested))

    assert rejected.value.code == "B2_LOCAL_DURABLE_EVIDENCE_MISMATCH"
    assert store.read_calls == []


@pytest.mark.asyncio
async def test_reader_passes_the_durable_source_scope_before_store_deduplication() -> None:
    """A newer revision from another source cannot replace the receipt-bound fact."""
    receipt_source = _revision("IF2610C100", source_snapshot_id="source-b2-evidence")
    foreign_source = _revision(
        "IF2610C100",
        revision_number=2,
        source_snapshot_id="source-foreign",
    )
    store = _LocalOnlyStore(
        revisions=(receipt_source, foreign_source),
        anchor=MarketDataVisibilityAnchor(visible_at=_at(14), max_visibility_sequence=7),
    )

    execution = await _service(store).execute(
        _request(context=_local_context(), selector=_selector(receipt_source))
    )

    assert execution.completeness.status is CompletenessStatus.COMPLETE
    assert execution.observations == (receipt_source,)
    assert store.read_calls[-1][-1] == "source-b2-evidence"


@pytest.mark.asyncio
async def test_cursor_replays_the_first_page_anchor_and_pages_without_duplicates() -> None:
    """Continuation uses its signed PIT anchor instead of resolving a new one."""
    first = _revision("IF2610C100")
    second = _revision("IF2610C105")
    third = _revision("IF2610C110")
    anchor = MarketDataVisibilityAnchor(visible_at=_at(14), max_visibility_sequence=7)
    store = _LocalOnlyStore(revisions=(third, first, second), anchor=anchor)
    service = _service(store)
    selector = _selector(first, second, third)
    first_page = await service.execute(
        _request(context=_local_context(), selector=selector, page_size=1)
    )

    assert first_page.next_cursor is not None
    second_page = await service.execute(
        _request(
            context=_local_context(),
            selector=selector,
            page_size=1,
            cursor=first_page.next_cursor,
        )
    )

    assert [item.revision_id for item in first_page.observations + second_page.observations] == [
        item.revision_id
        for item in sorted((first, second, third), key=lambda item: item.semantic_record_key)
    ][:2]
    assert store.resolve_cutoffs == [_at(14)]
    assert [call[1] for call in store.read_calls] == [anchor, anchor]
    assert [call[3] for call in store.read_calls] == [_at(10), _at(10)]
    assert [call[4] for call in store.read_calls] == ["source-b2-evidence", "source-b2-evidence"]


@pytest.mark.asyncio
async def test_cursor_rejects_a_changed_durable_receipt_before_fact_read() -> None:
    """A continuation cannot silently move to a newer receipt for the same selector."""
    first = _revision("IF2610C100")
    second = _revision("IF2610C105")
    third = _revision("IF2610C110")
    anchor = MarketDataVisibilityAnchor(visible_at=_at(14), max_visibility_sequence=7)
    store = _LocalOnlyStore(revisions=(first, second, third), anchor=anchor)
    service = _service(store)
    selector = _selector(first, second, third)
    first_page = await service.execute(
        _request(context=_local_context(), selector=selector, page_size=1)
    )
    assert first_page.next_cursor is not None
    store.evidence = DurableB2CompletenessEvidence(
        receipt_id="receipt-b2-evidence-replaced",
        receipt_sha256="c" * 64,
        source_snapshot_id="source-b2-evidence",
        event_at=_at(10),
        selector=selector,
        zero_record_certificate=None,
    )
    reads_before = len(store.read_calls)

    with pytest.raises(MultiRecordLocalQueryServiceError) as rejected:
        await service.execute(
            _request(
                context=_local_context(),
                selector=selector,
                page_size=1,
                cursor=first_page.next_cursor,
            )
        )

    assert rejected.value.code == "B2_LOCAL_CURSOR_EVIDENCE_MISMATCH"
    assert len(store.read_calls) == reads_before


@pytest.mark.asyncio
async def test_cursor_tamper_or_selector_replay_is_rejected_before_another_store_read() -> None:
    """HMAC and selector digest bind a continuation before local data is touched."""
    first = _revision("IF2610C100")
    second = _revision("IF2610C105")
    third = _revision("IF2610C110")
    anchor = MarketDataVisibilityAnchor(visible_at=_at(14), max_visibility_sequence=7)
    store = _LocalOnlyStore(revisions=(first, second, third), anchor=anchor)
    service = _service(store)
    selector = _selector(first, second, third)
    first_page = await service.execute(
        _request(context=_local_context(), selector=selector, page_size=1)
    )
    assert first_page.next_cursor is not None
    reads_before = len(store.read_calls)
    tampered = first_page.next_cursor[:-1] + ("A" if first_page.next_cursor[-1] != "A" else "B")

    with pytest.raises(MultiRecordLocalQueryServiceError) as tamper_rejected:
        await service.execute(
            _request(
                context=_local_context(),
                selector=selector,
                page_size=1,
                cursor=tampered,
            )
        )
    with pytest.raises(MultiRecordLocalQueryServiceError) as selector_rejected:
        await service.execute(
            _request(
                context=_local_context(),
                selector=_selector(first, second),
                page_size=1,
                cursor=first_page.next_cursor,
            )
        )

    assert tamper_rejected.value.code == "B2_LOCAL_CURSOR_SIGNATURE_INVALID"
    assert selector_rejected.value.code == "B2_LOCAL_CURSOR_MISMATCH"
    assert len(store.read_calls) == reads_before


@pytest.mark.asyncio
async def test_local_service_rejects_non_local_mode_before_visibility_or_store_reads() -> None:
    """The internal B2 reader cannot be repurposed as a local-first fetch path."""
    first = _revision("IF2610C100")
    store = _LocalOnlyStore(
        revisions=(first,),
        anchor=MarketDataVisibilityAnchor(visible_at=_at(14), max_visibility_sequence=7),
    )

    with pytest.raises(MultiRecordLocalQueryServiceError) as rejected:
        await _service(store).execute(
            _request(context=_local_context(mode="local_first"), selector=_selector(first))
        )

    assert rejected.value.code == "B2_LOCAL_MODE_REQUIRED"
    assert store.resolve_cutoffs == []
    assert store.read_calls == []


@pytest.mark.parametrize(
    ("dimensions", "selector_dimensions"),
    [
        ({}, {"settlement_type": None}),
        ({"settlement_type": True}, {"settlement_type": 1}),
        ({"strike": 1}, {"strike": 1.0}),
        ({"settlement_price": -0.0}, {"settlement_price": 0.0}),
        (
            {"greeks": {"delta": True, "legs": (1,)}},
            {"greeks": {"delta": 1, "legs": (1.0,)}},
        ),
    ],
)
def test_selector_dimensions_require_present_keys_and_exact_json_value_types(
    dimensions: dict[str, object],
    selector_dimensions: dict[str, object],
) -> None:
    """A selector digest cannot match a row with absent or coercible JSON values."""
    assert not _dimensions_match_selector(dimensions, selector_dimensions)


def test_selector_dimensions_accept_exact_null_json_value() -> None:
    """A declared null matches only a present null-valued business dimension."""
    assert _dimensions_match_selector(
        {"settlement_type": None},
        {"settlement_type": None},
    )


@pytest.mark.asyncio
async def test_cursor_keeps_its_original_expiry_and_rejects_the_exact_expiry_instant() -> None:
    """A continuation cannot extend the lifetime of a frozen local replay."""
    first = _revision("IF2610C100")
    second = _revision("IF2610C105")
    third = _revision("IF2610C110")
    anchor = MarketDataVisibilityAnchor(visible_at=_at(14), max_visibility_sequence=7)
    store = _LocalOnlyStore(revisions=(first, second, third), anchor=anchor)
    selector = _selector(first, second, third)
    request = _request(context=_local_context(), selector=selector, page_size=1)
    first_service = MultiRecordLocalQueryService(
        store,
        cursor_signing_key=_CURSOR_SIGNING_KEY,
        clock=lambda: _at(14),
    )
    first_page = await first_service.execute(request)
    assert first_page.next_cursor is not None

    continuation_service = MultiRecordLocalQueryService(
        store,
        cursor_signing_key=_CURSOR_SIGNING_KEY,
        clock=lambda: _at(14) + timedelta(minutes=1),
    )
    second_page = await continuation_service.execute(
        _request(
            context=_local_context(),
            selector=selector,
            page_size=1,
            cursor=first_page.next_cursor,
        )
    )
    assert second_page.next_cursor is not None

    at_original_expiry_service = MultiRecordLocalQueryService(
        store,
        cursor_signing_key=_CURSOR_SIGNING_KEY,
        clock=lambda: _at(14) + timedelta(minutes=15),
    )
    reads_before = len(store.read_calls)
    with pytest.raises(MultiRecordLocalQueryServiceError) as expired:
        await at_original_expiry_service.execute(
            _request(
                context=_local_context(),
                selector=selector,
                page_size=1,
                cursor=second_page.next_cursor,
            )
        )

    assert expired.value.code == "B2_LOCAL_CURSOR_EXPIRED"
    assert len(store.read_calls) == reads_before
