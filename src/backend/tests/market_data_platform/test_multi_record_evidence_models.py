"""Durable internal evidence contracts for B2 multi-record completeness."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import update

from app.db.database import async_session_maker
from app.models.market_data_platform import (
    ImmutableMarketDataRecordError,
    MdB2CompletenessManifestEntry,
    MdB2CompletenessReceipt,
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

UTC = timezone.utc


def _digest(label: str) -> str:
    """Return a stable shape-only test digest without provider evidence."""
    return label * 64


async def _persist_source_receipt() -> tuple[str, str]:
    """Create a local B2 fact receipt used only as an evidence parent fixture."""
    context = _multi_record_context()
    async with async_session_maker() as db:
        await _seed_dataset_and_provider(db)
        persisted = await MarketDataStore(db, clock=lambda: _at(14)).persist_provider_result(
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
        return persisted.series_id, persisted.source_snapshot_id


def _receipt(*, series_id: str, source_snapshot_id: str) -> MdB2CompletenessReceipt:
    """Build one nonzero exact-manifest receipt before it is published."""
    return MdB2CompletenessReceipt(
        series_id=series_id,
        source_snapshot_id=source_snapshot_id,
        family_id="option.derivative",
        family_contract_version="market-data-family-v1",
        selector_kind="slice",
        event_at=datetime(2026, 9, 11, 10, tzinfo=UTC),
        selector_dimensions_json={
            "underlying_canonical_id": "instrument:futures:cn:IF",
            "expiry": "2026-10-30",
        },
        selector_digest=_digest("a"),
        manifest_sha256=_digest("b"),
        expected_record_count=1,
        zero_record_evidence_sha256=None,
        receipt_sha256=_digest("c"),
    )


def test_b2_completeness_models_expose_a_parent_child_immutable_evidence_shape() -> None:
    """Expected keys are durable child rows, never an unbounded JSON-only manifest."""
    receipt_columns = set(MdB2CompletenessReceipt.__table__.c.keys())
    entry_columns = set(MdB2CompletenessManifestEntry.__table__.c.keys())

    assert {
        "id",
        "series_id",
        "source_snapshot_id",
        "family_id",
        "family_contract_version",
        "selector_kind",
        "event_at",
        "selector_dimensions_json",
        "selector_digest",
        "manifest_sha256",
        "expected_record_count",
        "zero_record_evidence_sha256",
        "receipt_sha256",
        "created_at",
    } <= receipt_columns
    assert entry_columns == {"receipt_id", "semantic_record_key_sha256", "created_at"}
    assert "uq_md_b2_completeness_receipt_sha256" in {
        constraint.name
        for constraint in MdB2CompletenessReceipt.__table__.constraints
        if getattr(constraint, "name", None)
    }
    foreign_key = next(iter(MdB2CompletenessManifestEntry.__table__.foreign_keys))
    assert foreign_key.target_fullname == "md_b2_completeness_receipts.id"


@pytest.mark.asyncio
async def test_b2_completeness_receipt_is_immutable_and_publication_recovery_rechecks_its_hash() -> (
    None
):
    """A stale pending receipt cannot publish after raw SQL tampered its durable hash."""
    series_id, source_snapshot_id = await _persist_source_receipt()

    async with async_session_maker() as db:
        receipt = _receipt(series_id=series_id, source_snapshot_id=source_snapshot_id)
        db.add(receipt)
        await db.flush()
        db.add(
            MdB2CompletenessManifestEntry(
                receipt_id=receipt.id,
                semantic_record_key_sha256=_digest("d"),
            )
        )
        await MarketDataPublicationManager(db).stage(
            entity_type=PUBLICATION_B2_COMPLETENESS_RECEIPT,
            entity_id=receipt.id,
            entity_sha256=receipt.receipt_sha256,
        )
        receipt_id = receipt.id
        await db.commit()

        receipt.family_id = "option.risk_surface"
        with pytest.raises(ImmutableMarketDataRecordError):
            await db.flush()
        await db.rollback()

        await db.execute(
            update(MdB2CompletenessReceipt)
            .where(MdB2CompletenessReceipt.id == receipt_id)
            .values(receipt_sha256=_digest("e"))
        )
        await db.commit()

        with pytest.raises(MarketDataPublicationError, match="PUBLICATION_ENTITY_INTEGRITY"):
            await MarketDataPublicationManager(db).recover_pending()
