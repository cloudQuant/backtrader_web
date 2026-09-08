# 迭代 196 外部派发与模型配额闭环补充

日期：2026-09-05。范围：候选工作树 `codex/iteration-196-ai-research-trust`，未提交；仅本地受控 Provider/runner 与测试数据库，不是真实外部模型或容器执行验收。

## 1. 复现与修复

| 问题 | 修复与证据 |
| --- | --- |
| 同一 reservation 重复调用 gateway/runner 会再次执行外部副作用 | 新 `QuotaService.claim_external_dispatch` 仅允许一次 `RESERVED → IN_FLIGHT` 条件 UPDATE；只有 rowcount=1 的调用者能派发。operation ID 包含 reservation ID，避免不同 bucket 的 fencing token 相同而重名。LLM/Sandbox 各 2 项初始测试均先出现预期失败，再修复通过。 |
| 初次读取通过之后取消、换租约或撤销 stage 仍可派发 | 在派发 UPDATE 中同时检查 bucket、task、attempt、run、stage、lease、expiry、resource_type 和 unit；初读结果不作为最终许可。新增取消和 10 类撤销负例，以及两独立 gateway、SQLite NullPool 独立连接的竞争测试。 |
| Python 提前采样的 now 在连接等待后可能过时 | 派发谓词使用数据库 UTC 时钟；SQLite 用带毫秒精度的 `strftime`，PostgreSQL 用 `clock_timestamp()`，MySQL 用 `UTC_TIMESTAMP(6)`。旧应用时钟负例先复现，再通过。未支持的方言不会静默降级为无时钟检查。 |
| 模型成功返回后永远 IN_FLIGHT，最后被误判为未知操作 | Gateway 在返回成功前核验完整非负整数 token 用量并结算。缺失、不完整、负数、布尔值、浮点数或相互矛盾的计数不当作 0；记录 `LLM_PROVIDER_USAGE_UNVERIFIED`，保留 reservation 等待核对。超过预留量记录 `LLM_QUOTA_SETTLEMENT_FAILED`，不截断实际用量或释放预算。 |
| 两个不同 reservation 同时结算丢失一次 bucket 记账 | 真实独立连接先复现 `(reserved, settled, active)=(32,17,1)`，应为 `(0,34,0)`。现以同一事务内 reservation CAS 与 bucket 算术 UPDATE 结算；不再将旧 ORM 快照覆盖回汇总。 |

`mark_in_flight` 保留既有幂等记录语义，但文档明确它不是派发授权；当前 LLM/Sandbox 两个外部派发入口都已切换到单次 claim。

已成功 claim 后再取消，不能撤销已经开始的外部工作；迟到结果仍受 task/stage checkpoint 的租约与取消检查约束。本补丁没有声称跨数据库原子提交等于“外部调用 exactly once”：claim 后进程崩溃仍是需要核对的未知结果，不能自动重派。`RECONCILING` 也不能经普通 settle 绕过专用 readback 流程。

