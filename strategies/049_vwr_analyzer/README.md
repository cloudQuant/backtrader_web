# VWR波动率加权收益率策略

## 策略简介

本策略实现了双移动平均线交叉交易系统，用于测试Backtrader框架中的VWR（Variability-Weighted Return，波动率加权收益率）分析器。

## 策略原理

### VWR指标

VWR（Variability-Weighted Return）是一个风险调整后收益指标，与夏普比率类似但计算方法不同。

**核心概念：**
- 考虑收益率的波动性
- 对高波动策略给予惩罚
- 更全面地评估风险调整后表现

**与Sharpe比率的区别：**
- Sharpe比率使用标准差作为风险度量
- VWR使用不同的波动性计算方法
- 两者都是衡量单位风险下的超额收益

### 交易逻辑

1. **买入信号**：快速SMA（周期10）上穿慢速SMA（周期30）
2. **卖出信号**：快速SMA下穿慢速SMA
3. **持仓管理**：始终保持单边持仓（多头或现金）

## 策略参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| p1 | 快速移动平均线周期 | 10 |
| p2 | 慢速移动平均线周期 | 30 |

## 适用场景

- 需要评估波动率调整后收益的策略
- 风险敏感型投资组合
- 策略性能对比分析

## 风险提示

1. 短周期均线策略信号频繁，交易成本较高
2. VWR指标对极端值敏感
3. 历史表现不代表未来收益
4. 建议结合Sharpe比率、SQN等指标综合评估

## 使用示例

```python
import backtrader as bt
from strategy_vwr import VWRTestStrategy, load_config

# 加载配置
config = load_config()

# 创建Cerebro引擎
cerebro = bt.Cerebro()
cerebro.broker.setcash(100000)

# 添加数据
# ...

# 添加策略
params = config['params']
cerebro.addstrategy(VWRTestStrategy, **params)

# 添加分析器
cerebro.addanalyzer(bt.analyzers.VWR, _name="vwr")
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
cerebro.addanalyzer(bt.analyzers.SQN, _name="sqn")
cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")

# 运行回测
results = cerebro.run()
```

## 分析器输出

运行回测后，可获取以下指标：

- **VWR比率**：波动率加权收益率
- **Sharpe比率**：经典风险调整收益指标
- **SQN**：系统质量数
- **最大回撤**：历史最大跌幅

## 参考

- 原始来源：backtrader-master2/samples/vwr/vwr.py
