# 参数优化策略

## 策略简介

本策略展示了Backtrader的参数优化功能，使用SMA与MACD组合指标，通过遍历参数空间寻找最优参数组合。

## 策略原理

### 指标组合

**MACD（移动平均收敛散度）：**
- 由快速EMA、慢速EMA和信号线组成
- 金叉（MACD上穿信号线）：买入信号
- 死叉（MACD下穿信号线）：卖出信号

**SMA（简单移动平均）：**
- 辅助指标，用于参数优化
- 可调整周期以优化策略表现

### 参数优化

**优化流程：**
1. 定义参数空间（如smaperiod从10到12）
2. 对每个参数组合运行回测
3. 计算每个组合的性能指标（如Sharpe比率）
4. 选择最优参数组合

**优化目标：**
- 最大化Sharpe比率（风险调整后收益）
- 最小化最大回撤
- 最大化年化收益率

## 策略参数

| 参数 | 说明 | 默认值 | 优化范围 |
|------|------|--------|----------|
| smaperiod | SMA周期 | 15 | 10-12 |
| macdperiod1 | MACD快速EMA | 12 | 固定 |
| macdperiod2 | MACD慢速EMA | 26 | 固定 |
| macdperiod3 | MACD信号线 | 9 | 固定 |

## 适用场景

- 策略开发阶段寻找最优参数
- 不同市场环境下的参数调整
- 策略性能对比分析

## 风险提示

1. **过拟合风险**：历史最优参数不代表未来表现
2. **数据窥探偏差**：过度优化可能导致策略失效
3. **计算成本**：参数空间越大，计算时间越长
4. 建议使用样本外数据进行参数验证

## 使用示例

### 基本回测

```python
import backtrader as bt
from strategy_optimization import OptimizeStrategy, load_config

# 加载配置
config = load_config()

# 创建Cerebro引擎
cerebro = bt.Cerebro()
cerebro.broker.setcash(100000)

# 添加数据
# ...

# 添加策略（使用单个参数组合）
params = config['params']
cerebro.addstrategy(OptimizeStrategy, **params)

# 运行回测
results = cerebro.run()
```

### 参数优化

```python
import backtrader as bt
from strategy_optimization import OptimizeStrategy, load_config

# 加载配置
config = load_config()

# 创建Cerebro引擎（启用优化）
cerebro = bt.Cerebro(maxcpus=1)
cerebro.broker.setcash(100000)

# 添加数据
# ...

# 参数优化：遍历smaperiod参数
opt_config = config.get('optimization', {})
sma_range = opt_config.get('smaperiod_range', [10, 11, 12])

cerebro.optstrategy(
    OptimizeStrategy,
    smaperiod=sma_range,
    macdperiod1=[12],
    macdperiod2=[26],
    macdperiod3=[9],
)

# 添加分析器
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                    timeframe=bt.TimeFrame.Days, annualize=True)
cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")

# 运行优化
results = cerebro.run()

# 找出最优参数
all_results = []
for stratrun in results:
    for strat in stratrun:
        params = strat.p._getkwargs()
        sharpe = strat.analyzers.sharpe.get_analysis().get('sharperatio', None)
        all_results.append({
            'smaperiod': params.get('smaperiod'),
            'sharpe_ratio': sharpe,
        })

best = max(all_results, key=lambda x: x['sharpe_ratio'] or -999)
print(f"Best parameters: {best}")
```

## 优化建议

1. **分阶段优化**：先优化单个参数，再优化多个参数
2. **避免过拟合**：预留样本外数据进行验证
3. **稳健性测试**：在多种市场环境下测试参数稳定性
4. **计算效率**：合理设置CPU核心数（maxcpus）

## 参考

- 原始来源：backtrader-master2/samples/optimization/optimization.py
