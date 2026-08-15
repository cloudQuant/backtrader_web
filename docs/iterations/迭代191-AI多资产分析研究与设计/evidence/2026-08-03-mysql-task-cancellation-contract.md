# 2026-08-03 MySQL 9.4 交互任务取消竞争合同

## 范围

本证据验证交互多资产任务在用户取消与 worker 终态写入竞争时的持久化语义。它使用本机
Homebrew MySQL `9.4.0` 二进制启动独立、临时、无密码的实例；不使用共享开发库、生产库、
外部来源或账户数据。

临时实例的 data directory 和 `codex_iter191_cancel_contract` schema 在测试结束后均已删除。
连接串、应用账户凭据和任何用户数据均未写入本文件。

## 已执行的步骤

1. 对临时 MySQL 9.4.0 实例的空 schema 执行 `alembic upgrade head`；
2. 确认 revision 为 `20260811_asset_research_task_leases (head)`；
3. 运行以下 MySQL 方言合同：

   ```text
   test_mysql_interactive_task_runner_claims_and_releases_a_durable_lease
   test_mysql_interactive_task_runner_does_not_revive_a_cancelled_task
   test_mysql_asset_research_constraints_are_enforced_transactionally
   ```

4. 结果为 `3 passed`。

## 验证结论

- worker 成功终态会清除同一 lease 的 token、过期时间和心跳；
- 用户取消已先提交时，晚到 worker 的 `SUCCEEDED` 写入必须同时匹配
  `status=RUNNING + lease_token`，因此条件更新为 0 行，任务保持 `CANCELLED`；
- 竞争失败的 worker transaction 会 rollback，避免留下 run、prediction、report 或租约的
  部分事实；
- 现有 MySQL 约束（run-to-prediction、期权上下文、manifest、outcome maturity）仍在同一
  schema 中通过真实方言合同。

本项只证明租约/取消的 P0 持久化一致性，不代表真实数据源、真实资产研究、T1 数据观察或
T2 方向信号已经通过。
