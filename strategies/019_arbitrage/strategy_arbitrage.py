"""国债期货跨期套利策略 (Treasury Futures Spread Arbitrage Strategy)

基于价差的国债期货跨期套利策略:
- 近月-远月价差 < 下限 -> 开多价差（多近月空远月）
- 近月-远月价差 > 上限 -> 开空价差（空近月多远月）
- 价差回归时平仓
- 支持合约换月

Author: yunjinqi
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
from backtrader.comminfo import ComminfoFuturesPercent


class TreasuryFuturesSpreadArbitrageStrategy(bt.Strategy):
    """国债期货跨期套利策略

    该策略通过交易近月和远月合约之间的价差进行套利:
    - 当价差低于下限时，做多价差（买近月卖远月）
    - 当价差高于上限时，做空价差（卖近月买远月）
    - 当价差回归时平仓
    - 支持自动换月
    """
    # 策略作者
    author = 'yunjinqi'
    # 策略参数
    params = (
        ("spread_low", 0.06),   # 价差下限，低于此值开多
        ("spread_high", 0.52),  # 价差上限，高于此值开空
    )

    def log(self, txt, dt=None):
        """记录日志"""
        dt = dt or bt.num2date(self.datas[0].datetime[0])
        print('{}, {}'.format(dt.isoformat(), txt))

    def __init__(self):
        """初始化策略属性和状态变量"""
        # 通用属性变量
        self.bar_num = 0  # next中运行的bar数
        self.buy_count = 0
        self.sell_count = 0
        self.current_date = None  # 当前交易日
        # 保存当前持有的合约
        self.holding_contract_name = None
        self.market_position = 0

    def prenext(self):
        """在最小周期到达前调用"""
        self.next()

    def next(self):
        """执行主要策略逻辑"""
        # 每次运行bar_num加1，并更新交易日
        self.current_date = bt.num2date(self.datas[0].datetime[0])
        self.bar_num += 1
        near_data, far_data = self.get_near_far_data()
        if near_data is not None:
            if self.market_position != 0:
                hold_near_data = self.holding_contract_name[0]
                hold_far_data = self.holding_contract_name[1]
                near_name = hold_near_data._name
                far_name = hold_far_data._name
            else:
                near_name = None
                far_name = None
        else:
            self.log(f"near data is None------------------------------------------")

        # 开仓
        if self.market_position == 0:
            # 开多价差
            if near_data.close[0] - far_data.close[0] < self.p.spread_low:
                self.buy(near_data, size=1)
                self.sell(far_data, size=1)
                self.buy_count += 1
                self.sell_count += 1
                self.market_position = 1
                self.holding_contract_name = [near_data, far_data]
                self.log(f"Open position, buy: {near_data._name}, sell: {far_data._name}")
            # 开空价差
            if near_data.close[0] - far_data.close[0] > self.p.spread_high:
                self.sell(near_data, size=1)
                self.buy(far_data, size=1)
                self.buy_count += 1
                self.sell_count += 1
                self.market_position = -1
                self.holding_contract_name = [near_data, far_data]
                self.log(f"Open short position, buy: {far_data._name}, sell: {near_data._name}")
        # 平仓
        if self.market_position == 1:
            near_data = self.holding_contract_name[0]
            far_data = self.holding_contract_name[1]
            if near_data.close[0] - far_data.close[0] > self.p.spread_high:
                self.close(near_data)
                self.close(far_data)
                self.market_position = 0
                self.holding_contract_name = [None, None]

        if self.market_position == -1:
            near_data = self.holding_contract_name[0]
            far_data = self.holding_contract_name[1]
            if near_data.close[0] - far_data.close[0] < self.p.spread_low:
                self.close(near_data)
                self.close(far_data)
                self.market_position = 0
                self.holding_contract_name = [None, None]

        # 换月到新合约
        if self.market_position != 0:
            hold_near_data = self.holding_contract_name[0]
            hold_far_data = self.holding_contract_name[1]
            near_data, far_data = self.get_near_far_data()
            if near_data is not None:
                if hold_near_data._name != near_data._name or hold_far_data._name != far_data._name:
                    near_size = self.getposition(hold_near_data).size
                    far_size = self.getposition(hold_far_data).size
                    self.close(hold_far_data)
                    self.close(hold_near_data)
                    if near_size > 0:
                        self.buy(near_data, size=abs(near_size))
                        self.sell(far_data, size=abs(far_size))
                        self.holding_contract_name = [near_data, far_data]
                    else:
                        self.sell(near_data, size=abs(near_size))
                        self.buy(far_data, size=abs(far_size))
                        self.holding_contract_name = [near_data, far_data]

    def get_near_far_data(self):
        """确定近月和远月合约（基于持仓量）"""
        # 计算近月和远月合约价格
        target_datas = []
        for data in self.datas[1:]:
            try:
                data_date = bt.num2date(data.datetime[0])
                if self.current_date == data_date:
                    target_datas.append([data._name, data.openinterest[0], data])
            except:
                self.log(f"{data._name} is not yet listed for trading")

        target_datas = sorted(target_datas, key=lambda x: x[1])
        if len(target_datas) >= 2:
            if target_datas[-1][0] > target_datas[-2][0]:
                near_data = target_datas[-2][2]
                far_data = target_datas[-1][2]
            else:
                near_data = target_datas[-1][2]
                far_data = target_datas[-2][2]
            return [near_data, far_data]
        else:
            return [None, None]

    def get_dominant_contract(self):
        """确定主力合约（持仓量最大）"""
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
                self.log(f"{data._name} is not yet listed for trading")

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
