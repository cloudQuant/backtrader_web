# 过拟合检测方法说明

> 适用范围：AI for Trader 迭代 166 的 Walk-forward、样本外验证与 Monte Carlo 检测。检测结果仅供研究参考，不构成投资建议。

## 1. 总体目标

过拟合检测回答的是：当前回测结果是否过度依赖某个样本区间、参数组合或交易序列巧合。

系统输出：

- 整体风险等级：`low` / `medium` / `high`
- 稳健性分数：`0-100`
- 每种方法的解释和证据指标
- 降级标记：样本不足或无法构造检测时返回 `degraded=true`

## 2. Walk-forward 分析

Walk-forward 会把完整回测区间滚动切分为：

```text
样本内训练窗口(IS) → 样本外验证窗口(OOS) → 向前滚动 step 天
```

默认参数：

| 参数 | 默认值 | 含义 |
|------|--------|------|
| `walk_forward_train_days` | 180 | 样本内窗口天数 |
| `walk_forward_test_days` | 60 | 样本外窗口天数 |
| `walk_forward_step_days` | 60 | 每次滚动步长 |
| `walk_forward_max_concurrency` | 4 | 最大并发切片回测数 |

关键证据：

- `window_count`：有效窗口数量
- `avg_is_sharpe`：样本内平均 Sharpe
- `avg_oos_sharpe`：样本外平均 Sharpe
- `sharpe_decay_pct`：Sharpe 衰减比例
- `return_decay_pct`：收益衰减比例
- `windows`：每个滚动窗口的 IS/OOS Sharpe 与年化收益，用于前端图表展示

解读方式：

- OOS 与 IS 接近：更稳健
- OOS 明显弱于 IS：可能存在参数过拟合
- 窗口数量过少：结果应降级解读

## 3. 样本外验证

样本外验证按比例把完整区间切成前后两段：

```text
前 70% 样本内(IS) / 后 30% 样本外(OOS)
```

默认参数：

| 参数 | 默认值 | 含义 |
|------|--------|------|
| `out_of_sample_ratio` | 0.3 | 后段样本外占比 |

关键证据：

- `is_sharpe` / `oos_sharpe`
- `is_annual_return` / `oos_annual_return`
- `sharpe_decay_pct`
- `return_decay_pct`
- `test_method`：当前为 `welch_t_test_normal_approx`
- `t_statistic` / `degrees_of_freedom`
- `p_value`：Welch t 统计量的正态近似双侧显著性指标

解读方式：

- OOS 表现接近 IS：结果相对稳健
- OOS Sharpe 和收益明显衰减：过拟合风险升高
- `p_value` 只能作为辅助线索，不能单独作为结论

## 4. Monte Carlo 检测

Monte Carlo 基于已发生交易收益做 bootstrap 抽样，构造随机交易序列分布，再比较实际复合收益在分布中的位置。

默认参数：

| 参数 | 默认值 | 含义 |
|------|--------|------|
| `monte_carlo_iterations` | 300 / API 可调 | bootstrap 次数 |
| `random_seed` | backtest id hash | 默认可复现随机种子 |

关键证据：

- `trade_return_count`：交易样本数
- `actual_compound_return_pct`：实际复合收益
- `bootstrap_mean_return_pct`：随机分布均值
- `bootstrap_std_return_pct`：随机分布标准差
- `bootstrap_percentile`：实际收益在随机分布中的分位
- `bootstrap_p75_return_pct` / `bootstrap_p95_return_pct`
- `bootstrap_distribution_pct`：抽样后的 bootstrap 收益分布，用于前端直方/分布图展示

解读方式：

- 实际收益高于 P95：相对稳健
- 实际收益位于 P75-P95：中等稳健
- 实际收益低于 P75：可能没有明显优于随机重采样

## 5. 常见误区

| 误区 | 正确理解 |
|------|----------|
| 低过拟合风险 = 可以实盘 | 错。仍需交易成本、容量、滑点和风控验证 |
| 高过拟合风险 = 策略一定亏损 | 错。说明当前证据不足或样本依赖强 |
| p-value 越小越好 | 不一定。要结合 OOS 方向和业务意义 |
| Monte Carlo 可替代 Walk-forward | 不可替代。两者检验角度不同 |
| 样本不足也能下结论 | 不应。系统会返回 degraded 标记 |

## 6. 推荐工作流

1. 完成回测
2. 先看策略评分总览
3. 启动三种过拟合检测
4. 等待 WebSocket 或轮询结果
5. 查看方法级证据卡
6. 对高风险方法补充人工复核或重跑更长样本
7. 重新获取策略评分，让过拟合维度使用真实检测结果

## 7. 已完成增强

- Walk-forward 支持并发限流和窗口级进度推送
- OOS 输出 Welch t 统计量、自由度和近似 p-value
- Monte Carlo 暴露压缩后的 bootstrap 收益分布数组
- 前端提供方法级 tab、Walk-forward 窗口、OOS 对比、Monte Carlo 分布图

## 8. 后续增强方向

- OOS 可在确定 `scipy` 为直接依赖后切换为精确 t 分布 p-value
- Walk-forward 可进一步暴露取消、重试和窗口失败明细
- 检测结果与策略解释器联动，自动提示风险原因
