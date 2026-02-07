"""ETF轮动策略 (ETF Rotation Strategy)

基于均线比率的ETF轮动策略:
- 计算两个ETF的价格与均线比率
- 当两个ETF都低于均线时清仓
- 当至少一个ETF高于均线时，持有比率较高的那个

Author: yunjinqi
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt


class EtfRotationStrategy(bt.Strategy):
    """基于均线比率的ETF轮动策略

    该策略在两个ETF（上证50ETF和创业板ETF）之间进行轮动:
    1. 计算两个ETF的价格/均线比率
    2. 如果两个ETF都低于均线，清仓
    3. 如果至少一个ETF高于均线，持有比率较高的那个
    """
    # 策略作者
    author = 'yunjinqi'
    # 策略参数
    params = (("ma_period", 20),)

    def log(self, txt, dt=None):
        """记录日志"""
        dt = dt or bt.num2date(self.datas[0].datetime[0])
        print('{}, {}'.format(dt.isoformat(), txt))

    def __init__(self):
        """初始化ETF轮动策略"""
        self.bar_num = 0
        self.buy_count = 0
        self.sell_count = 0
        # 为两个ETF计算均线
        self.sz_ma = bt.indicators.SMA(self.datas[0].close, period=self.p.ma_period)
        self.cy_ma = bt.indicators.SMA(self.datas[1].close, period=self.p.ma_period)

    def prenext(self):
        """在最小周期到达前调用"""
        self.next()

    def next(self):
        """执行核心ETF轮动策略逻辑"""
        self.bar_num += 1
        # 两个ETF的数据
        sz_data = self.datas[0]
        cy_data = self.datas[1]
        # 计算当前持仓
        self.sz_pos = self.getposition(sz_data).size
        self.cy_pos = self.getposition(cy_data).size
        # 获取两个ETF的当前价格
        sz_close = sz_data.close[0]
        cy_close = cy_data.close[0]

        # 如果两个ETF都低于均线，清仓
        if sz_close < self.sz_ma[0] and cy_close < self.cy_ma[0]:
            if self.sz_pos > 0:
                self.close(sz_data)
            if self.cy_pos > 0:
                self.close(cy_data)

        # 如果至少一个ETF高于均线
        if sz_close > self.sz_ma[0] or cy_close > self.cy_ma[0]:
            # 如果上证50动量指标更大
            if sz_close / self.sz_ma[0] > cy_close / self.cy_ma[0]:

                # 如果当前没有持仓，直接买入上证50ETF
                if self.sz_pos == 0 and self.cy_pos == 0:
                    # 获取账户价值
                    total_value = self.broker.get_value()
                    # 计算买入数量
                    lots = int(0.95 * total_value / sz_close)
                    # 买入
                    self.buy(sz_data, size=lots)
                    self.buy_count += 1

                # 如果当前不持有sz但持有cy，平掉创业板ETF并买入sz
                if self.sz_pos == 0 and self.cy_pos > 0:
                    # 平掉创业板ETF
                    self.close(cy_data)
                    self.sell_count += 1
                    # 获取账户价值
                    total_value = self.broker.get_value()
                    # 计算买入数量
                    lots = int(0.95 * total_value / sz_close)
                    # 买入
                    self.buy(sz_data, size=lots)
                    self.buy_count += 1

                # 如果已经持有sz，忽略
                if self.sz_pos > 0:
                    pass

            # 如果创业板动量指标更大
            if sz_close / self.sz_ma[0] < cy_close / self.cy_ma[0]:
                # 如果当前没有持仓，直接买入创业板ETF
                if self.sz_pos == 0 and self.cy_pos == 0:
                    # 获取账户价值
                    total_value = self.broker.get_value()
                    # 计算买入数量
                    lots = int(0.95 * total_value / cy_close)
                    # 买入
                    self.buy(cy_data, size=lots)
                    self.buy_count += 1

                # 如果当前不持有cy但持有sz，平掉上证50ETF并买入cy
                if self.sz_pos > 0 and self.cy_pos == 0:
                    # 平掉上证50ETF
                    self.close(sz_data)
                    self.sell_count += 1
                    # 获取账户价值
                    total_value = self.broker.get_value()
                    # 计算买入数量
                    lots = int(0.95 * total_value / cy_close)
                    # 买入
                    self.buy(cy_data, size=lots)
                    self.buy_count += 1

                # 如果已经持有cy，忽略
                if self.cy_pos > 0:
                    pass

    def notify_order(self, order):
        """订单状态变化时调用"""
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Rejected:
            self.log(f"Rejected : order_ref:{order.ref}  data_name:{order.p.data._name}")

        if order.status == order.Margin:
            self.log(f"Margin : order_ref:{order.ref}  data_name:{order.p.data._name}")

        if order.status == order.Cancelled:
            self.log(f"Cancelled : order_ref:{order.ref}  data_name:{order.p.data._name}")

        if order.status == order.Partial:
            self.log(f"Partial : order_ref:{order.ref}  data_name:{order.p.data._name}")

        if order.status == order.Completed:
            if order.isbuy():
                self.log(f" BUY : data_name:{order.p.data._name} price : {order.executed.price} , cost : {order.executed.value} , commission : {order.executed.comm}")

            else:  # Sell
                self.log(f" SELL : data_name:{order.p.data._name} price : {order.executed.price} , cost : {order.executed.value} , commission : {order.executed.comm}")

    def notify_trade(self, trade):
        """交易生命周期事件处理"""
        # 输出交易结束时的信息
        if trade.isclosed:
            self.log('closed symbol is : {} , total_profit : {} , net_profit : {}' .format(
                            trade.getdataname(), trade.pnl, trade.pnlcomm))

        if trade.isopen:
            self.log('open symbol is : {} , price : {} ' .format(
                            trade.getdataname(), trade.price))

    def stop(self):
        """回测结束时调用"""
        self.log(f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}")
