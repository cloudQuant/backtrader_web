# HMA多趋势策略 (HMA MultiTrend Strategy)

## 策略简介

HMA多趋势策略使用四条不同周期的Hull移动平均线构建一个多周期趋势确认系统。只有当所有HMA按顺序排列时（上升或下降排列），才认为趋势确立并产生交易信号。

## 策略原理

### HMA排列确认

使用4条不同周期的HMA：
- **fast**: 10周期 - 最快速响应
- **mid1**: 20周期 - 短期趋势
- **mid2**: 30周期 - 中期趋势
- **mid3**: 50周期 - 长期趋势

### 交易逻辑

**做多条件**:
```
fast > mid1 > mid2 > mid3
```
所有HMA呈上升排列，表示趋势明确向上

**做空条件**:
```
fast < mid1 < mid2 < mid3
```
所有HMA呈下降排列，表示趋势明确向下

**平仓条件**:
- 多头持仓：当HMA排列转为下降时平仓
- 空头持仓：当HMA排列转为上升时平仓

### ADX过滤器

可选的ADX趋势强度过滤器，只在趋势足够强时交易。

## 策略参数

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `stake` | 10 | 每次交易的数量 |
| `fast` | 10 | 快速HMA周期 |
| `mid1` | 20 | 中速HMA1周期 |
| `mid2` | 30 | 中速HMA2周期 |
| `mid3` | 50 | 慢速HMA周期 |
| `atr_period` | 14 | ATR周期 |
| `adx_period` | 14 | ADX周期 |
| `adx_threshold` | 0.0 | ADX阈值(0=禁用) |

## 适用场景

1. **趋势明确的市场**: 需要清晰的单边趋势
2. **股票/期货**: 适合各种流动性好的品种
3. **日线级别**: 适合中长线交易

## 风险提示

1. **震荡市失效**: 在横盘震荡中几乎无交易机会
2. **入场滞后**: 需要等待所有HMA排列，入场较晚
3. **最大回撤**: 趋势反转时可能产生较大回撤

## 回测结果

基于ORCL(Oracle)股票2010-2014年历史数据回测：

- **初始资金**: $100,000
- **最终资金**: $100,003.09
- **夏普比率**: 0.006
- **年化收益率**: 0.0006%
- **最大回撤**: 25.88%

## 使用示例

```python
import backtrader as bt
from strategy_hma_multitrend import HmaMultiTrendStrategy

cerebro = bt.Cerebro()
cerebro.addstrategy(HmaMultiTrendStrategy,
                    stake=10,
                    fast=10,
                    mid1=20,
                    mid2=30,
                    mid3=50)
```

## 参考文献

- Reference: Backtrader1.0/strategies/hma_multitrend.py
