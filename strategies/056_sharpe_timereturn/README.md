# Sharpe比率与时间收益率分析策略

## 策略简介

本策略演示Backtrader中Sharpe比率和TimeReturn分析器的使用，用于评估策略的风险调整后收益和不同时间周期的收益率表现。

## 策略原理

### Sharpe比率

**Sharpe比率**是衡量风险调整后收益的核心指标，由诺贝尔奖得主William Sharpe提出。

**计算公式：**
```
Sharpe比率 = (策略收益率 - 无风险收益率) / 收益率标准差
```

**解读标准：**
- Sharpe < 1：较差
- 1 <= Sharpe < 2：良好
- Sharpe >= 2：优秀
- Sharpe >= 3：卓越

### TimeReturn分析器

**TimeReturn**计算不同时间周期的收益率：
- 年度收益率
- 月度收益率
- 周度收益率

**收益率类型：**
- 累计收益率：总收益百分比
- 年化收益率：转换为年度收益率

### 交易逻辑

1. **买入信号**：快速SMA（周期10）上穿慢速SMA（周期30）
2. **卖出信号**：快速SMA下穿慢速SMA
3. **持仓管理**：始终保持单边持仓（多头或现金）

## 策略参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| p1 | 快速移动平均线周期 | 10 |
| p2 | 慢速移动平均线周期 | 30 |

## 分析器配置

| 分析器 | 配置项 | 说明 |
|--------|--------|------|
| SharpeRatio | timeframe | 计算周期（Days/Weeks/Months） |
| SharpeRatio | annualize | 是否年化 |
| TimeReturn | timeframe | 时间周期（Years/Months/Weeks） |

## 适用场景

- 策略性能评估
- 风险调整后收益分析
- 不同策略对比
- 投资组合优化

## 风险提示

1. Sharpe比率假设收益正态分布，实际市场可能不符
2. 高Sharpe不一定意味着策略可持续
3. 无风险利率选择会影响结果
4. 建议结合其他指标综合评估

## 使用示例

### 基础用法

```python
import backtrader as bt
from strategy_sharpe_timereturn import SharpeTestStrategy, load_config

# 加载配置
config = load_config()
params = config['params']

# 创建Cerebro引擎
cerebro = bt.Cerebro()
cerebro.broker.setcash(100000)

# 添加数据
# ...

# 添加策略
cerebro.addstrategy(SharpeTestStrategy, **params)
cerebro.addsizer(bt.sizers.FixedSize, stake=10)

# 添加Sharpe比率分析器（日线，年化）
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                    timeframe=bt.TimeFrame.Days, annualize=True)

# 添加TimeReturn分析器
cerebro.addanalyzer(bt.analyzers.TimeReturn,
                    timeframe=bt.TimeFrame.Years, _name="yearly")
cerebro.addanalyzer(bt.analyzers.TimeReturn,
                    timeframe=bt.TimeFrame.Months, _name="monthly")

# 添加其他分析器
cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

# 运行回测
results = cerebro.run()
strat = results[0]

# 获取分析结果
sharpe = strat.analyzers.sharpe.get_analysis()
yearly = strat.analyzers.yearly.get_analysis()
monthly = strat.analyzers.monthly.get_analysis()
ret = strat.analyzers.returns.get_analysis()
drawdown = strat.analyzers.drawdown.get_analysis()

# 打印结果
print(f"Sharpe Ratio: {sharpe.get('sharperatio')}")
print(f"Annual Return: {ret.get('rnorm')}")
print(f"Max Drawdown: {drawdown['max']['drawdown']}")
print(f"Yearly Returns: {yearly}")
print(f"Monthly Returns: {monthly}")
```

### 不同时间框架的Sharpe比率

```python
# 日线Sharpe
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe_daily",
                    timeframe=bt.TimeFrame.Days, annualize=True)

# 周线Sharpe
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe_weekly",
                    timeframe=bt.TimeFrame.Weeks, annualize=True)

# 月线Sharpe
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe_monthly",
                    timeframe=bt.TimeFrame.Months, annualize=True)
```

### 带无风险利率的Sharpe比率

```python
# 设置无风险利率为3%
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                    timeframe=bt.TimeFrame.Days,
                    annualize=True,
                    riskfreerate=0.03)
```

### 自定义无风险利率

```python
# 使用动态无风险利率
class CustomSharpe(bt.Analyzer):
    params = ('rf_rate',)

    def __init__(self):
        self.rf_rate = self.p.rf_rate

    def create_analysis(self, strategy):
        # 计算超额收益
        excess_returns = []
        # ... 计算逻辑
        pass
```

## TimeReturn使用

### 年度收益率

```python
cerebro.addanalyzer(bt.analyzers.TimeReturn,
                    timeframe=bt.TimeFrame.Years, _name="yearly")

# 输出示例：
# {datetime(2005, 12, 31): 0.05, datetime(2006, 12, 31): 0.08}
```

### 月度收益率

```python
cerebro.addanalyzer(bt.analyzers.TimeReturn,
                    timeframe=bt.TimeFrame.Months, _name="monthly")
```

### 累计收益率

```python
# TimeReturn默认计算累计收益率
cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="cumreturn")
```

## 其他重要分析器

### Returns分析器

```python
cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")

# 可获取：
# rnorm: 正态年化收益率
# ravg: 平均收益率
```

### DrawDown分析器

```python
cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")

# 可获取：
# max: 最大回撤信息
#   - drawdown: 回撤百分比
#   - money: 回撤金额
#   - datetime: 回撤日期
```

### TradeAnalyzer分析器

```python
cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

# 可获取：
# total: 总交易统计
# won: 盈利交易统计
# lost: 亏损交易统计
# streak: 连续盈亏统计
```

## 综合评估指标

完整评估应包括：

```python
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
cerebro.addanalyzer(bt.analyzers.SQN, _name="sqn")  # 系统质量数
cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="timereturn")
```

## 参考

- 原始来源：backtrader-master2/samples/sharpe-timereturn/sharpe-timereturn.py
- Sharpe, William F. "The Sharpe Ratio" (1994)
