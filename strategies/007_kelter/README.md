# 肯特纳通道多合约期货策略

## 策略简介

本策略基于肯特纳通道（Keltner Channel）指标构建趋势跟踪系统。当价格突破上轨且中线上升时做多，当价格突破下轨且中线下降时做空。策略支持多合约交易和自动换月功能。

## 策略原理

### 肯特纳通道

肯特纳通道是基于ATR（平均真实波幅）的波动性指标：

1. **中线**：典型价（HLC/3）的移动平均线
2. **上轨**：中线 + (ATR × 倍数)
3. **下轨**：中线 - (ATR × 倍数)

其中典型价 = (最高价 + 最低价 + 收盘价) / 3

### 交易规则

**开多仓**：
- 前一日收盘价 < 上轨
- 当日收盘价 > 上轨（向上突破）
- 且中线在上升（当前中线 > 前一日中线）

**开空仓**：
- 前一日收盘价 > 下轨
- 当日收盘价 < 下轨（向下突破）
- 且中线在下降（当前中线 < 前一日中线）

**平仓规则**：
- 多头持仓：收盘价跌破中线时平仓
- 空头持仓：收盘价突破中线时平仓

**换月逻辑**：
- 检测主力合约变化（基于持仓量）
- 自动平旧仓开新仓

### 策略参数

| 参数名 | 类型 | 默认值 | 说明 |
|-------|-----|--------|------|
| avg_period | int | 110 | 中线周期（日） |
| atr_multi | int | 3 | ATR倍数 |

## 适用场景

1. **市场环境**：适合趋势明显且波动性较大的市场
2. **品种选择**：螺纹钢、铜等商品期货
3. **时间周期**：日线级别交易
4. **趋势类型**：捕捉中长线趋势机会

## 风险提示

1. **震荡亏损**：横盘震荡时容易产生连续亏损
2. **假突破**：价格可能短暂突破后快速回归
3. **参数敏感**：周期和倍数参数对策略表现影响较大
4. **换月损失**：主力合约切换时可能产生价差损失
5. **杠杆风险**：期货杠杆放大收益和亏损

## 回测示例

```python
import backtrader as bt
from backtrader.comminfo import ComminfoFuturesPercent

# 加载策略
from strategies.kelter.strategy import KeltnerStrategy, RbPandasFeed

cerebro = bt.Cerebro()

# 加载多合约数据
datas = load_rb_multi_data("rb")
for name, df in datas.items():
    feed = RbPandasFeed(dataname=df)
    cerebro.adddata(feed, name=name)
    comm = ComminfoFuturesPercent(commission=0.0002, margin=0.1, mult=10)
    cerebro.broker.addcommissioninfo(comm, name=name)

cerebro.broker.setcash(50000)
cerebro.addstrategy(KeltnerStrategy, avg_period=110, atr_multi=3)

# 运行回测
results = cerebro.run()
```

## 参考资料

1. 肯特纳通道指标原理
2. ATR平均真实波幅
3. 期货趋势跟踪策略
