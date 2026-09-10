"""Versioned API for the Iteration 197 normalized local-first query path."""

from __future__ import annotations

import asyncio
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.data.deps import (
    get_authorized_market_data_access,
    require_authorized_market_data_read,
)
from app.api.data.deps import (
    get_market_data_access_authorizer as _get_market_data_access_authorizer,
)
from app.config import get_settings
from app.db.database import get_db
from app.schemas.market_data_platform import (
    MarketDataCapabilitiesResponse,
    MarketDataCoverageGapResponse,
    MarketDataCoverageResponse,
    MarketDataFetchResponse,
    MarketDataObservationResponse,
    MarketDataQueryBundleRequest,
    MarketDataQueryBundleResponse,
    MarketDataQueryRequest,
    MarketDataQueryResponse,
    MarketDataQueryWarningResponse,
    PublicMarketDataQueryRequest,
)
from app.services.market_data.access import (
    MarketDataAuthorizationError,
    MarketDataQueryAccess,
)
from app.services.market_data.akshare_provider import AkShareMarketDataProvider
from app.services.market_data.capability_ledger import (
    MarketDataCapabilityEvaluation,
    MarketDataCapabilityLedger,
)
from app.services.market_data.catalog import DataCatalogResolver
from app.services.market_data.dataset_contracts import (
    DEFAULT_DATASET_CONTRACT_REGISTRY,
    FAMILY_CONTRACT_VERSION,
    KLINE_LEGACY_CONTRACT_VERSION,
    KLINE_LEGACY_FAMILY_ID,
    DatasetContractRegistryError,
)
from app.services.market_data.identity import (
    MarketDataIdentityResolutionError,
    MarketDataIdentityResolver,
)
from app.services.market_data.openbb_runtime import approved_openbb_runtime_route_permits
from app.services.market_data.providers import OpenBBSubprocessProvider
from app.services.market_data.query_resolution import (
    MarketDataQueryResolutionError,
    MarketDataQueryResolver,
)
from app.services.market_data.query_service import (
    MarketDataCursorBinding,
    MarketDataQueryExecution,
    MarketDataQueryService,
    MarketDataQueryServiceError,
)
from app.services.market_data.source_policy import (
    MarketDataProviderRoute,
    MarketDataSourcePolicy,
    MarketDataSourcePolicyError,
    MarketDataSourcePolicyRegistry,
)
from app.services.market_data.store import MarketDataStore, MarketDataStoreError

router = APIRouter()

# Preserve the dependency object imported by the existing API tests and
# application overrides while route dependencies now authorize through the
# auth-first wrapper above.
get_market_data_access_authorizer = _get_market_data_access_authorizer

_DAILY_BAR_FREQUENCIES = frozenset({"1d", "1w", "1mo"})
_DAILY_ONLY_FREQUENCIES = frozenset({"1d"})
_PUBLIC_MARKET_DATA_PURPOSES = frozenset({"display", "research", "backtest"})
_RESEARCH_CACHE_FILL_PURPOSE = "research_cache_fill"
_UNDECLARED = frozenset({None})
_CLOSE_OR_UNDECLARED = frozenset({None, "close"})
_UNADJUSTED_OR_UNDECLARED = frozenset({None, "unadjusted"})
_STOCK_FUND_ADJUSTMENTS = frozenset({None, "unadjusted", "qfq", "hfq"})
_CNY_OR_UNDECLARED = frozenset({None, "CNY"})
_SHARE_OR_UNDECLARED = frozenset({None, "share"})
_CONTRACT_OR_UNDECLARED = frozenset({None, "contract"})
_INFLIGHT_LOCAL_FIRST_QUERIES: dict[
    tuple[int, str, str, str, str], asyncio.Future[MarketDataQueryExecution]
] = {}


@lru_cache(maxsize=1)
def _shared_akshare_provider() -> AkShareMarketDataProvider:
    """Retain one process-wide AkShare concurrency gate across HTTP requests."""
    return AkShareMarketDataProvider()


@lru_cache(maxsize=1)
def _shared_openbb_provider() -> OpenBBSubprocessProvider:
    """Retain one process-owned subprocess adapter; env changes require restart."""
    return OpenBBSubprocessProvider.from_environment()


