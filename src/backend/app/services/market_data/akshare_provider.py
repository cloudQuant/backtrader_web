"""Explicit, local-first-safe AkShare provider adapter.

This module deliberately does not call the legacy market-instrument services.
It knows only a small, reviewed route registry and invokes a route with the
exact provider symbol supplied by the resolved master-data identity.  A missing
route is a typed failure: it is never replaced with a market-wide lookup,
another asset type, or sample data.

AkShare is synchronous, so endpoint invocation happens only in an isolated,
killable subprocess group. The parent validates its receipt before applying the
existing normalization and provenance logic.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import math
import os
import re
import shlex
import signal
import tempfile
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from importlib import metadata
from pathlib import Path
from types import MappingProxyType
from typing import Any

from app.services.market_data.dataset_contracts import (
    FAMILY_CONTRACT_VERSION,
    KLINE_LEGACY_CONTRACT_VERSION,
    KLINE_LEGACY_FAMILY_ID,
)
from app.services.market_data.provider_contracts import (
    AKSHARE_PROVIDER_CONTRACT_REGISTRY,
    AKSHARE_RESPONSE_FIELD_ALIASES,
    PreparedProviderRequest,
    ProviderContract,
    ProviderContractError,
)
from app.services.market_data.providers import (
    MarketDataProviderRequest,
    ProviderFetchResult,
    ProviderMarketObservation,
)

_UTC = timezone.utc
_MAX_RESPONSE_ROWS = 50_000
_MAX_PROVENANCE_BYTES = 10 * 1024 * 1024
AKSHARE_RUNNER_PROTOCOL_VERSION = "akshare-market-data-v1"
_MAX_RUNNER_OUTPUT_BYTES = 10 * 1024 * 1024
_RUNNER_READ_CHUNK_BYTES = 64 * 1024
_ALL_BAR_FREQUENCIES = frozenset({"5min", "30min", "1h", "1d", "1w", "1mo"})
_DAILY_BAR_FREQUENCIES = frozenset({"1d", "1w", "1mo"})
_DAILY_ONLY_FREQUENCIES = frozenset({"1d"})

_PERIOD_BY_FREQUENCY = {
    "1d": "daily",
    "1w": "weekly",
    "1mo": "monthly",
}

# Snapshot reviewed objects and their original descriptor identities at import
# time. The adapter selects only from this table; a later registry replacement
# cannot widen a response profile before provider I/O.
_AKSHARE_REVIEWED_CONTRACTS: Mapping[tuple[str, str], ProviderContract] = MappingProxyType(
    {
        (contract.provider, contract.route_id): contract
        for contract in AKSHARE_PROVIDER_CONTRACT_REGISTRY.contracts
    }
)
_AKSHARE_REVIEWED_CONTRACT_IDENTITIES: Mapping[tuple[str, str], tuple[str, str]] = (
    MappingProxyType(
        {
            key: (
                contract.contract_id,
                contract.descriptor_sha256,
            )
            for key, contract in _AKSHARE_REVIEWED_CONTRACTS.items()
        }
    )
)


def _assert_reviewed_contract_integrity(contract: ProviderContract) -> None:
    """Reject object replacement or post-construction contract mutation."""
    try:
        key = (contract.provider, contract.route_id)
        expected_contract = _AKSHARE_REVIEWED_CONTRACTS.get(key)
        expected_identity = _AKSHARE_REVIEWED_CONTRACT_IDENTITIES.get(key)
        if (
            contract is not expected_contract
            or expected_identity != (contract.contract_id, contract.descriptor_sha256)
        ):
            raise ProviderContractError("PROVIDER_CONTRACT_DESCRIPTOR_MISMATCH")
        contract.assert_descriptor_integrity()
    except ProviderContractError:
        raise
    except Exception as exc:
        raise ProviderContractError("PROVIDER_CONTRACT_DESCRIPTOR_MISMATCH") from exc


def _reviewed_contract_for_request(request: MarketDataProviderRequest) -> ProviderContract:
    """Select exactly one import-time reviewed contract without a registry seam."""
    if request.route_id is None:
        raise ProviderContractError("PROVIDER_CONTRACT_ROUTE_REQUIRED")
    contract = _AKSHARE_REVIEWED_CONTRACTS.get((request.provider, request.route_id))
    if contract is None:
        if any(route_id == request.route_id for _, route_id in _AKSHARE_REVIEWED_CONTRACTS):
            raise ProviderContractError("PROVIDER_CONTRACT_PROVIDER_MISMATCH")
        raise ProviderContractError("PROVIDER_CONTRACT_UNREGISTERED")
    _assert_reviewed_contract_integrity(contract)
    contract.assert_request_matches(request)
    return contract

# The response normalizer obtains its reviewed aliases from the immutable
# ProviderContract.  Keep this module-level alias for the schedule-only wide
# table schemas below, which deliberately remain outside request-time routes.
_FIELD_ALIASES = AKSHARE_RESPONSE_FIELD_ALIASES

RouteArgumentBuilder = Callable[[MarketDataProviderRequest], Mapping[str, Any]]
RouteRequestValidator = Callable[[MarketDataProviderRequest], None]
RouteEndpointResolver = Callable[[MarketDataProviderRequest], str]
AkShareTestRunner = Callable[[Mapping[str, Any]], Any]

_RUNNER_BASE_ENVIRONMENT_KEYS = (
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "PYTHONIOENCODING",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
)
_RUNNER_HOME_ENVIRONMENT_KEY = "AKSHARE_RUNNER_HOME"
_RUNNER_WORKDIR_ENVIRONMENT_KEY = "AKSHARE_RUNNER_WORKDIR"
_RUNNER_SITE_PACKAGES_ENVIRONMENT_KEY = "AKSHARE_RUNNER_SITE_PACKAGES"
_RUNNER_COMMAND_ENVIRONMENT_KEY = "AKSHARE_MARKET_DATA_RUNNER"


class AkShareProviderError(RuntimeError):
    """Stable failure code emitted by the explicit AkShare adapter."""

    def __init__(self, code: str, *, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class AkShareRoute:
    """One reviewed AkShare route and the data contract required to use it.

    ``endpoint`` or ``endpoint_resolver`` together with ``build_call_kwargs``
    define a supported route. Both endpoint fields are absent for an explicit
    unsupported capability. This makes a decision about every current asset
    type visible in the registry instead of leaving absent routes to an
    accidental fallback path. An endpoint resolver is permitted only when a
    compact, exact contract prefix chooses between reviewed source functions.
    """

    asset_type: str
    data_kind: str
    frequencies: frozenset[str]
    endpoint: str | None
    build_call_kwargs: RouteArgumentBuilder | None
    timestamp_columns: tuple[str, ...]
    endpoint_resolver: RouteEndpointResolver | None = None
    allowed_markets: frozenset[str] | None = None
    symbol_columns: tuple[str, ...] = ()
    client_filters_window: bool = False
    identity_proof: str = "source_request_bound"
    request_validator: RouteRequestValidator | None = None
    supported_adjustments: frozenset[str] = frozenset({"unadjusted"})
    supported_price_bases: frozenset[str] = frozenset({"close"})
    supported_currencies: frozenset[str] | None = None
    supported_units: frozenset[str] | None = None
    # A source function may be limited to one frozen product identity even
    # when several products share the same symbol syntax and market.
    supported_product_types: frozenset[str] | None = None
    supported_fund_identity_kinds: frozenset[str] | None = None
    # The policy-level route ID is deliberately separate from the AkShare
    # endpoint name.  Several single-record product families can share an
    # asset type and data kind (for example, stock reference series), but
    # must not be allowed to select each other's source function merely
    # because their broad dimensions happen to overlap.
    route_ids: frozenset[str] = frozenset()
    # A shared source endpoint can serve several data products only when each
    # dedicated policy route verifies the same family/version pair locally.
    family_id: str | None = None
    family_contract_version: str | None = None

    def __post_init__(self) -> None:
        has_endpoint = self.endpoint is not None or self.endpoint_resolver is not None
        if has_endpoint != (self.build_call_kwargs is not None):
            raise ValueError("AkShare routes must define an endpoint and arguments or neither")
        if self.endpoint is not None and self.endpoint_resolver is not None:
            raise ValueError("AkShare routes cannot define both a static and dynamic endpoint")
        if self.endpoint is not None and not self.endpoint.strip():
            raise ValueError("AkShare route endpoint must not be blank")
        if not self.asset_type or not self.data_kind or not self.frequencies:
            raise ValueError("AkShare route identity must not be blank")
        if not self.timestamp_columns:
            raise ValueError("AkShare routes require an explicit timestamp column list")
        if self.allowed_markets is not None and not self.allowed_markets:
            raise ValueError("AkShare supported-market sets must not be empty")
        if self.identity_proof not in {"source_request_bound", "response_symbol"}:
            raise ValueError("AkShare route identity_proof is invalid")
        if self.identity_proof == "response_symbol" and not self.symbol_columns:
            raise ValueError("response-symbol routes require a symbol column list")
        if not self.supported_adjustments or not self.supported_price_bases:
            raise ValueError("AkShare routes require explicit semantic capability sets")
        if self.supported_currencies is not None and not self.supported_currencies:
            raise ValueError("use None to reject all explicit AkShare currencies")
        if self.supported_units is not None and not self.supported_units:
            raise ValueError("use None to reject all explicit AkShare units")
        for field_name, values in (
            ("supported_product_types", self.supported_product_types),
            ("supported_fund_identity_kinds", self.supported_fund_identity_kinds),
        ):
            if values is not None:
                if (
                    not isinstance(values, frozenset)
                    or not values
                    or any(not isinstance(value, str) or not value.strip() for value in values)
                ):
                    raise ValueError(f"{field_name} must be a non-empty frozenset of text")
                object.__setattr__(self, field_name, frozenset(value.strip() for value in values))
        if self.supported_fund_identity_kinds is not None and self.asset_type != "fund":
            raise ValueError("supported_fund_identity_kinds require a fund route")
        if not isinstance(self.route_ids, frozenset):
            raise TypeError("AkShare route_ids must be a frozenset")
        if any(not isinstance(route_id, str) or not route_id.strip() for route_id in self.route_ids):
            raise ValueError("AkShare route_ids must contain non-blank strings")
        object.__setattr__(
            self,
            "route_ids",
            frozenset(route_id.strip() for route_id in self.route_ids),
        )
        if (self.family_id is None) != (self.family_contract_version is None):
            raise ValueError("AkShare family routes require both family_id and family_contract_version")
        if self.route_ids and self.family_id is None:
            raise ValueError("AkShare source-policy routes require an exact family pair")
        if self.family_id is not None:
            if not isinstance(self.family_id, str) or not self.family_id.strip():
                raise ValueError("AkShare family_id must be non-blank when supplied")
            object.__setattr__(self, "family_id", self.family_id.strip())
        if self.family_contract_version is not None:
            if self.family_id is None:
                raise ValueError("AkShare family_contract_version requires family_id")
            if (
                not isinstance(self.family_contract_version, str)
                or not self.family_contract_version.strip()
            ):
                raise ValueError("AkShare family_contract_version must be non-blank")
            object.__setattr__(
                self,
                "family_contract_version",
                self.family_contract_version.strip(),
            )


@dataclass(frozen=True, slots=True)
class AkShareSnapshotRowSchema:
    """A schedule-only full-market row shape, deliberately separate from fetch routes.

    The exact-request provider registry above must never select a broad spot
    endpoint and then filter a symbol at request time.  These schemas exist
    only for a scheduler or shadow worker that has already captured a bounded
    source row set and a frozen identity map.  They declare which returned
    columns can prove identity, source time, and normalized snapshot fields.
    """

    asset_type: str
    identity_columns: tuple[str, ...]
    timestamp_columns: tuple[str, ...]
    field_aliases: Mapping[str, str]
    source_timezone: str
    collector_observed_allowed: bool = False
    source_market_columns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject incomplete or ambiguous schema declarations at process start."""
        if not isinstance(self.asset_type, str) or not self.asset_type.strip():
            raise ValueError("snapshot schema asset_type must not be blank")
        for field_name, columns in (
            ("identity_columns", self.identity_columns),
            ("source_market_columns", self.source_market_columns),
            ("timestamp_columns", self.timestamp_columns),
        ):
            if not isinstance(columns, tuple):
                raise ValueError(f"snapshot schema {field_name} must be a tuple")
            if field_name != "source_market_columns" and not columns:
                raise ValueError(f"snapshot schema {field_name} must be a non-empty tuple")
            if any(not isinstance(column, str) or not column.strip() for column in columns):
                raise ValueError(f"snapshot schema {field_name} must contain non-blank strings")
            if len(columns) != len(set(columns)):
                raise ValueError(f"snapshot schema {field_name} must be distinct")
        identity_column_sets = (
            set(self.identity_columns),
            set(self.source_market_columns),
            set(self.timestamp_columns),
        )
        if any(
            left & right
            for index, left in enumerate(identity_column_sets)
            for right in identity_column_sets[index + 1 :]
        ):
            raise ValueError(
                "snapshot schema identity, market, and timestamp columns must not overlap"
            )
        if not isinstance(self.field_aliases, Mapping) or not self.field_aliases:
            raise ValueError("snapshot schema field_aliases must be a non-empty mapping")
        normalized_aliases: dict[str, str] = {}
        for source_name, field_name in self.field_aliases.items():
            if (
                not isinstance(source_name, str)
                or not source_name.strip()
                or not isinstance(field_name, str)
                or not field_name.strip()
            ):
                raise ValueError("snapshot schema aliases must use non-blank strings")
            normalized_aliases[source_name.strip()] = field_name.strip()
        if not isinstance(self.source_timezone, str) or not self.source_timezone.strip():
            raise ValueError("snapshot schema source_timezone must not be blank")
        if not isinstance(self.collector_observed_allowed, bool):
            raise TypeError("snapshot schema collector_observed_allowed must be bool")
        object.__setattr__(self, "asset_type", self.asset_type.strip())
        object.__setattr__(self, "field_aliases", MappingProxyType(normalized_aliases))
        object.__setattr__(self, "source_timezone", self.source_timezone.strip())


