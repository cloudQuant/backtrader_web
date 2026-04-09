"""
Enhanced backtest schemas.

Includes strict input validation and range checks.
"""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _to_utc(dt: datetime) -> datetime:
    """Normalize datetimes to timezone-aware UTC for safe comparisons.

    Args:
        dt: The datetime to normalize.

    Returns:
        A timezone-aware UTC datetime.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class TaskStatus(str, Enum):
    """Task status enum."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BacktestRequest(BaseModel):
    """Backtest request schema (enhanced version)."""

    # Basic parameters
    strategy_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Strategy ID",
        pattern=r"^[a-zA-Z0-9_-]+$",  # Only letters, numbers, underscores, and hyphens
    )

    symbol: str = Field(
        ...,
        description="Stock code",
        pattern=r"^\d{6}\.(SH|SZ)$",  # Must be A-share format: 6 digits.SH or .SZ
    )

    # Date range (with validation)
    start_date: datetime = Field(
        ...,
        description="Start date",
    )

    end_date: datetime = Field(
        ...,
        description="End date",
    )

    # Capital and commission (with range limits)
    initial_cash: float = Field(
        ...,
        gt=0,  # Must be greater than 0
        le=10000000,  # Maximum 10 million
        description="Initial capital",
        examples=[100000, 1000000],
    )

    commission: float = Field(
        ...,
        ge=0,  # Must be greater than or equal to 0
        le=0.1,  # Maximum 10%
        description="Commission rate",
        examples=[0.001, 0.0003, 0.01],
    )

    # Strategy parameters (with type and range validation)
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Strategy parameters (must match strategy parameter definitions)",
    )

    @field_validator("start_date")
    @classmethod
    def normalize_start_date_timezone(cls, v: datetime) -> datetime:
        """Ensure start_date is timezone-aware UTC."""
        return _to_utc(v)

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, v: datetime, info) -> datetime:
        """Validate date range.

        Args:
            v: The end date value.
            info: Field validation context.

        Returns:
            The validated end date.

        Raises:
            ValueError: If end_date is before start_date, range exceeds 10 years,
                or end_date is in the future.
        """
        v = _to_utc(v)
        start_date = info.data.get("start_date")
        if isinstance(start_date, datetime):
            start_date = _to_utc(start_date)
        if start_date and v <= start_date:
            raise ValueError("end_date must be later than start_date")

        # Limit backtest time range (maximum 10 years)
        max_end_date = start_date + timedelta(days=3650) if start_date else None
        if max_end_date and v > max_end_date:
            raise ValueError("Backtest time range cannot exceed 10 years")

        # Cannot use future dates
        now = datetime.now(timezone.utc)
        if v > now:
            raise ValueError("end_date cannot be a future date")

        return v

    @field_validator("params")
    @classmethod
    def validate_params(cls, v: dict[str, Any], info) -> dict[str, Any]:
        """Validate strategy parameters.

        Args:
            v: The parameters to validate.
            info: Field validation context.

        Returns:
            The validated parameters.

        Raises:
            ValueError: If a parameter is unknown or has an invalid value.
        """
        if not v:
            return {}

        strategy_id = info.data.get("strategy_id")

        # Get strategy parameter definitions
        param_specs = get_strategy_params(strategy_id)

        # Validate each parameter
        for key, value in v.items():
            if key not in param_specs:
                raise ValueError(f"Unknown parameter: {key}")

            spec = param_specs[key]

            # Type validation. ParamSpec is defined in app/schemas/strategy.py.
            spec_type = (spec.type or "").lower()

            if spec_type == "int":
                if not isinstance(value, int):
                    raise ValueError(f"{key} must be an integer")
                if spec.min is not None and value < spec.min:
                    raise ValueError(f"{key} must be greater than or equal to {spec.min}")
                if spec.max is not None and value > spec.max:
                    raise ValueError(f"{key} must be less than or equal to {spec.max}")

            elif spec_type == "float":
                if not isinstance(value, (int, float)):
                    raise ValueError(f"{key} must be a number")
                if spec.min is not None and value < spec.min:
                    raise ValueError(f"{key} must be greater than or equal to {spec.min}")
                if spec.max is not None and value > spec.max:
                    raise ValueError(f"{key} must be less than or equal to {spec.max}")

            elif spec_type in {"str", "string"}:
                if not isinstance(value, str):
                    raise ValueError(f"{key} must be a string")
                if spec.options and value not in spec.options:
                    raise ValueError(f"{key} must be one of: {', '.join(map(str, spec.options))}")

            elif spec_type in {"bool", "boolean"}:
                if not isinstance(value, bool):
                    raise ValueError(f"{key} must be a boolean")

            # Generic enum-style validation: if options are provided, enforce membership.
            elif spec.options:
                if value not in spec.options:
                    raise ValueError(f"{key} must be one of: {', '.join(map(str, spec.options))}")

        return v

    @model_validator(mode="after")
    def validate_backtest_days(self) -> "BacktestRequest":
        """Validate backtest duration is at least 30 trading days.

        Returns:
            The validated backtest request.

        Raises:
            ValueError: If date range is less than 30 days.
        """
        if self.start_date and self.end_date:
            days = (self.end_date - self.start_date).days
            if days < 30:
                raise ValueError(
                    "Backtest time range cannot be less than 30 days (approximately 20 trading days)"
                )
        return self

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "strategy_id": "ma_cross",
                "symbol": "000001.SZ",
                "start_date": "2023-01-01T00:00:00",
                "end_date": "2023-12-31T00:00:00",
                "initial_cash": 100000,
                "commission": 0.001,
                "params": {
                    "fast_period": 5,
                    "slow_period": 20,
                },
            }
        }
    )


