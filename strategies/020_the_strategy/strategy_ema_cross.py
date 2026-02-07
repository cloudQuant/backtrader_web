"""EMA双均线交叉策略 (EMA Dual Moving Average Crossover Strategy)

基于双EMA交叉的交易策略:
- 死叉（快线下穿慢线）-> 开空仓
- 金叉（快线上穿慢线）-> 开多仓
- 使用多周期数据（5分钟+日线）进行过滤

Author: yunjinqi
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt


class EmaCrossStrategy(bt.Strategy):
    """EMA双均线交叉策略，支持多周期

    该策略使用两个不同周期的EMA产生交易信号:
    - 快线上穿慢线（金叉）→ 开多仓
    - 快线下穿慢线（死叉）→ 开空仓
    - 使用日线数据过滤交易时机

    策略参数:
        fast_period: 快线EMA周期（默认80）
        slow_period: 慢线EMA周期（默认200）
        short_size: 空头仓位规模（默认2）
        long_size: 多头仓位规模（默认1）

    数据源:
        datas[0]: 5分钟bar数据（用于信号生成）
        datas[1]: 日线数据（用于日期同步过滤，可选）
    """

    params = (
        ("fast_period", 80),
        ("slow_period", 200),
        ("short_size", 2),
        ("long_size", 1),
    )

    def log(self, txt, dt=None, force=False):
        """记录日志"""
        if not force:
            return
        dt = dt or self.datas[0].datetime.datetime(0)
        print(f"{dt.isoformat()}, {txt}")

    def __init__(self):
        """初始化策略指标和状态变量"""
        # 初始化统计跟踪
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.sum_profit = 0.0
        self.win_count = 0
        self.loss_count = 0

        # 获取数据引用 - 通过datas列表进行标准访问
        self.minute_data = self.datas[0]  # 5分钟数据（主要）
        self.daily_data = self.datas[1] if len(self.datas) > 1 else None  # 日线数据（过滤）

        # 在分钟数据上计算EMA指标
        self.fast_ema = bt.ind.EMA(self.minute_data, period=self.p.fast_period)
        self.slow_ema = bt.ind.EMA(self.minute_data, period=self.p.slow_period)
        self.ema_cross = bt.indicators.CrossOver(self.fast_ema, self.slow_ema)

        # 如果日线数据存在，在日线数据上计算SMA用于过滤
        if self.daily_data is not None:
            self.sma_day = bt.ind.SMA(self.daily_data, period=6)

    def notify_trade(self, trade):
        """处理交易完成事件并更新统计"""
        if not trade.isclosed:
            return

        # 更新胜负统计
        if trade.pnl > 0:
            self.win_count += 1
        else:
            self.loss_count += 1

        # 跟踪累积利润
        self.sum_profit += trade.pnl
        self.log(
            f"Trade completed: Gross profit={trade.pnl:.2f}, "
            f"Net profit={trade.pnlcomm:.2f}, Cumulative={self.sum_profit:.2f}"
        )

    def notify_order(self, order):
        """处理订单状态更新并记录执行"""
        # 跳过待处理订单
        if order.status in [order.Submitted, order.Accepted]:
            return

        # 记录已完成的订单
        if order.status == order.Completed:
            if order.isbuy():
                self.log(
                    f"Buy executed: Price={order.executed.price:.2f}, "
                    f"Size={order.executed.size}"
                )
            else:
                self.log(
                    f"Sell executed: Price={order.executed.price:.2f}, "
                    f"Size={order.executed.size}"
                )
        # 记录订单问题
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f"Order status: {order.Status[order.status]}")

    def next(self):
        """为每个bar执行交易逻辑"""
        self.bar_num += 1

        # 获取EMA交叉信号历史（最近80根bar）
        # CrossOver在金叉时返回1，死叉时返回-1，其他情况返回0
        crosslist = [i for i in self.ema_cross.get(size=80) if i == 1 or i == -1]

        # 检查日期同步（如果日线数据存在）
        # 只在两个数据馈都有同一天数据时交易，防止不匹配
        date_synced = True
        if self.daily_data is not None:
            date_synced = (
                self.minute_data.datetime.date(0) == self.daily_data.datetime.date(0)
            )

        # 开仓逻辑（没有当前持仓）
        if not self.position and date_synced:
            # 交叉信号总和表示总体趋势方向
            if len(crosslist) > 0:
                signal_sum = sum(crosslist)

                # 死叉信号 - 开空仓
                if signal_sum == -1:
                    self.sell(data=self.minute_data, size=self.p.short_size)
                    self.sell_count += 1
                # 金叉信号 - 开多仓
                elif signal_sum == 1:
                    self.buy(data=self.minute_data, size=self.p.long_size)
                    self.buy_count += 1

        # 平仓逻辑（有持仓）
        elif self.position and date_synced:
            signal_sum = sum(crosslist) if len(crosslist) > 0 else 0

            # 持有空仓时，金叉平仓
            if self.position.size < 0 and signal_sum == 1:
                self.close()
                self.buy_count += 1
            # 持有多仓时，死叉平仓
            elif self.position.size > 0 and signal_sum == -1:
                self.close()
                self.sell_count += 1

    def stop(self):
        """策略完成时输出最终统计"""
        total_trades = self.win_count + self.loss_count
        win_rate = (self.win_count / total_trades * 100) if total_trades > 0 else 0

        self.log(
            f"bar_num={self.bar_num}, buy_count={self.buy_count}, "
            f"sell_count={self.sell_count}, wins={self.win_count}, "
            f"losses={self.loss_count}, win_rate={win_rate:.2f}%, "
            f"profit={self.sum_profit:.2f}",
            force=True
        )
