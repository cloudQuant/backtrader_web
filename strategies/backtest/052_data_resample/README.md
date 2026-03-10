# 数据重采样策略

## 策略简介

本策略演示Backtrader的数据重采样（Resample）功能，将日K线数据转换为周K线，并运行双移动平均线交叉策略。

## 策略原理

### 数据重采样

**重采样（Resampling）是指将数据从一个时间框架转换为另一个时间框架：**

- 日线 -> 周线
- 日线 -> 月线
- 分钟线 -> 小时线

**在Backtrader中使用resampledata：**

```python
cerebro.resampledata(
    data,
    timeframe=bt.TimeFrame.Weeks,  # 目标时间框架
    compression=1                  # 压缩比例
)
```

### 重采样方法

Backtrader支持两种数据转换方式：

1. **resampledata**：重采样数据（保留原始数据点）
2. **replaydata**：回放数据（以新时间框架重新计算）

### 交易逻辑

1. **买入信号**：快速SMA（周期5）上穿慢速SMA（周期15）
2. **卖出信号**：快速SMA下穿慢速SMA
3. **持仓管理**：始终保持单边持仓（多头或现金）

## 策略参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| fast_period | 快速移动平均线周期（周线） | 5 |
| slow_period | 慢速移动平均线周期（周线） | 15 |

## 时间框架

| TimeFrame | 值 | 说明 |
|-----------|-----|------|
| Minutes | 0 | 分钟级别 |
| Days | 1 | 日线 |
| Weeks | 2 | 周线 |
| Months | 3 | 月线 |
| Years | 4 | 年线 |

## 适用场景

- 需要在不同时间框架上分析数据
- 降低数据噪声，提高信号质量
- 长周期策略回测
- 多时间框架分析

## 风险提示

1. 重采样后数据点减少，可能导致信号延迟
2. 不同重采样方法可能产生不同结果
3. 参数需要根据新时间框架调整
4. 注意数据对齐问题

## 使用示例

### 日线转周线

```python
import backtrader as bt
from strategy_data_resample import SimpleMAStrategy, load_config

# 加载配置
config = load_config()
params = config['params']

# 创建Cerebro引擎
cerebro = bt.Cerebro()
cerebro.broker.setcash(100000)

# 加载日K线数据
data = bt.feeds.BacktraderCSVData(dataname='daily_data.csv')

# 重采样为周K线
cerebro.resampledata(
    data,
    timeframe=bt.TimeFrame.Weeks,
    compression=1
)

# 添加策略
cerebro.addstrategy(SimpleMAStrategy, **params)

# 添加分析器（使用周线时间框架）
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                    timeframe=bt.TimeFrame.Weeks, annualize=True)

# 运行回测
results = cerebro.run()
```

### 日线转月线

```python
# 重采样为月K线
cerebro.resampledata(
    data,
    timeframe=bt.TimeFrame.Months,
    compression=1
)
```

### 压缩数据

```python
# 将5分钟数据压缩为30分钟
cerebro.resampledata(
    data,
    timeframe=bt.TimeFrame.Minutes,
    compression=6  # 5分钟 * 6 = 30分钟
)
```

### 多数据源不同时间框架

```python
# 数据1：日线
data1 = bt.feeds.BacktraderCSVData(dataname='daily.csv')
cerebro.adddata(data1, name='daily')

# 数据2：周线（从同一数据重采样）
data2 = bt.feeds.BacktraderCSVData(dataname='daily.csv')
cerebro.resampledata(data2, timeframe=bt.TimeFrame.Weeks, name='weekly')

# 策略可以使用self.data0和self.data1访问不同时间框架的数据
```

## resampledata vs replaydata

| 特性 | resampledata | replaydata |
|------|-------------|------------|
| 数据生成 | 保留原始数据点 | 按新框架重新计算 |
| 信号时机 | 原框架信号 | 新框架信号 |
| 使用场景 | 需要原始和新框架 | 仅需要新框架 |
| 性能 | 内存占用较高 | 内存占用较低 |

### 使用replaydata

```python
# replaydata会按周重新计算数据
cerebro.replaydata(
    data,
    timeframe=bt.TimeFrame.Weeks,
    compression=1
)
```

## 参数调整建议

重采样后，策略参数需要相应调整：

| 原时间框架 | 新时间框架 | 建议参数调整 |
|-----------|-----------|-------------|
| 日线(10,30) | 周线 | (5,15) |
| 日线(10,30) | 月线 | (3,10) |
| 小时(20,60) | 日线 | (10,30) |

## 参考

- 原始来源：backtrader-master2/samples/data-resample/data-resample.py
