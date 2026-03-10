# R-Breaker日内突破策略

## 策略简介

R-Breaker策略是经典的日内交易策略，根据前一日的高、低、收盘价计算出当日的支撑阻力位。策略包含突破交易和反转交易两种逻辑：突破R3做多、跌破S3做空；同时在R1/S1位置设置反转信号。

## 策略原理

### 价格水平计算

```
Pivot点 = (前高 + 前低 + 前收) / 3
R1 = Pivot + k1 × (前高 - 前低)
R3 = Pivot + (k1 + k2) × (前高 - 前低)
S1 = Pivot - k1 × (前高 - 前低)
S3 = Pivot - (k1 + k2) × (前高 - 前低)
```

其中：
- Pivot：核心轴心点
- R1/R3：阻力位（Resistance）
- S1/S3：支撑位（Support）

### 交易规则

**交易时间**：
- 夜盘：21:00-23:00
- 日盘：9:00-11:00

**突破交易**：
- 突破R3：做多
- 跌破S3：做空

**反转交易**：
- 持有多单时，价格跌破R1：平多并开空
- 持有空单时，价格突破S1：平空并开多

**强制平仓**：
- 14:55强制平仓所有持仓

### 策略参数

| 参数名 | 类型 | 默认值 | 说明 |
|-------|-----|--------|------|
| k1 | float | 0.5 | R1/S1系数 |
| k2 | float | 0.5 | R3/S3额外系数 |

## 适用场景

1. **市场环境**：适合有明确开盘跳空和日内波动的品种
2. **品种选择**：螺纹钢、铁矿石等商品期货
3. **时间周期**：日内交易，不隔夜持仓
4. **市场状态**：趋势明显的交易日效果更好

## 风险提示

1. **日内风险**：必须收盘前平仓
2. **假突破**：开盘后可能出现假突破
3. **反转风险**：反转信号可能在趋势行情中导致亏损
4. **手续费占比**：频繁交易产生较高手续费
5. **跳空风险**：次日跳空造成隔夜风险（如果未及时平仓）

## 回测示例

```python
import backtrader as bt
from backtrader.comminfo import ComminfoFuturesPercent

# 加载策略
from strategies.r_breaker.strategy import RBreakerStrategy, RbPandasFeed

cerebro = bt.Cerebro()

# 加载数据
df = load_rb889_data("RB889.csv")
feed = RbPandasFeed(dataname=df)
cerebro.adddata(feed, name="RB")

# 设置期货交易参数
comm = ComminfoFuturesPercent(commission=0.0003, margin=0.10, mult=10)
cerebro.broker.addcommissioninfo(comm, name="RB")
cerebro.broker.setcash(50000)

# 添加策略
cerebro.addstrategy(RBreakerStrategy, k1=0.5, k2=0.5)

# 运行回测
results = cerebro.run()
```

## 参考资料

1. R-Breaker策略原理
2. Pivot点分析方法
3. 日内支撑阻力位理论
