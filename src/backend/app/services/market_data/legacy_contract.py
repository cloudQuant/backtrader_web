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
from app.services.market_data.dataset_contracts import (
    DEFAULT_DATASET_CONTRACT_REGISTRY,
    FAMILY_CONTRACT_VERSION,
    DatasetContract,
    DatasetContractRegistry,
)
from app.services.market_data.identity import (
    MarketDataIdentityResolutionError,
    MarketDataIdentityResolver,
)

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
        family_contracts: DatasetContractRegistry = DEFAULT_DATASET_CONTRACT_REGISTRY,
    ) -> None:
        self._db = db
        self._identities = MarketDataIdentityResolver(db)
        self._catalog = DataCatalogResolver(db)
        self._openbb_allowed_markets = frozenset(
            market.strip() for market in openbb_allowed_markets if market.strip()
        )
        self._family_contracts = family_contracts

    async def resolve(
        self,
        *,
        asset_type: str,
        symbol: str,
        period: str,
        family_id: str | None = None,
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

        # The compatibility endpoint used to publish a generic, unbound bars
        # request when a legacy client did not yet send a family ID.  That
        # leaves a future product route able to bypass the server-owned
        # product registry.  Preserve the legacy input shape, but have the
        # server select the one compatible real-time family for the requested
        # asset type.  There is intentionally no nearby-family fallback: an
        # unconfigured class such as ``crypto.realtime`` raises the registry's
        # stable error before catalog or identity work can mint a request.
        selected_family_id = (
            family_id if family_id is not None else f"{normalized_asset_type}.realtime"
        )
        family_contract: DatasetContract = self._family_contracts.ready_contract_for(
            family_id=selected_family_id,
            asset_type=normalized_asset_type,
        )
        if frequency not in family_contract.frequencies:
            return None

        canonical_id = await self._unique_active_canonical_id(
            asset_type=normalized_asset_type,
            symbol=normalized_symbol,
        )
        if canonical_id is None:
            return None
        try:
            identity = await self._identities.resolve(QueryIdentity(canonical_id=canonical_id))
            await self._catalog.resolve_primary(family_contract.dataset_code)
        except (MarketDataIdentityResolutionError, DatasetStorageNotFoundError):
            return None
        # The active legacy lookup key is only an index projection.  Its
        # asset type must agree with the published canonical identity before
        # it can mint a v2 request; a stale or corrupt projection must not
        # transform a stock page selection into a futures (or other asset)
        # contract.  The server-issued family adds the same invariant at the
        # product boundary, rather than relying on the later query resolver to
        # catch the mismatch after this endpoint has signed a contract.
        if identity.asset_type != normalized_asset_type:
            return None
        if identity.asset_type != family_contract.asset_type:
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
        request: dict[str, Any] = {
            "identity": {"canonical_id": identity.canonical_id},
            "dataset_code": family_contract.dataset_code,
            "data_kind": family_contract.data_kind,
            "frequency": frequency,
            "required_fields": list(family_contract.field_profile.required_fields),
            "adjustment": semantics.adjustment,
            "price_basis": semantics.price_basis,
            "currency": semantics.currency,
            "unit": semantics.unit,
            "source_policy_id": family_contract.source_policy_id,
            "mode": "local_first",
        }
        # ``ready_contract_for`` guarantees the policy is populated. Keep the
        # check explicit so a future registry mutation cannot publish an
        # executable contract with an omitted authorization axis.
        if request["source_policy_id"] is None:
            return None
        request.update(
            {
                "family_id": family_contract.family_id,
                "family_contract_version": FAMILY_CONTRACT_VERSION,
            }
        )
        return {
            "version": "market-data-v2",
            "request": request,
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
