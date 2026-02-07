# Sky Garden日内跳空策略

## 策略简介

Sky Garden（天空花园）策略是一个基于跳空开盘和第一根K线突破的日内交易策略。策略通过检测开盘跳空方向，配合第一根K线的高低点突破来判断入场时机，在收盘前自动平仓。

## 策略原理

### 核心思想

跳空开盘反映市场情绪变化，第一根K线定义当日波动区间：
- **向上跳空**：开盘价高于前日收盘价，看涨信号
- **向下跳空**：开盘价低于前日收盘价，看跌信号

### 交易规则

**跳空条件**：
- 向上跳空：开盘价 > 前收盘 × (1 + k1/1000)
- 向下跳空：开盘价 < 前收盘 × (1 - k2/1000)

**开多仓**：
- 满足向上跳空条件
- 价格突破第一根K线的高点

**开空仓**：
- 满足向下跳空条件
- 价格跌破第一根K线的低点

**平仓规则**：
- 14:55强制平仓所有持仓

### 策略参数

| 参数名 | 类型 | 默认值 | 说明 |
|-------|-----|--------|------|
| k1 | int | 8 | 向上跳空阈值（千分比，0.8%） |
| k2 | int | 8 | 向下跳空阈值（千分比，0.8%） |

## 适用场景

1. **市场环境**：适合有明显跳空特征的品种
2. **品种选择**：锌、铜等有色金属期货
3. **时间周期**：日内交易，不隔夜持仓
4. **市场状态**：外盘影响大、开盘跳空频繁的品种

## 风险提示

1. **假跳空**：开盘后可能迅速回补跳空
2. **日内风险**：必须收盘前平仓
3. **波动限制**：第一根K线后可能无交易机会
4. **手续费占比**：相对较低，但胜率依赖跳空质量
5. **限制交易**：无跳空时当日无交易

## 回测示例

```python
import backtrader as bt
from backtrader.comminfo import ComminfoFuturesPercent

# 加载策略
from strategies.sky_garden.strategy import SkyGardenStrategy, ZnPandasFeed

cerebro = bt.Cerebro()

# 加载数据
df = load_zn889_data("ZN889.csv")
feed = ZnPandasFeed(dataname=df)
cerebro.adddata(feed, name="ZN")

# 设置期货交易参数
comm = ComminfoFuturesPercent(commission=0.0003, margin=0.10, mult=10)
cerebro.broker.addcommissioninfo(comm, name="ZN")
cerebro.broker.setcash(50000)

# 添加策略
cerebro.addstrategy(SkyGardenStrategy, k1=8, k2=8)

# 运行回测
results = cerebro.run()
```

## 参考资料

1. 跳空开盘交易理论
2. 日外盘影响分析
3. 第一根K线交易法
