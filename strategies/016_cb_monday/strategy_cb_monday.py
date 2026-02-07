"""可转债周五高溢价轮动策略 (Convertible Bond Friday Rotation Strategy)

每周五买入溢价率最高的3只可转债:
- 每周五平掉现有持仓
- 选择溢价率最高的3只可转债买入
- 持有到下周五重新轮动

Author: yunjinqi
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
from backtrader.comminfo import ComminfoFuturesPercent


class ExtendPandasFeed(bt.feeds.PandasData):
    """扩展的可转债Pandas数据源（带溢价率）"""
    params = (
        ('datetime', None),
        ('open', 0),
        ('high', 1),
        ('low', 2),
        ('close', 3),
        ('volume', 4),
        ('openinterest', -1),
        ('premium_rate', 5),
    )
    lines = ('premium_rate',)


class ConvertibleBondFridayRotationStrategy(bt.Strategy):
    """可转债周五高溢价轮动策略

    每周五:
    - 平掉现有持仓
    - 买入溢价率最高的3只可转债
    - 持有到下周五
    """
    author = 'yunjinqi'
    params = (
        ("hold_num", 3),
    )

    def log(self, txt, dt=None):
        """记录日志"""
        dt = dt or bt.num2date(self.datas[0].datetime[0])
        print('{}, {}'.format(dt.isoformat(), txt))

    def __init__(self):
        """初始化策略"""
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.data_order_dict = {}
        self.order_list = []

    def prenext(self):
        """在最小周期到达前调用"""
        self.next()

    def next(self):
        """主策略逻辑，每个bar调用一次"""
        self.bar_num += 1
        self.current_datetime = bt.num2date(self.datas[0].datetime[0])
        total_value = self.broker.get_value()
        available_cash = self.broker.get_cash()

        # 如果今天是周五，开始下单平掉现有持仓并准备新订单
        today = self.current_datetime.weekday() + 1

        if today == 5:
            # 平掉现有持仓
            for data, order in self.order_list:
                size = self.getposition(data).size
                if size > 0:
                    self.close(data)
                    self.sell_count += 1
                if size == 0:
                    self.cancel(order)
            self.order_list = []

            # 收集当前可交易的可转债
            result = []
            for data in self.datas[1:]:
                data_datetime = bt.num2date(data.datetime[0])
                if data_datetime == self.current_datetime:
                    data_name = data._name
                    premium_rate = data.premium_rate[0]
                    result.append([data, premium_rate])

            # 按溢价率排序
            sorted_result = sorted(result, key=lambda x: x[1])

            # 买入溢价率最高的
            for data, _ in sorted_result[-self.p.hold_num:]:
                close_price = data.close[0]
                total_value = self.broker.getvalue()
                plan_tobuy_value = 0.1 * total_value
                lots = 10 * int(plan_tobuy_value / (close_price * 10))
                if lots > 0:
                    order = self.buy(data, size=lots)
                    self.buy_count += 1
                    self.order_list.append([data, order])

    def notify_order(self, order):
        """订单状态变化时调用"""
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.log(f"BUY: {order.p.data._name} price={order.executed.price:.2f}")
            else:
                self.log(f"SELL: {order.p.data._name} price={order.executed.price:.2f}")

    def notify_trade(self, trade):
        """交易完成时调用"""
        if trade.isclosed:
            self.log(f"Trade completed: {trade.getdataname()} pnl={trade.pnl:.2f}")

    def stop(self):
        """回测结束时调用"""
        self.log(f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}")
