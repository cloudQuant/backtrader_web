"""Exact, publication-gated master-data resolution for Iteration 197 queries.

The broad research application owns ``asset_instruments``. The market-data
path consumes immutable projections of those records and their post-commit
publication receipts, so a later lifecycle update cannot rewrite a strict
historical query's identity facts.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data_platform import MdInstrumentIdentityRevision, MdPublication
from app.schemas.asset_research import InstrumentIdentity
from app.schemas.market_data_platform import QueryIdentity
from app.services.market_data.publication import PUBLICATION_INSTRUMENT_IDENTITY

_MAX_CANONICAL_VERSION_CANDIDATES = 128
_MAX_TRIPLE_VERSION_CANDIDATES = 128
UTC = timezone.utc


def _utc_now() -> datetime:
    """Return an aware UTC instant for a default master-data lookup."""
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    """Normalize persisted UTC timestamps while rejecting no public input here."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class MarketDataIdentityResolutionError(ValueError):
    """Stable, non-provider error code for exact market identity failures."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ResolvedMarketDataIdentity:
    """The immutable identity version bound into a market-data query."""

    instrument_id: str
    canonical_id: str
    asset_type: str
    metadata_version: str
    venue: str | None
    identity: InstrumentIdentity
    valid_from: datetime
    valid_to: datetime | None
    known_at: datetime


@dataclass(frozen=True)
class _PublishedIdentityRevision:
    revision: MdInstrumentIdentityRevision
    published_at: datetime


class MarketDataIdentityResolver:
    """Resolve only exact, published, internally coherent identity projections."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def resolve(
        self,
        selector: QueryIdentity,
        *,
        effective_at: datetime | None = None,
        knowledge_cutoff: datetime | None = None,
    ) -> ResolvedMarketDataIdentity:
        """Resolve one canonical ID or complete asset/symbol/market selector.

        The public DTO already enforces its XOR selector shape. No case
        folding, alias lookup, display-name search or fallback record is
        permitted. An authoritative record without a published market-data
        projection is deliberately absent from this endpoint.
        """
        effective = self._normalize_effective_at(effective_at)
        cutoff = self._normalize_knowledge_cutoff(knowledge_cutoff)
        rows = await self._load_candidate_rows(selector)
        known_rows = self._known_rows_at_cutoff(rows, cutoff)
        if cutoff is not None and rows and not known_rows:
            raise MarketDataIdentityResolutionError("IDENTITY_NOT_KNOWN_AT_CUTOFF")
        rows = self._latest_published_projection_per_instrument(known_rows)
        self._assert_no_overlapping_versions(rows)
        groups = self._current_groups(rows, effective)

        if selector.canonical_id is not None:
            current = groups.get(selector.canonical_id)
            if current is None:
                raise MarketDataIdentityResolutionError("IDENTITY_NOT_FOUND")
            if len(current) != 1:
                raise MarketDataIdentityResolutionError("IDENTITY_AMBIGUOUS")
            resolved = self._validated_projection(current[0])
            if resolved.canonical_id != selector.canonical_id:
                raise MarketDataIdentityResolutionError("IDENTITY_NOT_FOUND")
            return self._freeze(resolved)

        matches: list[_PublishedIdentityRevision] = []
        for current in groups.values():
            if not current:
                continue
            if len(current) > 1:
                raise MarketDataIdentityResolutionError("IDENTITY_AMBIGUOUS")
            projection = current[0]
            identity = self._validated_projection(projection)
            if self._matches_exact_triple(identity.identity, selector):
                matches.append(projection)

        if not matches:
            raise MarketDataIdentityResolutionError("IDENTITY_NOT_FOUND")
        if len(matches) != 1:
            raise MarketDataIdentityResolutionError("IDENTITY_AMBIGUOUS")
        return self._freeze(self._validated_projection(matches[0]))

    @staticmethod
    def _normalize_effective_at(effective_at: datetime | None) -> datetime:
        if effective_at is None:
            return _utc_now()
        if effective_at.tzinfo is None or effective_at.utcoffset() is None:
            raise MarketDataIdentityResolutionError("IDENTITY_EFFECTIVE_AT_INVALID")
        return effective_at.astimezone(UTC)

    @staticmethod
    def _normalize_knowledge_cutoff(knowledge_cutoff: datetime | None) -> datetime | None:
        if knowledge_cutoff is None:
            return None
        if knowledge_cutoff.tzinfo is None or knowledge_cutoff.utcoffset() is None:
            raise MarketDataIdentityResolutionError("IDENTITY_KNOWLEDGE_CUTOFF_INVALID")
        return knowledge_cutoff.astimezone(UTC)

    @staticmethod
    def _known_rows_at_cutoff(
        rows: Iterable[_PublishedIdentityRevision],
        knowledge_cutoff: datetime | None,
    ) -> list[_PublishedIdentityRevision]:
        """Retain only identities with a durable post-commit receipt at cutoff."""
        if knowledge_cutoff is None:
            return list(rows)
        return [row for row in rows if row.published_at <= knowledge_cutoff]

    async def _load_candidate_rows(
        self,
        selector: QueryIdentity,
    ) -> list[_PublishedIdentityRevision]:
        """Load a bounded candidate set from immutable published projections."""
        statement = (
            select(MdInstrumentIdentityRevision, MdPublication)
            .join(
                MdPublication,
                (MdPublication.entity_type == PUBLICATION_INSTRUMENT_IDENTITY)
                & (MdPublication.entity_id == MdInstrumentIdentityRevision.id),
            )
            .where(MdPublication.published_at.is_not(None))
        )
        if selector.canonical_id is not None:
            maximum = _MAX_CANONICAL_VERSION_CANDIDATES
            statement = statement.where(
                MdInstrumentIdentityRevision.canonical_id == selector.canonical_id
            )
        else:
            maximum = _MAX_TRIPLE_VERSION_CANDIDATES
            statement = statement.where(
                MdInstrumentIdentityRevision.asset_type == selector.asset_type,
                MdInstrumentIdentityRevision.market == selector.market,
                MdInstrumentIdentityRevision.symbol == selector.symbol,
            )
        rows = list(
            (
                await self._db.execute(
                    statement.order_by(
                        MdInstrumentIdentityRevision.canonical_id,
                        MdInstrumentIdentityRevision.instrument_id,
                        MdInstrumentIdentityRevision.revision_number,
                    ).limit(maximum + 1)
                )
            ).all()
        )
        if len(rows) > maximum:
            raise MarketDataIdentityResolutionError("IDENTITY_CANDIDATE_LIMIT_EXCEEDED")
        result: list[_PublishedIdentityRevision] = []
        for revision, publication in rows:
            if publication.entity_sha256 != revision.revision_sha256:
                raise MarketDataIdentityResolutionError("IDENTITY_PUBLICATION_INTEGRITY")
            published_at = publication.published_at
            if published_at is None:
                raise MarketDataIdentityResolutionError("IDENTITY_PUBLICATION_INTEGRITY")
            result.append(
                _PublishedIdentityRevision(
                    revision=revision,
                    published_at=_as_utc(published_at),
                )
            )
        return result

    @staticmethod
    def _latest_published_projection_per_instrument(
        rows: Iterable[_PublishedIdentityRevision],
    ) -> list[_PublishedIdentityRevision]:
        selected: dict[str, _PublishedIdentityRevision] = {}
        for candidate in rows:
            current = selected.get(candidate.revision.instrument_id)
            if current is None or (
                candidate.published_at,
                candidate.revision.revision_number,
                candidate.revision.id,
            ) > (
                current.published_at,
                current.revision.revision_number,
                current.revision.id,
            ):
                selected[candidate.revision.instrument_id] = candidate
        return list(selected.values())

    @staticmethod
    def _current_groups(
        rows: Iterable[_PublishedIdentityRevision],
        effective_at: datetime,
    ) -> dict[str, list[_PublishedIdentityRevision]]:
        grouped: dict[str, list[_PublishedIdentityRevision]] = defaultdict(list)
        for row in rows:
            revision = row.revision
            valid_from = _as_utc(revision.valid_from)
            valid_to = _as_utc(revision.valid_to) if revision.valid_to is not None else None
            if valid_from > effective_at:
                continue
            if valid_to is not None and valid_to <= effective_at:
                continue
            grouped[revision.canonical_id].append(row)

        result: dict[str, list[_PublishedIdentityRevision]] = {}
        for canonical_id, versions in grouped.items():
            newest_from = max(_as_utc(row.revision.valid_from) for row in versions)
            result[canonical_id] = [
                row for row in versions if _as_utc(row.revision.valid_from) == newest_from
            ]
        return result

    @staticmethod
    def _assert_no_overlapping_versions(rows: Iterable[_PublishedIdentityRevision]) -> None:
        grouped: dict[str, list[tuple[datetime, datetime | None]]] = defaultdict(list)
        for row in rows:
            revision = row.revision
            valid_from = _as_utc(revision.valid_from)
            valid_to = _as_utc(revision.valid_to) if revision.valid_to is not None else None
            if valid_to is not None and valid_to <= valid_from:
                raise MarketDataIdentityResolutionError("IDENTITY_INTEGRITY")
            grouped[revision.canonical_id].append((valid_from, valid_to))
        for versions in grouped.values():
            latest_end: datetime | None = None
            previous_start: datetime | None = None
            has_previous = False
            for valid_from, valid_to in sorted(versions, key=lambda item: item[0]):
                if has_previous:
                    if valid_from == previous_start:
                        raise MarketDataIdentityResolutionError("IDENTITY_AMBIGUOUS")
                    if latest_end is None or valid_from < latest_end:
                        raise MarketDataIdentityResolutionError("IDENTITY_VERSION_OVERLAP")
                latest_end = valid_to
                previous_start = valid_from
                has_previous = True

    @staticmethod
    def _validated_projection(
        published: _PublishedIdentityRevision,
    ) -> ResolvedMarketDataIdentity:
        revision = published.revision
        try:
            identity = InstrumentIdentity.model_validate(revision.identity_json)
        except ValidationError as exc:
            raise MarketDataIdentityResolutionError("IDENTITY_INTEGRITY") from exc
        if (
            identity.asset_type != revision.asset_type
            or identity.canonical_id != revision.canonical_id
            or identity.metadata_version != revision.metadata_version
            or identity.venue != revision.market
            or identity.display_symbol != revision.symbol
        ):
            raise MarketDataIdentityResolutionError("IDENTITY_INTEGRITY")
        return ResolvedMarketDataIdentity(
            instrument_id=revision.instrument_id,
            canonical_id=identity.canonical_id,
            asset_type=identity.asset_type,
            metadata_version=identity.metadata_version,
            venue=identity.venue,
            identity=identity,
            valid_from=_as_utc(revision.valid_from),
            valid_to=_as_utc(revision.valid_to) if revision.valid_to is not None else None,
            known_at=published.published_at,
        )

    @staticmethod
    def _matches_exact_triple(identity: InstrumentIdentity, selector: QueryIdentity) -> bool:
        return (
            selector.asset_type is not None
            and selector.symbol is not None
            and selector.market is not None
            and identity.asset_type == selector.asset_type
            and identity.display_symbol == selector.symbol
            and identity.venue == selector.market
        )

    @staticmethod
    def _freeze(resolved: ResolvedMarketDataIdentity) -> ResolvedMarketDataIdentity:
        return resolved