class BacktestResponse(BaseModel):
    """Backtest task response schema."""

    task_id: str = Field(..., description="Task ID")
    status: TaskStatus = Field(..., description="Task status")
    message: str | None = Field(None, description="Status message")


class BacktestStatusResponse(BaseModel):
    """Backtest task status response schema."""

    task_id: str = Field(..., description="Task ID")
    status: TaskStatus = Field(..., description="Task status")


class TradeRecord(BaseModel):
    """Trade record schema."""

    date: datetime
    type: Literal["buy", "sell"]  # Only allow buy or sell
    price: float = Field(..., gt=0, description="Trade price")
    size: int = Field(..., gt=0, description="Trade quantity")
    value: float = Field(..., gt=0, description="Trade value")
    pnl: float | None = Field(None, description="Profit/loss")


class BacktestResult(BaseModel):
    """Backtest result schema."""

    task_id: str
    strategy_id: str
    symbol: str
    start_date: datetime
    end_date: datetime
    status: TaskStatus

    # Performance metrics (with range validation)
    total_return: float = Field(0, ge=-100, le=10000, description="Total return (%)")
    annual_return: float = Field(0, ge=-100, le=10000, description="Annualized return (%)")
    sharpe_ratio: float = Field(0, description="Sharpe ratio")
    max_drawdown: float = Field(0, ge=-100, le=100, description="Maximum drawdown (%)")
    win_rate: float = Field(0, ge=0, le=100, description="Win rate (%)")

    # Trade statistics
    total_trades: int = Field(0, ge=0, description="Total trades")
    profitable_trades: int = Field(0, ge=0, description="Profitable trades")
    losing_trades: int = Field(0, ge=0, description="Losing trades")

    # Equity curve data
    equity_curve: list[float] = Field(default_factory=list, description="Equity curve")
    equity_dates: list[str] = Field(default_factory=list, description="Date sequence")
    drawdown_curve: list[float] = Field(default_factory=list, description="Drawdown curve")

    # Trade records
    trades: list[TradeRecord] = Field(default_factory=list, description="Trade records")

    # Meta information
    created_at: datetime
    error_message: str | None = None


class BacktestListResponse(BaseModel):
    """Backtest list response schema."""

    total: int = Field(..., ge=0, description="Total count")
    items: list[BacktestResult]


class BacktestConnectedEvent(BaseModel):
    """WebSocket connected event schema."""

    type: Literal["connected"] = "connected"
    task_id: str
    client_id: str
    message: str = "WebSocket connected successfully"


class BacktestTaskCreatedEvent(BaseModel):
    """Backtest task created event schema."""

    type: Literal["task_created"] = "task_created"
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    message: str = "Backtest task submitted"


class BacktestProgressEvent(BaseModel):
    """Backtest progress event schema."""

    type: Literal["progress"] = "progress"
    task_id: str
    status: TaskStatus = TaskStatus.RUNNING
    progress: int = Field(..., ge=0, le=100)
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class BacktestCompletedEvent(BaseModel):
    """Backtest completed event schema."""

    type: Literal["completed"] = "completed"
    task_id: str
    status: TaskStatus = TaskStatus.COMPLETED
    progress: int = Field(default=100, ge=0, le=100)
    message: str = "Backtest completed"
    result: dict[str, Any] | None = None


