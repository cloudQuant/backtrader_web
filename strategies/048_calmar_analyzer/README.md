# Calmar比率分析策略

## 策略简介

本策略实现了双移动平均线交叉交易系统，专门用于测试Backtrader框架中的Calmar比率分析器。Calmar比率是一个重要的风险调整后收益指标。

## 策略原理

### Calmar比率

Calmar比率（Calmar Ratio）是衡量投资组合风险调整后收益的指标，计算公式为：

```
Calmar比率 = 年化收益率 / 最大回撤
```

- **年化收益率**：策略在一年内的平均收益率
- **最大回撤**：从峰值到谷底的最大跌幅

**解读：**
- Calmar比率越高，表示单位风险下的回报越高
- 负值表示年化收益为负
- 通常认为Calmar比率 > 3 为优秀表现

### 交易逻辑

1. **买入信号**：快速SMA（周期15）上穿慢速SMA（周期50）
2. **卖出信号**：快速SMA下穿慢速SMA
3. **持仓管理**：始终保持单边持仓（多头或现金）

## 策略参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| p1 | 快速移动平均线周期 | 15 |
| p2 | 慢速移动平均线周期 | 50 |

## 适用场景

- 趋势明显的市场环境
- 需要评估风险调整后收益的场景
- 策略性能对比分析

## 风险提示

1. 双均线策略在震荡市中容易产生频繁交易
2. Calmar比率对回撤敏感，极端行情下可能失真
3. 历史表现不代表未来收益
4. 建议结合其他指标综合评估策略表现

## 使用示例

```python
import backtrader as bt
from strategy_calmar import CalmarTestStrategy, load_config

# 加载配置
config = load_config()

# 创建Cerebro引擎
cerebro = bt.Cerebro()
cerebro.broker.setcash(100000)

# 添加数据
# ...

# 添加策略
params = config['params']
cerebro.addstrategy(CalmarTestStrategy, **params)

# 添加Calmar分析器
cerebro.addanalyzer(bt.analyzers.Calmar, _name="calmar")
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")

# 运行回测
results = cerebro.run()
```

## 分析器输出

运行回测后，Calmar分析器将输出以下指标：

- **Calmar比率**：主要风险调整后收益指标
- **Sharpe比率**：另一个风险调整指标
- **最大回撤**：历史最大跌幅
- **年化收益率**：策略平均年回报

## 参考

- 原始来源：backtrader-master2/samples/calmar/calmar-test.py
