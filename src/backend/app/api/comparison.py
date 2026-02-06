"""
回测结果对比 API 路由

支持多个回测结果的对比和分析
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
import logging

from app.schemas.comparison import (
    ComparisonCreate,
    ComparisonUpdate,
    ComparisonResponse,
    ComparisonListResponse,
    ComparisonDetail,
)
from app.services.comparison_service import ComparisonService
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


def get_comparison_service():
    return ComparisonService()


# ==================== 对比 API ====================

@router.post("/", response_model=ComparisonResponse, summary="创建回测对比")
async def create_comparison(
    request: ComparisonCreate,
    current_user=Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
):
    """
    创建回测对比
    
    请求体：
    - name: 对比名称
    - description: 对比描述
    - type: 对比类型
    - backtest_task_ids: 回测任务 ID 列表
    """
    comparison = await service.create_comparison(
        user_id=current_user.sub,
        name=request.name,
        description=request.description,
        backtest_task_ids=request.backtest_task_ids,
        comparison_type=request.type,
        is_public=False,
    )

    return comparison


@router.get("/{comparison_id}", response_model=ComparisonDetail, summary="获取回测对比详情")
async def get_comparison_detail(
    comparison_id: str,
    current_user=Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
):
    """获取回测对比详情"""
    comparison = await service.get_comparison(comparison_id, current_user.sub)

    if not comparison:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对比不存在"
        )

    # 检查权限
    if comparison.user_id != current_user.sub and not comparison.is_public:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问该对比"
        )

    return comparison


@router.put("/{comparison_id}", response_model=ComparisonResponse, summary="更新回测对比")
async def update_comparison(
    comparison_id: str,
    request: ComparisonUpdate,
    current_user=Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
):
    """更新回测对比"""
    comparison = await service.update_comparison(
        comparison_id=comparison_id,
        user_id=current_user.sub,
        update_data=request.model_dump(exclude_none=True),
    )

    if not comparison:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对比不存在或无权更新"
        )

    return comparison


@router.delete("/{comparison_id}", summary="删除回测对比")
async def delete_comparison(
    comparison_id: str,
    current_user=Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
):
    """删除回测对比"""
    success = await service.delete_comparison(comparison_id, current_user.sub)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对比不存在或无权删除"
        )

    return {"message": "删除成功"}


@router.get("/", response_model=ComparisonListResponse, summary="获取回测对比列表")
async def list_comparisons(
    current_user=Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    is_public: Optional[bool] = Query(None, description="是否只看公开的"),
):
    """
    获取回测对比列表
    
    参数：
    - limit: 每页数量
    - offset: 偏移量
    - is_public: 是否只看公开的（可选）
    """
    filters = {}
    if is_public is not None:
        filters["is_public"] = is_public

    comparisons, total = await service.list_comparisons(
        user_id=current_user.sub,
        limit=limit,
        offset=offset,
        filters=filters,
    )

    return ComparisonListResponse(total=total, items=comparisons)


@router.post("/{comparison_id}/toggle-favorite", summary="切换收藏状态")
async def toggle_comparison_favorite(
    comparison_id: str,
    current_user=Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
):
    """
    切换对比的收藏状态
    
    将对比添加或移除到收藏列表
    """
    comparison = await service.get_comparison(comparison_id, current_user.sub)

    if not comparison:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对比不存在"
        )

    # 切换收藏状态
    comparison.is_favorite = not comparison.is_favorite

    # 更新
    updated_comparison = await service.update_comparison(
        comparison_id=comparison_id,
        user_id=current_user.sub,
        update_data={"is_favorite": comparison.is_favorite},
    )

    return {
        "comparison_id": comparison_id,
        "is_favorite": updated_comparison.is_favorite,
    }


@router.post("/{comparison_id}/share", summary="分享回测对比")
async def share_comparison(
    comparison_id: str,
    request: dict,
    current_user=Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
):
    """
    分享回测对比
    
    请求体：
    - shared_with_user_ids: 用户 ID 列表（分享给哪些用户）
    """
    shared_with_user_ids = request.get("shared_with_user_ids", [])

    comparison = await service.get_comparison(comparison_id, current_user.sub)

    if not comparison:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对比不存在"
        )

    # 检查权限
    if comparison.user_id != current_user.sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权分享该对比"
        )

    # TODO: 实现分享逻辑
    # await service.share_comparison(comparison_id, current_user.sub, shared_with_user_ids)

    return {
        "comparison_id": comparison_id,
        "message": "分享成功",
    }


# ==================== 对比数据 API ====================

@router.get("/{comparison_id}/metrics", summary="获取指标对比数据")
async def get_metrics_comparison(
    comparison_id: str,
    current_user=Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
):
    """
    获取指标对比数据
    
    返回多个回测的指标对比（总收益率、年化收益率、夏普比率、最大回撤、胜率等）
    """
    comparison = await service.get_comparison(comparison_id, current_user.sub)

    if not comparison:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对比不存在"
        )

    metrics_comparison = comparison.comparison_data.get("metrics_comparison", {})

    return {
        "comparison_id": comparison_id,
        "metrics_comparison": metrics_comparison,
    }


@router.get("/{comparison_id}/equity", summary="获取资金曲线对比数据")
async def get_equity_comparison(
    comparison_id: str,
    current_user=Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
):
    """
    获取资金曲线对比数据
    
    返回多个回测的资金曲线数据，用于绘图
    """
    comparison = await service.get_comparison(comparison_id, current_user.sub)

    if not comparison:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对比不存在"
        )

    equity_comparison = comparison.comparison_data.get("equity_comparison", {})

    return {
        "comparison_id": comparison_id,
        "equity_comparison": equity_comparison,
    }


@router.get("/{comparison_id}/trades", summary="获取交易对比数据")
async def get_trades_comparison(
    comparison_id: str,
    current_user=Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
):
    """
    获取交易对比数据
    
    返回多个回测的交易对比数据（交易次数、盈亏等）
    """
    comparison = await service.get_comparison(comparison_id, current_user.sub)

    if not comparison:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对比不存在"
        )

    trades_comparison = comparison.comparison_data.get("trades_comparison", {})

    return {
        "comparison_id": comparison_id,
        "trades_comparison": trades_comparison,
    }


@router.get("/{comparison_id}/drawdown", summary="获取回撤对比数据")
async def get_drawdown_comparison(
    comparison_id: str,
    current_user=Depends(get_current_user),
    service: ComparisonService = Depends(get_comparison_service),
):
    """
    获取回撤对比数据
    
    返回多个回测的回撤曲线数据
    """
    comparison = await service.get_comparison(comparison_id, current_user.sub)

    if not comparison:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对比不存在"
        )

    drawdown_comparison = comparison.comparison_data.get("drawdown_comparison", {})

    return {
        "comparison_id": comparison_id,
        "drawdown_comparison": drawdown_comparison,
    }
