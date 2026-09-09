"""Operator-only import of versioned market-data master identities.

This module never exposes an HTTP write path. It validates one strict JSON
manifest, writes approved versions through the Iteration 197-only identity
writer, and lets the caller either commit the whole batch or roll it back.
``asset_instruments`` remains the identity authority, but generic Iteration
196 research writes never require the new local-first projection tables.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_research import AssetInstrument
from app.models.market_data_platform import MdInstrumentLookupKey
from app.schemas.asset_research import InstrumentIdentity
from app.services.market_data.master_data import (
    MarketDataIdentityWriteError,
    MarketDataIdentityWriter,
)
from app.services.market_data.publication import (
    MarketDataPublicationError,
)

MASTER_DATA_MANIFEST_VERSION = "market-data-master-v1"
MAX_MANIFEST_BYTES = 5 * 1024 * 1024
MAX_MANIFEST_IDENTITIES = 10_000


class MarketDataMasterDataImportError(RuntimeError):
    """A stable, non-secret error code for operator manifest handling."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class MarketDataMasterDataManifest(BaseModel):
    """Strict JSON envelope around the existing versioned identity DTO."""

    model_config = ConfigDict(extra="forbid")

    manifest_version: Literal[MASTER_DATA_MANIFEST_VERSION]
    identities: list[InstrumentIdentity] = Field(min_length=1, max_length=MAX_MANIFEST_IDENTITIES)


@dataclass(frozen=True, slots=True)
class _PreparedIdentity:
    """An input identity with its deterministic existing-version classification."""

    identity: InstrumentIdentity
    already_persisted: bool


@dataclass(frozen=True, slots=True)
class MarketDataMasterDataImportResult:
    """Safe aggregate output for one committed or dry-run manifest import."""

    manifest_sha256: str
    identity_count: int
    created_count: int
    reused_count: int
    lookup_key_count: int
    canonical_only_count: int
    asset_type_counts: dict[str, int]

    def as_dict(self) -> dict[str, object]:
        """Return only counts and a content fingerprint, never input or secret values."""
        return {
            "manifest_sha256": self.manifest_sha256,
            "identity_count": self.identity_count,
            "created_count": self.created_count,
            "reused_count": self.reused_count,
            "lookup_key_count": self.lookup_key_count,
            "canonical_only_count": self.canonical_only_count,
            "asset_type_counts": dict(sorted(self.asset_type_counts.items())),
        }


