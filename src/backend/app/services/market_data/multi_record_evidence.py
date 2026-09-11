"""Durable server-owned evidence for internal B2 completeness selectors.

A generic ``B2SliceSelector`` or ``B2ReportSelector`` is only an in-memory
planning value.  This module is the narrow bridge from reviewed family
dimensions to an immutable database receipt, its member manifest, and a
pending visibility receipt.  It deliberately has no public query DTO,
provider adapter, scheduler, route registration, or network capability.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data_platform import (
    MdB2CompletenessManifestEntry,
    MdB2CompletenessReceipt,
    MdDataSeries,
    MdObservationRevision,
    MdSourceSnapshot,
)
from app.services.market_data.multi_record import (
    B2ReportSelector,
    B2SliceSelector,
    normalize_record_dimensions,
)
from app.services.market_data.multi_record_contracts import (
    B2FamilyContractError,
    get_b2_family_contract,
    issue_b2_selector,
    normalize_b2_selector_dimensions,
)

if TYPE_CHECKING:
    from app.services.market_data.publication import MarketDataPublicationManager

UTC = timezone.utc
_B2_COMPLETENESS_RECEIPT_CONTRACT_VERSION = "market-data-b2-completeness-receipt-v1"
_MAX_EVIDENCE_BYTES = 16 * 1024
_SHA256_CHARS = frozenset("0123456789abcdef")


class B2CompletenessEvidenceError(ValueError):
    """Stable rejection for an unsafe B2 durable evidence transition."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class B2CompletenessEvidenceRequest:
    """Input to server-owned issuance of one exact B2 completeness receipt.

    ``expected_record_dimensions`` intentionally contains reviewed business
    dimensions rather than caller-provided semantic hashes.  For zero results,
    the issuer receives a structured attestation and retains only its derived
    digest, never a caller-supplied digest or a raw payload.
    """

    series_id: str
    source_snapshot_id: str
    family_id: str
    family_contract_version: str
    event_at: datetime
    selector_dimensions: Mapping[str, object]
    expected_record_dimensions: Iterable[Mapping[str, object]]
    zero_record_evidence: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class StagedB2CompletenessEvidence:
    """IDs and frozen selector returned after transaction-A evidence staging."""

    receipt_id: str
    publication_id: str
    receipt_sha256: str
    selector: B2SliceSelector | B2ReportSelector
    event_at: datetime
    source_snapshot_id: str


