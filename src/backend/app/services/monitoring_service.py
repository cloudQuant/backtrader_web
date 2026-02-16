"""
Monitoring and alerting service.

Supports:
- Account monitoring
- Position monitoring
- Strategy monitoring
- System monitoring
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import logging
import asyncio
import json
import urllib.request
import urllib.error

from app.models.alerts import (
    Alert,
    AlertRule,
    AlertNotification,
    AlertType,
    AlertSeverity,
    AlertStatus,
)
from app.schemas.monitoring import (
    AlertCreate,
    AlertResponse,
    AlertListResponse,
    AlertRuleCreate,
    AlertRuleResponse,
    AlertRuleListResponse,
)
from app.services.live_trading_service import LiveTradingService
from app.services.backtest_service import BacktestService
from app.services.paper_trading_service import PaperTradingService
from app.db.sql_repository import SQLRepository
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
        self._monitoring_tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        self._trigger_state: Dict[str, Any] = {}

    async def create_alert_rule(
        self,
        user_id: str,
        name: str,
        description: str,
        alert_type: str,
        severity: str,
        trigger_type: str,
        trigger_config: Dict[str, Any],
        notification_enabled: bool = True,
        notification_channels: Optional[List[str]] = None,
    ) -> AlertRule:
        """Create an alert rule and start monitoring if enabled."""
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

        # 启动监控任务
        await self._start_monitoring(rule.id)

        return rule

    async def update_alert_rule(
        self,
        rule_id: str,
        user_id: str,
        update_data: Dict[str, Any],
    ) -> Optional[AlertRule]:
        """Update an alert rule and start/stop monitoring as needed."""
        rule = await self.alert_rule_repo.get_by_id(rule_id)
        if not rule or rule.user_id != user_id:
            return None

        was_active = bool(getattr(rule, "is_active", False))

        # 如果规则变为不活跃，停止监控
        if not update_data.get("is_active", True) and rule.is_active:
            await self._stop_monitoring(rule_id)

        # 更新规则
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
        """Delete an alert rule and stop its monitoring task."""
        rule = await self.alert_rule_repo.get_by_id(rule_id)
        if not rule or rule.user_id != user_id:
            return False

        # 停止监控
        await self._stop_monitoring(rule_id)

        # 删除规则
        await self.alert_rule_repo.delete(rule_id)

        return True

    async def list_alert_rules(
        self,
        user_id: str,
        alert_type: Optional[str] = None,
        severity: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> tuple[List[AlertRule], int]:
        """List alert rules for a user with optional filters."""
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

    async def get_alert_rule(self, rule_id: str, user_id: str) -> Optional[AlertRule]:
        """Get a single alert rule by id with permission check."""
        rule = await self.alert_rule_repo.get_by_id(rule_id)
        if not rule:
            return None
        if getattr(rule, "user_id", None) != user_id:
            raise PermissionError("forbidden")
        return rule

    async def list_alerts(
        self,
        user_id: str,
        alert_type: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        is_read: Optional[bool] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[List[Alert], int]:
        """List alerts for a user with optional filters and pagination."""
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

    async def get_alert(self, alert_id: str, user_id: str) -> Optional[Alert]:
        """Get a single alert by id with permission check."""
        alert = await self.alert_repo.get_by_id(alert_id)
        if not alert:
            return None
        if getattr(alert, "user_id", None) != user_id:
            raise PermissionError("forbidden")
        return alert

    async def _start_monitoring(self, rule_id: str):
        """Start a background monitoring loop for a rule."""
        if rule_id in self._monitoring_tasks:
            logger.warning(f"Monitoring task already exists: {rule_id}")
            return

        rule = await self.alert_rule_repo.get_by_id(rule_id)
        if not rule or not rule.is_active:
            return

        # 创建监控任务
        task = asyncio.create_task(self._monitor_task(rule_id))

        self._monitoring_tasks[rule_id] = task

        logger.info(f"Started monitoring task: {rule_id}")

    async def _stop_monitoring(self, rule_id: str):
        """Stop a background monitoring loop for a rule."""
        if rule_id in self._monitoring_tasks:
            task = self._monitoring_tasks[rule_id]
            task.cancel()
            del self._monitoring_tasks[rule_id]

            logger.info(f"Stopped monitoring task: {rule_id}")

    async def _monitor_task(self, rule_id: str):
        """Background monitoring loop for a single rule."""
        rule = await self.alert_rule_repo.get_by_id(rule_id)
        if not rule or not rule.is_active:
            logger.info(f"Rule not active, stopping monitoring: {rule_id}")
            return

        logger.info(f"Monitoring task started for rule: {rule_id}")

        while True:
            try:
                # 获取规则配置
                rule = await self.alert_rule_repo.get_by_id(rule_id)
                if not rule or not rule.is_active:
                    logger.info(f"Rule not active, stopping monitoring: {rule_id}")
                    break

                # 检查触发条件
                should_trigger = await self._check_trigger(rule)

                if should_trigger:
                    # 触发告警
                    await self._trigger_alert(rule)

                # 根据告警类型决定检查间隔
                if rule.alert_type == AlertType.SYSTEM:
                    # 系统告警：每 5 分钟检查一次
                    await asyncio.sleep(300)
                elif rule.alert_type in [AlertType.ACCOUNT, AlertType.POSITION]:
                    # 账户/持仓告警：每 30 秒检查一次
                    await asyncio.sleep(30)
                elif rule.alert_type == AlertType.STRATEGY:
                    # 策略告警：每 60 秒检查一次
                    await asyncio.sleep(60)
                else:
                    # 其他：每 60 秒检查一次
                    await asyncio.sleep(60)

            except asyncio.CancelledError:
                logger.info(f"Monitoring task cancelled: {rule_id}")
                break
            except Exception as e:
                logger.error(f"Monitoring task error ({rule_id}): {e}")
                await asyncio.sleep(60)

    async def _check_trigger(self, rule: AlertRule) -> bool:
        """Evaluate whether a rule should trigger."""
        trigger_type = rule.trigger_type
        trigger_config = rule.trigger_config

        if trigger_type == "threshold":
            # 阈值触发
            return await self._check_threshold_trigger(rule, trigger_config)
        elif trigger_type == "rate":
            # 变化率触发
            return await self._check_rate_trigger(rule, trigger_config)
        elif trigger_type == "cross":
            # 交叉触发
            return await self._check_cross_trigger(rule, trigger_config)
        elif trigger_type == "manual":
            # 手动触发
            return False
        else:
            return False

    async def _check_threshold_trigger(self, rule: AlertRule, config: Dict[str, Any]) -> bool:
        """Evaluate a threshold trigger.

        Supported data sources (in `trigger_config`):
        - Paper trading: `account_id` (+ optional `symbol` for position rules)
        - Live trading: `live_task_id`
        - Backtest: `backtest_task_id`
        - Fallback/manual: `current_value`
        """
        threshold = config.get("threshold")
        if threshold is None:
            return False

        current_value = await self._get_current_metric_value(rule, config)
        if current_value is None:
            return False

        return self._compare(current_value, threshold, config.get("condition", "lt"))

    async def _check_rate_trigger(self, rule: AlertRule, config: Dict[str, Any]) -> bool:
        """Evaluate a rate-of-change trigger.

        This implementation keeps state in-memory per rule id. If there is no
        previous value, it records the current value and returns False.
        """
        threshold = config.get("threshold")
        if threshold is None:
            return False

        current_value = await self._get_current_metric_value(rule, config)
        if current_value is None:
            return False

        rule_id = getattr(rule, "id", None)
        if not rule_id:
            return False
        state_key = f"rate:{rule_id}"
        prev = self._trigger_state.get(state_key)
        self._trigger_state[state_key] = current_value
        if prev is None:
            return False

        mode = config.get("mode", "pct")  # pct | abs
        if mode == "abs":
            change = current_value - float(prev)
        else:
            prev_f = float(prev)
            if prev_f == 0:
                change = float("inf") if current_value != 0 else 0.0
            else:
                change = (current_value - prev_f) / abs(prev_f)

        return self._compare(change, float(threshold), config.get("condition", "gt"))

    async def _check_cross_trigger(self, rule: AlertRule, config: Dict[str, Any]) -> bool:
        """Evaluate a cross trigger based on two values.

        Expected config keys:
        - `value1`: current value 1 (optional if `current_value` is provided)
        - `value2`: value 2, or use `threshold` as value 2
        - `direction`: "up" (crosses from <=0 to >0) or "down" (>=0 to <0)
        """
        v1 = config.get("value1", config.get("current_value"))
        v2 = config.get("value2", config.get("threshold", 0.0))
        try:
            v1_f = float(v1)
            v2_f = float(v2)
        except (TypeError, ValueError):
            return False

        diff = v1_f - v2_f
        rule_id = getattr(rule, "id", None)
        if not rule_id:
            return False
        state_key = f"cross:{rule_id}"
        prev_diff = self._trigger_state.get(state_key)
        self._trigger_state[state_key] = diff
        if prev_diff is None:
            return False

        direction = str(config.get("direction", "up")).lower()
        if direction == "down":
            return float(prev_diff) >= 0 and diff < 0
        return float(prev_diff) <= 0 and diff > 0

    async def _trigger_alert(self, rule: AlertRule):
        """Create an alert record and push notifications."""
        # 更新触发次数
        await self.alert_rule_repo.update(rule.id, {
            "triggered_count": rule.triggered_count + 1,
            "last_triggered_at": datetime.now(timezone.utc),
        })

        trigger_config = rule.trigger_config if isinstance(getattr(rule, "trigger_config", None), dict) else {}
        trigger_value = await self._get_current_metric_value(rule, trigger_config)
        threshold_value = None
        threshold_value = trigger_config.get("threshold")
        trigger_type = getattr(rule, "trigger_type", "threshold")

        # 创建告警
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

        # 推送通知
        await self._send_notification(rule, alert)

        # 推送 WebSocket
        await self._send_websocket_alert(rule, alert)

        logger.info(f"Alert triggered: {alert.id}")

    async def _send_notification(self, rule: AlertRule, alert: Alert):
        """Send notifications for an alert.

        Channels:
        - web: handled by WebSocket publishing (always attempted)
        - webhook: best-effort HTTP call if `trigger_config.webhook.url` is provided
        - email/sms/push: recorded as pending (integration-specific)
        """
        if not rule.notification_enabled:
            return

        # 根据渠道发送通知
        channels = rule.notification_channels or []

        for channel in channels:
            if channel == "email":
                await self._record_notification(alert.id, channel="email", status="pending", message="email integration not configured")
            elif channel == "sms":
                await self._record_notification(alert.id, channel="sms", status="pending", message="sms integration not configured")
            elif channel == "push":
                await self._record_notification(alert.id, channel="push", status="pending", message="push integration not configured")
            elif channel == "webhook":
                await self._send_webhook(rule, alert)

        # Mark the alert as having attempted notifications.
        await self.alert_repo.update(alert.id, {"is_notification_sent": True})

    async def _send_webhook(self, rule: AlertRule, alert: Alert) -> None:
        """Best-effort webhook delivery using stdlib urllib."""
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
            "created_at": alert.created_at.isoformat() if getattr(alert, "created_at", None) else None,
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
            await self._record_notification(alert.id, channel="webhook", status="sent", message="ok")
        except (urllib.error.URLError, ValueError) as e:
            await self._record_notification(alert.id, channel="webhook", status="failed", message=str(e))

    async def _record_notification(self, alert_id: str, channel: str, status: str, message: str) -> None:
        """Persist a notification delivery attempt."""
        note = AlertNotification(
            alert_id=alert_id,
            channel=channel,
            status=status,
            message=message,
        )
        await self.notification_repo.create(note)

    async def _send_websocket_alert(self, rule: AlertRule, alert: Alert):
        """Publish a WebSocket alert message."""
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

        # 推送给用户
        await ws_manager.send_to_task(f"alert:{rule.user_id}", message)

        # 推送给策略（如果有关联）
        if alert.strategy_id:
            await ws_manager.send_to_task(f"strategy:{alert.strategy_id}", message)

    async def mark_alert_read(self, alert_id: str, user_id: str) -> bool:
        """Mark an alert as read."""
        alert = await self.alert_repo.get_by_id(alert_id)
        if not alert or alert.user_id != user_id:
            return False

        await self.alert_repo.update(alert_id, {"is_read": True})

        return True

    async def resolve_alert(self, alert_id: str, user_id: str) -> bool:
        """Resolve an alert."""
        alert = await self.alert_repo.get_by_id(alert_id)
        if not alert or alert.user_id != user_id:
            return False

        await self.alert_repo.update(alert_id, {
            "status": AlertStatus.RESOLVED,
            "resolved_at": datetime.now(timezone.utc),
        })

        return True

    async def acknowledge_alert(self, alert_id: str, user_id: str) -> bool:
        """Acknowledge an alert."""
        alert = await self.alert_repo.get_by_id(alert_id)
        if not alert or alert.user_id != user_id:
            return False

        await self.alert_repo.update(alert_id, {
            "status": AlertStatus.ACKNOWLEDGED,
        })

        return True

    async def get_alert_summary(self, user_id: str, recent_limit: int = 10) -> Dict[str, Any]:
        """Build a lightweight alert summary for a user."""
        alerts, total = await self.list_alerts(user_id=user_id, limit=1000, offset=0)

        by_type: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
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
    ) -> Dict[str, Any]:
        """Compute alert counts by type for a given time range."""
        alerts, _ = await self.list_alerts(user_id=user_id, limit=5000, offset=0)
        by_type: Dict[str, int] = {}
        for a in alerts:
            created_at = getattr(a, "created_at", None)
            if not created_at:
                continue
            if created_at < start_dt or created_at > end_dt:
                continue
            at = str(getattr(a, "alert_type", ""))
            by_type[at] = by_type.get(at, 0) + 1
        return {"by_type": by_type}

    async def _get_current_metric_value(self, rule: AlertRule, config: Dict[str, Any]) -> Optional[float]:
        """Resolve the current numeric value for a rule based on its type and config."""
        alert_type = getattr(rule, "alert_type", None)
        try:
            alert_type_enum = AlertType(alert_type)
        except Exception:
            alert_type_enum = alert_type

        # Manual/compat fallback.
        if "current_value" in config:
            try:
                return float(config.get("current_value"))
            except (TypeError, ValueError):
                return None

        if alert_type_enum == AlertType.ACCOUNT:
            metric = str(config.get("metric", "cash"))
            account_id = config.get("account_id")
            if account_id:
                account = await self.paper_trading_service.get_account(account_id)
                if not account:
                    return None
                if metric == "cash":
                    return float(account.current_cash)
                if metric in ("value", "equity"):
                    return float(account.total_equity)
                return None

            live_task_id = config.get("live_task_id")
            if live_task_id:
                status = await self.live_trading_service.get_task_status(rule.user_id, live_task_id)
                if not status:
                    return None
                if metric == "cash":
                    return float(status.get("cash", 0.0))
                if metric in ("value", "equity"):
                    return float(status.get("value", 0.0))
                return None

        if alert_type_enum == AlertType.POSITION:
            metric = str(config.get("metric", "unrealized_pnl"))
            symbol = config.get("symbol")
            if not symbol:
                return None

            account_id = config.get("account_id")
            if account_id:
                positions, _ = await self.paper_trading_service.list_positions(
                    filters={"account_id": account_id, "symbol": symbol},
                    limit=1,
                    offset=0,
                )
                if not positions:
                    return None
                pos = positions[0]
                if metric == "market_value":
                    return float(pos.market_value)
                if metric == "unrealized_pnl":
                    return float(pos.unrealized_pnl)
                if metric == "unrealized_pnl_pct":
                    return float(pos.unrealized_pnl_pct)
                return None

            live_task_id = config.get("live_task_id")
            if live_task_id:
                status = await self.live_trading_service.get_task_status(rule.user_id, live_task_id)
                if not status:
                    return None
                positions = status.get("positions") or []
                for p in positions:
                    if p.get("symbol") == symbol:
                        size = float(p.get("size", 0.0))
                        price = float(p.get("price", 0.0))
                        if metric == "market_value":
                            return size * price
                        return size * price
                return None

        if alert_type_enum == AlertType.STRATEGY:
            metric = str(config.get("metric", "sharpe_ratio"))
            backtest_task_id = config.get("backtest_task_id")
            if backtest_task_id:
                result = await self.backtest_service.get_result(backtest_task_id, user_id=rule.user_id)
                if not result:
                    return None
                if metric == "sharpe_ratio":
                    return float(result.sharpe_ratio)
                if metric == "total_return":
                    return float(result.total_return)
                if metric == "max_drawdown":
                    return float(result.max_drawdown)
                if metric == "win_rate":
                    return float(result.win_rate)
                return None
        return None

    @staticmethod
    def _compare(current_value: float, threshold: float, condition: str) -> bool:
        """Compare two floats using a simple operator string."""
        cond = str(condition or "lt").lower()
        if cond == "gt":
            return current_value > threshold
        if cond == "eq":
            return current_value == threshold
        return current_value < threshold
