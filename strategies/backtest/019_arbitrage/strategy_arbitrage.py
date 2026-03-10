#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Treasury Futures Spread Arbitrage Strategy.

A treasury futures inter-contract spread arbitrage strategy:
- Near month - Far month spread < Lower limit -> Open long spread (long near, short far)
- Near month - Far month spread > Upper limit -> Open short spread (short near, long far)
- Close position when spread reverts
- Supports contract rollover

Author: yunjinqi
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import backtrader as bt
from backtrader.comminfo import ComminfoFuturesPercent


class TreasuryFuturesSpreadArbitrageStrategy(bt.Strategy):
    """Treasury Futures Inter-Contract Spread Arbitrage Strategy.

    This strategy trades the spread between near and far month contracts:
    - When spread is below lower limit, go long spread (buy near, sell far)
    - When spread is above upper limit, go short spread (sell near, buy far)
    - Close position when spread reverts
    - Supports automatic contract rollover
    """
    # Strategy author
    author = 'yunjinqi'
    # Strategy parameters
    params = (
        ("spread_low", 0.06),   # Spread lower limit, go long when below this
        ("spread_high", 0.52),  # Spread upper limit, go short when above this
    )

    def log(self, txt, dt=None):
        """Log strategy information."""
        dt = dt or bt.num2date(self.datas[0].datetime[0])
        print('{}, {}'.format(dt.isoformat(), txt))

    def __init__(self):
        """Initialize strategy attributes and state variables."""
        # Common attribute variables
        self.bar_num = 0  # Number of bars run in next()
        self.buy_count = 0
        self.sell_count = 0
        self.current_date = None  # Current trading day
        # Save currently held contracts
        self.holding_contract_name = None
        self.market_position = 0

    def prenext(self):
        """Called before minimum period is reached."""
        self.next()

    def next(self):
        """Execute main strategy logic."""
        # Increment bar_num and update trading day each run
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

        # Open positions
        if self.market_position == 0:
            # Open long spread
            if near_data.close[0] - far_data.close[0] < self.p.spread_low:
                self.buy(near_data, size=1)
                self.sell(far_data, size=1)
                self.buy_count += 1
                self.sell_count += 1
                self.market_position = 1
                self.holding_contract_name = [near_data, far_data]
                self.log(f"Open position, buy: {near_data._name}, sell: {far_data._name}")
            # Open short spread
            if near_data.close[0] - far_data.close[0] > self.p.spread_high:
                self.sell(near_data, size=1)
                self.buy(far_data, size=1)
                self.buy_count += 1
                self.sell_count += 1
                self.market_position = -1
                self.holding_contract_name = [near_data, far_data]
                self.log(f"Open short position, buy: {far_data._name}, sell: {near_data._name}")
        # Close positions
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

        # Rollover to new contracts
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
        """Determine near and far month contracts (based on open interest)."""
        # Calculate near and far month contract prices
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
        """Determine dominant contract (highest open interest)."""
        # Use contract with highest open interest as dominant contract, return data name
        # Can customize how to calculate dominant contract as needed

        # Get currently trading instruments
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
        """Called when order status changes."""
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
        """Handle trade lifecycle events."""
        # Output information when trade ends
        if trade.isclosed:
            self.log('closed symbol is : {} , total_profit : {} , net_profit : {}'.format(
                trade.getdataname(), trade.pnl, trade.pnlcomm))

        if trade.isopen:
            self.log('open symbol is : {} , price : {} '.format(
                trade.getdataname(), trade.price))

    def stop(self):
        """Called when backtesting ends."""
        self.log(f"bar_num={self.bar_num}, buy_count={self.buy_count}, sell_count={self.sell_count}")
