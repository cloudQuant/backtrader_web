"""
Strategy schemas.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrategyType(str, Enum):
    """Strategy type enumeration."""

    backtest = "backtest"
    simulate = "simulate"
    live = "live"


class ParamSpec(BaseModel):
    """Parameter specification schema."""

    type: str = Field("float", description="Parameter type: int/float/string/enum")
    default: Any = Field(..., description="Default value")
    min: float | None = Field(None, description="Minimum value")
    max: float | None = Field(None, description="Maximum value")
    options: list[Any] | None = Field(None, description="Enum options")
    description: str | None = Field(None, description="Parameter description")


class StrategyCreate(BaseModel):
    """Strategy creation request schema."""

    name: str = Field(..., min_length=1, max_length=100, description="Strategy name")
    description: str | None = Field(None, description="Strategy description")
    code: str = Field(..., description="Strategy code")
    params: dict[str, ParamSpec] = Field(default_factory=dict, description="Parameter definitions")
    category: str = Field("custom", description="Strategy category")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Dual Moving Average Strategy",
                "description": "Trend strategy based on fast and slow moving average crossover",
                "code": "class MaCrossStrategy(bt.Strategy):\n    params = (('fast', 5), ('slow', 20))\n    ...",
                "params": {
                    "fast_period": {
                        "type": "int",
                        "default": 5,
                        "min": 2,
                        "max": 50,
                        "description": "Fast period",
                    },
                    "slow_period": {
                        "type": "int",
                        "default": 20,
                        "min": 10,
                        "max": 200,
                        "description": "Slow period",
                    },
                },
                "category": "trend",
            }
        }
    )


class StrategyUpdate(BaseModel):
    """Strategy update request schema."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    code: str | None = None
    params: dict[str, ParamSpec] | None = None
    category: str | None = None


class StrategyResponse(BaseModel):
    """Strategy response schema."""

    id: str = Field(..., description="Strategy ID")
    user_id: str = Field(..., description="User ID")
    name: str = Field(..., description="Strategy name")
    description: str | None = Field(None, description="Strategy description")
    code: str = Field(..., description="Strategy code")
    params: dict[str, ParamSpec] = Field(default_factory=dict, description="Parameter definitions")
    category: str = Field(..., description="Strategy category")
    created_at: datetime = Field(..., description="Creation time")
    updated_at: datetime = Field(..., description="Update time")

    model_config = ConfigDict(from_attributes=True)


class StrategyListResponse(BaseModel):
    """Strategy list response schema."""

    total: int
    items: list[StrategyResponse]


class StrategyTemplate(BaseModel):
    """Strategy template schema."""

    id: str
    name: str
    description: str
    code: str
    params: dict[str, ParamSpec]
    category: str
