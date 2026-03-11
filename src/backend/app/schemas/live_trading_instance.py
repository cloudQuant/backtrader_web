"""
Live trading instance schemas.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LiveInstanceCreate(BaseModel):
    """Live trading instance creation request schema."""

    strategy_id: str = Field(..., description="Strategy directory name, e.g., 002_dual_ma")
    params: dict[str, Any] | None = Field(None, description="Custom parameter overrides")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "strategy_id": "us_stock_ib_gateway_demo",
                "params": {
                    "symbol": "AAPL",
                    "gateway": {
                        "enabled": True,
                        "provider": "gateway",
                        "exchange_type": "IB_WEB",
                        "asset_type": "STK",
                        "account_id": "DU123456",
                        "base_url": "https://localhost:5000",
                        "verify_ssl": False,
                    },
                },
            }
        }
    )


class LiveGatewayPresetFieldInfo(BaseModel):
    key: str = Field(..., description="Gateway field key")
    label: str = Field(..., description="Field label")
    input_type: str = Field(..., description="Field input type, e.g. string or boolean")
    placeholder: str | None = Field(None, description="Optional input placeholder")


class LiveGatewayPresetInfo(BaseModel):
    """Live gateway preset configuration info."""

    description: str | None = Field(None, description="Preset description")
    id: str = Field(..., description="Preset ID")
    name: str = Field(..., description="Preset name")
    params: dict[str, Any] = Field(default_factory=dict, description="Preset params payload")
    editable_fields: list[LiveGatewayPresetFieldInfo] = Field(
        default_factory=list,
        description="Editable gateway field metadata for frontend rendering",
    )


class LiveGatewayPresetListResponse(BaseModel):
    """Response schema for listing live gateway presets."""

    total: int
    presets: list[LiveGatewayPresetInfo]


class LiveInstanceInfo(BaseModel):
    """Live trading instance info schema."""

    id: str = Field(..., description="Unique instance ID")
    strategy_id: str = Field(..., description="Strategy directory name")
    strategy_name: str = Field("", description="Strategy name")
    status: str = Field("stopped", description="Status: running / stopped / error")
    pid: int | None = Field(None, description="Process PID")
    error: str | None = Field(None, description="Error message")
    params: dict[str, Any] = Field(default_factory=dict, description="Runtime parameters")
    created_at: str = Field("", description="Creation time")
    started_at: str | None = Field(None, description="Last start time")
    stopped_at: str | None = Field(None, description="Last stop time")
    log_dir: str | None = Field(None, description="Latest log directory")


class LiveInstanceListResponse(BaseModel):
    """Live trading instance list response schema."""

    total: int
    instances: list[LiveInstanceInfo]


class LiveBatchResponse(BaseModel):
    """Batch operation response schema."""

    success: int = 0
    failed: int = 0
    details: list[dict[str, str]] = Field(default_factory=list)
