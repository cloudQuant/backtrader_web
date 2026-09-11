"""Static, fail-closed provider contracts for reviewed market-data adapters.

OpenBB separates query transformation, provider extraction, and response
transformation.  This module supplies the equivalent *static control-plane*
boundary for adapters that remain in this application process.  It contains no
network client, database handle, runtime permit, or capability switch.  A
contract therefore records what an adapter is allowed to transform, not whether
an online route is enabled in a deployment.

The initial registry describes only reviewed AkShare request/response shapes.
The adapter must select one exact contract before resolving a provider callable.
Unknown routes, mismatched family/endpoint descriptors, and required fields
that no reviewed normalizer can emit all fail before provider I/O.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Any, Literal

from app.services.market_data.dataset_contracts import (
    FAMILY_CONTRACT_VERSION,
    KLINE_LEGACY_CONTRACT_VERSION,
    KLINE_LEGACY_FAMILY_ID,
)
from app.services.market_data.providers import MarketDataProviderRequest

_UTC = timezone.utc

PROVIDER_CONTRACT_DESCRIPTOR_VERSION = "market-data-provider-contract-v1"
AKSHARE_PROVIDER_CONTRACT_VERSION = "akshare-provider-contract-v1"
AKSHARE_ROW_NORMALIZER_ID = "akshare-row-normalizer-v1"
AKSHARE_UTC_DATE_NORMALIZER_ID = "akshare-utc-date-normalizer-v1"
AKSHARE_HALF_OPEN_WINDOW_SEMANTICS = "utc-half-open-window-v1"


class ProviderContractError(RuntimeError):
    """Stable failure emitted while selecting or transforming a contract."""

    def __init__(self, code: str, *, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(code)


def _text(value: object, *, field_name: str, maximum: int = 256) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{field_name} must be non-blank and at most {maximum} characters")
    return normalized


def _text_tuple(
    value: object,
    *,
    field_name: str,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{field_name} must be a tuple")
    normalized = tuple(_text(item, field_name=field_name) for item in value)
    if not normalized and not allow_empty:
        raise ValueError(f"{field_name} must not be empty")
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


def _text_set(
    value: object,
    *,
    field_name: str,
    allow_empty: bool = False,
) -> frozenset[str]:
    if not isinstance(value, frozenset):
        raise ValueError(f"{field_name} must be a frozenset")
    normalized = frozenset(_text(item, field_name=field_name) for item in value)
    if not normalized and not allow_empty:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _optional_text_set(value: object, *, field_name: str) -> frozenset[str] | None:
    if value is None:
        return None
    return _text_set(value, field_name=field_name)


def _mapping(value: object, *, field_name: str) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    normalized: dict[str, str] = {}
    for source_name, field_name_value in value.items():
        source = _text(source_name, field_name=f"{field_name} source")
        normalized_field = _text(field_name_value, field_name=f"{field_name} value")
        if source in normalized:
            raise ValueError(f"{field_name} source names must be distinct")
        normalized[source] = normalized_field
    return MappingProxyType(normalized)


def _canonical_json(payload: Mapping[str, Any]) -> str:
    # Descriptors deliberately expose read-only mapping proxies.  Snapshot the
    # top-level mapping before JSON encoding so its immutability boundary does
    # not change the canonical bytes used for the digest.
    return json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _descriptor_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ProviderResponseFieldProfile:
    """Reviewed normalized response fields for one provider product route.

    ``required_fields`` and ``optional_fields`` mirror the product-level field
    profile.  ``mapped_fields`` can be broader because an adapter preserves
    compatible source fields that are useful to a private compatibility route,
    while still rejecting a request for an entirely unmapped required field
    before its provider callable is resolved.
    """

    profile_id: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()
    mapped_fields: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "profile_id", _text(self.profile_id, field_name="profile_id"))
        required = _text_tuple(self.required_fields, field_name="required_fields")
        optional = _text_tuple(
            self.optional_fields,
            field_name="optional_fields",
            allow_empty=True,
        )
        if set(required) & set(optional):
            raise ValueError("required_fields and optional_fields must not overlap")
        mapped = _text_set(self.mapped_fields, field_name="mapped_fields")
        if not set(required) <= mapped or not set(optional) <= mapped:
            raise ValueError("field profile fields must have a reviewed response mapping")
        object.__setattr__(self, "required_fields", required)
        object.__setattr__(self, "optional_fields", optional)
        object.__setattr__(self, "mapped_fields", mapped)

    @property
    def descriptor(self) -> Mapping[str, Any]:
        """Return a canonicalizable, adapter-independent field declaration."""
        return MappingProxyType(
            {
                "profile_id": self.profile_id,
                "required_fields": list(self.required_fields),
                "optional_fields": list(self.optional_fields),
                "mapped_fields": sorted(self.mapped_fields),
            }
        )


@dataclass(frozen=True, slots=True)
class PreparedProviderRequest:
    """Pure transform result handed to an adapter after contract selection."""

    contract_id: str
    descriptor_sha256: str
    endpoint: str
    call_kwargs: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "contract_id", _text(self.contract_id, field_name="contract_id"))
        digest = _text(self.descriptor_sha256, field_name="descriptor_sha256", maximum=64)
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("descriptor_sha256 must be a lowercase SHA-256 hex digest")
        object.__setattr__(self, "descriptor_sha256", digest)
        object.__setattr__(self, "endpoint", _text(self.endpoint, field_name="endpoint"))
        if not isinstance(self.call_kwargs, Mapping):
            raise TypeError("call_kwargs must be a mapping")
        normalized: dict[str, Any] = {}
        for key, value in self.call_kwargs.items():
            normalized[_text(key, field_name="call_kwargs key")] = value
        object.__setattr__(self, "call_kwargs", MappingProxyType(normalized))


@dataclass(frozen=True, slots=True)
class ProviderContract:
    """One immutable reviewed provider route descriptor.

    The descriptor intentionally includes request transformation, response
    field mapping, time/window semantics, semantic axes, and endpoint choices.
    The digest excludes itself and is recomputed at construction and registry
    load time, preventing a copied descriptor from being silently retagged.
    """

    contract_id: str
    contract_version: str
    provider: str
    route_id: str
    family_id: str
    family_contract_version: str
    asset_type: str
    data_kind: str
    frequencies: frozenset[str]
    markets: frozenset[str]
    supported_adjustments: frozenset[str]
    supported_price_bases: frozenset[str]
    supported_currencies: frozenset[str] | None
    supported_units: frozenset[str] | None
    field_profile: ProviderResponseFieldProfile
    response_field_aliases: Mapping[str, str]
    timestamp_columns: tuple[str, ...]
    symbol_columns: tuple[str, ...]
    identity_proof: Literal["source_request_bound", "response_symbol"]
    source_policy_required: bool
    client_filters_window: bool
    request_transform_id: str
    endpoint_resolver_id: str
    endpoints: frozenset[str]
    request_validator_id: str | None = None
    supported_product_types: frozenset[str] | None = None
    supported_fund_identity_kinds: frozenset[str] | None = None
    normalizer_id: str = AKSHARE_ROW_NORMALIZER_ID
    timestamp_normalizer_id: str = AKSHARE_UTC_DATE_NORMALIZER_ID
    window_semantics: str = AKSHARE_HALF_OPEN_WINDOW_SEMANTICS
    descriptor_sha256: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "contract_id",
            "contract_version",
            "provider",
            "route_id",
            "family_id",
            "family_contract_version",
            "asset_type",
            "data_kind",
            "request_transform_id",
            "endpoint_resolver_id",
            "normalizer_id",
            "timestamp_normalizer_id",
            "window_semantics",
        ):
            object.__setattr__(
                self, field_name, _text(getattr(self, field_name), field_name=field_name)
            )
        object.__setattr__(
            self, "frequencies", _text_set(self.frequencies, field_name="frequencies")
        )
        object.__setattr__(self, "markets", _text_set(self.markets, field_name="markets"))
        object.__setattr__(
            self,
            "supported_adjustments",
            _text_set(self.supported_adjustments, field_name="supported_adjustments"),
        )
        object.__setattr__(
            self,
            "supported_price_bases",
            _text_set(self.supported_price_bases, field_name="supported_price_bases"),
        )
        object.__setattr__(
            self,
            "supported_currencies",
            _optional_text_set(self.supported_currencies, field_name="supported_currencies"),
        )
        object.__setattr__(
            self,
            "supported_units",
            _optional_text_set(self.supported_units, field_name="supported_units"),
        )
        if not isinstance(self.field_profile, ProviderResponseFieldProfile):
            raise TypeError("field_profile must be ProviderResponseFieldProfile")
        aliases = _mapping(self.response_field_aliases, field_name="response_field_aliases")
        if not set(aliases.values()) <= self.field_profile.mapped_fields:
            raise ValueError("response field aliases must map only to profile mapped_fields")
        object.__setattr__(self, "response_field_aliases", aliases)
        object.__setattr__(
            self,
            "timestamp_columns",
            _text_tuple(self.timestamp_columns, field_name="timestamp_columns"),
        )
        object.__setattr__(
            self,
            "symbol_columns",
            _text_tuple(
                self.symbol_columns,
                field_name="symbol_columns",
                allow_empty=True,
            ),
        )
        if self.identity_proof not in {"source_request_bound", "response_symbol"}:
            raise ValueError("identity_proof is invalid")
        if self.identity_proof == "response_symbol" and not self.symbol_columns:
            raise ValueError("response_symbol contracts require symbol_columns")
        if not isinstance(self.source_policy_required, bool):
            raise TypeError("source_policy_required must be bool")
        if not isinstance(self.client_filters_window, bool):
            raise TypeError("client_filters_window must be bool")
        object.__setattr__(self, "endpoints", _text_set(self.endpoints, field_name="endpoints"))
        if self.endpoint_resolver_id == "akshare.static-endpoint-v1" and len(self.endpoints) != 1:
            raise ValueError("static endpoint contracts require exactly one endpoint")
        if (
            self.endpoint_resolver_id == "akshare.cffex-option-prefix-v1"
            and len(self.endpoints) != 3
        ):
            raise ValueError("CFFEX option contracts require all three reviewed endpoints")
        if self.endpoint_resolver_id not in {
            "akshare.static-endpoint-v1",
            "akshare.cffex-option-prefix-v1",
        }:
            raise ValueError("endpoint_resolver_id is unsupported")
        if self.request_transform_id not in {
            "akshare.historical-kline-request-v1",
            "akshare.fund-nav-request-v1",
            "akshare.symbol-only-request-v1",
        }:
            raise ValueError("request_transform_id is unsupported")
        if self.normalizer_id != AKSHARE_ROW_NORMALIZER_ID:
            raise ValueError("normalizer_id is unsupported")
        if self.timestamp_normalizer_id != AKSHARE_UTC_DATE_NORMALIZER_ID:
            raise ValueError("timestamp_normalizer_id is unsupported")
        if self.window_semantics != AKSHARE_HALF_OPEN_WINDOW_SEMANTICS:
            raise ValueError("window_semantics is unsupported")
        if self.request_validator_id is not None:
            object.__setattr__(
                self,
                "request_validator_id",
                _text(self.request_validator_id, field_name="request_validator_id"),
            )
        object.__setattr__(
            self,
            "supported_product_types",
            _optional_text_set(self.supported_product_types, field_name="supported_product_types"),
        )
        object.__setattr__(
            self,
            "supported_fund_identity_kinds",
            _optional_text_set(
                self.supported_fund_identity_kinds,
                field_name="supported_fund_identity_kinds",
            ),
        )
        if self.supported_fund_identity_kinds is not None and self.asset_type != "fund":
            raise ValueError("supported_fund_identity_kinds require a fund contract")
        expected_digest = _descriptor_sha256(self._descriptor_without_digest())
        if self.descriptor_sha256 is not None:
            declared = _text(
                self.descriptor_sha256,
                field_name="descriptor_sha256",
                maximum=64,
            ).lower()
            if declared != expected_digest:
                raise ProviderContractError("PROVIDER_CONTRACT_DESCRIPTOR_MISMATCH")
        object.__setattr__(self, "descriptor_sha256", expected_digest)

    def _descriptor_without_digest(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "descriptor_version": PROVIDER_CONTRACT_DESCRIPTOR_VERSION,
                "contract_id": self.contract_id,
                "contract_version": self.contract_version,
                "provider": self.provider,
                "route_id": self.route_id,
                "family_id": self.family_id,
                "family_contract_version": self.family_contract_version,
                "asset_type": self.asset_type,
                "data_kind": self.data_kind,
                "frequencies": sorted(self.frequencies),
                "markets": sorted(self.markets),
                "supported_adjustments": sorted(self.supported_adjustments),
                "supported_price_bases": sorted(self.supported_price_bases),
                "supported_currencies": (
                    sorted(self.supported_currencies)
                    if self.supported_currencies is not None
                    else None
                ),
                "supported_units": sorted(self.supported_units)
                if self.supported_units is not None
                else None,
                "field_profile": dict(self.field_profile.descriptor),
                "response_field_aliases": dict(sorted(self.response_field_aliases.items())),
                "timestamp_columns": list(self.timestamp_columns),
                "symbol_columns": list(self.symbol_columns),
                "identity_proof": self.identity_proof,
                "source_policy_required": self.source_policy_required,
                "client_filters_window": self.client_filters_window,
                "request_transform_id": self.request_transform_id,
                "endpoint_resolver_id": self.endpoint_resolver_id,
                "endpoints": sorted(self.endpoints),
                "request_validator_id": self.request_validator_id,
                "supported_product_types": (
                    sorted(self.supported_product_types)
                    if self.supported_product_types is not None
                    else None
                ),
                "supported_fund_identity_kinds": (
                    sorted(self.supported_fund_identity_kinds)
                    if self.supported_fund_identity_kinds is not None
                    else None
                ),
                "normalizer_id": self.normalizer_id,
                "timestamp_normalizer_id": self.timestamp_normalizer_id,
                "window_semantics": self.window_semantics,
            }
        )

    @property
    def descriptor(self) -> Mapping[str, Any]:
        """Return a copy-safe static descriptor including its recomputed digest."""
        payload = dict(self._descriptor_without_digest())
        payload["descriptor_sha256"] = self.descriptor_sha256
        return MappingProxyType(payload)

    @property
    def summary(self) -> Mapping[str, str]:
        """Return the compact, stable receipt summary for one selected contract."""
        return MappingProxyType(
            {
                "contract_id": self.contract_id,
                "contract_version": self.contract_version,
                "provider": self.provider,
                "route_id": self.route_id,
                "family_id": self.family_id,
                "family_contract_version": self.family_contract_version,
                "field_profile_id": self.field_profile.profile_id,
                "normalizer_id": self.normalizer_id,
                "timestamp_normalizer_id": self.timestamp_normalizer_id,
                "window_semantics": self.window_semantics,
                "descriptor_sha256": self.descriptor_sha256,
            }
        )

    def assert_request_matches(self, request: MarketDataProviderRequest) -> None:
        """Validate every provider-selection axis before any source callable is resolved."""
        if request.provider != self.provider:
            raise ProviderContractError("PROVIDER_CONTRACT_PROVIDER_MISMATCH")
        if request.route_id is None:
            raise ProviderContractError("PROVIDER_CONTRACT_ROUTE_REQUIRED")
        if request.route_id != self.route_id:
            raise ProviderContractError("PROVIDER_CONTRACT_ROUTE_MISMATCH")
        if (
            request.family_id != self.family_id
            or request.family_contract_version != self.family_contract_version
        ):
            raise ProviderContractError("PROVIDER_CONTRACT_FAMILY_MISMATCH")
        if request.asset_type != self.asset_type or request.data_kind != self.data_kind:
            raise ProviderContractError("PROVIDER_CONTRACT_REQUEST_MISMATCH")
        if request.frequency not in self.frequencies:
            raise ProviderContractError("PROVIDER_CONTRACT_FREQUENCY_UNSUPPORTED")
        if request.market not in self.markets:
            raise ProviderContractError("PROVIDER_CONTRACT_MARKET_UNSUPPORTED")
        adjustment = request.adjustment or "unadjusted"
        if adjustment not in self.supported_adjustments:
            raise ProviderContractError("PROVIDER_CONTRACT_ADJUSTMENT_UNSUPPORTED")
        price_basis = request.price_basis or "close"
        if price_basis not in self.supported_price_bases:
            raise ProviderContractError("PROVIDER_CONTRACT_PRICE_BASIS_UNSUPPORTED")
        if request.currency is not None and (
            self.supported_currencies is None or request.currency not in self.supported_currencies
        ):
            raise ProviderContractError("PROVIDER_CONTRACT_CURRENCY_UNSUPPORTED")
        if request.unit is not None and (
            self.supported_units is None or request.unit not in self.supported_units
        ):
            raise ProviderContractError("PROVIDER_CONTRACT_UNIT_UNSUPPORTED")
        if (
            self.supported_product_types is not None
            and request.product_type not in self.supported_product_types
        ):
            raise ProviderContractError("PROVIDER_CONTRACT_PRODUCT_IDENTITY_UNSUPPORTED")
        if (
            self.supported_fund_identity_kinds is not None
            and request.fund_identity_kind not in self.supported_fund_identity_kinds
        ):
            raise ProviderContractError("PROVIDER_CONTRACT_PRODUCT_IDENTITY_UNSUPPORTED")
        if self.source_policy_required and request.source_policy_id is None:
            raise ProviderContractError("PROVIDER_CONTRACT_SOURCE_POLICY_REQUIRED")
        self.assert_required_fields_mappable(request.required_fields)

    def assert_required_fields_mappable(self, required_fields: frozenset[str]) -> None:
        """Reject a requested field absent from this reviewed normalizer profile."""
        missing = sorted(set(required_fields) - self.field_profile.mapped_fields)
        if missing:
            raise ProviderContractError(
                "PROVIDER_CONTRACT_FIELD_MAPPING_MISSING",
                detail=",".join(missing),
            )

    def normalized_field_name(self, source_name: str) -> str:
        """Apply only this contract's reviewed field aliases.

        Existing adapters retain unknown extra source columns for provenance and
        backwards compatibility.  They cannot satisfy ``required_fields`` with
        one because ``assert_required_fields_mappable`` ran before extraction.
        """
        normalized_source = _text(source_name, field_name="source field")
        return self.response_field_aliases.get(normalized_source, normalized_source)

    def prepare_akshare_request(
        self, request: MarketDataProviderRequest
    ) -> PreparedProviderRequest:
        """Perform the reviewed Query Transform for a selected AkShare contract."""
        self.assert_request_matches(request)
        endpoint = self._resolve_akshare_endpoint(request)
        if request.provider_endpoint is not None and request.provider_endpoint != endpoint:
            raise ProviderContractError("PROVIDER_CONTRACT_DESCRIPTOR_MISMATCH")
        if self.request_transform_id == "akshare.historical-kline-request-v1":
            call_kwargs = _historical_kline_kwargs(request)
        elif self.request_transform_id == "akshare.fund-nav-request-v1":
            call_kwargs = _fund_nav_kwargs(request)
        elif self.request_transform_id == "akshare.symbol-only-request-v1":
            call_kwargs = {"symbol": request.provider_symbol}
        else:  # Defensive against an object changed after static construction.
            raise ProviderContractError("PROVIDER_CONTRACT_TRANSFORM_UNSUPPORTED")
        return PreparedProviderRequest(
            contract_id=self.contract_id,
            descriptor_sha256=self.descriptor_sha256,
            endpoint=endpoint,
            call_kwargs=call_kwargs,
        )

    def _resolve_akshare_endpoint(self, request: MarketDataProviderRequest) -> str:
        if self.endpoint_resolver_id == "akshare.static-endpoint-v1":
            endpoint = next(iter(self.endpoints))
        elif self.endpoint_resolver_id == "akshare.cffex-option-prefix-v1":
            endpoint = _cffex_option_endpoint(request.provider_symbol)
        else:  # Defensive against an object changed after static construction.
            raise ProviderContractError("PROVIDER_CONTRACT_ENDPOINT_UNSUPPORTED")
        if endpoint not in self.endpoints:
            raise ProviderContractError("PROVIDER_CONTRACT_DESCRIPTOR_MISMATCH")
        return endpoint


class ProviderContractRegistry:
    """Immutable provider/route registry with exact contract lookup only."""

    def __init__(self, contracts: Iterable[ProviderContract]) -> None:
        normalized = tuple(contracts)
        if not normalized:
            raise ValueError("provider contract registry requires at least one contract")
        if any(not isinstance(contract, ProviderContract) for contract in normalized):
            raise TypeError("provider contracts must be ProviderContract values")
        by_key: dict[tuple[str, str], ProviderContract] = {}
        for contract in normalized:
            # Recompute after construction too.  This catches any accidental
            # object-level mutation performed by an unsafe integration seam.
            if contract.descriptor_sha256 != _descriptor_sha256(
                contract._descriptor_without_digest()
            ):
                raise ProviderContractError("PROVIDER_CONTRACT_DESCRIPTOR_MISMATCH")
            key = (contract.provider, contract.route_id)
            if key in by_key:
                raise ValueError(f"duplicate provider contract route: {key!r}")
            by_key[key] = contract
        self._contracts = normalized
        self._by_key = MappingProxyType(by_key)

    @property
    def contracts(self) -> tuple[ProviderContract, ...]:
        """Return static contracts in review order."""
        return self._contracts

    def select_for_request(self, request: MarketDataProviderRequest) -> ProviderContract:
        """Return the one exact contract, never a same-shaped fallback."""
        if request.route_id is None:
            raise ProviderContractError("PROVIDER_CONTRACT_ROUTE_REQUIRED")
        contract = self._by_key.get((request.provider, request.route_id))
        if contract is None:
            if any(route_id == request.route_id for _, route_id in self._by_key):
                raise ProviderContractError("PROVIDER_CONTRACT_PROVIDER_MISMATCH")
            raise ProviderContractError("PROVIDER_CONTRACT_UNREGISTERED")
        contract.assert_request_matches(request)
        return contract

    def contract_for(self, *, provider: str, route_id: str) -> ProviderContract:
        """Resolve one static route for offline auditing without creating I/O."""
        normalized_provider = _text(provider, field_name="provider")
        normalized_route_id = _text(route_id, field_name="route_id")
        contract = self._by_key.get((normalized_provider, normalized_route_id))
        if contract is None:
            raise ProviderContractError("PROVIDER_CONTRACT_UNREGISTERED")
        return contract


def _format_akshare_date(value: datetime) -> str:
    """Format an already-normalized instant using AkShare's date-only contract."""
    return value.astimezone(_UTC).strftime("%Y%m%d")


