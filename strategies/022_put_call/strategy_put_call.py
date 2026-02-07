"""Put/Call比率情绪策略 (Put/Call Ratio Sentiment Strategy)

基于Put/Call比率的逆向投资策略:
- Put/Call > 1.0（市场恐惧） -> 买入
- Put/Call < 0.45（市场贪婪） -> 卖出

Author: yunjinqi
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt


class SPYPutCallData(bt.feeds.GenericCSVData):
    """加载SPY价格数据和情绪指标的自定义数据源

    该数据源扩展了GenericCSVData，用于加载SPY（标普500ETF）历史价格数据
    以及市场情绪指标包括Put/Call比率、Fear & Greed指数和VIX波动率指数。

    CSV文件必须包含以下列（顺序）:
    Date, Open, High, Low, Close, Adj Close, Volume, Put Call, Fear Greed, VIX
    """
    lines = ('put_call', 'fear_greed', 'vix')

    params = (
        ('dtformat', '%Y-%m-%d'),
        ('datetime', 0),
        ('open', 1),
        ('high', 2),
        ('low', 3),
        ('close', 4),
        ('volume', 6),
        ('openinterest', -1),
        ('put_call', 7),
        ('fear_greed', 8),
        ('vix', 9),
    )


class PutCallStrategy(bt.Strategy):
    """基于Put/Call比率的逆向情绪策略

    该策略采用逆向投资方法，使用Put/Call比率作为市场情绪指标:
    - 高比率（> 1.0）表示恐惧 → 买入信号（逆向）
    - 低比率（< 0.45）表示贪婪/乐观 → 卖出信号

    策略假设极端情绪往往先于市场反转，
    允许在人群过度看空或看空时进行逆向定位。
    """

    params = (
        ("high_threshold", 1.0),   # 高阈值，高于此值买入（恐惧）
        ("low_threshold", 0.45),   # 低阈值，低于此值卖出（贪婪）
    )

    def log(self, txt, dt=None, force=False):
        """记录日志"""
        if not force:
            return
        dt = dt or self.datas[0].datetime.datetime(0)
        print(f"{dt.isoformat()}, {txt}")

    def __init__(self):
        """初始化策略属性和数据引用"""
        # 初始化统计计数器
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.sum_profit = 0.0
        self.win_count = 0
        self.loss_count = 0

        # 创建数据引用以便访问
        self.data0 = self.datas[0]
        self.put_call = self.data0.put_call
        self.close = self.data0.close

    def notify_trade(self, trade):
        """处理交易完成事件"""
        if not trade.isclosed:
            return
        if trade.pnl > 0:
            self.win_count += 1
        else:
            self.loss_count += 1
        self.sum_profit += trade.pnl
        self.log(f"Trade completed: gross_profit={trade.pnl:.2f}, net_profit={trade.pnlcomm:.2f}, cumulative={self.sum_profit:.2f}")

    def notify_order(self, order):
        """处理订单状态变化"""
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            if order.isbuy():
                self.log(f"Buy executed: price={order.executed.price:.2f}, size={order.executed.size}")
            else:
                self.log(f"Sell executed: price={order.executed.price:.2f}, size={order.executed.size}")
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f"Order status: {order.Status[order.status]}")

    def next(self):
        """每个bar执行交易逻辑"""
        self.bar_num += 1

        # 根据可用现金计算仓位规模
        size = int(self.broker.getcash() / self.close[0])

        # 买入信号：高Put/Call比率表示市场恐惧（逆向买入）
        if self.put_call[0] > self.p.high_threshold and not self.position:
            if size > 0:
                self.buy(size=size)
                self.buy_count += 1

        # 卖出信号：低Put/Call比率表示市场贪婪（逆向卖出）
        if self.put_call[0] < self.p.low_threshold and self.position.size > 0:
            self.sell(size=self.position.size)
            self.sell_count += 1

    def stop(self):
        """策略执行完成时计算并记录最终统计"""
        total_trades = self.win_count + self.loss_count
        win_rate = (self.win_count / total_trades * 100) if total_trades > 0 else 0
        self.log(
            f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}, "
            f"wins={self.win_count}, losses={self.loss_count}, win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}",
            force=True
        )
