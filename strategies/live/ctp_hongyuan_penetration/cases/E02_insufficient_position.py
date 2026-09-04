#!/usr/bin/env python
"""E02: 验证系统能接收并展示柜台返回的持仓不足错误码"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SUITE = _HERE.parent
_REPO = _SUITE.parents[2]
for _p in (_SUITE, _REPO):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from common import config as cfg, helpers
from common.result import CaseTimer
from common.runtime import (
    create_cerebro,
    record_runtime_events,
    run_with_timeout,
    started_store,
    wait_for_live_market_price,
)

import backtrader as bt

CASE_META = {
    "case_id": "E02",
    "case_name": "验证系统能接收并展示柜台返回的持仓不足错误码",
    "category": "错误提示",
    "optional": False,
}
PROBE_ORDER_SIZE = 1
REMOTE_RESPONSE_TIMEOUT_SECONDS = 35
_INSUFFICIENT_POSITION_TERMS = (
    "持仓不足",
    "可平持仓不足",
    "可用持仓不足",
    "仓位不足",
    "insufficient position",
    "not enough position",
)


def _first_value(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _normalize_remote_counter_error(event):
    details = event.get("details") if isinstance(event.get("details"), dict) else {}
    error_id = _first_value(
        event.get("ErrorID"),
        event.get("error_code"),
        details.get("ErrorID"),
        details.get("ErrorId"),
    )
    error_msg = _first_value(
        event.get("ErrorMsg"),
        event.get("error_msg"),
        details.get("ErrorMsg"),
    )
    status_msg = _first_value(
        event.get("StatusMsg"),
        event.get("status_msg"),
        event.get("status_message"),
        details.get("StatusMsg"),
        error_msg,
    )
    if not (str(error_id or "").isdigit() or "CTP" in str(error_msg or "")):
        return None
    return {
        "event_type": "order_reject_remote",
        "order_ref": _first_value(event.get("order_ref"), details.get("order_ref")),
        "ErrorID": str(error_id),
        "ErrorMsg": str(error_msg),
        "StatusMsg": str(status_msg),
        "source_event": event,
    }


def _matches_insufficient_position_error(error):
    """Return whether a counter rejection specifically denotes insufficient position."""
    if not isinstance(error, dict):
        return False
    text = " ".join(
        str(error.get(key) or "") for key in ("ErrorMsg", "StatusMsg", "error_msg")
    ).lower()
    return any(term in text for term in _INSUFFICIENT_POSITION_TERMS)


def _remote_counter_errors_from_log(log_dir):
    errors = []
    for path in sorted(Path(log_dir).glob("*.log")):
        for entry in helpers.read_json_lines(path):
            if entry.get("event_type") not in {"order_reject_remote", "order_rejected"}:
                continue
            normalized = _normalize_remote_counter_error(entry)
            if normalized is not None:
                errors.append(normalized)
    return errors


def run(report_dir):
    """Trigger a counter-side insufficient-position rejection."""
    env_key = cfg.get_env_key()
    symbol = cfg.get_order_symbol()
    log_dir = str(report_dir / "logs")

    with CaseTimer(CASE_META["case_id"], CASE_META["case_name"], env_key) as timer:
        try:
            with started_store(env_key, stop_on_exit=False) as (store, config, ek):
                current_positions = store.get_positions()
                long_volume = sum(
                    float(pos.get("volume") or 0)
                    for pos in current_positions or []
                    if pos.get("instrument") == symbol and pos.get("direction") == "long"
                )
                if long_volume > 0:
                    return timer.blocked_result(
                        f"账户已有 {symbol} 多仓 {long_volume}，为避免误平仓跳过",
                        evidence=helpers.collect_evidence_files(log_dir),
                    )

                market_price = wait_for_live_market_price(store, symbol)
                seed_bar = {
                    "datetime": dt.datetime.now().replace(microsecond=0),
                    "open": market_price,
                    "high": market_price,
                    "low": market_price,
                    "close": market_price,
                    "volume": 1.0,
                    "openinterest": 0.0,
                }
                store.set_history(symbol, [seed_bar])
                cerebro = create_cerebro(
                    store,
                    symbol=symbol,
                    bar_seconds=5,
                    with_trade_logger=True,
                    log_dir=log_dir,
                    historical_bars=[seed_bar],
                    validation_enabled=False,
                    remote_negative_close_probe=True,
                )

                class PositionCheckStrategy(bt.Strategy):
                    """Strategy for testing insufficient position rejection."""

                    def __init__(self):
                        """Initialize position check strategy."""
                        self.bar_count = 0
                        self.checked = False
                        self.position_size = None
                        self.rejected = False
                        self.completed = False
                        self.store_events = []
                        self.order_statuses = []

                    def notify_store(self, msg, *args, **kwargs):
                        event = kwargs.get("event")
                        if isinstance(event, dict):
                            self.store_events.append(event)
                            if event.get("event_type") == "order_reject_remote":
                                self.rejected = True
                                self.cerebro.runstop()

                    def notify_order(self, order):
                        """Handle order status updates.

                        Args:
                            order: Order instance.
                        """
                        status = order.getstatusname()
                        self.order_statuses.append({"ref": order.ref, "status": status})
                        print(f"  order_notify: ref={order.ref} status={status}")
                        if order.status == bt.Order.Rejected:
                            self.rejected = True
                            self.cerebro.runstop()
                        if order.status == bt.Order.Completed:
                            self.completed = True
                            self.cerebro.runstop()

                    def next(self):
                        """Process bar and check position."""
                        self.bar_count += 1
                        if self.checked:
                            return
                        self.checked = True
                        # Query current position from broker
                        pos = self.broker.getposition(self.data)
                        self.position_size = pos.size if pos else 0
                        print(f"  当前持仓: size={self.position_size}")
                        ref_price = float(self.data.close[0])
                        close_price = ref_price
                        print(f"  尝试提交无持仓平今卖单: size=1 price={close_price}")
                        self.sell(
                            size=PROBE_ORDER_SIZE, exectype=bt.Order.Limit,
                            price=close_price, offset="close_today",
                        )

                cerebro.addstrategy(PositionCheckStrategy)
                results = run_with_timeout(
                    cerebro,
                    timeout_seconds=REMOTE_RESPONSE_TIMEOUT_SECONDS,
                )
                runtime_event_types = record_runtime_events(
                    store.get_notifications(),
                    Path(log_dir) / "system.log",
                )

                strat = results[0] if results else None
                if not strat or strat.bar_count <= 0:
                    return timer.blocked_result(
                        "未能通过种子 bar 触发持仓不足校验流程",
                        next_action="检查 BtApiFeed 历史 bar 加载流程",
                    )

                event_types = {e.get("event_type") for e in strat.store_events}
                event_types.update(runtime_event_types)
                event_types.update(helpers.collect_log_event_types(log_dir))
                local_rejection = (
                    strat.rejected
                    or "order_reject_local" in runtime_event_types
                    or "order_validation_rejected" in runtime_event_types
                )
                remote_errors = []
                for event in strat.store_events:
                    if event.get("event_type") == "order_reject_remote":
                        normalized = _normalize_remote_counter_error(event)
                        if normalized is not None:
                            remote_errors.append(normalized)
                remote_errors.extend(_remote_counter_errors_from_log(log_dir))
                expected_remote_errors = [
                    error for error in remote_errors if _matches_insufficient_position_error(error)
                ]
                if remote_errors:
                    event_types.add("order_reject_remote")
                error_details = expected_remote_errors[-1] if expected_remote_errors else (
                    remote_errors[-1] if remote_errors else {}
                )
                details = {
                    "events": sorted(event_types),
                    "position_size": strat.position_size,
                    "order_statuses": strat.order_statuses,
                    "local_rejection": local_rejection,
                    "order_reject_remote": bool(remote_errors),
                    "expected_remote_error": bool(expected_remote_errors),
                    "remote_errors": remote_errors,
                    "ErrorID": error_details.get("ErrorID"),
                    "ErrorMsg": error_details.get("ErrorMsg"),
                    "StatusMsg": error_details.get("StatusMsg"),
                }

            if expected_remote_errors and strat.position_size == 0 and not strat.completed:
                print("✓ 已收到柜台持仓不足远端拒单")
                return timer.pass_result(
                    evidence=helpers.collect_evidence_files(log_dir),
                    details=details,
                )

            if local_rejection and not remote_errors:
                return timer.blocked_result(
                    "本地持仓校验已拒绝订单，未向柜台发送请求，无法验证柜台持仓不足错误",
                    next_action="在允许该专用负向测试透传至柜台的隔离环境中重跑",
                    evidence=helpers.collect_evidence_files(log_dir),
                    details=details,
                )

            if remote_errors:
                return timer.fail_result(
                    "收到柜台拒单，但错误语义并非持仓不足",
                    evidence=helpers.collect_evidence_files(log_dir),
                    details=details,
                )

            return timer.fail_result(
                "未观察到柜台持仓不足远端拒单",
                evidence=helpers.collect_evidence_files(log_dir),
                details=details,
            )

        except Exception as exc:
            return timer.fail_result(str(exc), evidence=helpers.collect_evidence_files(log_dir))


if __name__ == "__main__":
    from common.runtime import case_main
    case_main(run, CASE_META)