数据库时钟的选择依据官方文档：PostgreSQL 的 `CURRENT_TIMESTAMP` 取事务起点，`clock_timestamp()` 才反映实际当前时间；SQLite 的 `now` 在一次 step 内一致，当前小数秒精度为毫秒。因此该判断是数据库语义下的派发准入，不是操作系统实时期限或调用返回时仍持有租约的保证。[PostgreSQL 17](https://www.postgresql.org/docs/17/functions-datetime.html#FUNCTIONS-DATETIME-CURRENT)、[SQLite](https://www.sqlite.org/lang_datefunc.html)。MySQL 使用带小数秒精度的 UTC 函数，但仍需要实际 MySQL 验收，不能以 SQL 代码存在代替运行证据。[MySQL 8.4](https://dev.mysql.com/doc/refman/8.4/en/date-and-time-functions.html#function_utc-timestamp)。

## 2. 验证

```sh
cd /Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust/src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  -m pytest -p no:rerunfailures -q -n 6 --dist load \
  --junitxml=/private/tmp/iter196-current-head.WAaH1k/dispatch-settlement-final.xml \
  tests/test_ai_research_llm_gateway.py tests/test_ai_research_quota.py \
  tests/test_ai_research_sandbox_runner.py tests/test_ai_research_workflow_worker.py \
  tests/test_ai_research_stage_attempt.py tests/test_ai_research_generation_materialization.py
```

结果：**60 passed、7 warnings，17.32 秒，退出码 0**。5 个改动源码/测试文件的 Ruff check 通过。JUnit SHA-256：`a68ec59e0e899bfddef90040cc54d6efa4462aafcac091cff97b7737394fc0b5`。

中间新增 inactive bucket 用例最初误用了不属于数据库枚举的 `FROZEN`，触发 CHECK 约束；已改为真实合法的 `BLOCKED_UNKNOWN`。该夹具失败独立记录，不当作生产缺陷或绿色证据。

## 3. 仍需完成

- **quota/task 与阶段提交的数据库时钟本地修复已完成。** reservation、task claim/heartbeat/recover、stage、generation materialization 及 artifact 写入边界已统一到数据库 UTC；快慢 10 分钟及操作中途过期用例见第 4、5 节。该局部证据仍不外推为实际 PostgreSQL/MySQL 多进程跨主机并发证明。
- **ProviderResponse P1 已完成本地修复。** 16 项新用例先复现失败，随后完整响应验证、稳定错误账本、元数据限额/脱敏和合法 token 计数保留已落地；gateway + materialization 52 项通过。详见 [响应验证记录](PROVIDER_RESPONSE_VALIDATION_20260905.md)。该增量发生在 5,034 项完整回归之后，旧全量结果不能作为新补丁证明；真实 adapter 与数据库异常对账边界仍未闭合。
- HTTP Provider adapter、配置 pin/响应型号/request ID 与 server-owned GENERATE factory 已实现；本地 transport seam 的公开 worker 链路见 [生成部署记录](GENERATION_PROVIDER_DEPLOYMENT_20260905.md)。总 token/费用预算上界与真实供应商验收仍未完成，不能将测试 HTTP 响应称为已调用真实模型。
- Sandbox 目前只有派发单次性补丁，其成功收据还缺少可用于结算的权威实际资源用量；不得伪造秒数释放预算。
- 对账工作流需要进一步验证多个未知 reservation 共用 bucket、并发释放/核对以及 readback 审计链；本轮不把现有服务契约称为完整生产配额闭环。
- 本文 60 项是聚焦回归；此前 4,993 项完整后端跑次早于本补丁。后续冻结源码已独立完成 5,034 passed、129 skipped 的完整后端回归（197 项 v2 全部通过），以 [REGRESSION_6_WORKERS_20260905.md](REGRESSION_6_WORKERS_20260905.md) 的新跑次为准；它仍不覆盖上述已知实现缺口或真实外部环境。

对应需求：FR-PIPE-010、FR-TASK-004 及配额/取消/外部副作用验收；完整目标和 NO-GO 条件仍遵守 [ACCEPTANCE.md](ACCEPTANCE.md)。

## 4. 后续 quota/task 数据库时钟修复

新增 `app/services/research/database_clock.py` 作为唯一受支持方言的 UTC 时钟表达式及异步读取 helper；保留原 SQLite/PostgreSQL/MySQL 编译语义。quota reservation 在取得 bucket 后从该数据库会话采样时间，避免应用主机快/慢导致期限延长/提前。task claim、续租及恢复默认也从数据库会话读取；现有显式 `now=` 只保留服务层确定性测试入口，生产默认调用不传该值，不回退应用 `_now()`。

另修复 heartbeat 对“已过期但尚未 recover 的 RUNNING task”续租复活：生产 UPDATE 除 task ID/status/lease token 外，还原子使用 `DatabaseUtcNow()` 判定 `lease_expires_at > now`。新竞态用例在早期采样后、UPDATE 前把期限变为过期，先得到 1 failed，再修复通过；不是只在应用侧预读一次。

独立 worker 最终自有聚焦 `test_ai_research_lease_clock.py`、`test_ai_research_quota.py`、`test_ai_research_task_runner.py`：**22 passed、7 warnings，14.25 秒**，固定 6 worker；Ruff check/format 通过。一次包含 gateway 的联合收集撞上 root 同时新增参数化用例，xdist 报 collection mismatch；该跑次无效，既不是产品失败也不是绿色证据。随后只跑冻结的自有文件；统一源码回归另登记。

Root 另用已有一次性 PostgreSQL 17.7 实际验证 helper：Unix socket、read-only transaction、`SET LOCAL TIME ZONE 'Asia/Shanghai'`，helper 仍返回 UTC datetime，落在本机 before/after 采样范围内；连续表达式读取不倒退，退出码 0。脚本 `/private/tmp/iter196-current-head.WAaH1k/check_database_clock.py`；临时实例已停止且 `pg_ctl status` 确认为 no server running。这仅证明方言与时区 round-trip，不是 PostgreSQL 任务租约并发全链路，也不是 MySQL 执行证据。

## 5. 阶段、物化与工件提交的数据库时钟

`generation_materialization.py`、`stage_attempt.py`、`artifact_broker.py` 的新写入已补当前数据库 lease 复核，包含等待/对象重验之后的第二次检查。失效任务不能凭较慢应用时钟写入候选或工件；操作中途过期则回滚，不留下成功 checkpoint。完全相同的终态 replay 只读验证，不复活 lease、不推进新游标；显式 `now=` 可用于审计时间，不作为生产租约授权绕过入口。

新增时钟定向集最初 **6 failed / 2 passed**，修复后 **8 passed**。相邻两条 workflow recovery 测试的历史固定 claim 时间与生产数据库时间混用，已改由数据库 UTC 创建当前测试 lease，没有放宽生产条件。独立阶段/materialization/artifact/workflow/executor 聚焦最终 **53 passed、1 warning，28.19 秒**。

Root 随后统一 6 worker 运行 `tests/test_ai_research_*.py tests/test_config.py`：**303 passed，44.60 秒；其中 v2 299 项，0 failure/error/skip**。该组和全量结果以 [回归记录](REGRESSION_6_WORKERS_20260905.md) 为准；前述 60/22/53 项属于不同范围，不相加。