@lru_cache(maxsize=32)
def _default_source_policy_registry(
    openbb_provider: str,
    openbb_markets: tuple[str, ...],
    research_cache_fill_enabled: bool = False,
) -> MarketDataSourcePolicyRegistry:
    """Build the reviewed default policy without importing OpenBB in FastAPI.

    AkShare routes state the exact route-level capability verified by the local
    adapter. OpenBB routes must appear in the static runtime permit matrix;
    operator market configuration can only narrow those permits. Adding a
    paid/licensed route requires a separate server-owned policy and entitlement
    review.
    """
    routes: list[MarketDataProviderRoute] = [
        MarketDataProviderRoute(
            route_id="akshare-stock-primary-v1",
            request_provider="akshare",
            expected_result_provider_ids=frozenset({"akshare"}),
            asset_types=frozenset({"stock"}),
            data_kinds=frozenset({"bars"}),
            frequencies=_DAILY_BAR_FREQUENCIES,
            markets=frozenset({"CN-SSE", "CN-SZSE"}),
            adjustments=_STOCK_FUND_ADJUSTMENTS,
            price_bases=_CLOSE_OR_UNDECLARED,
            currencies=_CNY_OR_UNDECLARED,
            units=_SHARE_OR_UNDECLARED,
            adapter=_shared_akshare_provider(),
            family_id="stock.realtime",
            family_contract_version=FAMILY_CONTRACT_VERSION,
        ),
        # The legacy K-line facade is deliberately a separate full-OHLCV
        # product. It shares the reviewed source function with stock bars but
        # never falls back to the close-only stock.realtime family.
        MarketDataProviderRoute(
            route_id="akshare-stock-kline-legacy-v1",
            request_provider="akshare",
            expected_result_provider_ids=frozenset({"akshare"}),
            asset_types=frozenset({"stock"}),
            data_kinds=frozenset({"bars"}),
            frequencies=_DAILY_BAR_FREQUENCIES,
            markets=frozenset({"CN-SSE", "CN-SZSE"}),
            adjustments=frozenset({"qfq"}),
            price_bases=frozenset({"close"}),
            currencies=frozenset({"CNY"}),
            units=frozenset({"share"}),
            adapter=_shared_akshare_provider(),
            family_id=KLINE_LEGACY_FAMILY_ID,
            family_contract_version=KLINE_LEGACY_CONTRACT_VERSION,
        ),
        # Stock liquidity is a separate product from bars and valuation. The
        # bound family contract emits these exact semantics, which select the
        # adapter's separately reviewed liquidity route rather than a broad
        # reference-series fallback.
        MarketDataProviderRoute(
            route_id="akshare-stock-liquidity-primary-v1",
            request_provider="akshare",
            expected_result_provider_ids=frozenset({"akshare"}),
            asset_types=frozenset({"stock"}),
            data_kinds=frozenset({"reference_series"}),
            frequencies=_DAILY_ONLY_FREQUENCIES,
            markets=frozenset({"CN-SSE", "CN-SZSE"}),
            adjustments=frozenset({"unadjusted"}),
            price_bases=frozenset({"close"}),
            currencies=frozenset({"CNY"}),
            units=frozenset({"share"}),
            adapter=_shared_akshare_provider(),
            family_id="stock.liquidity",
            family_contract_version=FAMILY_CONTRACT_VERSION,
        ),
        MarketDataProviderRoute(
            route_id="akshare-fund-primary-v1",
            request_provider="akshare",
            expected_result_provider_ids=frozenset({"akshare"}),
            asset_types=frozenset({"fund"}),
            data_kinds=frozenset({"bars"}),
            frequencies=_DAILY_BAR_FREQUENCIES,
            markets=frozenset({"CN-SSE", "CN-SZSE"}),
            adjustments=_STOCK_FUND_ADJUSTMENTS,
            price_bases=_CLOSE_OR_UNDECLARED,
            currencies=_CNY_OR_UNDECLARED,
            units=_SHARE_OR_UNDECLARED,
            adapter=_shared_akshare_provider(),
            family_id="fund.realtime",
            family_contract_version=FAMILY_CONTRACT_VERSION,
        ),
        # ETF liquidity has the same narrow contract as stock liquidity, but
        # it retains a distinct policy route and provider route ID so a future
        # NAV/reference product cannot select this endpoint by resemblance.
        MarketDataProviderRoute(
            route_id="akshare-fund-liquidity-primary-v1",
            request_provider="akshare",
            expected_result_provider_ids=frozenset({"akshare"}),
            asset_types=frozenset({"fund"}),
            data_kinds=frozenset({"reference_series"}),
            frequencies=_DAILY_ONLY_FREQUENCIES,
            markets=frozenset({"CN-SSE", "CN-SZSE"}),
            adjustments=frozenset({"unadjusted"}),
            price_bases=frozenset({"close"}),
            currencies=frozenset({"CNY"}),
            units=frozenset({"share"}),
            adapter=_shared_akshare_provider(),
            family_id="fund.liquidity",
            family_contract_version=FAMILY_CONTRACT_VERSION,
        ),
        # ETF NAV is a separately sourced, source-reported reference series.
        # Its family binding and semantic axes prevent it from being selected
        # by either the ETF price-bar or liquidity contract.
        MarketDataProviderRoute(
            route_id="akshare-fund-nav-primary-v1",
            request_provider="akshare",
            expected_result_provider_ids=frozenset({"akshare"}),
            asset_types=frozenset({"fund"}),
            data_kinds=frozenset({"reference_series"}),
            frequencies=_DAILY_ONLY_FREQUENCIES,
            markets=frozenset({"CN-SSE", "CN-SZSE"}),
            adjustments=frozenset({"source_reported"}),
            price_bases=frozenset({"nav"}),
            currencies=frozenset({"CNY"}),
            units=frozenset({"fund_share"}),
            adapter=_shared_akshare_provider(),
            family_id="fund.nav",
            family_contract_version=FAMILY_CONTRACT_VERSION,
            # The reviewed endpoint is only for a listed CN ETF. Product
            # type and listing kind are frozen master-data facts, never
            # inferred from the symbol prefix at request time.
            product_types=frozenset({"ETF"}),
            fund_identity_kinds=frozenset({"LISTING"}),
        ),
        MarketDataProviderRoute(
            route_id="akshare-futures-primary-v1",
            request_provider="akshare",
            expected_result_provider_ids=frozenset({"akshare"}),
            asset_types=frozenset({"futures"}),
            data_kinds=frozenset({"bars"}),
            frequencies=_DAILY_ONLY_FREQUENCIES,
            markets=frozenset({"CFFEX"}),
            adjustments=_UNADJUSTED_OR_UNDECLARED,
            price_bases=_CLOSE_OR_UNDECLARED,
            currencies=_CNY_OR_UNDECLARED,
            units=_CONTRACT_OR_UNDECLARED,
            adapter=_shared_akshare_provider(),
            family_id="futures.realtime",
            family_contract_version=FAMILY_CONTRACT_VERSION,
        ),
        MarketDataProviderRoute(
            route_id="akshare-bond-primary-v1",
            request_provider="akshare",
            expected_result_provider_ids=frozenset({"akshare"}),
            asset_types=frozenset({"bond"}),
            data_kinds=frozenset({"bars"}),
            frequencies=_DAILY_ONLY_FREQUENCIES,
            markets=frozenset({"SSE", "SZSE", "CN-SSE", "CN-SZSE"}),
            adjustments=_UNADJUSTED_OR_UNDECLARED,
            price_bases=_CLOSE_OR_UNDECLARED,
            currencies=_CNY_OR_UNDECLARED,
            units=_UNDECLARED,
            adapter=_shared_akshare_provider(),
            family_id="bond.realtime",
            family_contract_version=FAMILY_CONTRACT_VERSION,
        ),
        MarketDataProviderRoute(
            route_id="akshare-fx-primary-v1",
            request_provider="akshare",
            expected_result_provider_ids=frozenset({"akshare"}),
            asset_types=frozenset({"fx"}),
            data_kinds=frozenset({"bars"}),
            frequencies=_DAILY_ONLY_FREQUENCIES,
            markets=frozenset({"OTC", "CN-OTC"}),
            adjustments=_UNADJUSTED_OR_UNDECLARED,
            price_bases=_CLOSE_OR_UNDECLARED,
            currencies=_UNDECLARED,
            units=_UNDECLARED,
            adapter=_shared_akshare_provider(),
            family_id="fx.realtime",
            family_contract_version=FAMILY_CONTRACT_VERSION,
        ),
        # FX range is a separately versioned market-page product even though
        # it uses the same reviewed AkShare endpoint.  A dedicated route ID
        # lets the adapter revalidate that family/revision pair, so a
        # family-bound range request cannot select the realtime route by
        # sharing its asset, cadence, venue, and semantic axes.
        MarketDataProviderRoute(
            route_id="akshare-fx-range-primary-v1",
            request_provider="akshare",
            expected_result_provider_ids=frozenset({"akshare"}),
            asset_types=frozenset({"fx"}),
            data_kinds=frozenset({"bars"}),
            frequencies=_DAILY_ONLY_FREQUENCIES,
            markets=frozenset({"OTC", "CN-OTC"}),
            adjustments=frozenset({"unadjusted"}),
            price_bases=frozenset({"close"}),
            currencies=_UNDECLARED,
            units=_UNDECLARED,
            adapter=_shared_akshare_provider(),
            family_id="fx.range",
            family_contract_version=FAMILY_CONTRACT_VERSION,
        ),
        MarketDataProviderRoute(
            route_id="akshare-cffex-option-primary-v1",
            request_provider="akshare",
            expected_result_provider_ids=frozenset({"akshare"}),
            asset_types=frozenset({"option"}),
            data_kinds=frozenset({"bars"}),
            frequencies=_DAILY_ONLY_FREQUENCIES,
            markets=frozenset({"CFFEX"}),
            adjustments=_UNADJUSTED_OR_UNDECLARED,
            price_bases=_CLOSE_OR_UNDECLARED,
            currencies=_CNY_OR_UNDECLARED,
            units=_CONTRACT_OR_UNDECLARED,
            adapter=_shared_akshare_provider(),
            family_id="option.realtime",
            family_contract_version=FAMILY_CONTRACT_VERSION,
        ),
    ]
    for permit in approved_openbb_runtime_route_permits(openbb_provider, openbb_markets):
        routes.append(
            MarketDataProviderRoute(
                route_id=permit.route_id,
                request_provider=permit.provider,
                expected_result_provider_ids=frozenset({f"openbb:{permit.provider}"}),
                asset_types=frozenset({permit.asset_type}),
                data_kinds=frozenset({permit.data_kind}),
                frequencies=frozenset({permit.frequency}),
                markets=frozenset({permit.market}),
                adjustments=frozenset({permit.adjustment}),
                price_bases=frozenset({permit.price_basis}),
                currencies=frozenset({permit.currency}),
                units=frozenset({permit.unit}),
                adapter=_shared_openbb_provider(),
                family_id=permit.family_id,
                family_contract_version=permit.family_contract_version,
                provider_endpoint=permit.endpoint,
            )
        )
    allowed_purposes = _PUBLIC_MARKET_DATA_PURPOSES
    if research_cache_fill_enabled:
        allowed_purposes = allowed_purposes | frozenset({_RESEARCH_CACHE_FILL_PURPOSE})
    return MarketDataSourcePolicyRegistry(
        (
            MarketDataSourcePolicy(
                policy_id="market-default-v1",
                allowed_purposes=allowed_purposes,
                routes=tuple(routes),
            ),
        )
    )


