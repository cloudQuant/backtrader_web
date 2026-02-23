"""
Strategy versioning schemas.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class VersionCreate(BaseModel):
    """Strategy version creation request schema."""
    strategy_id: str = Field(..., min_length=1, max_length=100, description="Strategy ID")
    version_name: str = Field(..., min_length=1, max_length=50, description="Version name (e.g., v1.0.0)")
    code: str = Field(..., min_length=1, description="Strategy code")
    params: Optional[Dict[str, Any]] = Field(None, description="Default parameters")
    branch: str = Field("main", min_length=1, max_length=50, description="Branch name")
    tags: Optional[List[str]] = Field(None, description="Version tags")
    changelog: Optional[str] = Field(None, description="Change log")
    is_default: bool = Field(False, description="Set as default version")


class VersionUpdate(BaseModel):
    """Strategy version update request schema."""
    code: Optional[str] = Field(None, min_length=1, description="Strategy code")
    params: Optional[Dict[str, Any]] = Field(None, description="Default parameters")
    description: Optional[str] = Field(None, description="Version description")
    tags: Optional[List[str]] = Field(None, description="Version tags")
    status: Optional[str] = Field(None, description="Version status: draft, stable, deprecated, archived")
    changelog: Optional[str] = Field(None, description="Change log (optional, usually filled when publishing stable)")


class VersionResponse(BaseModel):
    """Strategy version response schema."""
    id: str = Field(..., description="Version ID")
    strategy_id: str = Field(..., description="Strategy ID")
    version_number: int = Field(..., ge=1, description="Version number (1, 2, 3, ...)")
    version_name: str = Field(..., description="Version name")
    branch: str = Field(..., description="Branch name")
    status: str = Field(..., description="Version status: draft, stable, deprecated, archived")
    tags: List[str] = Field(..., description="Version tags")
    description: Optional[str] = Field(None, description="Version description")
    is_active: bool = Field(..., description="Whether the version is active")
    is_default: bool = Field(..., description="Whether the version is default")
    is_current: bool = Field(..., description="Whether the version is current (branch head)")
    parent_version_id: Optional[str] = Field(None, description="Parent version ID")
    created_at: datetime = Field(..., description="Creation time")
    updated_at: datetime = Field(..., description="Update time")


class VersionListResponse(BaseModel):
    """Strategy version list response schema."""
    total: int = Field(..., ge=0, description="Total count")
    items: List[VersionResponse] = Field(..., description="Version list")


class VersionComparisonRequest(BaseModel):
    """Version comparison request schema."""
    strategy_id: str = Field(..., description="Strategy ID")
    from_version_id: str = Field(..., description="Source version ID")
    to_version_id: str = Field(..., description="Target version ID")
    comparison_type: str = Field("code", description="Comparison type: code, params, performance")


# Alias for service layer compatibility
VersionComparisonCreate = VersionComparisonRequest


class VersionComparisonResponse(BaseModel):
    """Version comparison response schema."""
    comparison_id: str = Field(..., description="Comparison ID")
    strategy_id: str = Field(..., description="Strategy ID")
    from_version_id: str = Field(..., description="Source version ID")
    to_version_id: str = Field(..., description="Target version ID")
    code_diff: Optional[str] = Field(None, description="Code difference (Unified diff)")
    params_diff: Optional[Dict[str, Any]] = Field(None, description="Parameter difference")
    performance_diff: Optional[Dict[str, Any]] = Field(None, description="Performance difference (requires backtest results)")
    created_at: datetime = Field(..., description="Comparison creation time")


class VersionRollbackRequest(BaseModel):
    """Version rollback request schema."""
    strategy_id: str = Field(..., description="Strategy ID")
    target_version_id: str = Field(..., description="Target version ID")
    reason: str = Field(..., description="Rollback reason")


# Alias for service layer compatibility
VersionRollbackCreate = VersionRollbackRequest


class BranchCreate(BaseModel):
    """Strategy branch creation request schema."""
    strategy_id: str = Field(..., description="Strategy ID")
    branch_name: str = Field(..., min_length=1, max_length=50, pattern=r'^[a-zA-Z0-9/_-]+$', description="Branch name (e.g., feature/new-indicator)")
    parent_branch: Optional[str] = Field(None, description="Parent branch name (e.g., main)")


class BranchResponse(BaseModel):
    """Strategy branch response schema."""
    branch_id: str = Field(..., description="Branch ID")
    strategy_id: str = Field(..., description="Strategy ID")
    branch_name: str = Field(..., description="Branch name")
    parent_branch: Optional[str] = Field(None, description="Parent branch")
    version_count: int = Field(..., ge=0, description="Number of versions on the branch")
    last_version_id: Optional[str] = Field(None, description="Latest version ID on the branch")
    is_default: bool = Field(..., description="Whether the branch is default")
    created_at: datetime = Field(..., description="Creation time")


class BranchListResponse(BaseModel):
    """Strategy branch list response schema."""
    total: int = Field(..., ge=0, description="Total count")
    items: List[BranchResponse] = Field(..., description="Branch list")
