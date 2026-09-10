"""Strict contracts for Iteration 197 local-first market-data queries.

The public query model deliberately describes the requested data rather than a
provider function.  Identity resolution and catalog lookup happen after this
boundary, so callers cannot use a symbol-only request or an ambiguous legacy
period to accidentally retrieve nearby data.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MarketDataAssetType = Literal["stock", "futures", "bond", "fund", "option", "fx", "crypto"]
MarketDataKind = Literal[
    "bars",
    "quote_snapshot",
    "valuation_snapshot",
    "option_chain",
    "position_report",
    "reference_series",
    "inventory_report",
    "option_risk_surface",
]
MarketDataMode = Literal["local_first", "local_only", "refresh"]
MarketDataFrequency = Literal["5min", "30min", "1h", "1d", "1w", "1mo", "snapshot"]
MarketDataConsistency = Literal["display", "strict"]
MarketDataPurpose = Literal[
    "display",
    "research",
    "research_cache_fill",
    "backtest",
    "export",
]
MarketDataFamilyStatus = Literal["ready", "unconfigured", "not_applicable"]
MarketDataFamilyContractVersion = Literal["market-data-family-v1"]
MarketDataFrequencySemantics = Literal["calendar_grid", "snapshot", "reporting_period"]
MarketDataCoverageModel = Literal[
    "calendar_grid",
    "snapshot_freshness",
    "slice_completeness",
    "report_completeness",
]

_MAX_DIRECT_BAR_WINDOWS: dict[str, timedelta] = {
    "5min": timedelta(days=31),
    "30min": timedelta(days=90),
    "1h": timedelta(days=180),
    "1d": timedelta(days=3650),
    "1w": timedelta(days=7300),
    "1mo": timedelta(days=18250),
}
_MAX_DIRECT_SNAPSHOT_WINDOW = timedelta(days=7)


class _StrictMarketDataModel(BaseModel):
    """Base model that rejects misspelled public query fields."""

    model_config = ConfigDict(extra="forbid")


class QueryIdentity(_StrictMarketDataModel):
    """One exact instrument selector before server-side master-data resolution.

    A caller can supply a stable ``canonical_id`` or the complete identifying
    triple needed for a resolver to find one.  Supplying both is rejected so a
    disagreement cannot be silently resolved in favour of an arbitrary field.
    """

    canonical_id: str | None = Field(default=None, max_length=512)
    asset_type: MarketDataAssetType | None = None
    symbol: str | None = Field(default=None, max_length=128)
    market: str | None = Field(default=None, max_length=128)

    @field_validator("canonical_id", "symbol", "market")
    @classmethod
    def normalize_selector_text(cls, value: str | None) -> str | None:
        """Trim identifiers while preserving their provider-significant case."""
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("identity selector values must not be blank")
        return normalized

    @model_validator(mode="after")
    def require_one_exact_selector(self) -> QueryIdentity:
        """Reject partial triples and dual canonical/triple selectors."""
        triple = (self.asset_type, self.symbol, self.market)
        if self.canonical_id is not None:
            if any(value is not None for value in triple):
                raise ValueError(
                    "canonical_id cannot be combined with asset_type, symbol, or market"
                )
            return self

        if all(value is not None for value in triple):
            return self
        raise ValueError(
            "identity requires canonical_id or asset_type, symbol, and market together"
        )

    def semantic_payload(self) -> dict[str, str]:
        """Return the identity representation used by a pre-resolution query hash."""
        if self.canonical_id is not None:
            return {"canonical_id": self.canonical_id}
        return {
            "asset_type": self.asset_type or "",
            "symbol": self.symbol or "",
            "market": self.market or "",
        }


class MarketDataQueryBundleRequest(_StrictMarketDataModel):
    """Read-only request for the server-owned market-page family contract bundle.

    The bundle is a control-plane declaration, not a market-data query.  It
    therefore accepts no provider, endpoint, data window, or symbol selector.
    A symbol-specific bars request must still obtain the existing exact
    ``query-contract`` bridge before it can enter the v2 query service.
    """

    asset_type: MarketDataAssetType
    family_id: str | None = Field(default=None, max_length=128)

    @field_validator("family_id")
    @classmethod
    def normalize_family_id(cls, value: str | None) -> str | None:
        """Accept only a compact stable ``asset.family`` control-plane key."""
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("family_id must not be blank")
        parts = normalized.split(".")
        if len(parts) != 2 or any(not part.replace("_", "").isalnum() for part in parts):
            raise ValueError("family_id must use the stable asset.family form")
        if any(not part[0].islower() or part != part.lower() for part in parts):
            raise ValueError("family_id must use lowercase asset.family segments")
        return normalized


class MarketDataFieldProfileResponse(_StrictMarketDataModel):
    """Server-owned field and slice dimensions for one data-product contract."""

    profile_id: str = Field(min_length=1, max_length=128)
    required_fields: tuple[str, ...] = Field(min_length=1)
    optional_fields: tuple[str, ...] = ()
    dimension_fields: tuple[str, ...] = ()

    @field_validator("profile_id")
    @classmethod
    def normalize_profile_id(cls, value: str) -> str:
        """Reject whitespace-only or unstable profile identifiers."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("profile_id must not be blank")
        return normalized

    @field_validator("required_fields", "optional_fields", "dimension_fields", mode="before")
    @classmethod
    def normalize_field_groups(cls, value: Any) -> tuple[str, ...]:
        """Canonicalize field groups before checking their cross-group semantics."""
        if not isinstance(value, (list, tuple)):
            raise ValueError("field-profile groups must be lists or tuples")
        normalized_fields: list[str] = []
        for field_name in value:
            if not isinstance(field_name, str):
                raise ValueError("field-profile names must be strings")
            normalized = field_name.strip()
            if not normalized:
                raise ValueError("field-profile names must not be blank")
            normalized_fields.append(normalized)
        if len(normalized_fields) != len(set(normalized_fields)):
            raise ValueError("field-profile names must be distinct within a group")
        return tuple(normalized_fields)

    @model_validator(mode="after")
    def validate_disjoint_field_groups(self) -> MarketDataFieldProfileResponse:
        """Prevent a field from silently changing value/dimension semantics."""
        groups = (self.required_fields, self.optional_fields, self.dimension_fields)
        flattened = [field_name for group in groups for field_name in group]
        if len(flattened) != len(set(flattened)):
            raise ValueError("field-profile groups must not overlap")
        return self