def _openbb_markets(settings: object) -> tuple[str, ...]:
    """Read the already-normalized operator allow-list into a cacheable tuple."""
    configured_markets = getattr(settings, "MARKET_DATA_OPENBB_ALLOWED_MARKETS", "")
    if not isinstance(configured_markets, str):
        return ()
    return tuple(item.strip() for item in configured_markets.split(",") if item.strip())


def _openbb_provider(settings: object) -> str:
    """Keep incomplete test/deployment settings from becoming a provider grant."""
    configured_provider = getattr(settings, "MARKET_DATA_OPENBB_PROVIDER", "yfinance")
    if not isinstance(configured_provider, str) or not configured_provider.strip():
        return "yfinance"
    return configured_provider.strip()


def _source_policies_from_settings(settings: object) -> MarketDataSourcePolicyRegistry:
    """Build the full reviewed policy before the ledger narrows capabilities."""
    return _default_source_policy_registry(
        _openbb_provider(settings),
        _openbb_markets(settings),
        # Cache-fill is deliberately present in the static reviewed policy.
        # Its environment kill switch and durable lifecycle evidence are
        # intersected by ``MarketDataCapabilityLedger``; omitting it here
        # would turn a setting into an implicit policy rewrite.
        research_cache_fill_enabled=True,
    )


