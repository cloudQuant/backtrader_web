"""
策略版本管理 API 路由（完整版）

支持策略的版本控制、分支管理、回滚、对比
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
import logging
import asyncio
import difflib
from datetime import datetime

from app.schemas.strategy_version import (
    VersionCreate,
    VersionUpdate,
    VersionResponse,
    VersionListResponse,
    VersionComparisonRequest,
    VersionComparisonResponse,
    VersionRollbackRequest,
    BranchCreate,
    BranchResponse,
    BranchListResponse,
)
from app.services.strategy_version_service import VersionControlService
from app.api.deps import get_current_user
from app.websocket_manager import manager as ws_manager, MessageType

logger = logging.getLogger(__name__)

router = APIRouter()


def get_version_control_service():
    return VersionControlService()


# ==================== 策略版本 API ====================

@router.post("/versions", response_model=VersionResponse, summary="创建策略版本")
async def create_strategy_version(
    request: VersionCreate,
    current_user=Depends(get_current_user),
    service: VersionControlService = Depends(get_version_control_service),
):
    """
    创建策略新版本
    
    请求体：
    - strategy_id: 策略 ID
    - version_name: 版本名称（如 v1.0.0）
    - code: 策略代码
    - params: 默认参数
    - branch: 分支名称（默认 main）
    - tags: 版本标签（如 latest, stable）
    - changelog: 更新日志
    - is_default: 是否设为默认版本
    """
    version = await service.create_version(
        user_id=current_user.sub,
        strategy_id=request.strategy_id,
        version_name=request.version_name,
        code=request.code,
        params=request.params,
        branch=request.branch,
        tags=request.tags,
        changelog=request.changelog,
        is_default=request.is_default,
    )

    # 推送版本创建通知
    await ws_manager.send_to_task(f"strategy:{request.strategy_id}", {
        "type": MessageType.PROGRESS,
        "strategy_id": request.strategy_id,
        "version_id": version.id,
        "message": "策略版本已创建",
    })

    return version


@router.get("/strategies/{strategy_id}/versions", response_model=VersionListResponse, summary="获取策略版本列表")
async def list_strategy_versions(
    strategy_id: str,
    current_user=Depends(get_current_user),
    service: VersionControlService = Depends(get_version_control_service),
    branch: Optional[str] = Query(None, description="分支名称"),
    status: Optional[str] = Query(None, description="版本状态"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """获取策略的所有版本
    
    参数：
    - strategy_id: 策略 ID
    - branch: 分支筛选
    - status: 状态筛选
    - limit: 每页数量
    - offset: 偏移量
    """
    versions, total = await service.list_versions(
        user_id=current_user.sub,
        strategy_id=strategy_id,
        branch=branch,
        status=status,
        limit=limit,
        offset=offset,
    )

    return VersionListResponse(total=total, items=versions)


@router.get("/versions/{version_id}", response_model=VersionResponse, summary="获取策略版本详情")
async def get_strategy_version(
    version_id: str,
    current_user=Depends(get_current_user),
    service: VersionControlService = Depends(get_version_control_service),
):
    """获取策略版本详情"""
    version = await service.get_version(version_id)

    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="策略版本不存在"
        )

    # 检查权限
    if version.strategy_id != current_user.sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问该版本"
        )

    return version


@router.put("/versions/{version_id}", response_model=VersionResponse, summary="更新策略版本")
async def update_strategy_version(
    version_id: str,
    request: VersionUpdate,
    current_user=Depends(get_current_user),
    service: VersionControlService = Depends(get_version_control_service),
):
    """
    更新策略版本
    
    请求体：
    - code: 策略代码（可选）
    - params: 默认参数（可选）
    - description: 版本描述
    - tags: 版本标签（可选）
    - status: 版本状态（可选）
    """
    version = await service.update_version(
        version_id=version_id,
        user_id=current_user.sub,
        update_data=request.model_dump(exclude_none=True),
    )

    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="策略版本不存在或无权更新"
        )

    return version


@router.post("/versions/{version_id}/set-default", summary="设置为默认版本")
async def set_version_default(
    version_id: str,
    current_user=Depends(get_current_user),
    service: VersionControlService = Depends(get_version_control_service),
):
    """
    设置策略版本为默认版本
    
    每个分支只能有一个默认版本
    """
    success = await service.set_version_default(version_id, current_user.sub)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="策略版本不存在或无权设置"
        )

    return {"message": "已设置为默认版本"}


@router.post("/versions/{version_id}/activate", summary="激活策略版本")
async def activate_strategy_version(
    version_id: str,
    current_user=Depends(get_current_user),
    service: VersionControlService = Depends(get_version_control_service),
):
    """
    激活策略版本
    
    每个分支只能有一个活跃版本（当前使用）
    """
    success = await service.activate_version(version_id, current_user.sub)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="策略版本不存在或无权激活"
        )

    return {"message": "版本已激活"}


# ==================== 版本对比 API ====================

@router.post("/versions/compare", response_model=VersionComparisonResponse, summary="对比策略版本")
async def compare_strategy_versions(
    request: VersionComparisonRequest,
    current_user=Depends(get_current_user),
    service: VersionControlService = Depends(get_version_control_service),
):
    """
    对比两个策略版本
    
    请求体：
    - strategy_id: 策略 ID
    - from_version_id: 源版本 ID
    - to_version_id: 目标版本 ID
    - comparison_type: 对比类型（code, params, performance）
    """
    # comparison_type 在请求中指定，但服务会进行完整对比
    comparison = await service.compare_versions(
        user_id=current_user.sub,
        strategy_id=request.strategy_id,
        from_version_id=request.from_version_id,
        to_version_id=request.to_version_id,
    )

    # 推送对比完成通知
    await ws_manager.send_to_task(f"strategy:{request.strategy_id}", {
        "type": MessageType.PROGRESS,
        "strategy_id": request.strategy_id,
        "comparison_id": comparison.id,
        "message": "策略版本对比完成",
    })

    return comparison


# ==================== 版本回滚 API ====================

@router.post("/versions/rollback", response_model=VersionResponse, summary="回滚策略版本")
async def rollback_strategy_version(
    request: VersionRollbackRequest,
    current_user=Depends(get_current_user),
    service: VersionControlService = Depends(get_version_control_service),
):
    """
    回滚策略版本
    
    创建一个新的版本，包含目标版本的代码和参数
    
    请求体：
    - strategy_id: 策略 ID
    - target_version_id: 目标版本 ID
    - reason: 回滚原因
    """
    new_version = await service.rollback_version(
        user_id=current_user.sub,
        strategy_id=request.strategy_id,
        target_version_id=request.target_version_id,
        reason=request.reason,
    )

    # 推送回滚通知
    await ws_manager.send_to_task(f"strategy:{request.strategy_id}", {
        "type": MessageType.PROGRESS,
        "strategy_id": request.strategy_id,
        "version_id": new_version.id,
        "message": "策略版本已回滚",
    })

    return {
        "version_id": new_version.id,
        "version_name": new_version.version_name,
        "status": "rolled_back",
        "message": "策略版本已回滚",
    }


# ==================== 策略分支 API ====================

@router.post("/branches", response_model=BranchResponse, summary="创建策略分支")
async def create_strategy_branch(
    request: BranchCreate,
    current_user=Depends(get_current_user),
    service: VersionControlService = Depends(get_version_control_service),
):
    """
    创建策略分支
    
    请求体：
    - strategy_id: 策略 ID
    - branch_name: 分支名称（如 feature/new-indicator）
    - parent_branch: 父分支名称（如 main）
    
    分支类型：
    - main: 主分支
    - dev: 开发分支
    - feature/*: 功能分支
    - bugfix/*: 修复分支
    - release/*: 发布分支
    """
    # TODO: 实现创建分支
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="分支功能暂未实现"
    )

    # return BranchResponse(
    #     branch_id="branch-123",
    #     strategy_id=request.strategy_id,
    #     branch_name=request.branch_name,
    #     version_count=0,
    #     is_default=False,
    # )


@router.get("/strategies/{strategy_id}/branches", response_model=BranchListResponse, summary="获取策略分支列表")
async def list_strategy_branches(
    strategy_id: str,
    current_user=Depends(get_current_user),
    service: VersionControlService = Depends(get_version_control_service),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """获取策略的所有分支
    
    参数：
    - strategy_id: 策略 ID
    - limit: 每页数量
    - offset: 偏移量
    """
    # TODO: 实现列出分支
    # branches, total = await service.list_branches(
    #     user_id=current_user.sub,
    #     strategy_id=strategy_id,
    #     limit=limit,
    #     offset=offset,
    # )
    # return BranchListResponse(total=0, items=[])

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="分支功能暂未实现"
    )


# ==================== WebSocket 端点 ====================

@router.websocket("/ws/strategies/{strategy_id}")
async def strategy_version_websocket(
    websocket,
    strategy_id: str,
):
    """
    WebSocket 端点 - 策略版本实时推送
    
    推送内容：
    - 版本创建
    - 版本更新
    - 版本对比完成
    - 版本回滚
    - 分支更新
    
    连接 URL: ws://host/api/v1/strategy-versions/ws/strategies/{strategy_id}
    
    消息类型：
    - connected: 连接成功
    - version_created: 版本创建
    - version_updated: 版本更新
    - version_compared: 版本对比完成
    - version_rolled_back: 版本回滚
    - branch_created: 分支创建
    - branch_updated: 分支更新
    
    示例消息：
    {
        "type": "version_created",
        "strategy_id": "strategy-123",
        "version_id": "version-456",
        "data": {
            "version_name": "v1.0.0",
            "branch": "main",
            "created_at": "2024-01-01T00:00:00Z",
        }
    }
    """
    client_id = f"ws-version-client-{id(websocket)}"

    # 建立连接
    await ws_manager.connect(websocket, f"strategy:{strategy_id}", client_id)

    try:
        # 发送初始信息
        await ws_manager.send_to_task(f"strategy:{strategy_id}", {
            "type": MessageType.CONNECTED,
            "strategy_id": strategy_id,
            "message": "策略版本控制 WebSocket 连接成功",
        })

        # 保持连接
        while True:
            await asyncio.sleep(1)

            # 这里应该从版本控制服务获取最新数据
            # 并通过 WebSocket 推送
            # 暂时使用轮询方式，实际应用中应该使用事件驱动

    except Exception as e:
        logger.error(f"Strategy version WebSocket error: {e}")
        ws_manager.disconnect(websocket, f"strategy:{strategy_id}", client_id)