def _format_akshare_inclusive_end_date(value: datetime) -> str:
    """Translate the API's half-open end instant to AkShare's inclusive date argument."""
    return _format_akshare_date(value - timedelta(microseconds=1))


def _akshare_adjustment(request: MarketDataProviderRequest) -> str:
    """Map only reviewed AkShare adjustment values; never infer a new basis."""
    if request.adjustment is None or request.adjustment == "unadjusted":
        return ""
    if request.adjustment in {"qfq", "hfq"}:
        return request.adjustment
    raise ProviderContractError("PROVIDER_CONTRACT_ADJUSTMENT_UNSUPPORTED")


def _historical_kline_kwargs(request: MarketDataProviderRequest) -> Mapping[str, Any]:
    period_by_frequency = {"1d": "daily", "1w": "weekly", "1mo": "monthly"}
    try:
        period = period_by_frequency[request.frequency]
    except KeyError as exc:
        raise ProviderContractError("PROVIDER_CONTRACT_FREQUENCY_UNSUPPORTED") from exc
    return {
        "symbol": request.provider_symbol,
        "period": period,
        "start_date": _format_akshare_date(request.start_at),
        "end_date": _format_akshare_inclusive_end_date(request.end_at),
        "adjust": _akshare_adjustment(request),
    }


