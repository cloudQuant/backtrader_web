"""
参数优化 API 路由

提供:
- POST /submit  提交优化任务
- GET  /progress/{task_id}  查询优化进度
- GET  /results/{task_id}   获取优化结果
- POST /cancel/{task_id}    取消优化任务
- GET  /strategy-params/{strategy_id}  获取策略默认参数
"""
import logging
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.services.strategy_service import get_template_by_id
from app.services.param_optimization_service import (
    submit_optimization,
    get_optimization_progress,
    get_optimization_results,
    cancel_optimization,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ---- Schemas ----

class ParamRangeSpec(BaseModel):
    start: float
    end: float
    step: float
    type: str = "float"  # int or float


class OptimizationSubmitRequest(BaseModel):
    strategy_id: str
    param_ranges: Dict[str, ParamRangeSpec]
    n_workers: int = Field(default=4, ge=1, le=32)


class OptimizationSubmitResponse(BaseModel):
    task_id: str
    total_combinations: int
    message: str


# ---- Endpoints ----

@router.get("/strategy-params/{strategy_id}", summary="获取策略默认参数")
async def get_strategy_params(
    strategy_id: str,
    current_user=Depends(get_current_user),
):
    """返回策略的参数列表（名称、类型、默认值）"""
    tpl = get_template_by_id(strategy_id)
    if not tpl:
        raise HTTPException(status_code=404, detail=f"策略 {strategy_id} 不存在")

    params = []
    for name, spec in tpl.params.items():
        params.append({
            "name": name,
            "type": spec.type,
            "default": spec.default,
            "description": spec.description or name,
        })

    return {"strategy_id": strategy_id, "strategy_name": tpl.name, "params": params}


@router.post("/submit", response_model=OptimizationSubmitResponse, summary="提交优化任务")
async def submit_optimization_task(
    request: OptimizationSubmitRequest,
    current_user=Depends(get_current_user),
):
    """提交参数优化任务，返回 task_id"""
    from app.services.param_optimization_service import generate_param_grid

    # 验证策略
    tpl = get_template_by_id(request.strategy_id)
    if not tpl:
        raise HTTPException(status_code=404, detail=f"策略 {request.strategy_id} 不存在")

    # 构建 param_ranges dict
    param_ranges = {}
    for name, spec in request.param_ranges.items():
        param_ranges[name] = {
            "start": spec.start,
            "end": spec.end,
            "step": spec.step,
            "type": spec.type,
        }

    # 预计算组合数
    grid = generate_param_grid(param_ranges)
    if not grid:
        raise HTTPException(status_code=400, detail="参数网格为空，请检查参数范围")

    try:
        task_id = submit_optimization(
            strategy_id=request.strategy_id,
            param_ranges=param_ranges,
            n_workers=request.n_workers,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return OptimizationSubmitResponse(
        task_id=task_id,
        total_combinations=len(grid),
        message=f"优化任务已提交，共 {len(grid)} 个参数组合，使用 {request.n_workers} 个进程",
    )


@router.get("/progress/{task_id}", summary="查询优化进度")
async def get_progress(
    task_id: str,
    current_user=Depends(get_current_user),
):
    """返回优化任务的当前进度"""
    progress = get_optimization_progress(task_id)
    if not progress:
        raise HTTPException(status_code=404, detail="优化任务不存在")
    return progress


@router.get("/results/{task_id}", summary="获取优化结果")
async def get_results(
    task_id: str,
    current_user=Depends(get_current_user),
):
    """返回优化任务的完整结果"""
    results = get_optimization_results(task_id)
    if not results:
        raise HTTPException(status_code=404, detail="优化任务不存在")
    return results


@router.post("/cancel/{task_id}", summary="取消优化任务")
async def cancel_task(
    task_id: str,
    current_user=Depends(get_current_user),
):
    """取消正在运行的优化任务"""
    ok = cancel_optimization(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="优化任务不存在")
    return {"message": "已请求取消", "task_id": task_id}
