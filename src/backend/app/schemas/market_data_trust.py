"""Schemas for market data trust, precheck, execution model, and robustness."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AssetType = Literal["stock", "futures", "bond", "fund", "option", "fx", "crypto", "commodity"]
QualityStatus = Literal["pass", "warning", "failed", "unknown"]
GateSeverity = Literal["error", "warning", "info"]


class QualityGateEvaluation(BaseModel):
    """Unified quality gate evaluation item."""

    key: str
    label: str
    actual: float | int | str | bool | None = None
    threshold: float | int | str | bool | None = None
    operator: str = ">="
    passed: bool = False
    severity: GateSeverity = "error"
    message: str = ""


class AssetSpecBase(BaseModel):
    asset_type: AssetType | str
    symbol: str
    name: str = ""
    exchange: str = ""
    currency: str = "CNY"
    contract_multiplier: float | None = None
    margin_rate: float | None = None
    tick_size: float | None = None
    lot_size: float | None = None
    min_order_size: float | None = None
    commission_rate: float | None = None
    commission_fixed: float | None = None
    slippage_model: str = "bps"
    trading_calendar: str = "CN"
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_json")
    source: str = ""

    model_config = ConfigDict(populate_by_name=True)


class AssetSpecCreate(AssetSpecBase):
    pass


class AssetSpecResponse(AssetSpecBase):
    id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MarketDataCoverageBase(BaseModel):
    asset_type: AssetType | str
    symbol: str
    timeframe: str = "1d"
    provider: str = "local_csv"
    start_date: str | None = None
    end_date: str | None = None
    row_count: int = 0
    missing_count: int = 0
    missing_ratio: float = 0.0
    latest_bar_time: str | None = None
    quality_status: QualityStatus | str = "unknown"
    source_path: str | None = None


class MarketDataCoverageResponse(MarketDataCoverageBase):
    id: str
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class MarketDataQualityReportResponse(BaseModel):
    id: str
    asset_type: AssetType | str
    symbol: str
    timeframe: str
    provider: str
    issue_type: str
    severity: GateSeverity | str
    issue_count: int
    sample_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class MarketDataCoverageMatrixResponse(BaseModel):
    total: int
    items: list[MarketDataCoverageResponse]
    refreshed: bool = False


class DataPrecheckRequest(BaseModel):
    asset_type: AssetType | str | None = None
    symbol: str
    timeframe: str = "1d"
    provider: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class DataPrecheckResponse(BaseModel):
    passed: bool
    status: QualityStatus | str
    asset_type: str
    symbol: str
    timeframe: str
    provider: str
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    asset_spec: AssetSpecResponse | None = None
    coverage: MarketDataCoverageResponse | None = None
    quality_reports: list[MarketDataQualityReportResponse] = Field(default_factory=list)
    gate_evaluations: list[QualityGateEvaluation] = Field(default_factory=list)


class ExecutionModelResponse(BaseModel):
    asset_type: str
    symbol: str
    commission_rate: float = 0.0
    commission_fixed: float = 0.0
    slippage_bps: float = 0.0
    min_order_size: float = 1.0
    lot_size: float = 1.0
    contract_multiplier: float = 1.0
    margin_rate: float | None = None
    volume_limit_ratio: float | None = None
    price_limit_policy: str = "placeholder"
    suspended_policy: str = "placeholder"
    source: str = ""


class RobustnessValidationRequest(BaseModel):
    methods: list[str] = Field(default_factory=lambda: ["monte_carlo"])
    min_robustness_score: float = Field(55.0, ge=0, le=100)
    require_no_high_risk: bool = True
    monte_carlo_iterations: int = Field(300, ge=50, le=5000)
    random_seed: int | None = Field(None, ge=0)
    run_id: str | None = None
    strategy_version_id: str | None = None


class RobustnessTestResultResponse(BaseModel):
    id: str
    user_id: str
    run_id: str | None = None
    strategy_version_id: str | None = None
    backtest_id: str
    method: str
    status: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    gate_evaluations: list[QualityGateEvaluation | dict[str, Any]] = Field(default_factory=list)
    report: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
