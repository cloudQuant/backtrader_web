# 国债期货MACD策略 (Treasury Futures MACD Strategy)

## 策略简介

国债期货MACD策略是一个基于MACD指标的趋势跟踪策略，适用于国债期货等金融期货品种。该策略支持自动换月功能，能够在合约到期时自动转移到新的主力合约。

## 策略原理

### 核心思想
1. **MACD指标**: 使用快慢EMA交叉产生交易信号
2. **趋势确认**: 结合MACD柱状图确认趋势方向
3. **自动换月**: 根据持仓量自动切换到主力合约

### 入场条件
- **做多**: 短期EMA上穿长期EMA + MACD>0
- **做空**: 短期EMA下穿长期EMA + MACD<0

### 出场条件
- 多头：价格跌破短期EMA
- 空头：价格突破短期EMA

### 换月逻辑
- 当主力合约变化时自动换月
- 根据持仓量确定主力合约

## 策略参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| period_me1 | 10 | 快线EMA周期 |
| period_me2 | 20 | 慢线EMA周期 |
| period_dif | 9 | DEA线EMA周期 |

## 适用场景

- 国债期货等金融期货
- 趋势明显的市场环境
- 需要自动换月的期货品种

## 风险提示

1. MACD策略在震荡市场容易产生假信号
2. 换月时可能产生额外的滑点和成本
3. 期货交易具有杠杆风险
4. 需要确保主力合约切换逻辑正确

## 回测结果

基于国债期货数据的回测结果（数据文件: CFFEX_Futures_Contract_Data.csv）:

- bar_num: 1,990
- buy_count: 38
- sell_count: 38
- total_trades: 90
- sharpe_ratio: N/A (极端值)
- annual_return: ~0%
- max_drawdown: ~0%
- final_value: 999,982.29

## 数据要求

- 中金所国债期货合约数据: CFFEX_Futures_Contract_Data.csv

## 作者信息

- 作者: yunjinqi
- 策略类型: 国债期货趋势策略
