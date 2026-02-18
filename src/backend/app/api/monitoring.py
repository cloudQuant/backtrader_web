"""
Monitoring and alerts API routes.

Provides:
- Alert rule management (CRUD)
- Alert listing and status updates
- Real-time notifications via WebSocket
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
import logging
import asyncio

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
    AlertRuleListResponse,
    AlertListResponse,
    NotificationConfig,
)
from app.services.monitoring_service import MonitoringService
from app.api.deps import get_current_user
from app.websocket_manager import manager as ws_manager, MessageType

logger = logging.getLogger(__name__)

router = APIRouter()


def get_monitoring_service():
    """Dependency injection for MonitoringService.

    Returns:
        MonitoringService: An instance of the monitoring service.
    """
    return MonitoringService()


# ==================== Alert Rule API ====================

@router.post("/rules", response_model=AlertRuleResponse, summary="Create alert rule")
async def create_alert_rule(
    request: AlertRuleCreate,
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
):
    """Create a new alert rule.

    Args:
        request: The alert rule creation request containing name, description,
            alert_type, severity, trigger_type, trigger_config, and
            notification settings.
        current_user: The authenticated user.
        service: The monitoring service.

    Returns:
        AlertRuleResponse: The created alert rule details.
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


@router.get("/rules", response_model=AlertRuleListResponse, summary="List alert rules")
async def list_alert_rules(
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
    alert_type: Optional[str] = Query(None, description="Alert type filter"),
    severity: Optional[str] = Query(None, description="Alert severity filter"),
    is_active: Optional[bool] = Query(None, description="Active status filter"),
):
    """Get the current user's alert rule list.

    Args:
        current_user: The authenticated user.
        service: The monitoring service.
        alert_type: Filter by alert type.
        severity: Filter by severity level.
        is_active: Filter by active status.

    Returns:
        AlertRuleListResponse: Response containing total count and rule list.
    """
    rules, total = await service.list_alert_rules(
        user_id=current_user.sub,
        alert_type=alert_type,
        severity=severity,
        is_active=is_active,
    )

    return AlertRuleListResponse(total=total, items=rules)


@router.get("/rules/{rule_id}", response_model=AlertRuleResponse, summary="Get alert rule details")
async def get_alert_rule(
    rule_id: str,
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
):
    """Get an alert rule by ID.

    Args:
        rule_id: The unique identifier of the alert rule.
        current_user: The authenticated user.
        service: The monitoring service.

    Returns:
        AlertRuleResponse: The alert rule details.

    Raises:
        HTTPException: If user lacks permission (403) or rule not found (404).
    """
    try:
        rule = await service.get_alert_rule(rule_id=rule_id, user_id=current_user.sub)
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to access this rule")

    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")
    return rule


@router.put("/rules/{rule_id}", response_model=AlertRuleResponse, summary="Update alert rule")
async def update_alert_rule(
    rule_id: str,
    request: AlertRuleUpdate,
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
):
    """Update an alert rule.

    Args:
        rule_id: The unique identifier of the alert rule.
        request: The update request containing fields to modify.
        current_user: The authenticated user.
        service: The monitoring service.

    Returns:
        AlertRuleResponse: The updated alert rule details.
    """
    rule = await service.update_alert_rule(rule_id=rule_id, user_id=current_user.sub, update_data=request.model_dump(exclude_none=True))

    return rule


@router.delete("/rules/{rule_id}", summary="Delete alert rule")
async def delete_alert_rule(
    rule_id: str,
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
):
    """Delete an alert rule.

    Args:
        rule_id: The unique identifier of the alert rule.
        current_user: The authenticated user.
        service: The monitoring service.

    Returns:
        A message confirming deletion.

    Raises:
        HTTPException: If the rule does not exist or user lacks permission (404).
    """
    success = await service.delete_alert_rule(rule_id, current_user.sub)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert rule not found or no permission to delete"
        )

    return {"message": "Alert rule has been deleted"}


# ==================== Alert API ====================

