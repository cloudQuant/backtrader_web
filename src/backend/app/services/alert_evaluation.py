"""
Alert trigger evaluation and metric resolution.

Extracted from monitoring_service.py to keep file sizes manageable.
Contains the logic for checking trigger conditions (threshold, rate, cross)
and resolving current metric values from various data sources.
"""

import logging
from typing import Any

from app.models.alerts import AlertRule, AlertType

logger = logging.getLogger(__name__)


def compare_values(current_value: float, threshold: float, condition: str) -> bool:
    """Compare two float values using a simple operator string.

    Args:
        current_value: The current value to compare.
        threshold: The threshold value to compare against.
        condition: The comparison operator ("gt", "eq", or "lt"/default).

    Returns:
        True if the comparison condition is met, False otherwise.
    """
    cond = str(condition or "lt").lower()
    if cond == "gt":
        return current_value > threshold
    if cond == "eq":
        return current_value == threshold
    return current_value < threshold


async def check_trigger(
    rule: AlertRule,
    trigger_state: dict[str, Any],
    get_metric_fn,
) -> bool:
    """Evaluate whether a rule should trigger based on its trigger type.

    Args:
        rule: The alert rule to evaluate.
        trigger_state: Mutable dict for storing cross-check state between evaluations.
        get_metric_fn: Async callable(rule, config) -> float | None for fetching metric values.

    Returns:
        True if the rule should trigger, False otherwise.
    """
    trigger_type = rule.trigger_type
    trigger_config = rule.trigger_config

    if trigger_type == "threshold":
        return await _check_threshold_trigger(rule, trigger_config, get_metric_fn)
    elif trigger_type == "rate":
        return await _check_rate_trigger(rule, trigger_config, trigger_state, get_metric_fn)
    elif trigger_type == "cross":
        return await _check_cross_trigger(rule, trigger_config, trigger_state)
    elif trigger_type == "manual":
        return False
    else:
        return False


async def _check_threshold_trigger(
    rule: AlertRule,
    config: dict[str, Any],
    get_metric_fn,
) -> bool:
    """Evaluate a threshold-based trigger condition."""
    threshold = config.get("threshold")
    if threshold is None:
        return False

    current_value = await get_metric_fn(rule, config)
    if current_value is None:
        return False

    return compare_values(current_value, threshold, config.get("condition", "lt"))


async def _check_rate_trigger(
    rule: AlertRule,
    config: dict[str, Any],
    trigger_state: dict[str, Any],
    get_metric_fn,
) -> bool:
    """Evaluate a rate-of-change trigger condition."""
    threshold = config.get("threshold")
    if threshold is None:
        return False

    current_value = await get_metric_fn(rule, config)
    if current_value is None:
        return False

    rule_id = getattr(rule, "id", None)
    if not rule_id:
        return False
    state_key = f"rate:{rule_id}"
    prev = trigger_state.get(state_key)
    trigger_state[state_key] = current_value
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

    return compare_values(change, float(threshold), config.get("condition", "gt"))


async def _check_cross_trigger(
    rule: AlertRule,
    config: dict[str, Any],
    trigger_state: dict[str, Any],
) -> bool:
    """Evaluate a cross-over trigger condition based on two values."""
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
    prev_diff = trigger_state.get(state_key)
    trigger_state[state_key] = diff
    if prev_diff is None:
        return False

    direction = str(config.get("direction", "up")).lower()
    if direction == "down":
        return float(prev_diff) >= 0 and diff < 0
    return float(prev_diff) <= 0 and diff > 0


async def get_current_metric_value(
    rule: AlertRule,
    config: dict[str, Any],
    paper_trading_service,
    live_trading_service,
    backtest_service,
) -> float | None:
    """Resolve the current numeric metric value for a rule.

    Fetches real-time data from paper trading, live trading, or backtest
    services depending on the alert type and configuration.

    Args:
        rule: The alert rule requiring a metric value.
        config: Configuration specifying which metric to retrieve.
        paper_trading_service: Service for paper trading data.
        live_trading_service: Service for live trading data.
        backtest_service: Service for backtest data.

    Returns:
        The current metric value as a float, or None if unavailable.
    """
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
        return await _get_account_metric(rule, config, paper_trading_service, live_trading_service)

    if alert_type_enum == AlertType.POSITION:
        return await _get_position_metric(rule, config, paper_trading_service, live_trading_service)

    if alert_type_enum == AlertType.STRATEGY:
        return await _get_strategy_metric(rule, config, backtest_service)

    return None


async def _get_account_metric(
    rule: AlertRule,
    config: dict[str, Any],
    paper_trading_service,
    live_trading_service,
) -> float | None:
    """Resolve account-level metric value."""
    metric = str(config.get("metric", "cash"))
    account_id = config.get("account_id")
    if account_id:
        account = await paper_trading_service.get_account(account_id)
        if not account:
            return None
        if metric == "cash":
            return float(account.current_cash)
        if metric in ("value", "equity"):
            return float(account.total_equity)
        return None

    live_task_id = config.get("live_task_id")
    if live_task_id:
        status = await live_trading_service.get_task_status(rule.user_id, live_task_id)
        if not status:
            return None
        if metric == "cash":
            return float(status.get("cash", 0.0))
        if metric in ("value", "equity"):
            return float(status.get("value", 0.0))
        return None

    return None


async def _get_position_metric(
    rule: AlertRule,
    config: dict[str, Any],
    paper_trading_service,
    live_trading_service,
) -> float | None:
    """Resolve position-level metric value."""
    metric = str(config.get("metric", "unrealized_pnl"))
    symbol = config.get("symbol")
    if not symbol:
        return None

    account_id = config.get("account_id")
    if account_id:
        positions, _ = await paper_trading_service.list_positions(
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
        status = await live_trading_service.get_task_status(rule.user_id, live_task_id)
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

    return None


async def _get_strategy_metric(
    rule: AlertRule,
    config: dict[str, Any],
    backtest_service,
) -> float | None:
    """Resolve strategy-level metric value."""
    metric = str(config.get("metric", "sharpe_ratio"))
    backtest_task_id = config.get("backtest_task_id")
    if backtest_task_id:
        result = await backtest_service.get_result(
            backtest_task_id, user_id=rule.user_id
        )
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
