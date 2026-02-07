"""国债期货MACD策略 (Treasury Futures MACD Strategy)

基于MACD指标的国债期货交易策略:
- 快线上穿慢线且MACD>0 -> 做多
- 快线下穿慢线且MACD<0 -> 做空
- 支持合约换月

Author: yunjinqi
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
from backtrader.comminfo import ComminfoFuturesPercent


class TreasuryFuturesMacdStrategy(bt.Strategy):
    """基于MACD的国债期货交易策略，支持换月

    该策略使用MACD指标进行交易，并自动处理合约换月:
    - 当短期EMA上穿长期EMA且MACD>0时开多仓
    - 当短期EMA下穿长期EMA且MACD<0时开空仓
    - 当价格反向穿过短期EMA时平仓
    - 自动换月到主力合约
    """
    # 策略作者
    author = 'yunjinqi'
    # 策略参数
    params = (("period_me1", 10),
              ("period_me2", 20),
              ("period_dif", 9),

              )

    def log(self, txt, dt=None):
        """记录日志"""
        dt = dt or bt.num2date(self.datas[0].datetime[0])
        print('{}, {}'.format(dt.isoformat(), txt))

    def __init__(self):
        """初始化策略并设置指标"""
        # 通用属性变量
        self.bar_num = 0  # next运行的bar数
        self.buy_count = 0
        self.sell_count = 0
        self.current_date = None  # 当前交易日
        # 计算MACD指标
        self.ema_1 = bt.indicators.ExponentialMovingAverage(self.datas[0].close, period=self.p.period_me1)
        self.ema_2 = bt.indicators.ExponentialMovingAverage(self.datas[0].close, period=self.p.period_me2)
        self.dif = self.ema_1 - self.ema_2
        self.dea = bt.indicators.ExponentialMovingAverage(self.dif, period=self.p.period_dif)
        self.macd = (self.dif - self.dea) * 2
        # 保存当前持有的合约
        self.holding_contract_name = None

    def prenext(self):
        """在最小周期到达前调用"""
        self.next()

    def next(self):
        """执行主要策略逻辑"""
        # 每次运行bar_num加1并更新交易日
        self.current_date = bt.num2date(self.datas[0].datetime[0])
        self.bar_num += 1
        data = self.datas[0]
        # 开仓，先平后开
        # 平多仓
        if self.holding_contract_name is not None and self.getpositionbyname(self.holding_contract_name).size > 0 and \
                data.close[0] < self.ema_1[0]:
            data = self.getdatabyname(self.holding_contract_name)
            self.close(data)
            self.holding_contract_name = None
        # 平空仓
        if self.holding_contract_name is not None and self.getpositionbyname(self.holding_contract_name).size < 0 and \
                data.close[0] > self.ema_1[0]:
            data = self.getdatabyname(self.holding_contract_name)
            self.close(data)
            self.holding_contract_name = None

        # 开多仓
        if self.holding_contract_name is None and self.ema_1[-1] < self.ema_2[-1] and self.ema_1[0] > self.ema_2[0] and \
                self.macd[0] > 0:
            dominant_contract = self.get_dominant_contract()
            next_data = self.getdatabyname(dominant_contract)
            self.buy(next_data, size=1)
            self.buy_count += 1
            self.holding_contract_name = dominant_contract

        # 开空仓
        if self.holding_contract_name is None and self.ema_1[-1] > self.ema_2[-1] and self.ema_1[0] < self.ema_2[0] and \
                self.macd[0] < 0:
            dominant_contract = self.get_dominant_contract()
            next_data = self.getdatabyname(dominant_contract)
            self.sell(next_data, size=1)
            self.sell_count += 1
            self.holding_contract_name = dominant_contract

        # 换月到下一个合约
        if self.holding_contract_name is not None:
            dominant_contract = self.get_dominant_contract()
            # 如果出现新的主力合约，开始换月
            if dominant_contract != self.holding_contract_name:
                # 下一个主力合约
                next_data = self.getdatabyname(dominant_contract)
                # 当前合约持仓规模和数据
                size = self.getpositionbyname(self.holding_contract_name).size  # 持仓规模
                data = self.getdatabyname(self.holding_contract_name)
                # 平掉旧的
                self.close(data)
                # 开新的
                if size > 0:
                    self.buy(next_data, size=abs(size))
                if size < 0:
                    self.sell(next_data, size=abs(size))
                self.holding_contract_name = dominant_contract

    def get_dominant_contract(self):
        """确定主力合约（基于持仓量）"""
        # 使用持仓量最大的合约作为主力合约，返回数据名称
        # 可以根据需要自定义如何计算主力合约

        # 获取当前交易的品种
        target_datas = []
        for data in self.datas[1:]:
            try:
                data_date = bt.num2date(data.datetime[0])
                if self.current_date == data_date:
                    target_datas.append([data._name, data.openinterest[0]])
            except:
                self.log(f"{data._name} not yet listed for trading")

        target_datas = sorted(target_datas, key=lambda x: x[1])
        print(target_datas)
        return target_datas[-1][0]

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
                self.log(
                    f" BUY : data_name:{order.p.data._name} price : {order.executed.price} , cost : {order.executed.value} , commission : {order.executed.comm}")

            else:  # Sell
                self.log(
                    f" SELL : data_name:{order.p.data._name} price : {order.executed.price} , cost : {order.executed.value} , commission : {order.executed.comm}")

    def notify_trade(self, trade):
        """交易生命周期事件处理"""
        # 输出交易结束时的信息
        if trade.isclosed:
            self.log('closed symbol is : {} , total_profit : {} , net_profit : {}'.format(
                trade.getdataname(), trade.pnl, trade.pnlcomm))

        if trade.isopen:
            self.log('open symbol is : {} , price : {} '.format(
                trade.getdataname(), trade.price))

    def stop(self):
        """回测结束时调用"""
        self.log(f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}")
