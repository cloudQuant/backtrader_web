# 佣金方案策略

## 策略简介

本策略演示Backtrader中不同佣金计算方案的使用，通过双移动平均线交叉策略测试佣金对策略表现的影响。

## 策略原理

### 佣金类型

Backtrader支持多种佣金计算方式：

1. **百分比佣金（COMM_PERC）**
   - 按交易金额的百分比收取
   - 适用于股票、期货等
   - 公式：佣金 = 交易金额 × 佣金率

2. **固定佣金（COMM_FIXED）**
   - 每笔交易固定金额
   - 适用于固定手续费场景
   - 公式：佣金 = 固定金额

3. **每手佣金（COMMISSION_PER_CONTRACT）**
   - 按合约/手数收取
   - 适用于期货、期权

### 交易逻辑

1. **买入信号**：快速SMA（周期10）上穿慢速SMA（周期30）
2. **卖出信号**：快速SMA下穿慢速SMA
3. **持仓管理**：始终保持单边持仓（多头或现金）

## 策略参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| stake | 每次交易股数 | 10 |
| fast_period | 快速移动平均线周期 | 10 |
| slow_period | 慢速移动平均线周期 | 30 |

## 佣金配置

| 类型 | rate说明 | 示例 |
|------|----------|------|
| percentage | 百分比（如0.001=0.1%） | 0.001 |
| fixed | 固定金额（如5元/笔） | 5.0 |

## 适用场景

- 真实交易前的成本评估
- 比较不同佣金方案的影响
- 优化交易频率与成本平衡

## 风险提示

1. 佣金会显著影响高频交易策略的收益
2. 真实交易中还有滑点等其他成本
3. 不同券商佣金标准不同
4. 佣金可能包含印花税、过户费等

## 使用示例

### 百分比佣金

```python
import backtrader as bt
from strategy_commission import (
    CommissionStrategy,
    load_config,
    setup_commission
)

# 加载配置
config = load_config()
params = config['params']

# 创建Cerebro引擎
cerebro = bt.Cerebro()
cerebro.broker.setcash(100000)

# 添加数据
# ...

# 添加策略
cerebro.addstrategy(CommissionStrategy, **params)

# 设置百分比佣金（0.1%）
cerebro.broker.setcommission(
    commission=0.001,
    commtype=bt.CommInfoBase.COMM_PERC,
    stocklike=True
)

# 运行回测
results = cerebro.run()

# 查看总佣金
strat = results[0]
print(f"Total commission: {strat.total_commission:.2f}")
```

### 固定佣金

```python
# 每笔交易固定5元
cerebro.broker.setcommission(
    commission=5.0,
    commtype=bt.CommInfoBase.COMM_FIXED,
    stocklike=True
)
```

### 股票全佣金方案（含印花税）

```python
# A股佣金方案示例
class StockCommInfo(bt.CommInfoBase):
    params = (
        ('commission', 0.0003),  # 券商佣金 0.03%
        ('stamp_duty', 0.001),   # 印花税 0.1%（仅卖出）
        ('min_commission', 5),   # 最低佣金 5元
    )

    def _getcommission(self, size, price, pseudoexec):
        # 计算基础佣金
        comm = abs(size) * price * self.p.commission
        # 最低佣金
        comm = max(comm, self.p.min_commission)

        # 卖出时加印花税
        if size < 0:  # 卖出
            stamp = abs(size) * price * self.p.stamp_duty
            comm += stamp

        return comm

# 使用自定义佣金
cerebro.broker.addcommissioninfo(StockCommInfo())
```

### 期货佣金

```python
# 期货按手收取
cerebro.broker.setcommission(
    commission=10,  # 每手10元
    commtype=bt.CommInfoBase.COMM_FIXED,
    margin=50000,   # 每手保证金
    mult=10,        # 合约乘数
)
```

### 不同品种不同佣金

```python
# 为不同数据源设置不同佣金
data1 = bt.feeds.BacktraderCSVData(dataname='stock.csv')
cerebro.adddata(data1, name='stock')

data2 = bt.feeds.BacktraderCSVData(dataname='future.csv')
cerebro.adddata(data2, name='future')

# 设置佣金
cerebro.broker.setcommission(commission=0.001, name='stock')
cerebro.broker.setcommission(commission=10, margin=50000, name='future')
```

## 佣金影响分析

### 交易频率 vs 佣金成本

| 策略类型 | 年化收益率（无佣金） | 年化收益率（0.1%佣金） |
|---------|---------------------|---------------------|
| 低频（<10次/年） | 15% | 14.5% |
| 中频（10-50次/年） | 15% | 13% |
| 高频（>50次/年） | 15% | 8% |

### 优化建议

1. **降低交易频率**：适当放宽交易条件
2. **提高单笔盈利**：确保单笔利润覆盖佣金成本
3. **选择低佣金券商**：长期可节省大量成本
4. **批量交易**：减少交易次数

## 常见佣金标准

### A股
- 券商佣金：0.02%-0.03%（最低5元）
- 印花税：0.1%（仅卖出）
- 过户费：0.001%

### 港股
- 佣金：0.03%-0.25%（最低50-100港币）
- 印花税：0.1%
- 交易征费：0.0027%

### 期货
- 手续费：按合约计算（如每手5-50元）
- 无印花税

## 参考

- 原始来源：backtrader-master2/samples/commission-schemes/commission-schemes.py