async def evaluate_market_data_capabilities(
    db: AsyncSession,
    *,
    settings: object | None = None,
) -> MarketDataCapabilityEvaluation:
    """Read effective capability state from durable lifecycle evidence.

    Callers must authorize their principal before invoking this helper.  It
    intentionally has no FastAPI dependencies so request, research, and
    runtime consumers can share one fail-closed evaluation without manually
    calling a dependency function.
    """
    effective_settings = get_settings() if settings is None else settings
    return await MarketDataCapabilityLedger(db).evaluate(
        settings=effective_settings,
        source_policies=_source_policies_from_settings(effective_settings),
    )


def build_market_data_query_service(
    db: AsyncSession,
    capabilities: MarketDataCapabilityEvaluation,
) -> MarketDataQueryService:
    """Compose a query service from one already-authorized durable evaluation."""
    if not isinstance(capabilities, MarketDataCapabilityEvaluation):
        raise TypeError("capabilities must be a MarketDataCapabilityEvaluation")
    return MarketDataQueryService(
        resolver=MarketDataQueryResolver(
            catalog=DataCatalogResolver(db),
            identities=MarketDataIdentityResolver(db),
        ),
        store=MarketDataStore(db),
        source_policies=capabilities.effective_source_policies,
        allow_online_fetch=capabilities.response.online_fetch_enabled,
        # Keep the full reviewed policy for local reads.  Durable deployment
        # evidence narrows provider I/O only, so an expired route attestation
        # cannot make already-persisted local facts disappear.
        online_route_ids=capabilities.effective_route_ids,
    )


