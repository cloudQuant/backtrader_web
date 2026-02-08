"""
回测API路由
"""
from functools import lru_cache
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.schemas.backtest import (
    BacktestRequest,
    BacktestResponse,
    BacktestResult,
    BacktestListResponse,
    TaskStatus,
)
from app.services.backtest_service import BacktestService
from app.api.deps import get_current_user

router = APIRouter()


@lru_cache
def get_backtest_service():
    return BacktestService()


@router.post("/run", response_model=BacktestResponse, summary="运行回测")
async def run_backtest(
    request: BacktestRequest,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """
    提交回测任务
    
    - **strategy_id**: 策略ID
    - **symbol**: 股票代码
    - **start_date**: 开始日期
    - **end_date**: 结束日期
    - **initial_cash**: 初始资金
    - **commission**: 手续费率
    - **params**: 策略参数
    """
    result = await service.run_backtest(current_user.sub, request)
    return result


@router.get("/{task_id}", response_model=BacktestResult, summary="获取回测结果")
async def get_backtest_result(
    task_id: str,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """获取回测结果"""
    result = await service.get_result(task_id, user_id=current_user.sub)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回测结果不存在",
        )
    return result


@router.get("/{task_id}/status", summary="获取回测任务状态")
async def get_backtest_status(
    task_id: str,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """获取回测任务状态"""
    task_status = await service.get_task_status(task_id, user_id=current_user.sub)
    if task_status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在",
        )
    return {"task_id": task_id, "status": task_status}


@router.get("/", response_model=BacktestListResponse, summary="列出回测历史")
async def list_backtests(
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("created_at", description="排序字段: created_at/strategy_id/symbol"),
    sort_order: str = Query("desc", description="排序方向: asc/desc"),
):
    """列出用户的回测历史，支持排序"""
    results = await service.list_results(
        current_user.sub, limit, offset,
        sort_by=sort_by, sort_desc=(sort_order == "desc"),
    )
    return results


@router.post("/{task_id}/cancel", summary="取消回测任务")
async def cancel_backtest(
    task_id: str,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """取消运行中的回测任务"""
    success = await service.cancel_task(task_id, current_user.sub)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="任务不存在、无权操作或任务已完成",
        )
    return {"message": "任务已取消", "task_id": task_id}


@router.delete("/{task_id}", summary="删除回测结果")
async def delete_backtest(
    task_id: str,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """删除回测结果"""
    success = await service.delete_result(task_id, current_user.sub)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回测结果不存在或无权删除",
        )
    return {"message": "删除成功"}
