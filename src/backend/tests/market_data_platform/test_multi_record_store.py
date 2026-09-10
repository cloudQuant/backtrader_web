"""Local-only persistence contracts for Iteration 197 B2 record-keyed facts."""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.dialects import mysql

from app.db.database import async_session_maker
from app.models.market_data_platform import MdObservationRevision, MdSourceSnapshot
from app.services.market_data import store as store_module
from app.services.market_data.multi_record import SINGLE_RECORD_SEMANTIC_KEY_SHA256
from app.services.market_data.providers import ProviderMarketObservation
from app.services.market_data.store import (
    UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
    MarketDataStore,
    MarketDataStoreError,
)
from tests.market_data_platform.test_store import (
    _at,
    _context,
    _result,
    _seed_dataset_and_provider,
)


def _record_observation(
    *,
    event_at: datetime,
    available_at: datetime,
    contract: str,
    close: str,
) -> ProviderMarketObservation:
    """Make one option-like same-time record without opening an option route."""
    return ProviderMarketObservation(
        event_at=event_at,
        available_at=available_at,
        fields={"close": close},
        record_dimensions={
            "contract_canonical_id": contract,
            "right": "call",
            "strike": contract.rsplit("C", maxsplit=1)[-1],
        },
    )


def _multi_record_context():
    """Build a lower-level context; public B2 family resolution remains disabled."""
    return _context(
        family_id="option.derivative",
        family_contract_version="market-data-family-v1",
    )


def test_provider_record_dimensions_are_deeply_frozen_before_store_identity_derivation() -> None:
    """Mutating a caller payload cannot change an already-created record DTO's key."""
    raw_dimensions: dict[str, object] = {
        "contract": {"canonical_id": "IF2610C100"},
        "coordinate": ["call", "100"],
    }
    observation = ProviderMarketObservation(
        event_at=_at(10),
        available_at=_at(11),
        fields={"close": "10.00"},
        record_dimensions=raw_dimensions,
    )
    raw_dimensions["contract"] = {"canonical_id": "MUTATED"}
    raw_dimensions["coordinate"] = ["put", "999"]

    assert observation.record_dimensions == {
        "contract": {"canonical_id": "IF2610C100"},
        "coordinate": ("call", "100"),
    }


def test_provider_record_dimensions_reject_an_oversized_identity_before_store_receipt() -> None:
    """A provider cannot defer an overlarge business identity until persistence."""
    with pytest.raises(ValueError, match="canonical JSON exceeds the maximum permitted size"):
        ProviderMarketObservation(
            event_at=_at(10),
            available_at=_at(11),
            fields={"close": "10.00"},
            record_dimensions={f"dimension_{index:03d}": "x" * 255 for index in range(128)},
        )


def test_revision_number_allocation_uses_a_mysql_current_locking_read_after_series_lock() -> None:
    """The ordinal reader cannot reuse an earlier REPEATABLE READ snapshot."""
    statement = store_module._revision_number_current_read_statement(
        series_id="series-id",
        record_coordinates=((_at(10), "a" * 64),),
    )
    compiled = str(statement.compile(dialect=mysql.dialect()))

    assert "FOR UPDATE" in compiled
    assert "max(" not in compiled.lower()
    assert "GROUP BY" not in compiled
    assert "semantic_record_key_sha256" in compiled
    assert "LIMIT" in compiled


def test_series_race_recovery_uses_a_mysql_current_locking_read() -> None:
    """A unique-series collision cannot retry through an old RR read view."""
    statement = store_module._series_lookup_statement(
        semantic_key_sha256="a" * 64,
        for_update=True,
    )
    compiled = str(statement.compile(dialect=mysql.dialect()))

    assert "FOR UPDATE" in compiled


