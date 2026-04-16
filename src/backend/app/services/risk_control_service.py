"""
Risk Control Service - 风控服务

提供实盘交易的风险控制功能，包括仓位限制、止损止盈、亏损预警等。
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.utils.logger import get_logger

logger = get_logger(__name__)


class RiskAlertType(str, Enum):
    """风控告警类型"""

    POSITION_LIMIT = "position_limit"  # 仓位超限
    DAILY_LOSS = "daily_loss"  # 日亏损超限
    MAX_DRAWDOWN = "max_drawdown"  # 最大回撤
    STOP_LOSS = "stop_loss"  # 止损触发
    TAKE_PROFIT = "take_profit"  # 止盈触发
    ABNORMAL_TRADING = "abnormal_trading"  # 异常交易


class RiskAlertLevel(str, Enum):
    """风控告警级别"""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class RiskControlConfig:
    """风控配置"""

    # 仓位限制
    max_position_pct: float = 30.0  # 单品种最大仓位比例(%)
    max_total_position_pct: float = 80.0  # 总仓位上限(%)

    # 亏损限制
    max_daily_loss_pct: float = 5.0  # 日亏损上限(%)
    max_drawdown_pct: float = 20.0  # 最大回撤限制(%)

    # 止损止盈
    stop_loss_pct: float = 5.0  # 止损比例(%)
    take_profit_pct: float = 20.0  # 止盈比例(%)

    # 交易限制
    max_daily_trades: int = 50  # 每日最大交易次数
    max_order_size: float = 100000.0  # 单笔最大金额

    # 开关
    enable_stop_loss: bool = True  # 启用止损
    enable_take_profit: bool = True  # 启用止盈
    enable_position_limit: bool = True  # 启用仓位限制


@dataclass
class RiskAlert:
    """风控告警"""

    alert_type: RiskAlertType
    level: RiskAlertLevel
    message: str
    instance_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict[str, Any] = field(default_factory=dict)


class RiskControlService:
    """风控服务"""

    def __init__(self, config: RiskControlConfig | None = None):
        self.config = config or RiskControlConfig()
        self._alerts: list[RiskAlert] = []
        self._daily_trades: dict[str, int] = {}  # instance_id -> count
        self._daily_pnl: dict[str, float] = {}  # instance_id -> pnl

    def update_config(self, config: RiskControlConfig) -> None:
        """更新风控配置"""
        self.config = config
        logger.info(f"Risk control config updated: {config}")

    async def check_position_limit(
        self,
        instance_id: str,
        symbol: str,
        position_size: float,
        account_balance: float,
        current_positions: dict[str, float],
    ) -> tuple[bool, RiskAlert | None]:
        """
        检查仓位限制

        Args:
            instance_id: 实例ID
            symbol: 交易标的
            position_size: 拟开仓金额
            account_balance: 账户余额
            current_positions: 当前持仓 {symbol: size}

        Returns:
            (是否通过检查, 告警信息)
        """
        if not self.config.enable_position_limit:
            return True, None

        # 检查单品种仓位
        single_position_pct = (position_size / account_balance) * 100
        if single_position_pct > self.config.max_position_pct:
            alert = RiskAlert(
                alert_type=RiskAlertType.POSITION_LIMIT,
                level=RiskAlertLevel.WARNING,
                message=f"单品种仓位超限: {symbol} 仓位 {single_position_pct:.1f}% 超过上限 {self.config.max_position_pct}%",
                instance_id=instance_id,
                details={
                    "symbol": symbol,
                    "position_pct": single_position_pct,
                    "limit": self.config.max_position_pct,
                },
            )
            self._add_alert(alert)
            return False, alert

        # 检查总仓位
        total_position = sum(current_positions.values()) + position_size
        total_position_pct = (total_position / account_balance) * 100
        if total_position_pct > self.config.max_total_position_pct:
            alert = RiskAlert(
                alert_type=RiskAlertType.POSITION_LIMIT,
                level=RiskAlertLevel.WARNING,
                message=f"总仓位超限: 当前 {total_position_pct:.1f}% 超过上限 {self.config.max_total_position_pct}%",
                instance_id=instance_id,
                details={
                    "total_position_pct": total_position_pct,
                    "limit": self.config.max_total_position_pct,
                },
            )
            self._add_alert(alert)
            return False, alert

        return True, None

    async def check_daily_loss(
        self,
        instance_id: str,
        account_balance: float,
        initial_balance: float,
    ) -> tuple[bool, RiskAlert | None]:
        """
        检查日亏损

        Args:
            instance_id: 实例ID
            account_balance: 当前余额
            initial_balance: 初始余额(当日开盘时)

        Returns:
            (是否继续交易, 告警信息)
        """
        daily_pnl = account_balance - initial_balance
        daily_pnl_pct = (daily_pnl / initial_balance) * 100 if initial_balance > 0 else 0

        self._daily_pnl[instance_id] = daily_pnl

        if daily_pnl_pct <= -self.config.max_daily_loss_pct:
            alert = RiskAlert(
                alert_type=RiskAlertType.DAILY_LOSS,
                level=RiskAlertLevel.CRITICAL,
                message=f"日亏损超限: 当前亏损 {abs(daily_pnl_pct):.1f}% 超过上限 {self.config.max_daily_loss_pct}%",
                instance_id=instance_id,
                details={
                    "daily_pnl": daily_pnl,
                    "daily_pnl_pct": daily_pnl_pct,
                    "limit": self.config.max_daily_loss_pct,
                },
            )
            self._add_alert(alert)
            return False, alert

        # 预警(达到80%阈值)
        if daily_pnl_pct <= -self.config.max_daily_loss_pct * 0.8:
            alert = RiskAlert(
                alert_type=RiskAlertType.DAILY_LOSS,
                level=RiskAlertLevel.WARNING,
                message=f"日亏损预警: 当前亏损 {abs(daily_pnl_pct):.1f}% 接近上限 {self.config.max_daily_loss_pct}%",
                instance_id=instance_id,
                details={
                    "daily_pnl": daily_pnl,
                    "daily_pnl_pct": daily_pnl_pct,
                    "threshold": self.config.max_daily_loss_pct * 0.8,
                },
            )
            self._add_alert(alert)

        return True, None

    async def check_stop_loss(
        self,
        instance_id: str,
        symbol: str,
        entry_price: float,
        current_price: float,
        position_size: float,
    ) -> RiskAlert | None:
        """
        检查止损

        Args:
            instance_id: 实例ID
            symbol: 交易标的
            entry_price: 开仓价格
            current_price: 当前价格
            position_size: 持仓数量

        Returns:
            告警信息(如果触发止损)
        """
        if not self.config.enable_stop_loss:
            return None

        # 计算盈亏比例
        pnl_pct = ((current_price - entry_price) / entry_price) * 100

        # 做空方向
        if position_size < 0:
            pnl_pct = -pnl_pct

        if pnl_pct <= -self.config.stop_loss_pct:
            alert = RiskAlert(
                alert_type=RiskAlertType.STOP_LOSS,
                level=RiskAlertLevel.CRITICAL,
                message=f"止损触发: {symbol} 亏损 {abs(pnl_pct):.1f}% 达到止损线 {self.config.stop_loss_pct}%",
                instance_id=instance_id,
                details={
                    "symbol": symbol,
                    "entry_price": entry_price,
                    "current_price": current_price,
                    "pnl_pct": pnl_pct,
                    "stop_loss_pct": self.config.stop_loss_pct,
                    "action": "close_position",
                },
            )
            self._add_alert(alert)
            return alert

        return None

    async def check_take_profit(
        self,
        instance_id: str,
        symbol: str,
        entry_price: float,
        current_price: float,
        position_size: float,
    ) -> RiskAlert | None:
        """
        检查止盈

        Args:
            instance_id: 实例ID
            symbol: 交易标的
            entry_price: 开仓价格
            current_price: 当前价格
            position_size: 持仓数量

        Returns:
            告警信息(如果触发止盈)
        """
        if not self.config.enable_take_profit:
            return None

        # 计算盈亏比例
        pnl_pct = ((current_price - entry_price) / entry_price) * 100

        # 做空方向
        if position_size < 0:
            pnl_pct = -pnl_pct

        if pnl_pct >= self.config.take_profit_pct:
            alert = RiskAlert(
                alert_type=RiskAlertType.TAKE_PROFIT,
                level=RiskAlertLevel.INFO,
                message=f"止盈触发: {symbol} 盈利 {pnl_pct:.1f}% 达到止盈线 {self.config.take_profit_pct}%",
                instance_id=instance_id,
                details={
                    "symbol": symbol,
                    "entry_price": entry_price,
                    "current_price": current_price,
                    "pnl_pct": pnl_pct,
                    "take_profit_pct": self.config.take_profit_pct,
                    "action": "close_position",
                },
            )
            self._add_alert(alert)
            return alert

        return None

    async def check_order_size(
        self,
        instance_id: str,
        order_size: float,
    ) -> tuple[bool, RiskAlert | None]:
        """
        检查订单金额

        Args:
            instance_id: 实例ID
            order_size: 订单金额

        Returns:
            (是否通过检查, 告警信息)
        """
        if order_size > self.config.max_order_size:
            alert = RiskAlert(
                alert_type=RiskAlertType.ABNORMAL_TRADING,
                level=RiskAlertLevel.WARNING,
                message=f"单笔金额超限: {order_size:.2f} 超过上限 {self.config.max_order_size}",
                instance_id=instance_id,
                details={
                    "order_size": order_size,
                    "limit": self.config.max_order_size,
                },
            )
            self._add_alert(alert)
            return False, alert

        return True, None

    async def increment_trade_count(self, instance_id: str) -> tuple[bool, RiskAlert | None]:
        """
        增加交易计数并检查是否超限

        Args:
            instance_id: 实例ID

        Returns:
            (是否允许交易, 告警信息)
        """
        count = self._daily_trades.get(instance_id, 0) + 1
        self._daily_trades[instance_id] = count

        if count > self.config.max_daily_trades:
            alert = RiskAlert(
                alert_type=RiskAlertType.ABNORMAL_TRADING,
                level=RiskAlertLevel.WARNING,
                message=f"每日交易次数超限: {count} 超过上限 {self.config.max_daily_trades}",
                instance_id=instance_id,
                details={
                    "trade_count": count,
                    "limit": self.config.max_daily_trades,
                },
            )
            self._add_alert(alert)
            return False, alert

        return True, None

    def get_alerts(
        self,
        instance_id: str | None = None,
        level: RiskAlertLevel | None = None,
        limit: int = 100,
    ) -> list[RiskAlert]:
        """
        获取告警列表

        Args:
            instance_id: 实例ID过滤
            level: 告警级别过滤
            limit: 返回数量限制

        Returns:
            告警列表
        """
        alerts = self._alerts

        if instance_id:
            alerts = [a for a in alerts if a.instance_id == instance_id]

        if level:
            alerts = [a for a in alerts if a.level == level]

        return alerts[-limit:]

    def clear_alerts(self, instance_id: str | None = None) -> int:
        """
        清除告警

        Args:
            instance_id: 实例ID(可选，不指定则清除全部)

        Returns:
            清除数量
        """
        if instance_id:
            original_count = len(self._alerts)
            self._alerts = [a for a in self._alerts if a.instance_id != instance_id]
            return original_count - len(self._alerts)
        else:
            count = len(self._alerts)
            self._alerts = []
            return count

    def reset_daily_counters(self, instance_id: str | None = None) -> None:
        """
        重置每日计数器(应在每日开盘时调用)

        Args:
            instance_id: 实例ID(可选，不指定则重置全部)
        """
        if instance_id:
            self._daily_trades.pop(instance_id, None)
            self._daily_pnl.pop(instance_id, None)
        else:
            self._daily_trades.clear()
            self._daily_pnl.clear()

        logger.info(f"Daily counters reset for instance: {instance_id or 'all'}")

    def _add_alert(self, alert: RiskAlert) -> None:
        """添加告警"""
        self._alerts.append(alert)
        logger.warning(f"Risk alert: [{alert.level.value}] {alert.message}")


# 全局风控服务实例
_risk_control_service: RiskControlService | None = None


def get_risk_control_service() -> RiskControlService:
    """获取风控服务实例"""
    global _risk_control_service
    if _risk_control_service is None:
        _risk_control_service = RiskControlService()
    return _risk_control_service


def init_risk_control_service(config: RiskControlConfig) -> RiskControlService:
    """初始化风控服务"""
    global _risk_control_service
    _risk_control_service = RiskControlService(config)
    return _risk_control_service
