# 外汇EMA三均线策略 (Forex EMA Strategy)

## 策略简介

外汇EMA三均线策略使用三条不同周期的指数移动平均线(EMA)来识别趋势方向并产生交易信号。该策略在外汇市场中被广泛使用，通过EMA的多头或空头排列来确认趋势。

## 策略原理

### 三EMA系统

使用三条不同周期的EMA：
- **短期EMA**: 默认5周期，快速响应价格变化
- **中期EMA**: 默认20周期，过滤短期噪音
- **长期EMA**: 默认50周期，判断主趋势方向

### 交易逻辑

**做多条件**:
1. 短期EMA上穿中期EMA(金叉)
2. 当前K线最低价 > 长期EMA
3. 中期EMA > 长期EMA
4. 短期EMA > 长期EMA

**做空条件**:
1. 短期EMA下穿中期EMA(死叉)
2. 当前K线最高价 < 长期EMA
3. 中期EMA < 长期EMA
4. 短期EMA < 长期EMA

**平仓条件**:
- 多头持仓：短期EMA下穿中期EMA时平仓
- 空头持仓：短期EMA上穿中期EMA时平仓

## 策略参数

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `stake` | 10 | 每次交易的数量 |
| `shortema` | 5 | 短期EMA周期 |
| `mediumema` | 20 | 中期EMA周期 |
| `longema` | 50 | 长期EMA周期 |

## 适用场景

1. **外汇市场**: 特别适合主要货币对
2. **趋势市场**: 在有明显趋势时表现最佳
3. **4小时/日线**: 适合中长周期交易

## 风险提示

1. **震荡市场表现差**: 在横盘震荡中容易频繁止损
2. **入场滞后**: EMA交叉信号存在滞后
3. **假突破风险**: 可能出现EMA假交叉

## 回测结果

基于ORCL(Oracle)股票2010-2014年历史数据回测：

- **初始资金**: $100,000
- **最终资金**: $99,898.69
- **夏普比率**: -0.69
- **年化收益率**: -0.02%
- **最大回撤**: 15.89%

## 使用示例

```python
import backtrader as bt
from strategy_forex_ema import ForexEmaStrategy

cerebro = bt.Cerebro()
cerebro.addstrategy(ForexEmaStrategy,
                    stake=10,
                    shortema=5,
                    mediumema=20,
                    longema=50)
```

## 参考文献

- Reference: backtrader-strategies/forexema.py
