"""Immutable point-in-time projections of authoritative instrument identities."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_research import AssetInstrument
from app.models.market_data_platform import MdInstrumentIdentityRevision
from app.schemas.asset_research import InstrumentIdentity
from app.services.market_data.publication import (
    PUBLICATION_INSTRUMENT_IDENTITY,
    MarketDataPublicationError,
    MarketDataPublicationManager,
)

UTC = timezone.utc


class MarketDataIdentityProjectionError(ValueError):
    """Stable failure code for a projection that cannot be safely published."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


class MarketDataIdentityProjectionWriter:
    """Append frozen v2 identity projections in the caller's business transaction."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._db = db
        self._publications = MarketDataPublicationManager(db, clock=clock)
        self._staged_publication_ids: list[str] = []

    @property
    def staged_publication_ids(self) -> tuple[str, ...]:
        """Publication IDs that must be made visible after the caller commits."""
        return tuple(self._staged_publication_ids)

    async def publish_staged(self) -> None:
        """Publish projections after their caller has committed the business batch."""
        if not self._staged_publication_ids:
            return
        publication_ids = tuple(self._staged_publication_ids)
        await self._publications.publish_staged(publication_ids)
        # Keep only receipts that still need a post-commit transition.  A
        # long-lived importer/backfill object may process more than one batch;
        # retaining already visible IDs would needlessly mix old and new
        # receipts in a later recovery/publication operation.
        self._staged_publication_ids.clear()

    async def project(self, record: AssetInstrument) -> MdInstrumentIdentityRevision:
        """Append a frozen projection if the current authority state is new.

        A projection includes validity dates and the complete validated identity
        JSON.  When an authority row is later retired, a new projection is
        appended rather than mutating the old one; strict replays select the
        newest receipt visible at their cutoff for that instrument.
        """
        identity = self._validated_identity(record)
        payload = {
            "projection_contract_version": "market-data-identity-projection-v1",
            "instrument_id": record.id,
            "canonical_id": identity.canonical_id,
            "asset_type": identity.asset_type,
            "market": identity.venue,
            "symbol": identity.display_symbol,
            "metadata_version": identity.metadata_version,
            "identity": identity.model_dump(mode="json"),
            "valid_from": _as_utc(record.valid_from).isoformat(),
            "valid_to": _as_utc(record.valid_to).isoformat() if record.valid_to else None,
        }
        digest = _sha256(payload)
        existing = await self._db.scalar(
            select(MdInstrumentIdentityRevision).where(
                MdInstrumentIdentityRevision.revision_sha256 == digest
            )
        )
        if existing is not None:
            receipt = await self._publications.stage(
                entity_type=PUBLICATION_INSTRUMENT_IDENTITY,
                entity_id=existing.id,
                entity_sha256=existing.revision_sha256,
            )
            self._remember(receipt.id)
            return existing

        next_revision = int(
            (
                await self._db.scalar(
                    select(func.max(MdInstrumentIdentityRevision.revision_number)).where(
                        MdInstrumentIdentityRevision.instrument_id == record.id
                    )
                )
                or 0
            )
            + 1
        )
        projection = MdInstrumentIdentityRevision(
            instrument_id=record.id,
            canonical_id=identity.canonical_id,
            asset_type=identity.asset_type,
            market=identity.venue,
            symbol=identity.display_symbol,
            metadata_version=identity.metadata_version,
            identity_json=identity.model_dump(mode="json"),
            valid_from=_as_utc(record.valid_from),
            valid_to=_as_utc(record.valid_to) if record.valid_to is not None else None,
            revision_number=next_revision,
            revision_sha256=digest,
        )
        self._db.add(projection)
        try:
            await self._db.flush()
            receipt = await self._publications.stage(
                entity_type=PUBLICATION_INSTRUMENT_IDENTITY,
                entity_id=projection.id,
                entity_sha256=projection.revision_sha256,
            )
        except (IntegrityError, MarketDataPublicationError) as exc:
            raise MarketDataIdentityProjectionError("IDENTITY_PROJECTION_WRITE_CONFLICT") from exc
        self._remember(receipt.id)
        return projection

    async def project_records(
        self,
        records: Sequence[AssetInstrument],
    ) -> tuple[MdInstrumentIdentityRevision, ...]:
        """Project a deterministic collection without duplicate receipts."""
        by_id = {record.id: record for record in records}
        projections: list[MdInstrumentIdentityRevision] = []
        for record_id in sorted(by_id):
            projections.append(await self.project(by_id[record_id]))
        return tuple(projections)

    @staticmethod
    def _validated_identity(record: AssetInstrument) -> InstrumentIdentity:
        try:
            identity = InstrumentIdentity.model_validate(record.identity_json)
        except ValidationError as exc:
            raise MarketDataIdentityProjectionError("IDENTITY_PROJECTION_INTEGRITY") from exc
        if (
            identity.canonical_id != record.canonical_id
            or identity.asset_type != record.asset_type
            or identity.identity_level != record.identity_level
            or identity.venue != record.venue
            or identity.currency != record.currency
            or identity.product_type != record.product_type
            or identity.metadata_version != record.metadata_version
        ):
            raise MarketDataIdentityProjectionError("IDENTITY_PROJECTION_INTEGRITY")
        return identity

    def _remember(self, publication_id: str) -> None:
        if publication_id not in self._staged_publication_ids:
            self._staged_publication_ids.append(publication_id)