class MarketDataFamilyContractResponse(_StrictMarketDataModel):
    """One auditable data-product declaration for a market-page display family."""

    family_id: str = Field(min_length=3, max_length=128)
    family_contract_version: MarketDataFamilyContractVersion = "market-data-family-v1"
    asset_type: MarketDataAssetType
    status: MarketDataFamilyStatus
    dataset_code: str = Field(min_length=1, max_length=255)
    data_kind: MarketDataKind
    frequency_semantics: MarketDataFrequencySemantics
    frequencies: tuple[MarketDataFrequency, ...] = Field(min_length=1)
    field_profile_id: str = Field(min_length=1, max_length=128)
    required_fields: tuple[str, ...] = Field(min_length=1)
    optional_fields: tuple[str, ...] = ()
    dimension_fields: tuple[str, ...] = ()
    coverage_model: MarketDataCoverageModel
    source_policy_id: str | None = Field(default=None, max_length=128)
    reason_code: str | None = Field(default=None, max_length=128)

    @field_validator(
        "family_id",
        "dataset_code",
        "field_profile_id",
        "source_policy_id",
        "reason_code",
    )
    @classmethod
    def normalize_contract_text(cls, value: str | None) -> str | None:
        """Reject blank contract axes instead of converting them to wildcards."""
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("market-data family contract text must not be blank")
        return normalized

    @field_validator("frequencies", mode="before")
    @classmethod
    def normalize_contract_frequencies(cls, value: Any) -> tuple[str, ...]:
        """Keep frequency declarations nonempty, ordered, and duplicate-free."""
        if not isinstance(value, (list, tuple)):
            raise ValueError("frequencies must be a list or tuple")
        normalized = tuple(value)
        if not normalized:
            raise ValueError("frequencies must not be empty")
        if len(normalized) != len(set(normalized)):
            raise ValueError("frequencies must be distinct")
        return normalized

    @field_validator("required_fields", "optional_fields", "dimension_fields", mode="before")
    @classmethod
    def normalize_contract_field_groups(cls, value: Any) -> tuple[str, ...]:
        """Apply the profile field-name rules to flattened public contract fields."""
        return MarketDataFieldProfileResponse.normalize_field_groups(value)

    @model_validator(mode="after")
    def validate_family_contract_semantics(self) -> MarketDataFamilyContractResponse:
        """Fail closed on data-kind, cadence, and execution-status disagreements."""
        family_asset_type, separator, family_name = self.family_id.partition(".")
        if (
            separator != "."
            or not family_name
            or family_asset_type != self.asset_type
            or self.family_id != self.family_id.lower()
        ):
            raise ValueError("family contract identity must match its lowercase asset.family key")
        # Constructing the reusable profile DTO proves that the flattened
        # wire shape cannot overlap its required, optional, and dimension axes.
        MarketDataFieldProfileResponse(
            profile_id=self.field_profile_id,
            required_fields=self.required_fields,
            optional_fields=self.optional_fields,
            dimension_fields=self.dimension_fields,
        )
        snapshot_kinds = {
            "quote_snapshot",
            "valuation_snapshot",
            "option_chain",
            "option_risk_surface",
        }
        has_snapshot_frequency = "snapshot" in self.frequencies
        if self.frequency_semantics == "snapshot":
            if self.frequencies != ("snapshot",) or self.data_kind not in snapshot_kinds:
                raise ValueError("snapshot contracts require a snapshot data kind and cadence")
        elif has_snapshot_frequency:
            raise ValueError("only snapshot contracts may declare the snapshot cadence")
        if self.frequency_semantics == "reporting_period" and self.data_kind not in {
            "position_report",
            "inventory_report",
        }:
            raise ValueError("reporting-period contracts require a report data kind")
        if self.frequency_semantics == "calendar_grid" and self.data_kind in snapshot_kinds:
            raise ValueError("snapshot data kinds cannot use a calendar-grid cadence")
        if self.status == "ready":
            # A ready response may only describe a reviewed single-record
            # coverage shape.  The registry remains the authority for the
            # exact family/policy allowlist; this DTO guard deliberately does
            # not make multi-record chains, surfaces, inventories, or reports
            # executable merely because their wire fields look plausible.
            calendar_grid_single_record = (
                self.data_kind in {"bars", "reference_series"}
                and self.frequency_semantics == "calendar_grid"
                and self.coverage_model == "calendar_grid"
            )
            snapshot_single_record = (
                self.data_kind == "quote_snapshot"
                and self.frequency_semantics == "snapshot"
                and self.coverage_model == "snapshot_freshness"
            )
            if (
                not (calendar_grid_single_record or snapshot_single_record)
                or self.source_policy_id is None
                or self.reason_code is not None
            ):
                raise ValueError("ready contracts require a reviewed single-record coverage shape")
        elif self.source_policy_id is not None or self.reason_code is None:
            raise ValueError(
                "non-ready contracts require a reason and cannot expose an execution policy"
            )
        return self