def _fund_nav_kwargs(request: MarketDataProviderRequest) -> Mapping[str, Any]:
    return {
        "fund": request.provider_symbol,
        "start_date": _format_akshare_date(request.start_at),
        "end_date": _format_akshare_inclusive_end_date(request.end_at),
    }


def _cffex_option_endpoint(provider_symbol: str) -> str:
    endpoint_by_prefix = {
        "IO": "option_cffex_hs300_daily_sina",
        "HO": "option_cffex_sz50_daily_sina",
        "MO": "option_cffex_zz1000_daily_sina",
    }
    normalized_symbol = provider_symbol.upper()
    for prefix, endpoint in endpoint_by_prefix.items():
        if normalized_symbol.startswith(prefix) and len(normalized_symbol) > len(prefix):
            return endpoint
    raise ProviderContractError("PROVIDER_CONTRACT_ENDPOINT_UNSUPPORTED")


AKSHARE_RESPONSE_FIELD_ALIASES: Mapping[str, str] = MappingProxyType(
    {
        "开盘": "open",
        "今开": "open",
        "open": "open",
        "收盘": "close",
        "最新价": "close",
        "close": "close",
        "最高": "high",
        "high": "high",
        "最低": "low",
        "low": "low",
        "成交量": "volume",
        "volume": "volume",
        "成交额": "turnover",
        "turnover": "turnover",
        "振幅": "amplitude",
        "涨跌幅": "change_pct",
        "涨跌额": "change",
        "换手率": "turnover_rate",
        "持仓量": "open_interest",
        "hold": "open_interest",
        "结算价": "settle",
        "settle": "settle",
        "单位净值": "nav",
        "累计净值": "cumulative_nav",
        "日增长率": "daily_growth_rate",
    }
)


