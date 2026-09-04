#!/usr/bin/env python
"""E01: 验证系统能接收并展示柜台返回的资金不足错误码"""
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
    "case_id": "E01",
    "case_name": "验证系统能接收并展示柜台返回的资金不足错误码",
    "category": "错误提示",
    "optional": False,
}
PROBE_ORDER_SIZE = 1
PROBE_ORDER_COUNT = 1
REMOTE_RESPONSE_TIMEOUT_SECONDS = 35
_INSUFFICIENT_FUNDS_TERMS = (
    "资金不足",
    "可用资金不足",
    "保证金不足",
    "余额不足",
    "insufficient funds",
    "insufficient margin",
)
_FUNDS_PRECONDITION_TERMS = (
    "结算组数据没有同步",
    "结算数据没有同步",
    "settlement group data is not synchronized",
    "settlement data is not synchronized",
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
    explicit_remote_rejection = event.get("event_type") == "order_reject_remote"
    if not (
        explicit_remote_rejection
        or str(error_id or "").isdigit()
        or "CTP" in str(error_msg or "")
    ):
        return None
    return {
        "event_type": "order_reject_remote",
        "order_ref": _first_value(event.get("order_ref"), details.get("order_ref")),
        "ErrorID": str(error_id),
        "ErrorMsg": str(error_msg),
        "StatusMsg": str(status_msg),
        "source_event": event,
    }


def _matches_insufficient_funds_error(error):
    """Return whether a counter rejection specifically denotes insufficient funds."""
    if not isinstance(error, dict):
        return False
    text = " ".join(
        str(error.get(key) or "") for key in ("ErrorMsg", "StatusMsg", "error_msg")
    ).lower()
    return any(term in text for term in _INSUFFICIENT_FUNDS_TERMS)


def _matches_funds_precondition_error(error):
    """Return whether CTP stopped before it could evaluate account funds."""
    if not isinstance(error, dict):
        return False
    text = " ".join(
        str(error.get(key) or "") for key in ("ErrorMsg", "StatusMsg", "error_msg")
    ).lower()
    return any(term in text for term in _FUNDS_PRECONDITION_TERMS)


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
    """Trigger a counter-side insufficient-funds rejection without filling."""
    env_key = cfg.get_env_key()
    symbol = cfg.get_order_symbol()
    log_dir = str(report_dir / "logs")

    with CaseTimer(CASE_META["case_id"], CASE_META["case_name"], env_key) as timer:
        try:
            with started_store(env_key) as (store, config, ek):
                market_price = wait_for_live_market_price(store, symbol)
                now = dt.datetime.now().replace(microsecond=0)
                seed_bar = {
                    "datetime": now,
                    "open": market_price,
                    "high": market_price,
                    "low": market_price,
                    "close": market_price,
                    "volume": 1.0,
                    "openinterest": 0.0,
                }
                cerebro = create_cerebro(
                    store,
                    symbol=symbol,
                    bar_seconds=5,
                    with_trade_logger=True,
                    log_dir=log_dir,
                    validation_enabled=False,
                    historical_bars=[seed_bar],
                )

                class InsufficientFundsStrategy(bt.Strategy):
                    """Strategy that freezes margin until the counter rejects."""

                    def __init__(self):
                        self.bar_count = 0
                        self.orders = []
                        self.store_events = []
                        self.order_statuses = []
                        self.rejected = False
                        self.completed = False
                        self.cleanup_started = False
                        self.limit_price = None

                    def notify_store(self, msg, *args, **kwargs):
                        event = kwargs.get("event")
                        if isinstance(event, dict):
                            self.store_events.append(event)
                            if event.get("event_type") == "order_reject_remote":
                                self.rejected = True
                                self.cleanup_started = True
                                for order in list(self.orders):
                                    if order is not None and order.alive():
                                        self.cancel(order)

                    def notify_order(self, order):
                        status = order.getstatusname()
                        self.order_statuses.append({"ref": order.ref, "status": status})
                        print(f"  order_notify: ref={order.ref} status={status}")
                        if order.status == bt.Order.Rejected:
                            self.rejected = True
                            self.cleanup_started = True
                            for pending in list(self.orders):
                                if pending is not None and pending.alive():
                                    self.cancel(pending)
                        if order.status == bt.Order.Completed:
                            self.completed = True
                            self.cerebro.runstop()
                        if self.cleanup_started and all(
                            not item.alive() for item in self.orders if item is not None
                        ):
                            self.cerebro.runstop()

                    def next(self):
                        self.bar_count += 1
                        if self.rejected or self.completed:
                            self.cerebro.runstop()
                            return
                        ref_price = float(self.data.close[0])
                        if self.limit_price is None:
                            self.limit_price = ref_price
                        if not self.orders:
                            print(
                                "  提交一笔当前有效价一手挂单等待柜台资金不足拒单: "
                                f"symbol={symbol} size={PROBE_ORDER_SIZE} "
                                f"price={self.limit_price:.2f}"
                            )
                            for _ in range(PROBE_ORDER_COUNT):
                                order = self.buy(
                                    size=PROBE_ORDER_SIZE,
                                    exectype=bt.Order.Limit,
                                    price=self.limit_price,
                                    offset="open",
                                )
                                if order is not None:
                                    self.orders.append(order)
                            return
                        if not self.cleanup_started:
                            self.cleanup_started = True
                            for order in list(self.orders):
                                if order is not None and order.alive():
                                    self.cancel(order)

                cerebro.addstrategy(InsufficientFundsStrategy)
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
                        "未能通过种子 bar 触发资金不足校验流程",
                        next_action="检查 BtApiFeed 历史 bar 加载流程",
                    )

                event_types = {e.get("event_type") for e in strat.store_events}
                event_types.update(runtime_event_types)
                event_types.update(helpers.collect_log_event_types(log_dir))
                remote_errors = []
                for event in strat.store_events:
                    if event.get("event_type") == "order_reject_remote":
                        normalized = _normalize_remote_counter_error(event)
                        if normalized is not None:
                            remote_errors.append(normalized)
                remote_errors.extend(_remote_counter_errors_from_log(log_dir))
                expected_remote_errors = [
                    error for error in remote_errors if _matches_insufficient_funds_error(error)
                ]
                funds_precondition_errors = [
                    error for error in remote_errors if _matches_funds_precondition_error(error)
                ]
                if remote_errors:
                    event_types.add("order_reject_remote")
                error_details = expected_remote_errors[-1] if expected_remote_errors else (
                    remote_errors[-1] if remote_errors else {}
                )
                observed_order_statuses = {
                    str(item.get("status") or "")
                    for item in strat.order_statuses
                    if isinstance(item, dict)
                }
                passive_probe_cancelled = {
                    "Accepted",
                    "Canceled",
                }.issubset(observed_order_statuses)
                details = {
                    "events": sorted(event_types),
                    "order_statuses": strat.order_statuses,
                    "submitted_orders": len(strat.orders),
                    "order_reject_remote": bool(remote_errors),
                    "expected_remote_error": bool(expected_remote_errors),
                    "funds_precondition_blocked": bool(funds_precondition_errors),
                    "passive_probe_cancelled": passive_probe_cancelled,
                    "remote_errors": remote_errors,
                    "ErrorID": error_details.get("ErrorID"),
                    "ErrorMsg": error_details.get("ErrorMsg"),
                    "StatusMsg": error_details.get("StatusMsg"),
                }

            if expected_remote_errors and not strat.completed:
                print("✓ 已收到柜台资金/保证金相关远端拒单")
                return timer.pass_result(
                    evidence=helpers.collect_evidence_files(log_dir),
                    details=details,
                )

            if remote_errors:
                if funds_precondition_errors:
                    return timer.blocked_result(
                        "柜台在资金校验前因结算数据状态拒绝受控委托，"
                        "未进入资金不足语义路径",
                        next_action=(
                            "等待宏源仿真柜台结算数据同步完成后重跑，"
                            "并使用专用低余额仿真账户验证资金不足错误"
                        ),
                        evidence=helpers.collect_evidence_files(log_dir),
                        details=details,
                    )
                return timer.fail_result(
                    "收到柜台拒单，但错误语义并非资金不足",
                    evidence=helpers.collect_evidence_files(log_dir),
                    details=details,
                )

            if passive_probe_cancelled:
                return timer.blocked_result(
                    "柜台接受并允许撤销受控一手被动委托，未产生资金不足远端拒单",
                    next_action=(
                        "使用会在报单阶段拒绝的专用低余额仿真账户，"
                        "或明确授权更高风险的激进资金不足探针后重跑"
                    ),
                    evidence=helpers.collect_evidence_files(log_dir),
                    details=details,
                )

            return timer.fail_result(
                "未观察到柜台资金不足远端拒单",
                evidence=helpers.collect_evidence_files(log_dir),
                details=details,
            )

        except Exception as exc:
            return timer.fail_result(str(exc), evidence=helpers.collect_evidence_files(log_dir))


if __name__ == "__main__":
    from common.runtime import case_main
    case_main(run, CASE_META)