@pytest.mark.asyncio
async def test_store_persists_two_same_time_record_keys_and_reads_them_independently() -> None:
    """Distinct dimensions can coexist at one event time and survive PIT selection."""
    context = _multi_record_context()
    event_at = _at(10)

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db, clock=lambda: _at(14))
        persisted = await store.persist_provider_result(
            context,
            _result(
                context=context,
                retrieved_at=_at(12),
                observations=(
                    _record_observation(
                        event_at=event_at,
                        available_at=_at(11),
                        contract="IF2610C100",
                        close="10.00",
                    ),
                    _record_observation(
                        event_at=event_at,
                        available_at=_at(11),
                        contract="IF2610C105",
                        close="11.00",
                    ),
                ),
            ),
            received_at=_at(12),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await db.commit()

        stored = list(
            (
                await db.execute(
                    select(MdObservationRevision)
                    .where(MdObservationRevision.id.in_(persisted.observation_revision_ids))
                    .order_by(MdObservationRevision.semantic_record_key_sha256)
                )
            )
            .scalars()
            .all()
        )
        selected = await store.read_observation_revisions(context, knowledge_cutoff=_at(15))
        current_authorized_read = await store.read_observation_revisions(
            context,
            knowledge_cutoff=_at(15),
            allowed_source_registry_ids=frozenset({"akshare:stock"}),
        )

    assert len(stored) == 2
    assert {
        store_module._stored_utc(item.event_time, field_name="stored multi-record event_time")
        for item in stored
    } == {event_at}
    assert {item.revision_number for item in stored} == {1}
    assert len({item.semantic_record_key_sha256 for item in stored}) == 2
    assert len(selected) == 2
    assert [item.semantic_record_key for item in selected] == sorted(
        item.semantic_record_key for item in selected
    )
    assert {item.fields["close"] for item in selected} == {"10.00", "11.00"}
    # This test uses the explicit legacy-import compatibility seam. B2's local
    # reader always passes a current allow-list, so these historical receipts
    # cannot be exposed through that path.
    assert current_authorized_read == ()


@pytest.mark.asyncio
async def test_store_rejects_duplicate_same_time_semantic_record_before_source_receipt() -> None:
    """A repeated business row cannot create an ambiguous source snapshot."""
    context = _multi_record_context()
    event_at = _at(10)

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db, clock=lambda: _at(14))

        with pytest.raises(MarketDataStoreError) as rejected:
            await store.persist_provider_result(
                context,
                _result(
                    context=context,
                    retrieved_at=_at(12),
                    observations=(
                        _record_observation(
                            event_at=event_at,
                            available_at=_at(11),
                            contract="IF2610C100",
                            close="10.00",
                        ),
                        _record_observation(
                            event_at=event_at,
                            available_at=_at(11),
                            contract="IF2610C100",
                            close="11.00",
                        ),
                    ),
                ),
                received_at=_at(12),
                unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
            )
        snapshot_count = await db.scalar(select(func.count()).select_from(MdSourceSnapshot))

    assert rejected.value.code == "DUPLICATE_PROVIDER_RECORD"
    assert snapshot_count == 0


