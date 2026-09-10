"""
Market data API routes.
"""

import logging
import typing
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.data.deps import (
    get_market_data_access_authorizer,
    require_authorized_market_data_read,
)
from app.api.deps import get_current_user
from app.config import get_settings
from app.db.database import get_db
from app.services.market_data.access import MarketDataAccessAuthorizer, MarketDataAuthorizationError
from app.services.market_data.dataset_contracts import DatasetContractRegistryError
from app.services.market_data.legacy_contract import LegacyMarketDataQueryContractResolver
from app.services.market_instrument import (
    LegacyMarketDataOnlineRefreshDisabledError,
    MarketAssetType,
    MarketInstrumentService,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def get_market_instrument_service() -> MarketInstrumentService:
    return MarketInstrumentService()


def get_legacy_market_data_query_contract_resolver(
    db: AsyncSession = Depends(get_db),
) -> LegacyMarketDataQueryContractResolver:
    """Build the read-only v2 compatibility bridge for a request database session."""
    settings = get_settings()
    allowed_markets = frozenset(
        item.strip()
        for item in str(getattr(settings, "MARKET_DATA_OPENBB_ALLOWED_MARKETS", "")).split(",")
        if item.strip()
    )
    return LegacyMarketDataQueryContractResolver(
        db,
        openbb_provider=str(getattr(settings, "MARKET_DATA_OPENBB_PROVIDER", "yfinance")),
        openbb_allowed_markets=allowed_markets,
    )


@router.get(
    "/market-instruments/query-contract",
    summary="Resolve a local-first market-data query contract",
    response_model=None,
)
async def get_market_data_query_contract(
    symbol: str = Query(
        ..., min_length=1, description="Exact instrument code from approved master data"
    ),
    asset_type: MarketAssetType = Query("stock", description="Instrument type"),
    period: str = Query("daily", description="Period: daily/weekly/monthly"),
    family_id: str | None = Query(
        default=None,
        max_length=128,
        description="Optional exact market-page family selected from the server bundle",
    ),
    _read_authorized: None = Depends(require_authorized_market_data_read),
    query_contracts: LegacyMarketDataQueryContractResolver = Depends(
        get_legacy_market_data_query_contract_resolver
    ),
) -> typing.Any:
    """Return a strict v2 template without touching legacy data providers.

    A page uses this probe before the legacy lookup so a catalog-backed,
    uniquely registered identity can take the normalized local-first path on
    its first request. The resolver does not derive an identity from a nearby
    symbol and the endpoint intentionally returns 404 if bootstrap or
    approved master data is incomplete; clients then retain the legacy path.
    """
    if not get_settings().MARKET_DATA_QUERY_V2_ENABLED:
        raise HTTPException(
            status_code=503,
            detail={"code": "MARKET_DATA_QUERY_V2_DISABLED"},
        )
    try:
        resolve_args: dict[str, str] = {
            "asset_type": asset_type,
            "symbol": symbol,
            "period": period,
        }
        if family_id is not None:
            resolve_args["family_id"] = family_id
        contract = await query_contracts.resolve(**resolve_args)
    except DatasetContractRegistryError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code},
        ) from exc
    except SQLAlchemyError as exc:
        # A partially migrated metadata store is an unavailable compatibility
        # probe, not a server trace exposed to a market-page client.
        logger.warning("market-data v2 query contract unavailable")
        raise HTTPException(
            status_code=503,
            detail={"code": "MARKET_DATA_QUERY_CONTRACT_UNAVAILABLE"},
        ) from exc
    if contract is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "MARKET_DATA_QUERY_CONTRACT_UNAVAILABLE"},
        )
    return contract


