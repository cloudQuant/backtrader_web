"""Static, fail-closed data-product contracts for the Iteration 197 market page.

This module is deliberately a control plane.  It does not inspect a warehouse,
resolve an instrument, construct a provider, or call the network.  A ``ready``
entry must match one reviewed single-record family shape, but it is not itself
proof that a provider route, persistence path, or page consumer has passed
end-to-end acceptance.  Families stay explicit and unconfigured until those
separate prerequisites are complete.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.schemas.market_data_platform import (
    MarketDataFamilyContractResponse,
    MarketDataQueryBundleRequest,
    MarketDataQueryBundleResponse,
)

_ASSET_TYPES = frozenset({"stock", "futures", "bond", "fund", "option", "fx", "crypto"})
_BAR_FREQUENCIES = frozenset({"5min", "30min", "1h", "1d", "1w", "1mo"})
FAMILY_CONTRACT_VERSION = "market-data-family-v1"
_SEMANTIC_AXIS_NAMES = frozenset({"adjustment", "price_basis", "currency", "unit"})
_REQUIRED_FAMILY_IDS = frozenset(
    {
        "stock.realtime",
        "stock.valuation",
        "stock.liquidity",
        "futures.realtime",
        "futures.settlement",
        "futures.inventory",
        "bond.realtime",
        "bond.orderbook",
        "bond.fixed_income",
        "fund.realtime",
        "fund.liquidity",
        "fund.nav",
        "option.realtime",
        "option.derivative",
        "option.risk_surface",
        "fx.realtime",
        "fx.macro_fx",
        "fx.range",
        "crypto.realtime",
        "crypto.cme_position",
        "crypto.range",
    }
)


class DatasetContractRegistryError(ValueError):
    """Stable failure for a family key the server did not declare."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class DatasetSemanticBinding:
    """Exact semantic axes attached to one executable family contract.

    ``None`` is a real, reviewed value for an undeclared axis.  It is not a
    wildcard and does not permit a client to omit that axis: callers must pass
    all four names through ``explicit_axis_names`` so the registry can tell a
    deliberately undeclared axis from a generic/defaulted request.
    """

    adjustment: str | None
    price_basis: str | None
    currency: str | None
    unit: str | None

    def __post_init__(self) -> None:
        """Reject blank strings that would otherwise collapse into an unset axis."""
        for field_name in _SEMANTIC_AXIS_NAMES:
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field_name} must be a non-blank string or None")

    def matches(
        self,
        *,
        adjustment: str | None,
        price_basis: str | None,
        currency: str | None,
        unit: str | None,
        explicit_axis_names: frozenset[str],
    ) -> bool:
        """Return whether a request carries every exact, explicitly supplied axis."""
        return (
            _SEMANTIC_AXIS_NAMES <= explicit_axis_names
            and adjustment == self.adjustment
            and price_basis == self.price_basis
            and currency == self.currency
            and unit == self.unit
        )


