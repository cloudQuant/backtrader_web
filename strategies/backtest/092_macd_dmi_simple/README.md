# MACD+DMI简化策略 (MACD + DMI Simplified Strategy)

## 策略简介

MACD+DMI简化策略结合了MACD动量指标和DMI趋势指标。MACD用于识别趋势变化和动量方向，DMI用于确认趋势强度。该策略简化版专注于MACD交叉信号，DMI作为辅助参考。

## 策略原理

### MACD指标

MACD(移动平均收敛散度)由三部分组成：
- **MACD线**: 快速EMA - 慢速EMA
- **信号线**: MACD线的EMA
- **柱状图**: MACD线 - 信号线

### DMI指标

DMI(方向运动指数)包含：
- **+DI**: 上升方向指标
- **-DI**: 下降方向指标
- **ADX**: 平均趋向指数(衡量趋势强度)

### 交易逻辑

**做多条件**:
- MACD线上穿信号线(金叉)

**做空条件**:
- MACD线下穿信号线(死叉)

**平仓条件**:
- 多头持仓：MACD出现死叉时平仓
- 空头持仓：MACD出现金叉时平仓

## 策略参数

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `stake` | 10 | 每次交易的数量 |
| `macd_fast` | 12 | MACD快速EMA周期 |
| `macd_slow` | 26 | MACD慢速EMA周期 |
| `macd_signal` | 9 | MACD信号线周期 |
| `dmi_period` | 14 | DMI周期 |

## 适用场景

1. **趋势市场**: MACD在趋势市场中表现较好
2. **股票/期货**: 适用于各种流动性好的品种
3. **日线级别**: 适合中长线交易

## 风险提示

1. **震荡市频繁交易**: 在横盘中容易产生大量无效信号
2. **滞后性**: MACD是滞后指标，入场点不够理想
3. **假交叉风险**: 可能出现MACD假交叉

## 回测结果

基于ORCL(Oracle)股票2010-2014年历史数据回测：

- **初始资金**: $100,000
- **最终资金**: $99,948.71
- **夏普比率**: -0.21
- **年化收益率**: -0.01%
- **最大回撤**: 12.26%

## 使用示例

```python
import backtrader as bt
from strategy_macd_dmi_simple import MacdDmiSimpleStrategy

cerebro = bt.Cerebro()
cerebro.addstrategy(MacdDmiSimpleStrategy,
                    stake=10,
                    macd_fast=12,
                    macd_slow=26,
                    macd_signal=9)
```

## 参考文献

- Reference: backtrader-strategies/macddmi.py