@router.get("/kline", summary="Query K-line data", response_model=None)
async def get_kline_data(
    symbol: str = Query(..., description="Stock code, e.g., 000001.SZ"),
    start_date: str = Query(..., description="Start date YYYY-MM-DD"),
    end_date: str = Query(..., description="End date YYYY-MM-DD"),
    period: str = Query("daily", description="Period: daily/weekly/monthly"),
    current_user: typing.Any = Depends(get_current_user),
) -> typing.Any:
    """Fetch A-share kline OHLCV data via AkShare.

    Args:
        symbol: Stock code (e.g., 000001.SZ).
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.
        period: Data period (daily/weekly/monthly).

    Returns:
        A payload containing `kline` arrays and a flat `records` list for UI display.
    """
    import akshare as ak

    code = symbol.split(".")[0]
    start_str = start_date.replace("-", "")
    end_str = end_date.replace("-", "")

    try:
        df = ak.stock_zh_a_hist(
            symbol=code,
            period=period,
            start_date=start_str,
            end_date=end_str,
            adjust="qfq",
            timeout=10,
        )

        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data retrieved for {symbol}")

        # akshare returns Chinese column names, rename to English
        df = df.rename(
            columns={
                "日期": "date",  # Date
                "开盘": "open",  # Open
                "最高": "high",  # High
                "最低": "low",  # Low
                "收盘": "close",  # Close
                "成交量": "volume",  # Volume
                "涨跌幅": "change_pct",  # Change percentage
            }
        )

        records = []
        dates = []
        ohlc = []
        volumes = []

        for _, row in df.iterrows():
            d = str(row["date"])
            dates.append(d)
            o = round(float(row["open"]), 2)
            h = round(float(row["high"]), 2)
            low = round(float(row["low"]), 2)
            c = round(float(row["close"]), 2)
            v = int(row["volume"])
            change = round(float(row.get("change_pct", 0)), 2)

            ohlc.append([o, c, low, h])
            volumes.append(v)
            records.append(
                {
                    "date": d,
                    "open": o,
                    "high": h,
                    "low": low,
                    "close": c,
                    "volume": v,
                    "change": change,
                }
            )

        return {
            "symbol": symbol,
            "count": len(records),
            "kline": {"dates": dates, "ohlc": ohlc, "volumes": volumes},
            "records": records,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch market data: {symbol}, {e}")
        raise HTTPException(status_code=500, detail=f"Query failed: {e}") from e


@router.get(
    "/market-instruments/lookup",
    summary="Lookup aggregated market instrument data",
    response_model=None,
)
async def lookup_market_instrument(
    symbol: str = Query(..., min_length=1, description="Instrument code, e.g. 000001 or RB2510"),
    asset_type: MarketAssetType = Query("stock", description="Instrument type"),
    start_date: date | None = Query(None, description="Start date YYYY-MM-DD"),
    end_date: date | None = Query(None, description="End date YYYY-MM-DD"),
    period: str = Query("daily", description="Period: daily/weekly/monthly"),
    market: str | None = Query(None, description="Futures market, default CF"),
    refresh_online: bool = Query(
        False,
        description="Deprecated legacy online refresh; use the v2 local-first query endpoint",
    ),
    current_user: typing.Any = Depends(get_current_user),
    service: MarketInstrumentService = Depends(get_market_instrument_service),
    access_authorizer: MarketDataAccessAuthorizer = Depends(get_market_data_access_authorizer),
    query_contracts: LegacyMarketDataQueryContractResolver = Depends(
        get_legacy_market_data_query_contract_resolver
    ),
) -> typing.Any:
    """Return a normalized snapshot, historical rows, and derived indicators."""
    try:
        payload = await service.lookup(
            asset_type=asset_type,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            period=period,
            market=market,
            refresh_online=refresh_online,
        )
        # The legacy shape remains authoritative until the v2 rollout is
        # explicitly enabled and its catalog/master-data prerequisites are
        # satisfied.  Absence of this optional field is a safe instruction for
        # clients to continue using the existing compatibility endpoint.
        if get_settings().MARKET_DATA_QUERY_V2_ENABLED:
            try:
                principal = await access_authorizer.principal_for_user(current_user)
                access_authorizer.require_read_data(principal=principal)
            except MarketDataAuthorizationError:
                # Keep the legacy lookup's historic authorization semantics,
                # but never mint or disclose a v2 catalog/identity template to
                # a caller without the independent data-read entitlement.
                contract = None
            except SQLAlchemyError:
                # A current-principal check is optional on this legacy route.
                # Its metadata outage must not invalidate an already completed
                # compatibility lookup, and must never cause a v2 disclosure.
                logger.warning("market-data v2 compatibility authorization unavailable")
                contract = None
            else:
                try:
                    contract = await query_contracts.resolve(
                        asset_type=asset_type,
                        symbol=symbol,
                        period=period,
                    )
                except DatasetContractRegistryError:
                    # The derived family is not executable. Keep the legacy
                    # response usable without advertising a generic v2 route.
                    contract = None
                except SQLAlchemyError:
                    # The optional bridge must never turn a completed legacy
                    # lookup into a 500. Its metadata outage omits only the
                    # optional v2 template.
                    logger.warning("market-data v2 compatibility contract unavailable")
                    contract = None
            if contract is not None:
                # A legacy lookup may advertise a v2 template only with an
                # explicit echo of the exact symbol and canonical identity
                # used to mint it.  Do not let a mixed or malformed metadata
                # response turn an otherwise complete legacy read into a 500,
                # or advertise a contract that the client cannot safely bind.
                contract_request = contract.get("request") if isinstance(contract, dict) else None
                contract_identity = (
                    contract_request.get("identity") if isinstance(contract_request, dict) else None
                )
                canonical_id = (
                    contract_identity.get("canonical_id")
                    if isinstance(contract_identity, dict)
                    else None
                )
                if not isinstance(canonical_id, str) or not canonical_id.strip():
                    logger.warning("market-data v2 compatibility contract malformed")
                else:
                    payload["query_contract"] = contract
                    # The frontend compares all three values before allowing
                    # this compatibility bridge to issue a v2 query, so a
                    # stale/mixed legacy payload cannot redirect a current
                    # symbol to a different canonical instrument.
                    payload["query_contract_symbol"] = symbol.strip()
                    payload["query_contract_canonical_id"] = canonical_id
        return payload
    except LegacyMarketDataOnlineRefreshDisabledError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/market-instruments/options", summary="List selectable market instruments", response_model=None
)
async def list_market_instrument_options(
    asset_type: MarketAssetType = Query("stock", description="Instrument type"),
    search: str = Query("", description="Search by symbol, name, market, or variety"),
    limit: int = Query(80, ge=1, le=200, description="Maximum number of options"),
    current_user: typing.Any = Depends(get_current_user),
    service: MarketInstrumentService = Depends(get_market_instrument_service),
) -> typing.Any:
    """Return selectable instruments for the market data query page."""
    try:
        return await service.list_instruments(
            asset_type=asset_type,
            search=search,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