class MarketDataQueryBundleResponse(_StrictMarketDataModel):
    """Read-only, server-issued contracts for one market-page asset type."""

    version: Literal["market-data-family-bundle-v1"] = "market-data-family-bundle-v1"
    requested_asset_type: MarketDataAssetType
    families: tuple[MarketDataFamilyContractResponse, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bundle_family_uniqueness(self) -> MarketDataQueryBundleResponse:
        """Ensure a client never receives competing contracts for one family ID."""
        family_ids = [family.family_id for family in self.families]
        if len(family_ids) != len(set(family_ids)):
            raise ValueError("query bundle family IDs must be unique")
        return self


class MarketDataCapabilitiesResponse(_StrictMarketDataModel):
    """Safe effective rollout capabilities for authenticated market-data clients."""

    version: Literal["market-data-capabilities-v1"] = "market-data-capabilities-v1"
    query_v2_enabled: bool
    online_fetch_enabled: bool
    research_cache_fill_enabled: bool
    research_backtest_bridge_enabled: bool
    capability_states: tuple[MarketDataCapabilityStateResponse, ...] = Field(default_factory=tuple)


class MarketDataCapabilityStateResponse(_StrictMarketDataModel):
    """One safe lifecycle read for a server-owned rollout control or route.

    These fields are intentionally capability facts only.  They never expose
    credentials, provider commands, endpoint URLs, evidence hashes, or a
    caller's entitlement.  Route-level ``authorized`` means the durable
    deployment authorization record is current; a query still receives its
    exact user/source authorization at execution time.
    """

    capability_id: str = Field(min_length=1, max_length=192)
    scope: Literal["rollout", "route"]
    route_id: str | None = Field(default=None, max_length=128)
    declared: bool
    installed: bool
    verified: bool
    authorized: bool
    effective: bool
    reason_code: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_safe_lifecycle_shape(self) -> MarketDataCapabilityStateResponse:
        """Keep disabled explanations and route references unambiguous."""
        if self.scope == "route":
            if self.route_id is None:
                raise ValueError("route lifecycle state requires route_id")
        elif self.route_id is not None:
            raise ValueError("rollout lifecycle state cannot carry route_id")
        if self.effective and self.reason_code is not None:
            raise ValueError("effective capability state cannot carry a disable reason")
        if not self.effective and self.reason_code is None:
            raise ValueError("disabled capability state requires reason_code")
        return self


class MarketDataQueryRequest(_StrictMarketDataModel):
    """Versioned public request for one bounded local-first market-data query.

    ``start`` is inclusive and ``end`` is exclusive.  Both values are required
    to include an offset and are normalised to UTC before they reach coverage,
    provider, or persistence code.  Legacy inputs such as ``1m`` must be
    translated by a compatibility adapter before constructing this model.
    """

    identity: QueryIdentity
    data_kind: MarketDataKind
    start: datetime = Field(description="Inclusive ISO-8601 timestamp with timezone")
    end: datetime = Field(description="Exclusive ISO-8601 timestamp with timezone")
    required_fields: tuple[str, ...] = Field(description="Distinct canonical schema field names")

    # A request without this pair is the retained pre-bundle compatibility
    # path. When a market-page family bundle selected the query, the pair is
    # copied verbatim into the executable request and checked again after
    # catalog and identity resolution. This prevents a control-plane card from
    # being routed through a merely similar bars dataset.
    family_id: str | None = Field(default=None, max_length=128)
    family_contract_version: MarketDataFamilyContractVersion | None = None
    dataset_code: str | None = Field(default=None, max_length=255)
    frequency: MarketDataFrequency | None = None
    adjustment: str | None = Field(default=None, max_length=128)
    price_basis: str | None = Field(default=None, max_length=128)
    currency: str | None = Field(default=None, max_length=32)
    unit: str | None = Field(default=None, max_length=128)
    source_policy_id: str | None = Field(default=None, max_length=128)
    consistency: MarketDataConsistency = "display"
    purpose: MarketDataPurpose = "display"
    knowledge_cutoff: datetime | None = Field(
        default=None,
        description="Optional PIT availability cutoff, expressed with timezone",
    )
    mode: MarketDataMode = "local_first"
    page_size: int = Field(default=500, ge=1, le=2000)
    cursor: str | None = Field(default=None, max_length=2048)

    @field_validator(
        "family_id",
        "dataset_code",
        "adjustment",
        "price_basis",
        "currency",
        "unit",
        "source_policy_id",
        "cursor",
    )
    @classmethod
    def normalize_optional_query_text(cls, value: str | None) -> str | None:
        """Reject empty optional semantic values instead of treating them as unset."""
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("query text values must not be blank")
        return normalized

    @field_validator("family_id")
    @classmethod
    def validate_query_family_id(cls, value: str | None) -> str | None:
        """Require the same stable family key shape used by the bundle endpoint."""
        return MarketDataQueryBundleRequest.normalize_family_id(value)

    @field_validator("start", "end", "knowledge_cutoff")
    @classmethod
    def require_aware_utc_timestamps(cls, value: datetime | None) -> datetime | None:
        """Require explicit timezone evidence and keep all comparison values in UTC."""
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("market-data timestamps must include a timezone")
        return value.astimezone(timezone.utc)

    @field_validator("required_fields", mode="before")
    @classmethod
    def validate_required_fields(cls, value: Any) -> tuple[str, ...]:
        """Canonicalise a field set while failing closed on blanks and duplicates."""
        if not isinstance(value, (list, tuple)):
            raise ValueError("required_fields must be a non-empty list or tuple")

        normalized_fields: list[str] = []
        for field_name in value:
            if not isinstance(field_name, str):
                raise ValueError("required_fields must contain strings")
            normalized = field_name.strip()
            if not normalized:
                raise ValueError("required_fields must not contain blank names")
            normalized_fields.append(normalized)

        if not normalized_fields:
            raise ValueError("required_fields must not be empty")
        if len(normalized_fields) != len(set(normalized_fields)):
            raise ValueError("required_fields must be distinct")
        return tuple(sorted(normalized_fields))

    @model_validator(mode="after")
    def validate_query_window_and_frequency(self) -> MarketDataQueryRequest:
        """Enforce the half-open interval and the approved grid cadence."""
        if (self.family_id is None) != (self.family_contract_version is None):
            raise ValueError("family_id and family_contract_version must be specified together")
        if self.start >= self.end:
            raise ValueError("end must be later than start for half-open [start, end) queries")
        snapshot_kinds = {
            "quote_snapshot",
            "valuation_snapshot",
            "option_chain",
            "option_risk_surface",
        }
        report_kinds = {"position_report", "inventory_report"}
        if self.data_kind == "bars":
            if self.frequency is None:
                raise ValueError("bars queries require an explicit unambiguous frequency")
            if self.frequency == "snapshot":
                raise ValueError("bars queries cannot use the snapshot frequency")
        elif self.data_kind in snapshot_kinds:
            if self.frequency != "snapshot":
                raise ValueError("snapshot data kinds require the explicit snapshot frequency")
        elif self.data_kind in report_kinds | {"reference_series"}:
            if self.frequency is None or self.frequency == "snapshot":
                raise ValueError(
                    "report and reference-series queries require a non-snapshot frequency"
                )
        if self.purpose in {"research", "backtest"}:
            if self.consistency != "strict":
                raise ValueError("research and backtest queries require strict consistency")
        if self.purpose == "research_cache_fill":
            if self.mode != "local_first":
                raise ValueError("research_cache_fill queries require local_first mode")
            if self.consistency != "display":
                raise ValueError("research_cache_fill queries require display consistency")
            if self.knowledge_cutoff is not None:
                raise ValueError("research_cache_fill queries cannot set a knowledge_cutoff")
            if self.cursor is not None:
                raise ValueError("research_cache_fill queries cannot use a pagination cursor")
        if self.consistency == "strict" and self.knowledge_cutoff is None:
            raise ValueError("strict queries require a knowledge_cutoff")
        if self.mode == "refresh" and self.cursor is not None:
            raise ValueError("refresh queries cannot use a frozen pagination cursor")
        if (
            self.purpose == "backtest"
            and self.knowledge_cutoff is not None
            and self.knowledge_cutoff > self.end
        ):
            raise ValueError("backtest knowledge_cutoff cannot be after the query end")
        # Reference series have the same calendar-grid coverage semantics as
        # bars: an exact daily (or later reviewed weekly/monthly) series needs
        # a practical historical request window, not the seven-day freshness
        # cap reserved for snapshots and unsupported record shapes.  Public
        # callers still need a server-issued family binding, and the registry
        # limits currently-ready reference products to their declared cadence.
        max_window = (
            _MAX_DIRECT_BAR_WINDOWS[self.frequency]
            if self.data_kind in {"bars", "reference_series"} and self.frequency is not None
            else _MAX_DIRECT_SNAPSHOT_WINDOW
        )
        if self.end - self.start > max_window:
            raise ValueError("query interval exceeds the direct local-first window limit")
        return self

    def semantic_payload(self) -> dict[str, object]:
        """Build the canonical content-affecting payload for query deduplication.

        Pagination alters transport behaviour only, so ``cursor`` and
        ``page_size`` are intentionally omitted.
        All selection, data-shape, and policy fields remain in the payload.
        """
        return {
            "contract_version": "market-data-query-v1",
            "identity": self.identity.semantic_payload(),
            "family_id": self.family_id,
            "family_contract_version": self.family_contract_version,
            "dataset_code": self.dataset_code,
            "data_kind": self.data_kind,
            "frequency": self.frequency,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "required_fields": list(self.required_fields),
            "adjustment": self.adjustment,
            "price_basis": self.price_basis,
            "currency": self.currency,
            "unit": self.unit,
            "source_policy_id": self.source_policy_id,
            "consistency": self.consistency,
            "purpose": self.purpose,
            "knowledge_cutoff": (
                self.knowledge_cutoff.isoformat() if self.knowledge_cutoff is not None else None
            ),
            "mode": self.mode,
        }

    @property
    def query_fingerprint(self) -> str:
        """Return a stable SHA-256 fingerprint of the query's semantic payload."""
        canonical_json = json.dumps(
            self.semantic_payload(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class PublicMarketDataQueryRequest(MarketDataQueryRequest):
    """Public v2 request with a mandatory server-issued family binding.

    ``MarketDataQueryRequest`` remains the internal orchestration DTO so
    lower-level import and migration tools can describe normalized work before
    a display-family contract exists.  Every HTTP v2 request uses this subtype:
    it requires the family identifier and version before catalog, identity, or
    provider work can begin.
    """

    family_id: str = Field(min_length=1, max_length=128)
    family_contract_version: MarketDataFamilyContractVersion


class ResolvedMarketDataQuery(MarketDataQueryRequest):
    """A query after the server has fixed catalog and instrument identity facts.

    Services must use this model's fingerprint for work sharing and version
    lookup.  In particular, a symbol/market selector is replaced by its server
    canonical identity so aliases cannot become independent persisted series.
    """

    canonical_id: str = Field(min_length=1, max_length=512)
    dataset_code: str = Field(min_length=1, max_length=255)
    instrument_metadata_version: str = Field(min_length=1, max_length=128)

    @field_validator("canonical_id", "instrument_metadata_version")
    @classmethod
    def normalize_resolved_text(cls, value: str) -> str:
        """Ensure resolver outputs cannot smuggle blank identity/version values."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("resolved identity values must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_explicit_canonical_selector(self) -> ResolvedMarketDataQuery:
        """Require the public selector to be replaced by its resolved canonical ID."""
        if self.identity.canonical_id != self.canonical_id:
            raise ValueError("resolved query identity must equal its canonical_id")
        return self

    @classmethod
    def from_request(
        cls,
        request: MarketDataQueryRequest,
        *,
        canonical_id: str,
        dataset_code: str,
        instrument_metadata_version: str,
    ) -> ResolvedMarketDataQuery:
        """Create the post-resolution contract without preserving transport controls as semantics."""
        payload = request.model_dump()
        if (
            request.identity.canonical_id is not None
            and request.identity.canonical_id != canonical_id
        ):
            raise ValueError("resolved canonical_id does not match the requested canonical_id")
        payload.update(
            {
                "identity": {"canonical_id": canonical_id},
                "canonical_id": canonical_id,
                "dataset_code": dataset_code,
                "instrument_metadata_version": instrument_metadata_version,
            }
        )
        return cls.model_validate(payload)

    def semantic_payload(self) -> dict[str, object]:
        """Replace an input alias with the authoritative identity in the semantic key."""
        payload = super().semantic_payload()
        payload["identity"] = {"canonical_id": self.canonical_id}
        payload["dataset_code"] = self.dataset_code
        payload["instrument_metadata_version"] = self.instrument_metadata_version
        return payload


class MarketDataObservationResponse(BaseModel):
    """One locally selected, source-traceable normalized observation."""

    model_config = ConfigDict(extra="forbid")

    revision_id: str
    source_snapshot_id: str
    event_at: datetime
    available_at: datetime
    committed_at: datetime
    revision_number: int
    quality: str
    fields: dict[str, Any]


class MarketDataCoverageGapResponse(BaseModel):
    """A contiguous exact-calendar gap and the bounded interval that could fill it."""

    model_config = ConfigDict(extra="forbid")

    position: str
    event_at: tuple[datetime, ...]
    fetch_start: datetime
    fetch_end: datetime


class MarketDataCoverageResponse(BaseModel):
    """Coverage evidence evaluated from local rows and a frozen calendar."""

    model_config = ConfigDict(extra="forbid")

    status: str
    expected_event_count: int
    accepted_event_count: int
    missing_event_count: int
    coverage_ratio: float | None
    gaps: tuple[MarketDataCoverageGapResponse, ...]
    rejection_counts: dict[str, int]
    calendar_reason: str | None


class MarketDataFetchResponse(BaseModel):
    """Durable evidence identifiers produced by one provider route execution."""

    model_config = ConfigDict(extra="forbid")

    route_id: str
    provider_id: str
    source_snapshot_id: str
    observation_revision_ids: tuple[str, ...]
    passing_observation_count: int
    failed_observation_count: int


class MarketDataQueryWarningResponse(BaseModel):
    """Non-sensitive machine-readable policy or provider diagnostic."""

    model_config = ConfigDict(extra="forbid")

    code: str
    route_id: str | None = None
    provider_id: str | None = None


class MarketDataQueryResponse(BaseModel):
    """Fixed v2 payload returned after a local-first market-data query."""

    model_config = ConfigDict(extra="forbid")

    query_id: str
    canonical_id: str
    dataset_code: str
    asset_type: MarketDataAssetType
    instrument_metadata_version: str
    data_kind: MarketDataKind
    frequency: str
    source_policy_id: str
    family_id: str
    family_contract_version: MarketDataFamilyContractVersion
    knowledge_cutoff: datetime
    identity_knowledge_cutoff: datetime
    observations: tuple[MarketDataObservationResponse, ...]
    next_cursor: str | None
    coverage: MarketDataCoverageResponse
    fetches: tuple[MarketDataFetchResponse, ...]
    warnings: tuple[MarketDataQueryWarningResponse, ...]
    refresh_status: (
        Literal["fresh_complete", "fresh_incomplete", "fresh_unknown_calendar"] | None
    ) = None
    historical_status: Literal["unknown_calendar", "HISTORICAL_COVERAGE_UNAVAILABLE"] | None = None