# These are input row schemas for an offline/scheduled importer, not callable
# AkShare routes.  In particular, none is inserted into ``AKSHARE_ROUTE_REGISTRY``.
_STOCK_SNAPSHOT_FIELD_ALIASES = {
    "最新价": "price",
    "现价": "price",
    "price": "price",
    "涨跌额": "change",
    "change": "change",
    "涨跌幅": "change_pct",
    "change_pct": "change_pct",
    "今开": "open",
    "开盘": "open",
    "open": "open",
    "最高": "high",
    "high": "high",
    "最低": "low",
    "low": "low",
    "昨收": "previous_close",
    "previous_close": "previous_close",
    "成交量": "volume",
    "volume": "volume",
    "成交额": "turnover",
    "turnover": "turnover",
    "换手率": "turnover_rate",
    # ``stock_zh_a_spot_em`` is a broad offline/scheduled snapshot source.
    # Keep its valuation aliases on the snapshot schema only: adding them
    # here must never promote the wide table into ``AKSHARE_ROUTE_REGISTRY``.
    "总市值": "market_cap",
    "market_cap": "market_cap",
    "流通市值": "float_market_cap",
    "float_market_cap": "float_market_cap",
    "市盈率-动态": "pe",
    "市盈率": "pe",
    "pe": "pe",
    "市净率": "pb",
    "pb": "pb",
}
_FUND_SNAPSHOT_FIELD_ALIASES = {
    "最新价": "price",
    "现价": "price",
    "price": "price",
    "涨跌额": "change",
    "change": "change",
    "涨跌幅": "change_pct",
    "change_pct": "change_pct",
    "今开": "open",
    "开盘": "open",
    "open": "open",
    "最高": "high",
    "high": "high",
    "最低": "low",
    "low": "low",
    "昨收": "previous_close",
    "previous_close": "previous_close",
    "成交量": "volume",
    "volume": "volume",
    "成交额": "turnover",
    "turnover": "turnover",
    "IOPV": "iopv",
    "iopv": "iopv",
    "单位净值": "nav",
    "累计净值": "cumulative_nav",
    "日增长率": "daily_growth_rate",
}
_FX_SNAPSHOT_FIELD_ALIASES = {
    "最新价": "price",
    "现价": "price",
    "price": "price",
    "涨跌额": "change",
    "change": "change",
    "涨跌幅": "change_pct",
    "change_pct": "change_pct",
    "今开": "open",
    "开盘": "open",
    "open": "open",
    "最高": "high",
    "high": "high",
    "最低": "low",
    "low": "low",
    "昨收": "previous_close",
    "previous_close": "previous_close",
    "买入价": "bid",
    "买一": "bid",
    "bid": "bid",
    "卖出价": "ask",
    "卖一": "ask",
    "ask": "ask",
}
_CRYPTO_SNAPSHOT_FIELD_ALIASES = {
    "最新价": "price",
    "现价": "price",
    "最近报价": "price",
    "price": "price",
    "last": "price",
    "涨跌额": "change",
    "change": "change",
    "涨跌幅": "change_pct",
    "change_pct": "change_pct",
    "最高": "high",
    "24h最高": "high",
    "high": "high",
    "最低": "low",
    "24h最低": "low",
    "low": "low",
    "成交量": "volume",
    "24h成交量": "volume",
    "volume": "volume",
    "成交额": "turnover",
    "turnover": "turnover",
    "持仓量": "open_interest",
    "open_interest": "open_interest",
    "买一": "bid",
    "bid": "bid",
    "卖一": "ask",
    "ask": "ask",
}
_OPTION_SNAPSHOT_FIELD_ALIASES = {
    "最新价": "price",
    "现价": "price",
    "price": "price",
    "涨跌额": "change",
    "change": "change",
    "涨跌幅": "change_pct",
    "change_pct": "change_pct",
    "成交量": "volume",
    "volume": "volume",
    "成交额": "turnover",
    "turnover": "turnover",
    "持仓量": "open_interest",
    "open_interest": "open_interest",
    "行权价": "strike",
    "strike": "strike",
    "剩余天数": "days_to_expiry",
    "days_to_expiry": "days_to_expiry",
    "买一": "bid",
    "bid": "bid",
    "卖一": "ask",
    "ask": "ask",
}

AKSHARE_SNAPSHOT_ROW_SCHEMAS: tuple[AkShareSnapshotRowSchema, ...] = (
    AkShareSnapshotRowSchema(
        asset_type="stock",
        identity_columns=("代码", "股票代码", "symbol", "code"),
        source_market_columns=(),
        timestamp_columns=("更新时间", "时间", "timestamp", "update_time"),
        field_aliases=_STOCK_SNAPSHOT_FIELD_ALIASES,
        source_timezone="Asia/Shanghai",
        collector_observed_allowed=True,
    ),
    AkShareSnapshotRowSchema(
        asset_type="fund",
        identity_columns=("基金代码", "代码", "symbol", "code"),
        source_market_columns=(),
        timestamp_columns=("更新时间", "时间", "timestamp", "update_time"),
        field_aliases=_FUND_SNAPSHOT_FIELD_ALIASES,
        source_timezone="Asia/Shanghai",
    ),
    AkShareSnapshotRowSchema(
        asset_type="fx",
        identity_columns=("代码", "货币对", "currency_pair", "symbol", "code"),
        source_market_columns=(),
        timestamp_columns=("更新时间", "时间", "timestamp", "update_time"),
        field_aliases=_FX_SNAPSHOT_FIELD_ALIASES,
        source_timezone="Asia/Shanghai",
        collector_observed_allowed=True,
    ),
    AkShareSnapshotRowSchema(
        asset_type="crypto",
        identity_columns=("交易品种", "交易对", "代码", "symbol", "code"),
        source_market_columns=("市场", "market"),
        timestamp_columns=("更新时间", "时间", "timestamp", "update_time"),
        field_aliases=_CRYPTO_SNAPSHOT_FIELD_ALIASES,
        source_timezone="UTC",
    ),
    AkShareSnapshotRowSchema(
        asset_type="option",
        identity_columns=("合约代码", "期权代码", "代码", "symbol", "code"),
        source_market_columns=("市场标识", "市场", "market"),
        timestamp_columns=("更新时间", "时间", "timestamp", "update_time"),
        field_aliases=_OPTION_SNAPSHOT_FIELD_ALIASES,
        source_timezone="Asia/Shanghai",
        collector_observed_allowed=True,
    ),
)


