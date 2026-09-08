"""Bind public market-data requests to exact catalog and master-data facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.schemas.market_data_platform import MarketDataQueryRequest, ResolvedMarketDataQuery
from app.services.market_data.catalog import (
    DataCatalogResolver,
    DatasetStorageNotFoundError,
    DatasetStorageResolution,
)
from app.services.market_data.coverage import QueryIdentity as CoverageQueryIdentity
from app.services.market_data.identity import (
    MarketDataIdentityResolver,
    ResolvedMarketDataIdentity,
)


class MarketDataQueryResolutionError(ValueError):
    """Stable failure code for a request that cannot enter the local-first path."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ResolvedMarketDataQueryContext:
    """All server-owned facts needed before local coverage or provider work starts."""

    query: ResolvedMarketDataQuery
    identity: ResolvedMarketDataIdentity
    storage: DatasetStorageResolution
    coverage_identity: CoverageQueryIdentity


class MarketDataQueryResolver:
    """Resolve dataset and instrument facts without inspecting legacy table names."""

    def __init__(
        self,
        *,
        catalog: DataCatalogResolver,
        identities: MarketDataIdentityResolver,
    ) -> None:
        self._catalog = catalog
        self._identities = identities

    async def resolve(
        self,
        request: MarketDataQueryRequest,
        *,
        identity_knowledge_cutoff: datetime | None = None,
    ) -> ResolvedMarketDataQueryContext:
        """Return a query whose persistence key contains all authoritative identity facts.

        The public contract permits an omitted dataset code only so a future
        explicitly registered policy resolver can supply one.  No such policy
        exists in this foundational increment, so guessing from a provider,
        asset type, or legacy target table is deliberately forbidden.
        """
        if request.dataset_code is None:
            raise MarketDataQueryResolutionError("DATASET_REQUIRED")
        if request.source_policy_id is None:
            raise MarketDataQueryResolutionError("SOURCE_POLICY_REQUIRED")

        try:
            storage = await self._catalog.resolve_primary(request.dataset_code)
        except DatasetStorageNotFoundError as exc:
            raise MarketDataQueryResolutionError("DATASET_UNAVAILABLE") from exc

        cutoff = _resolve_identity_knowledge_cutoff(
            request.knowledge_cutoff,
            identity_knowledge_cutoff,
        )
        identity = await self._identities.resolve(
            request.identity,
            effective_at=request.start,
            knowledge_cutoff=cutoff,
        )
        if identity.valid_to is not None and identity.valid_to < request.end:
            raise MarketDataQueryResolutionError("IDENTITY_VERSION_WINDOW_CROSSES")
        if identity.venue is None:
            raise MarketDataQueryResolutionError("IDENTITY_MARKET_UNSUPPORTED")

        query = ResolvedMarketDataQuery.from_request(
            request,
            canonical_id=identity.canonical_id,
            dataset_code=storage.dataset_code,
            instrument_metadata_version=identity.metadata_version,
        )
        coverage_identity = CoverageQueryIdentity(
            dataset_code=query.dataset_code,
            canonical_id=identity.canonical_id,
            asset_type=identity.asset_type,
            instrument_metadata_version=identity.metadata_version,
            data_kind=query.data_kind,
            market=identity.venue,
            frequency=query.frequency or "snapshot",
            source_policy_id=query.source_policy_id,
            adjustment=query.adjustment,
            price_basis=query.price_basis,
            currency=query.currency,
            unit=query.unit,
        )
        return ResolvedMarketDataQueryContext(
            query=query,
            identity=identity,
            storage=storage,
            coverage_identity=coverage_identity,
        )


def _resolve_identity_knowledge_cutoff(
    request_cutoff: datetime | None,
    override_cutoff: datetime | None,
) -> datetime | None:
    """Choose one trusted master-data cutoff without mutating query semantics.

    Cursor pagination freezes master-data resolution at the first page's local
    receipt boundary.  The cursor cutoff is intentionally used only for
    identity visibility; it is not copied into the public query model because
    that would change the stable query fingerprint carried by the cursor.
    """
    if override_cutoff is None:
        return request_cutoff
    if override_cutoff.tzinfo is None or override_cutoff.utcoffset() is None:
        raise MarketDataQueryResolutionError("IDENTITY_KNOWLEDGE_CUTOFF_INVALID")
    normalized_override = override_cutoff.astimezone(timezone.utc)
    if request_cutoff is not None and request_cutoff != normalized_override:
        raise MarketDataQueryResolutionError("CURSOR_CUTOFF_MISMATCH")
    return normalized_override
