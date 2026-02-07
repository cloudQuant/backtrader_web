# 涨跌蜡烛均值回归策略 (Up Down Candles Strategy)

## 策略简介

涨跌蜡烛均值回归策略是一种基于价格收益率和蜡烛强度的均值回归策略。该策略通过计算指定周期内的价格收益率，识别市场的超买和超卖状态，并在价格极端偏离均值时进行反向交易。

## 策略原理

### 核心思想

均值回归理论认为，价格在极端波动后会向均值回归。本策略通过以下方式识别交易机会：

1. **蜡烛强度指标 (UpDownCandleStrength)**: 计算指定周期内上涨蜡烛与下跌蜡烛的比例，反映市场多空力量对比
2. **期间收益率指标 (PercentReturnsPeriod)**: 计算指定周期内的价格收益率，衡量价格偏离均值的程度

### 交易逻辑

- **做多信号**: 当期间收益率低于负阈值时，认为资产超卖，买入
- **做空信号**: 当期间收益率高于正阈值时，认为资产超买，卖出
- **平仓逻辑**: 当收益率回归至合理范围时平仓

## 策略参数

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `stake` | 10 | 每次交易的数量 |
| `strength_period` | 20 | 蜡烛强度计算周期 |
| `returns_period` | 40 | 收益率计算周期 |
| `returns_threshold` | 0.01 | 收益率阈值(1%) |

## 适用场景

1. **震荡市场**: 价格在一定范围内上下波动，适合均值回归策略
2. **高波动资产**: 价格波动较大，容易出现超买超卖
3. **日内或短线交易**: 利用短期价格波动获利

## 风险提示

1. **趋势市场风险**: 在强趋势行情中，均值回归策略可能持续亏损
2. **参数敏感性**: 收益率阈值和周期参数需要针对不同品种优化
3. **最大回撤**: 均值回归策略可能面临较大的最大回撤

## 回测结果

基于ORCL(Oracle)股票2010-2014年历史数据回测：

- **初始资金**: $100,000
- **最终资金**: $99,976.91
- **夏普比率**: -0.11
- **年化收益率**: -0.005%
- **最大回撤**: 13.26%

## 使用示例

```python
import backtrader as bt
from strategy_up_down_candles import UpDownCandlesStrategy

cerebro = bt.Cerebro()
cerebro.addstrategy(UpDownCandlesStrategy,
                    stake=10,
                    strength_period=20,
                    returns_period=40,
                    returns_threshold=0.01)
```

## 参考文献

- Reference: https://github.com/backtrader-stuff/strategies
