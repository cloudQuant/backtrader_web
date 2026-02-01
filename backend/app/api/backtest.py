"""
回测API路由
"""
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
    result = await service.get_result(task_id)
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
    status = await service.get_task_status(task_id)
    if status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在",
        )
    return {"task_id": task_id, "status": status}


@router.get("/", response_model=BacktestListResponse, summary="列出回测历史")
async def list_backtests(
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """列出用户的回测历史"""
    results = await service.list_results(current_user.sub, limit, offset)
    return results


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
