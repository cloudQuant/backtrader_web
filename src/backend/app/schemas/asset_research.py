"""Strict public contracts for the Iteration 191 multi-asset research API.

The contracts intentionally keep research opinions separate from execution: a
``ResearchDecision`` may explain a view, but it always carries
``execution_disabled=true`` and never represents an order.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AssetType = Literal["stock", "bond", "fund", "futures", "option", "fx", "crypto"]
PublicAssetType = Literal["bond", "fund", "futures", "option", "fx", "crypto"]
IdentityLevel = Literal["ASSET", "PRODUCT", "CONTRACT", "SERIES"]
PositionContext = Literal["FLAT", "LONG", "SHORT", "UNKNOWN"]
MarketView = Literal["BULLISH", "BEARISH", "NEUTRAL", "INDETERMINATE"]
NormalizedDirection = Literal["LONG", "SHORT", "NEUTRAL", "INDETERMINATE"]
Recommendation = Literal["BUY", "SELL", "HOLD", "AVOID"]
Actionability = Literal["ACTIONABLE", "RESEARCH_ONLY", "INSUFFICIENT_DATA", "REGION_RESTRICTED"]
TradeIntent = Literal["OPEN", "ADD", "REDUCE", "CLOSE", "KEEP", "NONE"]
QualityStatus = Literal["ELIGIBLE", "DEGRADED", "REJECTED"]
TaskStatus = Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]
RunStatus = Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]
OutcomeStatus = Literal["PENDING", "PARTIAL", "SCORED", "UNSCORABLE"]
MaturityReason = Literal[
    "HORIZON_REACHED",
    "EXPIRY",
    "MATURITY",
    "CALL",
    "REDEMPTION",
    "ROLL",
    "DELISTING",
    "LIQUIDATION",
    "EXERCISE",
]
OwnerScope = Literal["USER", "PUBLIC_SHADOW", "ADMIN_EVAL"]
VisibleOwnerScope = Literal["USER", "PUBLIC_SHADOW"]
ScheduleManifestOwnerScope = Literal["PUBLIC_SHADOW", "ADMIN_EVAL"]
ScheduleManifestStatus = Literal["ACTIVE", "RETIRED"]
PromotionScopeType = Literal["POOLED", "INSTRUMENT_SPECIFIC", "VENUE_PRODUCT"]
ModelStatus = Literal["DRAFT", "SHADOW", "PROMOTED", "SUSPENDED", "RETIRED"]


class StrictModel(BaseModel):
    """Reject unversioned or misspelled API fields at every domain boundary."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class StockIdentityDetails(StrictModel):
    kind: Literal["STOCK"] = "STOCK"
    exchange_symbol: str


class BondIdentityDetails(StrictModel):
    kind: Literal["BOND"] = "BOND"
    bond_identity_kind: Literal["ISSUE", "LISTING"]
    isin: str | None = None
    issuer_id: str
    maturity_date: date | None = None
    is_perpetual: bool | None = None
    settlement_calendar_id: str | None = None


class FundIdentityDetails(StrictModel):
    kind: Literal["FUND"] = "FUND"
    fund_identity_kind: Literal["SHARE_CLASS", "LISTING"]
    fund_id: str
    share_class_id: str
    nav_calendar_id: str | None = None
    official_benchmark_id: str | None = None
    dealing_frequency: str | None = None
    dealing_channel: str | None = None
    subscription_cutoff: time | None = None
    redemption_cutoff: time | None = None


class FuturesIdentityDetails(StrictModel):
    kind: Literal["FUTURES"] = "FUTURES"
    product_code: str
    contract_month: str | None = None
    underlying_id: str | None = None
    expiry_at: datetime | None = None
    contract_multiplier: Decimal | None = None
    trading_calendar_id: str
    mapped_contract_id: str | None = None


class OptionIdentityDetails(StrictModel):
    """Immutable terms needed to distinguish and safely value one option contract."""

    kind: Literal["OPTION"] = "OPTION"
    option_contract_id: str = Field(min_length=1, max_length=255)
    exchange: str = Field(min_length=1, max_length=128)
    underlying_instrument_id: str = Field(min_length=1, max_length=512)
    underlying_contract_id: str = Field(min_length=1, max_length=512)
    expiry_at: datetime
    last_trade_at: datetime
    strike: Decimal
    option_right: Literal["CALL", "PUT"]
    exercise_style: Literal["EUROPEAN", "AMERICAN", "OTHER"]
    contract_multiplier: Decimal = Field(gt=0)
    settlement_type: str = Field(min_length=1, max_length=128)
    deliverable: str = Field(min_length=1, max_length=512)
    quote_unit: str = Field(min_length=1, max_length=128)
    tick_size: Decimal = Field(gt=0)
    trading_calendar_id: str = Field(min_length=1, max_length=128)
    automatic_exercise_rule: str = Field(min_length=1, max_length=255)
    position_limit_rule: str = Field(min_length=1, max_length=255)
    margin_rule_version: str = Field(min_length=1, max_length=128)

    @field_validator("expiry_at", "last_trade_at")
    @classmethod
    def normalize_contract_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("option contract timestamp must include a timezone")
        return value.astimezone(timezone.utc)

    @property
    def underlying_id(self) -> str:
        """Compatibility accessor for readers that only need the product reference."""
        return self.underlying_instrument_id


class FxIdentityDetails(StrictModel):
    kind: Literal["FX"] = "FX"
    base_currency: str
    quote_currency: str
    settlement_type: Literal["SPOT", "FORWARD", "NDF"]
    value_date: date | None = None
    expiry_at: datetime | None = None
    contract_multiplier: Decimal | None = None
    settlement_currency: str | None = None
    calendar_id: str
    price_convention: str

    @field_validator("expiry_at")
    @classmethod
    def normalize_contract_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("fx contract timestamp must include a timezone")
        return value.astimezone(timezone.utc)


