# 当前候选迁移头的实际数据库验收

日期：2026-09-05。候选工作树：`/Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust`。

> 历史证据提示：本文实际执行的是当时的 candidate-freeze receipt head。当前唯一 head 已推进为 `20260907_ai_research_holdout_claim`；它只有本地 SQLite/schema/FSM 合同证据，真实 PostgreSQL/MySQL 尚未重跑。最新状态见 [HOLDOUT_CLAIM_START_20260907.md](HOLDOUT_CLAIM_START_20260907.md)，不得把本文三数据库会话外推到新 head。

## 历史：candidate-freeze receipt head（2026-09-07）

当前唯一线性 head 为 `20260907_ai_research_candidate_freeze_receipt`，父版本为 `20260906_ai_research_workflow_version`。该迁移创建每个冻结候选唯一的追加式 identity receipt，将 forward observation epoch 绑定到 receipt/fingerprint，并把 holdout authorization 从复合唯一约束收紧为每个 experiment epoch 唯一。迁移 SHA-256 为 `674d215299e75b16f0e94668794cd9aeae7bc9dbcfac66615c852ab561aa8f99`。

本次会话 stdout 记录一次性 SQLite、PostgreSQL 17.7 和 MySQL 9.4 均实际完成当前 head 的升级与 schema check，并验证：

- receipt 表、索引、外键、检查约束和 holdout epoch 唯一约束存在；
- 有效 receipt 的 `UPDATE` 与 `DELETE` 被数据库原生触发器以 `CANDIDATE_FREEZE_RECEIPT_IMMUTABLE` 拒绝；
- receipt 非空时降级以 `CANDIDATE_FREEZE_RECEIPT_DOWNGRADE_BLOCKED` 拒绝，head、字段和数据保持；
- receipt 为空时可降回 `20260906_ai_research_workflow_version`，随后重新升级当前 head 并通过 schema check；
- 迁移图只有一个 head，无 branch point 或 merge point。

PostgreSQL 预期的更新/删除拒绝可在 `/private/tmp/iter196-freeze-receipt-pg.JwYPcZ/postgresql.log` 读回；其 SHA-256 为 `b21412dc5747840bc479c7257e16457c5ac89f2d06b8a764bd1745679d0d54b6`。最终重跑服务日志 `/private/tmp/iter196-freeze-receipt-pg.JwYPcZ/postgresql-retry.log` 的 SHA-256 为 `27ff6c43ceb073e144758ca1d70440264d8e810311cbc23b162e535fa3348066`。临时集群已 fast stop，当前 `pg_ctl status` 读回 `no server running`。

MySQL 使用仅 Unix socket、端口 0 的一次性 9.4.0 实例。初轮验证暴露降级时显式删除一个仍被外键选作支撑的索引会失败；修复仅改为让随后 `DROP TABLE` 负责删除该表索引，未关闭外键检查或放宽不可变约束。新启动实例完整重跑上述升级、拒绝、空表降级和重升流程通过。初始化日志 SHA-256 为 `13e0737d1319291ff660212fa8dfa4ff5d19a8b744aef28acf0452eca6727b89`，最终服务日志 SHA-256 为 `f2d547c7df9800f006404c6ddc62deb9c4f73e28ef52a8fa58c448e4d8a247c2`；实例已正常 shutdown，socket 不存在。

本节判定为 `SESSION_TRANSCRIPT_PASS / PERSISTENT_EVIDENCE_PARTIAL`：当前持久目录只保留 PostgreSQL/MySQL server lifecycle 日志，PostgreSQL 旧日志还能独立读回 UPDATE/DELETE 的预期触发器拒绝；最终 retry/MySQL 日志本身不含 upgrade/check/downgrade 的客户端断言，SQLite 也没有独立结构化输出。因此这些结果支持本次会话裁决，但尚未形成可脱离会话复核的完整迁移证据包。发布前应保存精确验证器、结构化断言输出及其哈希。

它们也不证明真实 MySQL task-runner/shared-schema 并发、在途任务迁移、生产备份恢复或 operational rollback。相应真实 MySQL 合同仍在当前六 worker 功能回归中按环境条件 skip，不能用本节填成 PASS。

## 历史：workflow_version head（2026-09-06）

当前唯一 head 为 `20260906_ai_research_workflow_version`，父版本 `20260906_ai_research_search_allocation`。新增非空/带数据库默认的 `ResearchRun.workflow_version`，旧行保持 `generation-v1`。若存在 discovery-v1 或未知图数据，默认降级会以 `RESEARCH_WORKFLOW_VERSION_DOWNGRADE_BLOCKED` 拒绝，避免 drop 后重升将新图错误地解释为旧图。

