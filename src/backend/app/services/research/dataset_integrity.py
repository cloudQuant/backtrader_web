"""Server-owned object attestations for protocol-v2 dataset snapshots.

The browser never supplies a storage URI, provider version, digest, or byte
count for an attested snapshot.  It supplies only a previously registered,
opaque receipt identifier.  A deployment-owned resolver turns that receipt
into these durable facts before the dataset registry persists them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from app.services.research.canonical import content_hash

_SHA256_HEX = re.compile(r"^[a-f0-9]{64}$")
_MAX_RECEIPT_ID_LENGTH = 256
_MAX_OBJECT_ID_LENGTH = 256
_MAX_VERSION_LENGTH = 512


@dataclass(frozen=True, slots=True)
class DatasetObjectAttestation:
    """One server-issued view of a controlled immutable dataset object."""

    receipt_id: str
    user_id: str
    logical_object_id: str
    object_version: str
    object_digest: str
    object_size_bytes: int
    storage_uri: str
    attested_at: datetime


class DatasetObjectResolver(Protocol):
    """Resolve server-registered dataset object facts without client assertions."""

    async def resolve_receipt(
        self,
        *,
        user_id: str,
        receipt_id: str,
    ) -> DatasetObjectAttestation:
        """Resolve an opaque ingestion/registered-object receipt for its owner."""

    async def resolve_current(
        self,
        *,
        user_id: str,
        logical_object_id: str,
    ) -> DatasetObjectAttestation:
        """Resolve the current server view of one stable logical object."""


class InMemoryDatasetObjectResolver:
    """Controlled local resolver for tests and non-production fixtures only."""

    def __init__(self) -> None:
        self._by_receipt: dict[tuple[str, str], DatasetObjectAttestation] = {}
        self._current_by_object: dict[tuple[str, str], DatasetObjectAttestation] = {}

    def register(
        self,
        attestation: DatasetObjectAttestation,
        *,
        make_current: bool = True,
    ) -> DatasetObjectAttestation:
        """Register a fixture attestation and optionally advance its current object view."""

        normalized = normalize_object_attestation(attestation)
        receipt_key = (normalized.user_id, normalized.receipt_id)
        existing = self._by_receipt.get(receipt_key)
        if existing is not None and existing != normalized:
            raise ValueError("DATASET_OBJECT_RECEIPT_CONFLICT")
        self._by_receipt[receipt_key] = normalized
        if make_current:
            self._current_by_object[(normalized.user_id, normalized.logical_object_id)] = normalized
        return normalized

    async def resolve_receipt(
        self,
        *,
        user_id: str,
        receipt_id: str,
    ) -> DatasetObjectAttestation:
        """Return an owner-scoped receipt or fail closed without cross-owner disclosure."""

        attestation = self._by_receipt.get((user_id, receipt_id))
        if attestation is None:
            raise ValueError("DATASET_OBJECT_RECEIPT_NOT_FOUND")
        return attestation

    async def resolve_current(
        self,
        *,
        user_id: str,
        logical_object_id: str,
    ) -> DatasetObjectAttestation:
        """Return the current owner-scoped object identity or fail closed."""

        attestation = self._current_by_object.get((user_id, logical_object_id))
        if attestation is None:
            raise ValueError("DATASET_OBJECT_REVALIDATION_NOT_FOUND")
        return attestation


def normalize_object_attestation(
    attestation: DatasetObjectAttestation,
    *,
    expected_user_id: str | None = None,
) -> DatasetObjectAttestation:
    """Validate and UTC-normalize a server resolver response before persistence."""

    if not isinstance(attestation, DatasetObjectAttestation):
        raise ValueError("DATASET_OBJECT_ATTESTATION_INVALID")
    if expected_user_id is not None and attestation.user_id != expected_user_id:
        raise ValueError("DATASET_OBJECT_ATTESTATION_OWNER_MISMATCH")
    if not _bounded_identifier(attestation.receipt_id, _MAX_RECEIPT_ID_LENGTH):
        raise ValueError("DATASET_OBJECT_ATTESTATION_INVALID")
    if not _bounded_identifier(attestation.user_id, _MAX_OBJECT_ID_LENGTH):
        raise ValueError("DATASET_OBJECT_ATTESTATION_INVALID")
    if not _bounded_identifier(attestation.logical_object_id, _MAX_OBJECT_ID_LENGTH):
        raise ValueError("DATASET_OBJECT_ATTESTATION_INVALID")
    if not _bounded_identifier(attestation.object_version, _MAX_VERSION_LENGTH):
        raise ValueError("DATASET_OBJECT_ATTESTATION_INVALID")
    if (
        not isinstance(attestation.object_digest, str)
        or _SHA256_HEX.fullmatch(attestation.object_digest) is None
    ):
        raise ValueError("DATASET_OBJECT_ATTESTATION_INVALID")
    if type(attestation.object_size_bytes) is not int or attestation.object_size_bytes < 0:
        raise ValueError("DATASET_OBJECT_ATTESTATION_INVALID")
    if not isinstance(attestation.storage_uri, str) or not attestation.storage_uri.strip():
        raise ValueError("DATASET_OBJECT_ATTESTATION_INVALID")
    return DatasetObjectAttestation(
        receipt_id=attestation.receipt_id,
        user_id=attestation.user_id,
        logical_object_id=attestation.logical_object_id,
        object_version=attestation.object_version,
        object_digest=attestation.object_digest,
        object_size_bytes=attestation.object_size_bytes,
        storage_uri=attestation.storage_uri,
        attested_at=_as_utc(attestation.attested_at),
    )


def object_attestation_receipt_hash(attestation: DatasetObjectAttestation) -> str:
    """Hash the complete resolver attestation without exposing its storage reference."""

    normalized = normalize_object_attestation(attestation)
    return content_hash(
        {
            "schema_version": "dataset-object-attestation-v1",
            "receipt_id": normalized.receipt_id,
            "user_id": normalized.user_id,
            "logical_object_id": normalized.logical_object_id,
            "object_version": normalized.object_version,
            "object_digest": normalized.object_digest,
            "object_size_bytes": normalized.object_size_bytes,
            "storage_uri": normalized.storage_uri,
            "attested_at": normalized.attested_at,
        }
    )


def _bounded_identifier(value: object, maximum_length: int) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum_length


def _as_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("DATASET_OBJECT_ATTESTATION_TIMESTAMP_INVALID")
    return value.astimezone(timezone.utc)
