"""恐惧贪婪情绪指标策略 (Fear & Greed Sentiment Strategy)

基于Fear & Greed情绪指数的逆向投资策略:
- Fear & Greed < 10 (极端恐惧) -> 买入
- Fear & Greed > 94 (极端贪婪) -> 卖出

Author: yunjinqi
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt


class SPYFearGreedData(bt.feeds.GenericCSVData):
    """加载SPY价格数据和Fear & Greed情绪指标的自定义数据源

    该数据源扩展了GenericCSVData，用于加载SPY（标普500ETF）历史价格数据
    以及三个额外的情绪指标:
    - Put/Call Ratio: 期权市场情绪指标
    - Fear & Greed Index: 市场情绪指标（0-100刻度）
    - VIX: CBOE波动率指数

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


class FearGreedStrategy(bt.Strategy):
    """基于Fear & Greed情绪指数的逆向投资策略

    该策略采用均值回归方法，基于极端市场情绪进行交易:
    - 当Fear & Greed指数显示极端恐惧时买入SPY（< 10）
    - 当Fear & Greed指数显示极端贪婪时卖出SPY（> 94）

    基本假设是极端情绪时期往往先于市场反转，
    因此在过度恐惧时买入（市场超卖），
    在过度贪婪时卖出（市场超买）。
    """

    params = (
        ("fear_threshold", 10),   # 恐惧阈值，低于此值买入
        ("greed_threshold", 94),  # 贪婪阈值，高于此值卖出
    )

    def log(self, txt, dt=None, force=False):
        """记录日志"""
        if not force:
            return
        dt = dt or self.datas[0].datetime.datetime(0)
        print(f"{dt.isoformat()}, {txt}")

    def __init__(self):
        """初始化策略"""
        # 记录统计
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        self.sum_profit = 0.0
        self.win_count = 0
        self.loss_count = 0

        # 获取数据引用
        self.data0 = self.datas[0]
        self.fear_greed = self.data0.fear_greed
        self.close = self.data0.close

    def notify_trade(self, trade):
        """处理交易完成通知"""
        if not trade.isclosed:
            return
        if trade.pnl > 0:
            self.win_count += 1
        else:
            self.loss_count += 1
        self.sum_profit += trade.pnl
        self.log(f"Trade completed: Gross profit={trade.pnl:.2f}, Net profit={trade.pnlcomm:.2f}, Cumulative={self.sum_profit:.2f}")

    def notify_order(self, order):
        """处理订单状态变化"""
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            if order.isbuy():
                self.log(f"Buy executed: Price={order.executed.price:.2f}, Size={order.executed.size}")
            else:
                self.log(f"Sell executed: Price={order.executed.price:.2f}, Size={order.executed.size}")
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f"Order status: {order.Status[order.status]}")

    def next(self):
        """每个bar执行交易逻辑"""
        self.bar_num += 1

        # 计算可买入数量
        size = int(self.broker.getcash() / self.close[0])

        # 极度恐惧时买入
        if self.fear_greed[0] < self.p.fear_threshold and not self.position:
            if size > 0:
                self.buy(size=size)
                self.buy_count += 1

        # 极度贪婪时卖出
        if self.fear_greed[0] > self.p.greed_threshold and self.position.size > 0:
            self.sell(size=self.position.size)
            self.sell_count += 1

    def stop(self):
        """策略执行完成时输出最终统计"""
        total_trades = self.win_count + self.loss_count
        win_rate = (self.win_count / total_trades * 100) if total_trades > 0 else 0
        self.log(
            f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}, "
            f"wins={self.win_count}, losses={self.loss_count}, win_rate={win_rate:.2f}%, profit={self.sum_profit:.2f}",
            force=True
        )
