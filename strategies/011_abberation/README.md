# Abberation布林带突破策略

## 策略简介

Abberation策略是基于布林带突破的经典趋势跟踪策略。当价格突破布林带上轨时做多，突破下轨时做空，价格回归中轨时平仓。策略使用1倍杠杆进行交易。

## 策略原理

### 布林带指标

布林带由三条线组成：
1. **中轨**：N日移动平均线（默认200日）
2. **上轨**：中轨 + K × 标准差（默认K=2）
3. **下轨**：中轨 - K × 标准差（默认K=2）

### 交易规则

**开多仓**：
- 前一日收盘价 < 上轨
- 当日收盘价 > 上轨（向上突破）
- 使用1倍杠杆计算仓位

**开空仓**：
- 前一日收盘价 > 下轨
- 当日收盘价 < 下轨（向下突破）
- 使用1倍杠杆计算仓位

**平仓规则**：
- 多头持仓：价格跌破中轨时平仓
- 空头持仓：价格突破中轨时平仓

**仓位计算**：
- 仓位 = 总资产 / (合约乘数 × 价格)

### 策略参数

| 参数名 | 类型 | 默认值 | 说明 |
|-------|-----|--------|------|
| boll_period | int | 200 | 布林带周期（日） |
| boll_mult | float | 2 | 标准差倍数 |

## 适用场景

1. **市场环境**：适合大趋势行情
2. **品种选择**：螺纹钢等波动性适中的期货
3. **时间周期**：日线级别交易
4. **市场状态**：突破性行情表现最佳

## 风险提示

1. **震荡亏损**：横盘震荡时容易连续亏损
2. **假突破**：价格可能短暂突破后快速回归
3. **杠杆风险**：使用杠杆会放大收益和亏损
4. **中轨滞后**：回归中轨出场可能错过最佳出场点
5. **滑点影响**：大额交易可能产生较大滑点

## 回测示例

```python
import backtrader as bt
from backtrader.comminfo import ComminfoFuturesPercent

# 加载策略
from strategies.abberation.strategy import AbberationStrategy, RbPandasFeed

cerebro = bt.Cerebro()

# 加载数据
df = load_rb889_data("RB889.csv")
feed = RbPandasFeed(dataname=df)
cerebro.adddata(feed, name="RB")

# 设置期货交易参数
comm = ComminfoFuturesPercent(commission=0.0001, margin=0.10, mult=10)
cerebro.broker.addcommissioninfo(comm, name="RB")
cerebro.broker.setcash(1000000)

# 添加策略
cerebro.addstrategy(AbberationStrategy, boll_period=200, boll_mult=2)

# 运行回测
results = cerebro.run()
```

## 参考资料

1. 布林带指标原理
2. 统计学标准差应用
3. 趋势跟踪交易策略