def get_akshare_snapshot_row_schema(asset_type: str) -> AkShareSnapshotRowSchema:
    """Return an explicit offline-import schema without constructing a provider route."""
    if not isinstance(asset_type, str):
        raise AkShareProviderError("AKSHARE_SNAPSHOT_ASSET_UNSUPPORTED")
    normalized = asset_type.strip()
    for schema in AKSHARE_SNAPSHOT_ROW_SCHEMAS:
        if schema.asset_type == normalized:
            return schema
    raise AkShareProviderError("AKSHARE_SNAPSHOT_ASSET_UNSUPPORTED")


def _format_akshare_date(value: datetime) -> str:
    """Format an already-normalized instant using AkShare's date-only contract."""
    return value.astimezone(_UTC).strftime("%Y%m%d")


def _format_akshare_inclusive_end_date(value: datetime) -> str:
    """Translate a half-open end instant to AkShare's inclusive date argument."""
    return _format_akshare_date(value - timedelta(microseconds=1))


def _akshare_adjustment(request: MarketDataProviderRequest) -> str:
    """Map only documented AkShare adjustment values; never infer a basis."""
    if request.adjustment is None or request.adjustment == "unadjusted":
        return ""
    if request.adjustment in {"qfq", "hfq"}:
        return request.adjustment
    raise AkShareProviderError("AKSHARE_ADJUSTMENT_UNSUPPORTED")


def _build_historical_kline_kwargs(request: MarketDataProviderRequest) -> Mapping[str, Any]:
    """Build the bounded call shape shared by stock and ETF historical routes."""
    try:
        period = _PERIOD_BY_FREQUENCY[request.frequency]
    except KeyError as exc:
        raise AkShareProviderError("AKSHARE_ROUTE_UNSUPPORTED") from exc
    return {
        "symbol": request.provider_symbol,
        "period": period,
        "start_date": _format_akshare_date(request.start_at),
        "end_date": _format_akshare_inclusive_end_date(request.end_at),
        "adjust": _akshare_adjustment(request),
    }


def _build_fund_nav_kwargs(request: MarketDataProviderRequest) -> Mapping[str, Any]:
    """Build the exact ETF NAV-history call without borrowing the price-bar route.

    ``fund_etf_fund_info_em`` has a different argument contract from
    ``fund_etf_hist_em`` and returns source-reported net asset values. Its
    inclusive source dates are derived from the v2 half-open query window.
    """
    return {
        "fund": request.provider_symbol,
        "start_date": _format_akshare_date(request.start_at),
        "end_date": _format_akshare_inclusive_end_date(request.end_at),
    }


def _build_symbol_only_kwargs(request: MarketDataProviderRequest) -> Mapping[str, Any]:
    """Build a route that returns the source's full history for one exact symbol."""
    return {"symbol": request.provider_symbol}


def _validate_cn_stock_symbol(request: MarketDataProviderRequest) -> None:
    """Reject a master-data venue that contradicts AkShare's deterministic routing."""
    if request.market == "CN-SSE" and not request.provider_symbol.startswith("6"):
        raise AkShareProviderError("AKSHARE_SYMBOL_MARKET_MISMATCH")
    if request.market == "CN-SZSE" and not request.provider_symbol.startswith(("0", "3")):
        raise AkShareProviderError("AKSHARE_SYMBOL_MARKET_MISMATCH")


def _validate_cn_bond_symbol(request: MarketDataProviderRequest) -> None:
    """Require the exchange prefix that the reviewed bond endpoint consumes."""
    expected_prefix = "sh" if request.market in {"SSE", "CN-SSE"} else "sz"
    if not request.provider_symbol.startswith(expected_prefix):
        raise AkShareProviderError("AKSHARE_SYMBOL_MARKET_MISMATCH")


def _validate_cffex_futures_symbol(request: MarketDataProviderRequest) -> None:
    """Limit the Sina daily route to CFFEX product codes with a known venue mapping."""
    symbol = request.provider_symbol
    if symbol.startswith(("IF", "IH", "IC", "IM", "TS", "TF", "TL")):
        return
    if symbol.startswith("T") and len(symbol) > 1 and symbol[1].isdigit():
        return
    raise AkShareProviderError("AKSHARE_SYMBOL_MARKET_MISMATCH")


def _validate_cn_etf_symbol(request: MarketDataProviderRequest) -> None:
    """Apply AkShare's documented ETF code-to-market decision before fetching."""
    symbol = request.provider_symbol
    source_market = "CN-SSE"
    if symbol.startswith(("0", "1", "2", "3")):
        source_market = "CN-SZSE"
    if request.market != source_market:
        raise AkShareProviderError("AKSHARE_SYMBOL_MARKET_MISMATCH")


def _resolve_cffex_option_endpoint(request: MarketDataProviderRequest) -> str:
    """Select the reviewed CFFEX option history endpoint from an exact contract code.

    The source API offers separate history methods for HS300, SSE50 and
    CSI1000 options. Prefix selection is safe because the master-data identity
    already supplies the complete immutable contract code; there is no chain
    lookup, dominant-contract alias, or nearby-symbol fallback here.
    """
    symbol = request.provider_symbol.upper()
    endpoint_by_prefix = {
        "IO": "option_cffex_hs300_daily_sina",
        "HO": "option_cffex_sz50_daily_sina",
        "MO": "option_cffex_zz1000_daily_sina",
    }
    for prefix, endpoint in endpoint_by_prefix.items():
        if symbol.startswith(prefix) and len(symbol) > len(prefix):
            return endpoint
    raise AkShareProviderError("AKSHARE_SYMBOL_MARKET_MISMATCH")


_AKSHARE_REQUEST_VALIDATORS: Mapping[str | None, RouteRequestValidator | None] = MappingProxyType(
    {
        None: None,
        "akshare.cn-stock-symbol-v1": _validate_cn_stock_symbol,
        "akshare.cn-bond-symbol-v1": _validate_cn_bond_symbol,
        "akshare.cffex-futures-symbol-v1": _validate_cffex_futures_symbol,
        "akshare.cn-etf-symbol-v1": _validate_cn_etf_symbol,
    }
)


