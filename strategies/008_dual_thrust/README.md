# Dual Thrust日内突破策略

## 策略简介

Dual Thrust策略是经典的日内突破策略，由Michael Chalek开发。策略根据前N日的行情波动区间计算当日的上下轨，在交易时段内突破上轨做多，突破下轨做空，并在收盘前自动平仓。

## 策略原理

### 核心公式

```
Range = max(最高价的最大值 - 收盘价的最小值, 收盘价的最大值 - 最低价的最小值)
上轨 = 开盘价 + k1 × Range
下轨 = 开盘价 - k2 × Range
```

其中：
- HH：N日内最高价的最高值
- HC：N日内收盘价的最高值
- LC：N日内收盘价的最低值
- LL：N日内最低价的最低值

### 交易规则

**交易时间**：
- 日盘：9:00-11:00
- 夜盘：21:00-23:00

**开多仓**：
- 价格突破上轨
- 当前无持仓或持有空单（反手）

**开空仓**：
- 价格突破下轨
- 当前无持仓或持有多单（反手）

**平仓规则**：
- 收盘前14:55强制平仓
- 反手时自动平旧仓开新仓

### 策略参数

| 参数名 | 类型 | 默认值 | 说明 |
|-------|-----|--------|------|
| look_back_days | int | 10 | 回看天数（用于计算Range） |
| k1 | float | 0.5 | 上轨系数 |
| k2 | float | 0.5 | 下轨系数 |

## 适用场景

1. **市场环境**：适合波动性较大的期货品种
2. **品种选择**：玻璃、螺纹钢等商品期货
3. **时间周期**：日内交易，不隔夜持仓
4. **交易时段**：有明显开盘跳空和盘中突破的品种

## 风险提示

1. **日内风险**：必须收盘前平仓，可能错过收盘前的有利机会
2. **假突破**：开盘后可能迅速触发假突破信号
3. **跳空风险**：次日开盘跳空可能造成损失
4. **手续费占比**：日内交易频繁，手续费成本较高
5. **滑点影响**：日内交易对滑点更敏感

## 回测示例

```python
import backtrader as bt
from backtrader.comminfo import ComminfoFuturesFixed

# 加载策略
from strategies.dual_thrust.strategy import DualThrustStrategy, FgPandasFeed

cerebro = bt.Cerebro()

# 加载数据
df = load_fg_data("FG889.csv")
feed = FgPandasFeed(dataname=df)
cerebro.adddata(feed, name="FG")

# 设置期货交易参数
comm = ComminfoFuturesFixed(commission=26, margin=0.15, mult=20)
cerebro.broker.addcommissioninfo(comm, name="FG")
cerebro.broker.setcash(50000)

# 添加策略
cerebro.addstrategy(DualThrustStrategy, look_back_days=10, k1=0.5, k2=0.5)

# 运行回测
results = cerebro.run()
```

## 参考资料

1. Dual Thrust策略原理
2. 日内交易策略研究
3. 期货日内波动特征
