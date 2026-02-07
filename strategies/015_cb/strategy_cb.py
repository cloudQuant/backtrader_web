"""可转债多因子日内策略 (Convertible Bond Intraday Strategy)

基于多因子筛选的可转债日内交易策略:
- 价格>20周期均线
- 价格>时间均价线
- 价格涨跌幅在-1%到1%之间
- 成交量<30周期均量的4倍
- 均线上升但增速放缓

Author: yunjinqi
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
from backtrader.comminfo import ComminfoFuturesPercent


class ExtendPandasFeed(bt.feeds.PandasData):
    """扩展的可转债Pandas数据源"""
    params = (
        ('datetime', None),
        ('open', 0),
        ('high', 1),
        ('low', 2),
        ('close', 3),
        ('volume', 4),
        ('openinterest', -1),
    )


class ConvertibleBondIntradayStrategy(bt.Strategy):
    """可转债多因子日内策略

    使用多个因子进行筛选和交易:
    - 价格>20周期均线
    - 价格>时间均价线
    - 价格涨跌幅在-1%到1%之间
    - 成交量<30周期均量的4倍
    - 均线上升但增速放缓
    """
    author = 'yunjinqi'
    params = (
        ("ma_period", 20),
        ("can_trade_num", 2),
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
        # 最大可同时持有的可转债数量
        self.can_trade_num = self.p.can_trade_num
        # 为每个可转债计算20周期均线
        self.cb_ma_dict = {data._name: bt.indicators.SMA(data.close, period=self.p.ma_period) for data in self.datas[1:]}
        # 计算最近30周期的平均成交量
        self.cb_avg_volume_dict = {data._name: bt.indicators.SMA(data.volume, period=30) for data in self.datas[1:]}
        # 记录前一日的收盘价
        self.cb_pre_close_dict = {data._name: None for data in self.datas[1:]}
        # 记录开仓时的bar数
        self.cb_bar_num_dict = {data._name: None for data in self.datas[1:]}
        # 记录开仓价格
        self.cb_open_position_price_dict = {data._name: None for data in self.datas[1:]}
        # 使用最近20周期的最低点作为前期低点
        self.cb_low_point_dict = {data._name: bt.indicators.Lowest(data.low, period=20) for data in self.datas[1:]}

    def prenext(self):
        """在最小周期到达前调用"""
        self.next()

    def next(self):
        """主策略逻辑，每个bar调用一次"""
        self.bar_num += 1
        self.current_datetime = bt.num2date(self.datas[0].datetime[0])

        for data in self.datas[1:]:
            data_datetime = bt.num2date(data.datetime[0])
            if data_datetime == self.current_datetime:
                data_name = data._name
                close_price = data.close[0]

                # 检查前一日的收盘价是否存在
                pre_close = self.cb_pre_close_dict[data_name]
                if pre_close is None:
                    pre_close = data.open[0]
                    self.cb_pre_close_dict[data_name] = pre_close

                # 更新收盘价(日线数据直接更新)
                self.cb_pre_close_dict[data_name] = close_price

                # 到期平仓逻辑
                position_size = self.getposition(data).size
                if position_size > 0:
                    try:
                        _ = data.open[2]
                    except:
                        self.close(data)
                        self.cb_bar_num_dict[data_name] = None
                        self.can_trade_num += 1

                # 准备平仓
                open_bar_num = self.cb_bar_num_dict[data_name]
                if open_bar_num is not None:
                    # 持仓超过10根bar就平仓
                    if open_bar_num < self.bar_num - 10:
                        self.close(data)
                        self.sell_count += 1
                        self.cb_bar_num_dict[data_name] = None
                        self.can_trade_num += 1

                open_bar_num = self.cb_bar_num_dict[data_name]
                if open_bar_num is not None:
                    # 价格低于前期低点就平仓
                    low_point = self.cb_low_point_dict[data_name][0]
                    if close_price < low_point:
                        self.close(data)
                        self.sell_count += 1
                        self.cb_bar_num_dict[data_name] = None
                        self.can_trade_num += 1

                open_bar_num = self.cb_bar_num_dict[data_name]
                if open_bar_num is not None:
                    # 收益超过3%就止盈
                    open_position_price = self.cb_open_position_price_dict[data_name]
                    if open_position_price and close_price / open_position_price > 1.03:
                        self.close(data)
                        self.sell_count += 1
                        self.cb_bar_num_dict[data_name] = None
                        self.can_trade_num += 1

                # 准备开仓
                ma_line = self.cb_ma_dict[data_name]
                ma_price = ma_line[0]
                if close_price > ma_price:
                    # 检查价格涨跌幅是否在-1%到1%之间
                    up_percent = close_price / pre_close
                    if up_percent > 0.99 and up_percent < 1.01:
                        # 检查成交量是否小于平均成交量的4倍
                        volume = data.volume[0]
                        avg_volume = self.cb_avg_volume_dict[data_name][0]
                        if avg_volume > 0 and volume < avg_volume * 4:
                            # 均线上升但增速放缓
                            if ma_line[0] > ma_line[-1] and ma_line[0] - ma_line[-1] < ma_line[-1] - ma_line[-2]:
                                open_bar_num = self.cb_bar_num_dict[data_name]
                                if self.can_trade_num > 0 and open_bar_num is None:
                                    total_value = self.broker.getvalue()
                                    plan_tobuy_value = 0.4 * total_value
                                    lots = int(plan_tobuy_value / close_price)
                                    if lots > 0:
                                        self.buy(data, size=lots)
                                        self.buy_count += 1
                                        self.can_trade_num -= 1
                                        self.cb_bar_num_dict[data_name] = self.bar_num
                                        try:
                                            self.cb_open_position_price_dict[data_name] = data.open[1]
                                        except:
                                            self.cb_open_position_price_dict[data_name] = close_price

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
