# 多数据源策略

## 策略简介

本策略演示如何在Backtrader中使用多个数据源。策略从一个数据源（data1）生成交易信号，然后在另一个数据源（data0）上执行交易。

## 策略原理

### 多数据源架构

**数据源角色分工：**
- **data0**：交易数据源，实际买卖的目标
- **data1**：信号数据源，用于生成交易信号

**工作流程：**
1. 在data1上计算技术指标（如SMA）
2. 根据data1的指标交叉生成交易信号
3. 在data0上执行买卖操作

### 交易逻辑

1. **买入信号**：data1的收盘价上穿SMA（周期15）
2. **卖出信号**：data1的收盘价下穿SMA
3. **执行交易**：在data0上进行买卖操作

## 策略参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| period | SMA周期（用于data1信号生成） | 15 |
| stake | 每次交易股数 | 10 |

## 适用场景

- **配对交易**：相关品种之间的价差交易
- **期现套利**：期货与现货之间的套利
- **跨市场交易**：不同市场的同一品种
- **信号跟随**：使用指数信号交易个股

## 风险提示

1. 多数据源需要确保时间对齐
2. 信号数据与交易数据的延迟可能影响效果
3. 佣金和滑点会显著影响收益
4. 建议充分测试数据源之间的相关性

## 使用示例

### 基础多数据源策略

```python
import backtrader as bt
from strategy_multidata import MultiDataStrategy, load_config

# 加载配置
config = load_config()
params = config['params']

# 创建Cerebro引擎
cerebro = bt.Cerebro()
cerebro.broker.setcash(100000)

# 加载交易数据源（data0）
data0 = bt.feeds.YahooFinanceCSVData(
    dataname='stock.csv',
    fromdate=datetime.datetime(2005, 1, 1),
    todate=datetime.datetime(2006, 12, 31)
)
cerebro.adddata(data0, name='Data0')

# 加载信号数据源（data1）
data1 = bt.feeds.YahooFinanceCSVData(
    dataname='index.csv',
    fromdate=datetime.datetime(2005, 1, 1),
    todate=datetime.datetime(2006, 12, 31)
)
cerebro.adddata(data1, name='Data1')

# 添加策略
cerebro.addstrategy(MultiDataStrategy, **params)

# 设置佣金
cerebro.broker.setcommission(commission=0.005)

# 运行回测
results = cerebro.run()
```

### 使用同一数据的两个实例

```python
# 使用相同文件但作为两个数据源
data_path = 'data.csv'

# 数据0：交易目标
data0 = bt.feeds.BacktraderCSVData(dataname=data_path)
cerebro.adddata(data0, name='Target')

# 数据1：信号源
data1 = bt.feeds.BacktraderCSVData(dataname=data_path)
cerebro.adddata(data1, name='Signal')

# 策略中使用
class MultiDataStrategy(bt.Strategy):
    def __init__(self):
        # 在信号源上计算指标
        self.sma = bt.ind.SMA(self.data1, period=15)
        self.signal = bt.ind.CrossOver(self.data1.close, self.sma)

    def next(self):
        # 在交易目标上执行
        if self.signal > 0 and not self.position:
            self.buy(data=self.data0)  # 明确指定在data0上交易
        elif self.signal < 0 and self.position:
            self.sell(data=self.data0)
```

### 配对交易示例

```python
class PairTradingStrategy(bt.Strategy):
    """配对交易策略"""

    params = dict(
        period=15,
        stake=10,
        threshold=2.0  # 标准差阈值
    )

    def __init__(self):
        # 计算两个品种的价差
        self.diff = self.data0.close - self.data1.close
        self.sma = bt.ind.SMA(self.diff, period=self.p.period)
        self.std = bt.ind.StdDev(self.diff, period=self.p.period)

        # Z-score指标
        self.zscore = (self.diff - self.sma) / self.std

    def next(self):
        # 价差异常时进行配对交易
        if self.zscore > self.p.threshold:
            # 价差过高：做空A，做多B
            if not self.getposition(self.data0):
                self.sell(data=self.data0, size=self.p.stake)
            if not self.getposition(self.data1):
                self.buy(data=self.data1, size=self.p.stake)

        elif self.zscore < -self.p.threshold:
            # 价差过低：做多A，做空B
            if not self.getposition(self.data0):
                self.buy(data=self.data0, size=self.p.stake)
            if not self.getposition(self.data1):
                self.sell(data=self.data1, size=self.p.stake)

        # 价差回归：平仓
        elif abs(self.zscore) < 0.5:
            if self.getposition(self.data0):
                self.close(data=self.data0)
            if self.getposition(self.data1):
                self.close(data=self.data1)
```

### 期现套利示例

```python
class FutureSpotArbStrategy(bt.Strategy):
    """期现套利策略"""

    params = dict(
        threshold=0.02,  # 套利阈值2%
        stake=10
    )

    def __init__(self):
        # 计算基差（期货价格 - 现货价格）
        self.basis = self.data0.close - self.data1.close
        self.basis_pct = self.basis / self.data1.close

    def next(self):
        # 正向套利：基差过大，卖期货买现货
        if self.basis_pct > self.p.threshold:
            if not self.getposition(self.data0):  # 期货
                self.sell(data=self.data0, size=self.p.stake)
            if not self.getposition(self.data1):  # 现货
                self.buy(data=self.data1, size=self.p.stake)

        # 反向套利：基差过小（负基差），买期货卖现货
        elif self.basis_pct < -self.p.threshold:
            if not self.getposition(self.data0):  # 期货
                self.buy(data=self.data0, size=self.p.stake)
            if not self.getposition(self.data1):  # 现货
                self.sell(data=self.data1, size=self.p.stake)

        # 基差回归：平仓
        elif abs(self.basis_pct) < 0.005:
            if self.getposition(self.data0):
                self.close(data=self.data0)
            if self.getposition(self.data1):
                self.close(data=self.data1)
```

### 不同时间框架

```python
# 添加不同时间框架的数据
data_daily = bt.feeds.BacktraderCSVData(dataname='daily.csv')
cerebro.adddata(data_daily, name='daily')

data_weekly = bt.feeds.BacktraderCSVData(dataname='weekly.csv')
cerebro.adddata(data_weekly, name='weekly')

class MultiTimeFrameStrategy(bt.Strategy):
    def __init__(self):
        # 在周线上计算趋势
        self.weekly_sma = bt.ind.SMA(self.data1, period=15)
        self.weekly_signal = bt.ind.CrossOver(self.data1.close, self.weekly_sma)

    def next(self):
        # 周线趋势向上时，在日线上寻找买点
        if self.data1.close[0] > self.weekly_sma[0]:
            # 日线买入逻辑
            if not self.position:
                self.buy(data=self.data0)
```

## 数据源访问方式

| 访问方式 | 说明 |
|---------|------|
| self.data0 | 第一个数据源 |
| self.data1 | 第二个数据源 |
| self.datas[0] | 通过索引访问第一个 |
| self.getbyname('name') | 通过名称访问 |

## 佣金设置

为不同数据源设置不同佣金：

```python
# 为data0设置佣金
cerebro.broker.setcommission(commission=0.001, name='Data0')

# 为data1设置佣金（如果data1也交易）
cerebro.broker.setcommission(commission=0.0005, name='Data1')
```

## 注意事项

1. **数据对齐**：确保所有数据源的时间戳对齐
2. **数据长度**：不同数据源应有相同的时间范围
3. **数据频率**：建议使用相同频率的数据
4. **订单管理**：明确指定在哪个数据源上交易

## 参考

- 原始来源：backtrader-master2/samples/multidata-strategy/multidata-strategy.py
