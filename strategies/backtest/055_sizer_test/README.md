# 仓位管理测试策略

## 策略简介

本策略演示Backtrader中Sizer（仓位管理器）的使用。Sizer用于控制每次交易的数量，是风险管理的重要组成部分。

## 策略原理

### Sizer（仓位管理器）

**Sizer是Backtrader中控制交易数量的组件：**

- 每次下单时，Sizer决定交易多少股/合约
- 可以根据现金、风险、固定数量等规则计算
- 支持自定义Sizer实现复杂的仓位管理逻辑

### 内置Sizer类型

1. **FixedSize**：固定数量
   ```python
   cerebro.addsizer(bt.sizers.FixedSize, stake=100)
   ```

2. **FixedReverser**：固定数量，支持反向
   ```python
   cerebro.addsizer(bt.sizers.FixedReverser, stake=100)
   ```

3. **Percent**：按资金百分比
   ```python
   cerebro.addsizer(bt.sizers.Percent, percents=10)
   ```

4. **AllIn**：全仓
   ```python
   cerebro.addsizer(bt.sizers.AllIn)
   ```

### 交易逻辑

1. **买入信号**：价格上穿SMA（周期15）
2. **卖出信号**：价格下穿SMA
3. **仓位控制**：使用LongOnlySizer确保只做多

## 策略参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| period | SMA周期 | 15 |

## Sizer配置

| 类型 | 参数说明 |
|------|----------|
| LongOnly | stake: 每次交易股数 |
| Fixed | stake: 每次交易股数 |
| Percent | percents: 使用资金百分比 |

## 适用场景

- 需要精确控制交易数量的策略
- 风险管理中的仓位控制
- 资金管理规则实现

## 风险提示

1. 仓位过大可能导致风险过高
2. 固定仓位不考虑账户资金变化
3. 建议结合止损和风险控制
4. 不同市场需要不同的仓位策略

## 使用示例

### 使用固定数量Sizer

```python
import backtrader as bt
from strategy_sizer import SizerTestStrategy, load_config

# 加载配置
config = load_config()

# 创建Cerebro引擎
cerebro = bt.Cerebro()
cerebro.broker.setcash(50000)

# 添加数据
# ...

# 添加策略
params = config['params']
cerebro.addstrategy(SizerTestStrategy, **params)

# 添加固定数量Sizer
cerebro.addsizer(bt.sizers.FixedSize, stake=100)

# 运行回测
results = cerebro.run()
```

### 使用百分比Sizer

```python
# 使用可用资金的10%进行每次交易
cerebro.addsizer(bt.sizers.Percent, percents=10)
```

### 使用全仓Sizer

```python
# 每次全仓买入/卖出
cerebro.addsizer(bt.sizers.AllIn)
```

## 自定义Sizer

### 固定金额Sizer

```python
class FixedAmount(bt.Sizer):
    """每次交易固定金额"""

    params = (('amount', 10000),)  # 每次交易10000元

    def _getsizing(self, comminfo, cash, data, isbuy):
        if isbuy:
            # 计算可以买入的股数
            size = self.p.amount / data.close[0]
            return int(size)
        # 卖出时返回持仓数量
        position = self.broker.getposition(data)
        return position.size
```

### 风险百分比Sizer

```python
class RiskPercentSizer(bt.Sizer):
    """根据风险百分比决定仓位"""

    params = (
        ('risk_pct', 0.02),     # 风险百分比2%
        ('stop_distance', 0.05), # 止损距离5%
    )

    def _getsizing(self, comminfo, cash, data, isbuy):
        if not isbuy:
            position = self.broker.getposition(data)
            return position.size

        # 风险金额
        risk_amount = cash * self.p.risk_pct

        # 每股风险 = 止损距离
        risk_per_share = data.close[0] * self.p.stop_distance

        # 计算股数
        if risk_per_share > 0:
            size = int(risk_amount / risk_per_share)
            return max(0, size)

        return 0
```

### 波动率调整Sizer

```python
class VolatilitySizer(bt.Sizer):
    """根据ATR波动率调整仓位"""

    params = (
        ('atr_period', 14),
        ('risk_pct', 0.02),
    )

    def __init__(self):
        self.atr = bt.ind.ATR(period=self.p.atr_period)

    def _getsizing(self, comminfo, cash, data, isbuy):
        if not isbuy:
            position = self.broker.getposition(data)
            return position.size

        # 使用ATR作为风险度量
        risk_amount = cash * self.p.risk_pct
        atr_value = self.atr[0]

        if atr_value > 0:
            size = int(risk_amount / atr_value)
            return max(0, size)

        return 0
```

### 凯利公式Sizer

```python
class KellySizer(bt.Sizer):
    """使用凯利公式计算仓位"""

    params = (
        ('win_rate', 0.55),     # 胜率
        ('avg_win', 1.5),       # 平均盈利/平均亏损比
        ('risk_pct', 0.02),     # 基础风险百分比
    )

    def _getsizing(self, comminfo, cash, data, isbuy):
        if not isbuy:
            position = self.broker.getposition(data)
            return position.size

        # 凯利公式: f = (bp - q) / b
        # b = 盈亏比, p = 胜率, q = 败率
        b = self.p.avg_win
        p = self.p.win_rate
        q = 1 - p

        kelly_pct = (b * p - q) / b

        # 限制最大仓位为风险的2倍
        kelly_pct = min(kelly_pct, self.p.risk_pct * 2)
        kelly_pct = max(kelly_pct, 0)  # 不做空

        amount = cash * kelly_pct
        size = int(amount / data.close[0])

        return max(0, size)
```

## Sizer选择指南

| 场景 | 推荐Sizer |
|------|-----------|
| 初学者/固定交易 | FixedSize |
| 资金管理 | Percent |
| 风险控制 | RiskPercentSizer |
| 波动率市场 | VolatilitySizer |
| 趋势策略 | FixedReverser |

## 参考

- 原始来源：backtrader-master2/samples/sizertest/sizertest.py
