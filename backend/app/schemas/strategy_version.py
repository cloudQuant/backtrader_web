"""
策略版本管理相关的 Pydantic 模型
"""
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class VersionCreate(BaseModel):
    """创建策略版本请求"""
    strategy_id: str = Field(..., min_length=1, max_length=100, description="策略 ID")
    version_name: str = Field(..., min_length=1, max_length=50, description="版本名称（如 v1.0.0）")
    code: str = Field(..., min_length=1, description="策略代码")
    params: Optional[Dict[str, Any]] = Field(None, description="默认参数")
    branch: str = Field("main", min_length=1, max_length=50, description="分支名称")
    tags: Optional[List[str]] = Field(None, description="版本标签")
    changelog: Optional[str] = Field(None, description="变更日志")
    is_default: bool = Field(False, description="是否设为默认版本")


class VersionUpdate(BaseModel):
    """更新策略版本请求"""
    code: Optional[str] = Field(None, min_length=1, description="策略代码")
    params: Optional[Dict[str, Any]] = Field(None, description="默认参数")
    description: Optional[str] = Field(None, description="版本描述")
    tags: Optional[List[str]] = Field(None, description="版本标签")
    status: Optional[str] = Field(None, description="版本状态：draft, stable, deprecated, archived")


class VersionResponse(BaseModel):
    """策略版本响应"""
    id: str = Field(..., description="版本 ID")
    strategy_id: str = Field(..., description="策略 ID")
    version_number: int = Field(..., ge=1, description="版本号（1, 2, 3, ...）")
    version_name: str = Field(..., description="版本名称")
    branch: str = Field(..., description="分支名称")
    status: str = Field(..., description="版本状态：draft, stable, deprecated, archived")
    tags: List[str] = Field(..., description="版本标签")
    description: Optional[str] = Field(None, description="版本描述")
    is_active: bool = Field(..., description="是否为活跃版本")
    is_default: bool = Field(..., description="是否为默认版本")
    is_current: bool = Field(..., description="是否为当前版本（分支头部）")
    parent_version_id: Optional[str] = Field(None, description="父版本 ID")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")


class VersionListResponse(BaseModel):
    """策略版本列表响应"""
    total: int = Field(..., ge=0, description="总数量")
    items: List[VersionResponse] = Field(..., description="版本列表")


class VersionComparisonRequest(BaseModel):
    """版本对比请求"""
    strategy_id: str = Field(..., description="策略 ID")
    from_version_id: str = Field(..., description="源版本 ID")
    to_version_id: str = Field(..., description="目标版本 ID")
    comparison_type: str = Field("code", description="对比类型：code, params, performance")


class VersionComparisonResponse(BaseModel):
    """版本对比响应"""
    comparison_id: str = Field(..., description="对比 ID")
    strategy_id: str = Field(..., description="策略 ID")
    from_version_id: str = Field(..., description="源版本 ID")
    to_version_id: str = Field(..., description="目标版本 ID")
    code_diff: Optional[str] = Field(None, description="代码差异（Unified diff）")
    params_diff: Optional[Dict[str, Any]] = Field(None, description="参数差异")
    performance_diff: Optional[Dict[str, Any]] = Field(None, description="性能差异（需要回测结果）")
    created_at: datetime = Field(..., description="对比创建时间")


class VersionRollbackRequest(BaseModel):
    """版本回滚请求"""
    strategy_id: str = Field(..., description="策略 ID")
    target_version_id: str = Field(..., description="目标版本 ID")
    reason: str = Field(..., description="回滚原因")


class BranchCreate(BaseModel):
    """创建策略分支请求"""
    strategy_id: str = Field(..., description="策略 ID")
    branch_name: str = Field(..., min_length=1, max_length=50, pattern=r'^[a-zA-Z0-9/_-]+$', description="分支名称（如 feature/new-indicator）")
    parent_branch: Optional[str] = Field(None, description="父分支名称（如 main）")


class BranchResponse(BaseModel):
    """策略分支响应"""
    branch_id: str = Field(..., description="分支 ID")
    strategy_id: str = Field(..., description="策略 ID")
    branch_name: str = Field(..., description="分支名称")
    parent_branch: Optional[str] = Field(None, description="父分支")
    version_count: int = Field(..., ge=0, description="分支上的版本数量")
    last_version_id: Optional[str] = Field(None, description="分支最新版本 ID")
    is_default: bool = Field(..., description="是否为默认分支")
    created_at: datetime = Field(..., description="创建时间")


class BranchListResponse(BaseModel):
    """策略分支列表响应"""
    total: int = Field(..., ge=0, description="总数量")
    items: List[BranchResponse] = Field(..., description="分支列表")
