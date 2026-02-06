"""
策略API路由
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.schemas.strategy import (
    StrategyCreate,
    StrategyUpdate,
    StrategyResponse,
    StrategyListResponse,
)
from app.services.strategy_service import StrategyService
from app.api.deps import get_current_user

router = APIRouter()


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
    service: StrategyService = Depends(get_strategy_service),
):
    """获取内置策略模板"""
    templates = await service.get_templates()
    return {"templates": templates}


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
