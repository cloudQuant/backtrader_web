# 2026-08-03 本机 MySQL 运行时冒烟证据

## 范围

本证据只覆盖本机共享开发库 `backtrader_web` 的迁移、应用生命周期、认证和
fail-closed 数据源门禁。它不代表任何外部数据源、六类资产真实研报、T1 观察或 T2
方向信号已经通过。

所有连接串和登录凭据均仅在本机进程内使用，未写入本文件或命令输出。

## 前置状态

- MySQL：本机 Homebrew MySQL `9.4.0`，监听 `127.0.0.1:3306`；
- 应用配置的数据库：`backtrader_web`；
- 起始 Alembic revision：`20260810_asset_research_option_context_binding`；
- 起始资产运行事实：`asset_analysis_tasks`、来源注册、主数据、schedule、prediction、
  outcome、registry 等均为 0 行；已有 `asset_specs=8` 未被本次变更修改。

## 已执行的验证

1. 执行 `alembic upgrade head`，日志确认
   `20260810_asset_research_option_context_binding ->
   20260811_asset_research_task_leases`；
2. postflight 只读核验结果：
   - revision 为 `20260811_asset_research_task_leases`；
   - `asset_analysis_tasks` 仍为 0 行；
   - `lease_token`、`lease_expires_at`、`lease_heartbeat_at`、`attempt_count` 均存在；
   - `ix_asset_task_runner_claim` 存在；
3. 对该已迁移共享开发 schema 运行事务回滚式 MySQL 合同：
   `tests/asset_research/test_mysql_contract.py::test_mysql_asset_research_constraints_are_enforced_transactionally`
   结果为 `1 passed`；该测试的夹具写入全部回滚；
4. 在该库上启动 FastAPI：应用完成生命周期启动，`AssetResearchTaskRunner.run_due`
   已注册并完成空队列轮询；`GET /api/v1/health` 返回 HTTP 200、`database=healthy`；
5. 使用本机管理员配置登录后，`GET /api/v1/asset-research/capabilities` 返回：
   - `asset_type_count=6`；
   - `research_enabled_count=0`；
   - `availability_reasons=[SOURCE_CAPABILITY_UNAVAILABLE]`；
   - `execution_disabled=true`；
6. 尝试创建一个 syntactically valid 的期货研究任务返回 HTTP 422，服务端原因码为
   `SOURCE_CAPABILITY_UNAVAILABLE`；请求前后 `asset_analysis_tasks` 均为 0 行；
7. 向临时 Uvicorn 进程发送中断后，日志显示应用、两个 APScheduler 实例和 audit sink
   均优雅关闭；端口 `8000` 随后不可达。

## 当前结论

迁移与运行时门禁在实际 MySQL 9.4.0 开发环境中已通过。由于来源注册、获批主数据、
市场日历和真实覆盖仍为空，系统正确拒绝创建研究任务。该结果保持迭代 191 的
T1/T2 状态为 **NO-GO**，并证明不会以未授权或示例行情生成资产建议。

## 仍需外部输入

- 每类资产的获批数据源、许可、能力清单和版本化主数据；
- 真实市场日历与到期结果的可评分输入；
- T2 所需 point-in-time walk-forward、至少 200 条成熟行动信号、校准/基线、前瞻影子结果和审批；
- 生产目标的备份、维护窗口、恢复演练和独立发布授权。
