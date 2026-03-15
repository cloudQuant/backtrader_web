"""
Workspace and StrategyUnit Pydantic schemas.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Workspace schemas
# ---------------------------------------------------------------------------


class WorkspaceCreate(BaseModel):
    """Create workspace request."""

    name: str = Field(..., max_length=200, description="Workspace name")
    description: str | None = Field(None, max_length=500, description="Description")
    settings: dict[str, Any] = Field(default_factory=dict, description="Settings JSON")


class WorkspaceUpdate(BaseModel):
    """Update workspace request."""

    name: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=500)
    settings: dict[str, Any] | None = None


class WorkspaceResponse(BaseModel):
    """Workspace response."""

    id: str
    user_id: str
    name: str
    description: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    unit_count: int = 0
    completed_count: int = 0
    status: str = "idle"
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkspaceListResponse(BaseModel):
    """Workspace list response."""

    total: int
    items: list[WorkspaceResponse]


# ---------------------------------------------------------------------------
# StrategyUnit schemas
# ---------------------------------------------------------------------------


class StrategyUnitCreate(BaseModel):
    """Create strategy unit request."""

    group_name: str = Field("", max_length=200, description="Group name")
    strategy_id: str | None = Field(None, description="Strategy template ID")
    strategy_name: str = Field("", max_length=200, description="Strategy display name")
    symbol: str = Field("", max_length=50, description="Trading symbol code")
    symbol_name: str = Field("", max_length=200, description="Symbol display name")
    timeframe: str = Field("1d", max_length=10, description="K-line timeframe")
    timeframe_n: int = Field(1, ge=1, description="Timeframe multiplier")
    category: str = Field("", max_length=100, description="Classification tag")
    data_config: dict[str, Any] = Field(default_factory=dict)
    unit_settings: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    optimization_config: dict[str, Any] = Field(default_factory=dict)


class StrategyUnitBatchCreate(BaseModel):
    """Batch create strategy units request."""

    units: list[StrategyUnitCreate] = Field(..., min_length=1)


class StrategyUnitUpdate(BaseModel):
    """Update strategy unit request."""

    group_name: str | None = None
    strategy_id: str | None = None
    strategy_name: str | None = None
    symbol: str | None = None
    symbol_name: str | None = None
    timeframe: str | None = None
    timeframe_n: int | None = None
    category: str | None = None
    data_config: dict[str, Any] | None = None
    unit_settings: dict[str, Any] | None = None
    params: dict[str, Any] | None = None
    optimization_config: dict[str, Any] | None = None


class StrategyUnitResponse(BaseModel):
    """Strategy unit response."""

    id: str
    workspace_id: str
    group_name: str = ""
    strategy_id: str | None = None
    strategy_name: str = ""
    symbol: str = ""
    symbol_name: str = ""
    timeframe: str = "1d"
    timeframe_n: int = 1
    category: str = ""
    sort_order: int = 0
    data_config: dict[str, Any] = Field(default_factory=dict)
    unit_settings: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    optimization_config: dict[str, Any] = Field(default_factory=dict)
    run_status: str = "idle"
    run_count: int = 0
    last_run_time: float | None = None
    last_task_id: str | None = None
    last_optimization_task_id: str | None = None
    bar_count: int | None = None
    metrics_snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StrategyUnitListResponse(BaseModel):
    """Strategy unit list response."""

    total: int
    items: list[StrategyUnitResponse]


# ---------------------------------------------------------------------------
# Bulk operation schemas
# ---------------------------------------------------------------------------


class BulkDeleteRequest(BaseModel):
    """Bulk delete request."""

    ids: list[str] = Field(..., min_length=1)


class SortRequest(BaseModel):
    """Reorder units request."""

    unit_ids: list[str] = Field(..., min_length=1, description="Ordered list of unit IDs")


class GroupRenameRequest(BaseModel):
    """Group rename request."""

    unit_ids: list[str] = Field(..., min_length=1)
    mode: str = Field(
        "custom",
        description="Rename mode: custom/strategy/symbol/symbol_name/category/replace",
    )
    value: str = Field("", description="New name for custom mode")
    search: str = Field("", description="Search string for replace mode")
    replace: str = Field("", description="Replace string for replace mode")


class UnitRenameRequest(BaseModel):
    """Unit rename request (single unit display name override)."""

    unit_id: str
    mode: str = Field("custom")
    value: str = Field("")
    search: str = Field("")
    replace: str = Field("")


# ---------------------------------------------------------------------------
# Run orchestration schemas
# ---------------------------------------------------------------------------


class RunUnitsRequest(BaseModel):
    """Run selected strategy units."""

    unit_ids: list[str] = Field(..., min_length=1)
    parallel: bool = Field(False, description="Run in parallel if True, sequential if False")


class StopUnitsRequest(BaseModel):
    """Stop selected running strategy units."""

    unit_ids: list[str] = Field(..., min_length=1)


class UnitStatusResponse(BaseModel):
    """Unit run status response for polling."""

    id: str
    run_status: str
    last_task_id: str | None = None
    metrics_snapshot: dict[str, Any] = Field(default_factory=dict)
    run_count: int = 0
    last_run_time: float | None = None


# ---------------------------------------------------------------------------
# Optimization schemas (Phase 4)
# ---------------------------------------------------------------------------


class ParamRangeSpec(BaseModel):
    """Parameter range for optimization."""

    start: float
    end: float
    step: float
    type: str = "float"


class UnitOptimizationRequest(BaseModel):
    """Submit optimization for a strategy unit."""

    unit_id: str
    param_ranges: dict[str, ParamRangeSpec]
    n_workers: int = Field(default=4, ge=1, le=32)
    mode: str = Field("grid", description="Optimization mode: grid/random")
    timeout: int = Field(0, ge=0, description="Timeout in seconds (0 = no limit)")


class ApplyBestParamsRequest(BaseModel):
    """Apply best parameters from optimization to a unit."""

    unit_id: str
    optimization_task_id: str
    result_index: int = Field(0, ge=0, description="Index of result to apply (0 = best)")


# ---------------------------------------------------------------------------
# Report schemas (Phase 5)
# ---------------------------------------------------------------------------


class ReportCreateRequest(BaseModel):
    """Create / recalculate combined report with config."""

    start_date: str | None = Field(None, description="Statistics start date (ISO)")
    end_date: str | None = Field(None, description="Statistics end date (ISO)")
    max_cash: float | None = Field(None, description="Override max invested cash")
    calc_method: str = Field("simple", description="Calculation method: simple/compound")
    annual_days: int = Field(252, ge=1, description="Trading days per year")
    weight_mode: str = Field("equal", description="Weight mode: equal/custom")
    weights: dict[str, float] = Field(default_factory=dict, description="Unit ID -> weight (custom mode)")


class ReportDeleteRequest(BaseModel):
    """Delete report (clear cached report for workspace)."""

    pass
