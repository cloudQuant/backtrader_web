"""
Live trading instance schemas.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class LiveInstanceCreate(BaseModel):
    """Live trading instance creation request schema."""
    strategy_id: str = Field(..., description="Strategy directory name, e.g., 002_dual_ma")
    params: Optional[Dict[str, Any]] = Field(None, description="Custom parameter overrides")


class LiveInstanceInfo(BaseModel):
    """Live trading instance info schema."""
    id: str = Field(..., description="Unique instance ID")
    strategy_id: str = Field(..., description="Strategy directory name")
    strategy_name: str = Field("", description="Strategy name")
    status: str = Field("stopped", description="Status: running / stopped / error")
    pid: Optional[int] = Field(None, description="Process PID")
    error: Optional[str] = Field(None, description="Error message")
    params: Dict[str, Any] = Field(default_factory=dict, description="Runtime parameters")
    created_at: str = Field("", description="Creation time")
    started_at: Optional[str] = Field(None, description="Last start time")
    stopped_at: Optional[str] = Field(None, description="Last stop time")
    log_dir: Optional[str] = Field(None, description="Latest log directory")


class LiveInstanceListResponse(BaseModel):
    """Live trading instance list response schema."""
    total: int
    instances: List[LiveInstanceInfo]


class LiveBatchResponse(BaseModel):
    """Batch operation response schema."""
    success: int = 0
    failed: int = 0
    details: List[Dict[str, str]] = Field(default_factory=list)