@dataclass(frozen=True, slots=True)
class DatasetFieldProfile:
    """Fields and dimensions that make a dataset's observation shape explicit."""

    profile_id: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()
    dimension_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate once at registry construction rather than at page execution time."""
        MarketDataFamilyContractResponse.model_validate(
            {
                "family_id": "stock.realtime",
                "asset_type": "stock",
                "status": "unconfigured",
                "dataset_code": "market.validation_probe",
                "data_kind": "reference_series",
                "frequency_semantics": "calendar_grid",
                "frequencies": ["1d"],
                "field_profile_id": self.profile_id,
                "required_fields": self.required_fields,
                "optional_fields": self.optional_fields,
                "dimension_fields": self.dimension_fields,
                "coverage_model": "calendar_grid",
                "reason_code": "PROFILE_VALIDATION_ONLY",
            }
        )


@dataclass(frozen=True, slots=True)
class DatasetContract:
    """One immutable dataset declaration mapped to a stable UI family ID."""

    family_id: str
    asset_type: str
    status: str
    dataset_code: str
    data_kind: str
    frequency_semantics: str
    frequencies: tuple[str, ...]
    field_profile: DatasetFieldProfile
    coverage_model: str
    source_policy_id: str | None = None
    reason_code: str | None = None
    semantic_binding: DatasetSemanticBinding | None = None

    def to_response(
        self,
        *,
        status_override: str | None = None,
        reason_override: str | None = None,
    ) -> MarketDataFamilyContractResponse:
        """Render an independently validated public contract DTO.

        A cross-asset family filter is intentionally rendered as
        ``not_applicable`` with no executable source policy.  Returning the
        static dataset metadata lets the page explain the state, while omission
        of the policy makes it impossible to misroute the result to a provider.
        """
        status = status_override or self.status
        if status == "ready":
            _assert_ready_family_shape(self)
        return MarketDataFamilyContractResponse(
            family_id=self.family_id,
            family_contract_version=FAMILY_CONTRACT_VERSION,
            asset_type=self.asset_type,
            status=status,
            dataset_code=self.dataset_code,
            data_kind=self.data_kind,
            frequency_semantics=self.frequency_semantics,
            frequencies=self.frequencies,
            field_profile_id=self.field_profile.profile_id,
            required_fields=self.field_profile.required_fields,
            optional_fields=self.field_profile.optional_fields,
            dimension_fields=self.field_profile.dimension_fields,
            coverage_model=self.coverage_model,
            source_policy_id=self.source_policy_id if status == "ready" else None,
            reason_code=(
                reason_override
                if status != "ready" and reason_override is not None
                else self.reason_code
                if status != "ready"
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class _ReadyFamilyShape:
    """The immutable execution shape one family may use after separate acceptance."""

    dataset_code: str
    data_kind: str
    frequency_semantics: str
    frequencies: tuple[str, ...]
    required_fields: tuple[str, ...]
    coverage_model: str
    semantic_binding: DatasetSemanticBinding | None = None

    def matches(self, contract: DatasetContract) -> bool:
        """Return whether all material product axes remain exactly reviewed."""
        return (
            contract.dataset_code == self.dataset_code
            and contract.data_kind == self.data_kind
            and contract.frequency_semantics == self.frequency_semantics
            and contract.frequencies == self.frequencies
            and contract.field_profile.required_fields == self.required_fields
            and contract.coverage_model == self.coverage_model
            and contract.semantic_binding == self.semantic_binding
        )


# The schema DTO permits only safe *classes* of single-record products.  This
# registry-owned map is the second, narrower boundary: it names each exact
# reviewed page family and prevents a future product from becoming executable
# merely by looking like a reference series or quote snapshot. Presence here
# does not promote the family; the default declarations below mark ``ready``
# only after its complete product-specific provider, bridge, and page gates
# have been reviewed.
_READY_FAMILY_SHAPES: dict[str, _ReadyFamilyShape] = {
    "stock.realtime": _ReadyFamilyShape(
        "market.bars",
        "bars",
        "calendar_grid",
        ("1d", "1w", "1mo"),
        ("close",),
        "calendar_grid",
    ),
    "stock.valuation": _ReadyFamilyShape(
        "market.valuation",
        "reference_series",
        "calendar_grid",
        ("1d",),
        ("market_cap", "float_market_cap", "pe", "pb", "as_of"),
        "calendar_grid",
    ),
    "stock.liquidity": _ReadyFamilyShape(
        "market.liquidity",
        "reference_series",
        "calendar_grid",
        ("1d",),
        ("volume", "turnover", "turnover_rate"),
        "calendar_grid",
        DatasetSemanticBinding(
            adjustment="unadjusted",
            price_basis="close",
            currency="CNY",
            unit="share",
        ),
    ),
    "futures.realtime": _ReadyFamilyShape(
        "market.bars",
        "bars",
        "calendar_grid",
        ("1d",),
        ("close",),
        "calendar_grid",
    ),
    "futures.settlement": _ReadyFamilyShape(
        "market.settlement",
        "reference_series",
        "calendar_grid",
        ("1d",),
        ("settle", "previous_settle", "open_interest"),
        "calendar_grid",
    ),
    "bond.realtime": _ReadyFamilyShape(
        "market.bars",
        "bars",
        "calendar_grid",
        ("1d",),
        ("close",),
        "calendar_grid",
    ),
    "bond.orderbook": _ReadyFamilyShape(
        "market.quote_snapshot",
        "quote_snapshot",
        "snapshot",
        ("snapshot",),
        ("bid", "ask", "volume", "turnover", "update_time"),
        "snapshot_freshness",
    ),
    "bond.fixed_income": _ReadyFamilyShape(
        "market.bond_reference",
        "reference_series",
        "calendar_grid",
        ("1d",),
        ("yield_to_maturity", "coupon", "maturity_date", "previous_close"),
        "calendar_grid",
    ),
    "fund.realtime": _ReadyFamilyShape(
        "market.bars",
        "bars",
        "calendar_grid",
        ("1d", "1w", "1mo"),
        ("close",),
        "calendar_grid",
    ),
    "fund.liquidity": _ReadyFamilyShape(
        "market.liquidity",
        "reference_series",
        "calendar_grid",
        ("1d",),
        ("volume", "turnover"),
        "calendar_grid",
        DatasetSemanticBinding(
            adjustment="unadjusted",
            price_basis="close",
            currency="CNY",
            unit="share",
        ),
    ),
    "fund.nav": _ReadyFamilyShape(
        "market.fund_nav",
        "reference_series",
        "calendar_grid",
        ("1d",),
        ("nav", "cumulative_nav", "daily_growth_rate"),
        "calendar_grid",
        DatasetSemanticBinding(
            # The source supplies a published per-fund-share NAV series. No
            # client-side price adjustment is permitted; cumulative NAV is a
            # separately reported field rather than an inferred calculation.
            adjustment="source_reported",
            price_basis="nav",
            currency="CNY",
            unit="fund_share",
        ),
    ),
    "option.realtime": _ReadyFamilyShape(
        "market.bars",
        "bars",
        "calendar_grid",
        ("1d",),
        ("close",),
        "calendar_grid",
    ),
    "fx.realtime": _ReadyFamilyShape(
        "market.bars",
        "bars",
        "calendar_grid",
        ("1d",),
        ("close",),
        "calendar_grid",
    ),
    "fx.macro_fx": _ReadyFamilyShape(
        "market.fx_reference",
        "reference_series",
        "calendar_grid",
        ("1d",),
        ("rate", "previous_close", "base_currency", "quote_currency"),
        "calendar_grid",
    ),
    "fx.range": _ReadyFamilyShape(
        "market.bars",
        "bars",
        "calendar_grid",
        ("1d",),
        ("open", "high", "low", "close"),
        "calendar_grid",
        DatasetSemanticBinding(
            adjustment="unadjusted",
            price_basis="close",
            currency=None,
            unit=None,
        ),
    ),
    "crypto.realtime": _ReadyFamilyShape(
        "market.quote_snapshot",
        "quote_snapshot",
        "snapshot",
        ("snapshot",),
        ("price", "change", "change_pct", "high", "low", "volume"),
        "snapshot_freshness",
    ),
    "crypto.range": _ReadyFamilyShape(
        "market.bars",
        "bars",
        "calendar_grid",
        ("1d",),
        ("open", "high", "low", "close", "volume"),
        "calendar_grid",
    ),
}


def _assert_ready_family_shape(contract: DatasetContract) -> None:
    """Reject ready declarations outside the finite single-record family whitelist."""
    shape = _READY_FAMILY_SHAPES.get(contract.family_id)
    if shape is None or not shape.matches(contract):
        raise ValueError("ready family contract shape is not approved")


class DatasetContractRegistry:
    """Read-only registry with no provider or database fallback path."""

    def __init__(self, contracts: Iterable[DatasetContract]) -> None:
        normalized = tuple(contracts)
        if len(normalized) != len(_REQUIRED_FAMILY_IDS):
            raise ValueError("dataset registry must declare every current market-page family")
        if any(not isinstance(contract, DatasetContract) for contract in normalized):
            raise TypeError("dataset registry entries must be DatasetContract values")
        family_ids = [contract.family_id for contract in normalized]
        if len(family_ids) != len(set(family_ids)):
            raise ValueError("dataset registry family IDs must be unique")
        if frozenset(family_ids) != _REQUIRED_FAMILY_IDS:
            raise ValueError("dataset registry family IDs do not match the market-page contract")
        if any(contract.asset_type not in _ASSET_TYPES for contract in normalized):
            raise ValueError("dataset registry uses an unsupported asset type")
        for contract in normalized:
            family_asset_type, _, _ = contract.family_id.partition(".")
            if family_asset_type != contract.asset_type:
                raise ValueError("family ID asset type must equal its declared asset type")
            # This invokes every response-level invariant while the process is
            # starting, so an invalid new product cannot be served partially.
            contract.to_response()

        by_asset_type: dict[str, tuple[DatasetContract, ...]] = {}
        for asset_type in sorted(_ASSET_TYPES):
            asset_contracts = tuple(
                contract for contract in normalized if contract.asset_type == asset_type
            )
            if len(asset_contracts) != 3:
                raise ValueError(
                    "every market-page asset type requires exactly three family contracts"
                )
            by_asset_type[asset_type] = asset_contracts
        self._by_id = {contract.family_id: contract for contract in normalized}
        self._by_asset_type = by_asset_type

    def bundle_for(self, request: MarketDataQueryBundleRequest) -> MarketDataQueryBundleResponse:
        """Return all applicable families, or one explicit filtered-family state."""
        if request.family_id is None:
            families = tuple(
                contract.to_response() for contract in self._by_asset_type[request.asset_type]
            )
        else:
            contract = self._by_id.get(request.family_id)
            if contract is None:
                raise DatasetContractRegistryError("DATA_FAMILY_UNSUPPORTED")
            if contract.asset_type == request.asset_type:
                families = (contract.to_response(),)
            else:
                families = (
                    contract.to_response(
                        status_override="not_applicable",
                        reason_override="DATA_FAMILY_NOT_APPLICABLE",
                    ),
                )
        return MarketDataQueryBundleResponse(
            requested_asset_type=request.asset_type,
            families=families,
        )

    def ready_contract_for(self, *, family_id: str, asset_type: str) -> DatasetContract:
        """Return the one executable family contract for an exact asset selection.

        This deliberately does not select a nearby ``ready`` contract.  The
        page's family ID is part of the server-issued query request, so adding
        a second executable product cannot silently retarget an older client.
        """
        contract = self._by_id.get(family_id)
        if contract is None:
            raise DatasetContractRegistryError("DATA_FAMILY_UNSUPPORTED")
        if contract.asset_type != asset_type:
            raise DatasetContractRegistryError("DATA_FAMILY_NOT_APPLICABLE")
        if contract.status != "ready" or contract.source_policy_id is None:
            raise DatasetContractRegistryError("DATA_FAMILY_UNCONFIGURED")
        return contract

    def assert_executable_family_preflight(
        self,
        *,
        family_id: str,
        family_contract_version: str,
    ) -> None:
        """Reject non-executable public families before catalog or identity I/O.

        An unconfigured product is not a request for storage discovery.  This
        first gate deliberately validates only the server-issued family key,
        version, and executable lifecycle; the exact asset type is verified
        after canonical identity resolution in ``assert_query_binding``.
        """
        if family_contract_version != FAMILY_CONTRACT_VERSION:
            raise DatasetContractRegistryError("DATA_FAMILY_CONTRACT_VERSION_UNSUPPORTED")
        contract = self._by_id.get(family_id)
        if contract is None:
            raise DatasetContractRegistryError("DATA_FAMILY_UNSUPPORTED")
        if contract.status != "ready" or contract.source_policy_id is None:
            raise DatasetContractRegistryError("DATA_FAMILY_UNCONFIGURED")

    def assert_query_binding(
        self,
        *,
        family_id: str,
        family_contract_version: str,
        asset_type: str,
        dataset_code: str | None,
        data_kind: str,
        frequency: str | None,
        required_fields: tuple[str, ...],
        source_policy_id: str | None,
        adjustment: str | None = None,
        price_basis: str | None = None,
        currency: str | None = None,
        unit: str | None = None,
        explicit_semantic_axis_names: frozenset[str] = frozenset(),
    ) -> None:
        """Reject a v2 request whose executable axes drift from its family card.

        A family bundle is a declaration, not a broad provider capability.  A
        client that sends its selected family must therefore preserve the exact
        dataset, shape, cadence, required fields, and source-policy version
        issued for that product.  This check runs after canonical identity
        resolution so the declared asset type is independently established.
        """
        if family_contract_version != FAMILY_CONTRACT_VERSION:
            raise DatasetContractRegistryError("DATA_FAMILY_CONTRACT_VERSION_UNSUPPORTED")
        contract = self.ready_contract_for(family_id=family_id, asset_type=asset_type)
        if (
            dataset_code != contract.dataset_code
            or data_kind != contract.data_kind
            or frequency not in contract.frequencies
            or tuple(required_fields) != tuple(sorted(contract.field_profile.required_fields))
            or source_policy_id != contract.source_policy_id
            or (
                contract.semantic_binding is not None
                and not contract.semantic_binding.matches(
                    adjustment=adjustment,
                    price_basis=price_basis,
                    currency=currency,
                    unit=unit,
                    explicit_axis_names=explicit_semantic_axis_names,
                )
            )
        ):
            raise DatasetContractRegistryError("DATA_FAMILY_QUERY_CONTRACT_MISMATCH")


def _profile(
    profile_id: str,
    required_fields: tuple[str, ...],
    *,
    optional_fields: tuple[str, ...] = (),
    dimension_fields: tuple[str, ...] = (),
) -> DatasetFieldProfile:
    """Keep the 21 declarations readable while retaining constructor validation."""
    return DatasetFieldProfile(
        profile_id=profile_id,
        required_fields=required_fields,
        optional_fields=optional_fields,
        dimension_fields=dimension_fields,
    )


# ``ready`` is intentionally limited to the exact reviewed product families.
# Realtime bars retain ``close`` as their cross-asset minimum. Liquidity and
# range products advance only when their own dataset, provider route, semantic
# defaults, and legacy-page bridge are all bound to the same family ID.
_CONTRACTS: tuple[DatasetContract, ...] = (
    DatasetContract(
        "stock.realtime",
        "stock",
        "ready",
        "market.bars",
        "bars",
        "calendar_grid",
        ("1d", "1w", "1mo"),
        _profile(
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
        ),
        "calendar_grid",
        source_policy_id="market-default-v1",
    ),
    DatasetContract(
        "stock.valuation",
        "stock",
        "unconfigured",
        "market.valuation",
        "reference_series",
        "calendar_grid",
        ("1d",),
        _profile(
            "stock-valuation-v1",
            ("market_cap", "float_market_cap", "pe", "pb", "as_of"),
        ),
        "calendar_grid",
        reason_code="DATASET_CONTRACT_UNCONFIGURED",
    ),
    DatasetContract(
        "stock.liquidity",
        "stock",
        "ready",
        "market.liquidity",
        "reference_series",
        "calendar_grid",
        ("1d",),
        _profile("stock-liquidity-v1", ("volume", "turnover", "turnover_rate")),
        "calendar_grid",
        source_policy_id="market-default-v1",
        semantic_binding=DatasetSemanticBinding(
            adjustment="unadjusted",
            price_basis="close",
            currency="CNY",
            unit="share",
        ),
    ),
    DatasetContract(
        "futures.realtime",
        "futures",
        "ready",
        "market.bars",
        "bars",
        "calendar_grid",
        ("1d",),
        _profile(
            "futures-bars-compatibility-v1",
            ("close",),
            optional_fields=("open", "high", "low", "volume", "open_interest", "settle", "change"),
        ),
        "calendar_grid",
        source_policy_id="market-default-v1",
    ),
    DatasetContract(
        "futures.settlement",
        "futures",
        "unconfigured",
        "market.settlement",
        "reference_series",
        "calendar_grid",
        ("1d",),
        _profile("futures-settlement-v1", ("settle", "previous_settle", "open_interest")),
        "calendar_grid",
        reason_code="DATASET_CONTRACT_UNCONFIGURED",
    ),
    DatasetContract(
        "futures.inventory",
        "futures",
        "unconfigured",
        "market.inventory",
        "inventory_report",
        "reporting_period",
        ("1d", "1w"),
        _profile(
            "futures-inventory-v1",
            ("receipt_quantity", "inventory_quantity", "delivery_quantity"),
            dimension_fields=("report_date", "location", "warehouse", "commodity"),
        ),
        "report_completeness",
        reason_code="DATASET_CONTRACT_UNCONFIGURED",
    ),
    DatasetContract(
        "bond.realtime",
        "bond",
        "ready",
        "market.bars",
        "bars",
        "calendar_grid",
        ("1d",),
        _profile(
            "bond-bars-compatibility-v1",
            ("close",),
            optional_fields=("open", "high", "low", "volume", "turnover", "change_pct"),
        ),
        "calendar_grid",
        source_policy_id="market-default-v1",
    ),
    DatasetContract(
        "bond.orderbook",
        "bond",
        "unconfigured",
        "market.quote_snapshot",
        "quote_snapshot",
        "snapshot",
        ("snapshot",),
        _profile("bond-orderbook-v1", ("bid", "ask", "volume", "turnover", "update_time")),
        "snapshot_freshness",
        reason_code="DATASET_CONTRACT_UNCONFIGURED",
    ),
    DatasetContract(
        "bond.fixed_income",
        "bond",
        "unconfigured",
        "market.bond_reference",
        "reference_series",
        "calendar_grid",
        ("1d",),
        _profile(
            "bond-fixed-income-v1",
            ("yield_to_maturity", "coupon", "maturity_date", "previous_close"),
        ),
        "calendar_grid",
        reason_code="DATASET_CONTRACT_UNCONFIGURED",
    ),
    DatasetContract(
        "fund.realtime",
        "fund",
        "ready",
        "market.bars",
        "bars",
        "calendar_grid",
        ("1d", "1w", "1mo"),
        _profile(
            "fund-bars-compatibility-v1",
            ("close",),
            optional_fields=("open", "high", "low", "volume", "turnover", "change_pct"),
        ),
        "calendar_grid",
        source_policy_id="market-default-v1",
    ),
    DatasetContract(
        "fund.liquidity",
        "fund",
        "ready",
        "market.liquidity",
        "reference_series",
        "calendar_grid",
        ("1d",),
        _profile("fund-liquidity-v1", ("volume", "turnover")),
        "calendar_grid",
        source_policy_id="market-default-v1",
        semantic_binding=DatasetSemanticBinding(
            adjustment="unadjusted",
            price_basis="close",
            currency="CNY",
            unit="share",
        ),
    ),
    DatasetContract(
        "fund.nav",
        "fund",
        "ready",
        "market.fund_nav",
        "reference_series",
        "calendar_grid",
        ("1d",),
        _profile("fund-nav-v1", ("nav", "cumulative_nav", "daily_growth_rate")),
        "calendar_grid",
        source_policy_id="market-default-v1",
        semantic_binding=DatasetSemanticBinding(
            adjustment="source_reported",
            price_basis="nav",
            currency="CNY",
            unit="fund_share",
        ),
    ),
    DatasetContract(
        "option.realtime",
        "option",
        "ready",
        "market.bars",
        "bars",
        "calendar_grid",
        ("1d",),
        _profile(
            "option-bars-compatibility-v1",
            ("close",),
            optional_fields=("volume", "turnover", "open_interest", "change", "change_pct"),
        ),
        "calendar_grid",
        source_policy_id="market-default-v1",
    ),
    DatasetContract(
        "option.derivative",
        "option",
        "unconfigured",
        "market.option_chain",
        "option_chain",
        "snapshot",
        ("snapshot",),
        _profile(
            "option-chain-v1",
            ("bid", "ask", "last", "volume", "open_interest", "implied_volatility"),
            dimension_fields=(
                "underlying_canonical_id",
                "contract_canonical_id",
                "expiry",
                "strike",
                "right",
            ),
        ),
        "slice_completeness",
        reason_code="DATASET_CONTRACT_UNCONFIGURED",
    ),
    DatasetContract(
        "option.risk_surface",
        "option",
        "unconfigured",
        "market.option_risk_surface",
        "option_risk_surface",
        "snapshot",
        ("snapshot",),
        _profile(
            "option-risk-surface-v1",
            ("implied_volatility", "delta", "gamma", "theta", "vega", "model_version"),
            dimension_fields=("underlying_canonical_id", "expiry", "moneyness"),
        ),
        "slice_completeness",
        reason_code="DATASET_CONTRACT_UNCONFIGURED",
    ),
    DatasetContract(
        "fx.realtime",
        "fx",
        "ready",
        "market.bars",
        "bars",
        "calendar_grid",
        ("1d",),
        _profile(
            "fx-bars-compatibility-v1",
            ("close",),
            optional_fields=("open", "high", "low", "change_pct"),
        ),
        "calendar_grid",
        source_policy_id="market-default-v1",
    ),
    DatasetContract(
        "fx.macro_fx",
        "fx",
        "unconfigured",
        "market.fx_reference",
        "reference_series",
        "calendar_grid",
        ("1d",),
        _profile("fx-reference-v1", ("rate", "previous_close", "base_currency", "quote_currency")),
        "calendar_grid",
        reason_code="DATASET_CONTRACT_UNCONFIGURED",
    ),
    DatasetContract(
        "fx.range",
        "fx",
        "ready",
        "market.bars",
        "bars",
        "calendar_grid",
        ("1d",),
        _profile("fx-range-v1", ("open", "high", "low", "close")),
        "calendar_grid",
        source_policy_id="market-default-v1",
        semantic_binding=DatasetSemanticBinding(
            adjustment="unadjusted",
            price_basis="close",
            currency=None,
            unit=None,
        ),
    ),
    DatasetContract(
        "crypto.realtime",
        "crypto",
        "unconfigured",
        "market.quote_snapshot",
        "quote_snapshot",
        "snapshot",
        ("snapshot",),
        _profile("crypto-quote-v1", ("price", "change", "change_pct", "high", "low", "volume")),
        "snapshot_freshness",
        reason_code="SOURCE_ROUTE_UNCONFIGURED",
    ),
    DatasetContract(
        "crypto.cme_position",
        "crypto",
        "unconfigured",
        "market.position_report",
        "position_report",
        "reporting_period",
        ("1d", "1w"),
        _profile(
            "crypto-cme-position-v1",
            ("long_position", "short_position", "net_position", "open_interest"),
            dimension_fields=("report_date", "reporting_entity", "rank"),
        ),
        "report_completeness",
        reason_code="DATASET_CONTRACT_UNCONFIGURED",
    ),
    DatasetContract(
        "crypto.range",
        "crypto",
        "unconfigured",
        "market.bars",
        "bars",
        "calendar_grid",
        ("1d",),
        _profile("crypto-range-v1", ("open", "high", "low", "close", "volume")),
        "calendar_grid",
        reason_code="SOURCE_ROUTE_UNCONFIGURED",
    ),
)

DEFAULT_DATASET_CONTRACT_REGISTRY = DatasetContractRegistry(_CONTRACTS)

__all__ = [
    "DEFAULT_DATASET_CONTRACT_REGISTRY",
    "FAMILY_CONTRACT_VERSION",
    "DatasetContract",
    "DatasetContractRegistry",
    "DatasetContractRegistryError",
    "DatasetFieldProfile",
]
