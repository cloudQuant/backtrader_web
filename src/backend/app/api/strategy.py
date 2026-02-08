"""
策略API路由
"""
from functools import lru_cache
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.schemas.strategy import (
    StrategyCreate,
    StrategyUpdate,
    StrategyResponse,
    StrategyListResponse,
)
from app.services.strategy_service import StrategyService, get_template_by_id, get_strategy_readme
from app.api.deps import get_current_user

router = APIRouter()


@lru_cache
def get_strategy_service():
    return StrategyService()


@router.post("/", response_model=StrategyResponse, summary="创建策略")
async def create_strategy(
    strategy: StrategyCreate,
    current_user=Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
):
    """
    创建新策略
    
    - **name**: 策略名称
    - **description**: 策略描述
    - **code**: 策略代码
    - **params**: 默认参数
    - **category**: 策略分类
    """
    result = await service.create_strategy(current_user.sub, strategy)
    return result


@router.get("/", response_model=StrategyListResponse, summary="列出策略")
async def list_strategies(
    current_user=Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    category: str = Query(None, description="按分类筛选"),
):
    """列出用户的策略"""
    results = await service.list_strategies(
        current_user.sub, limit, offset, category
    )
    return results


@router.get("/templates", summary="获取策略模板")
async def get_templates(
    category: str = Query(None, description="按分类筛选"),
    service: StrategyService = Depends(get_strategy_service),
):
    """获取内置策略模板，支持按分类筛选"""
    templates = await service.get_templates()
    if category:
        templates = [t for t in templates if t.category == category]
    return {"templates": templates, "total": len(templates)}


@router.get("/templates/{template_id}", summary="获取策略模板详情")
async def get_template_detail(template_id: str):
    """获取单个策略模板的详细信息，包含代码和参数"""
    template = get_template_by_id(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="策略模板不存在")
    return template


@router.get("/templates/{template_id}/readme", summary="获取策略README文档")
async def get_template_readme(template_id: str):
    """获取策略的README.md文档内容（Markdown格式）"""
    readme = get_strategy_readme(template_id)
    if readme is None:
        raise HTTPException(status_code=404, detail="README不存在")
    return {"template_id": template_id, "content": readme}


@router.get("/templates/{template_id}/config", summary="获取策略配置")
async def get_template_config(template_id: str):
    """
    读取策略的config.yaml，返回完整配置：
    - strategy: 名称、描述、作者
    - params: 策略参数（含默认值）
    - data: 数据配置（标的代码、数据类型）
    - backtest: 回测配置（初始资金、手续费）
    """
    from app.services.strategy_service import STRATEGIES_DIR
    import yaml as _yaml

    config_path = STRATEGIES_DIR / template_id / "config.yaml"
    if not config_path.is_file():
        raise HTTPException(status_code=404, detail="策略配置文件不存在")

    with open(config_path, "r", encoding="utf-8") as f:
        config = _yaml.safe_load(f) or {}

    return {
        "strategy_id": template_id,
        "strategy": config.get("strategy", {}),
        "params": config.get("params", {}),
        "data": config.get("data", {}),
        "backtest": config.get("backtest", {}),
    }


@router.get("/{strategy_id}", response_model=StrategyResponse, summary="获取策略详情")
async def get_strategy(
    strategy_id: str,
    current_user=Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
):
    """获取策略详情"""
    strategy = await service.get_strategy(strategy_id)
    if strategy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="策略不存在",
        )
    return strategy


@router.put("/{strategy_id}", response_model=StrategyResponse, summary="更新策略")
async def update_strategy(
    strategy_id: str,
    strategy_update: StrategyUpdate,
    current_user=Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
):
    """更新策略"""
    result = await service.update_strategy(
        strategy_id, current_user.sub, strategy_update
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="策略不存在或无权修改",
        )
    return result


@router.delete("/{strategy_id}", summary="删除策略")
async def delete_strategy(
    strategy_id: str,
    current_user=Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service),
):
    """删除策略"""
    success = await service.delete_strategy(strategy_id, current_user.sub)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="策略不存在或无权删除",
        )
    return {"message": "删除成功"}