class B2CompletenessEvidenceIssuer:
    """Stage immutable B2 manifest receipts in a caller-owned transaction."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def stage(
        self,
        request: B2CompletenessEvidenceRequest,
        *,
        publications: MarketDataPublicationManager | None = None,
    ) -> StagedB2CompletenessEvidence:
        """Derive, prove, and stage one selector receipt without publishing it.

        The associated source facts must equal the expected semantic-key set at
        the exact event coordinate.  A zero selector instead requires a
        nonempty server-hashed evidence object and proves no same-source fact
        exists at that coordinate.  The caller commits transaction A; normal
        post-commit publication remains the existing transaction-B protocol.
        """
        if not isinstance(request, B2CompletenessEvidenceRequest):
            raise TypeError("request must be a B2CompletenessEvidenceRequest")
        series_id = _require_identifier(request.series_id, code="B2_COMPLETENESS_SERIES_INVALID")
        source_snapshot_id = _require_identifier(
            request.source_snapshot_id,
            code="B2_COMPLETENESS_SOURCE_INVALID",
        )
        event_at = _require_event_at(request.event_at)
        try:
            contract = get_b2_family_contract(
                request.family_id,
                request.family_contract_version,
            )
            selector = issue_b2_selector(
                family_id=contract.family_id,
                family_contract_version=contract.family_contract_version,
                selector_dimensions=request.selector_dimensions,
                expected_record_dimensions=request.expected_record_dimensions,
            )
        except B2FamilyContractError as exc:
            raise B2CompletenessEvidenceError(exc.code) from exc
        except (TypeError, ValueError) as exc:
            raise B2CompletenessEvidenceError("B2_COMPLETENESS_REQUEST_INVALID") from exc

        zero_evidence_sha256 = _zero_evidence_sha256(
            expected_record_count=len(selector.expected_record_key_sha256s or ()),
            zero_record_evidence=request.zero_record_evidence,
        )
        expected_hashes = tuple(sorted(selector.expected_record_key_sha256s or ()))
        manifest_sha256 = _manifest_sha256(expected_hashes)

        series = await self._locked_series(series_id)
        await self._locked_source_snapshot(source_snapshot_id)
        _assert_series_family_binding(
            series,
            family_id=contract.family_id,
            family_contract_version=contract.family_contract_version,
        )
        await assert_b2_source_event_manifest_integrity(
            self._db,
            series_id=series_id,
            source_snapshot_id=source_snapshot_id,
            event_at=event_at,
            expected_hashes=expected_hashes,
        )

        selector_dimensions = dict(
            normalize_b2_selector_dimensions(
                family_id=contract.family_id,
                family_contract_version=contract.family_contract_version,
                dimensions=request.selector_dimensions,
            )
        )
        receipt_sha256 = _receipt_sha256(
            series_id=series_id,
            source_snapshot_id=source_snapshot_id,
            family_id=contract.family_id,
            family_contract_version=contract.family_contract_version,
            selector_kind=contract.selector_kind,
            event_at=event_at,
            selector_dimensions=selector_dimensions,
            selector_digest=selector.selector_digest,
            manifest_sha256=manifest_sha256,
            expected_hashes=expected_hashes,
            zero_record_evidence_sha256=zero_evidence_sha256,
        )
        receipt = await self._create_or_reuse_receipt(
            series_id=series_id,
            source_snapshot_id=source_snapshot_id,
            family_id=contract.family_id,
            family_contract_version=contract.family_contract_version,
            selector_kind=contract.selector_kind,
            event_at=event_at,
            selector_dimensions=selector_dimensions,
            selector_digest=selector.selector_digest,
            manifest_sha256=manifest_sha256,
            expected_hashes=expected_hashes,
            zero_record_evidence_sha256=zero_evidence_sha256,
            receipt_sha256=receipt_sha256,
        )
        if publications is None:
            # The local import prevents the shared publication module from
            # gaining an import cycle when it independently recomputes B2
            # receipt integrity during pending-receipt recovery.
            from app.services.market_data.publication import MarketDataPublicationManager

            publications = MarketDataPublicationManager(self._db)
        from app.services.market_data.publication import PUBLICATION_B2_COMPLETENESS_RECEIPT

        publication = await publications.stage(
            entity_type=PUBLICATION_B2_COMPLETENESS_RECEIPT,
            entity_id=receipt.id,
            entity_sha256=receipt.receipt_sha256,
        )
        return StagedB2CompletenessEvidence(
            receipt_id=receipt.id,
            publication_id=publication.id,
            receipt_sha256=receipt.receipt_sha256,
            selector=selector,
            event_at=event_at,
            source_snapshot_id=source_snapshot_id,
        )

    async def _locked_series(self, series_id: str) -> MdDataSeries:
        series = await self._db.scalar(
            select(MdDataSeries)
            .where(MdDataSeries.id == series_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if series is None:
            raise B2CompletenessEvidenceError("B2_COMPLETENESS_SERIES_NOT_FOUND")
        return series

    async def _locked_source_snapshot(self, source_snapshot_id: str) -> None:
        source_snapshot = await self._db.scalar(
            select(MdSourceSnapshot.id)
            .where(MdSourceSnapshot.id == source_snapshot_id)
            .with_for_update()
        )
        if source_snapshot is None:
            raise B2CompletenessEvidenceError("B2_COMPLETENESS_SOURCE_NOT_FOUND")

    async def _create_or_reuse_receipt(
        self,
        *,
        series_id: str,
        source_snapshot_id: str,
        family_id: str,
        family_contract_version: str,
        selector_kind: str,
        event_at: datetime,
        selector_dimensions: Mapping[str, object],
        selector_digest: str,
        manifest_sha256: str,
        expected_hashes: Sequence[str],
        zero_record_evidence_sha256: str | None,
        receipt_sha256: str,
    ) -> MdB2CompletenessReceipt:
        existing = await self._db.scalar(
            select(MdB2CompletenessReceipt)
            .where(
                MdB2CompletenessReceipt.series_id == series_id,
                MdB2CompletenessReceipt.event_at == event_at,
                MdB2CompletenessReceipt.selector_digest == selector_digest,
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if existing is not None:
            await self._assert_existing_receipt(
                existing,
                source_snapshot_id=source_snapshot_id,
                family_id=family_id,
                family_contract_version=family_contract_version,
                selector_kind=selector_kind,
                event_at=event_at,
                selector_dimensions=selector_dimensions,
                selector_digest=selector_digest,
                manifest_sha256=manifest_sha256,
                expected_hashes=expected_hashes,
                zero_record_evidence_sha256=zero_record_evidence_sha256,
                receipt_sha256=receipt_sha256,
            )
            return existing

        receipt = MdB2CompletenessReceipt(
            series_id=series_id,
            source_snapshot_id=source_snapshot_id,
            family_id=family_id,
            family_contract_version=family_contract_version,
            selector_kind=selector_kind,
            event_at=event_at,
            selector_dimensions_json=dict(selector_dimensions),
            selector_digest=selector_digest,
            manifest_sha256=manifest_sha256,
            expected_record_count=len(expected_hashes),
            zero_record_evidence_sha256=zero_record_evidence_sha256,
            receipt_sha256=receipt_sha256,
        )
        self._db.add(receipt)
        try:
            await self._db.flush()
            self._db.add_all(
                MdB2CompletenessManifestEntry(
                    receipt_id=receipt.id,
                    semantic_record_key_sha256=semantic_record_key_sha256,
                )
                for semantic_record_key_sha256 in expected_hashes
            )
            await self._db.flush()
        except IntegrityError as exc:
            raise B2CompletenessEvidenceError("B2_COMPLETENESS_RECEIPT_WRITE_CONFLICT") from exc
        return receipt

    async def _assert_existing_receipt(
        self,
        receipt: MdB2CompletenessReceipt,
        *,
        source_snapshot_id: str,
        family_id: str,
        family_contract_version: str,
        selector_kind: str,
        event_at: datetime,
        selector_dimensions: Mapping[str, object],
        selector_digest: str,
        manifest_sha256: str,
        expected_hashes: Sequence[str],
        zero_record_evidence_sha256: str | None,
        receipt_sha256: str,
    ) -> None:
        entries = tuple(
            (
                await self._db.execute(
                    select(MdB2CompletenessManifestEntry.semantic_record_key_sha256)
                    .where(MdB2CompletenessManifestEntry.receipt_id == receipt.id)
                    .order_by(MdB2CompletenessManifestEntry.semantic_record_key_sha256)
                    .with_for_update()
                )
            ).scalars()
        )
        if (
            receipt.source_snapshot_id != source_snapshot_id
            or receipt.family_id != family_id
            or receipt.family_contract_version != family_contract_version
            or receipt.selector_kind != selector_kind
            or _stored_utc(receipt.event_at) != event_at
            or _canonical_json(receipt.selector_dimensions_json)
            != _canonical_json(selector_dimensions)
            or receipt.selector_digest != selector_digest
            or receipt.manifest_sha256 != manifest_sha256
            or receipt.expected_record_count != len(expected_hashes)
            or receipt.zero_record_evidence_sha256 != zero_record_evidence_sha256
            or receipt.receipt_sha256 != receipt_sha256
            or entries != tuple(expected_hashes)
        ):
            raise B2CompletenessEvidenceError("B2_COMPLETENESS_RECEIPT_CONFLICT")


def assert_b2_completeness_receipt_integrity(
    receipt: MdB2CompletenessReceipt,
    entry_hashes: Iterable[str],
) -> B2SliceSelector | B2ReportSelector:
    """Recompute a persisted receipt before it can become point-in-time visible.

    ``MdPublication``'s generic entity hash check validates the parent digest.
    This function additionally binds that digest to child manifest members,
    exact family contract, selector, zero evidence state, and receipt payload.
    It is deliberately pure so publication recovery can call it under locks.
    """
    if not isinstance(receipt, MdB2CompletenessReceipt):
        raise TypeError("receipt must be an MdB2CompletenessReceipt")
    try:
        contract = get_b2_family_contract(receipt.family_id, receipt.family_contract_version)
        if receipt.selector_kind != contract.selector_kind:
            raise B2CompletenessEvidenceError("B2_COMPLETENESS_RECEIPT_INVALID")
        selector_dimensions = dict(
            normalize_b2_selector_dimensions(
                family_id=contract.family_id,
                family_contract_version=contract.family_contract_version,
                dimensions=receipt.selector_dimensions_json,
            )
        )
        event_at = _stored_utc(receipt.event_at)
        series_id = _require_identifier(receipt.series_id, code="B2_COMPLETENESS_RECEIPT_INVALID")
        source_snapshot_id = _require_identifier(
            receipt.source_snapshot_id,
            code="B2_COMPLETENESS_RECEIPT_INVALID",
        )
        hashes = _normalize_entry_hashes(entry_hashes)
        expected_count = receipt.expected_record_count
        if (
            not isinstance(expected_count, int)
            or isinstance(expected_count, bool)
            or expected_count != len(hashes)
        ):
            raise B2CompletenessEvidenceError("B2_COMPLETENESS_RECEIPT_INVALID")
        zero_evidence_sha256 = receipt.zero_record_evidence_sha256
        if expected_count == 0:
            if not _is_sha256(zero_evidence_sha256):
                raise B2CompletenessEvidenceError("B2_COMPLETENESS_RECEIPT_INVALID")
        elif zero_evidence_sha256 is not None:
            raise B2CompletenessEvidenceError("B2_COMPLETENESS_RECEIPT_INVALID")
        selector = _selector_from_receipt(
            family_id=contract.family_id,
            family_contract_version=contract.family_contract_version,
            selector_kind=contract.selector_kind,
            selector_dimensions=selector_dimensions,
            expected_hashes=hashes,
        )
        manifest_sha256 = _manifest_sha256(hashes)
        expected_receipt_sha256 = _receipt_sha256(
            series_id=series_id,
            source_snapshot_id=source_snapshot_id,
            family_id=contract.family_id,
            family_contract_version=contract.family_contract_version,
            selector_kind=contract.selector_kind,
            event_at=event_at,
            selector_dimensions=selector_dimensions,
            selector_digest=selector.selector_digest,
            manifest_sha256=manifest_sha256,
            expected_hashes=hashes,
            zero_record_evidence_sha256=zero_evidence_sha256,
        )
        if (
            receipt.selector_digest != selector.selector_digest
            or receipt.manifest_sha256 != manifest_sha256
            or receipt.receipt_sha256 != expected_receipt_sha256
        ):
            raise B2CompletenessEvidenceError("B2_COMPLETENESS_RECEIPT_INVALID")
        return selector
    except B2FamilyContractError as exc:
        raise B2CompletenessEvidenceError("B2_COMPLETENESS_RECEIPT_INVALID") from exc
    except (TypeError, ValueError) as exc:
        raise B2CompletenessEvidenceError("B2_COMPLETENESS_RECEIPT_INVALID") from exc


async def assert_b2_source_event_manifest_integrity(
    db: AsyncSession,
    *,
    series_id: str,
    source_snapshot_id: str,
    event_at: datetime,
    expected_hashes: Iterable[str],
) -> None:
    """Require the current exact source-event key set to equal a B2 manifest.

    Issuance checks this before creating a receipt, while publication and
    strict readers repeat it before trusting durable evidence.  The source
    snapshot boundary is mandatory: revisions from a later receipt must never
    complete, replace, or invalidate an earlier selector manifest.
    """
    if not isinstance(db, AsyncSession):
        raise TypeError("db must be an AsyncSession")
    normalized_series_id = _require_identifier(
        series_id,
        code="B2_COMPLETENESS_RECEIPT_INVALID",
    )
    normalized_source_snapshot_id = _require_identifier(
        source_snapshot_id,
        code="B2_COMPLETENESS_RECEIPT_INVALID",
    )
    normalized_event_at = _require_event_at(event_at)
    normalized_expected_hashes = _normalize_entry_hashes(expected_hashes)
    rows = tuple(
        (
            await db.execute(
                select(MdObservationRevision.semantic_record_key_sha256)
                .where(
                    MdObservationRevision.series_id == normalized_series_id,
                    MdObservationRevision.source_snapshot_id == normalized_source_snapshot_id,
                    MdObservationRevision.event_time == normalized_event_at,
                )
                .order_by(MdObservationRevision.semantic_record_key_sha256)
                .with_for_update()
            )
        ).scalars()
    )
    if rows != normalized_expected_hashes:
        raise B2CompletenessEvidenceError("B2_COMPLETENESS_SOURCE_RECORDS_MISMATCH")


def _assert_series_family_binding(
    series: MdDataSeries,
    *,
    family_id: str,
    family_contract_version: str,
) -> None:
    identity = series.semantic_identity_json
    if not isinstance(identity, Mapping) or (
        identity.get("family_id") != family_id
        or identity.get("family_contract_version") != family_contract_version
    ):
        raise B2CompletenessEvidenceError("B2_COMPLETENESS_SERIES_FAMILY_MISMATCH")


def _selector_from_receipt(
    *,
    family_id: str,
    family_contract_version: str,
    selector_kind: str,
    selector_dimensions: Mapping[str, object],
    expected_hashes: Sequence[str],
) -> B2SliceSelector | B2ReportSelector:
    kwargs = {
        "family_id": family_id,
        "family_contract_version": family_contract_version,
        "selector_dimensions": selector_dimensions,
        "expected_record_key_sha256s": expected_hashes,
    }
    if selector_kind == "slice":
        return B2SliceSelector(**kwargs)
    if selector_kind == "report":
        return B2ReportSelector(**kwargs)
    raise B2CompletenessEvidenceError("B2_COMPLETENESS_RECEIPT_INVALID")


def _normalize_entry_hashes(value: Iterable[str]) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise B2CompletenessEvidenceError("B2_COMPLETENESS_RECEIPT_INVALID")
    hashes = tuple(sorted(value))
    if (
        len(hashes) > 50_000
        or len(set(hashes)) != len(hashes)
        or any(not _is_sha256(item) for item in hashes)
    ):
        raise B2CompletenessEvidenceError("B2_COMPLETENESS_RECEIPT_INVALID")
    return hashes


def _zero_evidence_sha256(
    *,
    expected_record_count: int,
    zero_record_evidence: Mapping[str, object] | None,
) -> str | None:
    if expected_record_count > 0:
        if zero_record_evidence is not None:
            raise B2CompletenessEvidenceError("B2_ZERO_RECORD_EVIDENCE_UNEXPECTED")
        return None
    if zero_record_evidence is None:
        raise B2CompletenessEvidenceError("B2_ZERO_RECORD_EVIDENCE_REQUIRED")
    try:
        normalized = normalize_record_dimensions(zero_record_evidence)
    except (TypeError, ValueError) as exc:
        raise B2CompletenessEvidenceError("B2_ZERO_RECORD_EVIDENCE_INVALID") from exc
    return _sha256(_canonical_json(dict(normalized)))


def _manifest_sha256(expected_hashes: Sequence[str]) -> str:
    return _sha256(
        _canonical_json(
            {
                "b2_completeness_manifest_contract_version": _B2_COMPLETENESS_RECEIPT_CONTRACT_VERSION,
                "expected_record_key_sha256s": list(expected_hashes),
            }
        )
    )


def _receipt_sha256(
    *,
    series_id: str,
    source_snapshot_id: str,
    family_id: str,
    family_contract_version: str,
    selector_kind: str,
    event_at: datetime,
    selector_dimensions: Mapping[str, object],
    selector_digest: str,
    manifest_sha256: str,
    expected_hashes: Sequence[str],
    zero_record_evidence_sha256: str | None,
) -> str:
    return _sha256(
        _canonical_json(
            {
                "b2_completeness_receipt_contract_version": _B2_COMPLETENESS_RECEIPT_CONTRACT_VERSION,
                "series_id": series_id,
                "source_snapshot_id": source_snapshot_id,
                "family_id": family_id,
                "family_contract_version": family_contract_version,
                "selector_kind": selector_kind,
                "event_at": event_at.isoformat(),
                "selector_dimensions": dict(selector_dimensions),
                "selector_digest": selector_digest,
                "manifest_sha256": manifest_sha256,
                "expected_record_count": len(expected_hashes),
                "expected_record_key_sha256s": list(expected_hashes),
                "zero_record_evidence_sha256": zero_record_evidence_sha256,
            }
        )
    )


def _canonical_json(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise B2CompletenessEvidenceError("B2_COMPLETENESS_RECEIPT_INVALID") from exc
    if len(encoded.encode("utf-8")) > _MAX_EVIDENCE_BYTES:
        raise B2CompletenessEvidenceError("B2_COMPLETENESS_RECEIPT_INVALID")
    return encoded


def _require_identifier(value: object, *, code: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 36:
        raise B2CompletenessEvidenceError(code)
    return value


def _require_event_at(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise B2CompletenessEvidenceError("B2_COMPLETENESS_EVENT_AT_INVALID")
    return value.astimezone(UTC)


def _stored_utc(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise B2CompletenessEvidenceError("B2_COMPLETENESS_RECEIPT_INVALID")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _SHA256_CHARS for character in value)
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
