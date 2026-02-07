# 开盘价执行策略 (Cheat On Open Strategy)

## 策略简介

Cheat On Open策略演示了Backtrader的`cheat_on_open`功能，该功能允许策略在开盘时执行订单，而不是默认的收盘时执行。这更真实地模拟了现实交易中"收盘后分析，次日开盘执行"的场景。

## 策略原理

### 什么是Cheat On Open

默认情况下，Backtrader在当前K线收盘时调用`next()`方法，订单在收盘价执行。启用`cheat_on_open`后：

- **next()在开盘前调用**：可以使用前一根K线的数据做决策
- **订单在开盘价执行**：更接近真实的市场开盘交易

### 技术指标

- **快速SMA**（默认10周期）：快速响应价格变化
- **慢速SMA**（默认30周期）：平滑显示趋势
- **交叉信号**：双均线金叉/死叉

### 交易逻辑

1. **入场信号**：快速SMA上穿慢速SMA（金叉）时买入
2. **出场信号**：快速SMA下穿慢速SMA（死叉）时卖出
3. **执行方式**：所有订单在开盘价执行

## 策略参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `periods` | [10, 30] | SMA周期列表 [快速, 慢速] |

## 适用场景

1. **日线交易**：收盘分析决策，次日开盘执行
2. **跳空策略**：利用开盘跳空进行交易
3. **更真实模拟**：避免使用未来数据（收盘价在开盘时还不知道）

## 风险提示

1. **开盘跳空**：实际开盘价可能与前一收盘价相差较大
2. **流动性风险**：开盘时流动性可能较差
3. **滑点风险**：开盘时滑点可能更大
4. **隔夜风险**：持仓过夜面临突发消息风险

## 使用示例

```python
import backtrader as bt
from strategy_cheat_on_open import CheatOnOpenStrategy, load_config

# 加载配置
config = load_config()

# 创建Cerebro引擎（启用cheat_on_open）
cerebro = bt.Cerebro(stdstats=True, cheat_on_open=True)
cerebro.broker.setcash(100000)

# 添加策略
cerebro.addstrategy(CheatOnOpenStrategy, **config['params'])

# 运行回测
results = cerebro.run()
```

## 参考来源

- Backtrader官方示例：backtrader-master2/samples/cheat-on-open/cheat-on-open.py
