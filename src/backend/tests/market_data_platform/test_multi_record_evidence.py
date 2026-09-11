"""Server-owned issuance contracts for B2 durable completeness evidence."""

from __future__ import annotations

import hashlib
from datetime import datetime

import pytest
from sqlalchemy import delete, func, select, update

from app.db.database import async_session_maker
from app.models.market_data_platform import (
    MdB2CompletenessManifestEntry,
    MdB2CompletenessReceipt,
    MdObservationRevision,
    MdPublication,
)
from app.services.market_data.multi_record_evidence import (
    B2CompletenessEvidenceError,
    B2CompletenessEvidenceIssuer,
    B2CompletenessEvidenceRequest,
)
from app.services.market_data.publication import (
    PUBLICATION_B2_COMPLETENESS_RECEIPT,
    MarketDataPublicationError,
    MarketDataPublicationManager,
)
from app.services.market_data.store import (
    UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
    MarketDataStore,
)
from tests.market_data_platform.test_multi_record_store import (
    _multi_record_context,
    _record_observation,
)
from tests.market_data_platform.test_store import _at, _result, _seed_dataset_and_provider


def _option_dimensions(*, strike: str = "100") -> dict[str, object]:
    return {
        "underlying_canonical_id": "instrument:futures:cn:IF",
        "contract_canonical_id": f"instrument:option:cn:IF2610C{strike}",
        "expiry": "2026-10-30",
        "strike": strike,
        "right": "call",
    }


async def _persist_b2_source(*, strikes: tuple[str, ...] = ("100",)) -> tuple[str, str]:
    """Persist one source receipt whose observations can become a B2 manifest."""
    context = _multi_record_context()
    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        persisted = await MarketDataStore(db, clock=lambda: _at(14)).persist_provider_result(
            context,
            _result(
                context=context,
                retrieved_at=_at(12),
                observations=tuple(
                    _record_observation(
                        event_at=_at(10),
                        available_at=_at(11),
                        contract=f"instrument:option:cn:IF2610C{strike}",
                        close=f"{index + 10}.00",
                    )
                    for index, strike in enumerate(strikes)
                ),
            ),
            received_at=_at(12),
            unverified_compatibility_reason=UNVERIFIED_COMPATIBILITY_REASON_LEGACY_IMPORT,
        )
        await db.commit()
        return persisted.series_id, persisted.source_snapshot_id


def _request(
    *,
    series_id: str,
    source_snapshot_id: str,
    expected_record_dimensions: tuple[dict[str, object], ...] = (_option_dimensions(),),
    event_at: datetime | None = None,
    zero_record_evidence: dict[str, object] | None = None,
) -> B2CompletenessEvidenceRequest:
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
        expected_record_dimensions=expected_record_dimensions,
        zero_record_evidence=zero_record_evidence,
    )


@pytest.mark.asyncio
async def test_issuer_derives_one_durable_manifest_receipt_and_stages_its_publication() -> None:
    """Callers submit reviewed dimensions; hashes and visibility receipt are server-owned."""
    series_id, source_snapshot_id = await _persist_b2_source()

    async with async_session_maker() as db:
        staged = await B2CompletenessEvidenceIssuer(db).stage(
            _request(series_id=series_id, source_snapshot_id=source_snapshot_id)
        )
        await db.commit()
        receipt = await db.get(MdB2CompletenessReceipt, staged.receipt_id)
        entries = list(
            (
                await db.execute(
                    select(MdB2CompletenessManifestEntry).where(
                        MdB2CompletenessManifestEntry.receipt_id == staged.receipt_id
                    )
                )
            ).scalars()
        )
        publication = await db.get(MdPublication, staged.publication_id)

    assert receipt is not None
    assert receipt.expected_record_count == 1
    assert receipt.zero_record_evidence_sha256 is None
    assert receipt.selector_digest == staged.selector.selector_digest
    assert len(entries) == 1
    assert publication is not None
    assert publication.entity_type == PUBLICATION_B2_COMPLETENESS_RECEIPT
    assert publication.entity_id == receipt.id
    assert publication.entity_sha256 == receipt.receipt_sha256
    assert publication.published_at is None


@pytest.mark.asyncio
async def test_issuer_reuses_an_exact_receipt_and_its_pending_publication() -> None:
    """A retry does not create another manifest or visibility receipt for one selector."""
    series_id, source_snapshot_id = await _persist_b2_source()

    async with async_session_maker() as db:
        issuer = B2CompletenessEvidenceIssuer(db)
        first = await issuer.stage(
            _request(series_id=series_id, source_snapshot_id=source_snapshot_id)
        )
        second = await issuer.stage(
            _request(series_id=series_id, source_snapshot_id=source_snapshot_id)
        )
        await db.commit()
        receipt_count = await db.scalar(select(func.count()).select_from(MdB2CompletenessReceipt))
        publication_count = await db.scalar(
            select(func.count())
            .select_from(MdPublication)
            .where(MdPublication.entity_type == PUBLICATION_B2_COMPLETENESS_RECEIPT)
        )

    assert second.receipt_id == first.receipt_id
    assert second.publication_id == first.publication_id
    assert receipt_count == 1
    assert publication_count == 1


@pytest.mark.asyncio
async def test_issuer_rejects_a_manifest_that_does_not_exactly_match_its_source_event() -> None:
    """A receipt cannot hide an additional same-source record behind a smaller manifest."""
    series_id, source_snapshot_id = await _persist_b2_source(strikes=("100", "105"))

    async with async_session_maker() as db:
        with pytest.raises(B2CompletenessEvidenceError) as rejected:
            await B2CompletenessEvidenceIssuer(db).stage(
                _request(series_id=series_id, source_snapshot_id=source_snapshot_id)
            )
        receipt_count = await db.scalar(select(func.count()).select_from(MdB2CompletenessReceipt))

    assert rejected.value.code == "B2_COMPLETENESS_SOURCE_RECORDS_MISMATCH"
    assert receipt_count == 0


