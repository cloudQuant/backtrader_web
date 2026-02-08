"""
回测 API 路由（优化版）

集成了参数优化、报告导出、WebSocket 实时推送
"""
from functools import lru_cache
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response, WebSocket, WebSocketDisconnect

from app.schemas.backtest_enhanced import (
    BacktestRequest,
    BacktestResponse,
    BacktestResult,
    BacktestListResponse,
    OptimizationRequest,
    OptimizationResult,
    TaskStatus,
)
from app.services.backtest_service import BacktestService
from app.services.optimization_service import OptimizationService
from app.services.report_service import ReportService
from app.api.deps import get_current_user
from app.websocket_manager import manager as ws_manager

router = APIRouter()


@lru_cache
def get_backtest_service():
    return BacktestService()


@lru_cache
def get_optimization_service():
    return OptimizationService()


@lru_cache
def get_report_service():
    return ReportService()


# ==================== 回测 API ====================

@router.post("/run", response_model=BacktestResponse, summary="运行回测")
async def run_backtest(
    request: BacktestRequest,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """
    提交回测任务（增强版）
    
    使用了增强的输入验证和权限控制
    """
    result = await service.run_backtest(current_user.sub, request)

    # 通知 WebSocket 客户端（如果有连接）
    await ws_manager.send_to_task(request.strategy_id, {
        "type": "task_created",
        "task_id": result.task_id,
        "status": "pending",
    })

    return result


@router.get("/{task_id}", response_model=BacktestResult, summary="获取回测结果")
async def get_backtest_result(
    task_id: str,
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
):
    """获取回测结果"""
    result = await service.get_result(task_id, user_id=current_user.sub)
    if not result:
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
    task_status = await service.get_task_status(task_id)
    if not task_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在",
        )
    return {"task_id": task_id, "status": task_status.value}


@router.get("/", response_model=BacktestListResponse, summary="列出回测历史")
async def list_backtests(
    current_user=Depends(get_current_user),
    service: BacktestService = Depends(get_backtest_service),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    sort_by: str = Query("created_at", description="排序字段：created_at/sharpe_ratio/total_return"),
    sort_order: str = Query("desc", description="排序方向：asc/desc"),
):
    """列出用户的回测历史（增强版，支持排序）"""
    results = await service.list_results(
        current_user.sub, limit, offset, sort_by, sort_order
    )
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


# ==================== 参数优化 API ====================

@router.post("/optimization/grid", response_model=OptimizationResult, summary="网格搜索优化")
async def grid_search_optimization(
    request: OptimizationRequest,
    current_user=Depends(get_current_user),
    service: OptimizationService = Depends(get_optimization_service),
):
    """
    网格搜索优化

    遍历所有参数组合，找到最优参数
    """
    if request.method != "grid":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="网格搜索需要 method=grid",
        )

    result = await service.run_grid_search(current_user.sub, request)
    return result


@router.post("/optimization/bayesian", response_model=OptimizationResult, summary="贝叶斯优化")
async def bayesian_optimization(
    request: OptimizationRequest,
    current_user=Depends(get_current_user),
    service: OptimizationService = Depends(get_optimization_service),
):
    """
    贝叶斯优化（智能优化）

    使用 Optuna 进行贝叶斯优化，找到最优参数
    """
    if request.method != "bayesian":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="贝叶斯优化需要 method=bayesian",
        )

    result = await service.run_bayesian_optimization(current_user.sub, request)
    return result


# ==================== 回测报告导出 API ====================

@router.get("/{task_id}/report/html", summary="导出 HTML 报告")
async def get_html_report(
    task_id: str,
    current_user=Depends(get_current_user),
    backtest_service: BacktestService = Depends(get_backtest_service),
    report_service: ReportService = Depends(get_report_service),
):
    """
    导出 HTML 格式的回测报告
    """
    result = await backtest_service.get_result(task_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回测结果不存在",
        )

    # 获取策略信息
    # TODO: 从策略表获取
    strategy = {
        'name': f"策略 {result.strategy_id}",
        'description': '自定义策略',
    }

    # 生成 HTML 报告
    html_content = await report_service.generate_html_report(
        result.model_dump(mode='python'),
        strategy
    )

    return Response(
        content=html_content,
        media_type="text/html",
        headers={"Content-Disposition": "attachment; filename=backtest.html"}
    )


