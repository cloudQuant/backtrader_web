# 配对交易策略 (Pairs Trading Strategy)

## 策略简介

配对交易是一种统计套利策略，通过利用两个相关资产之间的价差回归特性进行交易。本策略使用OLS变换计算Z-Score，当价差超出统计区间时进行交易。

## 策略原理

1. **选择配对**：选择两个高度相关的资产(如Visa和Mastercard)
2. **计算Z-Score**：使用OLS变换计算价差的Z-Score
3. **做空价差**：当Z-Score > 2.5时，卖出资产A、买入资产B
4. **做多价差**：当Z-Score < -2.5时，买入资产A、卖出资产B
5. **平仓条件**：当Z-Score回到均值区间(-0.5到0.5)时平仓

## 策略参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| period | 20 | OLS变换周期 |
| upper | 2.5 | Z-Score上限(做空价差) |
| lower | -2.5 | Z-Score下限(做多价差) |
| up_medium | 0.5 | Z-Sscore中等上限(平仓) |
| low_medium | -0.5 | Z-Score中等下限(平仓) |
| stop_loss | 3.0 | 止损阈值 |

## 适用场景

- 两个高度相关的股票或ETF
- 统计套利交易
- 市场中性策略

## 风险提示

- 配对关系可能失效
- 需要密切监控相关性变化
- 双边交易增加手续费成本

## 参考资料

- https://github.com/arikaufman/algorithmicTrading