def _aliases_for(mapped_fields: frozenset[str]) -> Mapping[str, str]:
    return MappingProxyType(
        {
            source_name: normalized_name
            for source_name, normalized_name in AKSHARE_RESPONSE_FIELD_ALIASES.items()
            if normalized_name in mapped_fields
        }
    )


def _profile(
    profile_id: str,
    required_fields: tuple[str, ...],
    *,
    optional_fields: tuple[str, ...] = (),
    mapped_fields: frozenset[str],
) -> ProviderResponseFieldProfile:
    return ProviderResponseFieldProfile(
        profile_id=profile_id,
        required_fields=required_fields,
        optional_fields=optional_fields,
        mapped_fields=mapped_fields,
    )


_STOCK_MAPPED_FIELDS = frozenset(
    {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "turnover",
        "amplitude",
        "change_pct",
        "change",
        "turnover_rate",
        "settle",
    }
)
_FUTURES_MAPPED_FIELDS = frozenset(
    {"open", "high", "low", "close", "volume", "open_interest", "settle", "change"}
)
_BOND_MAPPED_FIELDS = frozenset(
    {"open", "high", "low", "close", "volume", "turnover", "change_pct"}
)
_FUND_NAV_MAPPED_FIELDS = frozenset({"nav", "cumulative_nav", "daily_growth_rate"})
_OPTION_MAPPED_FIELDS = frozenset(
    {"open", "high", "low", "close", "volume", "turnover", "open_interest", "change", "change_pct"}
)
_FX_MAPPED_FIELDS = frozenset({"open", "high", "low", "close", "change_pct"})