PostgreSQL 17.7 已在新临时集群实测含完整外键历史行的升级/check、纯旧图降级/重升/check、新图降级拒绝后 head/字段/历史保留及再次check，三次均无待生成操作。脚本、摘要、限制和临时集群已停止的 readback 见 [工作流迁移证据](DISCOVERY_WORKFLOW_20260906.md)。此处不以 PostgreSQL schema 结果替代 MySQL、运行中流量迁移或生产回滚验收。

## 历史：search_allocation head（2026-09-06）

当时唯一 head 为 `20260906_ai_research_search_allocation`，父版本 `20260905_ai_research_discovery_executions`。独立验证器在 `/private/tmp/iter196-search-allocation-verify.Ds27JZ` 的临时 SQLite 与 PostgreSQL 17.7 上插入完整外键祖先链及历史 journal，实际执行 parent → head/check → 写入分配字段 → parent → head/check。

- 新增 nullable `search_epoch_id`、`search_ordinal`、`search_budget_hash`、`trial_id`，分别为 String/Integer/String/String，**不是 JSON**。实际核对两项新唯一约束、两项 RESTRICT 外键及全 NULL/完整正序号分配 CHECK；四次 Alembic check 均无待生成变更。
- 首次升级保留历史 NULL。写入合法分配后降级，仅去掉新分配/关联字段，journal 的命令、结果与主体数据保留；重升仍为 NULL，不按当前预算伪造历史分配。
- 分配和 trial 关联元数据在降级中丢失，**不是无损回退**。恢复派发前必须从备份核对在途执行/搜索账；新 prepare 明确拒绝 NULL 旧证据的幂等重发路径。
- 首次临时验证器错误地把 SQLite inspector 的外键 constraint name 当作列名，修正验证器后使用新 SQLite 文件及独立 PG 数据库重新完整验证；没有修改候选迁移来迎合该错误断言。
- PostgreSQL 使用临时独立 cluster/role/database、Unix socket 和 `listen_addresses=''`，不接业务库；后续锁序并发检查及最终停止证明随 [发布验收记录](DISCOVERY_PUBLICATION_20260906.md) 保存。

验证器：`/private/tmp/iter196-search-allocation-verify.Ds27JZ/check_search_allocation_migrations.py`，SHA-256 `d4126c09f0b51b842aa2e66f90b795fddacc2513b721678b128839b860b1f55e`。旧 head 的空表演练保留如下，不冒充当前含历史行升级证据。本次仍不替代 MySQL 或运行中业务回滚验收。

## 历史：discovery_executions head（2026-09-06）

当前唯一 head 为 `20260905_ai_research_discovery_executions`，父版本 `20260905_ai_research_budget_context`。新建临时目录 `/private/tmp/iter196-discovery-execution-migration.tOBmLU`，SQLite 与 PostgreSQL 17.7 均实际完成 parent → head/check → parent → head/check，验证器退出码 0，四次 check 均无待生成操作。

- 表数分别为 120 → 121 → 120 → 121。降级仅移除 `ai_research_discovery_executions`，父迁移的 nullable JSON `reservation_context` 仍在。
- 实际检查新表 PK(id)、attempt/reservation 两个命名唯一约束、六个 RESTRICT 外键、PREPARED/OBSERVED/UNKNOWN 状态 CHECK 和 owner/run/created_at 索引。
- `command_json` 是 NOT NULL JSON，`result_json` 是 nullable JSON；首次升级与重升结构相同，两库实际 `alembic_version` 与迁移图均为唯一目标 head。
- **仅为空表 schema 验证**，不是含在途请求/结果的无损回退证明。降级会删除 journal 表及其中证据；实际回退须先停派发、备份、核对未结 operation，不能靠重升空表恢复回执。
- PostgreSQL 使用独立 cluster/user/db，仅该临时目录 Unix socket、端口标识 56497，`listen_addresses=''`。已 fast stop，主代理再次读回 `pg_ctl status` 为 `no server running`（exit 3）；未使用业务库、业务凭据或常驻服务。

命令（只能复查本次记录；再次执行需新的空目标，验证器拒绝覆盖证据）：

```sh
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  /private/tmp/iter196-discovery-execution-migration.tOBmLU/check_discovery_execution_migrations.py
```

