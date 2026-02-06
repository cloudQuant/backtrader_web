"""
策略相关Pydantic模型
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ParamSpec(BaseModel):
    """参数规格"""
    type: str = Field("float", description="参数类型: int/float/string/enum")
    default: Any = Field(..., description="默认值")
    min: Optional[float] = Field(None, description="最小值")
    max: Optional[float] = Field(None, description="最大值")
    options: Optional[List[Any]] = Field(None, description="枚举选项")
    description: Optional[str] = Field(None, description="参数描述")


class StrategyCreate(BaseModel):
    """创建策略请求"""
    name: str = Field(..., min_length=1, max_length=100, description="策略名称")
    description: Optional[str] = Field(None, description="策略描述")
    code: str = Field(..., description="策略代码")
    params: Dict[str, ParamSpec] = Field(default_factory=dict, description="参数定义")
    category: str = Field("custom", description="策略分类")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "双均线策略",
                "description": "基于快慢均线交叉的趋势策略",
                "code": "class MaCrossStrategy(bt.Strategy):\n    params = (('fast', 5), ('slow', 20))\n    ...",
                "params": {
                    "fast_period": {
                        "type": "int",
                        "default": 5,
                        "min": 2,
                        "max": 50,
                        "description": "快线周期"
                    },
                    "slow_period": {
                        "type": "int", 
                        "default": 20,
                        "min": 10,
                        "max": 200,
                        "description": "慢线周期"
                    }
                },
                "category": "trend"
            }
        }


class StrategyUpdate(BaseModel):
    """更新策略请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    code: Optional[str] = None
    params: Optional[Dict[str, ParamSpec]] = None
    category: Optional[str] = None


class StrategyResponse(BaseModel):
    """策略响应"""
    id: str = Field(..., description="策略ID")
    user_id: str = Field(..., description="用户ID")
    name: str = Field(..., description="策略名称")
    description: Optional[str] = Field(None, description="策略描述")
    code: str = Field(..., description="策略代码")
    params: Dict[str, ParamSpec] = Field(default_factory=dict, description="参数定义")
    category: str = Field(..., description="策略分类")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    
    class Config:
        from_attributes = True


class StrategyListResponse(BaseModel):
    """策略列表响应"""
    total: int
    items: List[StrategyResponse]


class StrategyTemplate(BaseModel):
    """策略模板"""
    id: str
    name: str
    description: str
    code: str
    params: Dict[str, ParamSpec]
    category: str
