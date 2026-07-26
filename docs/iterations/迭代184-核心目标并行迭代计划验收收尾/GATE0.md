# 迭代 184 Gate 0 决策记录

> **日期**：2026-07-18  
> **基线 commit**：`105adb6b`  
> **Alembic head**：`20260705_b_data_backtest_trust`  
> **结论**：Gate 0 已关闭；以下契约是 184 后续实现和验收的唯一依据。

## G0-1：指标契约

`MetricsService.normalize()` 是计算后的唯一 canonical schema 入口。所有 canonical
收益/回撤/胜率字段使用**百分数**（例如 `12.5` 表示 12.5%），金额字段使用账户货币，
数量字段使用整数。字段为：

- `total_return`、`annual_return`、`sharpe_ratio`、`max_drawdown`、`win_rate`；
- `total_trades`、`profitable_trades`、`losing_trades`、`break_even_trades`；
- `avg_holding_bars`、`avg_holding_period`、`max_consecutive_wins`、
  `max_consecutive_losses`、`profit_loss_ratio`；
- `initial_cash`、`final_value`、`metrics_source`。

空序列返回有类型的零值，不能以 `null`、`NaN` 或伪造权益点表达。旧
`PerformanceMetrics` 消费者由 adapter 转换：其中 `total_return`、`annualized_return`、
`max_drawdown` 和 `win_rate` 为小数比例，`trade_count` 对应 `total_trades`，
`profit_factor` 对应 `profit_loss_ratio`。adapter 不得重新计算指标。

## G0-2：模拟运行时身份与数据真源

AI 投研主闭环的模拟交易真源是：

```text
User -> Workspace(type=paper) -> StrategyUnit -> trading_instance_id
```

因此 184 新增的快照、复核、风控规则和告警均以 `(user_id, workspace_id, unit_id,
instance_id)` 归属和查询；`instance_id` 是运行时粒度的 canonical ID。旧
`paper_trading_accounts` 引擎仅通过 nullable `paper_account_id` 关联，不能取代
workspace/unit/instance，也不能作为新 API 的路径参数。

新详情 API 的路径为 `/api/v1/paper-runtimes/{instance_id}`；服务必须从 instance
反查 unit/workspace/user，跨用户一律按不存在处理。`workspace_id` 和 `unit_id` 是
响应中的冗余可校验字段，不能由客户端独立信任。

## G0-3：生产稳健性门控

生产环境运行投研或创建 paper unit 时：

1. `require_robustness_validation=true` 自动规范化为
   `robustness_validation=true`；
2. 任何未执行、失败、无结果或服务异常的稳健性校验均拒绝 promotion；
3. 请求体不能关闭该门。仅 `APP_ENV in {test, development}` 且服务器配置
   `ALLOW_ROBUSTNESS_BYPASS=true` 时，才允许显式 bypass，并写入审计事件；
4. 数据预检同样必须在服务端执行，前端 debounce 仅改善体验。

## G0-4：迁移拓扑

方向 A/C 各新增一个 expand-only Alembic revision，均基于基线 head
`20260705_b_data_backtest_trust`。合入前由 Integrator 生成唯一 merge revision（若
产生两个 head）。验收必须覆盖 fresh、当前 head 非空库和历史 `create_all` 库；禁止在
开发者默认数据库直接运行 upgrade/downgrade。

## G0-5：API 与事件契约

- `BacktestSummaryResponse` 固定采用 `metrics: CanonicalMetrics` 嵌套层级，响应不含
  equity curve、drawdown 和 trades。
- `PaperEquitySnapshotResponse` 使用 UTC ISO-8601 时间、`points`、`next_cursor` 与
  `sampled` 字段；无数据返回空 `points`。
- 风控告警复用 `Alert`，新增 `workspace_id`、`unit_id`、`instance_id`、`dedupe_key`；
  对外只返回脱敏 `details`。
- live handoff 决策枚举为 `approved`、`rejected`、`requested_changes`；后者保持
  live 锁定并恢复到可继续优化的状态。
- 事件最少包含 `run_id`、`workspace_id`、`stage`、`status`、`failure_reason`（失败时）
  和 UTC `created_at`。

## G0-6：快照容量与生命周期

快照使用 UTC，幂等键为 `(instance_id, source, observed_at)`。写入时机为：实例创建、
成交后、以及运行中每 60 秒估值一次。查询默认最多 1,000 个点，可按时间窗口和
`max_points` 降采样；原始点保留 90 天，之后保留每日收盘点 365 天。清理任务必须可重复
执行，且绝不删除最后一个快照。

按 100 个同时运行单元计算，60 秒一次约 144,000 点/日；90 天约 1,296 万原始点。
因此 `(instance_id, observed_at)` 复合唯一索引及 `(user_id, instance_id, observed_at)`
查询索引为必需项，不能依赖 JSON 日志全表扫描。

## G0-7：结构化存储与告警

新建 `PaperReviewReport`、`LiveHandoffReview`、`RiskRule` 和
`PaperEquitySnapshot`。结构化表是新增写入真源；历史 run-record JSON 只读兼容一个
迭代，回填以 source record ID 为幂等键。告警不新建表：扩展现有 `Alert` scope 和
dedupe key，`RiskControlService._alerts` 仅保留瞬态计算缓存，不得作为查询结果真源。

## 审查依据

- 当前 `MetricsService` 已提供 canonical 字段，但 `AnalyticsService` 仍直接调用
  extended helper，因此 B1 必须以 characterization test 锁定 adapter 行为。
- AI 投研运行记录存储 `paper_workspace_id`/`paper_unit_id`，而独立 paper-account
  服务使用 `paper_trading_accounts`；两者不具有可假设的一对一关系。
- 当前 Alembic 单 head 为 `20260705_b_data_backtest_trust`，且数据库初始化仍存在
  `create_all` 兼容路径，故迁移需以三种基线验证。
