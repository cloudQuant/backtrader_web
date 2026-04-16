"""
Monitoring and alerting service.

Supports:
- Account monitoring
- Position monitoring
- Strategy monitoring
- System monitoring
"""

import asyncio
import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.db.sql_repository import SQLRepository
from app.models.alerts import (
    Alert,
    AlertNotification,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    AlertType,
)
from app.services.alert_evaluation import (
    compare_values,
    get_current_metric_value,
)
from app.services.backtest_service import BacktestService
from app.services.live_trading_service import LiveTradingService
from app.services.paper_trading_service import PaperTradingService
from app.websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)


class MonitoringService:
    """
    Monitoring and alerting service.

    Responsibilities:
    1. Manage alert rules
    2. Run monitoring tasks
    3. Trigger alerts
    4. Send notifications
    5. Manage alert lifecycle
    """

    def __init__(self):
        self.alert_repo = SQLRepository(Alert)
        self.alert_rule_repo = SQLRepository(AlertRule)
        self.notification_repo = SQLRepository(AlertNotification)
        self.live_trading_service = LiveTradingService()
        self.backtest_service = BacktestService()
        self.paper_trading_service = PaperTradingService()

        # In-memory monitoring task registry (per-process).
        #
        # Note: this is intentionally kept in-memory; for production usage you would
        # likely want a proper scheduler and persistent state.
        self._monitoring_tasks: dict[str, asyncio.Task] = {}
        self._running = False
        self._trigger_state: dict[str, Any] = {}

    async def create_alert_rule(
        self,
        user_id: str,
        name: str,
        description: str,
        alert_type: str,
        severity: str,
        trigger_type: str,
        trigger_config: dict[str, Any],
        notification_enabled: bool = True,
        notification_channels: list[str] | None = None,
    ) -> AlertRule:
        """Creates a new alert rule and starts monitoring if enabled.

        Args:
            user_id: The unique identifier of the user creating the rule.
            name: The name of the alert rule.
            description: A description of what the rule monitors.
            alert_type: The type of alert (e.g., ACCOUNT, POSITION, STRATEGY, SYSTEM).
            severity: The severity level of the alert.
            trigger_type: The type of trigger (e.g., threshold, rate, cross).
            trigger_config: Configuration for the trigger condition.
            notification_enabled: Whether notifications are enabled for this rule.
            notification_channels: List of notification channels (e.g., web, email, webhook).

        Returns:
            AlertRule: The created alert rule instance.
        """
        rule = AlertRule(
            user_id=user_id,
            name=name,
            description=description,
            alert_type=AlertType(alert_type),
            severity=AlertSeverity(severity),
            trigger_type=trigger_type,
            trigger_config=trigger_config,
            notification_enabled=notification_enabled,
            notification_channels=notification_channels or ["web"],
            is_active=True,
            triggered_count=0,
        )

        rule = await self.alert_rule_repo.create(rule)

        logger.info(f"Created alert rule: {rule.id}")

        # Start monitoring task for this rule.
        await self._start_monitoring(rule.id)

        return rule

    async def update_alert_rule(
        self,
        rule_id: str,
        user_id: str,
        update_data: dict[str, Any],
    ) -> AlertRule | None:
        """Updates an existing alert rule and manages monitoring state.

        Stops monitoring if the rule becomes inactive and starts monitoring
        if an inactive rule becomes active.

        Args:
            rule_id: The unique identifier of the alert rule to update.
            user_id: The unique identifier of the user updating the rule.
            update_data: Dictionary containing fields to update.

        Returns:
            AlertRule: The updated alert rule, or None if not found.
        """
        rule = await self.alert_rule_repo.get_by_id(rule_id)
        if not rule or rule.user_id != user_id:
            return None

        was_active = bool(getattr(rule, "is_active", False))

        # Stop monitoring if the rule becomes inactive.
        if not update_data.get("is_active", True) and rule.is_active:
            await self._stop_monitoring(rule_id)

        # Update the rule with new data.
        rule = await self.alert_rule_repo.update(rule_id, update_data)

        # If the rule was inactive and becomes active, start monitoring.
        if bool(getattr(rule, "is_active", False)) and not was_active:
            await self._start_monitoring(rule.id)

        return rule

    async def delete_alert_rule(
        self,
        rule_id: str,
        user_id: str,
    ) -> bool:
        """Deletes an alert rule and stops its associated monitoring task.

        Args:
            rule_id: The unique identifier of the alert rule to delete.
            user_id: The unique identifier of the user requesting deletion.

        Returns:
            bool: True if the rule was deleted, False if not found or permission denied.
        """
        rule = await self.alert_rule_repo.get_by_id(rule_id)
        if not rule or rule.user_id != user_id:
            return False

        # Stop monitoring for this rule.
        await self._stop_monitoring(rule_id)

        # Delete the rule from the repository.
        await self.alert_rule_repo.delete(rule_id)

        return True

    async def list_alert_rules(
        self,
        user_id: str,
        alert_type: str | None = None,
        severity: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[AlertRule], int]:
        """Lists alert rules for a user with optional filters.

        Args:
            user_id: The unique identifier of the user.
            alert_type: Optional filter by alert type.
            severity: Optional filter by severity level.
            is_active: Optional filter by active status.

        Returns:
            A tuple containing:
                - List of AlertRule objects matching the filters.
                - Total count of matching rules.
        """
        filters = {"user_id": user_id}
        if alert_type:
            filters["alert_type"] = alert_type
        if severity:
            filters["severity"] = severity
        if is_active is not None:
            filters["is_active"] = is_active

        rules = await self.alert_rule_repo.list(
            filters=filters,
            sort_by="created_at",
            sort_order="desc",
        )

        total = await self.alert_rule_repo.count(filters=filters)

        return rules, total

    async def get_alert_rule(self, rule_id: str, user_id: str) -> AlertRule | None:
        """Retrieves a single alert rule by ID with permission check.

        Args:
            rule_id: The unique identifier of the alert rule.
            user_id: The unique identifier of the user requesting the rule.

        Returns:
            AlertRule: The requested alert rule, or None if not found.

        Raises:
            PermissionError: If the user does not own the rule.
        """
        rule = await self.alert_rule_repo.get_by_id(rule_id)
        if not rule:
            return None
        if getattr(rule, "user_id", None) != user_id:
            raise PermissionError("forbidden")
        return rule

    async def list_alerts(
        self,
        user_id: str,
        alert_type: str | None = None,
        severity: str | None = None,
        status: str | None = None,
        is_read: bool | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Alert], int]:
        """Lists alerts for a user with optional filters and pagination.

        Args:
            user_id: The unique identifier of the user.
            alert_type: Optional filter by alert type.
            severity: Optional filter by severity level.
            status: Optional filter by alert status.
            is_read: Optional filter by read status.
            limit: Maximum number of alerts to return.
            offset: Number of alerts to skip for pagination.

        Returns:
            A tuple containing:
                - List of Alert objects matching the filters.
                - Total count of matching alerts.
        """
        filters = {"user_id": user_id}
        if alert_type:
            filters["alert_type"] = alert_type
        if severity:
            filters["severity"] = severity
        if status:
            filters["status"] = status
        if is_read is not None:
            filters["is_read"] = is_read

        alerts = await self.alert_repo.list(
            filters=filters,
            skip=offset,
            limit=limit,
            sort_by="created_at",
            sort_order="desc",
        )

        total = await self.alert_repo.count(filters=filters)

        return alerts, total

    async def get_alert(self, alert_id: str, user_id: str) -> Alert | None:
        """Retrieves a single alert by ID with permission check.

        Args:
            alert_id: The unique identifier of the alert.
            user_id: The unique identifier of the user requesting the alert.

        Returns:
            Alert: The requested alert, or None if not found.

        Raises:
            PermissionError: If the user does not own the alert.
        """
        alert = await self.alert_repo.get_by_id(alert_id)
        if not alert:
            return None
        if getattr(alert, "user_id", None) != user_id:
            raise PermissionError("forbidden")
        return alert

    async def _start_monitoring(self, rule_id: str):
        """Starts a background monitoring loop for an alert rule.

        Args:
            rule_id: The unique identifier of the alert rule to monitor.
        """
        if rule_id in self._monitoring_tasks:
            logger.warning(f"Monitoring task already exists: {rule_id}")
            return

        rule = await self.alert_rule_repo.get_by_id(rule_id)
        if not rule or not rule.is_active:
            return

        # Create the monitoring task.
        task = asyncio.create_task(self._monitor_task(rule_id))

        self._monitoring_tasks[rule_id] = task

        logger.info(f"Started monitoring task: {rule_id}")

    async def _stop_monitoring(self, rule_id: str):
        """Stops a background monitoring loop for an alert rule.

        Args:
            rule_id: The unique identifier of the alert rule to stop monitoring.
        """
        if rule_id in self._monitoring_tasks:
            task = self._monitoring_tasks[rule_id]
            task.cancel()
            del self._monitoring_tasks[rule_id]

            logger.info(f"Stopped monitoring task: {rule_id}")

    async def _monitor_task(self, rule_id: str):
        """Background monitoring loop for a single alert rule.

        Periodically checks if the rule's trigger conditions are met and
        triggers alerts when necessary. Sleep intervals vary by alert type.

        Args:
            rule_id: The unique identifier of the alert rule to monitor.
        """
        rule = await self.alert_rule_repo.get_by_id(rule_id)
        if not rule or not rule.is_active:
            logger.info(f"Rule not active, stopping monitoring: {rule_id}")
            return

        logger.info(f"Monitoring task started for rule: {rule_id}")

        while True:
            try:
                # Fetch the latest rule configuration.
                rule = await self.alert_rule_repo.get_by_id(rule_id)
                if not rule or not rule.is_active:
                    logger.info(f"Rule not active, stopping monitoring: {rule_id}")
                    break

                # Check if trigger conditions are met.
                should_trigger = await self._check_trigger(rule)

                if should_trigger:
                    # Trigger the alert.
                    await self._trigger_alert(rule)

                # Determine check interval based on alert type.
                settings = get_settings()
                if rule.alert_type == AlertType.SYSTEM:
                    await asyncio.sleep(settings.MONITORING_SYSTEM_INTERVAL)
                elif rule.alert_type in [AlertType.ACCOUNT, AlertType.POSITION]:
                    await asyncio.sleep(settings.MONITORING_ACCOUNT_INTERVAL)
                elif rule.alert_type == AlertType.STRATEGY:
                    await asyncio.sleep(settings.MONITORING_STRATEGY_INTERVAL)
                else:
                    await asyncio.sleep(settings.MONITORING_DEFAULT_INTERVAL)

            except asyncio.CancelledError:
                logger.info(f"Monitoring task cancelled: {rule_id}")
                break
            except Exception as e:
                logger.error(f"Monitoring task error ({rule_id}): {e}")
                await asyncio.sleep(get_settings().MONITORING_DEFAULT_INTERVAL)

    async def _check_trigger(self, rule: AlertRule) -> bool:
        """Evaluates whether a rule should trigger based on its trigger type."""
        trigger_type = rule.trigger_type
        trigger_config = rule.trigger_config
        if trigger_type == "threshold":
            return await self._check_threshold_trigger(rule, trigger_config)
        elif trigger_type == "rate":
            return await self._check_rate_trigger(rule, trigger_config)
        elif trigger_type == "cross":
            return await self._check_cross_trigger(rule, trigger_config)
        elif trigger_type == "manual":
            return False
        return False

    async def _check_threshold_trigger(self, rule, config):
        from app.services.alert_evaluation import _check_threshold_trigger

        return await _check_threshold_trigger(rule, config, self._get_current_metric_value)

    async def _check_rate_trigger(self, rule, config):
        from app.services.alert_evaluation import _check_rate_trigger

        return await _check_rate_trigger(
            rule, config, self._trigger_state, self._get_current_metric_value
        )

    async def _check_cross_trigger(self, rule, config):
        from app.services.alert_evaluation import _check_cross_trigger

        return await _check_cross_trigger(rule, config, self._trigger_state)

    async def _trigger_alert(self, rule: AlertRule):
        """Creates an alert record and pushes notifications.

        Updates the rule's trigger count, creates a new Alert entity, and
        sends notifications via configured channels.

        Args:
            rule: The alert rule that was triggered.
        """
        # Update the trigger count and last triggered timestamp.
        await self.alert_rule_repo.update(
            rule.id,
            {
                "triggered_count": rule.triggered_count + 1,
                "last_triggered_at": datetime.now(timezone.utc),
            },
        )

        trigger_config = (
            rule.trigger_config if isinstance(getattr(rule, "trigger_config", None), dict) else {}
        )
        trigger_value = await self._get_current_metric_value(rule, trigger_config)
        threshold_value = None
        threshold_value = trigger_config.get("threshold")
        trigger_type = getattr(rule, "trigger_type", "threshold")

        # Create the alert record.
        alert = Alert(
            user_id=rule.user_id,
            alert_type=rule.alert_type,
            severity=rule.severity,
            status=AlertStatus.ACTIVE,
            title=f"{rule.alert_type} alert",
            message=rule.description,
            details=trigger_config,
            rule_id=rule.id,
            trigger_type=trigger_type,
            trigger_value=trigger_value,
            threshold_value=threshold_value,
        )

        alert = await self.alert_repo.create(alert)

        # Send notifications via configured channels.
        await self._send_notification(rule, alert)

        # Send WebSocket alert to connected clients.
        await self._send_websocket_alert(rule, alert)

        logger.info(f"Alert triggered: {alert.id}")

    async def _send_notification(self, rule: AlertRule, alert: Alert):
        """Sends notifications for an alert via configured channels.

        Args:
            rule: The alert rule containing notification configuration.
            alert: The alert to send notifications for.

        Notification channels:
            - web: handled by WebSocket publishing (always attempted)
            - webhook: best-effort HTTP call if `trigger_config.webhook.url` is provided
            - email/sms/push: recorded as pending (integration-specific)
        """
        if not rule.notification_enabled:
            return

        # Send notifications based on configured channels.
        channels = rule.notification_channels or []

        for channel in channels:
            if channel == "email":
                await self._record_notification(
                    alert.id,
                    channel="email",
                    status="pending",
                    message="email integration not configured",
                )
            elif channel == "sms":
                await self._record_notification(
                    alert.id,
                    channel="sms",
                    status="pending",
                    message="sms integration not configured",
                )
            elif channel == "push":
                await self._record_notification(
                    alert.id,
                    channel="push",
                    status="pending",
                    message="push integration not configured",
                )
            elif channel == "webhook":
                await self._send_webhook(rule, alert)

        # Mark the alert as having attempted notifications.
        await self.alert_repo.update(alert.id, {"is_notification_sent": True})

    async def _send_webhook(self, rule: AlertRule, alert: Alert) -> None:
        """Performs best-effort webhook delivery using standard library urllib.

        Args:
            rule: The alert rule containing webhook configuration.
            alert: The alert to send in the webhook payload.

        Note:
            This is a fire-and-forget implementation. Failures are recorded
            in the notification log but do not affect alert processing.
        """
        webhook = None
        if isinstance(rule.trigger_config, dict):
            webhook = rule.trigger_config.get("webhook") or {}
        url = webhook.get("url") if isinstance(webhook, dict) else None
        if not url:
            await self._record_notification(
                alert.id,
                channel="webhook",
                status="failed",
                message="missing webhook url",
            )
            return

        payload = {
            "alert_id": alert.id,
            "user_id": alert.user_id,
            "alert_type": str(alert.alert_type),
            "severity": str(alert.severity),
            "title": alert.title,
            "message": alert.message,
            "details": alert.details,
            "created_at": alert.created_at.isoformat()
            if getattr(alert, "created_at", None)
            else None,
        }

        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if isinstance(webhook, dict) and isinstance(webhook.get("headers"), dict):
            headers.update({str(k): str(v) for k, v in webhook["headers"].items()})
        method = str(webhook.get("method", "POST")).upper() if isinstance(webhook, dict) else "POST"

        req = urllib.request.Request(url=url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                _ = resp.read()  # drain
            await self._record_notification(
                alert.id, channel="webhook", status="sent", message="ok"
            )
        except (urllib.error.URLError, ValueError) as e:
            await self._record_notification(
                alert.id, channel="webhook", status="failed", message=str(e)
            )

    async def _record_notification(
        self, alert_id: str, channel: str, status: str, message: str
    ) -> None:
        """Persists a notification delivery attempt to the database.

        Args:
            alert_id: The unique identifier of the alert.
            channel: The notification channel (e.g., webhook, email).
            status: The delivery status (e.g., sent, failed, pending).
            message: Additional details about the delivery attempt.
        """
        note = AlertNotification(
            alert_id=alert_id,
            channel=channel,
            status=status,
            message=message,
        )
        await self.notification_repo.create(note)

    async def _send_websocket_alert(self, rule: AlertRule, alert: Alert):
        """Publishes an alert message via WebSocket to connected clients.

        Args:
            rule: The alert rule that was triggered.
            alert: The alert to send to WebSocket clients.
        """
        message = {
            "type": "alert",
            "alert_id": alert.id,
            "rule_id": rule.id,
            "data": {
                "alert_type": alert.alert_type.value,
                "severity": alert.severity.value,
                "title": alert.title,
                "message": alert.message,
                "details": alert.details,
                "created_at": alert.created_at.isoformat(),
            },
        }

        # Send to the user's alert channel.
        await ws_manager.send_to_task(f"alert:{rule.user_id}", message)

        # Send to the strategy channel if associated.
        if alert.strategy_id:
            await ws_manager.send_to_task(f"strategy:{alert.strategy_id}", message)

    async def mark_alert_read(self, alert_id: str, user_id: str) -> bool:
        """Marks an alert as read.

        Args:
            alert_id: The unique identifier of the alert.
            user_id: The unique identifier of the user marking the alert.

        Returns:
            bool: True if the alert was marked as read, False otherwise.
        """
        alert = await self.alert_repo.get_by_id(alert_id)
        if not alert or alert.user_id != user_id:
            return False

        await self.alert_repo.update(alert_id, {"is_read": True})

        return True

    async def resolve_alert(self, alert_id: str, user_id: str) -> bool:
        """Resolves an alert by setting its status to RESOLVED.

        Args:
            alert_id: The unique identifier of the alert.
            user_id: The unique identifier of the user resolving the alert.

        Returns:
            bool: True if the alert was resolved, False otherwise.
        """
        alert = await self.alert_repo.get_by_id(alert_id)
        if not alert or alert.user_id != user_id:
            return False

        await self.alert_repo.update(
            alert_id,
            {
                "status": AlertStatus.RESOLVED,
                "resolved_at": datetime.now(timezone.utc),
            },
        )

        return True

    async def acknowledge_alert(self, alert_id: str, user_id: str) -> bool:
        """Acknowledges an alert by setting its status to ACKNOWLEDGED.

        Args:
            alert_id: The unique identifier of the alert.
            user_id: The unique identifier of the user acknowledging the alert.

        Returns:
            bool: True if the alert was acknowledged, False otherwise.
        """
        alert = await self.alert_repo.get_by_id(alert_id)
        if not alert or alert.user_id != user_id:
            return False

        await self.alert_repo.update(
            alert_id,
            {
                "status": AlertStatus.ACKNOWLEDGED,
            },
        )

        return True

    async def get_alert_summary(self, user_id: str, recent_limit: int = 10) -> dict[str, Any]:
        """Builds a lightweight alert summary for a user.

        Provides counts of alerts grouped by type, severity, and status,
        along with a list of recent alerts.

        Args:
            user_id: The unique identifier of the user.
            recent_limit: Maximum number of recent alerts to include.

        Returns:
            A dictionary containing:
                - total_alerts: Total number of alerts.
                - by_type: Dictionary of alert counts by type.
                - by_severity: Dictionary of alert counts by severity.
                - by_status: Dictionary of alert counts by status.
                - recent: List of recent alert summaries.
        """
        alerts, total = await self.list_alerts(user_id=user_id, limit=1000, offset=0)

        by_type: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for a in alerts:
            at = getattr(a, "alert_type", None)
            sev = getattr(a, "severity", None)
            st = getattr(a, "status", None)
            by_type[str(at)] = by_type.get(str(at), 0) + 1
            by_severity[str(sev)] = by_severity.get(str(sev), 0) + 1
            by_status[str(st)] = by_status.get(str(st), 0) + 1

        recent = [
            {
                "id": a.id,
                "alert_type": str(getattr(a, "alert_type", "")),
                "severity": str(getattr(a, "severity", "")),
                "status": str(getattr(a, "status", "")),
                "title": a.title,
                "message": a.message,
                "created_at": a.created_at.isoformat() if getattr(a, "created_at", None) else None,
            }
            for a in alerts[:recent_limit]
        ]

        return {
            "total_alerts": total,
            "by_type": by_type,
            "by_severity": by_severity,
            "by_status": by_status,
            "recent": recent,
        }

    async def get_alerts_by_type(
        self,
        user_id: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> dict[str, Any]:
        """Computes alert counts grouped by type for a given time range.

        Args:
            user_id: The unique identifier of the user.
            start_dt: Start of the time range (inclusive).
            end_dt: End of the time range (inclusive).

        Returns:
            A dictionary containing alert counts by type under the key "by_type".
        """
        alerts, _ = await self.list_alerts(user_id=user_id, limit=5000, offset=0)
        by_type: dict[str, int] = {}
        for a in alerts:
            created_at = getattr(a, "created_at", None)
            if not created_at:
                continue
            if created_at < start_dt or created_at > end_dt:
                continue
            at = str(getattr(a, "alert_type", ""))
            by_type[at] = by_type.get(at, 0) + 1
        return {"by_type": by_type}

    async def _get_current_metric_value(
        self, rule: AlertRule, config: dict[str, Any]
    ) -> float | None:
        """Resolves the current numeric metric value for a rule."""
        return await get_current_metric_value(
            rule,
            config,
            getattr(self, "paper_trading_service", None),
            getattr(self, "live_trading_service", None),
            getattr(self, "backtest_service", None),
        )

    @staticmethod
    def _compare(current_value: float, threshold: float, condition: str) -> bool:
        """Compares two float values using a simple operator string."""
        return compare_values(current_value, threshold, condition)