| 制品 | SHA-256 |
| --- | --- |
| 临时目录中的 `check_discovery_execution_migrations.py` | `6553b6bc44bb63ad5f167fee7c509d8f3f7d05037484299eff2f567b4fadb4cc` |
| 同目录 `migration-evidence.json` | `d66ed03fda87295685b22b2465a9f00669deed4e5cfe030ce69672c773ff5339` |
| 同目录 `postgresql.log` | `41ca7d9187b31253e902381643e0d0158c109c29c5b6209bd43b31e66ab1340b` |
| `20260905_ai_research_discovery_executions.py` | `856f46cde33f8f2f02c3bc79717670e1fc17056726fe24ce0dec545e7378fc15` |

首次临时验证器因未将 backend 加入模块搜索路径，在执行迁移前发生 `ModuleNotFoundError`；只修正临时验证器后完整重跑成功，没有修改候选源码。本段不替代 MySQL、三库并发 claim 或含业务历史数据的迁移验收。

## 历史：budget_context head 的升级、历史数据与回退

该历史唯一 head 为 `20260905_ai_research_budget_context`，父版本 `20260905_ai_research_provider_model`。独立一次性 SQLite 文件 `budget-context-migration.sqlite` 与新增 PostgreSQL 数据库 `iter196_budget_context` 均实际完成 parent → head → parent → head；没有覆盖旧 provider-model 验证库或日志。

- 新列 `ai_research_quota_reservations.reservation_context` 为 nullable JSON；正常外键祖先链下的历史 reservation 升级后为 NULL。
- head 写入嵌套 JSON 并读回一致；降回父版本后主体字段、预留额度、状态、fencing 与 operation 记录不变，新列移除。
- 重升后历史 context 为 NULL，不按现价或旧运行 hash 伪造 quote；四次 `alembic check` 均无待生成操作。
- **非空 JSON 在降级时会丢失**：重升 NULL 不是恢复原快照。生产回滚必须停派发并先备份/核对未结操作与预算证据，本次不是无损审计回滚证明。
- PostgreSQL 17.7 仅监听本任务目录的 Unix socket、端口标识56496，使用独立临时用户/数据库；验证结束 fast stop，主代理再次读回 `pg_ctl status` 为 no server running（exit 3）。未触碰业务服务或业务库。

在候选 `src/backend` 执行：

```sh
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  /private/tmp/iter196-current-head.WAaH1k/check_budget_context_migrations.py
```

验证器拒绝已有 SQLite 文件/非空目标版本，重复验收应使用新的明确临时目标，不能覆盖已保留证据。

| 制品 | SHA-256 |
| --- | --- |
| `/private/tmp/iter196-current-head.WAaH1k/check_budget_context_migrations.py` | `419325e063e9eeab82bd0d2f0210da3ab0536d17f419e5bb7a6d652ccdbb24b2` |
| `/private/tmp/iter196-current-head.WAaH1k/budget-context-migration-verification.log` | `9889eb0fba42d31aa50409331897f65683342648bd8d3064a9a34f30ebd8f18c` |
| `20260905_ai_research_budget_context.py` | `6dc3103ea0b3f9ab0b0bd94897f36e04e0b18cc0301d7ae9309364aedda29d02` |

这些证据验证 schema/JSON/历史行，不代表 PostgreSQL/MySQL 多连接联合预算竞争、真实 provider、在途任务恢复或生产部署通过。

## 历史：provider_model head 的升级、历史数据与回退

该历史跑次唯一 head 为 `20260905_ai_research_provider_model`，父版本 `20260905_ai_research_dataset_identity`。临时 SQLite 与 PostgreSQL 17.7 均实际完成：旧 head → 插入正常外键绑定的历史 invocation → upgrade → check → downgrade 父版本 → re-upgrade → check。

- 新列 `ai_research_model_invocations.provider_reported_model` 为 nullable VARCHAR(256)。
- 历史 `resolved_model=legacy-configured-model` 行在升级后保留，observed 列仍 NULL；没有把配置 pin 回填为供应商实际观察值。
- 降级后新列移除、历史行保留；重升后列恢复且历史值仍 NULL。两次 `alembic check` 均无待生成 schema 操作。
- SQLite 使用新增 `provider-model-migration-retry.sqlite`；PostgreSQL 使用本文同一临时集群、仅 Unix socket。已停止并由 root 读回 `pg_ctl status: no server running`。

在候选 `src/backend` 执行的验证脚本：

```sh
/Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  /private/tmp/iter196-current-head.WAaH1k/check_provider_model_migrations.py
```