def _akshare_contract(
    *,
    contract_id: str,
    route_id: str,
    family_id: str,
    family_contract_version: str,
    asset_type: str,
    data_kind: str,
    frequencies: frozenset[str],
    markets: frozenset[str],
    supported_adjustments: frozenset[str],
    supported_price_bases: frozenset[str],
    supported_currencies: frozenset[str] | None,
    supported_units: frozenset[str] | None,
    field_profile: ProviderResponseFieldProfile,
    timestamp_columns: tuple[str, ...],
    endpoints: frozenset[str],
    request_transform_id: str,
    endpoint_resolver_id: str = "akshare.static-endpoint-v1",
    symbol_columns: tuple[str, ...] = (),
    identity_proof: Literal["source_request_bound", "response_symbol"] = "source_request_bound",
    source_policy_required: bool = False,
    request_validator_id: str | None = None,
    supported_product_types: frozenset[str] | None = None,
    supported_fund_identity_kinds: frozenset[str] | None = None,
) -> ProviderContract:
    return ProviderContract(
        contract_id=contract_id,
        contract_version=AKSHARE_PROVIDER_CONTRACT_VERSION,
        provider="akshare",
        route_id=route_id,
        family_id=family_id,
        family_contract_version=family_contract_version,
        asset_type=asset_type,
        data_kind=data_kind,
        frequencies=frequencies,
        markets=markets,
        supported_adjustments=supported_adjustments,
        supported_price_bases=supported_price_bases,
        supported_currencies=supported_currencies,
        supported_units=supported_units,
        field_profile=field_profile,
        response_field_aliases=_aliases_for(field_profile.mapped_fields),
        timestamp_columns=timestamp_columns,
        symbol_columns=symbol_columns,
        identity_proof=identity_proof,
        source_policy_required=source_policy_required,
        client_filters_window=True,
        request_transform_id=request_transform_id,
        endpoint_resolver_id=endpoint_resolver_id,
        endpoints=endpoints,
        request_validator_id=request_validator_id,
        supported_product_types=supported_product_types,
        supported_fund_identity_kinds=supported_fund_identity_kinds,
    )


