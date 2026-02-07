# Renko EMA交叉策略 (Renko EMA Crossover Strategy)

## 策略简介

Renko EMA交叉策略将Renko图表的价格平滑特性与EMA交叉信号结合。Renko过滤能够有效减少市场噪音，只在价格出现实质性移动时更新，从而提高交易信号的质量。

## 策略原理

### Renko图表过滤

Renko图表是一种不关注时间的图表类型，只在价格移动指定"砖块"大小时才绘制新砖块：
- 价格上涨超过砖块大小 → 绘制阳线砖块
- 价格下跌超过砖块大小 → 绘制阴线砖块

这种过滤方式能有效：
- 减少小幅波动噪音
- 突出趋势方向
- 提供更清晰的价格结构

### EMA交叉信号

在Renko过滤后的价格上应用EMA交叉：
- **做多信号**: 快速EMA上穿慢速EMA
- **平仓信号**: 快速EMA下穿慢速EMA

## 策略参数

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `stake` | 10 | 每次交易的数量 |
| `fast_period` | 10 | 快速EMA周期 |
| `slow_period` | 20 | 慢速EMA周期 |
| `renko_brick_size` | 1.0 | Renko砖块大小 |

## 适用场景

1. **趋势市场**: 在单边趋势中表现最佳
2. **高波动品种**: Renko能有效过滤高波动噪音
3. **中长线交易**: 适合日线及以上周期

## 风险提示

1. **砖块大小敏感**: 砖块大小需要根据品种特性调整
2. **信号滞后**: Renko过滤会增加信号滞后
3. **震荡市表现**: 在横盘中可能错过机会

## 回测结果

基于ORCL(Oracle)股票2010-2014年历史数据回测：

- **初始资金**: $100,000
- **最终资金**: $100,057.43
- **夏普比率**: 0.32
- **年化收益率**: 0.012%
- **最大回撤**: 9.54%

## 使用示例

```python
import backtrader as bt
from strategy_renko_ema import RenkoEmaStrategy

cerebro = bt.Cerebro()
cerebro.addstrategy(RenkoEmaStrategy,
                    stake=10,
                    fast_period=10,
                    slow_period=20,
                    renko_brick_size=1.0)
```

## 参考文献

- Reference: Backtrader1.0/strategies/renko_ema_crossover.py