# The registry is intentionally small and source-specific. CFFEX option
# contracts have three reviewed exact-code history functions; their selector
# never resolves a dominant alias or option chain. Crypto remains explicitly
# unsupported in AkShare and can only reach an approved isolated OpenBB route.
AKSHARE_ROUTE_REGISTRY: tuple[AkShareRoute, ...] = (
    AkShareRoute(
        asset_type="stock",
        data_kind="bars",
        frequencies=_DAILY_BAR_FREQUENCIES,
        endpoint="stock_zh_a_hist",
        build_call_kwargs=_build_historical_kline_kwargs,
        timestamp_columns=("日期", "date"),
        allowed_markets=frozenset({"CN-SSE", "CN-SZSE"}),
        symbol_columns=("股票代码", "symbol", "code"),
        client_filters_window=True,
        identity_proof="response_symbol",
        request_validator=_validate_cn_stock_symbol,
        supported_adjustments=frozenset({"unadjusted", "qfq", "hfq"}),
        supported_currencies=frozenset({"CNY"}),
        supported_units=frozenset({"share"}),
        route_ids=frozenset({"akshare-stock-primary-v1"}),
        family_id="stock.realtime",
        family_contract_version=FAMILY_CONTRACT_VERSION,
    ),
    AkShareRoute(
        asset_type="stock",
        data_kind="bars",
        frequencies=_DAILY_BAR_FREQUENCIES,
        endpoint="stock_zh_a_hist",
        build_call_kwargs=_build_historical_kline_kwargs,
        timestamp_columns=("日期", "date"),
        allowed_markets=frozenset({"CN-SSE", "CN-SZSE"}),
        symbol_columns=("股票代码", "symbol", "code"),
        client_filters_window=True,
        identity_proof="response_symbol",
        request_validator=_validate_cn_stock_symbol,
        supported_adjustments=frozenset({"qfq"}),
        supported_price_bases=frozenset({"close"}),
        supported_currencies=frozenset({"CNY"}),
        supported_units=frozenset({"share"}),
        route_ids=frozenset({"akshare-stock-kline-legacy-v1"}),
        family_id=KLINE_LEGACY_FAMILY_ID,
        family_contract_version=KLINE_LEGACY_CONTRACT_VERSION,
    ),
    # This is deliberately a separate route from stock bars even though it
    # uses the same exact-symbol AkShare function.  The route ID prevents a
    # future valuation/reference policy from accidentally receiving a
    # liquidity-only field set through a broad `reference_series` match.
    AkShareRoute(
        asset_type="stock",
        data_kind="reference_series",
        frequencies=_DAILY_ONLY_FREQUENCIES,
        endpoint="stock_zh_a_hist",
        build_call_kwargs=_build_historical_kline_kwargs,
        timestamp_columns=("日期", "date"),
        allowed_markets=frozenset({"CN-SSE", "CN-SZSE"}),
        symbol_columns=("股票代码", "symbol", "code"),
        client_filters_window=True,
        identity_proof="response_symbol",
        request_validator=_validate_cn_stock_symbol,
        supported_adjustments=frozenset({"unadjusted"}),
        supported_currencies=frozenset({"CNY"}),
        supported_units=frozenset({"share"}),
        route_ids=frozenset({"akshare-stock-liquidity-primary-v1"}),
        family_id="stock.liquidity",
        family_contract_version=FAMILY_CONTRACT_VERSION,
    ),
    AkShareRoute(
        asset_type="futures",
        data_kind="bars",
        frequencies=_DAILY_ONLY_FREQUENCIES,
        endpoint="futures_zh_daily_sina",
        build_call_kwargs=_build_symbol_only_kwargs,
        timestamp_columns=("date", "日期"),
        allowed_markets=frozenset({"CFFEX"}),
        client_filters_window=True,
        supported_currencies=frozenset({"CNY"}),
        supported_units=frozenset({"contract"}),
        request_validator=_validate_cffex_futures_symbol,
        route_ids=frozenset({"akshare-futures-primary-v1"}),
        family_id="futures.realtime",
        family_contract_version=FAMILY_CONTRACT_VERSION,
    ),
    AkShareRoute(
        asset_type="bond",
        data_kind="bars",
        frequencies=_DAILY_ONLY_FREQUENCIES,
        endpoint="bond_zh_hs_daily",
        build_call_kwargs=_build_symbol_only_kwargs,
        timestamp_columns=("date", "日期"),
        allowed_markets=frozenset({"SSE", "SZSE", "CN-SSE", "CN-SZSE"}),
        client_filters_window=True,
        request_validator=_validate_cn_bond_symbol,
        supported_currencies=frozenset({"CNY"}),
        route_ids=frozenset({"akshare-bond-primary-v1"}),
        family_id="bond.realtime",
        family_contract_version=FAMILY_CONTRACT_VERSION,
    ),
    AkShareRoute(
        asset_type="fund",
        data_kind="bars",
        frequencies=_DAILY_BAR_FREQUENCIES,
        endpoint="fund_etf_hist_em",
        build_call_kwargs=_build_historical_kline_kwargs,
        timestamp_columns=("日期", "date"),
        allowed_markets=frozenset({"CN-SSE", "CN-SZSE"}),
        client_filters_window=True,
        supported_adjustments=frozenset({"unadjusted", "qfq", "hfq"}),
        supported_currencies=frozenset({"CNY"}),
        supported_units=frozenset({"share"}),
        request_validator=_validate_cn_etf_symbol,
        route_ids=frozenset({"akshare-fund-primary-v1"}),
        family_id="fund.realtime",
        family_contract_version=FAMILY_CONTRACT_VERSION,
    ),
    # ETF liquidity is an exact code/date range request.  AkShare's endpoint
    # does not echo the code in each returned row, so it retains the existing
    # request-bound identity proof plus the deterministic ETF venue check.
    AkShareRoute(
        asset_type="fund",
        data_kind="reference_series",
        frequencies=_DAILY_ONLY_FREQUENCIES,
        endpoint="fund_etf_hist_em",
        build_call_kwargs=_build_historical_kline_kwargs,
        timestamp_columns=("日期", "date"),
        allowed_markets=frozenset({"CN-SSE", "CN-SZSE"}),
        client_filters_window=True,
        supported_adjustments=frozenset({"unadjusted"}),
        supported_currencies=frozenset({"CNY"}),
        supported_units=frozenset({"share"}),
        request_validator=_validate_cn_etf_symbol,
        route_ids=frozenset({"akshare-fund-liquidity-primary-v1"}),
        family_id="fund.liquidity",
        family_contract_version=FAMILY_CONTRACT_VERSION,
    ),
    # NAV is a source-reported per-fund-share reference series. It is neither
    # a traded ETF price bar nor a liquidity projection, so it uses the
    # dedicated Eastmoney/AkShare history endpoint and separate semantic axes.
    AkShareRoute(
        asset_type="fund",
        data_kind="reference_series",
        frequencies=_DAILY_ONLY_FREQUENCIES,
        endpoint="fund_etf_fund_info_em",
        build_call_kwargs=_build_fund_nav_kwargs,
        timestamp_columns=("净值日期", "date"),
        allowed_markets=frozenset({"CN-SSE", "CN-SZSE"}),
        client_filters_window=True,
        supported_adjustments=frozenset({"source_reported"}),
        supported_price_bases=frozenset({"nav"}),
        supported_currencies=frozenset({"CNY"}),
        supported_units=frozenset({"fund_share"}),
        supported_product_types=frozenset({"ETF"}),
        supported_fund_identity_kinds=frozenset({"LISTING"}),
        request_validator=_validate_cn_etf_symbol,
        route_ids=frozenset({"akshare-fund-nav-primary-v1"}),
        family_id="fund.nav",
        family_contract_version=FAMILY_CONTRACT_VERSION,
    ),
    AkShareRoute(
        asset_type="option",
        data_kind="bars",
        frequencies=_DAILY_ONLY_FREQUENCIES,
        endpoint=None,
        endpoint_resolver=_resolve_cffex_option_endpoint,
        build_call_kwargs=_build_symbol_only_kwargs,
        timestamp_columns=("date", "日期"),
        allowed_markets=frozenset({"CFFEX"}),
        client_filters_window=True,
        supported_currencies=frozenset({"CNY"}),
        supported_units=frozenset({"contract"}),
        route_ids=frozenset({"akshare-cffex-option-primary-v1"}),
        family_id="option.realtime",
        family_contract_version=FAMILY_CONTRACT_VERSION,
    ),
    AkShareRoute(
        asset_type="fx",
        data_kind="bars",
        frequencies=_DAILY_ONLY_FREQUENCIES,
        endpoint="forex_hist_em",
        build_call_kwargs=_build_symbol_only_kwargs,
        timestamp_columns=("日期", "date"),
        allowed_markets=frozenset({"OTC", "CN-OTC"}),
        symbol_columns=("代码", "code", "symbol"),
        client_filters_window=True,
        identity_proof="response_symbol",
        route_ids=frozenset({"akshare-fx-primary-v1"}),
        family_id="fx.realtime",
        family_contract_version=FAMILY_CONTRACT_VERSION,
    ),
    # The same reviewed source function can supply a full OHLC range, but the
    # range product owns a distinct public family and policy route. Keeping a
    # second exact family pair prevents either FX product from selecting the
    # other merely because its endpoint and semantic axes overlap.
    AkShareRoute(
        asset_type="fx",
        data_kind="bars",
        frequencies=_DAILY_ONLY_FREQUENCIES,
        endpoint="forex_hist_em",
        build_call_kwargs=_build_symbol_only_kwargs,
        timestamp_columns=("日期", "date"),
        allowed_markets=frozenset({"OTC", "CN-OTC"}),
        symbol_columns=("代码", "code", "symbol"),
        client_filters_window=True,
        identity_proof="response_symbol",
        route_ids=frozenset({"akshare-fx-range-primary-v1"}),
        family_id="fx.range",
        family_contract_version=FAMILY_CONTRACT_VERSION,
    ),
    AkShareRoute(
        asset_type="crypto",
        data_kind="bars",
        frequencies=_ALL_BAR_FREQUENCIES,
        endpoint=None,
        build_call_kwargs=None,
        timestamp_columns=("日期",),
    ),
)


@dataclass(frozen=True, slots=True)
class _BoundedRunnerStream:
    """A fully drained runner pipe with a bounded retained prefix."""

    data: bytes
    exceeded_limit: bool


def _has_safe_akshare_process_group() -> bool:
    """Return whether this process can create and terminate an isolated group.

    The adapter deliberately has no request-process fallback.  Checking the
    concrete primitives before spawn keeps an unusual POSIX-like platform from
    starting AkShare work that it cannot later terminate as a group.
    """
    return (
        os.name == "posix"
        and callable(getattr(os, "setsid", None))
        and callable(getattr(os, "killpg", None))
        and hasattr(signal, "SIGKILL")
    )


async def _read_runner_stream_bounded(
    stream: asyncio.StreamReader,
    *,
    maximum_bytes: int,
) -> _BoundedRunnerStream:
    """Drain one pipe even when its retained evidence exceeds the hard cap."""
    retained: list[bytes] = []
    remaining = maximum_bytes
    exceeded_limit = False
    while chunk := await stream.read(_RUNNER_READ_CHUNK_BYTES):
        if remaining <= 0:
            exceeded_limit = True
            continue
        if len(chunk) <= remaining:
            retained.append(chunk)
            remaining -= len(chunk)
            continue
        retained.append(chunk[:remaining])
        remaining = 0
        exceeded_limit = True
    return _BoundedRunnerStream(data=b"".join(retained), exceeded_limit=exceeded_limit)


