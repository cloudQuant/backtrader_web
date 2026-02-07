"""Hans123日内突破策略

基于开盘后N根K线的高低点进行突破交易:
- MA向上且价格>MA且价格突破上轨 -> 做多
- MA向下且价格<MA且价格突破下轨 -> 做空
- 收盘前(14:55)平掉所有持仓

Author: yunjinqi
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
from backtrader.comminfo import ComminfoFuturesPercent


class Hans123Strategy(bt.Strategy):
    """Hans123日内突破策略（带均线过滤）

    使用开盘后N根K线的高低点作为突破区间:
    - MA向上 + 价格>MA + 价格突破上轨 -> 做多
    - MA向下 + 价格<MA + 价格突破下轨 -> 做空
    - 收盘前平仓
    """
    author = 'yunjinqi'
    params = (
        ("ma_period", 200),
        ("bar_num", 2),
    )

    def log(self, txt, dt=None):
        """记录日志"""
        dt = dt or bt.num2date(self.datas[0].datetime[0])
        print('{}, {}'.format(dt.isoformat(), txt))

    def __init__(self):
        """初始化策略"""
        self.bar_num = 0
        self.day_bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        # 计算均线指标
        self.ma_value = bt.indicators.SMA(self.datas[0].close, period=self.p.ma_period)
        # 保存交易状态
        self.marketposition = 0
        # 保存当前交易日的最高价、最低价、收盘价
        self.now_high = 0
        self.now_low = 999999999
        self.now_close = None
        self.now_open = None
        # 上下轨
        self.upper_line = None
        self.lower_line = None

    def prenext(self):
        """在指标最小周期到达前调用"""
        pass

    def next(self):
        """主策略逻辑，每个bar调用一次"""
        self.current_datetime = bt.num2date(self.datas[0].datetime[0])
        self.current_hour = self.current_datetime.hour
        self.current_minute = self.current_datetime.minute
        self.day_bar_num += 1
        self.bar_num += 1
        data = self.datas[0]

        # 更新最高价、最低价、收盘价
        self.now_high = max(self.now_high, data.high[0])
        self.now_low = min(self.now_low, data.low[0])
        if self.now_close is None:
            self.now_open = data.open[0]
        self.now_close = data.close[0]

        # 如果当前bar数量等于计算高低点的时间周期，计算上下轨价格
        if self.day_bar_num == self.p.bar_num:
            self.upper_line = self.now_high
            self.lower_line = self.now_low

        # 如果是当前交易日的最后一分钟
        if self.current_hour == 15:
            self.now_high = 0
            self.now_low = 999999999
            self.now_close = None
            self.day_bar_num = 0

        # Hans123改进版: 使用均线过滤交易
        if len(data.close) > self.p.ma_period and self.day_bar_num >= self.p.bar_num:
            # 开始交易
            open_time_1 = self.current_hour >= 21 and self.current_hour <= 23
            open_time_2 = self.current_hour >= 9 and self.current_hour <= 11
            # 开仓
            if open_time_1 or open_time_2:
                # 开多仓
                if self.marketposition == 0 and self.ma_value[0] > self.ma_value[-1] and data.close[0] > self.ma_value[0] and data.close[0] > self.upper_line:
                    info = self.broker.getcommissioninfo(data)
                    symbol_multi = info.p.mult
                    close = data.close[0]
                    total_value = self.broker.getvalue()
                    lots = total_value / (symbol_multi * close)
                    self.buy(data, size=lots)
                    self.buy_count += 1
                    self.marketposition = 1
                # 开空仓
                if self.marketposition == 0 and self.ma_value[0] < self.ma_value[-1] and data.close[0] < self.ma_value[0] and data.close[0] < self.lower_line:
                    info = self.broker.getcommissioninfo(data)
                    symbol_multi = info.p.mult
                    close = data.close[0]
                    total_value = self.broker.getvalue()
                    lots = total_value / (symbol_multi * close)
                    self.sell(data, size=lots)
                    self.sell_count += 1
                    self.marketposition = -1
            # 平仓
            if self.marketposition != 0 and self.current_hour == 14 and self.current_minute == 55:
                self.close(data)
                self.marketposition = 0

    def notify_order(self, order):
        """订单状态变化时调用"""
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status == order.Completed:
            if order.isbuy():
                self.log(f"BUY: price={order.executed.price:.2f}")
            else:
                self.log(f"SELL: price={order.executed.price:.2f}")

    def notify_trade(self, trade):
        """交易完成时调用"""
        if trade.isclosed:
            self.log(f"Trade completed: pnl={trade.pnl:.2f}, pnlcomm={trade.pnlcomm:.2f}")

    def stop(self):
        """回测结束时调用"""
        self.log(f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}")


class RbPandasFeed(bt.feeds.PandasData):
    """螺纹钢期货Pandas数据源"""
    params = (
        ('datetime', None),
        ('open', 0),
        ('high', 1),
        ('low', 2),
        ('close', 3),
        ('volume', 4),
        ('openinterest', 5),
    )