async def get_market_data_capability_evaluation(
    db: AsyncSession = Depends(get_db),
    _access: MarketDataQueryAccess = Depends(get_authorized_market_data_access),
) -> MarketDataCapabilityEvaluation:
    """Read durable lifecycle state only after current data-read authorization."""
    return await evaluate_market_data_capabilities(db)


async def get_market_data_query_service(
    db: AsyncSession = Depends(get_db),
    capabilities: MarketDataCapabilityEvaluation = Depends(get_market_data_capability_evaluation),
) -> MarketDataQueryService:
    """Compose the v2 service from the same durable capability read as the endpoint."""
    return build_market_data_query_service(db, capabilities)


def get_market_data_query_bundle_request(
    http_request: Request,
    _read_authorized: None = Depends(require_authorized_market_data_read),
    asset_type: str = Query(..., min_length=1, max_length=32, description="Market-page asset type"),
    family_id: str | None = Query(
        default=None,
        max_length=128,
        description="Optional stable asset.family display-family key",
    ),
) -> MarketDataQueryBundleRequest:
    """Parse the static bundle selector before entering the authenticated route.

    This dependency intentionally accepts no symbol, provider, endpoint,
    date, mode, or free-form data-kind axis.  Those values belong to a later
    exact query contract, and accepting them here would make a static product
    declaration look like a data query.
    """
    allowed_keys = {"asset_type", "family_id"}
    query_keys = set(http_request.query_params.keys())
    if query_keys - allowed_keys:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "DATA_FAMILY_REQUEST_INVALID"},
        )
    if any(len(http_request.query_params.getlist(key)) != 1 for key in query_keys):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "DATA_FAMILY_REQUEST_INVALID"},
        )
    try:
        return MarketDataQueryBundleRequest.model_validate(
            {"asset_type": asset_type, "family_id": family_id}
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "DATA_FAMILY_REQUEST_INVALID"},
        ) from exc


@router.get(
    "/market-data/capabilities",
    response_model=MarketDataCapabilitiesResponse,
    summary="Read effective market-data rollout capabilities",
)
async def get_market_data_capabilities(
    capabilities: MarketDataCapabilityEvaluation = Depends(get_market_data_capability_evaluation),
) -> MarketDataCapabilitiesResponse:
    """Return durable effective state after current data-read authorization."""
    return capabilities.response