class MarketDataMasterDataImporter:
    """Run a strict, all-or-nothing identity import in a caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._identity_writer = MarketDataIdentityWriter(session)

    @property
    def staged_publication_ids(self) -> tuple[str, ...]:
        """Return pending post-commit identity receipts for this import batch."""
        return self._identity_writer.staged_publication_ids

    async def publish_staged(self) -> None:
        """Publish this import's frozen identities after the caller commits them."""
        ids = self.staged_publication_ids
        if not ids:
            return
        try:
            # Delegate through the owner of the staged-id list. It clears only
            # after the post-commit receipt transaction succeeds, so a reused
            # importer cannot indefinitely carry prior batches into later
            # publication attempts.
            await self._identity_writer.publish_staged()
        except MarketDataPublicationError as exc:
            raise MarketDataMasterDataImportError("MASTER_DATA_PUBLICATION_FAILED") from exc

    async def import_manifest(
        self,
        manifest: MarketDataMasterDataManifest,
        *,
        manifest_sha256: str,
    ) -> MarketDataMasterDataImportResult:
        """Persist every identity and materialize keys inside one nested transaction.

        A caller uses the same code path for ``--apply`` and dry-run.  A
        failed later entry rolls back all preceding manifest writes to the
        savepoint; a successful dry-run is then rolled back by the caller.
        """
        if not isinstance(manifest, MarketDataMasterDataManifest):
            raise TypeError("manifest must be a validated master-data manifest")
        if not _is_sha256(manifest_sha256):
            raise ValueError("manifest_sha256 must be a lowercase SHA-256 digest")

        await self._begin_root_transaction_if_needed()
        prepared = await self._preflight(manifest.identities)
        lookup_key_count = 0
        canonical_only_count = 0
        async with self._session.begin_nested():
            for entry in prepared:
                try:
                    record = await self._identity_writer.persist_identity(entry.identity)
                except MarketDataIdentityWriteError as exc:
                    raise MarketDataMasterDataImportError(exc.code) from exc
                has_lookup_key = await self._validate_materialization(record, entry.identity)
                if has_lookup_key:
                    lookup_key_count += 1
                else:
                    canonical_only_count += 1

        counts = Counter(entry.identity.asset_type for entry in prepared)
        reused_count = sum(entry.already_persisted for entry in prepared)
        return MarketDataMasterDataImportResult(
            manifest_sha256=manifest_sha256,
            identity_count=len(prepared),
            created_count=len(prepared) - reused_count,
            reused_count=reused_count,
            lookup_key_count=lookup_key_count,
            canonical_only_count=canonical_only_count,
            asset_type_counts=dict(counts),
        )

    async def _begin_root_transaction_if_needed(self) -> None:
        """Ensure a fresh SQLite session has a real transaction beneath a savepoint.

        SQLite treats a first savepoint as a complete transaction when no
        driver-level ``BEGIN`` has been issued. Releasing it would persist a
        supposed dry-run before the caller can roll back. Other supported
        dialects start their transaction through SQLAlchemy normally.
        """
        if self._session.in_transaction():
            return
        await self._session.begin()
        connection = await self._session.connection()
        if connection.dialect.name == "sqlite":
            await connection.exec_driver_sql("BEGIN")

    async def _preflight(
        self,
        identities: Sequence[InstrumentIdentity],
    ) -> tuple[_PreparedIdentity, ...]:
        """Reject duplicate or drifted versions before any batch DML begins."""
        seen: set[tuple[str, str]] = set()
        prepared: list[_PreparedIdentity] = []
        for identity in identities:
            key = (identity.canonical_id, identity.metadata_version)
            if key in seen:
                raise MarketDataMasterDataImportError(
                    "MASTER_DATA_IMPORT_DUPLICATE_MANIFEST_VERSION"
                )
            seen.add(key)
            rows = list(
                (
                    await self._session.execute(
                        select(AssetInstrument).where(
                            AssetInstrument.canonical_id == identity.canonical_id,
                            AssetInstrument.metadata_version == identity.metadata_version,
                        )
                    )
                )
                .scalars()
                .all()
            )
            if len(rows) > 1:
                raise MarketDataMasterDataImportError("MASTER_DATA_IMPORT_VERSION_INTEGRITY")
            existing = rows[0] if rows else None
            if existing is not None and not _matches_existing_identity(existing, identity):
                raise MarketDataMasterDataImportError(
                    "MASTER_DATA_IMPORT_EXISTING_VERSION_CONFLICT"
                )
            prepared.append(
                _PreparedIdentity(identity=identity, already_persisted=existing is not None)
            )
        return tuple(prepared)

    async def _validate_materialization(
        self,
        record: AssetInstrument,
        identity: InstrumentIdentity,
    ) -> bool:
        """Ensure the operator writer's lookup-key result fits the frozen identity."""
        rows = list(
            (
                await self._session.execute(
                    select(MdInstrumentLookupKey).where(
                        MdInstrumentLookupKey.instrument_id == record.id
                    )
                )
            )
            .scalars()
            .all()
        )
        if identity.venue is None:
            if rows:
                raise MarketDataMasterDataImportError(
                    "MASTER_DATA_IMPORT_CANONICAL_ONLY_KEY_CONFLICT"
                )
            return False
        if len(rows) != 1:
            raise MarketDataMasterDataImportError("MASTER_DATA_IMPORT_LOOKUP_KEY_MISSING")
        key = rows[0]
        if (
            key.asset_type != identity.asset_type
            or key.market != identity.venue
            or key.symbol != identity.display_symbol
            or key.canonical_id != identity.canonical_id
            or key.metadata_version != identity.metadata_version
        ):
            raise MarketDataMasterDataImportError("MASTER_DATA_IMPORT_LOOKUP_KEY_INTEGRITY")
        return True


def load_market_data_master_manifest(path: Path) -> tuple[MarketDataMasterDataManifest, str]:
    """Read and strictly validate one bounded JSON manifest from an operator path."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise MarketDataMasterDataImportError("MASTER_DATA_IMPORT_MANIFEST_UNREADABLE") from exc
    if size < 1 or size > MAX_MANIFEST_BYTES:
        raise MarketDataMasterDataImportError("MASTER_DATA_IMPORT_MANIFEST_SIZE_INVALID")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise MarketDataMasterDataImportError("MASTER_DATA_IMPORT_MANIFEST_UNREADABLE") from exc
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MarketDataMasterDataImportError("MASTER_DATA_IMPORT_MANIFEST_INVALID_JSON") from exc
    if not isinstance(payload, Mapping):
        raise MarketDataMasterDataImportError("MASTER_DATA_IMPORT_MANIFEST_INVALID")
    try:
        manifest = MarketDataMasterDataManifest.model_validate(payload)
    except ValidationError as exc:
        raise MarketDataMasterDataImportError("MASTER_DATA_IMPORT_MANIFEST_INVALID") from exc
    return manifest, hashlib.sha256(raw).hexdigest()


def _matches_existing_identity(record: AssetInstrument, identity: InstrumentIdentity) -> bool:
    """Allow an exact re-import while refusing a reused canonical/version label."""
    try:
        existing = InstrumentIdentity.model_validate(record.identity_json)
    except ValidationError:
        return False
    return (
        existing.matches_frozen_identity(identity)
        and record.asset_type == identity.asset_type
        and record.identity_level == identity.identity_level
        and record.venue == identity.venue
        and record.currency == identity.currency
        and record.product_type == identity.product_type
        and record.metadata_version == identity.metadata_version
    )


def _is_sha256(value: str) -> bool:
    """Require the deterministic digest generated by ``load_market_data_master_manifest``."""
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
