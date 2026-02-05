"""
监控告警 API 路由

提供完整的告警管理、规则配置、实时通知功能
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
import logging

from app.schemas.monitoring import (
    AlertCreate,
    AlertUpdate,
    AlertRuleCreate,
    AlertRuleUpdate,
    AccountAlertConfig,
    PositionAlertConfig,
    StrategyAlertConfig,
    WebhookConfig,
    AlertResponse,
    AlertRuleResponse,
    AlertListResponse,
    NotificationConfig,
)
from app.services.monitoring_service import MonitoringService
from app.api.deps import get_current_user
from app.websocket_manager import manager as ws_manager, MessageType

logger = logging.getLogger(__name__)

router = APIRouter()


def get_monitoring_service():
    return MonitoringService()


# ==================== 告警规则 API ====================

@router.post("/rules", response_model=AlertRuleResponse, summary="创建告警规则")
async def create_alert_rule(
    request: AlertRuleCreate,
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
):
    """
    创建告警规则
    
    请求体：
    - name: 规则名称
    - description: 规则描述
    - alert_type: 告警类型
    - severity: 告警级别
    - trigger_type: 触发类型
    - trigger_config: 触发配置
    - notification_enabled: 是否启用通知
    - notification_channels: 通知渠道
    """
    rule = await service.create_alert_rule(
        user_id=current_user.sub,
        name=request.name,
        description=request.description,
        alert_type=request.alert_type,
        severity=request.severity,
        trigger_type=request.trigger_type,
        trigger_config=request.trigger_config,
        notification_enabled=request.notification_enabled,
        notification_channels=request.notification_channels,
    )

    return rule


@router.get("/rules", response_model=AlertRuleListResponse, summary="获取告警规则列表")
async def list_alert_rules(
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
    alert_type: Optional[str] = Query(None, description="告警类型"),
    severity: Optional[str] = Query(None, description="告警级别"),
    is_active: Optional[bool] = Query(None, description="是否活跃"),
):
    """获取用户的告警规则列表"""
    rules, total = await service.list_alert_rules(
        user_id=current_user.sub,
        alert_type=alert_type,
        severity=severity,
        is_active=is_active,
    )

    return AlertRuleListResponse(total=total, items=rules)


@router.get("/rules/{rule_id}", response_model=AlertRuleResponse, summary="获取告警规则详情")
async def get_alert_rule(
    rule_id: str,
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
):
    """获取告警规则详情"""
    # TODO: 实现获取规则详情
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="暂未实现"
    )


@router.put("/rules/{rule_id}", response_model=AlertRuleResponse, summary="更新告警规则")
async def update_alert_rule(
    rule_id: str,
    request: AlertRuleUpdate,
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
):
    """更新告警规则"""
    rule = await service.update_alert_rule(
        rule_id=rule_id,
        user_id=current_user.sub,
        name=request.name,
        description=request.description,
        severity=request.severity,
        notification_enabled=request.notification_enabled,
        notification_channels=request.notification_channels,
        is_active=request.is_active,
    )

    return rule


@router.delete("/rules/{rule_id}", summary="删除告警规则")
async def delete_alert_rule(
    rule_id: str,
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
):
    """删除告警规则"""
    success = await service.delete_alert_rule(rule_id, current_user.sub)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="告警规则不存在或无权删除"
        )

    return {"message": "告警规则已删除"}


# ==================== 告警 API ====================

@router.get("/", response_model=AlertListResponse, summary="获取告警列表")
async def list_alerts(
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
    alert_type: Optional[str] = Query(None, description="告警类型"),
    severity: Optional[str] = Query(None, description="告警级别"),
    status: Optional[str] = Query(None, description="告警状态"),
    is_read: Optional[bool] = Query(None, description="是否已读"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """获取告警列表"""
    alerts, total = await service.list_alerts(
        user_id=current_user.sub,
        alert_type=alert_type,
        severity=severity,
        status=status,
        is_read=is_read,
        limit=limit,
        offset=offset,
    )

    return AlertListResponse(total=total, items=alerts)


@router.get("/{alert_id}", response_model=AlertResponse, summary="获取告警详情")
async def get_alert(
    alert_id: str,
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
):
    """获取告警详情"""
    # TODO: 实现获取告警详情
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="暂未实现"
    )


@router.put("/{alert_id}/read", summary="标记告警为已读")
async def mark_alert_read(
    alert_id: str,
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
):
    """标记告警为已读"""
    success = await service.mark_alert_read(alert_id, current_user.sub)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="告警不存在或无权标记"
        )

    return {"message": "告警已标记为已读"}


@router.put("/{alert_id}/resolve", summary="解决告警")
async def resolve_alert(
    alert_id: str,
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
):
    """解决告警"""
    success = await service.resolve_alert(alert_id, current_user.sub)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="告警不存在或无权解决"
        )

    return {"message": "告警已解决"}


@router.put("/{alert_id}/acknowledge", summary="确认告警")
async def acknowledge_alert(
    alert_id: str,
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
):
    """确认告警"""
    success = await service.acknowledge_alert(alert_id, current_user.sub)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="告警不存在或无权确认"
        )

    return {"message": "告警已确认"}


# ==================== 告警统计 API ====================

@router.get("/statistics/summary", summary="获取告警统计摘要")
async def get_alert_summary(
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
):
    """获取告警统计摘要"""
    # TODO: 实现告警统计
    summary = {
        "total_alerts": 0,
        "by_type": {},
        "by_severity": {},
        "recent": [],
    }

    return summary


@router.get("/statistics/by-type", summary="按类型获取告警统计")
async def get_alerts_by_type(
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
    start_date: str = Query(..., description="开始日期"),
    end_date: str = Query(..., description="结束日期"),
):
    """按类型获取告警统计"""
    # TODO: 实现按类型统计
    from datetime import datetime
    try:
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"日期格式错误: {e}"
        )

    stats = {
        "start_date": start_date,
        "end_date": end_date,
        "by_type": {},
    }

    return stats


# ==================== WebSocket 端点 ====================

@router.websocket("/ws/alerts")
async def alerts_websocket(
    websocket,
):
    """
    WebSocket 端点 - 告警实时推送
    
    推送内容：
    - 新告警创建
    - 告警状态更新
    - 告警解决通知
    - 告警统计更新
    
    连接 URL: ws://host/api/v1/monitoring/ws/alerts
    
    消息类型：
    - connected: 连接成功
    - alert_created: 新告警
    - alert_updated: 告警更新
    - alert_resolved: 告警解决
    - alert_acknowledged: 告警确认
    - stats_update: 统计更新
    """
    client_id = f"ws-alerts-client-{id(websocket)}"

    # 建立连接
    await ws_manager.connect(websocket, "alerts:global", client_id)

    try:
        # 发送初始信息
        await ws_manager.send_to_task("alerts:global", {
            "type": MessageType.CONNECTED,
            "message": "告警监控 WebSocket 连接成功",
        })

        # 保持连接
        while True:
            await asyncio.sleep(1)

            # 这里应该从监控服务获取最新告警
            # 并通过 WebSocket 推送
            # 暂时使用轮询方式，实际应用中应该使用事件驱动

    except Exception as e:
        logger.error(f"Alerts WebSocket error: {e}")
        ws_manager.disconnect(websocket, "alerts:global", client_id)