async def _terminate_runner_group(
    process: asyncio.subprocess.Process,
    *,
    process_group_id: int,
) -> None:
    """Kill a POSIX runner session and wait for its direct child to exit.

    The known session leader PID remains usable even after the direct child
    exits.  This is deliberate: a descendant can otherwise retain a pipe or
    continue source I/O after the web request releases its durable fetch
    lease.
    """
    try:
        os.killpg(process_group_id, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    with suppress(ProcessLookupError):
        await process.wait()


async def _await_runner_cleanup(*tasks: asyncio.Future[Any]) -> None:
    """Wait for reaping/draining even when request cancellation repeats.

    ``fetch`` re-raises its original cancellation after this helper returns.
    Suppressing a repeated cancellation here is intentionally narrow: it
    makes cleanup a completion boundary, rather than allowing the caller to
    release a fetch lease while an AkShare child still owns network I/O.
    """
    pending = [task for task in tasks if task is not None]
    if not pending:
        return
    cleanup = asyncio.gather(*pending, return_exceptions=True)
    while not cleanup.done():
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            continue
    await cleanup


def _strict_json_loads(value: bytes) -> object:
    """Decode RFC-JSON without accepting JavaScript NaN/Infinity extensions."""

    def reject_constant(_: str) -> object:
        raise ValueError("non-finite JSON token")

    return json.loads(value.decode("utf-8"), parse_constant=reject_constant)


class _AkShareSubprocessRunner:
    """Run one exact AkShare call in a killable POSIX child session."""

    def __init__(
        self,
        *,
        command: tuple[str, ...] | None,
        environment: Mapping[str, str] | None,
        workdir: str | None,
        configuration_error: str | None,
    ) -> None:
        self._command = command
        self._environment = dict(environment) if environment is not None else None
        self._workdir = workdir
        self._configuration_error = configuration_error

    async def execute(
        self,
        envelope: Mapping[str, Any],
        *,
        timeout_seconds: float,
    ) -> Mapping[str, Any]:
        """Exchange one bounded JSON receipt, reaping the group before return."""
        if self._configuration_error is not None:
            raise AkShareProviderError(self._configuration_error)
        if not _has_safe_akshare_process_group():
            raise AkShareProviderError("AKSHARE_RUNNER_PROCESS_GROUP_UNSUPPORTED")
        if self._command is None or self._environment is None or self._workdir is None:
            raise AkShareProviderError("AKSHARE_RUNNER_ENV_UNCONFIGURED")

        try:
            process = await asyncio.create_subprocess_exec(
                *self._command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._environment,
                cwd=self._workdir,
                start_new_session=True,
            )
        except OSError as exc:
            raise AkShareProviderError("AKSHARE_RUNNER_UNAVAILABLE", detail=_error_detail(exc)) from exc

        if process.stdin is None or process.stdout is None or process.stderr is None:
            await _terminate_runner_group(process, process_group_id=process.pid)
            raise AkShareProviderError("AKSHARE_RUNNER_UNAVAILABLE")

        stdout_task = asyncio.create_task(
            _read_runner_stream_bounded(process.stdout, maximum_bytes=_MAX_RUNNER_OUTPUT_BYTES)
        )
        stderr_task = asyncio.create_task(
            _read_runner_stream_bounded(process.stderr, maximum_bytes=_MAX_RUNNER_OUTPUT_BYTES)
        )

        async def send_and_collect() -> tuple[int, _BoundedRunnerStream, _BoundedRunnerStream]:
            try:
                process.stdin.write(_canonical_json(dict(envelope)).encode("utf-8"))
                await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                # The runner may reject input and exit. Its bounded receipt and
                # exit status still select the fail-closed provider outcome.
                pass
            finally:
                process.stdin.close()
                with suppress(BrokenPipeError, ConnectionResetError):
                    await process.stdin.wait_closed()
            returncode = await process.wait()
            stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
            return int(returncode), stdout, stderr

        collector_task = asyncio.create_task(send_and_collect())
        try:
            returncode, stdout, stderr = await asyncio.wait_for(
                asyncio.shield(collector_task), timeout=timeout_seconds
            )
        except TimeoutError as exc:
            raise AkShareProviderError("AKSHARE_TIMEOUT") from exc
        finally:
            # This is intentionally also executed after a successful direct
            # child exit. A detached descendant that no longer owns a pipe
            # must not survive a successful fetch and outlive its lease.
            await _terminate_runner_group(process, process_group_id=process.pid)
            await _await_runner_cleanup(collector_task, stdout_task, stderr_task)

        if stdout.exceeded_limit or stderr.exceeded_limit:
            raise AkShareProviderError("AKSHARE_RUNNER_OUTPUT_TOO_LARGE")
        if returncode != 0:
            detail = stderr.data.decode("utf-8", errors="replace")[:2048] or None
            raise AkShareProviderError("AKSHARE_RUNNER_FAILED", detail=detail)
        try:
            response = _strict_json_loads(stdout.data)
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            raise AkShareProviderError("AKSHARE_RUNNER_INVALID_RESPONSE") from exc
        if not isinstance(response, Mapping):
            raise AkShareProviderError("AKSHARE_RUNNER_INVALID_RESPONSE")
        return response


class AkShareMarketDataProvider:
    """Fetch a reviewed AkShare contract through a reaped subprocess runner.

    Production construction uses :meth:`from_environment`; it never imports
    AkShare or invokes an endpoint in the FastAPI process. ``test_runner`` is
    an explicit, non-production receipt seam for parent-side protocol tests.
    """

    def __init__(
        self,
        *,
        routes: Sequence[AkShareRoute] = AKSHARE_ROUTE_REGISTRY,
        command: tuple[str, ...] | None = None,
        runner_environment: Mapping[str, str] | None = None,
        runner_workdir: str | None = None,
        configuration_error: str | None = None,
        test_runner: AkShareTestRunner | None = None,
        timeout_seconds: float = 30.0,
        max_concurrency: int = 4,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("AkShare timeout_seconds must be positive")
        if max_concurrency < 1 or max_concurrency > 32:
            raise ValueError("AkShare max_concurrency must be between 1 and 32")
        if command is not None and not _is_safe_akshare_runner_command(command):
            raise ValueError(
                "runner command must be '<absolute python> -I -S <absolute runner.py>'"
            )
        if configuration_error is not None and command is not None:
            raise ValueError("configured runner command cannot carry a configuration error")
        if test_runner is not None and (command is not None or configuration_error is not None):
            raise ValueError("test runner seam cannot carry production runner configuration")
        self._routes = tuple(routes)
        self._validate_routes(self._routes)
        self._timeout_seconds = timeout_seconds
        self._semaphore = asyncio.BoundedSemaphore(max_concurrency)
        self._test_runner = test_runner
        self._runner = _AkShareSubprocessRunner(
            command=command,
            environment=runner_environment,
            workdir=runner_workdir,
            configuration_error=configuration_error
            or ("AKSHARE_RUNNER_COMMAND_UNCONFIGURED" if command is None else None),
        )

    @classmethod
    def from_environment(
        cls,
        *,
        routes: Sequence[AkShareRoute] = AKSHARE_ROUTE_REGISTRY,
        timeout_seconds: float = 30.0,
        max_concurrency: int = 4,
        parent_environment: Mapping[str, str] | None = None,
    ) -> AkShareMarketDataProvider:
        """Build the production-only subprocess adapter from operator config."""
        source = os.environ if parent_environment is None else parent_environment
        if not _has_safe_akshare_process_group():
            return cls(
                routes=routes,
                configuration_error="AKSHARE_RUNNER_PROCESS_GROUP_UNSUPPORTED",
                timeout_seconds=timeout_seconds,
                max_concurrency=max_concurrency,
            )
        raw_command = source.get(_RUNNER_COMMAND_ENVIRONMENT_KEY, "").strip()
        if not raw_command:
            return cls(
                routes=routes,
                configuration_error="AKSHARE_RUNNER_COMMAND_UNCONFIGURED",
                timeout_seconds=timeout_seconds,
                max_concurrency=max_concurrency,
            )
        try:
            command = tuple(shlex.split(raw_command))
        except ValueError:
            command = ()
        if not _is_safe_akshare_runner_command(command):
            return cls(
                routes=routes,
                configuration_error="AKSHARE_RUNNER_COMMAND_INVALID",
                timeout_seconds=timeout_seconds,
                max_concurrency=max_concurrency,
            )
        try:
            runner_environment = _akshare_runner_environment(source)
            runner_workdir = _akshare_runner_workdir(source)
        except AkShareProviderError as exc:
            return cls(
                routes=routes,
                configuration_error=exc.code,
                timeout_seconds=timeout_seconds,
                max_concurrency=max_concurrency,
            )
        return cls(
            routes=routes,
            command=command,
            runner_environment=runner_environment,
            runner_workdir=runner_workdir,
            timeout_seconds=timeout_seconds,
            max_concurrency=max_concurrency,
        )

    async def fetch(self, request: MarketDataProviderRequest) -> ProviderFetchResult:
        """Fetch only one frozen static contract after all parent checks pass."""
        if request.provider != "akshare":
            raise AkShareProviderError("AKSHARE_PROVIDER_MISMATCH")
        try:
            contract = _reviewed_contract_for_request(request)
            route = self._route_for(request)
            self._assert_route_contract_matches(route, contract)
            self._validate_route_request(route, request)
            prepared_request = contract.prepare_akshare_request(request)
            _assert_reviewed_contract_integrity(contract)
            endpoint = prepared_request.endpoint
            call_kwargs = dict(prepared_request.call_kwargs)
            _validate_call_kwargs(call_kwargs)
            source_revision = _source_revision(endpoint)
            execution = _akshare_execution_payload(
                route=route,
                contract=contract,
                prepared_request=prepared_request,
                endpoint=endpoint,
                call_kwargs=call_kwargs,
                source_revision=source_revision,
            )
        except ProviderContractError as exc:
            raise _akshare_contract_error(exc) from exc
        except AkShareProviderError:
            raise
        except Exception as exc:
            raise AkShareProviderError("AKSHARE_ROUTE_INVALID", detail=_error_detail(exc)) from exc

        response_rows = await self._fetch_response_rows(
            request=request,
            execution=execution,
            source_revision=source_revision,
        )
        try:
            # A source child can run long enough for unsafe in-process code to
            # mutate a frozen descriptor after spawn. Recompute integrity again
            # before that descriptor selects aliases or persistence provenance.
            _assert_reviewed_contract_integrity(contract)
            retrieved_at = datetime.now(_UTC)
            observations = _normalize_observations(contract, request, response_rows, retrieved_at)
            raw_payload = _build_raw_payload(
                request,
                contract,
                endpoint,
                call_kwargs,
                response_rows,
            )
        except ProviderContractError as exc:
            raise _akshare_contract_error(exc) from exc
        except AkShareProviderError:
            raise
        except Exception as exc:
            raise AkShareProviderError(
                "AKSHARE_RESPONSE_INVALID", detail=_error_detail(exc)
            ) from exc

        return ProviderFetchResult(
            provider_id="akshare",
            source_revision=source_revision,
            retrieved_at=retrieved_at,
            observations=tuple(observations),
            raw_payload=raw_payload,
            request=request,
            warnings=(
                ("AKSHARE_IDENTITY_SOURCE_REQUEST_BOUND",)
                if contract.identity_proof == "source_request_bound"
                else ()
            ),
        )

    async def _fetch_response_rows(
        self,
        *,
        request: MarketDataProviderRequest,
        execution: Mapping[str, Any],
        source_revision: str,
    ) -> list[dict[str, Any]]:
        """Await one verified runner receipt before releasing capacity."""
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=self._timeout_seconds)
        except TimeoutError as exc:
            raise AkShareProviderError("AKSHARE_TIMEOUT") from exc
        try:
            envelope = {
                "protocol_version": AKSHARE_RUNNER_PROTOCOL_VERSION,
                "request_id": request.request_id,
                "request": request.dto_payload,
                "execution": execution,
            }
            if self._test_runner is not None:
                response = self._test_runner(envelope)
                if inspect.isawaitable(response):
                    response = await asyncio.wait_for(response, timeout=self._timeout_seconds)
                if not isinstance(response, Mapping):
                    raise AkShareProviderError("AKSHARE_RUNNER_INVALID_RESPONSE")
            else:
                response = await self._runner.execute(
                    envelope,
                    timeout_seconds=self._timeout_seconds,
                )
            return _validate_runner_response(
                response=response,
                request=request,
                execution=execution,
                source_revision=source_revision,
            )
        except TimeoutError as exc:
            raise AkShareProviderError("AKSHARE_TIMEOUT") from exc
        except AkShareProviderError:
            raise
        except Exception as exc:
            raise AkShareProviderError("AKSHARE_FETCH_FAILED", detail=_error_detail(exc)) from exc
        finally:
            # The production runner does not return until group kill/reap/drain
            # finishes, so this capacity release cannot outrun its child I/O.
            self._semaphore.release()

    def _route_for(self, request: MarketDataProviderRequest) -> AkShareRoute:
        type_candidates = [
            route
            for route in self._routes
            if route.asset_type == request.asset_type
            and route.data_kind == request.data_kind
            and request.frequency in route.frequencies
        ]
        if not type_candidates:
            raise AkShareProviderError("AKSHARE_ROUTE_UNSUPPORTED")
        candidates = [
            route
            for route in type_candidates
            if route.allowed_markets is None or request.market in route.allowed_markets
        ]
        if not candidates:
            raise AkShareProviderError("AKSHARE_MARKET_UNSUPPORTED")
        # A private product family is an exact route constraint, not a hint.
        # Conversely, an older/internal caller without a family binding must
        # not become able to select the dedicated legacy K-line endpoint just
        # because it shares stock/bar/frequency dimensions with the generic
        # adapter route.
        if request.family_id is None:
            candidates = [route for route in candidates if route.family_id is None]
        else:
            candidates = [
                route
                for route in candidates
                if route.family_id == request.family_id
                and route.family_contract_version == request.family_contract_version
            ]
        if not candidates:
            raise AkShareProviderError("AKSHARE_ROUTE_UNSUPPORTED")
        # `route_id` is supplied by the reviewed source-policy route in the
        # real query path.  Respect it here as an adapter-side second check so
        # adding another exact route for the same asset/data-kind dimensions
        # cannot silently select a semantically different endpoint.
        if request.route_id is not None:
            candidates = [
                route for route in candidates if request.route_id in route.route_ids
            ]
            if not candidates:
                raise AkShareProviderError("AKSHARE_ROUTE_UNSUPPORTED")
        if len(candidates) != 1:
            raise AkShareProviderError("AKSHARE_ROUTE_UNSUPPORTED")
        return candidates[0]

    @staticmethod
    def _validate_route_request(route: AkShareRoute, request: MarketDataProviderRequest) -> None:
        if route.family_id is not None and request.family_id != route.family_id:
            raise AkShareProviderError("AKSHARE_FAMILY_UNSUPPORTED")
        if (
            route.family_contract_version is not None
            and request.family_contract_version != route.family_contract_version
        ):
            raise AkShareProviderError("AKSHARE_FAMILY_CONTRACT_VERSION_UNSUPPORTED")
        adjustment = request.adjustment or "unadjusted"
        if adjustment not in route.supported_adjustments:
            raise AkShareProviderError("AKSHARE_ADJUSTMENT_UNSUPPORTED")
        price_basis = request.price_basis or "close"
        if price_basis not in route.supported_price_bases:
            raise AkShareProviderError("AKSHARE_PRICE_BASIS_UNSUPPORTED")
        if request.currency is not None and (
            route.supported_currencies is None or request.currency not in route.supported_currencies
        ):
            raise AkShareProviderError("AKSHARE_CURRENCY_UNSUPPORTED")
        if request.unit is not None and (
            route.supported_units is None or request.unit not in route.supported_units
        ):
            raise AkShareProviderError("AKSHARE_UNIT_UNSUPPORTED")
        if (
            route.supported_product_types is not None
            and request.product_type not in route.supported_product_types
        ):
            raise AkShareProviderError("AKSHARE_PRODUCT_IDENTITY_UNSUPPORTED")
        if (
            route.supported_fund_identity_kinds is not None
            and request.fund_identity_kind not in route.supported_fund_identity_kinds
        ):
            raise AkShareProviderError("AKSHARE_PRODUCT_IDENTITY_UNSUPPORTED")
        if route.identity_proof == "source_request_bound" and request.source_policy_id is None:
            raise AkShareProviderError("AKSHARE_SOURCE_POLICY_REQUIRED")
        if route.request_validator is not None:
            route.request_validator(request)

    @staticmethod
    def _assert_route_contract_matches(route: AkShareRoute, contract: ProviderContract) -> None:
        """Reject registry drift before resolving an AkShare callable.

        ``AKSHARE_ROUTE_REGISTRY`` still makes every asset-type decision easy
        to review, while ProviderContract is the runtime source of request and
        response semantics.  Compare the material declaration axes here so a
        future route edit cannot silently retain an old contract digest.
        """
        try:
            _assert_reviewed_contract_integrity(contract)
        except ProviderContractError as exc:
            raise AkShareProviderError("AKSHARE_PROVIDER_CONTRACT_DESCRIPTOR_MISMATCH") from exc
        expected_static_endpoint = (
            next(iter(contract.endpoints))
            if contract.endpoint_resolver_id == "akshare.static-endpoint-v1"
            else None
        )
        expected_validator = _AKSHARE_REQUEST_VALIDATORS.get(contract.request_validator_id)
        if (
            contract.route_id not in route.route_ids
            or route.asset_type != contract.asset_type
            or route.data_kind != contract.data_kind
            or route.frequencies != contract.frequencies
            or route.allowed_markets != contract.markets
            or route.timestamp_columns != contract.timestamp_columns
            or route.symbol_columns != contract.symbol_columns
            or route.identity_proof != contract.identity_proof
            or route.client_filters_window != contract.client_filters_window
            or route.supported_adjustments != contract.supported_adjustments
            or route.supported_price_bases != contract.supported_price_bases
            or route.supported_currencies != contract.supported_currencies
            or route.supported_units != contract.supported_units
            or route.supported_product_types != contract.supported_product_types
            or route.supported_fund_identity_kinds != contract.supported_fund_identity_kinds
            or route.family_id != contract.family_id
            or route.family_contract_version != contract.family_contract_version
            or route.request_validator is not expected_validator
            or route.endpoint != expected_static_endpoint
            or (
                contract.endpoint_resolver_id == "akshare.cffex-option-prefix-v1"
                and route.endpoint_resolver is not _resolve_cffex_option_endpoint
            )
            or (
                contract.endpoint_resolver_id == "akshare.static-endpoint-v1"
                and route.endpoint_resolver is not None
            )
        ):
            raise AkShareProviderError("AKSHARE_PROVIDER_CONTRACT_DESCRIPTOR_MISMATCH")

    @staticmethod
    def _validate_routes(routes: tuple[AkShareRoute, ...]) -> None:
        seen_routes: dict[tuple[str, str, str], list[AkShareRoute]] = {}
        seen_route_ids: set[str] = set()
        for route in routes:
            duplicate_route_ids = seen_route_ids & route.route_ids
            if duplicate_route_ids:
                raise ValueError(
                    "duplicate AkShare source-policy route ID: "
                    f"{sorted(duplicate_route_ids)!r}"
                )
            seen_route_ids.update(route.route_ids)
            for frequency in route.frequencies:
                key = (route.asset_type, route.data_kind, frequency)
                conflicts = seen_routes.setdefault(key, [])
                if any(
                    _routes_overlap(route, existing)
                    and not _route_ids_disambiguate(route, existing)
                    for existing in conflicts
                ):
                    raise ValueError(f"duplicate AkShare route: {key!r}")
                conflicts.append(route)


# The short alias fits the provider naming used by orchestration code while
# retaining the descriptive class name above for direct configuration.
AkShareProvider = AkShareMarketDataProvider


def _resolve_endpoint(route: AkShareRoute, request: MarketDataProviderRequest) -> str:
    """Return one registry-authorized function name for this exact request."""
    if route.endpoint is not None:
        return route.endpoint
    if route.endpoint_resolver is None:
        raise AkShareProviderError("AKSHARE_ROUTE_UNSUPPORTED")
    endpoint = route.endpoint_resolver(request)
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise AkShareProviderError("AKSHARE_ROUTE_INVALID")
    return endpoint


def _akshare_contract_error(exc: ProviderContractError) -> AkShareProviderError:
    """Translate provider-neutral static contract failures to adapter codes."""
    code_by_contract_code = {
        "PROVIDER_CONTRACT_PROVIDER_MISMATCH": "AKSHARE_PROVIDER_MISMATCH",
        "PROVIDER_CONTRACT_ROUTE_REQUIRED": "AKSHARE_ROUTE_UNSUPPORTED",
        "PROVIDER_CONTRACT_UNREGISTERED": "AKSHARE_ROUTE_UNSUPPORTED",
        "PROVIDER_CONTRACT_ROUTE_MISMATCH": "AKSHARE_ROUTE_UNSUPPORTED",
        "PROVIDER_CONTRACT_FAMILY_MISMATCH": "AKSHARE_ROUTE_UNSUPPORTED",
        "PROVIDER_CONTRACT_REQUEST_MISMATCH": "AKSHARE_ROUTE_UNSUPPORTED",
        "PROVIDER_CONTRACT_FREQUENCY_UNSUPPORTED": "AKSHARE_ROUTE_UNSUPPORTED",
        "PROVIDER_CONTRACT_MARKET_UNSUPPORTED": "AKSHARE_MARKET_UNSUPPORTED",
        "PROVIDER_CONTRACT_ADJUSTMENT_UNSUPPORTED": "AKSHARE_ADJUSTMENT_UNSUPPORTED",
        "PROVIDER_CONTRACT_PRICE_BASIS_UNSUPPORTED": "AKSHARE_PRICE_BASIS_UNSUPPORTED",
        "PROVIDER_CONTRACT_CURRENCY_UNSUPPORTED": "AKSHARE_CURRENCY_UNSUPPORTED",
        "PROVIDER_CONTRACT_UNIT_UNSUPPORTED": "AKSHARE_UNIT_UNSUPPORTED",
        "PROVIDER_CONTRACT_PRODUCT_IDENTITY_UNSUPPORTED": "AKSHARE_PRODUCT_IDENTITY_UNSUPPORTED",
        "PROVIDER_CONTRACT_SOURCE_POLICY_REQUIRED": "AKSHARE_SOURCE_POLICY_REQUIRED",
        "PROVIDER_CONTRACT_ENDPOINT_UNSUPPORTED": "AKSHARE_SYMBOL_MARKET_MISMATCH",
        "PROVIDER_CONTRACT_DESCRIPTOR_MISMATCH": "AKSHARE_PROVIDER_CONTRACT_DESCRIPTOR_MISMATCH",
        "PROVIDER_CONTRACT_FIELD_MAPPING_MISSING": "AKSHARE_PROVIDER_CONTRACT_FIELD_MAPPING_MISSING",
        "PROVIDER_CONTRACT_TRANSFORM_UNSUPPORTED": "AKSHARE_PROVIDER_CONTRACT_INVALID",
    }
    return AkShareProviderError(
        code_by_contract_code.get(exc.code, "AKSHARE_PROVIDER_CONTRACT_INVALID"),
        detail=exc.detail,
    )


def _canonical_json(payload: Mapping[str, Any]) -> str:
    """Encode a runner receipt in one deterministic, strict JSON representation."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )


def _is_safe_akshare_runner_file(value: object, *, executable: bool) -> bool:
    """Accept one existing absolute runner file or Python executable only."""
    if not isinstance(value, str) or not value or "\x00" in value:
        return False
    path = Path(value)
    if not path.is_absolute():
        return False
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    return resolved.is_file() and (not executable or os.access(resolved, os.X_OK))


def _is_safe_akshare_python(value: object) -> bool:
    """Require an absolute Python interpreter rather than a shell/wrapper."""
    if not _is_safe_akshare_runner_file(value, executable=True):
        return False
    try:
        executable_name = Path(str(value)).resolve(strict=True).name
    except (OSError, RuntimeError, ValueError):
        return False
    return re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", executable_name) is not None


def _is_safe_akshare_runner_command(command: tuple[str, ...]) -> bool:
    """Require only ``<absolute python> -I -S <absolute runner.py>``."""
    return (
        len(command) == 4
        and _is_safe_akshare_python(command[0])
        and command[1] == "-I"
        and command[2] == "-S"
        and _is_safe_akshare_runner_file(command[3], executable=False)
    )


def _runner_path_overlaps_application_checkout(path: Path) -> bool:
    """Reject a runner directory that exposes the web checkout or its parent."""
    try:
        resolved = path.resolve(strict=True)
        source_path = Path(__file__).resolve(strict=True)
        checkout_root = next(
            (parent for parent in source_path.parents if (parent / ".git").exists()),
            None,
        )
        current_workdir = Path.cwd().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return True
    protected_paths = [current_workdir]
    if checkout_root is not None:
        protected_paths.append(checkout_root)
    return any(
        resolved == protected
        or resolved.is_relative_to(protected)
        or protected.is_relative_to(resolved)
        for protected in protected_paths
    )


def _dedicated_akshare_runner_directory(
    source: Mapping[str, str],
    *,
    environment_key: str,
    error_code: str,
) -> str:
    """Resolve a configured runner-only directory without inherited fallback."""
    configured = source.get(environment_key, "").strip()
    if not configured or "\x00" in configured:
        raise AkShareProviderError(error_code)
    candidate = Path(configured)
    if not candidate.is_absolute():
        raise AkShareProviderError(error_code)
    try:
        resolved = candidate.resolve(strict=True)
        temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise AkShareProviderError(error_code) from exc
    if (
        not resolved.is_dir()
        or resolved == temporary_root
        or _runner_path_overlaps_application_checkout(resolved)
    ):
        raise AkShareProviderError(error_code)
    inherited_home = source.get("HOME", "").strip()
    if inherited_home:
        try:
            inherited_home_path = Path(inherited_home).resolve(strict=True)
        except (OSError, RuntimeError, ValueError):
            inherited_home_path = None
        if inherited_home_path is not None and resolved == inherited_home_path:
            raise AkShareProviderError(error_code)
    return str(resolved)


def _akshare_runner_site_packages(source: Mapping[str, str]) -> str:
    """Pass one operator-selected package directory to the isolated runner."""
    configured = source.get(_RUNNER_SITE_PACKAGES_ENVIRONMENT_KEY, "").strip()
    if not configured or "\x00" in configured:
        raise AkShareProviderError("AKSHARE_RUNNER_SITE_PACKAGES_INVALID")
    candidate = Path(configured)
    if not candidate.is_absolute():
        raise AkShareProviderError("AKSHARE_RUNNER_SITE_PACKAGES_INVALID")
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise AkShareProviderError("AKSHARE_RUNNER_SITE_PACKAGES_INVALID") from exc
    if not resolved.is_dir() or _runner_path_overlaps_application_checkout(resolved):
        raise AkShareProviderError("AKSHARE_RUNNER_SITE_PACKAGES_INVALID")
    return str(resolved)


def _akshare_runner_environment(parent: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build a minimal runner environment without app secrets or proxy config."""
    source = os.environ if parent is None else parent
    environment = {
        key: value for key in _RUNNER_BASE_ENVIRONMENT_KEYS if (value := source.get(key))
    }
    environment["HOME"] = _dedicated_akshare_runner_directory(
        source,
        environment_key=_RUNNER_HOME_ENVIRONMENT_KEY,
        error_code="AKSHARE_RUNNER_HOME_INVALID",
    )
    environment[_RUNNER_SITE_PACKAGES_ENVIRONMENT_KEY] = _akshare_runner_site_packages(source)
    return environment


def _akshare_runner_workdir(parent: Mapping[str, str] | None = None) -> str:
    """Return a dedicated runner working directory, never the web checkout."""
    source = os.environ if parent is None else parent
    return _dedicated_akshare_runner_directory(
        source,
        environment_key=_RUNNER_WORKDIR_ENVIRONMENT_KEY,
        error_code="AKSHARE_RUNNER_WORKDIR_INVALID",
    )


def _validate_call_kwargs(call_kwargs: Mapping[str, Any]) -> None:
    """Reject non-JSON or unbounded parent-built endpoint arguments before spawn."""
    if not isinstance(call_kwargs, Mapping) or len(call_kwargs) > 32:
        raise AkShareProviderError("AKSHARE_ROUTE_INVALID")
    if any(not isinstance(key, str) or not key.strip() for key in call_kwargs):
        raise AkShareProviderError("AKSHARE_ROUTE_INVALID")
    try:
        _canonical_json(dict(call_kwargs))
    except (TypeError, ValueError) as exc:
        raise AkShareProviderError("AKSHARE_ROUTE_INVALID") from exc


def _akshare_execution_payload(
    *,
    route: AkShareRoute,
    contract: ProviderContract,
    prepared_request: PreparedProviderRequest,
    endpoint: str,
    call_kwargs: Mapping[str, Any],
    source_revision: str,
) -> dict[str, Any]:
    """Freeze parent-parsed route and static-contract facts for the runner."""
    return {
        "route": {
            "asset_type": route.asset_type,
            "data_kind": route.data_kind,
            "frequencies": sorted(route.frequencies),
            "allowed_markets": sorted(route.allowed_markets) if route.allowed_markets else None,
            "timestamp_columns": list(route.timestamp_columns),
            "symbol_columns": list(route.symbol_columns),
            "identity_proof": route.identity_proof,
            "client_filters_window": route.client_filters_window,
            "route_ids": sorted(route.route_ids),
            "family_id": route.family_id,
            "family_contract_version": route.family_contract_version,
        },
        "provider_contract": _json_safe(contract.summary),
        "prepared_request": {
            "contract_id": prepared_request.contract_id,
            "descriptor_sha256": prepared_request.descriptor_sha256,
        },
        "endpoint": endpoint,
        "call_kwargs": _json_safe(call_kwargs),
        "source_revision": source_revision,
    }


def _runner_error_code(value: object) -> str:
    """Accept only a bounded AkShare-domain error code from the child."""
    if not isinstance(value, str) or not re.fullmatch(r"AKSHARE_[A-Z0-9_]{1,120}", value):
        return "AKSHARE_RUNNER_ERROR"
    return value


def _mapping_matches(left: object, right: Mapping[str, Any]) -> bool:
    """Compare untrusted JSON by canonical bytes, rejecting non-object values."""
    if not isinstance(left, Mapping):
        return False
    try:
        return _canonical_json(dict(left)) == _canonical_json(dict(right))
    except (TypeError, ValueError):
        return False


def _validate_runner_response(
    *,
    response: Mapping[str, Any],
    request: MarketDataProviderRequest,
    execution: Mapping[str, Any],
    source_revision: str,
) -> list[dict[str, Any]]:
    """Authenticate a child receipt before reusing parent normalization logic."""
    expected_receipt_fields = {
        "protocol_version",
        "request_id",
        "request",
        "execution",
        "source_revision",
    }
    if not isinstance(response, Mapping) or not expected_receipt_fields <= set(response):
        raise AkShareProviderError("AKSHARE_RUNNER_INVALID_RESPONSE")
    allowed_receipt_fields = expected_receipt_fields | {"response_rows", "error"}
    if set(response) - allowed_receipt_fields:
        raise AkShareProviderError("AKSHARE_RUNNER_INVALID_RESPONSE")
    if response.get("protocol_version") != AKSHARE_RUNNER_PROTOCOL_VERSION:
        raise AkShareProviderError("AKSHARE_RUNNER_PROTOCOL_MISMATCH")
    if response.get("request_id") != request.request_id:
        raise AkShareProviderError("AKSHARE_RUNNER_PROTOCOL_MISMATCH")
    if not _mapping_matches(response.get("request"), request.dto_payload):
        raise AkShareProviderError("AKSHARE_RUNNER_PROTOCOL_MISMATCH")
    if not _mapping_matches(response.get("execution"), execution):
        raise AkShareProviderError("AKSHARE_RUNNER_PROTOCOL_MISMATCH")
    if response.get("source_revision") != source_revision:
        raise AkShareProviderError("AKSHARE_RUNNER_SOURCE_REVISION_MISMATCH")
    error = response.get("error")
    if error is not None:
        if not isinstance(error, Mapping) or "response_rows" in response:
            raise AkShareProviderError("AKSHARE_RUNNER_INVALID_RESPONSE")
        detail = error.get("detail")
        raise AkShareProviderError(
            _runner_error_code(error.get("code")),
            detail=str(detail)[:512] if detail is not None else None,
        )
    rows = response.get("response_rows")
    if not isinstance(rows, list):
        raise AkShareProviderError("AKSHARE_RUNNER_INVALID_RESPONSE")
    try:
        _canonical_json({"response_rows": rows})
    except (TypeError, ValueError) as exc:
        raise AkShareProviderError("AKSHARE_RUNNER_INVALID_RESPONSE") from exc
    return _coerce_response_rows(rows)



def _routes_overlap(left: AkShareRoute, right: AkShareRoute) -> bool:
    """Return whether two same-kind routes can accept the same exact market."""
    if left.allowed_markets is None or right.allowed_markets is None:
        return True
    return bool(left.allowed_markets & right.allowed_markets)


def _route_ids_disambiguate(left: AkShareRoute, right: AkShareRoute) -> bool:
    """Return whether server-issued policy route IDs separate overlapping products.

    Products such as ETF liquidity and NAV legitimately share asset type,
    data kind, frequency and market. They may coexist only when their
    non-empty policy route-ID sets are disjoint. A direct adapter call without
    one of those IDs still sees multiple candidates and fails closed in
    ``_route_for``; only the server-owned source-policy path supplies it.
    """
    return bool(left.route_ids and right.route_ids and left.route_ids.isdisjoint(right.route_ids))


def _coerce_response_rows(response: object) -> list[dict[str, Any]]:
    """Convert dataframe-like output to bounded mappings without importing pandas."""
    if response is None:
        return []
    try:
        response_length = len(response)  # type: ignore[arg-type]
    except TypeError:
        response_length = None
    if response_length is not None and response_length > _MAX_RESPONSE_ROWS:
        raise AkShareProviderError("AKSHARE_RESPONSE_TOO_LARGE")
    rows: object
    to_dict = getattr(response, "to_dict", None)
    if callable(to_dict):
        try:
            rows = to_dict(orient="records")
        except (TypeError, ValueError) as exc:
            raise AkShareProviderError("AKSHARE_RESPONSE_INVALID") from exc
    elif isinstance(response, Sequence) and not isinstance(response, (str, bytes, bytearray)):
        rows = response
    else:
        raise AkShareProviderError("AKSHARE_RESPONSE_INVALID")

    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise AkShareProviderError("AKSHARE_RESPONSE_INVALID")
    if len(rows) > _MAX_RESPONSE_ROWS:
        raise AkShareProviderError("AKSHARE_RESPONSE_TOO_LARGE")

    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise AkShareProviderError("AKSHARE_RESPONSE_INVALID")
        normalized_rows.append(dict(row))
    return normalized_rows


def _build_raw_payload(
    request: MarketDataProviderRequest,
    contract: ProviderContract,
    endpoint: str,
    call_kwargs: Mapping[str, Any],
    response_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build and size-check persistence provenance outside the request event loop."""
    payload = {
        "request": {
            **request.dto_payload,
            "request_id": request.request_id,
            "canonical_id": request.canonical_id,
            "provider_symbol": request.provider_symbol,
        },
        "route": {
            "endpoint": endpoint,
            "call_kwargs": _json_safe(call_kwargs),
            "identity_proof": contract.identity_proof,
            "client_filters_window": contract.client_filters_window,
        },
        "provider_contract": _json_safe(contract.summary),
        "response_rows": [_json_safe(row) for row in response_rows],
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    if len(encoded) > _MAX_PROVENANCE_BYTES:
        raise AkShareProviderError("AKSHARE_PROVENANCE_TOO_LARGE")
    return payload


def _normalize_observations(
    contract: ProviderContract,
    request: MarketDataProviderRequest,
    response_rows: Sequence[Mapping[str, Any]],
    retrieved_at: datetime,
) -> list[ProviderMarketObservation]:
    """Validate identity and timestamps before creating persistence-ready rows."""
    observations: list[ProviderMarketObservation] = []
    seen_events: set[datetime] = set()
    for row in response_rows:
        _validate_response_identity(contract, request, row)
        timestamps = _present_columns(row, contract.timestamp_columns)
        if not timestamps:
            raise AkShareProviderError("AKSHARE_TIMESTAMP_MISSING")
        if len(timestamps) != 1:
            raise AkShareProviderError("AKSHARE_RESPONSE_AMBIGUOUS_TIMESTAMP")
        _, timestamp_value = timestamps[0]
        event_at = _parse_event_at(timestamp_value)
        if not request.start_at <= event_at < request.end_at:
            if contract.client_filters_window:
                continue
            raise AkShareProviderError("AKSHARE_RESPONSE_OUT_OF_WINDOW")
        if event_at in seen_events:
            raise AkShareProviderError("AKSHARE_RESPONSE_DUPLICATE_EVENT")
        seen_events.add(event_at)
        fields = _normalize_fields(
            row,
            contract=contract,
            required_fields=request.required_fields,
        )
        observations.append(
            ProviderMarketObservation(
                event_at=event_at,
                available_at=retrieved_at,
                fields=fields,
            )
        )
    return observations


def _validate_response_identity(
    contract: ProviderContract,
    request: MarketDataProviderRequest,
    row: Mapping[str, Any],
) -> None:
    """Require an exact returned symbol where the source route exposes one."""
    if contract.identity_proof == "source_request_bound":
        return
    source_symbols = _present_columns(row, contract.symbol_columns)
    if not source_symbols:
        raise AkShareProviderError("AKSHARE_IDENTITY_UNVERIFIABLE")
    for _, source_symbol in source_symbols:
        if not isinstance(source_symbol, str) or source_symbol.strip() != request.provider_symbol:
            raise AkShareProviderError("AKSHARE_IDENTITY_MISMATCH")


def _present_columns(row: Mapping[str, Any], columns: Sequence[str]) -> list[tuple[str, Any]]:
    """Return every explicit source-column match so conflicting facts cannot hide."""
    return [(column, row[column]) for column in columns if column in row]


def _parse_event_at(value: object) -> datetime:
    """Normalize date-only daily bars to UTC midnight and reject ambiguous instants."""
    if isinstance(value, datetime):
        if value.tzinfo is not None and value.utcoffset() is not None:
            return value.astimezone(_UTC)
        return datetime(value.year, value.month, value.day, tzinfo=_UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=_UTC)
    if not isinstance(value, str):
        raise AkShareProviderError("AKSHARE_TIMESTAMP_INVALID")
    normalized = value.strip()
    if not normalized:
        raise AkShareProviderError("AKSHARE_TIMESTAMP_INVALID")
    try:
        parsed_date = date.fromisoformat(normalized)
    except ValueError:
        try:
            parsed_datetime = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AkShareProviderError("AKSHARE_TIMESTAMP_INVALID") from exc
        if parsed_datetime.tzinfo is not None and parsed_datetime.utcoffset() is not None:
            return parsed_datetime.astimezone(_UTC)
        return datetime(
            parsed_datetime.year, parsed_datetime.month, parsed_datetime.day, tzinfo=_UTC
        )
    return datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=_UTC)


def _normalize_fields(
    row: Mapping[str, Any],
    *,
    contract: ProviderContract,
    required_fields: frozenset[str],
) -> dict[str, Any]:
    """Map approved source labels while preserving other fields exactly."""
    excluded_columns = {*contract.timestamp_columns, *contract.symbol_columns}
    fields: dict[str, Any] = {}
    for raw_name, raw_value in row.items():
        if not isinstance(raw_name, str):
            raise AkShareProviderError("AKSHARE_RESPONSE_INVALID")
        source_name = raw_name.strip()
        if not source_name:
            raise AkShareProviderError("AKSHARE_RESPONSE_INVALID")
        if raw_name in excluded_columns:
            continue
        field_name = contract.normalized_field_name(source_name)
        if field_name in fields:
            raise AkShareProviderError("AKSHARE_RESPONSE_AMBIGUOUS_FIELDS")
        fields[field_name] = _json_safe(raw_value)

    missing_fields = sorted(
        field_name
        for field_name in required_fields
        if field_name not in fields or fields[field_name] is None
    )
    if missing_fields:
        raise AkShareProviderError(
            "AKSHARE_REQUIRED_FIELDS_MISSING", detail=",".join(missing_fields)
        )
    if not fields:
        raise AkShareProviderError("AKSHARE_RESPONSE_INVALID")
    return fields


def _source_revision(endpoint: str) -> str:
    """Expose the installed source version alongside the reviewed endpoint name."""
    try:
        version = metadata.version("akshare")
    except metadata.PackageNotFoundError:
        version = "unknown"
    return f"akshare-{version}:{endpoint}"


def _json_safe(value: Any) -> Any:
    """Convert common dataframe scalars to deterministic persistence-safe values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return _json_safe(item_method())
        except (TypeError, ValueError):
            pass
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        try:
            return str(isoformat())
        except (TypeError, ValueError):
            pass
    return str(value)


def _error_detail(exc: Exception) -> str:
    """Keep provider diagnostics bounded before exposing them to orchestration logs."""
    return str(exc)[:512]
