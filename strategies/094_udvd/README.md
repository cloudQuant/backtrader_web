# UDVD策略 (UDVD Strategy)

## 策略简介

UDVD(Upper/Lower Shadow Difference)策略是一种基于K线实体动量的趋势跟踪策略。它通过计算收盘价与开盘价的差值(即K线实体)来衡量买卖力量，并使用SMA平滑信号来识别趋势方向。

## 策略原理

### K线实体动量

K线实体 = 收盘价 - 开盘价
- 实体 > 0: 阳线，买方力量强
- 实体 < 0: 阴线，卖方力量强

### 信号平滑

计算K线实体的SMA以平滑噪音：
```
signal = SMA(收盘价 - 开盘价, period)
```

### 交易逻辑

**做多条件**:
```
signal > 0
```
K线实体SMA为正，表示整体买方力量占优

**平仓条件**:
```
signal <= 0
```
K线实体SMA转为非正，表示趋势可能反转

## 策略参数

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `stake` | 10 | 每次交易的数量 |
| `period` | 3 | K线实体SMA周期 |

## 适用场景

1. **趋势市场**: 在单边趋势中表现较好
2. **高波动品种**: 波动越大，K线实体信号越明显
3. **短线交易**: 适合较短周期的交易

## 风险提示

1. **震荡市失效**: 在横盘震荡中容易频繁止损
2. **参数敏感**: SMA周期需要根据品种特性调整
3. **滞后风险**: 短期SMA仍存在一定滞后

## 回测结果

基于ORCL(Oracle)股票2010-2014年历史数据回测：

- **初始资金**: $100,000
- **最终资金**: $99,939.44
- **夏普比率**: -0.22
- **年化收益率**: -0.012%
- **最大回撤**: 20.02%

## 使用示例

```python
import backtrader as bt
from strategy_udvd import UdvdStrategy

cerebro = bt.Cerebro()
cerebro.addstrategy(UdvdStrategy,
                    stake=10,
                    period=3)
```

## 参考文献

- Reference: Time_Series_Backtesting/Effective Strategy Library/UDVD Strategy 1.0.py
