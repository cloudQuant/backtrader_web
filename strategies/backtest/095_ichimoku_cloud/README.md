# Ichimoku云图策略 (Ichimoku Cloud Strategy)

## 策略简介

Ichimoku云图策略基于日本的一目均衡表(Ichimoku Kinko Hyo)技术指标。该指标通过多条线和云带来提供价格趋势、支撑/阻力以及交易信号的综合分析，是世界上最复杂的指标之一。

## 策略原理

### Ichimoku指标组成部分

1. **转换线(Tenkan-sen)**: (9日最高价 + 9日最低价) / 2
2. **基准线(Kijun-sen)**: (26日最高价 + 26日最低价) / 2
3. **先行带A(Senkou Span A)**: (转换线 + 基准线) / 2，前移26日
4. **先行带B(Senkou Span B)**: (52日最高价 + 52日最低价) / 2，前移26日
5. **迟行线(Chikou Span)**: 当日收盘价，后移26日
6. **云带(Kumo)**: 先行带A和B之间的区域

### 交易逻辑

**做多条件**:
```
收盘价 > 先行带A AND 收盘价 > 先行带B
```
价格完全位于云带上方，表示强势上升趋势

**平仓条件**:
```
收盘价 < 先行带A AND 收盘价 < 先行带B
```
价格跌破云带下沿，表示趋势可能反转

## 策略参数

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `stake` | 10 | 每次交易的数量 |
| `tenkan` | 9 | 转换线周期 |
| `kijun` | 26 | 基准线周期 |
| `senkou` | 52 | 后行带Span B周期 |
| `senkou_lead` | 26 | 云带前移周期 |
| `chikou` | 26 | 迟行线后移周期 |

## 适用场景

1. **趋势市场**: Ichimoku在趋势市场中效果最佳
2. **股票/外汇/期货**: 适用于各类金融市场
3. **日线/周线**: 适合中长周期分析

## 风险提示

1. **震荡市场表现差**: 横盘时云带会频繁产生假信号
2. **参数复杂**: 需要深入理解各条线的含义
3. **信号滞后**: 作为趋势指标，入场信号有滞后

## 回测结果

基于ORCL(Oracle)股票2010-2014年历史数据回测：

- **初始资金**: $100,000
- **最终资金**: $100,088.51
- **夏普比率**: 0.91
- **年化收益率**: 0.018%
- **最大回撤**: 10.32%

## 使用示例

```python
import backtrader as bt
from strategy_ichimoku_cloud import IchimokuCloudStrategy

cerebro = bt.Cerebro()
cerebro.addstrategy(IchimokuCloudStrategy,
                    stake=10,
                    tenkan=9,
                    kijun=26,
                    senkou=52)
```

## 参考文献

- Reference: backtrader-strategies-compendium/strategies/Ichimoku.py
