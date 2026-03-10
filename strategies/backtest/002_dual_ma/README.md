# 双均线交叉策略

## 策略简介

双均线交叉策略是最经典的技术分析策略之一。该策略通过计算两条不同周期的移动平均线，当短期均线从下方穿越长期均线时产生买入信号（金叉），当短期均线从上方穿越长期均线时产生卖出信号（死叉）。

## 策略原理

### 技术指标

1. **短期均线**：默认5日移动平均线，反映短期价格趋势
2. **长期均线**：默认20日移动平均线，反映中长期价格趋势
3. **交叉信号**：使用CrossOver指标检测均线交叉

### 交易规则

**入场条件（开多仓）**：
- 短期均线从下方穿越长期均线（金叉）
- 使用当前可用资金的90%进行买入

**出场条件（平多仓）**：
- 短期均线从上方穿越长期均线（死叉）
- 平仓全部持仓

### 策略参数

| 参数名 | 类型 | 默认值 | 说明 |
|-------|-----|--------|------|
| short_period | int | 5 | 短期均线周期（日） |
| long_period | int | 20 | 长期均线周期（日） |

## 适用场景

1. **市场环境**：适合趋势明显的市场，无论是上涨还是下跌趋势
2. **品种选择**：适用于流动性好的股票、期货、可转债等
3. **时间周期**：日线级别交易策略
4. **市场状态**：单边行情表现优异，震荡市容易连续亏损

## 风险提示

1. **滞后性**：均线是滞后指标，信号出现时趋势可能已运行一段时间
2. **震荡亏损**：在横盘震荡市中容易产生连续的小亏损
3. **单一持仓**：策略始终保持单一持仓，无法分散风险
4. **参数敏感**：均线周期参数对策略表现影响较大，需针对不同品种优化
5. **滑点成本**：频繁交易产生较高的交易成本

## 回测示例

```python
import backtrader as bt
import pandas as pd

# 加载策略
from strategies.dual_ma.strategy import TwoMAStrategy, ExtendPandasFeed

# 创建Cerebro引擎
cerebro = bt.Cerebro()

# 加载数据
df = pd.read_csv('113013.csv')
data = ExtendPandasFeed(dataname=df)
cerebro.adddata(data)

# 设置初始资金和手续费
cerebro.broker.setcash(100000)
cerebro.broker.setcommission(commission=0.001)

# 添加策略
cerebro.addstrategy(TwoMAStrategy, short_period=5, long_period=20)

# 运行回测
results = cerebro.run()
```

## 参考资料

1. 移动平均线基础理论
2. 技术分析方法
3. 趋势跟踪策略原理