async def execute_market_data_query_with_singleflight(
    *,
    service: MarketDataQueryService,
    db: AsyncSession,
    request: MarketDataQueryRequest,
    cursor_binding: MarketDataCursorBinding | None = None,
    access: MarketDataQueryAccess | None = None,
) -> MarketDataQueryExecution:
    """Coalesce equivalent current local-first misses until their receipt commits.

    The first request owns the external call and commits its durable receipt.
    Same-loop followers wait for that complete transaction and then re-read
    their own session, which leaves them with a normal local result rather
    than a second provider request. Strict historical requests and local-only
    requests have no interactive provider path and bypass this coordinator.
    The service additionally obtains a database-backed, fenced lease for each
    exact coverage gap before it calls a provider, so separate workers become
    lease followers and re-read local facts. This process-local coordinator
    does not itself prove a production deployment: real multi-worker,
    database-dialect, clock, and takeover validation remains an acceptance
    requirement.
    """
    if cursor_binding is None and access is not None:
        binding = MarketDataCursorBinding(
            principal_scope=access.principal.principal_scope,
            tenant_scope=access.principal.tenant_scope,
            entitlement_revision=access.principal.entitlement_revision,
        )
    else:
        binding = cursor_binding or MarketDataCursorBinding()
    if request.mode != "local_first" or request.knowledge_cutoff is not None:
        return await service.execute(request, cursor_binding=binding, access=access)

    loop = asyncio.get_running_loop()
    key = (
        id(loop),
        request.query_fingerprint,
        binding.principal_scope,
        binding.tenant_scope,
        binding.entitlement_revision,
    )
    completion = _INFLIGHT_LOCAL_FIRST_QUERIES.get(key)
    if completion is None:
        completion = loop.create_future()
        _INFLIGHT_LOCAL_FIRST_QUERIES[key] = completion
        try:
            execution = await service.execute(request, cursor_binding=binding, access=access)
            if execution.fetches:
                await db.commit()
        except BaseException:
            # A leader owns a request-scoped database session. Do not detach it
            # into a background task after cancellation or failure; followers
            # receive cancellation and may retry through a fresh request.
            if not completion.done():
                completion.cancel()
            raise
        else:
            completion.set_result(execution)
            return execution
        finally:
            if _INFLIGHT_LOCAL_FIRST_QUERIES.get(key) is completion:
                _INFLIGHT_LOCAL_FIRST_QUERIES.pop(key, None)

    await asyncio.shield(completion)
    # Authentication and other request dependencies may already have issued a
    # read on this session. MySQL's default REPEATABLE READ would otherwise
    # keep that pre-leader snapshot after the leader's receipt commit, causing
    # this follower to miss the new local revisions and fetch the provider a
    # second time. A follower has not performed v2 writes, so ending its
    # read-only transaction here is safe and forces the re-read below to begin
    # from a fresh database snapshot.
    await db.rollback()
    follower_access = access
    follower_binding = binding
    if access is not None:
        # The leader can have spent arbitrary time in provider I/O.  Rebuild
        # this follower's execution context after its old read transaction is
        # ended, so a changed role/entitlement cannot be smuggled through the
        # coalesced local reread.
        current_principal = await access.authorizer.revalidate_principal(principal=access.principal)
        follower_access = MarketDataQueryAccess(
            principal=current_principal,
            authorizer=access.authorizer,
        )
        follower_binding = MarketDataCursorBinding(
            principal_scope=current_principal.principal_scope,
            tenant_scope=current_principal.tenant_scope,
            entitlement_revision=current_principal.entitlement_revision,
        )
    return await service.execute(
        request,
        cursor_binding=follower_binding,
        access=follower_access,
    )