@router.get("/{task_id}/report/pdf", summary="导出 PDF 报告")
async def get_pdf_report(
    task_id: str,
    current_user=Depends(get_current_user),
    backtest_service: BacktestService = Depends(get_backtest_service),
    report_service: ReportService = Depends(get_report_service),
):
    """
    导出 PDF 格式的回测报告
    """
    result = await backtest_service.get_result(task_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回测结果不存在",
        )

    # 获取策略信息
    strategy = {
        'name': f"策略 {result.strategy_id}",
        'description': '自定义策略',
    }

    # 生成 PDF 报告
    try:
        pdf_bytes = await report_service.generate_pdf_report(
            result.model_dump(mode='python'),
            strategy
        )

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=backtest.pdf"}
        )
    except ImportError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF 生成功能未启用，需要安装 weasyprint: {e}"
        )


@router.get("/{task_id}/report/excel", summary="导出 Excel 报告")
async def get_excel_report(
    task_id: str,
    current_user=Depends(get_current_user),
    backtest_service: BacktestService = Depends(get_backtest_service),
    report_service: ReportService = Depends(get_report_service),
):
    """
    导出 Excel 格式的回测报告
    """
    result = await backtest_service.get_result(task_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回测结果不存在",
        )

    # 获取策略信息
    strategy = {
        'name': f"策略 {result.strategy_id}",
        'description': '自定义策略',
    }

    # 生成 Excel 报告
    try:
        excel_bytes = await report_service.generate_excel_report(
            result.model_dump(mode='python'),
            strategy
        )

        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=backtest.xlsx"}
        )
    except ImportError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Excel 导出功能未启用，需要安装 pandas 和 openpyxl: {e}"
        )


# ==================== WebSocket 端点 ====================

@router.websocket("/ws/backtest/{task_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    task_id: str,
):
    """
    WebSocket 端点 - 实时推送回测进度和日志

    Args:
        websocket: WebSocket 连接对象
        task_id: 回测任务 ID

    使用方式：
        - 客户端连接：ws://host/api/v1/backtest/ws/backtest/{task_id}
        - 接收消息：JSON 格式，包含 type, task_id, message, data
        - 消息类型：
            - connected: 连接成功
            - progress: 进度更新（包含进度百分比、当前结果）
            - log: 日志消息
            - completed: 回测完成（包含完整结果）
            - failed: 回测失败（包含错误信息）
    """
    import json

    # 生成唯一的客户端 ID
    client_id = f"client_{id(websocket)}"

    # 建立连接
    await ws_manager.connect(websocket, task_id, client_id)

    try:
        # 轮询任务状态并推送
        backtest_service = get_backtest_service()
        import asyncio

        while True:
            # 检查任务状态
            task_status = await backtest_service.get_task_status(task_id)
            result = await backtest_service.get_result(task_id)

            # 发送进度更新
            if task_status == TaskStatus.RUNNING:
                progress = await ws_manager.get_connection_count(task_id)
                await ws_manager.send_to_task(task_id, {
                    "type": "progress",
                    "task_id": task_id,
                    "progress": min(progress * 10, 100),
                    "data": result.model_dump(mode='python') if result else {},
                })

            # 发送完成消息
            elif task_status == TaskStatus.COMPLETED and result:
                await ws_manager.send_to_task(task_id, {
                    "type": "completed",
                    "task_id": task_id,
                    "result": result.model_dump(mode='python'),
                })
                break

            # 发送失败消息
            elif task_status == TaskStatus.FAILED:
                await ws_manager.send_to_task(task_id, {
                    "type": "failed",
                    "task_id": task_id,
                    "error": result.error_message if result else "Unknown error",
                })
                break

            # 如果任务已完成或失败，退出循环
            if task_status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                break

            # 等待 1 秒后再检查
            await asyncio.sleep(1)

    except WebSocketDisconnect:
        # 正常断开
        ws_manager.disconnect(websocket, task_id, client_id)
    except Exception as e:
        # 异常断开
        import logging
        logging.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket, task_id, client_id)