AKSHARE_PROVIDER_CONTRACTS: tuple[ProviderContract, ...] = (
    _akshare_contract(
        contract_id="akshare.stock.primary.contract-v1",
        route_id="akshare-stock-primary-v1",
        family_id="stock.realtime",
        family_contract_version=FAMILY_CONTRACT_VERSION,
        asset_type="stock",
        data_kind="bars",
        frequencies=frozenset({"1d", "1w", "1mo"}),
        markets=frozenset({"CN-SSE", "CN-SZSE"}),
        supported_adjustments=frozenset({"unadjusted", "qfq", "hfq"}),
        supported_price_bases=frozenset({"close"}),
        supported_currencies=frozenset({"CNY"}),
        supported_units=frozenset({"share"}),
        field_profile=_profile(
            "stock-bars-compatibility-v1",
            ("close",),
            optional_fields=(
                "open",
                "high",
                "low",
                "volume",
                "turnover",
                "change_pct",
                "turnover_rate",
            ),
            mapped_fields=_STOCK_MAPPED_FIELDS,
        ),
        timestamp_columns=("日期", "date"),
        symbol_columns=("股票代码", "symbol", "code"),
        identity_proof="response_symbol",
        endpoints=frozenset({"stock_zh_a_hist"}),
        request_transform_id="akshare.historical-kline-request-v1",
        request_validator_id="akshare.cn-stock-symbol-v1",
    ),
    _akshare_contract(
        contract_id="akshare.stock.kline-legacy.contract-v1",
        route_id="akshare-stock-kline-legacy-v1",
        family_id=KLINE_LEGACY_FAMILY_ID,
        family_contract_version=KLINE_LEGACY_CONTRACT_VERSION,
        asset_type="stock",
        data_kind="bars",
        frequencies=frozenset({"1d", "1w", "1mo"}),
        markets=frozenset({"CN-SSE", "CN-SZSE"}),
        supported_adjustments=frozenset({"qfq"}),
        supported_price_bases=frozenset({"close"}),
        supported_currencies=frozenset({"CNY"}),
        supported_units=frozenset({"share"}),
        field_profile=_profile(
            "stock-kline-legacy-v1",
            ("open", "high", "low", "close", "volume", "change_pct"),
            mapped_fields=_STOCK_MAPPED_FIELDS,
        ),
        timestamp_columns=("日期", "date"),
        symbol_columns=("股票代码", "symbol", "code"),
        identity_proof="response_symbol",
        endpoints=frozenset({"stock_zh_a_hist"}),
        request_transform_id="akshare.historical-kline-request-v1",
        request_validator_id="akshare.cn-stock-symbol-v1",
    ),
    _akshare_contract(
        contract_id="akshare.stock.liquidity.contract-v1",
        route_id="akshare-stock-liquidity-primary-v1",
        family_id="stock.liquidity",
        family_contract_version=FAMILY_CONTRACT_VERSION,
        asset_type="stock",
        data_kind="reference_series",
        frequencies=frozenset({"1d"}),
        markets=frozenset({"CN-SSE", "CN-SZSE"}),
        supported_adjustments=frozenset({"unadjusted"}),
        supported_price_bases=frozenset({"close"}),
        supported_currencies=frozenset({"CNY"}),
        supported_units=frozenset({"share"}),
        field_profile=_profile(
            "stock-liquidity-v1",
            ("volume", "turnover", "turnover_rate"),
            mapped_fields=_STOCK_MAPPED_FIELDS,
        ),
        timestamp_columns=("日期", "date"),
        symbol_columns=("股票代码", "symbol", "code"),
        identity_proof="response_symbol",
        endpoints=frozenset({"stock_zh_a_hist"}),
        request_transform_id="akshare.historical-kline-request-v1",
        request_validator_id="akshare.cn-stock-symbol-v1",
    ),
    _akshare_contract(
        contract_id="akshare.futures.primary.contract-v1",
        route_id="akshare-futures-primary-v1",
        family_id="futures.realtime",
        family_contract_version=FAMILY_CONTRACT_VERSION,
        asset_type="futures",
        data_kind="bars",
        frequencies=frozenset({"1d"}),
        markets=frozenset({"CFFEX"}),
        supported_adjustments=frozenset({"unadjusted"}),
        supported_price_bases=frozenset({"close"}),
        supported_currencies=frozenset({"CNY"}),
        supported_units=frozenset({"contract"}),
        field_profile=_profile(
            "futures-bars-compatibility-v1",
            ("close",),
            optional_fields=("open", "high", "low", "volume", "open_interest", "settle", "change"),
            mapped_fields=_FUTURES_MAPPED_FIELDS,
        ),
        timestamp_columns=("date", "日期"),
        endpoints=frozenset({"futures_zh_daily_sina"}),
        request_transform_id="akshare.symbol-only-request-v1",
        source_policy_required=True,
        request_validator_id="akshare.cffex-futures-symbol-v1",
    ),
    _akshare_contract(
        contract_id="akshare.bond.primary.contract-v1",
        route_id="akshare-bond-primary-v1",
        family_id="bond.realtime",
        family_contract_version=FAMILY_CONTRACT_VERSION,
        asset_type="bond",
        data_kind="bars",
        frequencies=frozenset({"1d"}),
        markets=frozenset({"SSE", "SZSE", "CN-SSE", "CN-SZSE"}),
        supported_adjustments=frozenset({"unadjusted"}),
        supported_price_bases=frozenset({"close"}),
        supported_currencies=frozenset({"CNY"}),
        supported_units=None,
        field_profile=_profile(
            "bond-bars-compatibility-v1",
            ("close",),
            optional_fields=("open", "high", "low", "volume", "turnover", "change_pct"),
            mapped_fields=_BOND_MAPPED_FIELDS,
        ),
        timestamp_columns=("date", "日期"),
        endpoints=frozenset({"bond_zh_hs_daily"}),
        request_transform_id="akshare.symbol-only-request-v1",
        source_policy_required=True,
        request_validator_id="akshare.cn-bond-symbol-v1",
    ),
    _akshare_contract(
        contract_id="akshare.fund.primary.contract-v1",
        route_id="akshare-fund-primary-v1",
        family_id="fund.realtime",
        family_contract_version=FAMILY_CONTRACT_VERSION,
        asset_type="fund",
        data_kind="bars",
        frequencies=frozenset({"1d", "1w", "1mo"}),
        markets=frozenset({"CN-SSE", "CN-SZSE"}),
        supported_adjustments=frozenset({"unadjusted", "qfq", "hfq"}),
        supported_price_bases=frozenset({"close"}),
        supported_currencies=frozenset({"CNY"}),
        supported_units=frozenset({"share"}),
        field_profile=_profile(
            "fund-bars-compatibility-v1",
            ("close",),
            optional_fields=("open", "high", "low", "volume", "turnover", "change_pct"),
            mapped_fields=_STOCK_MAPPED_FIELDS,
        ),
        timestamp_columns=("日期", "date"),
        endpoints=frozenset({"fund_etf_hist_em"}),
        request_transform_id="akshare.historical-kline-request-v1",
        source_policy_required=True,
        request_validator_id="akshare.cn-etf-symbol-v1",
    ),
    _akshare_contract(
        contract_id="akshare.fund.liquidity.contract-v1",
        route_id="akshare-fund-liquidity-primary-v1",
        family_id="fund.liquidity",
        family_contract_version=FAMILY_CONTRACT_VERSION,
        asset_type="fund",
        data_kind="reference_series",
        frequencies=frozenset({"1d"}),
        markets=frozenset({"CN-SSE", "CN-SZSE"}),
        supported_adjustments=frozenset({"unadjusted"}),
        supported_price_bases=frozenset({"close"}),
        supported_currencies=frozenset({"CNY"}),
        supported_units=frozenset({"share"}),
        field_profile=_profile(
            "fund-liquidity-v1",
            ("volume", "turnover"),
            mapped_fields=_STOCK_MAPPED_FIELDS,
        ),
        timestamp_columns=("日期", "date"),
        endpoints=frozenset({"fund_etf_hist_em"}),
        request_transform_id="akshare.historical-kline-request-v1",
        source_policy_required=True,
        request_validator_id="akshare.cn-etf-symbol-v1",
    ),
    _akshare_contract(
        contract_id="akshare.fund.nav.contract-v1",
        route_id="akshare-fund-nav-primary-v1",
        family_id="fund.nav",
        family_contract_version=FAMILY_CONTRACT_VERSION,
        asset_type="fund",
        data_kind="reference_series",
        frequencies=frozenset({"1d"}),
        markets=frozenset({"CN-SSE", "CN-SZSE"}),
        supported_adjustments=frozenset({"source_reported"}),
        supported_price_bases=frozenset({"nav"}),
        supported_currencies=frozenset({"CNY"}),
        supported_units=frozenset({"fund_share"}),
        field_profile=_profile(
            "fund-nav-v1",
            ("nav", "cumulative_nav", "daily_growth_rate"),
            mapped_fields=_FUND_NAV_MAPPED_FIELDS,
        ),
        timestamp_columns=("净值日期", "date"),
        endpoints=frozenset({"fund_etf_fund_info_em"}),
        request_transform_id="akshare.fund-nav-request-v1",
        source_policy_required=True,
        request_validator_id="akshare.cn-etf-symbol-v1",
        supported_product_types=frozenset({"ETF"}),
        supported_fund_identity_kinds=frozenset({"LISTING"}),
    ),
    _akshare_contract(
        contract_id="akshare.option.cffex.primary.contract-v1",
        route_id="akshare-cffex-option-primary-v1",
        family_id="option.realtime",
        family_contract_version=FAMILY_CONTRACT_VERSION,
        asset_type="option",
        data_kind="bars",
        frequencies=frozenset({"1d"}),
        markets=frozenset({"CFFEX"}),
        supported_adjustments=frozenset({"unadjusted"}),
        supported_price_bases=frozenset({"close"}),
        supported_currencies=frozenset({"CNY"}),
        supported_units=frozenset({"contract"}),
        field_profile=_profile(
            "option-bars-compatibility-v1",
            ("close",),
            optional_fields=("volume", "turnover", "open_interest", "change", "change_pct"),
            mapped_fields=_OPTION_MAPPED_FIELDS,
        ),
        timestamp_columns=("date", "日期"),
        endpoints=frozenset(
            {
                "option_cffex_hs300_daily_sina",
                "option_cffex_sz50_daily_sina",
                "option_cffex_zz1000_daily_sina",
            }
        ),
        request_transform_id="akshare.symbol-only-request-v1",
        endpoint_resolver_id="akshare.cffex-option-prefix-v1",
        source_policy_required=True,
    ),
    _akshare_contract(
        contract_id="akshare.fx.primary.contract-v1",
        route_id="akshare-fx-primary-v1",
        family_id="fx.realtime",
        family_contract_version=FAMILY_CONTRACT_VERSION,
        asset_type="fx",
        data_kind="bars",
        frequencies=frozenset({"1d"}),
        markets=frozenset({"OTC", "CN-OTC"}),
        supported_adjustments=frozenset({"unadjusted"}),
        supported_price_bases=frozenset({"close"}),
        supported_currencies=None,
        supported_units=None,
        field_profile=_profile(
            "fx-bars-compatibility-v1",
            ("close",),
            optional_fields=("open", "high", "low", "change_pct"),
            mapped_fields=_FX_MAPPED_FIELDS,
        ),
        timestamp_columns=("日期", "date"),
        symbol_columns=("代码", "code", "symbol"),
        identity_proof="response_symbol",
        endpoints=frozenset({"forex_hist_em"}),
        request_transform_id="akshare.symbol-only-request-v1",
    ),
    _akshare_contract(
        contract_id="akshare.fx.range.contract-v1",
        route_id="akshare-fx-range-primary-v1",
        family_id="fx.range",
        family_contract_version=FAMILY_CONTRACT_VERSION,
        asset_type="fx",
        data_kind="bars",
        frequencies=frozenset({"1d"}),
        markets=frozenset({"OTC", "CN-OTC"}),
        supported_adjustments=frozenset({"unadjusted"}),
        supported_price_bases=frozenset({"close"}),
        supported_currencies=None,
        supported_units=None,
        field_profile=_profile(
            "fx-range-v1",
            ("open", "high", "low", "close"),
            mapped_fields=_FX_MAPPED_FIELDS,
        ),
        timestamp_columns=("日期", "date"),
        symbol_columns=("代码", "code", "symbol"),
        identity_proof="response_symbol",
        endpoints=frozenset({"forex_hist_em"}),
        request_transform_id="akshare.symbol-only-request-v1",
    ),
)

AKSHARE_PROVIDER_CONTRACT_REGISTRY = ProviderContractRegistry(AKSHARE_PROVIDER_CONTRACTS)


__all__ = [
    "AKSHARE_HALF_OPEN_WINDOW_SEMANTICS",
    "AKSHARE_PROVIDER_CONTRACT_REGISTRY",
    "AKSHARE_PROVIDER_CONTRACT_VERSION",
    "AKSHARE_PROVIDER_CONTRACTS",
    "AKSHARE_RESPONSE_FIELD_ALIASES",
    "AKSHARE_ROW_NORMALIZER_ID",
    "AKSHARE_UTC_DATE_NORMALIZER_ID",
    "PROVIDER_CONTRACT_DESCRIPTOR_VERSION",
    "PreparedProviderRequest",
    "ProviderContract",
    "ProviderContractError",
    "ProviderContractRegistry",
    "ProviderResponseFieldProfile",
]