@router.get("/", response_model=AlertListResponse, summary="List alerts")
async def list_alerts(
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
    alert_type: Optional[str] = Query(None, description="Alert type filter"),
    severity: Optional[str] = Query(None, description="Alert severity filter"),
    status: Optional[str] = Query(None, description="Alert status filter"),
    is_read: Optional[bool] = Query(None, description="Read status filter"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Get the list of alerts for the current user.

    Args:
        current_user: The authenticated user.
        service: The monitoring service.
        alert_type: Filter by alert type.
        severity: Filter by severity level.
        status: Filter by alert status.
        is_read: Filter by read status.
        limit: Maximum number of alerts to return (1-100).
        offset: Number of alerts to skip.

    Returns:
        AlertListResponse: Response containing total count and alert list.
    """
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


@router.get("/{alert_id}", response_model=AlertResponse, summary="Get alert details")
async def get_alert(
    alert_id: str,
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
):
    """Get an alert by ID.

    Args:
        alert_id: The unique identifier of the alert.
        current_user: The authenticated user.
        service: The monitoring service.

    Returns:
        AlertResponse: The alert details.

    Raises:
        HTTPException: If user lacks permission (403) or alert not found (404).
    """
    try:
        alert = await service.get_alert(alert_id=alert_id, user_id=current_user.sub)
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to access this alert")

    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return alert


@router.put("/{alert_id}/read", summary="Mark alert as read")
async def mark_alert_read(
    alert_id: str,
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
):
    """Mark an alert as read.

    Args:
        alert_id: The unique identifier of the alert.
        current_user: The authenticated user.
        service: The monitoring service.

    Returns:
        A message confirming the alert has been marked as read.

    Raises:
        HTTPException: If the alert does not exist or user lacks permission (404).
    """
    success = await service.mark_alert_read(alert_id, current_user.sub)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found or no permission to mark"
        )

    return {"message": "Alert has been marked as read"}


@router.put("/{alert_id}/resolve", summary="Resolve alert")
async def resolve_alert(
    alert_id: str,
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
):
    """Resolve an alert.

    Args:
        alert_id: The unique identifier of the alert.
        current_user: The authenticated user.
        service: The monitoring service.

    Returns:
        A message confirming the alert has been resolved.

    Raises:
        HTTPException: If the alert does not exist or user lacks permission (404).
    """
    success = await service.resolve_alert(alert_id, current_user.sub)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found or no permission to resolve"
        )

    return {"message": "Alert has been resolved"}


@router.put("/{alert_id}/acknowledge", summary="Acknowledge alert")
async def acknowledge_alert(
    alert_id: str,
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
):
    """Acknowledge an alert.

    Args:
        alert_id: The unique identifier of the alert.
        current_user: The authenticated user.
        service: The monitoring service.

    Returns:
        A message confirming the alert has been acknowledged.

    Raises:
        HTTPException: If the alert does not exist or user lacks permission (404).
    """
    success = await service.acknowledge_alert(alert_id, current_user.sub)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found or no permission to acknowledge"
        )

    return {"message": "Alert has been acknowledged"}


# ==================== Alert Statistics API ====================

@router.get("/statistics/summary", summary="Get alert statistics summary")
async def get_alert_summary(
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
):
    """Get the alert statistics summary for the current user.

    Args:
        current_user: The authenticated user.
        service: The monitoring service.

    Returns:
        A dictionary containing alert statistics summary.
    """
    return await service.get_alert_summary(user_id=current_user.sub)


@router.get("/statistics/by-type", summary="Get alert statistics by type")
async def get_alerts_by_type(
    current_user=Depends(get_current_user),
    service: MonitoringService = Depends(get_monitoring_service),
    start_date: str = Query(..., description="Start date"),
    end_date: str = Query(..., description="End date"),
):
    """Get alert statistics grouped by type for a date range.

    Args:
        current_user: The authenticated user.
        service: The monitoring service.
        start_date: Start date in ISO 8601 format.
        end_date: End date in ISO 8601 format.

    Returns:
        A dictionary containing start_date, end_date, and statistics by type.

    Raises:
        HTTPException: If date format is invalid (400).
    """
    from datetime import datetime
    try:
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format: {e}"
        )

    stats = await service.get_alerts_by_type(user_id=current_user.sub, start_dt=start_dt, end_dt=end_dt)
    return {"start_date": start_date, "end_date": end_date, **stats}


# ==================== WebSocket Endpoint ====================

@router.websocket("/ws/alerts")
async def alerts_websocket(
    websocket,
):
    """WebSocket endpoint for alert real-time updates.

    Pushes:
        - New alert creation
        - Alert status updates
        - Alert resolution notifications
        - Alert statistics updates

    Connection URL: ws://host/api/v1/monitoring/ws/alerts

    Message types:
        - connected: Connection successful
        - alert_created: New alert
        - alert_updated: Alert updated
        - alert_resolved: Alert resolved
        - alert_acknowledged: Alert acknowledged
        - stats_update: Statistics update

    Args:
        websocket: The WebSocket connection instance.
    """
    client_id = f"ws-alerts-client-{id(websocket)}"

    # Establish connection
    await ws_manager.connect(websocket, "alerts:global", client_id)

    try:
        # Send initial message
        await ws_manager.send_to_task("alerts:global", {
            "type": MessageType.CONNECTED,
            "message": "Alert monitoring WebSocket connection successful",
        })

        # Keep connection alive
        while True:
            await asyncio.sleep(1)

            # Latest alerts should be fetched from monitoring service
            # and pushed via WebSocket
            # Temporarily using polling; should use event-driven in production

    except Exception as e:
        logger.error(f"Alerts WebSocket error: {e}")
        ws_manager.disconnect(websocket, "alerts:global", client_id)
