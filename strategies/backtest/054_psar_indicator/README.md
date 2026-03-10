# 抛物线SAR策略

## 策略简介

本策略使用Parabolic SAR（抛物线转向）指标生成交易信号。PSAR是Welles Wilder开发的一个经典趋势跟踪指标，广泛用于技术分析。

## 策略原理

### Parabolic SAR指标

**PSAR（Parabolic Stop and Reverse）**是一个趋势跟踪指标，具有以下特点：

**核心概念：**
- SAR代表"止损和反转"
- 指标值随价格变动而加速变化
- 价格在SAR上方时为上升趋势，反之则为下降趋势

**计算公式：**
```
上升趋势: SAR = 前一日SAR + AF × (EP - 前一日SAR)
下降趋势: SAR = 前一日SAR + AF × (EP - 前一日SAR)
```
- AF（加速因子）：从0.02开始，每创新高增加0.02，最高0.2
- EP（极点）：趋势中的最高点或最低点

**指标特点：**
- 趋势市场表现优秀
- 震荡市场容易产生假信号
- 提供明确的止损位

### 交易逻辑

1. **买入信号**：收盘价上穿PSAR值
2. **卖出信号**：收盘价下穿PSAR值
3. **止损位**：PSAR值本身即为动态止损位

## 策略参数

PSAR指标使用默认参数，通常无需调整：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| period | SAR周期 | 2 |
| af | 加速因子初始值 | 0.02 |
| afmax | 加速因子最大值 | 0.2 |

## 适用场景

- 明显趋势的市场环境
- 需要动态止损的交易策略
- 中长期趋势跟踪

## 风险提示

1. 震荡市场中容易频繁止损
2. 趋势反转初期信号滞后
3. 不适合低波动率市场
4. 建议结合其他指标过滤信号

## 使用示例

```python
import backtrader as bt
from strategy_psar import PSARStrategy, load_config

# 加载配置
config = load_config()

# 创建Cerebro引擎
cerebro = bt.Cerebro()
cerebro.broker.setcash(100000)

# 添加数据
data = bt.feeds.BacktraderCSVData(dataname='data.csv')
cerebro.adddata(data)

# 添加策略
cerebro.addstrategy(PSARStrategy)

# 设置仓位大小
cerebro.addsizer(bt.sizers.FixedSize, stake=10)

# 添加分析器
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")

# 运行回测
results = cerebro.run()
```

## PSAR参数调整

```python
# 自定义PSAR参数
class CustomPSARStrategy(bt.Strategy):
    params = (
        ('period', 2),
        ('af', 0.02),    # 加速因子初始值
        ('afmax', 0.2),  # 加速因子最大值
    )

    def __init__(self):
        self.psar = bt.ind.ParabolicSAR(
            period=self.p.period,
            af=self.p.af,
            afmax=self.p.afmax
        )
```

## 信号过滤建议

### 趋势过滤

```python
class FilteredPSARStrategy(bt.Strategy):
    def __init__(self):
        self.psar = bt.ind.ParabolicSAR()
        self.adx = bt.ind.ADX()  # 趋势强度指标

    def next(self):
        # 只在ADX>25时交易（强趋势）
        if self.adx[0] < 25:
            return

        if self.data.close[0] > self.psar[0] and not self.position:
            self.buy()
        elif self.data.close[0] < self.psar[0] and self.position:
            self.sell()
```

### 波动率过滤

```python
class ATRFilteredPSARStrategy(bt.Strategy):
    params = (('atr_period', 14), ('atr_threshold', 0.01))

    def __init__(self):
        self.psar = bt.ind.ParabolicSAR()
        self.atr = bt.ind.ATR(period=self.p.atr_period)

    def next(self):
        # 只在高波动时交易
        if self.atr[0] / self.data.close[0] < self.p.atr_threshold:
            return

        if self.data.close[0] > self.psar[0] and not self.position:
            self.buy()
        elif self.data.close[0] < self.psar[0] and self.position:
            self.sell()
```

## PSAR与其他指标组合

### PSAR + MACD

```python
class PSARMACDStrategy(bt.Strategy):
    def __init__(self):
        self.psar = bt.ind.ParabolicSAR()
        self.macd = bt.ind.MACD()

    def next(self):
        # PSAR趋势 + MACD确认
        if self.data.close[0] > self.psar[0] and self.macd.macd[0] > self.macd.signal[0]:
            if not self.position:
                self.buy()
        elif self.data.close[0] < self.psar[0]:
            if self.position:
                self.sell()
```

## 指标可视化

PSAR指标通常以点状图形式显示在价格图表上：
- 价格上方：下降趋势，卖点
- 价格下方：上升趋势，买点

## 参考

- 原始来源：backtrader-master2/samples/psar/psar.py
- Wilder, J. Welles. "New Concepts in Technical Trading Systems" (1978)
