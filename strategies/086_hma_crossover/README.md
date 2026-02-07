# HMA交叉均线策略 (HMA Crossover Strategy)

## 策略简介

HMA交叉均线策略使用Hull移动平均线(HMA)构建双均线交叉系统。HMA是一种改进的移动平均线，相比传统MA具有更低的滞后性，能够更快速地响应价格变化。

## 策略原理

### Hull移动平均线(HMA)

HMA由Alan Hull开发，通过加权计算减少滞后：
1. 计算周期为n/2的WMA
2. 计算周期为n的WMA
3. HMA = 2 × WMA(n/2) - WMA(n)，再对结果计算周期为sqrt(n)的WMA

### 交易逻辑

- **做多信号**: 快速HMA上穿慢速HMA（金叉）
- **做空信号**: 快速HMA下穿慢速HMA（死叉）
- **平仓逻辑**: 交叉信号反转时平仓

## 策略参数

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `stake` | 10 | 每次交易的数量 |
| `hma_fast` | 60 | 快速HMA周期 |
| `hma_slow` | 90 | 慢速HMA周期 |
| `atr_period` | 14 | ATR周期(参考用) |

## 适用场景

1. **趋势市场**: 在有明显趋势的市场中表现良好
2. **中长线交易**: 适合日线级别以上的交易周期
3. **股票/期货**: 适用于流动性好的品种

## 风险提示

1. **震荡市场亏损**: 在横盘震荡中容易频繁止损
2. **滞后风险**: 虽然HMA滞后较小，但仍存在一定滞后
3. **参数敏感**: 快慢周期需要根据品种特性优化

## 回测结果

基于ORCL(Oracle)股票2010-2014年历史数据回测：

- **初始资金**: $100,000
- **最终资金**: $100,081.45
- **夏普比率**: 0.51
- **年化收益率**: 0.016%
- **最大回撤**: 10.33%

## 使用示例

```python
import backtrader as bt
from strategy_hma_crossover import HmaCrossoverStrategy

cerebro = bt.Cerebro()
cerebro.addstrategy(HmaCrossoverStrategy,
                    stake=10,
                    hma_fast=60,
                    hma_slow=90)
```

## 参考文献

- Reference: https://github.com/Backtrader1.0/strategies/hma_crossover.py
