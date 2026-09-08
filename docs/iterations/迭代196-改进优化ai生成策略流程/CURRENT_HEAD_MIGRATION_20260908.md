# 迭代 196：当前审批权威 migration 验收记录（2026-09-08）

> 结论：当前唯一 Alembic head 为 `20260908_ai_research_approval_authority`。独立 migration suite 135/135 通过，SQLite、PostgreSQL、MySQL、MariaDB 四个离线 SQL lane 与 heads 读回通过；真实 PostgreSQL/MySQL/MariaDB online upgrade/反射、触发器/函数执行、跨进程竞争与 operational rollback 均未运行，因此当前 head 只能判本地 migration 合同 `PASS`，不能判生产迁移可发布。

## 1. 候选与线性链

- 实现工作树：`/Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust`；
- 分支：`codex/iteration-196-ai-research-trust`；
- 基础/当前提交：`a18bcf52682686c30d919fe02d6fd734ee4271b9`；
- migration：`src/backend/alembic/versions/20260908_ai_research_approval_authority.py`；
- `down_revision`：`20260908_ai_research_holdout_executions`；
- 唯一 head：`20260908_ai_research_approval_authority`；
- 工作树未提交，`G0 provenance/candidate seal=NO-GO`。

2026-09-05 与 2026-09-07 的在线/会话记录仍按其发生时 head 保留为历史证据，不能外推到本 head。

## 2. schema 与安全合同

当前 head 为审批权威增加并约束 run-scoped grant、grant audit、审批请求/决定的 authority binding、profile/evidence material binding 与用户主体种类。关键合同包括：

1. candidate/run/evidence/policy 等父对象外键存在且删除策略为 `RESTRICT`；
2. grant 与 audit 使用追加式历史，`ISSUED`/`REVOKED` 形状、时间窗和唯一配对可重验；
3. `users.principal_kind` 只允许 `HUMAN/SERVICE/UNKNOWN`，历史数据保守回填为 `UNKNOWN`；
4. PostgreSQL 使用函数/触发器保护不可变记录，迁移会核对 OID、函数体、引用数量与现有对象，不能静默 replace 错误对象；
5. MySQL 与 MariaDB 分别核对 information_schema 的索引类型、visibility/ignored 属性，不能把 MariaDB 当作 MySQL 的同一 lane；
6. 精确列合同区分 `VARCHAR` 与 `CHAR/NVARCHAR`、PostgreSQL `timestamptz` 时区与 precision、MySQL/MariaDB `DATETIME(fsp=None)` 与 `TIMESTAMP/DATETIME(6)`、SQLite `DATETIME/VARCHAR/TEXT`；
7. partial re-entry 要求全列类型、默认值、可空性、computed/identity 和约束完全一致；
8. quote-aware CHECK 比较、unique constraint/index backing pair、完整历史 preflight 与合法 historical decision/grant window 都 fail-closed；
9. downgrade 在存在审批权威历史或无法证明安全时拒绝，避免破坏性降级掩盖数据。

## 3. 已执行证据

| 检查 | 结果 | 可声明范围 |
| --- | --- | --- |
| Alembic heads | 唯一 `20260908_ai_research_approval_authority` | 本地源码图 |
| 独立 migration suite | 135/135 passed | SQLite 执行 + 多方言合同/mock |
| 离线 SQL | SQLite、PostgreSQL、MySQL、MariaDB 4/4 PASS | SQL 生成；不是 online DDL 执行 |
| head + 四方言组合检查 | PASS | 本地静态/合同层 |
| Ruff/scoped format/diff | PASS | 本轮 migration 文件与测试范围 |
| 最终 6 worker 功能回归 | migration 相邻合同包含于 6,131 passed、123 skipped、0 failure/error | 见 [REGRESSION_6_WORKERS_20260908.md](REGRESSION_6_WORKERS_20260908.md) |

## 4. 真实 online lane 状态

| 引擎/场景 | 状态 | 尚需证据 |
| --- | --- | --- |
| PostgreSQL | `NOT_RUN_CURRENT_HEAD` | 空库/历史库 upgrade，catalog 反射，timestamptz、函数/触发器执行，重复/篡改拒绝，downgrade/re-upgrade |
| MySQL | `NOT_RUN_CURRENT_HEAD` | 空库/历史库 upgrade，索引 type/visibility，DATETIME 精度，触发器执行与 downgrade/re-upgrade |
| MariaDB | `NOT_RUN_CURRENT_HEAD` | 独立于 MySQL 的 upgrade/反射，ignored/index 元数据，DATETIME 精度，触发器执行与 downgrade/re-upgrade |
| 三数据库竞争 | `NOT_RUN_CURRENT_HEAD` | 每引擎 20 个独立 process/connection 的 ready barrier、锁/commit 结果、唯一拒绝 fence 与零 current approval 读回 |
| operational rollback | `NOT_RUN_CURRENT_HEAD` | 真实备份/恢复、运行中任务、不可逆历史与应用版本协同演练 |

SQLite、离线 SQL、catalog mock 或六 worker 单元回归均不得补填上述 online 证据。

## 5. 依赖与静态限制

- 回归使用只读 Backtrader `1.3.0` 快照，摘要 `34a1e78d996dc423d24d0ada5cd2609251734551ece05b523f51aa3fd8b8bee1`，不满足声明的 `>=1.9.78.123`；依赖来源 `NO-GO`。
- 全仓 `ruff check` 通过，但 `ruff format --check app tests alembic scripts` 报 16 files would reformat；本轮 migration scoped format 通过，未改无关文件。全仓 format 仍是 P2/gate limitation。
- 当前工作树未提交，不能把唯一 head 与本地测试报告称为已封存 release candidate。

## 6. 最终判定

当前 head 在本地 schema/migration 合同层为 `PASS`；PostgreSQL/MySQL/MariaDB online 与 operational rollback 为 `NOT_RUN_CURRENT_HEAD`。因此 `IMPLEMENTATION_ACCEPTED=NO-GO`、`PROTOCOL_PRODUCTION_ENABLED=NO-GO`，迁移发布门尚未闭合。