@pytest.mark.asyncio
async def test_issuer_requires_server_hashed_zero_evidence_for_an_empty_exact_event() -> None:
    """A zero result must bind a nonempty server-hashed attestation to its selector/event."""
    series_id, source_snapshot_id = await _persist_b2_source()

    async with async_session_maker() as db:
        issuer = B2CompletenessEvidenceIssuer(db)
        with pytest.raises(B2CompletenessEvidenceError) as missing_evidence:
            await issuer.stage(
                _request(
                    series_id=series_id,
                    source_snapshot_id=source_snapshot_id,
                    expected_record_dimensions=(),
                    event_at=_at(11),
                )
            )

        staged = await issuer.stage(
            _request(
                series_id=series_id,
                source_snapshot_id=source_snapshot_id,
                expected_record_dimensions=(),
                event_at=_at(11),
                zero_record_evidence={"attestation": "no contracts reported"},
            )
        )
        await db.commit()
        receipt = await db.get(MdB2CompletenessReceipt, staged.receipt_id)

    assert missing_evidence.value.code == "B2_ZERO_RECORD_EVIDENCE_REQUIRED"
    assert receipt is not None
    assert receipt.expected_record_count == 0
    assert (
        receipt.zero_record_evidence_sha256
        == hashlib.sha256(b'{"attestation":"no contracts reported"}').hexdigest()
    )


@pytest.mark.asyncio
async def test_pending_receipt_publication_rejects_a_raw_sql_manifest_entry_tamper() -> None:
    """Publication recovery recomputes immutable evidence, including child members."""
    series_id, source_snapshot_id = await _persist_b2_source()

    async with async_session_maker() as db:
        staged = await B2CompletenessEvidenceIssuer(db).stage(
            _request(series_id=series_id, source_snapshot_id=source_snapshot_id)
        )
        await db.commit()
        db.add(
            MdB2CompletenessManifestEntry(
                receipt_id=staged.receipt_id,
                semantic_record_key_sha256="f" * 64,
            )
        )
        await db.commit()

        with pytest.raises(MarketDataPublicationError, match="PUBLICATION_ENTITY_INTEGRITY"):
            await MarketDataPublicationManager(db).recover_pending()


@pytest.mark.asyncio
async def test_pending_receipt_publication_rejects_a_raw_sql_parent_semantic_tamper() -> None:
    """Recovery recomputes the parent payload instead of trusting its stored digest."""
    series_id, source_snapshot_id = await _persist_b2_source()

    async with async_session_maker() as db:
        staged = await B2CompletenessEvidenceIssuer(db).stage(
            _request(series_id=series_id, source_snapshot_id=source_snapshot_id)
        )
        await db.commit()
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

        with pytest.raises(MarketDataPublicationError, match="PUBLICATION_ENTITY_INTEGRITY"):
            await MarketDataPublicationManager(db).recover_pending()


@pytest.mark.asyncio
async def test_direct_receipt_publication_rejects_a_raw_sql_manifest_tamper() -> None:
    """The normal publish path has the same deep B2 integrity guard as recovery."""
    series_id, source_snapshot_id = await _persist_b2_source()

    async with async_session_maker() as db:
        staged = await B2CompletenessEvidenceIssuer(db).stage(
            _request(series_id=series_id, source_snapshot_id=source_snapshot_id)
        )
        await db.commit()
        db.add(
            MdB2CompletenessManifestEntry(
                receipt_id=staged.receipt_id,
                semantic_record_key_sha256="f" * 64,
            )
        )
        await db.commit()

        with pytest.raises(MarketDataPublicationError, match="PUBLICATION_ENTITY_INTEGRITY"):
            await MarketDataPublicationManager(db).publish_staged((staged.publication_id,))


@pytest.mark.asyncio
async def test_direct_receipt_publication_rejects_a_raw_sql_source_event_tamper() -> None:
    """A manifest cannot publish after its exact source-event set was changed."""
    series_id, source_snapshot_id = await _persist_b2_source()

    async with async_session_maker() as db:
        staged = await B2CompletenessEvidenceIssuer(db).stage(
            _request(series_id=series_id, source_snapshot_id=source_snapshot_id)
        )
        await db.commit()
        await db.execute(
            delete(MdObservationRevision).where(
                MdObservationRevision.series_id == series_id,
                MdObservationRevision.source_snapshot_id == source_snapshot_id,
                MdObservationRevision.event_time == _at(10),
            )
        )
        await db.commit()

        with pytest.raises(MarketDataPublicationError, match="PUBLICATION_ENTITY_INTEGRITY"):
            await MarketDataPublicationManager(db).publish_staged((staged.publication_id,))


@pytest.mark.asyncio
async def test_direct_receipt_publication_seals_intact_exact_source_evidence() -> None:
    """An intact receipt can pass the same source-event proof and become visible."""
    series_id, source_snapshot_id = await _persist_b2_source()

    async with async_session_maker() as db:
        staged = await B2CompletenessEvidenceIssuer(db).stage(
            _request(series_id=series_id, source_snapshot_id=source_snapshot_id)
        )
        await db.commit()
        await MarketDataPublicationManager(db).publish_staged((staged.publication_id,))
        publication = await db.get(MdPublication, staged.publication_id)

    assert publication is not None
    assert publication.published_at is not None
    assert publication.visibility_sequence is not None