@router.get(
    "/market-instruments/query-bundle",
    response_model=MarketDataQueryBundleResponse,
    summary="Read server-owned market-page data-family contracts",
)
async def get_market_data_query_bundle(
    request: MarketDataQueryBundleRequest = Depends(get_market_data_query_bundle_request),
    capabilities: MarketDataCapabilityEvaluation = Depends(get_market_data_capability_evaluation),
) -> MarketDataQueryBundleResponse:
    """Return static product contracts without resolving data or invoking providers.

    A ``ready`` entry remains only a server-owned product declaration. The
    caller must still obtain the exact-identity ``query-contract`` and execute
    the v2 data endpoint; the bundle itself cannot trigger online fetches or
    create a fallback data path.
    """
    if not capabilities.response.query_v2_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "MARKET_DATA_QUERY_V2_DISABLED"},
        )
    # The legacy K-line product is server-owned by the compatibility facade.
    # Do not let a public bundle selector enter the registry and turn this
    # private control-plane boundary into an ordinary 422 family lookup.
    if request.family_id == KLINE_LEGACY_FAMILY_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "MARKET_DATA_PRIVATE_FAMILY"},
        )
    try:
        return DEFAULT_DATASET_CONTRACT_REGISTRY.bundle_for(request)
    except DatasetContractRegistryError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code},
        ) from exc


@router.post(
    "/queries",
    response_model=MarketDataQueryResponse,
    summary="Query normalized local-first market data",
)
async def query_market_data(
    request: PublicMarketDataQueryRequest,
    db: AsyncSession = Depends(get_db),
    access: MarketDataQueryAccess = Depends(get_authorized_market_data_access),
    capabilities: MarketDataCapabilityEvaluation = Depends(get_market_data_capability_evaluation),
    service: MarketDataQueryService = Depends(get_market_data_query_service),
) -> MarketDataQueryResponse:
    """Execute a typed v2 data query after the deployment gate is enabled."""
    if not capabilities.response.query_v2_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "MARKET_DATA_QUERY_V2_DISABLED"},
        )
    # ``stock.kline_legacy`` is a private compatibility contract.  Its fixed
    # server-issued request is consumed only by the legacy K-line facade after
    # it has validated the legacy selector and frozen identity.  Accepting it
    # here would let an HTTP caller bypass that boundary and select a product
    # which is intentionally absent from public bundles and query contracts.
    if request.family_id == KLINE_LEGACY_FAMILY_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "MARKET_DATA_PRIVATE_FAMILY"},
        )
    if (
        request.purpose == _RESEARCH_CACHE_FILL_PURPOSE
        and not capabilities.response.research_cache_fill_enabled
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "MARKET_DATA_RESEARCH_CACHE_FILL_DISABLED"},
        )
    try:
        execution = await execute_market_data_query_with_singleflight(
            service=service,
            db=db,
            request=request,
            cursor_binding=MarketDataCursorBinding(
                principal_scope=access.principal.principal_scope,
                tenant_scope=access.principal.tenant_scope,
                entitlement_revision=access.principal.entitlement_revision,
            ),
            access=access,
        )
    except (
        MarketDataAuthorizationError,
        MarketDataQueryResolutionError,
        MarketDataIdentityResolutionError,
        MarketDataSourcePolicyError,
        MarketDataQueryServiceError,
        MarketDataStoreError,
    ) as exc:
        await db.rollback()
        raise _market_data_http_error(exc.code) from exc
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "MARKET_DATA_WRITE_FAILED"},
        ) from exc
    return _response_from_execution(execution)


def _market_data_http_error(code: str) -> HTTPException:
    """Map stable internal codes to bounded public HTTP semantics."""
    if code in {
        "MARKET_DATA_READ_ENTITLEMENT_DENIED",
        "MARKET_DATA_ACCESS_REQUIRED",
        "MARKET_DATA_PRINCIPAL_REVOKED",
        "MARKET_DATA_ACCESS_CHANGED_DURING_FETCH",
        "SOURCE_REGISTRY_UNREGISTERED",
        "SOURCE_REGISTRY_DISABLED",
        "SOURCE_REGISTRY_ASSET_TYPE_DENIED",
        "SOURCE_LICENSE_DENIED",
        "SOURCE_USE_DENIED",
        "SOURCE_EFFECTIVE_WINDOW_DENIED",
        "SOURCE_JURISDICTION_DENIED",
        "SOURCE_RETENTION_DENIED",
        "SOURCE_REDISTRIBUTION_DENIED",
        "SOURCE_ROUTE_AUTHORIZATION_DENIED",
        "CURSOR_ACCESS_GRANT_MISMATCH",
    }:
        response_status = status.HTTP_403_FORBIDDEN
    elif code == "IDENTITY_NOT_FOUND":
        response_status = status.HTTP_404_NOT_FOUND
    elif code in {
        "DATASET_UNAVAILABLE",
        "DATA_FAMILY_CONTRACT_VERSION_UNSUPPORTED",
        "DATA_FAMILY_QUERY_CONTRACT_MISMATCH",
        "DATA_FAMILY_UNCONFIGURED",
        "SOURCE_POLICY_UNAVAILABLE",
        "SOURCE_POLICY_PURPOSE_DENIED",
        "ONLINE_FETCH_DISABLED",
        "MARKET_DATA_RESEARCH_CACHE_FILL_DISABLED",
    }:
        response_status = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        response_status = status.HTTP_422_UNPROCESSABLE_CONTENT
    return HTTPException(status_code=response_status, detail={"code": code})


