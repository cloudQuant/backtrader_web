"""Versioned API for the Iteration 197 normalized local-first query path."""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.data.deps import get_current_db_user
from app.config import Settings, get_settings
from app.db.database import get_db
from app.schemas.market_data_platform import (
    MarketDataCoverageGapResponse,
    MarketDataCoverageResponse,
    MarketDataFetchResponse,
    MarketDataObservationResponse,
    MarketDataQueryBundleRequest,
    MarketDataQueryBundleResponse,
    MarketDataQueryRequest,
    MarketDataQueryResponse,
    MarketDataQueryWarningResponse,
)
from app.services.market_data.akshare_provider import AkShareMarketDataProvider
from app.services.market_data.catalog import DataCatalogResolver
from app.services.market_data.dataset_contracts import (
    DEFAULT_DATASET_CONTRACT_REGISTRY,
    DatasetContractRegistryError,
)
from app.services.market_data.identity import (
    MarketDataIdentityResolutionError,
    MarketDataIdentityResolver,
)
from app.services.market_data.providers import OpenBBSubprocessProvider
from app.services.market_data.query_resolution import (
    MarketDataQueryResolutionError,
    MarketDataQueryResolver,
)
from app.services.market_data.query_service import (
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

_DAILY_BAR_FREQUENCIES = frozenset({"1d", "1w", "1mo"})
_DAILY_ONLY_FREQUENCIES = frozenset({"1d"})
_OPENBB_ASSET_TYPES = frozenset({"stock", "futures", "fund", "fx", "crypto"})
_PUBLIC_MARKET_DATA_PURPOSES = frozenset({"display", "research", "backtest"})
_UNDECLARED = frozenset({None})
_CLOSE_OR_UNDECLARED = frozenset({None, "close"})
_UNADJUSTED_OR_UNDECLARED = frozenset({None, "unadjusted"})
_STOCK_FUND_ADJUSTMENTS = frozenset({None, "unadjusted", "qfq", "hfq"})
_CNY_OR_UNDECLARED = frozenset({None, "CNY"})
_SHARE_OR_UNDECLARED = frozenset({None, "share"})
_CONTRACT_OR_UNDECLARED = frozenset({None, "contract"})
_INFLIGHT_LOCAL_FIRST_QUERIES: dict[tuple[int, str], asyncio.Future[MarketDataQueryExecution]] = {}


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
) -> MarketDataSourcePolicyRegistry:
    """Build the reviewed default policy without importing OpenBB in FastAPI.

    AkShare routes state the exact route-level capability verified by the local
    adapter.  OpenBB is present only when an operator supplies a nonempty venue
    allow-list and is restricted to provider-native, undeclared semantics until
    the runner can evidence conversions.  Adding a paid/licensed route requires
    a separate server-owned policy and entitlement review.
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
        ),
    ]
    if openbb_markets:
        routes.append(
            MarketDataProviderRoute(
                route_id=f"openbb-{openbb_provider}-fallback-v1",
                request_provider=openbb_provider,
                expected_result_provider_ids=frozenset({f"openbb:{openbb_provider}"}),
                asset_types=_OPENBB_ASSET_TYPES,
                data_kinds=frozenset({"bars"}),
                # The isolated yfinance runner has a verified date-inclusive
                # conversion only for date-aligned bars. Intraday semantics
                # remain unapproved until a provider-specific half-open
                # contract is added and tested.
                frequencies=_DAILY_BAR_FREQUENCIES,
                markets=frozenset(openbb_markets),
                adjustments=_UNDECLARED,
                price_bases=_UNDECLARED,
                currencies=_UNDECLARED,
                units=_UNDECLARED,
                adapter=_shared_openbb_provider(),
            )
        )
    return MarketDataSourcePolicyRegistry(
        (
            MarketDataSourcePolicy(
                policy_id="market-default-v1",
                allowed_purposes=_PUBLIC_MARKET_DATA_PURPOSES,
                routes=tuple(routes),
            ),
        )
    )


def _openbb_markets(settings: Settings) -> tuple[str, ...]:
    """Read the already-normalized operator allow-list into a cacheable tuple."""
    return tuple(
        item.strip()
        for item in settings.MARKET_DATA_OPENBB_ALLOWED_MARKETS.split(",")
        if item.strip()
    )


def get_market_data_query_service(
    db: AsyncSession = Depends(get_db),
) -> MarketDataQueryService:
    """Compose the v2 query service from the request-scoped database session."""
    settings = get_settings()
    return MarketDataQueryService(
        resolver=MarketDataQueryResolver(
            catalog=DataCatalogResolver(db),
            identities=MarketDataIdentityResolver(db),
        ),
        store=MarketDataStore(db),
        source_policies=_default_source_policy_registry(
            settings.MARKET_DATA_OPENBB_PROVIDER,
            _openbb_markets(settings),
        ),
        allow_online_fetch=settings.MARKET_DATA_ONLINE_FETCH_ENABLED,
    )


def get_market_data_query_bundle_request(
    http_request: Request,
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


async def execute_market_data_query_with_singleflight(
    *,
    service: MarketDataQueryService,
    db: AsyncSession,
    request: MarketDataQueryRequest,
) -> MarketDataQueryExecution:
    """Coalesce equivalent current local-first misses until their receipt commits.

    The first request owns the external call and commits its durable receipt.
    Same-loop followers wait for that complete transaction and then re-read
    their own session, which leaves them with a normal local result rather
    than a second provider request. Strict historical requests and local-only
    requests have no interactive provider path and bypass this coordinator.
    Database uniqueness still protects cross-process races; operator-scale
    multi-worker leasing remains a separate deployment concern.
    """
    if request.mode != "local_first" or request.knowledge_cutoff is not None:
        return await service.execute(request)

    loop = asyncio.get_running_loop()
    key = (id(loop), request.query_fingerprint)
    completion = _INFLIGHT_LOCAL_FIRST_QUERIES.get(key)
    if completion is None:
        completion = loop.create_future()
        _INFLIGHT_LOCAL_FIRST_QUERIES[key] = completion
        try:
            execution = await service.execute(request)
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
    return await service.execute(request)


@router.get(
    "/market-instruments/query-bundle",
    response_model=MarketDataQueryBundleResponse,
    summary="Read server-owned market-page data-family contracts",
)
async def get_market_data_query_bundle(
    request: MarketDataQueryBundleRequest = Depends(get_market_data_query_bundle_request),
    current_user: Any = Depends(get_current_db_user),
) -> MarketDataQueryBundleResponse:
    """Return static product contracts without resolving data or invoking providers.

    A ``ready`` entry remains only a bars compatibility declaration.  The
    caller must still obtain the existing exact identity ``query-contract``
    and execute the v2 data endpoint; the bundle itself cannot trigger online
    fetches or create a fallback data path.
    """
    del current_user
    if not get_settings().MARKET_DATA_QUERY_V2_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "MARKET_DATA_QUERY_V2_DISABLED"},
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
    request: MarketDataQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_db_user),
    service: MarketDataQueryService = Depends(get_market_data_query_service),
) -> MarketDataQueryResponse:
    """Execute a typed v2 data query after the deployment gate is enabled."""
    del current_user  # Authentication is a required transport boundary for this public policy.
    if not get_settings().MARKET_DATA_QUERY_V2_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "MARKET_DATA_QUERY_V2_DISABLED"},
        )
    try:
        execution = await execute_market_data_query_with_singleflight(
            service=service,
            db=db,
            request=request,
        )
    except (
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
    if code == "IDENTITY_NOT_FOUND":
        response_status = status.HTTP_404_NOT_FOUND
    elif code in {
        "DATASET_UNAVAILABLE",
        "SOURCE_POLICY_UNAVAILABLE",
        "SOURCE_POLICY_PURPOSE_DENIED",
        "ONLINE_FETCH_DISABLED",
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
    return MarketDataQueryResponse(
        query_id=query.query_fingerprint,
        canonical_id=query.canonical_id,
        dataset_code=query.dataset_code,
        asset_type=context.identity.asset_type,
        instrument_metadata_version=query.instrument_metadata_version,
        data_kind=query.data_kind,
        frequency=query.frequency or "snapshot",
        source_policy_id=source_policy_id,
        # The resolver always constructs these attributes.  Keep the HTTP
        # projection tolerant of older read-only execution fixtures during the
        # staged rollout, where an unbound compatibility query predates the
        # family-control-plane fields.
        family_id=getattr(query, "family_id", None),
        family_contract_version=getattr(query, "family_contract_version", None),
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
    )
