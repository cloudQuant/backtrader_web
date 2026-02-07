# 日出波动率扩展策略 (Sunrise Volatility Expansion Strategy)

## 策略简介

日出波动率扩展策略是一个完整的四阶段状态机入场系统，专门设计用于捕捉市场波动率扩张后的趋势突破机会。该策略通过EMA交叉信号识别趋势，等待回调确认，然后设置价格通道监控突破。

## 策略原理

### 四阶段入场系统

1. **阶段一：信号扫描 (SCANNING)**
   - 扫描EMA交叉信号
   - 应用多个过滤器确认信号有效性
   - 过滤器包括：EMA排列、价格过滤、K线方向、EMA斜率角度、ATR波动率

2. **阶段二：回调确认 (ARMED)**
   - 等待指定数量的回调K线确认
   - 全局失效机制防止错误信号

3. **阶段三：突破窗口开启 (WINDOW_OPEN)**
   - 计算双边价格通道
   - 设置窗口到期时间

4. **阶段四：突破监控**
   - 监控价格向上突破通道上轨（做多）
   - 监控价格向下突破通道下轨（做空）

### 风险管理

- **止损**: 入场价下方的ATR倍数距离
- **止盈**: 入场价上方的ATR倍数距离

## 策略参数

| 参数名 | 默认值 | 说明 |
|--------|--------|------|
| `stake` | 10 | 每次交易的数量 |
| `ema_fast` | 14 | 快速EMA周期 |
| `ema_medium` | 14 | 中速EMA周期 |
| `ema_slow` | 24 | 慢速EMA周期 |
| `ema_confirm` | 1 | 确认EMA周期 |
| `atr_period` | 10 | ATR周期 |
| `atr_sl_mult` | 4.5 | 止损ATR倍数 |
| `atr_tp_mult` | 6.5 | 止盈ATR倍数 |
| `long_pullback_candles` | 3 | 回调K线数量 |
| `entry_window_periods` | 1 | 入口窗口周期 |

## 适用场景

1. **趋势市场**: 适合有明显趋势的市场环境
2. **外汇和黄金**: 特别适合XAUUSD等高流动性品种
3. **高波动品种**: 波动率扩张后更容易产生有效突破

## 风险提示

1. **震荡市场亏损**: 在横盘震荡市场中容易频繁止损
2. **参数复杂**: 策略参数较多，需要仔细优化
3. **滑点风险**: 突破时可能面临滑点问题

## 回测结果

基于XAUUSD 5分钟数据2024-2025年回测：

- **初始资金**: $100,000
- **最终资金**: $99,780.54
- **夏普比率**: -0.06
- **年化收益率**: -0.16%
- **最大回撤**: 2.17%

## 使用示例

```python
import backtrader as bt
from strategy_sunrise_ema_crossover import SunriseVolatilityExpansionStrategy

cerebro = bt.Cerebro()
cerebro.addstrategy(SunriseVolatilityExpansionStrategy,
                    stake=10,
                    ema_fast=14,
                    ema_slow=24,
                    atr_period=10)
```

## 参考文献

- Reference: https://github.com/backtrader-pullback-window-xauusd
