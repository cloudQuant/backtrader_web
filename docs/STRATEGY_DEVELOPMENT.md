# 策略开发指南

本指南介绍如何为 Backtrader Web 开发自定义交易策略。

## 策略基础

### Backtrader 策略模板

```python
from backtrader import bt

class MyStrategy(bt.Strategy):
    """
    自定义策略模板

    参数:
        param1: 参数1说明
        param2: 参数2说明
    """
    params = (
        ('param1', 10),
        ('param2', 20),
    )

    def __init__(self):
        """初始化策略"""
        super().__init__()
        self.data_close = self.datas[0].close

    def next(self):
        """每根Bar调用一次"""
        if len(self.data) < self.p.param2:
            return

        # 获取当前价格
        current_price = self.data_close[0]

        # 策略逻辑
        if self.data_close[0] > self.data_close[-1]:
            self.buy(size=100)
        else:
            self.sell(size=100)
```

## 策略开发步骤

### 1. 定义参数

在策略中定义可调参数：

```python
params = (
    ('fast_period', 5),      # 快线周期
    ('slow_period', 20),     # 慢线周期
    ('stop_loss_pct', 0.05), # 止损百分比
)
```

### 2. 添加指标

```python
def __init__(self):
    super().__init__()

    # 添加指标
    self.ma_fast = bt.indicators.SMA(self.data.close, period=self.p.fast_period)
    self.ma_slow = bt.indicators.SMA(self.data.close, period=self.p.slow_period)

    # 交叉信号
    self.crossover = bt.indicators.CrossOver(self.ma_fast, self.ma_slow)
```

### 3. 交易逻辑

```python
def next(self):
    # 如果没有持仓
    if not self.position:
        # 金叉买入
        if self.crossover[0] > 0:
            self.buy(size=100)
    else:
        # 死叉卖出
        if self.crossover[0] < 0:
            self.sell(size=self.position.size)
```

## 策略示例

### 双均线策略

```python
class DualMovingAverage(bt.Strategy):
    """双均线交叉策略"""

    params = (
        ('fast_period', 5),
        ('slow_period', 20),
    )

    def __init__(self):
        super().__init__()
        self.ma_fast = bt.indicators.SMA(self.data.close, period=self.p.fast_period)
        self.ma_slow = bt.indicators.SMA(self.data.close, period=self.p.slow_period)
        self.crossover = bt.indicators.CrossOver(self.ma_fast, self.ma_slow)

    def next(self):
        if not self.position:
            if self.crossover[0] > 0:  # 金叉
                self.buy(size=100)
        else:
            if self.crossover[0] < 0:  # 死叉
                self.sell(size=self.position.size)
```

### RSI 策略

```python
class RSIStrategy(bt.Strategy):
    """RSI 超买超卖策略"""

    params = (
        ('rsi_period', 14),
        ('oversold', 30),
        ('overbought', 70),
    )

    def __init__(self):
        super().__init__()
        self.rsi = bt.indicators.RSI(self.data.close, period=self.p.rsi_period)

    def next(self):
        if not self.position:
            if self.rsi[0] < self.p.oversold:
                self.buy(size=100)
        else:
            if self.rsi[0] > self.p.overbought:
                self.sell(size=self.position.size)
```

### 布林带策略

```python
class BollingerBands(bt.Strategy):
    """布林带突破策略"""

    params = (
        ('period', 20),
        ('stddev', 2),
    )

    def __init__(self):
        super().__init__()
        self.boll = bt.indicators.BollingerBands(
            self.data.close,
            period=self.p.period,
            devfactor=self.p.stddev
        )

    def next(self):
        if not self.position:
            # 价格跌破下轨买入
            if self.data.close[0] < self.boll.lines.bot[0]:
                self.buy(size=100)
        else:
            # 价格突破上轨卖出
            if self.data.close[0] > self.boll.lines.top[0]:
                self.sell(size=self.position.size)
```

## 策略上传

### 1. 通过 API 上传

```bash
curl -X POST "http://localhost:8000/api/v1/strategy/" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "双均线策略",
    "description": "基于快慢均线交叉",
    "code": "class DualMA(bt.Strategy):\n    ...",
    "params": {
      "fast_period": {"type": "int", "default": 5, "min": 2, "max": 50},
      "slow_period": {"type": "int", "default": 20, "min": 10, "max": 100}
    },
    "category": "trend"
  }'
```

### 2. 通过 Web 界面上传

1. 登录系统
2. 进入"策略管理"
3. 点击"新建策略"
4. 填写策略信息
5. 粘贴策略代码
6. 保存策略

## 策略调试

### 使用日志

```python
class MyStrategy(bt.Strategy):
    def next(self):
        self.log(f'Close: {self.data.close[0]:.2f}')
        # ... 交易逻辑
```

### 查看输出

回测完成后，日志会显示在任务详情中。

## 策略最佳实践

### 1. 参数验证

```python
def __init__(self):
    super().__init__()
    if self.p.fast_period >= self.p.slow_period:
        raise ValueError('fast_period must be less than slow_period')
```

### 2. 数据检查

```python
def next(self):
    # 确保有足够的数据
    if len(self.data) < self.p.slow_period:
        return
```

### 3. 风险控制

```python
def next(self):
    # 检查持仓
    if self.position:
        # 止损
        if self.data.close[0] < self.position.price * (1 - self.p.stop_loss_pct):
            self.sell(size=self.position.size)
```

## 策略版本控制

系统支持策略版本控制：

1. 每次修改策略会创建新版本
2. 可以对比不同版本
3. 可以回滚到历史版本
4. 支持创建分支实验

## 内置指标

Backtrader 支持的内置指标：

- SMA: 简单移动平均
- EMA: 指数移动平均
- RSI: 相对强弱指标
- MACD: 平滑异同移动平均
- BollingerBands: 布林带
- ATR: 平均真实波幅
- Stochastic: 随机指标

更多指标参考: https://www.backtrader.com/docu/

## 常见问题

### Q: 如何获取历史价格？

```python
def next(self):
    # 当前价格
    current = self.data.close[0]
    # 前一日价格
    prev = self.data.close[-1]
    # N日前价格
    n_days_ago = self.data.close[-n]
```

### Q: 如何获取持仓信息？

```python
def next(self):
    position = self.position
    if position:
        size = position.size      # 持仓数量
        price = position.price    # 开仓价格
```

### Q: 如何获取账户信息？

```python
def next(self):
    total_value = self.broker.getvalue()
    cash = self.broker.getcash()
```

### Q: 如何设置止损止盈？

```python
# 在 __init__ 中设置
self.stop_loss = self.p.stop_loss_pct
self.take_profit = self.p.take_profit_pct

# 在 next 中检查
if self.position:
            entry_price = self.position.price
            unrealized_pnl_pct = (self.data.close[0] - entry_price) / entry_price

            if unrealized_pnl_pct < -self.stop_loss:
                self.sell(size=self.position.size)
            elif unrealized_pnl_pct > self.take_profit:
                self.sell(size=self.position.size)
```