class BacktestFailedEvent(BaseModel):
    """Backtest failed event schema."""

    type: Literal["failed"] = "failed"
    task_id: str
    status: TaskStatus = TaskStatus.FAILED
    message: str = "Backtest failed"
    error: str


class BacktestCancelledEvent(BaseModel):
    """Backtest cancelled event schema."""

    type: Literal["cancelled"] = "cancelled"
    task_id: str
    status: TaskStatus = TaskStatus.CANCELLED
    message: str = "Task cancelled"


class OptimizationRequest(BaseModel):
    """Parameter optimization request schema."""

    # Optimization configuration
    strategy_id: str = Field(..., description="Strategy ID")
    backtest_config: BacktestRequest = Field(..., description="Backtest configuration")

    # Optimization method
    method: Literal["grid", "bayesian"] = Field(
        default="bayesian",
        description="Optimization method: grid (grid search) or bayesian (Bayesian optimization)",
    )

    # Optimization objective
    metric: Literal["sharpe_ratio", "max_drawdown", "total_return"] = Field(
        default="sharpe_ratio",
        description="Optimization objective: sharpe_ratio, max_drawdown (minimize), total_return",
    )

    # Grid search parameters
    param_grid: dict[str, list[Any]] | None = Field(
        None, description="Parameter grid (for grid search)"
    )

    # Bayesian optimization parameters
    param_bounds: dict[str, dict[str, Any]] | None = Field(
        None, description="Parameter bounds (for Bayesian optimization)"
    )

    # Number of trials
    n_trials: int = Field(
        default=100, ge=10, le=1000, description="Number of trials (for Bayesian optimization)"
    )

    @model_validator(mode="after")
    def validate_optimization_config(self) -> "OptimizationRequest":
        """Validate optimization configuration.

        Returns:
            The validated optimization request.

        Raises:
            ValueError: If required parameters are missing for the chosen method.
        """
        if self.method == "grid":
            if not self.param_grid:
                raise ValueError("Grid search requires param_grid parameter")
        elif self.method == "bayesian":
            if not self.param_bounds:
                raise ValueError("Bayesian optimization requires param_bounds parameter")

        return self

    model_config = ConfigDict(
        json_schema_extra={
            "example_grid": {
                "strategy_id": "ma_cross",
                "method": "grid",
                "metric": "sharpe_ratio",
                "backtest_config": {
                    "strategy_id": "ma_cross",
                    "symbol": "000001.SZ",
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                    "initial_cash": 100000,
                    "commission": 0.001,
                },
                "param_grid": {
                    "fast_period": [5, 10, 15],
                    "slow_period": [20, 30, 40],
                },
            },
            "example_bayesian": {
                "strategy_id": "ma_cross",
                "method": "bayesian",
                "metric": "sharpe_ratio",
                "n_trials": 100,
                "backtest_config": {
                    "strategy_id": "ma_cross",
                    "symbol": "000001.SZ",
                    "start_date": "2023-01-01",
                    "end_date": "2023-12-31",
                    "initial_cash": 100000,
                    "commission": 0.001,
                },
                "param_bounds": {
                    "fast_period": {"type": "int", "min": 5, "max": 20},
                    "slow_period": {"type": "int", "min": 20, "max": 60},
                },
            },
        }
    )


class OptimizationResult(BaseModel):
    """Optimization result schema."""

    # Best parameters
    best_params: dict[str, Any] = Field(..., description="Best parameter combination")
    # Best metrics
    best_metrics: dict[str, float] = Field(..., description="Best metric values")
    # All trial results
    all_results: list[dict[str, Any]] = Field(..., description="All trial results")
    # Number of trials
    n_trials: int = Field(..., ge=0, description="Actual number of trials")


# Helper function
def get_strategy_params(strategy_id: str) -> dict[str, Any]:
    """Get strategy parameter definitions.

    Args:
        strategy_id: The strategy ID.

    Returns:
        A dictionary of parameter definitions.
    """
    # Get parameter definitions from strategy templates
    from app.services.strategy_service import get_all_strategy_templates

    for template in get_all_strategy_templates():
        if template.id == strategy_id:
            return template.params

    # Return empty dict if not found
    return {}
