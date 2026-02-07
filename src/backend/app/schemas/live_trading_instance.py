"""
实盘交易实例 Pydantic 模型
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class LiveInstanceCreate(BaseModel):
    """添加实盘策略请求"""
    strategy_id: str = Field(..., description="策略目录名，如 002_dual_ma")
    params: Optional[Dict[str, Any]] = Field(None, description="自定义参数覆盖")


class LiveInstanceInfo(BaseModel):
    """实盘策略实例信息"""
    id: str = Field(..., description="实例唯一ID")
    strategy_id: str = Field(..., description="策略目录名")
    strategy_name: str = Field("", description="策略名称")
    status: str = Field("stopped", description="状态: running / stopped / error")
    pid: Optional[int] = Field(None, description="进程PID")
    error: Optional[str] = Field(None, description="错误信息")
    params: Dict[str, Any] = Field(default_factory=dict, description="运行参数")
    created_at: str = Field("", description="添加时间")
    started_at: Optional[str] = Field(None, description="最近启动时间")
    stopped_at: Optional[str] = Field(None, description="最近停止时间")
    log_dir: Optional[str] = Field(None, description="最新日志目录")


class LiveInstanceListResponse(BaseModel):
    """实盘策略实例列表"""
    total: int
    instances: List[LiveInstanceInfo]


class LiveBatchResponse(BaseModel):
    """批量操作响应"""
    success: int = 0
    failed: int = 0
    details: List[Dict[str, str]] = Field(default_factory=list)
