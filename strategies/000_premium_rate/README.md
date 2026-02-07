# 可转债溢价率双均线策略

## 策略简介

本策略基于可转债的转股溢价率指标，采用双均线交叉系统生成交易信号。当短期均线上穿长期均线时产生买入信号，当短期均线下穿长期均线时产生卖出信号。策略专门针对可转债品种设计，利用转股溢价率反映的可转债套利空间进行趋势跟踪。

## 策略原理

### 技术指标

1. **转股溢价率**：可转债转股价值与当前价格的比率，反映可转债的理论套利空间
2. **短期均线**：默认10日移动平均线
3. **长期均线**：默认60日移动平均线
4. **交叉信号**：使用CrossOver指标检测均线交叉

### 交易规则

**入场条件（开多仓）**：
- 短期均线从下方穿越长期均线（金叉）
- 使用当前可用资金的95%进行买入

**出场条件（平多仓）**：
- 短期均线从上方穿越长期均线（死叉）
- 平仓全部持仓

**风险控制**：
- 单一持仓策略，每次只持有一个仓位
- 仓位管理：每次入场使用95%可用资金

### 策略参数

| 参数名 | 类型 | 默认值 | 说明 |
|-------|-----|--------|------|
| short_period | int | 10 | 短期均线周期（日） |
| long_period | int | 60 | 长期均线周期（日） |

## 适用场景

1. **市场环境**：适合可转债市场，特别是溢价率波动较为明显的品种
2. **品种选择**：适用于流动性较好的可转债品种
3. **时间周期**：日线级别交易策略
4. **市场状态**：趋势行情中表现较好，震荡市中容易产生频繁交易

## 风险提示

1. **单一持仓风险**：策略始终保持单一持仓，无法分散风险
2. **趋势依赖**：在震荡市中容易产生连续亏损
3. **滑点风险**：可转债流动性相对较低，大额交易可能存在滑点
4. **溢价率失效**：当可转债临近转股期或触发赎回条款时，溢价率策略可能失效
5. **回测偏差**：历史数据不代表未来表现，实盘需谨慎

## 回测示例

```python
import backtrader as bt
import pandas as pd

# 加载策略
from strategies.premium_rate.strategy import PremiumRateCrossoverStrategy, ExtendPandasFeed

# 创建Cerebro引擎
cerebro = bt.Cerebro()

# 加载数据
df = pd.read_csv('113013.csv')
# 数据预处理...
data = ExtendPandasFeed(dataname=df)
cerebro.adddata(data)

# 设置初始资金和手续费
cerebro.broker.setcash(100000)
cerebro.broker.setcommission(commission=0.0003)

# 添加策略
cerebro.addstrategy(PremiumRateCrossoverStrategy, short_period=10, long_period=60)

# 运行回测
results = cerebro.run()
```

## 参考资料

1. 可转债基础知识
2. 双均线交叉策略原理
3. Backtrader官方文档
