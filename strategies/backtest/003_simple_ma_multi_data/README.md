# 多品种简单均线策略

## 策略简介

本策略是一个多资产的趋势跟踪策略，使用单一均线判断入场和出场时机。当价格从下方穿越均线时买入，从上方穿越均线时卖出。策略支持多个可转债品种同时交易，采用等权重配置。

## 策略原理

### 核心思想

单一均线策略是趋势跟踪的经典方法：
- **均线含义**：反映价格的平均成本，具有支撑和阻力作用
- **趋势判断**：价格在均线之上视为上升趋势，之下视为下降趋势
- **多品种分散**：同时交易多个品种，降低单一品种风险

### 交易规则

**入场条件（开多仓）**：
- 前一日收盘价 < 前一日均线
- 当日收盘价 > 当日均线（价格上穿均线）
- 使用等权重分配的资金买入

**出场条件（平多仓）**：
- 前一日收盘价 > 前一日均线
- 当日收盘价 < 当日均线（价格下穿均线）
- 平仓全部持仓

**多品种管理**：
- 第一个数据源作为指数基准（不交易）
- 其他数据源为可交易品种
- 等权重分配资金到每个可交易的品种

### 策略参数

| 参数名 | 类型 | 默认值 | 说明 |
|-------|-----|--------|------|
| period | int | 60 | 均线周期（日） |
| verbose | bool | False | 是否输出详细日志 |

## 适用场景

1. **市场环境**：适合有明显趋势的市场环境
2. **品种选择**：适用于流动性好、相关性低的多个可转债
3. **时间周期**：日线级别交易策略
4. **资产配置**：适合分散化投资的组合管理

## 风险提示

1. **滞后性**：均线是滞后指标，入场点可能偏离趋势起点
2. **震荡市风险**：横盘震荡时容易产生频繁交易和连续亏损
3. **资金分配**：等权重分配可能导致资金利用率不高
4. **数据依赖**：需要多个品种的高质量历史数据
5. **滑点成本**：多品种交易产生的总交易成本较高

## 回测示例

```python
import backtrader as bt

# 加载策略
from strategies.simple_ma_multi_data.strategy import SimpleMAMultiDataStrategy, ExtendPandasFeed

cerebro = bt.Cerebro()

# 加载指数数据（用于时间对齐）
index_df = load_index_data('bond_index_000000.csv')
index_feed = ExtendPandasFeed(dataname=index_df)
cerebro.adddata(index_feed, name="index")

# 加载多个可转债数据
bond_data_dict = load_bond_data_multi('bond_merged_all_data.csv', max_bonds=100)
for bond_code, bond_df in bond_data_dict.items():
    feed = ExtendPandasFeed(dataname=bond_df)
    cerebro.adddata(feed, name=bond_code)

# 添加策略
cerebro.addstrategy(SimpleMAMultiDataStrategy, period=60, verbose=False)

# 运行回测
results = cerebro.run()
```

## 参考资料

1. 移动平均线理论
2. 多资产组合管理
3. 趋势跟踪策略
