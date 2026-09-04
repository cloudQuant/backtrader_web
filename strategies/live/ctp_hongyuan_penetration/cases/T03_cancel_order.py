#!/usr/bin/env python
"""T03: 验证能正常下达撤单指令"""
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
from common.runtime import create_broker, run_with_timeout, started_store

import backtrader as bt
from backtrader.feeds.btapifeed import BtApiFeed

CASE_META = {
    "case_id": "T03",
    "case_name": "验证能正常下达撤单指令",
    "category": "基础交易功能",
    "optional": False,
}


def run(report_dir):
    """Run T03 cancel order test case.

    Args:
        report_dir: Directory for test reports and logs.
    """
    env_key = cfg.get_env_key()
    symbol = cfg.get_order_symbol()
    log_dir = str(report_dir / "logs")

    with CaseTimer(CASE_META["case_id"], CASE_META["case_name"], env_key) as timer:
        try:
            with started_store(env_key, stop_on_exit=False) as (store, config, ek):
                seed_bar = {
                    "datetime": dt.datetime.now().replace(microsecond=0),
                    "open": 3000.0,
                    "high": 3000.0,
                    "low": 3000.0,
                    "close": 3000.0,
                    "volume": 1.0,
                    "openinterest": 0.0,
                }
                broker = create_broker(store)
                data = BtApiFeed(
                    store=store,
                    dataname=symbol,
                    timeframe=bt.TimeFrame.Seconds,
                    compression=5,
                    backfill_start=False,
                    historical_bars=[seed_bar],
                )
                cerebro = bt.Cerebro()
                cerebro.setbroker(broker)
                cerebro.adddata(data)
                cerebro.addobserver(
                    bt.observers.TradeLogger,
                    log_dir=log_dir,
                    log_format="json",
                )

                class CancelOrderStrategy(bt.Strategy):
                    """Strategy for testing cancel order functionality."""

                    def __init__(self):
                        """Initialize cancel order strategy."""
                        self.bar_count = 0
                        self.order = None
                        self.order_statuses = []
                        self.submit_status = ""
                        self.cancel_called = False
                        self.cancel_status = ""

                    def notify_order(self, order):
                        """Handle order status updates.

                        Args:
                            order: Order instance.
                        """
                        status = order.getstatusname()
                        self.order_statuses.append(status)
                        print(f"  order_notify: ref={order.ref} status={status}")
                        if status in ("Canceled", "Rejected", "Completed"):
                            self.cerebro.runstop()

                    def next(self):
                        """Process bar and submit cancel order."""
                        self.bar_count += 1
                        if self.order is not None:
                            return
                        limit_price = float(self.data.close[0])
                        self.order = self.buy(
                            size=1, exectype=bt.Order.Limit,
                            price=limit_price, offset="open",
                        )
                        if self.order is not None:
                            self.submit_status = self.order.getstatusname()
                            print(
                                "  buy() returned:"
                                f" status={self.submit_status}"
                                f" error_code={getattr(self.order.info, 'error_code', '')}"
                                f" error_msg={getattr(self.order.info, 'error_msg', '')}"
                            )
                            print(f"  提交后立即撤单: ref={self.order.ref}")
                            self.cancel_called = True
                            self.cancel(self.order)
                            self.cancel_status = self.order.getstatusname()
                            print(f"  order status after cancel(): {self.cancel_status}")

                cerebro.addstrategy(CancelOrderStrategy)
                results = run_with_timeout(cerebro, timeout_seconds=25)

                strat = results[0] if results else None
                if not strat or strat.bar_count <= 0:
                    return timer.blocked_result("未能通过种子 bar 触发撤单流程")

                event_types = helpers.collect_log_event_types(log_dir)
                assert strat.cancel_called, "Cancel path was not executed"
                if "order_status_completed" in event_types:
                    return timer.fail_result(
                        "撤单测试订单在收到柜台撤单终态前成交",
                        evidence=helpers.collect_evidence_files(log_dir),
                        details={
                            "events": sorted(event_types),
                            "submit_status": strat.submit_status,
                            "cancel_status": strat.cancel_status,
                            "order_statuses": strat.order_statuses,
                        },
                    )
                if "order_status_canceled" not in event_types:
                    return timer.blocked_result(
                        "仅观察到本地撤单请求，未收到柜台撤单终态回报",
                        next_action="确认仿真账户可用资金和柜台订单回报后重试",
                        evidence=helpers.collect_evidence_files(log_dir),
                        details={
                            "events": sorted(event_types),
                            "submit_status": strat.submit_status,
                            "cancel_status": strat.cancel_status,
                            "order_statuses": strat.order_statuses,
                        },
                    )
                print("✓ 撤单指令已成功下达并确认 order_cancel_request")

                evidence = helpers.collect_evidence_files(log_dir)
                return timer.pass_result(
                    evidence=evidence,
                    details={
                        "events": sorted(event_types),
                        "submit_status": strat.submit_status,
                        "cancel_status": strat.cancel_status,
                        "order_statuses": strat.order_statuses,
                    },
                )

        except Exception as exc:
            return timer.fail_result(str(exc), evidence=helpers.collect_evidence_files(log_dir))


if __name__ == "__main__":
    from common.runtime import case_main
    case_main(run, CASE_META)