class CryptoAssetIdentityDetails(StrictModel):
    kind: Literal["CRYPTO_ASSET"] = "CRYPTO_ASSET"
    caip_asset_id: str
    chain_id: str
    contract_address_or_native_asset: str


class CryptoProductIdentityDetails(StrictModel):
    kind: Literal["CRYPTO_PRODUCT"] = "CRYPTO_PRODUCT"
    base_asset_id: str
    quote_asset_id: str
    settlement_asset_id: str | None = None
    market_type: Literal["SPOT", "PERPETUAL", "DELIVERY_FUTURE"]
    linear_or_inverse: Literal["LINEAR", "INVERSE", "NOT_APPLICABLE"]
    expiry_at: datetime | None = None


IdentityDetails = Annotated[
    StockIdentityDetails
    | BondIdentityDetails
    | FundIdentityDetails
    | FuturesIdentityDetails
    | OptionIdentityDetails
    | FxIdentityDetails
    | CryptoAssetIdentityDetails
    | CryptoProductIdentityDetails,
    Field(discriminator="kind"),
]


class InstrumentIdentity(StrictModel):
    """Versioned identity that a plugin must resolve before a task may start."""

    asset_type: AssetType
    identity_level: IdentityLevel
    canonical_id: str = Field(min_length=3, max_length=512)
    display_symbol: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    venue: str | None = Field(default=None, max_length=128)
    currency: str | None = Field(default=None, max_length=32)
    timezone: str = Field(default="UTC", max_length=64)
    identifier_type: str = Field(min_length=1, max_length=64)
    identifier_value: str = Field(min_length=1, max_length=255)
    product_type: str | None = Field(default=None, max_length=64)
    metadata_version: str = Field(default="v1", min_length=1, max_length=64)
    details: IdentityDetails

    @field_validator("canonical_id", "display_symbol", "identifier_value")
    @classmethod
    def normalize_identifier_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("identity value must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_asset_specific_identity(self) -> InstrumentIdentity:
        """Keep the public type, identity level and frozen details coherent.

        Master-data rows are the authorization boundary for analysable assets.
        A generic union parser alone would accept a ``bond`` row containing
        fund fields, or a futures ``CONTRACT`` that has no expiry/multiplier.
        Reject those rows before they reach catalog search, schedules or a raw
        snapshot.  This validation deliberately checks identity facts only;
        data availability remains the later quality-gate responsibility.
        """
        details = self.details
        if self.asset_type == "stock":
            if not isinstance(details, StockIdentityDetails):
                raise ValueError("details do not match asset type")
            return self

        if self.asset_type == "bond":
            if not isinstance(details, BondIdentityDetails):
                raise ValueError("details do not match asset type")
            required_level = "ASSET" if details.bond_identity_kind == "ISSUE" else "PRODUCT"
            if self.identity_level != required_level:
                raise ValueError(f"bond {details.bond_identity_kind} requires {required_level}")
            if details.bond_identity_kind == "LISTING" and not self.venue:
                raise ValueError("bond LISTING requires venue")
            return self

        if self.asset_type == "fund":
            if not isinstance(details, FundIdentityDetails):
                raise ValueError("details do not match asset type")
            if self.identity_level != "PRODUCT":
                raise ValueError("fund research requires PRODUCT identity level")
            if details.fund_identity_kind == "LISTING" and not self.venue:
                raise ValueError("fund LISTING requires venue")
            if details.fund_identity_kind == "SHARE_CLASS":
                if self.venue is not None:
                    raise ValueError("fund SHARE_CLASS must not bind venue")
                if (
                    not details.dealing_channel
                    or not details.dealing_frequency
                    or details.subscription_cutoff is None
                    or details.redemption_cutoff is None
                    or not details.nav_calendar_id
                ):
                    raise ValueError(
                        "fund SHARE_CLASS requires dealing channel, cutoffs and nav calendar"
                    )
            return self

        if self.asset_type == "futures":
            if not isinstance(details, FuturesIdentityDetails):
                raise ValueError("details do not match asset type")
            if self.identity_level == "CONTRACT":
                expiry_at = details.expiry_at
                if (
                    not details.contract_month
                    or expiry_at is None
                    or expiry_at.tzinfo is None
                    or details.contract_multiplier is None
                    or details.contract_multiplier <= 0
                ):
                    raise ValueError("futures CONTRACT requires expiry_at and contract_multiplier")
                if not self.venue:
                    raise ValueError("futures CONTRACT requires venue")
            elif self.identity_level not in {"PRODUCT", "SERIES"}:
                raise ValueError("futures requires PRODUCT, CONTRACT or SERIES identity level")
            return self

        if self.asset_type == "option":
            if self.identity_level != "CONTRACT" or not isinstance(details, OptionIdentityDetails):
                raise ValueError("option research requires an exact option CONTRACT identity")
            if self.identifier_value.upper() != details.option_contract_id.upper():
                raise ValueError("option contract id must match the instrument identifier")
            if self.venue and self.venue.upper() != details.exchange.upper():
                raise ValueError("option exchange must match the instrument venue")
            return self

        if self.asset_type == "fx":
            if not isinstance(details, FxIdentityDetails):
                raise ValueError("details do not match asset type")
            if self.currency and self.currency.upper() != details.quote_currency.upper():
                raise ValueError("fx currency must match quote_currency")
            if self.identity_level == "ASSET":
                if self.venue is not None:
                    raise ValueError("fx ASSET must not bind venue")
                if details.settlement_type != "SPOT":
                    raise ValueError("fx ASSET requires SPOT reference identity")
                return self
            if self.identity_level == "PRODUCT":
                if not self.venue:
                    raise ValueError("fx PRODUCT requires venue")
                if details.settlement_type != "SPOT":
                    raise ValueError("fx PRODUCT requires SPOT settlement type")
                if not details.settlement_currency:
                    raise ValueError("fx PRODUCT requires settlement_currency")
                return self
            if self.identity_level != "CONTRACT":
                raise ValueError("fx requires ASSET, PRODUCT or CONTRACT identity level")
            if not self.venue:
                raise ValueError("fx CONTRACT requires venue")
            if details.settlement_type not in {"FORWARD", "NDF"}:
                raise ValueError("fx CONTRACT requires FORWARD or NDF settlement type")
            if not details.settlement_currency:
                raise ValueError("fx CONTRACT requires settlement_currency")
            if details.value_date is None and details.expiry_at is None:
                raise ValueError("fx CONTRACT requires value_date or expiry_at")
            if details.contract_multiplier is None or details.contract_multiplier <= 0:
                raise ValueError("fx CONTRACT requires contract_multiplier")
            return self

        if isinstance(details, CryptoAssetIdentityDetails):
            if self.identity_level != "ASSET":
                raise ValueError("crypto asset requires ASSET identity level")
            if self.venue is not None:
                raise ValueError("crypto asset must not bind a venue")
            return self
        if not isinstance(details, CryptoProductIdentityDetails):
            raise ValueError("details do not match asset type")
        if not self.venue:
            raise ValueError("crypto product requires venue")
        if details.market_type == "DELIVERY_FUTURE":
            if self.identity_level != "CONTRACT":
                raise ValueError("crypto DELIVERY_FUTURE requires CONTRACT identity level")
            if details.expiry_at is None or details.expiry_at.tzinfo is None:
                raise ValueError("crypto DELIVERY_FUTURE requires expiry_at")
            return self
        if self.identity_level != "PRODUCT":
            raise ValueError("crypto SPOT/PERPETUAL requires PRODUCT identity level")
        if details.expiry_at is not None:
            raise ValueError("crypto SPOT/PERPETUAL must not define expiry_at")
        return self

    def matches_frozen_identity(self, other: InstrumentIdentity) -> bool:
        """Return whether another snapshot carries precisely this frozen identity version."""
        return self.model_dump(mode="json") == other.model_dump(mode="json")


class HorizonSpec(StrictModel):
    count: int = Field(default=20, ge=1, le=3660)
    unit: Literal[
        "TRADING_SESSION",
        "TRADING_DAY",
        "BOND_SESSION",
        "FUND_VALUATION_DAY",
        "FX_SESSION",
        "CALENDAR_HOUR",
        "CALENDAR_DAY",
    ] = "TRADING_DAY"
    calendar_id: str = Field(default="UTC", min_length=1, max_length=128)
    entry_rule: str = Field(default="next_eligible_close", min_length=1, max_length=255)
    maturity_rule: str = Field(default="horizon_complete", min_length=1, max_length=255)


class PredictionHead(StrictModel):
    head_code: str = Field(min_length=1, max_length=128)
    head_spec_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_definition: str = Field(min_length=1)
    target_spec_version: str = Field(min_length=1, max_length=64)
    scoreability_rule: str = Field(min_length=1)
    scoreability_rule_version: str = Field(min_length=1, max_length=64)
    labels: list[str] = Field(min_length=2)
    probabilities: dict[str, float]
    probability_model_version: str = Field(min_length=1, max_length=64)
    probability_artifact_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    calibration_version: str = Field(min_length=1, max_length=64)
    calibration_artifact_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    training_cutoff_at: datetime
    baseline_code: str = Field(min_length=1, max_length=128)
    baseline_version: str = Field(min_length=1, max_length=64)
    success_threshold: Decimal | None = None
    primary_for_promotion: bool = False

    @model_validator(mode="after")
    def verify_probability_distribution(self) -> PredictionHead:
        if set(self.labels) != set(self.probabilities):
            raise ValueError("prediction head labels and probabilities must match")
        total = sum(self.probabilities.values())
        if any(value < 0 or value > 1 for value in self.probabilities.values()):
            raise ValueError("prediction head probabilities must be in [0, 1]")
        if abs(total - 1.0) > 1e-6:
            raise ValueError("prediction head probabilities must sum to one")
        return self


class PromotionScope(StrictModel):
    """Canonical, frozen applicability boundary for one promoted signal head.

    The registry keeps these components in queryable columns plus a JSON field,
    but the hash is authoritative only when it can be reproduced from this
    normalized contract.  A malformed or inconsistent projection therefore
    fails closed instead of widening the audience for a directional signal.
    """

    scope_type: PromotionScopeType
    asset_type: AssetType
    instrument_class: str = Field(min_length=1, max_length=128)
    canonical_id: str | None = Field(default=None, min_length=3, max_length=512)
    venue: str | None = Field(default=None, min_length=1, max_length=128)
    product_type: str | None = Field(default=None, min_length=1, max_length=64)
    quote_or_settlement_asset: str | None = Field(default=None, min_length=1, max_length=128)
    signal_head: str = Field(min_length=1, max_length=128)
    horizon_code: str = Field(min_length=1, max_length=64)
    scope_parameters: dict[str, str] = Field(default_factory=dict)

    @field_validator(
        "instrument_class",
        "venue",
        "product_type",
        "quote_or_settlement_asset",
        mode="before",
    )
    @classmethod
    def normalize_uppercase_scope_value(cls, value: str | None) -> str | None:
        """Normalize case-insensitive market identifiers before hashing them."""
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("scope identifiers must be non-empty strings")
        return value.strip().upper()

    @field_validator("canonical_id", "signal_head", "horizon_code", mode="before")
    @classmethod
    def normalize_exact_scope_value(cls, value: str | None) -> str | None:
        """Trim exact identifiers without changing their semantic case."""
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("scope identifiers must be non-empty strings")
        return value.strip()

    @field_validator("scope_parameters", mode="before")
    @classmethod
    def normalize_scope_parameters(cls, value: object) -> dict[str, str]:
        """Keep only explicit, scalar plugin parameters in deterministic order."""
        if not isinstance(value, Mapping):
            raise ValueError("scope_parameters must be a mapping of strings")

        normalized: dict[str, str] = {}
        for key, parameter in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("scope parameter names must be non-empty strings")
            if not isinstance(parameter, str) or not parameter.strip():
                raise ValueError("scope parameter values must be non-empty strings")
            normalized_key = key.strip()
            if normalized_key == "quote_or_settlement_asset":
                raise ValueError("quote_or_settlement_asset must use its dedicated scope field")
            if normalized_key in normalized:
                raise ValueError("scope parameter names must be unique after normalization")
            normalized[normalized_key] = parameter.strip()
        return dict(sorted(normalized.items()))

    @model_validator(mode="after")
    def validate_scope_shape(self) -> PromotionScope:
        """Reject ambiguous scope modes before a registry key can be trusted."""
        if self.scope_type == "POOLED" and self.canonical_id is not None:
            raise ValueError("POOLED scope must not define canonical_id")
        if self.scope_type == "INSTRUMENT_SPECIFIC" and self.canonical_id is None:
            raise ValueError("INSTRUMENT_SPECIFIC scope requires canonical_id")
        if self.scope_type == "VENUE_PRODUCT":
            if self.canonical_id is not None:
                raise ValueError("VENUE_PRODUCT scope must not define canonical_id")
            if not self.venue or not self.product_type or not self.quote_or_settlement_asset:
                raise ValueError("VENUE_PRODUCT scope requires venue, product_type and quote")
        return self

    def canonical_payload(self) -> dict[str, object]:
        """Return the exact normalized object whose hash identifies this scope."""
        return {
            "scope_type": self.scope_type,
            "asset_type": self.asset_type,
            "instrument_class": self.instrument_class,
            "canonical_id": self.canonical_id,
            "venue": self.venue,
            "product_type": self.product_type,
            "quote_or_settlement_asset": self.quote_or_settlement_asset,
            "signal_head": self.signal_head,
            "horizon_code": self.horizon_code,
            "scope_parameters": self.scope_parameters,
        }

    def scope_key(self) -> str:
        """Return the SHA-256 identifier for the canonical scope payload."""
        encoded = json.dumps(
            self.canonical_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class PromotionEvidenceMetrics(BaseModel):
    """The minimum machine-verifiable T2 evidence for one promoted model head.

    ``metrics_json`` remains extensible for research-specific diagnostics, but a
    public directional conclusion must not rely on a registry projection unless
    it supplies this complete common evidence set.
    """

    model_config = ConfigDict(extra="ignore")

    head_spec_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    sample_count: int = Field(ge=0)
    unique_evaluation_days: int = Field(ge=0)
    market_regime_count: int = Field(ge=0)
    walk_forward_train_before_test: bool
    overlap_purged: bool
    embargo_applied: bool
    vintage_data_enforced: bool
    block_length_covers_max_overlap: bool
    brier_score: float = Field(ge=0)
    baseline_brier_score: float = Field(gt=0)
    brier_skill_score: float
    expected_calibration_error: float = Field(ge=0)
    reliability_reviewed: bool
    mean_net_utility: float
    delta_net_utility_ci_lower: float
    tail_risk_approved: bool
    maximum_drawdown_approved: bool
    coverage_approved: bool
    data_failure_rate_approved: bool
    multiple_comparisons_controlled: bool
    forward_shadow_days: int = Field(ge=0)
    all_attempts_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_artifact_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_card_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    drift_report_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    max_instrument_share: float | None = Field(default=None, ge=0, le=1)
    cross_instrument_extrapolation_reviewed: bool | None = None
    futures_contract_month_count: int | None = Field(default=None, ge=0)
    option_expiry_count: int | None = Field(default=None, ge=0)
    option_strike_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def verify_brier_skill(self) -> PromotionEvidenceMetrics:
        """Reject non-finite or internally inconsistent probability evidence."""
        values = (
            self.brier_score,
            self.baseline_brier_score,
            self.brier_skill_score,
            self.expected_calibration_error,
            self.mean_net_utility,
            self.delta_net_utility_ci_lower,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("promotion evidence metrics must be finite")
        expected_skill = 1 - (self.brier_score / self.baseline_brier_score)
        if not math.isclose(self.brier_skill_score, expected_skill, rel_tol=1e-6, abs_tol=1e-6):
            raise ValueError("brier_skill_score must match brier_score and baseline_brier_score")
        return self


class BondResearchDetails(StrictModel):
    kind: Literal["BOND"] = "BOND"
    price_basis: Literal["EXECUTABLE", "OFFICIAL_VALUATION", "INDICATIVE"]
    clean_price: Decimal | None = None
    accrued_interest: Decimal | None = None
    dirty_price: Decimal | None = None
    yield_to_maturity: Decimal | None = None
    yield_to_worst: Decimal | None = None
    modified_duration: Decimal | None = None
    convexity: Decimal | None = None
    dv01: Decimal | None = None
    credit_spread_bps: Decimal | None = None
    valuation_reason_code: str | None = None
    liquidity_grade: Literal["HIGH", "MEDIUM", "LOW", "UNKNOWN"] = "UNKNOWN"


class FundResearchDetails(StrictModel):
    kind: Literal["FUND"] = "FUND"
    fund_type: Literal["ETF", "LOF", "OPEN_END", "MONEY_MARKET", "OTHER"]
    benchmark_code: str | None = None
    nav_total_return: Decimal | None = None
    benchmark_total_return: Decimal | None = None
    excess_return: Decimal | None = None
    expense_ratio: Decimal | None = None
    tracking_error: Decimal | None = None
    nav_premium_discount: Decimal | None = None
    style_drift_score: Decimal | None = None
    metrics_reason_code: str | None = None
    liquidity_grade: Literal["HIGH", "MEDIUM", "LOW", "NOT_APPLICABLE", "UNKNOWN"] = "UNKNOWN"


class FuturesResearchDetails(StrictModel):
    kind: Literal["FUTURES"] = "FUTURES"
    contract_code: str
    mapped_from_series: bool = False
    days_to_expiry: int | None = None
    basis: Decimal | None = None
    annualized_carry: Decimal | None = None
    roll_state: Literal["NORMAL", "ROLL_WINDOW", "NEAR_EXPIRY", "UNKNOWN"] = "UNKNOWN"
    margin_ratio: Decimal | None = None
    term_structure_reason_code: str | None = None


class OptionResearchDetails(StrictModel):
    kind: Literal["OPTION"] = "OPTION"
    underlying_view: Literal["BULLISH", "BEARISH", "NEUTRAL", "INDETERMINATE"]
    volatility_view: Literal["VOL_UP", "VOL_DOWN", "NEUTRAL", "INDETERMINATE"]
    contract_edge: Literal["CHEAP", "FAIR", "RICH", "UNKNOWN"]
    pricing_model: Literal["BSM", "BLACK_76", "AMERICAN_BINOMIAL"] | None = None
    market_price: Decimal | None = None
    theoretical_value: Decimal | None = None
    implied_volatility: Decimal | None = None
    implied_volatility_bid: Decimal | None = None
    implied_volatility_ask: Decimal | None = None
    delta: Decimal | None = None
    gamma: Decimal | None = None
    theta: Decimal | None = None
    vega: Decimal | None = None
    rho: Decimal | None = None
    break_even: Decimal | None = None
    max_loss: Decimal | None = None
    pricing_reason_code: str | None = None


class FxResearchDetails(StrictModel):
    kind: Literal["FX"] = "FX"
    base_currency: str
    quote_currency: str
    product_type: Literal["SPOT", "FORWARD", "NDF"]
    quote_kind: Literal["EXECUTABLE_PROXY", "INDICATIVE", "REFERENCE"]
    carry_estimate: Decimal | None = None
    valuation_gap: Decimal | None = None
    liquidity_grade: Literal["MAJOR", "MINOR", "EMERGING", "UNKNOWN"] = "UNKNOWN"


class CryptoResearchDetails(StrictModel):
    kind: Literal["CRYPTO"] = "CRYPTO"
    network: str | None = None
    venue: str | None = None
    product_type: Literal["ASSET", "SPOT", "PERPETUAL", "DELIVERY_FUTURE"]
    quote_currency: str | None = None
    composite_mid: Decimal | None = None
    composite_price_venue_count: int | None = None
    depth_1pct: Decimal | None = None
    stablecoin_depeg_bps: Decimal | None = None
    funding_rate: Decimal | None = None
    basis: Decimal | None = None
    onchain_regime: Literal["EXPANDING", "CONTRACTING", "MIXED", "UNAVAILABLE"] = "UNAVAILABLE"
    venue_risk_grade: Literal["LOW", "MEDIUM", "HIGH", "UNKNOWN"] = "UNKNOWN"
    market_quality_reason_code: str | None = None


AssetResearchDetails = Annotated[
    BondResearchDetails
    | FundResearchDetails
    | FuturesResearchDetails
    | OptionResearchDetails
    | FxResearchDetails
    | CryptoResearchDetails,
    Field(discriminator="kind"),
]


class EvidenceItem(StrictModel):
    evidence_id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=255)
    value: str | float | int | Decimal | None = None
    source_id: str | None = None


class ResearchDecision(StrictModel):
    """Canonical opinion persisted as candidate and separately as published output."""

    asset_type: AssetType
    market_view: MarketView
    normalized_direction: NormalizedDirection
    position_context: PositionContext
    horizon_code: str = Field(min_length=1, max_length=64)
    quality_status: QualityStatus
    recommendation: Recommendation = "HOLD"
    actionability: Actionability = "RESEARCH_ONLY"
    trade_intent: TradeIntent = "NONE"
    horizon_spec: HorizonSpec = Field(default_factory=HorizonSpec)
    confidence: float | None = Field(default=None, ge=0, le=1)
    primary_head_code: str | None = None
    prediction_heads: list[PredictionHead] = Field(default_factory=list)
    expected_return: float | None = None
    expected_risk: float | None = None
    reason_codes: list[str] = Field(default_factory=list)
    thesis: list[EvidenceItem] = Field(default_factory=list)
    counter_thesis: list[EvidenceItem] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    asset_details: AssetResearchDetails | None = None
    execution_disabled: Literal[True] = True

    @model_validator(mode="after")
    def verify_prediction_head_ownership(self) -> ResearchDecision:
        primary_heads = [head for head in self.prediction_heads if head.primary_for_promotion]
        if self.prediction_heads and len(primary_heads) != 1:
            raise ValueError("exactly one prediction head must be primary")
        if self.prediction_heads and self.primary_head_code != primary_heads[0].head_code:
            raise ValueError("primary_head_code must identify the primary prediction head")
        if not self.prediction_heads and self.primary_head_code is not None:
            raise ValueError("primary_head_code requires prediction_heads")
        return self


class AssetAdminSignalCandidateResponse(StrictModel):
    """Restricted shadow candidate payload for a system-owned evaluation record."""

    prediction_id: str
    owner_scope: Literal["PUBLIC_SHADOW", "ADMIN_EVAL"]
    asset_type: AssetType
    canonical_id: str
    as_of_at: datetime
    horizon_code: str
    candidate_decision: ResearchDecision


class AssetModelScopeResponse(StrictModel):
    """Read-only model-scope projection with its independently verifiable boundary."""

    registry_id: str
    promotion_scope_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    promotion_scope_type: str
    asset_type: AssetType
    instrument_class: str
    canonical_id_scope: str | None = None
    venue_scope: str | None = None
    product_type_scope: str | None = None
    scope_parameters: object
    scope_verified: bool
    signal_head: str
    horizon_code: str
    head_spec_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_spec_version: str
    scoreability_rule_version: str
    baseline_version: str
    policy_version: str
    model_version: str
    probability_artifact_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    calibration_version: str
    calibration_artifact_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    training_cutoff_at: datetime
    status: ModelStatus
    metrics: object
    approvals: object
    evidence_uri: str | None = None
    evidence_content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    approved_at: datetime | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    created_at: datetime


class AssetModelStatusEventResponse(StrictModel):
    """One immutable transition fact emitted alongside a model-scope projection."""

    event_id: str
    registry_id: str
    from_status: ModelStatus
    to_status: ModelStatus
    reason_codes: list[str] = Field(default_factory=list)
    metrics_snapshot: object
    evidence_uri: str | None = None
    evidence_content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    actor_id: str | None = None
    created_at: datetime


class AssetModelStatusTransitionRequest(StrictModel):
    """A status-only request; metrics, scope and evidence stay immutable server facts."""

    to_status: ModelStatus
    reason_codes: list[str] = Field(min_length=1, max_length=20)

    @field_validator("reason_codes")
    @classmethod
    def require_distinct_reason_codes(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 128 for value in normalized):
            raise ValueError("reason_codes must contain non-empty values up to 128 characters")
        if len(normalized) != len(set(normalized)):
            raise ValueError("reason_codes must be distinct")
        return normalized


class AssetModelStatusTransitionResponse(StrictModel):
    """The latest status projection and the append-only event that produced it."""

    model_scope: AssetModelScopeResponse
    event: AssetModelStatusEventResponse


class AssetModelCardResponse(StrictModel):
    """Read-only model-card projection generated from immutable registry facts."""

    registry_id: str
    model_name: str
    head_spec_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    owner: str
    evaluation_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_card_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    limitations: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)


class InstrumentSearchRequest(StrictModel):
    asset_type: PublicAssetType
    query: str = Field(min_length=1, max_length=128)
    venue: str | None = Field(default=None, max_length=128)
    identity_level: IdentityLevel | None = None
    limit: int = Field(default=20, ge=1, le=100)


class InstrumentResolveRequest(StrictModel):
    asset_type: PublicAssetType
    query: str = Field(min_length=1, max_length=128)
    venue: str | None = Field(default=None, max_length=128)
    canonical_id: str | None = Field(default=None, min_length=3, max_length=512)
    identity_level: IdentityLevel | None = None


class PositionContextCreateRequest(StrictModel):
    canonical_id: str = Field(min_length=3, max_length=512)
    position_context: PositionContext
    long_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    short_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    as_of_at: datetime
    expires_at: datetime | None = None


class PositionContextSnapshotResponse(StrictModel):
    """Public metadata for a user-declared context, without account details."""

    snapshot_id: str
    asset_type: AssetType
    canonical_id: str
    identity_version: str
    position_context: PositionContext
    long_quantity: Decimal
    short_quantity: Decimal
    as_of_at: datetime
    available_at: datetime
    expires_at: datetime | None = None
    source_type: str
    account_connected: Literal[False] = False
    content_hash: str


class AssetAnalysisCreateRequest(StrictModel):
    asset_type: PublicAssetType
    canonical_id: str = Field(min_length=3, max_length=512)
    horizon_code: str = Field(default="standard", min_length=1, max_length=64)
    position_context: PositionContext = "UNKNOWN"
    position_context_snapshot_id: str | None = None
    request_options: dict[str, Any] = Field(default_factory=dict)


class AssetSignalScheduleCreateRequest(StrictModel):
    """One confirmed asset schedule; v1 deliberately has no account context."""

    asset_type: PublicAssetType
    canonical_id: str = Field(min_length=3, max_length=512)
    horizon_code: str = Field(default="standard", min_length=1, max_length=64)
    horizon_spec: HorizonSpec = Field(default_factory=HorizonSpec)
    cron_expression: str = Field(min_length=9, max_length=128)
    timezone: str = Field(min_length=1, max_length=64)
    cutoff_policy: str = Field(min_length=1, max_length=128)
    misfire_policy: Literal["SKIP", "RUN_ONCE", "BACKFILL"] = "SKIP"


class AssetSignalScheduleUpdateRequest(StrictModel):
    """Only future schedule configuration can change; historical runs are frozen."""

    horizon_code: str | None = Field(default=None, min_length=1, max_length=64)
    horizon_spec: HorizonSpec | None = None
    cron_expression: str | None = Field(default=None, min_length=9, max_length=128)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    cutoff_policy: str | None = Field(default=None, min_length=1, max_length=128)
    misfire_policy: Literal["SKIP", "RUN_ONCE", "BACKFILL"] | None = None
    enabled: bool | None = None

    @model_validator(mode="after")
    def require_mutation(self) -> AssetSignalScheduleUpdateRequest:
        if all(value is None for value in self.model_dump().values()):
            raise ValueError("at least one future schedule field is required")
        return self


class AssetSignalScheduleResponse(StrictModel):
    schedule_id: str
    asset_type: AssetType
    canonical_id: str
    identity_version: str
    horizon_code: str
    horizon_spec: HorizonSpec
    position_context: Literal["UNKNOWN"] = "UNKNOWN"
    cron_expression: str
    timezone: str
    cutoff_policy: str
    cutoff_policy_version: str
    misfire_policy: Literal["SKIP", "RUN_ONCE", "BACKFILL"]
    schedule_version: int = Field(ge=1)
    enabled: bool
    next_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AssetSignalScheduleListResponse(StrictModel):
    items: list[AssetSignalScheduleResponse] = Field(default_factory=list)


class ApprovedScheduleManifestEntry(StrictModel):
    """One explicit, already-resolved target in an approved static manifest."""

    entry_key: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    schedule: AssetSignalScheduleCreateRequest


class ApprovedScheduleManifestCreateRequest(StrictModel):
    """Immutable configuration evidence for bounded system shadow schedules."""

    manifest_key: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    manifest_version: str = Field(min_length=1, max_length=64)
    owner_scope: ScheduleManifestOwnerScope
    approval_reference: str = Field(min_length=1, max_length=512)
    evidence_uri: str = Field(min_length=1, max_length=2048)
    evidence_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    entries: list[ApprovedScheduleManifestEntry] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def require_unique_entry_keys(self) -> ApprovedScheduleManifestCreateRequest:
        entry_keys = [entry.entry_key for entry in self.entries]
        if len(entry_keys) != len(set(entry_keys)):
            raise ValueError("manifest entry_key values must be unique")
        return self


class ApprovedScheduleManifestRetireRequest(StrictModel):
    """An explicit, durable reason for taking a system manifest out of service."""

    reason_codes: list[str] = Field(min_length=1, max_length=20)

    @field_validator("reason_codes")
    @classmethod
    def require_distinct_reason_codes(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 128 for value in normalized):
            raise ValueError("reason_codes must contain non-empty values up to 128 characters")
        if len(normalized) != len(set(normalized)):
            raise ValueError("reason_codes must be distinct")
        return normalized


class ApprovedScheduleManifestResponse(StrictModel):
    """Public control-plane metadata; it never exposes raw market payloads."""

    manifest_id: str
    manifest_key: str
    manifest_version: str
    owner_scope: ScheduleManifestOwnerScope
    approval_reference: str
    evidence_uri: str
    evidence_content_hash: str
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_by: str
    approved_at: datetime
    status: ScheduleManifestStatus
    retired_by: str | None = None
    retired_at: datetime | None = None
    retirement_reason_codes: list[str] = Field(default_factory=list)
    schedules: list[AssetSignalScheduleResponse] = Field(default_factory=list)


class AssetSignalRunResponse(StrictModel):
    run_id: str
    status: RunStatus
    schedule_id: str | None = None
    task_id: str | None = None
    asset_type: AssetType
    as_of_at: datetime
    cutoff_at: datetime
    counts: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    completed_at: datetime | None = None


class RawObservation(StrictModel):
    """One source field with the four timestamps required for PIT replay."""

    value: Any = None
    source_id: str | None = Field(default=None, min_length=1, max_length=128)
    observed_at: datetime | None = None
    published_at: datetime | None = None
    available_at: datetime | None = None
    retrieved_at: datetime
    license_tag: str | None = Field(default=None, min_length=1, max_length=64)
    missing_reason: str | None = Field(default=None, min_length=1, max_length=128)


class RawAssetSnapshot(StrictModel):
    """Unfiltered source state retained before quality gating can reject it."""

    identity: InstrumentIdentity
    cutoff_at: datetime
    retrieved_at: datetime
    raw_schema_version: str = Field(min_length=1, max_length=64)
    raw_fields: dict[str, Any] = Field(default_factory=dict)
    history_rows: list[dict[str, Any]] = Field(default_factory=list)
    observations: dict[str, RawObservation] = Field(default_factory=dict)
    source_manifest: dict[str, Any] = Field(default_factory=dict)
    license_tags: list[str] = Field(default_factory=list)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class QualityAssessment(StrictModel):
    status: QualityStatus
    reason_codes: list[str] = Field(default_factory=list)
    checks: dict[str, bool | str | int | float | None] = Field(default_factory=dict)


class EligibleAssetSnapshot(StrictModel):
    """A narrowed snapshot which only exists after a quality gate passes."""

    raw_snapshot: RawAssetSnapshot
    quality: QualityAssessment


class FeatureSet(StrictModel):
    feature_version: str = Field(min_length=1, max_length=64)
    values: dict[str, float | int | str | None] = Field(default_factory=dict)


class ReportSection(StrictModel):
    section_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    markdown: str
    evidence_ids: list[str] = Field(default_factory=list)


class OutcomeEvaluation(StrictModel):
    outcome_kind: str = Field(min_length=1, max_length=128)
    head_spec_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    horizon_code: str = Field(min_length=1, max_length=64)
    evaluator_version: str = Field(min_length=1, max_length=64)
    status: OutcomeStatus
    maturity_reason: MaturityReason | None = None
    maturity_at: datetime | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    reason_codes: list[str] = Field(default_factory=list)


class AssetAnalysisTaskResponse(StrictModel):
    task_id: str
    status: TaskStatus
    asset_type: AssetType
    canonical_id: str
    progress: int = Field(ge=0, le=100)
    message: str | None = None
    error_code: str | None = None
    report_id: str | None = None
    prediction_id: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class AssetAnalysisResultResponse(StrictModel):
    task_id: str
    status: TaskStatus
    report_id: str | None = None
    prediction_id: str | None = None
    published_decision: ResearchDecision | None = None
    report: dict[str, Any] | None = None


class AssetResearchReportResponse(StrictModel):
    report_id: str
    task_id: str
    prediction_id: str | None = None
    report: dict[str, Any]
    rendered_markdown: str
    content_hash: str
    created_at: datetime


class AssetAnalysisExportCreateRequest(StrictModel):
    format: Literal["MARKDOWN", "PDF"] = "MARKDOWN"


class AssetAnalysisExportResponse(StrictModel):
    export_id: str
    report_id: str
    format: Literal["MARKDOWN", "PDF"]
    status: Literal["QUEUED", "SUCCEEDED", "FAILED"]
    content_hash: str | None = None
    error_code: str | None = None
    download_url: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class AssetReportPublicationCreateRequest(StrictModel):
    target_type: Literal["KNOWLEDGE_BASE", "WORKSPACE"]
    target_ref: str = Field(min_length=1, max_length=256)
    title: str | None = Field(default=None, min_length=1, max_length=500)


class AssetReportPublicationResponse(StrictModel):
    publication_id: str
    report_id: str
    target_type: Literal["KNOWLEDGE_BASE", "WORKSPACE"]
    target_ref: str
    status: Literal["QUEUED", "SUCCEEDED", "FAILED"]
    external_ref: str | None = None
    content_hash: str | None = None
    error_code: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class SignalSummaryResponse(StrictModel):
    asset_type: AssetType
    canonical_id: str
    head_spec_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    available_head_spec_hashes: list[str] = Field(default_factory=list)
    cohort_selection_required: bool = False
    total_generated_count: int = Field(ge=0)
    excluded_prediction_count: int = Field(ge=0)
    generated_count: int = Field(ge=0)
    scorable_count: int = Field(ge=0)
    actioned_generated_count: int = Field(ge=0)
    actioned_scorable_count: int = Field(ge=0)
    actioned_success_count: int = Field(ge=0)
    actioned_success_rate: float | None = Field(default=None, ge=0, le=1)
    coverage_rate: float | None = Field(default=None, ge=0, le=1)
    maturity_rate: float | None = Field(default=None, ge=0, le=1)
    brier_score: float | None = Field(default=None, ge=0)
    brier_skill_score: float | None = None
    average_net_return: float | None = None
    max_drawdown: float | None = Field(default=None, le=0)
    calibration_bins: list[dict[str, float | int]] = Field(default_factory=list)
    action_breakdown: list[dict[str, Any]] = Field(default_factory=list)


class AssetSignalHistoryItem(StrictModel):
    prediction_id: str
    owner_scope: VisibleOwnerScope
    asset_type: AssetType
    canonical_id: str
    as_of_at: datetime
    horizon_code: str
    position_context: PositionContext
    actionability: Actionability
    quality_status: QualityStatus
    published_decision: ResearchDecision
    created_at: datetime


class AssetSignalHistoryResponse(StrictModel):
    items: list[AssetSignalHistoryItem] = Field(default_factory=list)
    next_cursor: str | None = None


class AssetSignalEvidenceSourceResponse(StrictModel):
    """Whitelisted provenance fields safe to return for a published prediction."""

    source_id: str | None = None
    provider: str | None = None
    license_status: str | None = None
    source_registry_status: str | None = None
    observed_at: datetime | None = None
    available_at: datetime | None = None
    retrieved_at: datetime | None = None
    capabilities: list[str] = Field(default_factory=list)
    allowed_uses: list[str] = Field(default_factory=list)


class AssetSignalEvidenceVersionsResponse(StrictModel):
    """Frozen version identifiers needed to reproduce a published result."""

    feature_version: str | None = None
    policy_version: str | None = None
    model_version: str | None = None
    calibration_version: str | None = None
    capability_version: str | None = None
    compliance_policy_version: str | None = None
    cutoff_policy_version: str | None = None
    head_spec_set_hash: str | None = None


class AssetSignalEvidenceResponse(StrictModel):
    """Redacted evidence manifest; raw source payloads and candidate decisions are excluded."""

    prediction_id: str
    canonical_id: str
    asset_type: PublicAssetType
    source: AssetSignalEvidenceSourceResponse
    source_snapshot_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    license_tags: list[str] = Field(default_factory=list)
    versions: AssetSignalEvidenceVersionsResponse
    reason_codes: list[str] = Field(default_factory=list)


class AssetSignalOutcomeResponse(StrictModel):
    outcome_id: str
    prediction_id: str
    outcome_kind: str
    head_spec_hash: str
    horizon_code: str
    evaluator_version: str
    status: OutcomeStatus
    maturity_reason: str | None = None
    maturity_at: datetime | None = None
    gross_return: Decimal | None = None
    net_return: Decimal | None = None
    benchmark_return: Decimal | None = None
    success_label: bool | None = None
    reason_codes: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    scored_at: datetime | None = None


class LegacyStockCompatibilityIdentity(StrictModel):
    """Legacy stock display identity intentionally kept outside canonical masters."""

    asset_type: Literal["stock"] = "stock"
    legacy_symbol: str = Field(min_length=1, max_length=32)
    symbol_name: str | None = Field(default=None, max_length=255)
    market_type: str = Field(min_length=1, max_length=32)
    identity_status: Literal["LEGACY_UNRESOLVED"] = "LEGACY_UNRESOLVED"


class LegacyStockCompatibilityDecision(StrictModel):
    """Versioned semantic view of one legacy action, always research-only."""

    legacy_signal_action: Literal["BUY", "SELL", "WATCH"]
    recommendation: Recommendation
    market_view: MarketView
    normalized_direction: NormalizedDirection
    confidence: float = Field(ge=0, le=1)
    risk_score: float = Field(ge=0, le=1)
    expected_excess_return: float | None = None
    actionability: Literal["RESEARCH_ONLY"] = "RESEARCH_ONLY"
    execution_disabled: Literal[True] = True


class LegacyStockCompatibilityOutcome(StrictModel):
    """Legacy score fields without fabricating a new outcome-head contract."""

    legacy_outcome_status: Literal["PENDING", "PARTIAL", "SCORED", "UNSCORABLE"]
    outcome_reason: str | None = None
    entry_date: date | None = None
    entry_price: float | None = None
    horizon_1d_return: float | None = None
    horizon_5d_return: float | None = None
    horizon_20d_return: float | None = None
    benchmark_20d_return: float | None = None
    excess_20d_return: float | None = None
    legacy_20d_action_correct: bool | None = None


class StockResearchCompatibilityItem(StrictModel):
    """Read-only bridge record; it is not an ``AssetSignalPrediction`` row."""

    compatibility_version: str = Field(min_length=1, max_length=64)
    legacy_prediction_id: str = Field(min_length=1, max_length=64)
    legacy_identity: LegacyStockCompatibilityIdentity
    source: str = Field(min_length=1, max_length=32)
    universe_code: str = Field(min_length=1, max_length=32)
    as_of_date: date
    available_at: datetime
    next_trading_date: date | None = None
    horizon_code: str = Field(min_length=1, max_length=64)
    decision: LegacyStockCompatibilityDecision
    quality_status: QualityStatus
    quality_reason_codes: list[str] = Field(default_factory=list)
    model_versions: dict[str, str] = Field(default_factory=dict)
    outcome: LegacyStockCompatibilityOutcome
    report_reference_id: str | None = None
    semantic_loss_reason_codes: list[str] = Field(default_factory=list)


class StockResearchCompatibilityHistoryResponse(StrictModel):
    """Scoped stock history rendered via the versioned compatibility adapter."""

    compatibility_version: str = Field(min_length=1, max_length=64)
    items: list[StockResearchCompatibilityItem] = Field(default_factory=list)
    next_cursor: str | None = None