def _response_from_execution(execution: MarketDataQueryExecution) -> MarketDataQueryResponse:
    """Convert internal immutable DTOs into the fixed public response shape."""
    context = execution.context
    query = context.query
    coverage = execution.coverage
    source_policy_id = query.source_policy_id
    if source_policy_id is None:
        # Resolver/context contracts make this unreachable; keep the response
        # boundary fail-closed if a future caller constructs one incorrectly.
        raise MarketDataQueryServiceError("SOURCE_POLICY_REQUIRED")
    family_id = query.family_id
    family_contract_version = query.family_contract_version
    if family_id is None or family_contract_version is None:
        # Internal migration/import DTOs may remain unbound until they are
        # assigned a reviewed family contract. A public response may not:
        # returning it would weaken the API's required binding invariant.
        raise MarketDataQueryServiceError("DATA_FAMILY_BINDING_REQUIRED")
    return MarketDataQueryResponse(
        query_id=query.query_fingerprint,
        canonical_id=query.canonical_id,
        dataset_code=query.dataset_code,
        asset_type=context.identity.asset_type,
        instrument_metadata_version=query.instrument_metadata_version,
        data_kind=query.data_kind,
        frequency=query.frequency or "snapshot",
        source_policy_id=source_policy_id,
        family_id=family_id,
        family_contract_version=family_contract_version,
        knowledge_cutoff=execution.knowledge_cutoff,
        identity_knowledge_cutoff=execution.identity_knowledge_cutoff,
        observations=tuple(
            MarketDataObservationResponse(
                revision_id=item.revision_id,
                source_snapshot_id=item.source_snapshot_id,
                event_at=item.event_at,
                available_at=item.available_at,
                committed_at=item.committed_at,
                revision_number=item.revision_number,
                quality=item.quality.value,
                fields=dict(item.fields),
            )
            for item in execution.observations
        ),
        next_cursor=execution.next_cursor,
        coverage=MarketDataCoverageResponse(
            status=coverage.status.value,
            expected_event_count=len(coverage.expected_event_keys),
            accepted_event_count=len(coverage.accepted_event_keys),
            missing_event_count=len(coverage.missing_event_keys),
            coverage_ratio=coverage.coverage_ratio,
            gaps=tuple(
                MarketDataCoverageGapResponse(
                    position=gap.position.value,
                    event_at=tuple(event.event_at for event in gap.event_keys),
                    fetch_start=gap.fetch_window.start_at,
                    fetch_end=gap.fetch_window.end_at,
                )
                for gap in coverage.gaps
            ),
            rejection_counts=dict(coverage.rejection_counts),
            calendar_reason=coverage.calendar_reason,
        ),
        fetches=tuple(
            MarketDataFetchResponse(
                route_id=item.route_id,
                provider_id=item.provider_id,
                source_snapshot_id=item.source_snapshot_id,
                observation_revision_ids=item.observation_revision_ids,
                passing_observation_count=item.passing_observation_count,
                failed_observation_count=item.failed_observation_count,
            )
            for item in execution.fetches
        ),
        warnings=tuple(
            MarketDataQueryWarningResponse(
                code=item.code,
                route_id=item.route_id,
                provider_id=item.provider_id,
            )
            for item in execution.warnings
        ),
        refresh_status=execution.refresh_status,
        historical_status=getattr(execution, "historical_status", None),
    )
