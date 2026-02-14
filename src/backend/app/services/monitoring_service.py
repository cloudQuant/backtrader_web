"""
监控告警服务

支持账户监控、持仓监控、策略监控、系统监控
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import logging
import asyncio

from app.models.alerts import (
    Alert,
    AlertRule,
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
from app.db.sql_repository import SQLRepository
from app.websocket_manager import manager as ws_manager

logger = logging.getLogger(__name__)


class MonitoringService:
    """
    监控告警服务

    功能：
    1. 创建告警规则
    2. 实时监控指标
    3. 触发告警
    4. 发送通知
    5. 告警管理
    """

    def __init__(self):
        self.alert_repo = SQLRepository(Alert)
        self.alert_rule_repo = SQLRepository(AlertRule)
        self.live_trading_service = LiveTradingService()
        self.backtest_service = BacktestService()

        # 监控任务
        self._monitoring_tasks: Dict[str, asyncio.Task] = {}
        self._running = False

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
        """
        创建告警规则

        Args:
            user_id: 用户 ID
            name: 规则名称
            description: 规则描述
            alert_type: 告警类型
            severity: 告警级别
            trigger_type: 触发类型
            trigger_config: 触发配置
            notification_enabled: 是否启用通知
            notification_channels: 通知渠道

        Returns:
            AlertRule: 创建的告警规则
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

        # 启动监控任务
        await self._start_monitoring(rule.id)

        return rule

    async def update_alert_rule(
        self,
        rule_id: str,
        user_id: str,
        update_data: Dict[str, Any],
    ) -> Optional[AlertRule]:
        """
        更新告警规则

        Args:
            rule_id: 规则 ID
            user_id: 用户 ID
            update_data: 更新数据

        Returns:
            AlertRule or None
        """
        rule = await self.alert_rule_repo.get_by_id(rule_id)
        if not rule or rule.user_id != user_id:
            return None

        # 如果规则变为不活跃，停止监控
        if not update_data.get("is_active", True) and rule.is_active:
            await self._stop_monitoring(rule_id)

        # 更新规则
        rule = await self.alert_rule_repo.update(rule_id, update_data)

        # 如果规则变为活跃，启动监控
        if update_data.get("is_active", True) and not rule.is_active:
            await self._start_monitoring(rule.id)

        return rule

    async def delete_alert_rule(
        self,
        rule_id: str,
        user_id: str,
    ) -> bool:
        """
        删除告警规则

        Args:
            rule_id: 规则 ID
            user_id: 用户 ID

        Returns:
            bool: 是否删除成功
        """
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
        """
        列出告警规则

        Args:
            user_id: 用户 ID
            alert_type: 告警类型筛选
            severity: 告警级别筛选
            is_active: 是否活跃

        Returns:
            (rules, total)
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
        """
        列出告警

        Args:
            user_id: 用户 ID
            alert_type: 告警类型筛选
            severity: 告警级别筛选
            status: 告警状态筛选
            is_read: 是否已读
            limit: 每页数量
            offset: 偏移量

        Returns:
            (alerts, total)
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

    async def _start_monitoring(self, rule_id: str):
        """
        启动监控任务

        Args:
            rule_id: 规则 ID
        """
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
        """
        停止监控任务

        Args:
            rule_id: 规则 ID
        """
        if rule_id in self._monitoring_tasks:
            task = self._monitoring_tasks[rule_id]
            task.cancel()
            del self._monitoring_tasks[rule_id]

            logger.info(f"Stopped monitoring task: {rule_id}")

    async def _monitor_task(self, rule_id: str):
        """
        监控任务

        Args:
            rule_id: 规则 ID
        """
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
        """
        检查是否应该触发告警

        Args:
            rule: 告警规则

        Returns:
            bool: 是否应该触发
        """
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
        """
        检查阈值触发

        Args:
            rule: 告警规则
            config: 触发配置

        Returns:
            bool: 是否应该触发
        """
        alert_type = rule.alert_type

        if alert_type == AlertType.ACCOUNT:
            # 账户监控
            # TODO: 从实盘账户获取数据
            current_value = config.get("current_value", 0.0)
            threshold = config.get("threshold")
            condition = config.get("condition", "lt")  # lt, gt, eq

            if condition == "lt":
                return current_value < threshold
            elif condition == "gt":
                return current_value > threshold
            else:
                return current_value == threshold

        elif alert_type == AlertType.POSITION:
            # 持仓监控
            symbol = config.get("symbol")
            metric = config.get("metric", "unrealized_pnl")
            threshold = config.get("threshold")
            condition = config.get("condition", "lt")

            # TODO: 从实盘持仓获取数据
            current_value = config.get("current_value", 0.0)

            if condition == "lt":
                return current_value < threshold
            elif condition == "gt":
                return current_value > threshold
            else:
                return current_value == threshold

        elif alert_type == AlertType.STRATEGY:
            # 策略监控
            # TODO: 从回测或模拟交易获取数据
            pass

        return False

    async def _check_rate_trigger(self, rule: AlertRule, config: Dict[str, Any]) -> bool:
        """
        检查变化率触发

        Args:
            rule: 告警规则
            config: 触发配置

        Returns:
            bool: 是否应该触发
        """
        # 获取历史值
        # TODO: 实现历史数据存储和比较
        return False

    async def _check_cross_trigger(self, rule: AlertRule, config: Dict[str, Any]) -> bool:
        """
        检查交叉触发

        Args:
            rule: 告警规则
            config: 触发配置

        Returns:
            bool: 是否应该触发
        """
        # TODO: 实现交叉检测
        return False

    async def _trigger_alert(self, rule: AlertRule):
        """
        触发告警

        Args:
            rule: 告警规则
        """
        # 更新触发次数
        await self.alert_rule_repo.update(rule.id, {
            "triggered_count": rule.triggered_count + 1,
            "last_triggered_at": datetime.now(timezone.utc),
        })

        # 创建告警
        alert = Alert(
            user_id=rule.user_id,
            alert_type=rule.alert_type,
            severity=rule.severity,
            status=AlertStatus.ACTIVE,
            title=f"{rule.alert_type} 告警",
            message=rule.description,
            details=rule.trigger_config,
            rule_id=rule.id,
        )

        alert = await self.alert_repo.create(alert)

        # 推送通知
        await self._send_notification(rule, alert)

        # 推送 WebSocket
        await self._send_websocket_alert(rule, alert)

        logger.info(f"Alert triggered: {alert.id}")

    async def _send_notification(self, rule: AlertRule, alert: Alert):
        """
        发送通知

        Args:
            rule: 告警规则
            alert: 告警对象
        """
        if not rule.notification_enabled:
            return

        # 根据渠道发送通知
        channels = rule.notification_channels or []

        for channel in channels:
            if channel == "email":
                # TODO: 发送邮件通知
                pass
            elif channel == "sms":
                # TODO: 发送短信通知
                pass
            elif channel == "push":
                # TODO: 发送推送通知
                pass
            elif channel == "webhook":
                # TODO: 发送 Webhook
                pass

    async def _send_websocket_alert(self, rule: AlertRule, alert: Alert):
        """
        发送 WebSocket 告警

        Args:
            rule: 告警规则
            alert: 告警对象
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

        # 推送给用户
        await ws_manager.send_to_task(f"alert:{rule.user_id}", message)

        # 推送给策略（如果有关联）
        if alert.strategy_id:
            await ws_manager.send_to_task(f"strategy:{alert.strategy_id}", message)

    async def mark_alert_read(self, alert_id: str, user_id: str) -> bool:
        """
        标记告警为已读

        Args:
            alert_id: 告警 ID
            user_id: 用户 ID

        Returns:
            bool: 是否成功
        """
        alert = await self.alert_repo.get_by_id(alert_id)
        if not alert or alert.user_id != user_id:
            return False

        await self.alert_repo.update(alert_id, {"is_read": True})

        return True

    async def resolve_alert(self, alert_id: str, user_id: str) -> bool:
        """
        解决告警

        Args:
            alert_id: 告警 ID
            user_id: 用户 ID

        Returns:
            bool: 是否成功
        """
        alert = await self.alert_repo.get_by_id(alert_id)
        if not alert or alert.user_id != user_id:
            return False

        await self.alert_repo.update(alert_id, {
            "status": AlertStatus.RESOLVED,
            "resolved_at": datetime.now(timezone.utc),
        })

        return True

    async def acknowledge_alert(self, alert_id: str, user_id: str) -> bool:
        """
        确认告警

        Args:
            alert_id: 告警 ID
            user_id: 用户 ID

        Returns:
            bool: 是否成功
        """
        alert = await self.alert_repo.get_by_id(alert_id)
        if not alert or alert.user_id != user_id:
            return False

        await self.alert_repo.update(alert_id, {
            "status": AlertStatus.ACKNOWLEDGED,
        })

        return True
