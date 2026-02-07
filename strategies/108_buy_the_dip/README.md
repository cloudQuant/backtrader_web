# Buy The Dip Strategy (逢低买入策略)

## 策略简介

逢低买入策略是一种基于均值回归思想的简单交易策略。该策略通过检测连续下跌的价格走势，在价格经历连续下跌后买入，并在持有固定天数后卖出，无论盈亏。

## 策略原理

### 入场条件
- 连续N天（默认3天）收盘价低于前一日收盘价
- 满足条件时买入

### 出场条件
- 持有N天（默认5天）后卖出
- 不考虑盈亏情况，固定持仓时间

## 策略参数

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| stake | 10 | 每次交易的股票数量 |
| hold_days | 5 | 持有天数，达到此天数后自动卖出 |
| consecutive_down | 3 | 触发买入的连续下跌天数 |

## 适用场景

- 震荡市场：价格在区间内波动，有均值回归特征
- 短期交易：适合短期持仓交易
- 风险可控：固定持仓时间，避免长期套牢

## 风险提示

1. **单边下跌风险**：在持续下跌趋势中可能连续亏损
2. **错过反弹机会**：固定持仓时间可能错过继续上涨的机会
3. **交易成本**：频繁交易产生较高的交易成本
4. **数据质量**：依赖准确的历史价格数据

## 回测结果

基于Oracle (ORCL) 2010-2014年数据回测：

| 指标 | 数值 |
|------|------|
| 初始资金 | $100,000 |
| 最终资金 | $100,151.25 |
| 夏普比率 | 1.028 |
| 年化收益率 | 0.03% |
| 最大回撤 | 4.95% |
| 处理K线数 | 1257 |

## 代码结构

```
108_buy_the_dip/
├── config.yaml              # 策略配置文件
├── strategy_buy_the_dip.py  # 策略实现代码
└── README.md                # 策略说明文档
```

## 使用方法

```python
import backtrader as bt
from strategy_buy_the_dip import BuyTheDipStrategy

cerebro = bt.Cerebro()
cerebro.addstrategy(BuyTheDipStrategy, stake=10, hold_days=5, consecutive_down=3)
# ... 添加数据和运行回测
```

## 参考来源

- backtrader-strategies-compendium/strategies/BuyTheDip.py
