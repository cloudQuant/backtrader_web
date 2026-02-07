# TD序列策略 (TD Sequential Strategy)

## 策略简介

TD序列是Tom DeMark开发的技术指标，用于识别潜在的价格衰竭点和趋势反转机会。策略分为Setup(设置)和Countdown(倒计时)两个阶段。

## 策略原理

### Setup阶段
- **买入Setup**：连续9根K线的收盘价低于4根K线前的收盘价
- **卖出Setup**：连续9根K线的收盘价高于4根K线前的收盘价

### Countdown阶段
- Setup完成后进入Countdown阶段
- **买入信号**：满足13个Countdown条件且价格低于第8个条件的价格
- **卖出信号**：满足13个Countdown条件且价格高于第8个条件的价格

## 策略参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| candles_past_to_compare | 4 | 比较过去K线的数量 |
| cancel_1 | true | 价格突破Setup高低点时取消 |
| cancel_2 | true | Setup完成时取消反向Setup |
| recycle_12 | true | 是否允许Setup和Countdown循环 |
| aggressive_countdown | false | 是否使用最低价进行Countdown比较 |

## 适用场景

- 识别市场顶部和底部
- 中长期趋势反转
- 需要精确入场时机的交易

## 风险提示

- TD序列信号可能出现多次失效
- 需要结合其他指标确认
- 在强趋势中可能过早离场

## 参考资料

- https://github.com/mk99999/TD-seq
