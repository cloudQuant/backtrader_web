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
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data_platform import (
    MdInstrumentIdentityRevision,
    MdInstrumentLookupKey,
    MdPublication,
)
from app.schemas.market_data_platform import QueryIdentity
from app.services.market_data.catalog import DataCatalogResolver, DatasetStorageNotFoundError
from app.services.market_data.dataset_contracts import (
    DEFAULT_DATASET_CONTRACT_REGISTRY,
    KLINE_LEGACY_FAMILY_ID,
    DatasetContract,
    DatasetContractRegistry,
    DatasetContractRegistryError,
)
from app.services.market_data.identity import (
    MarketDataIdentityResolutionError,
    MarketDataIdentityResolver,
)
from app.services.market_data.legacy_kline_identity import matches_legacy_kline_display_token
from app.services.market_data.openbb_runtime import (
    OpenBBRuntimeRoutePermit,
    approved_openbb_runtime_route_permits,
)
from app.services.market_data.publication import PUBLICATION_INSTRUMENT_IDENTITY

_FREQUENCY_BY_LEGACY_PERIOD = {
    # ``daily``/``weekly``/``monthly`` are retained for the legacy page
    # selector. A server-issued family bundle may also select an exact public
    # v2 cadence directly. Mapping it here is not a route grant: the exact
    # ready-family, declared-frequency, semantic, catalog, identity, and
    # reviewed-route checks below all still have to succeed.
    "5min": "5min",
    "30min": "30min",
    "1h": "1h",
    "daily": "1d",
    "weekly": "1w",
    "monthly": "1mo",
    "1d": "1d",
    "1w": "1w",
    "1mo": "1mo",
    "snapshot": "snapshot",
}
_DATE_ALIGNED_BAR_FREQUENCIES = frozenset({"1d", "1w", "1mo"})
_DAILY_BAR_FREQUENCIES = frozenset({"1d"})
_MAX_LEGACY_LOOKUP_CANDIDATES = 128


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
_CN_STOCK_FUND_LIQUIDITY_DEFAULTS = _SemanticDefaults(
    adjustment="unadjusted",
    price_basis="close",
    currency="CNY",
    unit="share",
)
_CN_ETF_NAV_DEFAULTS = _SemanticDefaults(
    # NAV is published by the source for one fund share. It must never be
    # reinterpreted as a qfq/hfq traded price or recomputed from ETF bars.
    adjustment="source_reported",
    price_basis="nav",
    currency="CNY",
    unit="fund_share",
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
        openbb_provider: str = "yfinance",
        openbb_allowed_markets: frozenset[str] = frozenset(),
        family_contracts: DatasetContractRegistry = DEFAULT_DATASET_CONTRACT_REGISTRY,
    ) -> None:
        self._db = db
        self._identities = MarketDataIdentityResolver(db)
        self._catalog = DataCatalogResolver(db)
        normalized_openbb_markets = tuple(
            market.strip() for market in openbb_allowed_markets if market.strip()
        )
        self._openbb_runtime_permits = approved_openbb_runtime_route_permits(
            openbb_provider,
            normalized_openbb_markets,
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
        if family_id == KLINE_LEGACY_FAMILY_ID:
            # This resolver backs the public query-contract endpoint. The K-line
            # compatibility product is intentionally server-selected by the
            # dedicated facade and must not be mintable from a browser family
            # selector.
            raise DatasetContractRegistryError("DATA_FAMILY_UNSUPPORTED")
        return await self._resolve(
            asset_type=asset_type,
            symbol=symbol,
            period=period,
            family_id=family_id,
        )

    async def resolve_kline_legacy(
        self,
        *,
        symbol: str,
        period: str,
    ) -> dict[str, Any] | None:
        """Mint the fixed private K-line contract for the server-owned legacy facade."""
        return await self._resolve(
            asset_type="stock",
            symbol=symbol,
            period=period,
            family_id=KLINE_LEGACY_FAMILY_ID,
            allow_frozen_exchange_symbol_alias=True,
        )

    async def _resolve(
        self,
        *,
        asset_type: str,
        symbol: str,
        period: str,
        family_id: str | None,
        allow_frozen_exchange_symbol_alias: bool = False,
    ) -> dict[str, Any] | None:
        """Resolve a selected server-owned family after the public/private gate."""
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
            allow_frozen_exchange_symbol_alias=allow_frozen_exchange_symbol_alias,
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
        # A case-insensitive database collation must never let the legacy
        # bridge mint a request for a differently cased display symbol.  The
        # lookup projection and its migration use binary collations, but this
        # second, frozen-identity comparison keeps an un-migrated or corrupt
        # database fail-closed as well.
        if allow_frozen_exchange_symbol_alias:
            if not matches_legacy_kline_display_token(
                identity.identity,
                token=normalized_symbol,
            ):
                return None
        elif identity.identity.display_symbol != normalized_symbol:
            return None

        semantics = _semantics_for(
            family_id=family_contract.family_id,
            asset_type=identity.asset_type,
            venue=identity.venue,
            product_type=identity.identity.product_type,
            fund_identity_kind=getattr(identity.identity.details, "fund_identity_kind", None),
        )
        # A compatibility bridge signs every B1 semantic field explicitly.
        # Keep that signature tied to the same registry-owned binding used by
        # the v2 resolver; otherwise a later edit to legacy defaults could mint
        # a request the public endpoint interprets with a generic default.
        if semantics is None:
            return None
        semantic_binding = family_contract.semantic_binding
        if semantic_binding is not None and not semantic_binding.matches(
            adjustment=semantics.adjustment,
            price_basis=semantics.price_basis,
            currency=semantics.currency,
            unit=semantics.unit,
            explicit_axis_names=frozenset({"adjustment", "price_basis", "currency", "unit"}),
        ):
            return None
        if not self._has_reviewed_route(
            family_id=family_contract.family_id,
            asset_type=identity.asset_type,
            venue=identity.venue,
            data_kind=family_contract.data_kind,
            frequency=frequency,
            semantics=semantics,
            product_type=identity.identity.product_type,
            fund_identity_kind=getattr(identity.identity.details, "fund_identity_kind", None),
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
                "family_contract_version": family_contract.family_contract_version,
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
        allow_frozen_exchange_symbol_alias: bool = False,
    ) -> str | None:
        """Return one canonical ID or fail closed on absent/ambiguous projected keys."""
        if allow_frozen_exchange_symbol_alias and asset_type == "stock":
            # The private K-line facade accepts two frozen token fields.  Its
            # candidate universe must therefore be one publication-gated,
            # current-identity union; consulting the mutable lookup projection
            # first would allow an exact display-symbol row to mask a distinct
            # exact ``details.exchange_symbol`` candidate.
            return await self._unique_current_published_kline_canonical_id(
                asset_type=asset_type,
                token=symbol,
            )

        rows = list(
            (
                await self._db.execute(
                    select(
                        MdInstrumentLookupKey.canonical_id,
                        MdInstrumentLookupKey.asset_type,
                        MdInstrumentLookupKey.symbol,
                    )
                    .where(
                        MdInstrumentLookupKey.asset_type == asset_type,
                        MdInstrumentLookupKey.symbol == symbol,
                        MdInstrumentLookupKey.is_active.is_(True),
                    )
                    .order_by(MdInstrumentLookupKey.market, MdInstrumentLookupKey.canonical_id)
                    .limit(_MAX_LEGACY_LOOKUP_CANDIDATES + 1)
                )
            ).all()
        )
        if len(rows) > _MAX_LEGACY_LOOKUP_CANDIDATES:
            return None
        # Retain the raw predicate for the binary covering index, then repeat
        # the comparison in Python.  This defends the compatibility endpoint
        # while a pre-existing MySQL schema is being migrated from a default
        # case-insensitive collation: a matching-but-differently-cased row is
        # not a valid exact identity.
        exact_canonical_ids = [
            canonical_id
            for canonical_id, stored_asset_type, stored_symbol in rows
            if isinstance(canonical_id, str)
            and canonical_id
            and stored_asset_type == asset_type
            and stored_symbol == symbol
        ]
        if len(exact_canonical_ids) != 1:
            return None
        return exact_canonical_ids[0]

    async def _unique_current_published_kline_canonical_id(
        self,
        *,
        asset_type: str,
        token: str,
    ) -> str | None:
        """Resolve exactly one current, published frozen K-line identity token.

        A legacy K-line token can be either the frozen display symbol or the
        frozen stock ``details.exchange_symbol`` (for example ``000001.SZ``).
        Discover both axes together from published projections, then ask the
        authoritative resolver to select the current revision for every
        candidate and repeat the exact frozen-token comparison in Python.
        This deliberately ignores pending and expired projections; neither can
        create an alias collision for a current request.
        """
        effective_at = datetime.now(timezone.utc)
        stored_exchange_symbol = MdInstrumentIdentityRevision.identity_json[
            "details"
        ]["exchange_symbol"].as_string()
        candidate_canonical_ids = list(
            (
                await self._db.execute(
                    select(MdInstrumentIdentityRevision.canonical_id)
                    .join(
                        MdPublication,
                        (MdPublication.entity_type == PUBLICATION_INSTRUMENT_IDENTITY)
                        & (MdPublication.entity_id == MdInstrumentIdentityRevision.id),
                    )
                    .where(
                        MdInstrumentIdentityRevision.asset_type == asset_type,
                        MdPublication.published_at.is_not(None),
                        MdInstrumentIdentityRevision.valid_from <= effective_at,
                        or_(
                            MdInstrumentIdentityRevision.valid_to.is_(None),
                            MdInstrumentIdentityRevision.valid_to > effective_at,
                        ),
                        or_(
                            MdInstrumentIdentityRevision.symbol == token,
                            stored_exchange_symbol == token,
                        ),
                    )
                    .distinct()
                    .order_by(MdInstrumentIdentityRevision.canonical_id)
                    .limit(_MAX_LEGACY_LOOKUP_CANDIDATES + 1)
                )
            )
            .scalars()
            .all()
        )
        if len(candidate_canonical_ids) > _MAX_LEGACY_LOOKUP_CANDIDATES:
            return None

        matches: set[str] = set()
        for canonical_id in candidate_canonical_ids:
            if not isinstance(canonical_id, str) or not canonical_id:
                return None
            try:
                identity = await self._identities.resolve(
                    QueryIdentity(canonical_id=canonical_id),
                    effective_at=effective_at,
                )
            except MarketDataIdentityResolutionError as exc:
                # A revision which was current when it was published may have
                # become historical before this request.  It is not a current
                # token match and must not produce a false collision.  Other
                # authoritative-resolution failures are unsafe to ignore.
                if exc.code == "IDENTITY_NOT_FOUND":
                    continue
                return None
            if identity.canonical_id != canonical_id or identity.asset_type != asset_type:
                return None
            if matches_legacy_kline_display_token(identity.identity, token=token):
                matches.add(canonical_id)

        if len(matches) != 1:
            return None
        return next(iter(matches))

    def _has_reviewed_route(
        self,
        *,
        family_id: str,
        asset_type: str,
        venue: str | None,
        frequency: str,
        semantics: _SemanticDefaults | None,
        product_type: str | None = None,
        fund_identity_kind: str | None = None,
        data_kind: str | None = None,
    ) -> bool:
        """Match one exact family to its default-policy route and semantics.

        This intentionally mirrors the declared routes in ``queries.py``
        without importing API composition or constructing a provider. A new
        route must update this compatibility precondition and its regression
        coverage before a page may enter the local-first path.
        """
        if semantics is None:
            return False
        if family_id == KLINE_LEGACY_FAMILY_ID:
            return (
                asset_type == "stock"
                and venue in {"CN-SSE", "CN-SZSE"}
                and data_kind in {None, "bars"}
                and frequency in _DATE_ALIGNED_BAR_FREQUENCIES
                and semantics == _CN_STOCK_FUND_DEFAULTS
            )
        if family_id == "stock.liquidity":
            return (
                asset_type == "stock"
                and venue in {"CN-SSE", "CN-SZSE"}
                and data_kind in {None, "reference_series"}
                and frequency in _DAILY_BAR_FREQUENCIES
                and semantics == _CN_STOCK_FUND_LIQUIDITY_DEFAULTS
            )
        if family_id == "fund.liquidity":
            return (
                asset_type == "fund"
                and venue in {"CN-SSE", "CN-SZSE"}
                and data_kind in {None, "reference_series"}
                and frequency in _DAILY_BAR_FREQUENCIES
                and semantics == _CN_STOCK_FUND_LIQUIDITY_DEFAULTS
            )
        if family_id == "fund.nav":
            return (
                asset_type == "fund"
                and venue in {"CN-SSE", "CN-SZSE"}
                and product_type == "ETF"
                and fund_identity_kind == "LISTING"
                and data_kind in {None, "reference_series"}
                and frequency in _DAILY_BAR_FREQUENCIES
                and semantics == _CN_ETF_NAV_DEFAULTS
            )
        if family_id == "fx.range":
            return (
                asset_type == "fx"
                and venue in {"OTC", "CN-OTC"}
                and data_kind in {None, "bars"}
                and frequency in _DAILY_BAR_FREQUENCIES
                and semantics == _CN_FX_DEFAULTS
            )
        if family_id != f"{asset_type}.realtime":
            return False
        if asset_type in {"stock", "fund"} and venue in {"CN-SSE", "CN-SZSE"}:
            return (
                data_kind in {None, "bars"}
                and frequency in _DATE_ALIGNED_BAR_FREQUENCIES
                and semantics == _CN_STOCK_FUND_DEFAULTS
            )
        if asset_type == "futures" and venue == "CFFEX":
            return (
                data_kind in {None, "bars"}
                and frequency in _DAILY_BAR_FREQUENCIES
                and semantics == _CN_FUTURES_DEFAULTS
            )
        if asset_type == "bond" and venue in {"SSE", "SZSE", "CN-SSE", "CN-SZSE"}:
            return (
                data_kind in {None, "bars"}
                and frequency in _DAILY_BAR_FREQUENCIES
                and semantics == _CN_BOND_DEFAULTS
            )
        if asset_type == "option" and venue == "CFFEX":
            return (
                data_kind in {None, "bars"}
                and frequency in _DAILY_BAR_FREQUENCIES
                and semantics == _CN_OPTION_DEFAULTS
            )
        if asset_type == "fx" and venue in {"OTC", "CN-OTC"}:
            return (
                data_kind in {None, "bars"}
                and frequency in _DAILY_BAR_FREQUENCIES
                and semantics == _CN_FX_DEFAULTS
            )
        try:
            family_contract_version = self._family_contracts.ready_contract_for(
                family_id=family_id,
                asset_type=asset_type,
            ).family_contract_version
        except DatasetContractRegistryError:
            return False
        return any(
            _permit_matches_legacy_request(
                permit,
                family_id=family_id,
                family_contract_version=family_contract_version,
                asset_type=asset_type,
                venue=venue,
                data_kind=data_kind or "bars",
                frequency=frequency,
                semantics=semantics,
            )
            for permit in self._openbb_runtime_permits
        )


def _permit_matches_legacy_request(
    permit: OpenBBRuntimeRoutePermit,
    *,
    family_id: str,
    family_contract_version: str,
    asset_type: str,
    venue: str | None,
    data_kind: str,
    frequency: str,
    semantics: _SemanticDefaults,
) -> bool:
    """Match every explicit OpenBB permit axis before a bridge can mint a contract."""
    return (
        permit.family_id == family_id
        and permit.family_contract_version == family_contract_version
        and permit.asset_type == asset_type
        and permit.market == venue
        and permit.data_kind == data_kind
        and permit.frequency == frequency
        and permit.adjustment == semantics.adjustment
        and permit.price_basis == semantics.price_basis
        and permit.currency == semantics.currency
        and permit.unit == semantics.unit
    )


def _semantics_for(
    *,
    family_id: str,
    asset_type: str,
    venue: str | None,
    product_type: str | None = None,
    fund_identity_kind: str | None = None,
) -> _SemanticDefaults | None:
    """Return defaults only for one exact ready-family/venue combination.

    Returning ``None`` is intentional: a family that is not reviewed for the
    selected asset and venue cannot fall back to another product's semantics
    merely because it uses a similar data kind or a shared source provider.
    """
    if family_id == "stock.liquidity":
        if asset_type == "stock" and venue in {"CN-SSE", "CN-SZSE"}:
            return _CN_STOCK_FUND_LIQUIDITY_DEFAULTS
        return None
    if family_id == KLINE_LEGACY_FAMILY_ID:
        if asset_type == "stock" and venue in {"CN-SSE", "CN-SZSE"}:
            return _CN_STOCK_FUND_DEFAULTS
        return None
    if family_id == "fund.liquidity":
        if asset_type == "fund" and venue in {"CN-SSE", "CN-SZSE"}:
            return _CN_STOCK_FUND_LIQUIDITY_DEFAULTS
        return None
    if family_id == "fund.nav":
        if (
            asset_type == "fund"
            and venue in {"CN-SSE", "CN-SZSE"}
            and product_type == "ETF"
            and fund_identity_kind == "LISTING"
        ):
            return _CN_ETF_NAV_DEFAULTS
        return None
    if family_id == "fx.range":
        if asset_type == "fx" and venue in {"OTC", "CN-OTC"}:
            return _CN_FX_DEFAULTS
        return None
    if family_id != f"{asset_type}.realtime":
        return None
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
    # A future OpenBB permit can use provider-native undeclared semantics, but
    # this default alone never creates a route or a compatibility contract.
    return _GLOBAL_DEFAULTS