脚本 SHA-256：`f290a6bedb6707390a21eb741cc369ac0f8689db2a2e67922ef2a146066ca64a`；migration SHA-256：`c3077a519aab2bf9e9ad5df62af285486331a907b61f66fa9341b6c1a0ebb9d6`；详细记录 `/private/tmp/iter196-current-head.WAaH1k/provider-model-migration-verification.log`，SHA-256 `0cb4b376a079f12a60848916953f945b3b45a344e46af55448f1e3894443eb5f`。

首次验证脚本在 PostgreSQL 旧 `users.created_at` 上误传 aware datetime 而中断，SQLite 首次库及记录未覆盖；修正的只是临时验证器时间绑定，最终使用另一 SQLite 文件完整重跑双数据库。未关闭 FK、未改业务时间模型、未访问业务库。

本批测试还同步了 `asset_research/test_migration.py` 的旧 head 断言：先复现 1 failed，再完整 12 passed（7.51 秒）。本次仅验证新列历史 NULL 的可逆 schema，不证明非空观察值可无损降级，更不替代生产在途回滚或 MySQL 验收。

## 历史：dataset_identity head 的空库结果

| 数据库 | 空库 upgrade head + check | downgrade 到 v2 前一版本 | 再 upgrade head + check |
| --- | --- | --- | --- |
| 一次性文件 SQLite | PASS | PASS；`ai_research_runs` 不存在 | PASS；表恢复、无待生成 schema 操作 |
| 一次性 PostgreSQL 17.7 | PASS | PASS；`ai_research_runs` 不存在 | PASS；表恢复、无待生成 schema 操作 |

两种数据库均实际读取 `alembic_version`：升级后唯一版本为 `20260905_ai_research_dataset_identity`；降级后唯一版本为 `20260811_asset_research_task_leases`；重升后恢复当前 head。验证脚本退出码为 0，每一步均带断言；不是只读取 migration 文件或编译 SQL。

本段证据覆盖当时 dataset_identity schema 的空库升级及 schema 回退，不覆盖后续 provider_model head、带生产数据的迁移、在途任务回滚、MySQL、真实对象存储或跨服务隔离。新 head 证据单独登记在上节，不借用旧结果。

## 命令与隔离范围

临时目录由 `mktemp -d /private/tmp/iter196-current-head.XXXXXX` 创建，实际路径为 `/private/tmp/iter196-current-head.WAaH1k`。PostgreSQL 集群仅使用该目录的 Unix socket，`listen_addresses=''`，未监听 TCP，也未使用现有业务数据库或凭据。

```sh
/opt/homebrew/opt/postgresql@17/bin/postgres --version
/opt/homebrew/opt/postgresql@17/bin/initdb \
  -D /private/tmp/iter196-current-head.WAaH1k/pgdata \
  -A trust -U iter196_local --no-locale --encoding=UTF8
/opt/homebrew/opt/postgresql@17/bin/pg_ctl \
  -D /private/tmp/iter196-current-head.WAaH1k/pgdata \
  -l /private/tmp/iter196-current-head.WAaH1k/postgres.log \
  -o "-k /private/tmp/iter196-current-head.WAaH1k -p 56496 -c listen_addresses=''" \
  -w start
```

在候选工作树的 `src/backend` 执行：

```sh
LOG_DIR=/private/tmp/iter196-current-head.WAaH1k/logs \
  /Users/yunjinqi/opt/anaconda3/bin/conda run --no-capture-output -n base python \
  /private/tmp/iter196-current-head.WAaH1k/check_migrations.py
```

脚本给 Alembic `Config('alembic.ini')` 显式设置以下 URL，依次调用 `command.upgrade(cfg, 'head')`、`command.check(cfg)`、`command.downgrade(cfg, '20260811_asset_research_task_leases')`、再次 upgrade/check，并通过独立连接读取版本和表清单：

- SQLite：`sqlite+aiosqlite:////private/tmp/iter196-current-head.WAaH1k/migration.db`
- PostgreSQL：`postgresql+asyncpg://iter196_local@/postgres?host=/private/tmp/iter196-current-head.WAaH1k&port=56496`

## 清理与证据保留

验证后已执行 `pg_ctl -D /private/tmp/iter196-current-head.WAaH1k/pgdata -m fast -w stop`，返回 `server stopped`；随后 `pg_ctl status` 返回 `no server running`（该状态命令退出码 3 符合已停止语义）。临时脚本、空库文件和日志保留供复查，未删除用户数据；无验收 PostgreSQL 进程继续运行。
