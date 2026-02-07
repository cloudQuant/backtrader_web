# 数据重放策略

## 策略简介

本策略演示Backtrader的数据重放（replaydata）功能。replaydata与resampledata不同，它会按新时间框架重新计算和生成数据点。

## 策略原理

### Replay vs Resample

**resampledata（重采样）：**
- 保留原始数据点
- 按新时间框架聚合数据
- 信号基于原始时间框架触发

**replaydata（重放）：**
- 按新时间框架重新计算数据
- 数据点更平滑
- 信号基于新时间框架触发
- 需要设置preload=False

**主要区别：**

| 特性 | resampledata | replaydata |
|------|-------------|------------|
| 数据点 | 保留原始 | 重新计算 |
| 内存占用 | 较高 | 较低 |
| 信号时机 | 原框架 | 新框架 |
| preload | 可True/False | 必须False |
| 使用场景 | 多框架分析 | 单框架重放 |

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

- 需要在新时间框架上完整回测
- 降低数据存储需求
- 简化策略逻辑（单时间框架）
- 减少市场噪音影响

## 风险提示

1. replaydata需要设置preload=False
2. 重放后数据点减少，可能影响策略表现
3. 参数需要根据新时间框架调整
4. 与resampledata的结果可能不同

## 使用示例

### 日线重放为周线

```python
import backtrader as bt
from strategy_data_replay import ReplayMAStrategy, load_config

# 加载配置
config = load_config()
params = config['params']

# 创建Cerebro引擎
cerebro = bt.Cerebro()
cerebro.broker.setcash(100000)

# 加载日K线数据
data = bt.feeds.BacktraderCSVData(dataname='daily_data.csv')

# 重放为周K线
cerebro.replaydata(
    data,
    timeframe=bt.TimeFrame.Weeks,
    compression=1
)

# 添加策略
cerebro.addstrategy(ReplayMAStrategy, **params)
cerebro.addsizer(bt.sizers.FixedSize, stake=10)

# 添加分析器（使用周线时间框架）
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                    timeframe=bt.TimeFrame.Weeks, annualize=True)
cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

# 运行回测（必须设置preload=False）
results = cerebro.run(preload=False)
```

### 日线重放为月线

```python
# 重放为月K线
cerebro.replaydata(
    data,
    timeframe=bt.TimeFrame.Months,
    compression=1
)
```

### 分钟数据重放为小时数据

```python
# 5分钟数据重放为30分钟
cerebro.replaydata(
    data,
    timeframe=bt.TimeFrame.Minutes,
    compression=6  # 5分钟 * 6 = 30分钟
)
```

### 带名称的数据重放

```python
data = bt.feeds.BacktraderCSVData(dataname='data.csv')
cerebro.replaydata(data, timeframe=bt.TimeFrame.Weeks, name='weekly')

# 策略中可以通过名称访问
def next(self):
    print(self.getbyname('weekly').close[0])
```

## resampledata vs replaydata 详细对比

### 数据生成方式

**resampledata：**
```python
# 原始日数据
# 1月1日: 100
# 1月2日: 101
# 1月3日: 102
# ... 1月7日: 107

# resample后保留所有点，按周聚合
# 第1周: 100, 101, 102, ..., 107
```

**replaydata：**
```python
# 原始日数据
# 1月1日: 100
# 1月2日: 101
# 1月3日: 102
# ... 1月7日: 107

# replay后只生成周线点
# 第1周: OHLC从日数据计算
```

### 性能对比

| 指标 | resampledata | replaydata |
|------|-------------|------------|
| 内存使用 | 高 | 低 |
| 执行速度 | 较慢 | 较快 |
| 数据完整性 | 保留原始 | 重计算 |

## 使用建议

### 选择replaydata的场景

1. 只需要新时间框架的数据
2. 内存有限
3. 不需要原始时间框架数据
4. 策略只在新框架上运行

### 选择resampledata的场景

1. 需要多时间框架对比
2. 需要保留原始数据
3. 策略使用多框架信号

## 参数调整

重放后，策略参数需要相应调整：

| 原框架 | 新框架 | 建议参数调整 |
|--------|--------|-------------|
| 日线(10,30) | 周线 | (5,15) |
| 日线(10,30) | 月线 | (3,10) |
| 小时(20,60) | 日线 | (10,30) |

## 参考

- 原始来源：backtrader-master2/samples/data-replay/data-replay.py
