# SuperTrend指标策略 (SuperTrend Indicator Strategy)

## 策略简介

SuperTrend指标策略基于ATR(平均真实波幅)构建动态支撑阻力线，用于识别趋势方向并产生交易信号。该指标在趋势市场中表现良好，能有效跟踪趋势并动态调整止损位。

## 策略原理

### SuperTrend指标计算

1. **基础上下轨**:
   - 上轨 = HL2 + (multiplier × ATR)
   - 下轨 = HL2 - (multiplier × ATR)
   - 其中 HL2 = (最高价 + 最低价) / 2

2. **修正后的上下轨**:
   - 上轨仅在基础上轨下降或价格突破前上轨时更新
   - 下轨仅在基础下轨上升或价格突破前下轨时更新

3. **趋势判断**:
   - 价格 > 前上轨 → 上升趋势(使用下轨作为SuperTrend线)
   - 价格 < 前下轨 → 下降趋势(使用上轨作为SuperTrend线)

### 交易逻辑

- **做多信号**: 价格从下方突破SuperTrend线
- **平仓信号**: 价格从下方跌破SuperTrend线
- **止损跟踪**: SuperTrend线本身作为移动止损线

## 策略参数

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `stake` | 10 | 每次交易的数量 |
| `st_period` | 20 | SuperTrend ATR周期 |
| `st_mult` | 3.0 | SuperTrend倍数 |

## 适用场景

1. **趋势市场**: 在单边趋势行情中效果最佳
2. **股票/期货/外汇**: 适用于各类金融品种
3. **中长线交易**: 适合日线及以上周期

## 风险提示

1. **震荡市场频繁止损**: 在横盘震荡中容易产生多次小亏
2. **滞后性**: 指标存在一定滞后，入场点可能不够理想
3. **参数敏感性**: multiplier参数需要根据品种波动特性调整

## 回测结果

基于ORCL(Oracle)股票2010-2014年历史数据回测：

- **初始资金**: $100,000
- **最终资金**: $99,977.89
- **夏普比率**: -0.09
- **年化收益率**: -0.004%
- **最大回撤**: 16.62%

## 使用示例

```python
import backtrader as bt
from strategy_supertrend_indicator import SuperTrendIndicatorStrategy

cerebro = bt.Cerebro()
cerebro.addstrategy(SuperTrendIndicatorStrategy,
                    stake=10,
                    st_period=20,
                    st_mult=3.0)
```

## 参考文献

- Reference: https://github.com/Backtrader1.0/strategies/supertrend.py
