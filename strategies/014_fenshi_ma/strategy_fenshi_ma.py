"""分时均线策略 (TimeLine MA Strategy)

基于时间均价线和均线过滤的日内交易策略:
- MA向上且价格>MA且价格突破时间均价线 -> 做多
- MA向下且价格<MA且价格跌破时间均价线 -> 做空
- 使用追踪止损
- 收盘前(14:55)平掉所有持仓

Author: yunjinqi
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
from backtrader.comminfo import ComminfoFuturesPercent


class TimeLine(bt.Indicator):
    """时间均价线指标

    计算当日收盘价的累积平均值作为时间均价线"""
    lines = ('day_avg_price',)
    params = (("day_end_time", (15, 0, 0)),)

    def __init__(self):
        """初始化时间均价线指标"""
        self.day_close_price_list = []

    def next(self):
        """计算当前bar的时间均价"""
        self.day_close_price_list.append(self.data.close[0])
        self.lines.day_avg_price[0] = sum(self.day_close_price_list) / len(self.day_close_price_list)

        self.current_datetime = bt.num2date(self.data.datetime[0])
        self.current_hour = self.current_datetime.hour
        self.current_minute = self.current_datetime.minute
        day_end_hour, day_end_minute, _ = self.p.day_end_time
        if self.current_hour == day_end_hour and self.current_minute == day_end_minute:
            self.day_close_price_list = []


class TimeLineMaStrategy(bt.Strategy):
    """分时均线策略

    使用时间均价线结合均线进行交易:
    - MA向上 + 价格>MA + 价格突破时间均价线 -> 做多
    - MA向下 + 价格<MA + 价格跌破时间均价线 -> 做空
    - 使用追踪止损
    - 收盘前平仓
    """
    author = 'yunjinqi'
    params = (
        ("ma_period", 200),
        ("stop_mult", 1),
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
        # 时间均价线指标
        self.day_avg_price = TimeLine(self.datas[0])
        self.ma_value = bt.indicators.SMA(self.datas[0].close, period=self.p.ma_period)
        # 交易状态
        self.marketposition = 0
        # 当前交易日的最高价、最低价、收盘价
        self.now_high = 0
        self.now_low = 999999999
        self.now_close = None
        self.now_open = None
        # 追踪止损订单
        self.stop_order = None

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
        if self.current_hour == 15:
            self.now_high = 0
            self.now_low = 999999999
            self.now_close = None
            self.day_bar_num = 0

        # 初始化持仓状态
        size = self.getposition(data).size
        if size == 0:
            self.marketposition = 0
            if self.stop_order is not None:
                self.broker.cancel(self.stop_order)
                self.stop_order = None

        # 分时均线策略
        if len(data.close) > self.p.ma_period:
            # 开始交易
            open_time_1 = self.current_hour >= 21 and self.current_hour <= 23
            open_time_2 = self.current_hour >= 9 and self.current_hour <= 11
            # 开仓
            if open_time_1 or open_time_2:
                # 做多
                if self.marketposition == 0 and self.day_bar_num >= 3 and self.ma_value[0] > self.ma_value[-1] and data.close[0] > self.ma_value[0] and data.close[0] > self.day_avg_price[0] and data.close[-1] < self.day_avg_price[-1]:
                    info = self.broker.getcommissioninfo(data)
                    symbol_multi = info.p.mult
                    close = data.close[0]
                    total_value = self.broker.getvalue()
                    lots = total_value / (symbol_multi * close)
                    self.buy(data, size=lots)
                    self.buy_count += 1
                    self.marketposition = 1
                    self.stop_order = self.sell(data, size=lots, exectype=bt.Order.StopTrail, trailpercent=self.p.stop_mult / 100)
                # 做空
                if self.marketposition == 0 and self.day_bar_num >= 3 and self.ma_value[0] < self.ma_value[-1] and data.close[0] < self.ma_value[0] and data.close[0] < self.day_avg_price[0] and data.close[-1] > self.day_avg_price[-1]:
                    info = self.broker.getcommissioninfo(data)
                    symbol_multi = info.p.mult
                    close = data.close[0]
                    total_value = self.broker.getvalue()
                    lots = total_value / (symbol_multi * close)
                    self.sell(data, size=lots)
                    self.sell_count += 1
                    self.marketposition = -1
                    self.stop_order = self.buy(data, size=lots, exectype=bt.Order.StopTrail, trailpercent=self.p.stop_mult / 100)

            # 基于信号的平仓
            # 平多仓
            if self.marketposition > 0 and data.close[0] < self.day_avg_price[0] and data.close[0] < self.now_low:
                self.close(data)
                self.marketposition = 0
                if self.stop_order is not None:
                    self.broker.cancel(self.stop_order)
                self.stop_order = None
            # 平空仓
            if self.marketposition < 0 and data.close[0] > self.day_avg_price[0] and data.close[0] > self.now_high:
                self.close(data)
                self.marketposition = 0
                if self.stop_order is not None:
                    self.broker.cancel(self.stop_order)
                self.stop_order = None

            # 收盘前平仓
            if self.marketposition != 0 and self.current_hour == 14 and self.current_minute == 55:
                self.close(data)
                self.marketposition = 0
                if self.stop_order is not None:
                    self.broker.cancel(self.stop_order)
                self.stop_order = None

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