@pytest.mark.asyncio
async def test_store_rejects_an_oversized_batch_of_record_identities_before_source_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Store retains a total semantic-identity budget across a receipt batch."""
    context = _multi_record_context()
    monkeypatch.setattr(store_module, "_MAX_NORMALIZED_RECORD_IDENTITIES_BYTES", 1)

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db, clock=lambda: _at(14))

        with pytest.raises(MarketDataStoreError) as rejected:
            await store.persist_provider_result(
                context,
                _result(
                    context=context,
                    retrieved_at=_at(12),
                    observations=(
                        _record_observation(
                            event_at=_at(10),
                            available_at=_at(11),
                            contract="IF2610C100",
                            close="10.00",
                        ),
                    ),
                ),
                received_at=_at(12),
                unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
            )
        snapshot_count = await db.scalar(select(func.count()).select_from(MdSourceSnapshot))

    assert rejected.value.code == "PROVIDER_RECORD_IDENTITIES_TOO_LARGE"
    assert snapshot_count == 0


@pytest.mark.asyncio
async def test_store_requires_dimensions_for_unconfigured_b2_family_before_receipt() -> None:
    """The lower-level writer cannot silently turn a B2 row into a singleton."""
    context = _multi_record_context()

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db, clock=lambda: _at(14))

        with pytest.raises(MarketDataStoreError) as rejected:
            await store.persist_provider_result(
                context,
                _result(
                    context=context,
                    retrieved_at=_at(12),
                    observations=(
                        ProviderMarketObservation(
                            event_at=_at(10),
                            available_at=_at(11),
                            fields={"close": "10.00"},
                        ),
                    ),
                ),
                received_at=_at(12),
                unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
            )
        snapshot_count = await db.scalar(select(func.count()).select_from(MdSourceSnapshot))

    assert rejected.value.code == "PROVIDER_RECORD_DIMENSIONS_REQUIRED"
    assert snapshot_count == 0


@pytest.mark.asyncio
async def test_store_rejects_record_dimensions_for_singleton_family_before_receipt() -> None:
    """A ready single-record family cannot opt into B2 storage shape by accident."""
    context = _context()

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db, clock=lambda: _at(14))

        with pytest.raises(MarketDataStoreError) as rejected:
            await store.persist_provider_result(
                context,
                _result(
                    context=context,
                    retrieved_at=_at(12),
                    observations=(
                        ProviderMarketObservation(
                            event_at=_at(10),
                            available_at=_at(11),
                            fields={"close": "10.00"},
                            record_dimensions={"contract_canonical_id": "IF2610C100"},
                        ),
                    ),
                ),
                received_at=_at(12),
                unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
            )
        snapshot_count = await db.scalar(select(func.count()).select_from(MdSourceSnapshot))

    assert rejected.value.code == "UNEXPECTED_PROVIDER_RECORD_DIMENSIONS"
    assert snapshot_count == 0


@pytest.mark.asyncio
async def test_store_corrects_one_same_time_record_without_revising_its_peer() -> None:
    """Revision allocation is scoped to event time plus semantic record key."""
    context = _multi_record_context()
    event_at = _at(10)

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db, clock=lambda: _at(16))
        await store.persist_provider_result(
            context,
            _result(
                context=context,
                retrieved_at=_at(12),
                observations=(
                    _record_observation(
                        event_at=event_at,
                        available_at=_at(11),
                        contract="IF2610C100",
                        close="10.00",
                    ),
                    _record_observation(
                        event_at=event_at,
                        available_at=_at(11),
                        contract="IF2610C105",
                        close="11.00",
                    ),
                ),
            ),
            received_at=_at(12),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await store.persist_provider_result(
            context,
            _result(
                context=context,
                retrieved_at=_at(14),
                source_revision="v2",
                observations=(
                    _record_observation(
                        event_at=event_at,
                        available_at=_at(13),
                        contract="IF2610C100",
                        close="12.00",
                    ),
                ),
            ),
            received_at=_at(14),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await db.commit()
        selected = await store.read_observation_revisions(context, knowledge_cutoff=_at(17))

    by_contract = {
        json.loads(item.semantic_record_key)["dimensions"]["contract_canonical_id"]: item
        for item in selected
    }
    assert by_contract["IF2610C100"].revision_number == 2
    assert by_contract["IF2610C100"].fields == {"close": "12.00"}
    assert by_contract["IF2610C105"].revision_number == 1
    assert by_contract["IF2610C105"].fields == {"close": "11.00"}


@pytest.mark.asyncio
async def test_store_exact_event_read_avoids_loading_other_context_events() -> None:
    """The B2 reader can constrain Store selection to the requested event instant."""
    context = _multi_record_context()
    exact_event_at = _at(10).replace(microsecond=123456)

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db, clock=lambda: _at(14))
        await store.persist_provider_result(
            context,
            _result(
                context=context,
                retrieved_at=_at(12),
                observations=(
                    _record_observation(
                        event_at=exact_event_at,
                        available_at=_at(11),
                        contract="IF2610C100",
                        close="10.00",
                    ),
                    _record_observation(
                        event_at=_at(11),
                        available_at=_at(11),
                        contract="IF2610C105",
                        close="11.00",
                    ),
                ),
            ),
            received_at=_at(12),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await db.commit()

        all_window_rows = await store.read_observation_revisions(
            context,
            knowledge_cutoff=_at(15),
        )
        exact_event_rows = await store.read_observation_revisions(
            context,
            knowledge_cutoff=_at(15),
            exact_event_at=exact_event_at,
        )

    assert {item.event_at for item in all_window_rows} == {exact_event_at, _at(11)}
    assert {item.event_at for item in exact_event_rows} == {exact_event_at}


@pytest.mark.asyncio
async def test_store_rejects_exact_event_outside_the_resolved_context_window() -> None:
    """A caller cannot use the narrowed predicate to escape its series context."""
    context = _multi_record_context()

    async with async_session_maker() as db:
        store = MarketDataStore(db, clock=lambda: _at(14))
        with pytest.raises(MarketDataStoreError) as rejected:
            await store.read_observation_revisions(
                context,
                knowledge_cutoff=_at(15),
                exact_event_at=_at(16),
            )

    assert rejected.value.code == "LOCAL_OBSERVATION_EVENT_OUT_OF_WINDOW"


@pytest.mark.asyncio
async def test_store_rejects_an_exact_event_without_a_timezone() -> None:
    """The narrowed local predicate cannot silently treat a naive time as UTC."""
    context = _multi_record_context()

    async with async_session_maker() as db:
        store = MarketDataStore(db, clock=lambda: _at(14))
        with pytest.raises(MarketDataStoreError) as rejected:
            await store.read_observation_revisions(
                context,
                knowledge_cutoff=_at(15),
                exact_event_at=_at(10).replace(tzinfo=None),
            )

    assert rejected.value.code == "TIMESTAMP_INVALID"


@pytest.mark.asyncio
async def test_store_uses_singleton_v3_identity_for_existing_single_record_writes() -> None:
    """The new key scheme retains one-record behavior without rehashing legacy rows."""
    context = _context()
    event_at = _at(10)

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db, clock=lambda: _at(14))
        persisted = await store.persist_provider_result(
            context,
            _result(
                context=context,
                retrieved_at=_at(12),
                observations=(
                    ProviderMarketObservation(
                        event_at=event_at,
                        available_at=_at(11),
                        fields={"close": "10.00"},
                    ),
                ),
            ),
            received_at=_at(12),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await db.commit()
        revision = await db.get(MdObservationRevision, persisted.observation_revision_ids[0])

    assert revision is not None
    assert revision.semantic_record_key_sha256 == SINGLE_RECORD_SEMANTIC_KEY_SHA256
    assert revision.revision_key_sha256 == store_module._observation_revision_identity_sha256(
        contract_version=store_module._OBSERVATION_REVISION_CONTRACT_V3,
        series_semantic_key_sha256=MarketDataStore.series_identity(context).semantic_key_sha256,
        source_snapshot_id=revision.source_snapshot_id,
        event_at=event_at,
        available_at=_at(12),
        fields_sha256=revision.fields_sha256,
        quality=store_module.ObservationQuality(revision.quality_status),
        revision_number=1,
        source_available_at=_at(11),
        semantic_record_key_sha256=SINGLE_RECORD_SEMANTIC_KEY_SHA256,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("contract_version", "source_available_at"),
    (
        (store_module._OBSERVATION_REVISION_CONTRACT_V1, None),
        (store_module._OBSERVATION_REVISION_CONTRACT_V2, _at(11)),
    ),
)
async def test_store_rejects_valid_legacy_revision_identities_on_non_singleton_records(
    contract_version: str,
    source_available_at: datetime | None,
) -> None:
    """V1/V2 identities remain valid only for the migration's singleton key."""
    context = _multi_record_context()

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db, clock=lambda: _at(14))
        persisted = await store.persist_provider_result(
            context,
            _result(
                context=context,
                retrieved_at=_at(12),
                observations=(
                    _record_observation(
                        event_at=_at(10),
                        available_at=_at(11),
                        contract="IF2610C100",
                        close="10.00",
                    ),
                ),
            ),
            received_at=_at(12),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await db.commit()
        revision = await db.get(MdObservationRevision, persisted.observation_revision_ids[0])
        assert revision is not None
        legacy_identity = store_module._observation_revision_identity_sha256(
            contract_version=contract_version,
            series_semantic_key_sha256=MarketDataStore.series_identity(context).semantic_key_sha256,
            source_snapshot_id=revision.source_snapshot_id,
            event_at=_at(10),
            available_at=_at(12),
            fields_sha256=revision.fields_sha256,
            quality=store_module.ObservationQuality(revision.quality_status),
            revision_number=revision.revision_number,
            source_available_at=source_available_at,
        )
        await db.execute(
            update(MdObservationRevision)
            .where(MdObservationRevision.id == revision.id)
            .values(revision_key_sha256=legacy_identity)
            .execution_options(synchronize_session=False)
        )
        await db.commit()
        db.expire_all()

        with pytest.raises(MarketDataStoreError) as rejected:
            await store.read_observation_revisions(context, knowledge_cutoff=_at(15))

    assert rejected.value.code == "LOCAL_OBSERVATION_INTEGRITY"


@pytest.mark.asyncio
async def test_store_fails_closed_for_tampered_v3_semantic_record_key() -> None:
    """A forged key digest cannot retain a valid V3 revision identity on local read."""
    context = _multi_record_context()

    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        store = MarketDataStore(db, clock=lambda: _at(14))
        persisted = await store.persist_provider_result(
            context,
            _result(
                context=context,
                retrieved_at=_at(12),
                observations=(
                    _record_observation(
                        event_at=_at(10),
                        available_at=_at(11),
                        contract="IF2610C100",
                        close="10.00",
                    ),
                ),
            ),
            received_at=_at(12),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await db.execute(
            update(MdObservationRevision)
            .where(MdObservationRevision.id == persisted.observation_revision_ids[0])
            .values(semantic_record_key_sha256="0" * 64)
            .execution_options(synchronize_session=False)
        )
        await db.commit()
        db.expire_all()

        with pytest.raises(MarketDataStoreError) as rejected:
            await store.read_observation_revisions(context, knowledge_cutoff=_at(15))

    assert rejected.value.code == "LOCAL_OBSERVATION_INTEGRITY"
