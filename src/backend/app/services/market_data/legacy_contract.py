"""Safe compatibility contracts from legacy market pages to the v2 query API.

The legacy market page discovers display symbols from an AkShare-oriented
warehouse.  Those symbols are not themselves safe v2 identities: a symbol can
exist on more than one venue and a page request may use a broad legacy market
label such as ``CN``.  This module therefore publishes a v2 contract only when
the canonical master-data projection contains exactly one *active, exact*
symbol key.  The contract then uses the canonical ID, so the actual v2 query
continues to take the strict identity path.

This is deliberately a read-only bridge.  It neither creates master data nor
guesses an identity, a dataset, a provider, or a storage target.  Operators
must bootstrap the canonical catalog and import approved identities before a
legacy page can opt into the new local-first path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data_platform import MdInstrumentLookupKey
from app.schemas.market_data_platform import QueryIdentity
from app.services.market_data.catalog import DataCatalogResolver, DatasetStorageNotFoundError
from app.services.market_data.identity import (
    MarketDataIdentityResolutionError,
    MarketDataIdentityResolver,
)

_DATASET_CODE = "market.bars"
_FREQUENCY_BY_LEGACY_PERIOD = {
    "daily": "1d",
    "weekly": "1w",
    "monthly": "1mo",
    "1d": "1d",
    "1w": "1w",
    "1mo": "1mo",
}
_DATE_ALIGNED_BAR_FREQUENCIES = frozenset({"1d", "1w", "1mo"})
_DAILY_BAR_FREQUENCIES = frozenset({"1d"})
_OPENBB_LEGACY_ASSET_TYPES = frozenset({"stock", "futures", "fund", "fx", "crypto"})


@dataclass(frozen=True)
class _SemanticDefaults:
    """The narrow, source-policy-compatible baseline for one legacy asset class."""

    adjustment: str | None
    price_basis: str | None
    currency: str | None
    unit: str | None


_GLOBAL_DEFAULTS = _SemanticDefaults(
    adjustment=None,
    price_basis=None,
    currency=None,
    unit=None,
)
_CN_STOCK_FUND_DEFAULTS = _SemanticDefaults(
    adjustment="qfq",
    price_basis="close",
    currency="CNY",
    unit="share",
)
_CN_FUTURES_DEFAULTS = _SemanticDefaults(
    adjustment="unadjusted",
    price_basis="close",
    currency="CNY",
    unit="contract",
)
_CN_BOND_DEFAULTS = _SemanticDefaults(
    adjustment="unadjusted",
    price_basis="close",
    currency="CNY",
    unit=None,
)
_CN_OPTION_DEFAULTS = _SemanticDefaults(
    adjustment="unadjusted",
    price_basis="close",
    currency="CNY",
    unit="contract",
)
_CN_FX_DEFAULTS = _SemanticDefaults(
    adjustment="unadjusted",
    price_basis="close",
    currency=None,
    unit=None,
)


class LegacyMarketDataQueryContractResolver:
    """Publish a canonical v2 request template for an unambiguous legacy selection."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        openbb_allowed_markets: frozenset[str] = frozenset(),
    ) -> None:
        self._db = db
        self._identities = MarketDataIdentityResolver(db)
        self._catalog = DataCatalogResolver(db)
        self._openbb_allowed_markets = frozenset(
            market.strip() for market in openbb_allowed_markets if market.strip()
        )

    async def resolve(
        self,
        *,
        asset_type: str,
        symbol: str,
        period: str,
    ) -> dict[str, Any] | None:
        """Return a v2 contract only when every prerequisite is already authoritative.

        The legacy ``market`` request parameter is intentionally not used as a
        substitute for a canonical venue.  It can be a broad UI grouping; the
        materialized key must prove a single active canonical identity before
        this bridge returns anything.
        """
        normalized_asset_type = asset_type.strip()
        normalized_symbol = symbol.strip()
        frequency = _FREQUENCY_BY_LEGACY_PERIOD.get(period.strip().lower())
        if not normalized_asset_type or not normalized_symbol or frequency is None:
            return None

        canonical_id = await self._unique_active_canonical_id(
            asset_type=normalized_asset_type,
            symbol=normalized_symbol,
        )
        if canonical_id is None:
            return None
        try:
            identity = await self._identities.resolve(QueryIdentity(canonical_id=canonical_id))
            await self._catalog.resolve_primary(_DATASET_CODE)
        except (MarketDataIdentityResolutionError, DatasetStorageNotFoundError):
            return None

        semantics = _semantics_for(identity.asset_type, identity.venue)
        if not self._has_reviewed_route(
            asset_type=identity.asset_type,
            venue=identity.venue,
            frequency=frequency,
            semantics=semantics,
        ):
            # The source policy remains the final authorization boundary, but
            # publishing no v2 contract here preserves the legacy page when
            # its exact period has no reviewed route yet.
            return None
        return {
            "version": "market-data-v2",
            "request": {
                "identity": {"canonical_id": identity.canonical_id},
                "dataset_code": _DATASET_CODE,
                "data_kind": "bars",
                "frequency": frequency,
                # ``close`` is the one cross-asset field required by the
                # existing display. Providers may retain additional normalized
                # OHLCV fields, but the bridge must not promise a field an
                # approved route cannot evidence.
                "required_fields": ["close"],
                "adjustment": semantics.adjustment,
                "price_basis": semantics.price_basis,
                "currency": semantics.currency,
                "unit": semantics.unit,
                "source_policy_id": "market-default-v1",
                "mode": "local_first",
            },
        }

    async def _unique_active_canonical_id(
        self,
        *,
        asset_type: str,
        symbol: str,
    ) -> str | None:
        """Return one canonical ID or fail closed on absent/ambiguous projected keys."""
        rows = list(
            (
                await self._db.execute(
                    select(MdInstrumentLookupKey.canonical_id)
                    .where(
                        MdInstrumentLookupKey.asset_type == asset_type,
                        MdInstrumentLookupKey.symbol == symbol,
                        MdInstrumentLookupKey.is_active.is_(True),
                    )
                    .order_by(MdInstrumentLookupKey.market, MdInstrumentLookupKey.canonical_id)
                    .limit(2)
                )
            )
            .scalars()
            .all()
        )
        if len(rows) != 1:
            return None
        canonical_id = rows[0]
        return canonical_id if isinstance(canonical_id, str) and canonical_id else None

    def _has_reviewed_route(
        self,
        *,
        asset_type: str,
        venue: str | None,
        frequency: str,
        semantics: _SemanticDefaults,
    ) -> bool:
        """Match only default-policy capabilities safe for a legacy page contract.

        This intentionally mirrors the declared routes in ``queries.py``
        without importing API composition or constructing a provider. A new
        route must update this compatibility precondition and its regression
        coverage before a page may enter the local-first path.
        """
        if asset_type in {"stock", "fund"} and venue in {"CN-SSE", "CN-SZSE"}:
            return frequency in _DATE_ALIGNED_BAR_FREQUENCIES
        if asset_type == "futures" and venue == "CFFEX":
            return frequency in _DAILY_BAR_FREQUENCIES
        if asset_type == "bond" and venue in {"SSE", "SZSE", "CN-SSE", "CN-SZSE"}:
            return frequency in _DAILY_BAR_FREQUENCIES
        if asset_type == "option" and venue == "CFFEX":
            return frequency in _DAILY_BAR_FREQUENCIES
        if asset_type == "fx" and venue in {"OTC", "CN-OTC"}:
            return frequency in _DAILY_BAR_FREQUENCIES
        return (
            venue in self._openbb_allowed_markets
            and asset_type in _OPENBB_LEGACY_ASSET_TYPES
            and frequency in _DATE_ALIGNED_BAR_FREQUENCIES
            and semantics == _GLOBAL_DEFAULTS
        )


def _semantics_for(asset_type: str, venue: str | None) -> _SemanticDefaults:
    """Use declared domestic semantics only for a reviewed domestic venue."""
    if asset_type in {"stock", "fund"} and venue in {"CN-SSE", "CN-SZSE"}:
        return _CN_STOCK_FUND_DEFAULTS
    if asset_type == "futures" and venue == "CFFEX":
        return _CN_FUTURES_DEFAULTS
    if asset_type == "bond" and venue in {"SSE", "SZSE", "CN-SSE", "CN-SZSE"}:
        return _CN_BOND_DEFAULTS
    if asset_type == "option" and venue in {"CFFEX", "SSE", "SZSE", "CN-SSE", "CN-SZSE"}:
        return _CN_OPTION_DEFAULTS
    if asset_type == "fx" and venue in {"OTC", "CN-OTC"}:
        return _CN_FX_DEFAULTS
    # OpenBB's isolated runner accepts only provider-native undeclared
    # semantics. Returning None here keeps the bridge compatible with a
    # reviewed OpenBB fallback and avoids relabelling a global provider's data.
    return _GLOBAL_DEFAULTS
