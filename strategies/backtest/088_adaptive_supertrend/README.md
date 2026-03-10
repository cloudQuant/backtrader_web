# 自适应SuperTrend策略 (Adaptive SuperTrend Strategy)

## 策略简介

自适应SuperTrend策略是对传统SuperTrend指标的改进版本。它根据市场波动率动态调整指标倍数，在高波动时使用较小倍数，低波动时使用较大倍数，从而更准确地跟踪趋势。

## 策略原理

### 动态倍数计算

传统SuperTrend使用固定倍数，而自适应版本根据ATR动态调整：

1. **基础倍数**:
   ```
   base_mult = a_coef + b_coef × avg_atr
   ```

2. **动态倍数**:
   ```
   dyn_mult = base_mult × (avg_atr / current_atr)
   ```

3. **倍数限制**:
   ```
   final_mult = clamp(dyn_mult, min_mult, max_mult)
   ```

### 递归逻辑

- 当收盘价 > 前SuperTrend值时: ST = max(下轨, 前ST值)
- 当收盘价 <= 前SuperTrend值时: ST = min(上轨, 前ST值)

### 交易逻辑

- **做多信号**: 价格突破SuperTrend线上方
- **平仓信号**: 价格跌破SuperTrend线下方

## 策略参数

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `stake` | 10 | 每次交易的数量 |
| `st_period` | 20 | SuperTrend ATR周期 |
| `vol_lookback` | 20 | 波动率回溯周期 |
| `a_coef` | 0.5 | 基础倍数系数a |
| `b_coef` | 2.0 | 基础倍数系数b |
| `min_mult` | 0.5 | 最小倍数 |
| `max_mult` | 3.0 | 最大倍数 |

## 适用场景

1. **波动率变化较大的品种**: 能适应不同波动环境
2. **趋势市场**: 在单边行情中效果最佳
3. **商品期货/外汇**: 适用于高波动品种

## 风险提示

1. **震荡市场表现不佳**: 横盘震荡中容易频繁止损
2. **参数复杂**: 需要优化多个参数以适应不同品种
3. **滞后性**: 仍然存在指标滞后问题

## 回测结果

基于ORCL(Oracle)股票2010-2014年历史数据回测：

- **初始资金**: $100,000
- **最终资金**: $99,936.86
- **夏普比率**: -0.36
- **年化收益率**: -0.013%
- **最大回撤**: 17.54%

## 使用示例

```python
import backtrader as bt
from strategy_adaptive_supertrend import AdaptiveSuperTrendStrategy

cerebro = bt.Cerebro()
cerebro.addstrategy(AdaptiveSuperTrendStrategy,
                    stake=10,
                    st_period=20,
                    vol_lookback=20)
```

## 参考文献

- Reference: https://github.com/Backtrader1.0/strategies/adaptive_supertrend.py
