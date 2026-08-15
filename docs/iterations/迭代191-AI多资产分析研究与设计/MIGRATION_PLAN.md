# 迭代 191 数据库与股票兼容迁移计划

## 1. 目的、基线与边界

本文是迭代 191 通用多资产持久化和既有股票研究能力兼容迁移的执行契约。采用
**expand-migrate-contract**，但本迭代只交付 expand、兼容读取和受控 migrate
能力；不会删除、重命名或批量改写既有 `stock_analysis_*`、`stock_signal_*`
表，也不会以新表可写为理由提前执行 contract。

本计划核验时的代码基线为：

- Git HEAD：`e7fd2d5151c86ba62173b8d19736983a0a379909`；
- Alembic 唯一 head：`20260801_stock_signal_predictions`；
- 该 head 的真实 `down_revision`：`21d572b67d8e`；
- 该 head 的 `depends_on`：`None`；
- 本地当前开发数据库使用 MySQL，并已位于
  `20260801_stock_signal_predictions (head)`。本文不记录连接凭据。

以上是计划评审时的历史基线，不能被后续实现 revision 覆盖。当前代码链已在线性
foundation 后追加下列 expand 迁移：

> **数据库决策（2026-08-02）**：迭代 191 的部署、发布演练和真实方言验收统一以
> **MySQL Server 9.4.0（InnoDB）** 为目标。运行时使用项目既有 `mysql+aiomysql`，
> Alembic 实库合同使用同步 `mysql+pymysql` 连接到同一版本服务。SQLite 仅保留给本地
> 快速回归，不能替代 MySQL 证据；
> PostgreSQL 不属于本迭代的运行、CI 或 Go/No-Go 前提。项目其他既有模块的多数据库
> 兼容策略不因本决策被删除。

> MySQL 9.4.0 是本机客户端、`mysqld` 二进制和当前 `backtrader_web` 服务端的实测版本。
> `test_mysql_contract.py` 以 `SELECT VERSION() = '9.4.0'` 固定该契约；升级数据库版本时
> 必须先更新本计划、重新运行真实契约和发布评审，不能静默放宽版本范围。

| Revision | 父 revision | 目的 | 已完成的隔离证据 |
| --- | --- | --- | --- |
| `20260802_asset_research_foundation` | `20260801_stock_signal_predictions` | 创建含历史 run-prediction 关联表在内的 15 张通用 `asset_*` 表及基础约束 | SQLite fresh upgrade/downgrade |
| `20260803_asset_research_schedule_reliability` | `20260802_asset_research_foundation` | 为 schedule 增加成对租约、失败重放冻结上下文和退避索引；为 run 增加 retry 谱系 | SQLite schedule/retry 合同测试 |
| `20260804_asset_research_run_integrity` | `20260803_asset_research_schedule_reliability` | 保留已发布 revision 的线性检查点；触发器实现已由 `20260806` 的行级约束设计取代 | 线性升级/降级链验证 |
| `20260805_asset_research_outcome_reliability` | `20260804_asset_research_run_integrity` | 为 immutable prediction 附加非内容化的 outcome 评估租约和错误审计，防止同一 prediction 多 worker 重复取数 | SQLite upgrade/downgrade、并发租约和失败重试合同测试 |
| `20260806_asset_research_direct_run_prediction` | `20260805_asset_research_outcome_reliability` | 将 run 的 prediction 外键和 `CREATED/REUSED` 角色直接列化、校验历史关联、回填后删除旧关联表/触发器；以 MySQL FK + CHECK 保护 run 的终态基数 | SQLite 与一次性/共享 MySQL 9.4.0 upgrade/downgrade/re-upgrade、真实拒绝合同 |
| `20260807_asset_research_schedule_manifests` | `20260806_asset_research_direct_run_prediction` | 创建带审批证据的版本化静态系统调度清单，并把每条 `PUBLIC_SHADOW/ADMIN_EVAL` schedule 绑定至 manifest/hash；拒绝无证据的历史系统 schedule 回填 | SQLite migration/API/worker 合同、共享 MySQL 9.4.0 forward-repair 后目录及 rollback-only 合同；未发布阶段修正 MySQL downgrade 的 FK/索引删除顺序后，空库 full round-trip 通过 |
| `20260808_asset_research_manifest_evidence_required` | `20260807_asset_research_schedule_manifests` | 将 manifest 的 evidence URI/hash 收紧为数据库非空字段；旧行缺证据时停止升级，不伪造 backfill | SQLite upgrade/downgrade 和共享 MySQL 9.4.0 preflight/catalog/rollback-only 合同 |
| `20260809_asset_research_maturity_reason_contract` | `20260808_asset_research_manifest_evidence_required` | 将公共 `MaturityReason` 枚举落实为 `asset_signal_outcomes` 的命名 CHECK；拒绝 `MATURED` 等未定义值，旧行不兼容时停止升级并要求人工回填 | Pydantic/API 枚举回归、SQLite upgrade/downgrade 和共享 MySQL 9.4.0 rollback-only 非法值拒绝合同 |
| `20260810_asset_research_option_context_binding` | `20260809_asset_research_maturity_reason_contract` | 将期权 `LONG` 预测绑定到同一访问主体、同一冻结 instrument 和同一不可变上下文时间窗；历史绑定不匹配、不可用或已过期时停止升级，绝不伪造回填 | SQLite upgrade/downgrade、直接越权写入拒绝及合法写入持久化合同；共享 MySQL 9.4.0 的 `20260809 → 20260810` 预检/升级/目录/rollback-only 合同，以及同版本空库 full round-trip 均通过 |
| `20260811_asset_research_task_leases` | `20260810_asset_research_option_context_binding` | 为交互式 `asset_analysis_tasks` 增加 worker token、过期时间、心跳、尝试次数及 claim 索引；任务重启后可以显式恢复，且不改变 prediction、run 或报告事实 | SQLite task runner 生命周期/续租/并发唤醒回归；一次性 MySQL 9.4.0 完成 `upgrade head → downgrade 20260801 → upgrade head`，并通过真实列/约束/索引与 claim/释放租约合同；本机共享开发 MySQL 9.4.0 已在 0 行运行事实 preflight 后完成 `20260810 → 20260811` 并通过 rollback-only 合同 |

因此当前代码的唯一 Alembic head 是
`20260811_asset_research_task_leases`。本机共享开发 MySQL 9.4.0 已在 0 行运行事实 preflight 后
从 `20260810_asset_research_option_context_binding` 升级至该 head；postflight 复核了 revision、
任务租约列和 claim 索引，并运行了 rollback-only 约束合同。此前的 `20260809 → 20260810` catalog
与 rollback-only 证据仍保留为历史链路证据。一次性同版本 MySQL 也已完成包含 `20260811` 的完整
`upgrade head → downgrade 20260801 → upgrade head`。本机开发库和隔离证据均不替代任何生产目标的
备份、恢复演练和独立发布授权。

`20260807` 的 MySQL downgrade 顺序在上述临时 round-trip 首次暴露问题后、**在本迭代迁移文件
提交或发布前**修正为“先删 FK、再删其支持索引”；升级 DDL 和已部署 schema 均未变化。此例外只适用
于当前未发布工作树；一旦迁移进入已发布版本，文件必须视为不可变，后续修复只能用新的 forward
migration 或受控 repair。

若开始实现时仍只有上述一个 head，首个通用资产迁移拟定义为：

```python
revision = "20260802_asset_research_foundation"
down_revision = "20260801_stock_signal_predictions"
branch_labels = None
depends_on = None
```

迁移文件生成前必须重新执行 `alembic heads`。如果 head 已变化，实施者应把
`down_revision` 更新为当时唯一真实 head，并在评审中记录差异；禁止为了绕过错误
父版本而保留过期的 `down_revision`。没有独立迁移分支时不得设置 `depends_on`，
更不能用 `depends_on` 代替正常的父子 revision 关系。

本计划的安全边界：

- 旧股票 API、任务、报告、信号和结果仍是兼容期内的可回退权威路径；
- 股票兼容映射只表达研究语义，不创建订单、不连接账户、不推断真实持仓；
- 通用预测保持不可变，结果按 head 追加；迁移不能修改旧预测的历史输入；
- 不要求旧新哈希相等，也不要求新旧 LLM 报告逐字或逐字节相等；
- run-prediction 终态完整性只使用 MySQL/InnoDB 的外键和行级 `CHECK`，不创建触发器、
  不修改 binary-log 全局变量，也不要求迁移账号取得全局 `SUPER` 或 `SET_USER_ID`；
- `20260810` 同样只使用已有表上的组合唯一键、组合外键和行级 `CHECK`，不使用跨表
  trigger：预测行冻结 context 的 `as_of_at/available_at/expires_at` 副本，再由外键证明它们
  属于同一 context row；期权 `LONG` 的 CHECK 要求该时间窗覆盖 prediction cutoff；
- `20260811` 只扩展 `asset_analysis_tasks` 的可恢复运行态：历史行以 `attempt_count=0` 和空租约
  保留，迁移不合成 RUNNING 状态、不补写 heartbeat，也不修改任何 prediction、run、report 或旧股票表；
- 不得用 `stamp`、关闭约束或删除检查来绕过 upgrade 的真实对象核验；
- contract 阶段是后续独立变更，需重新审批、备份和实库演练。

## 2. Expand 范围：最终准确创建 15 张通用表

`20260802` 的历史中间态创建 15 张表，包含 `asset_signal_run_predictions`。最终 head 由
`20260806` 将该关联回填至 run 行并删除，`20260807` 再增加 `asset_schedule_manifests`，故
`ARCHITECTURE.md` 的最终 schema 是 15 张新表，不是 12 张。迁移按依赖顺序创建：

### 2.1 基础身份、来源与上下文

1. `asset_instruments`
2. `asset_data_source_registry`
3. `asset_position_context_snapshots`
4. `asset_source_snapshots`

### 2.2 分析任务和报告交付

1. `asset_analysis_tasks`
2. `asset_analysis_reports`
3. `asset_analysis_exports`
4. `asset_report_publications`

### 2.3 信号、运行和结果

1. `asset_schedule_manifests`
2. `asset_signal_schedules`
3. `asset_signal_runs`
4. `asset_signal_predictions`
5. `asset_signal_outcomes`

### 2.4 模型治理

1. `asset_model_registry`
2. `asset_model_status_events`

模型晋级的 T2 指标使用既有 `asset_model_registry.metrics_json` 与
`asset_model_status_events.metrics_snapshot_json` 作为内容寻址的证据载体。注册表列和
`scope_parameters_json` 还能重建规范化 `PromotionScope` 并复算 scope hash；T2 字段完整性、
统计一致性、scope 语义和 prediction cutoff 时点均由应用层发布门逐项校验，**不新增数据库
迁移**：本轮没有改变表、列、索引或数据库约束。相反，若需要让 MySQL 拒绝某个枚举值、外键、
唯一性或行级状态组合，才应以受控 Alembic 迁移固化；单纯新增一张表或改 schema 不能证明模型
的 walk-forward、Brier Skill 或前瞻实证已经成立。

列、外键、CHECK、唯一约束和索引以 `ARCHITECTURE.md` 第 4 节为权威。实施时还须
满足以下迁移约束：

- 15 张最终表均创建 `retention_class/retention_expires_at/legal_hold/tombstoned_at`
  公共生命周期列；持仓上下文业务 `expires_at` 仍为独立列，不能复用；
- 父表先于子表创建，downgrade 反向删除；
- 审计事实使用 `ON DELETE RESTRICT`，不得增加级联删除；
- UUID、时区时间、定点数、64 位十六进制哈希和 JSON 类型应按方言实现等价语义；
- 对 run-prediction 的终态基数，`asset_signal_runs` 的行级约束必须拒绝：无 prediction/角色的
  run 转为 `SUCCEEDED`、成功 run 清空任一直接字段，或非成功终态保留任一直接字段；
  prediction 外键还必须拒绝删除被成功 run 引用的 prediction。MySQL 必须在真实一次性方言库中
  执行这些拒绝用例；SQLite 只保留快速回归夹具；
- expand 不得删除、改名或改变任何旧表列的可空性、默认值、外键或索引；
- 完成后必须同时证明 15 张最终新表存在、旧关联表不存在且既有股票表仍存在。

## 3. Expand-Migrate-Contract 发布阶段

### 3.1 Phase 0：预检和恢复准备

上线前由迁移负责人和数据库负责人共同完成：

1. 记录 Git SHA、应用版本、数据库产品和精确版本、`alembic current`、
   `alembic heads` 与 schema inventory；
2. 要求 `alembic heads` 只有一个结果，且目标数据库位于预期父 revision；
3. 对旧股票表记录表结构、约束、索引、行数和业务主键范围；数据摘要仅用于证明旧表
   未被改写，不用于要求异构新旧哈希相等；
4. 创建可恢复备份，并在隔离实例完成至少一次恢复演练，记录 RPO、RTO 实测值；
5. 验证迁移账号具有建表、索引和约束权限，但应用运行账号保持最小权限；
6. 检查磁盘、事务日志、锁等待和对象存储容量；
7. 将新通用读写、股票兼容新读和双写开关全部设为关闭；
8. 冻结迁移窗口内并行 schema 变更，明确值班人、停止条件和回退决策人。

任何一项证据缺失、数据库 revision 不明或备份无法恢复，都必须停止上线，不能用
`alembic stamp` 掩盖状态。

### 3.2 Phase 1：Expand

1. 部署仍能只使用旧表的应用版本；
2. 执行线性 Alembic upgrade，创建 15 张最终通用表及约束；
3. 运行只读 schema verifier，逐表核对列、类型、外键、CHECK、唯一约束和索引；
4. 对旧表重做结构和行数快照，确认无删除、重命名或批量更新；
5. 保持通用股票新读和双写关闭，完成旧 API 回归；
6. 通过后才允许开启非股票资产或管理员影子写入。

MySQL DDL 会隐式提交，不能把 Alembic 事务外观当作原子保证；每个 DDL 后均需记录
实际对象状态，并准备 forward-repair。SQLite 表重建语义只作为本地回归验证。

### 3.3 Phase 2：Migrate 和兼容运行

迭代 191 不要求把所有旧股票历史行复制进新表。默认路径是：

- 旧股票端点继续读写旧表；
- 只读兼容端点 `GET /api/v1/asset-research/stock-compat/signals` 通过
  `StockResearchCompatibilityAdapter` 读取旧事实并执行版本化语义映射；它保留旧表
  的 owner visibility 与 cursor 顺序，明确标记无法恢复的 canonical identity、来源
  manifest、持仓上下文和 outcome head，始终 `RESEARCH_ONLY + execution_disabled=true`；
- 新通用表用于新多资产任务、影子预测和明确启用后的新股票记录；
- 历史回填、双写和切换新读均使用独立开关，按租户/主体/流量 cohort 放量；
- 每次切换保留结构化对账证据和一键退回旧读路径的能力。

只有需要长期统一统计且能满足第 6 节来源契约的历史记录，才进入审批后的可选回填。
不满足来源、身份、cutoff、持仓上下文或 outcome head 契约的行保留在旧表，由兼容
适配器读取，禁止伪造通用事实来追求“100% 搬迁率”。

该桥接不是双写、回填或泛化 `AssetResearchPlugin`：旧 `/api/v1/stock-analysis` 仍是
股票任务、报告和信号的权威读写入口；兼容路由只能显示其已有事实。后续若要启用新股票
写入、双写或 cohort 切换，必须按本计划的独立开关、结构化对账和发布审批执行。

### 3.4 Phase 3：Contract（本迭代不执行）

contract 必须是后续独立 revision 和发布计划，并至少满足：

- 连续两个已部署发布版本的结构化语义对账无未解释缺陷；
- 观察窗口、最小样本量、租户覆盖率和错误预算由发布审批明确配置；
- 所有旧读调用点、离线任务、报表、运维脚本和回滚版本均已盘点；
- 已归档必要历史，恢复演练证明可以回到 contract 前状态；
- 旧写入已停止，数据保留、法务和审计责任人批准；
- 真实 MySQL 的 contract 与恢复演练通过；SQLite 仅作为本地回归辅助，不承担发布证明。

“两个版本”不自动等于固定天数，也不自动满足样本量。未达到门禁时可以无限期保留
旧表；本迭代的 upgrade/downgrade 不得包含旧表 drop。

## 4. 四类数据库起点

### 4.1 全新空库

1. 创建空的隔离数据库；
2. 从 Alembic base 执行 `upgrade head`，不得先用 ORM `create_all` 伪造迁移结果；
3. 核对唯一 head、全部历史表和 15 张最终新表；
4. 验证约束、索引、旧关联表/触发器不存在及最小写入/拒绝用例；
5. 在同一隔离库演练 downgrade 到
   `20260801_stock_signal_predictions`，再 upgrade 到 head。

### 4.2 正常现存库

适用于已处于 `20260801_stock_signal_predictions` 的真实现存库：

1. 备份和记录旧表结构、行数、关键范围；
2. 执行 upgrade；记录 revision 前后值和 schema inventory。若 DDL 失败，停止第二个迁移进程，
   按第 4.4 节进行只读对象盘点和已评审的 forward-repair，不能试探性重跑或 `stamp`；
3. 核对旧表结构、行数和抽样内容不变；
4. 运行旧股票 API、调度、报告、outcome 刷新和权限回归；
5. 保持双写关闭，先运行兼容只读和结构化对账；
6. 通过发布审批后再按 cohort 开影子写。

### 4.3 ORM `create_all` 或未 stamp 的历史库

不得看到表存在就直接 `stamp head`。先生成 schema inventory 并与每个历史 revision
的实际效果比较：

- 只有结构、约束、索引和必要数据前置条件与某个 revision 完全一致，且评审证据
  批准时，才可 stamp 到该 revision；
- 有缺列、缺约束或类型漂移时，应编写可审计的 repair migration，修复后再继续；
- 无法确定来源的库先克隆到隔离环境演练，生产库不得试探性升级；
- `create_all` 兼容测试只是特殊起点测试，不能代替真实 Alembic 全链验证。

### 4.4 部分失败或疑似已升级库

尤其在 MySQL 上，revision 表未前进不代表 DDL 未发生。恢复步骤是：

1. 停止新写和第二个迁移进程；
2. 获取迁移全局锁；
3. 使用只读 verifier 逐对象检查表、列、约束、索引，并确认旧关联表和资产 run 触发器不存在；
4. 将实际状态与预期 migration step 对比，保存差异证据；
5. 能无损补齐时执行评审过的 forward-repair；状态不可信时从已验证备份恢复；
6. 只有全部后置条件成立后才更新 revision 状态；
7. 禁止盲目重跑整个 migration，也禁止用 `stamp` 跳过残缺对象。

## 5. 批量回填的锁、事务和重启契约

历史回填是可选操作，必须由单独变更单启用。即便启用，也遵循以下契约。

### 5.1 稳定读取边界

- 启动时冻结 `source_high_water_mark`，例如 `(created_at, id)` 上界；
- 使用 `(created_at, id)` 稳定排序和 keyset pagination，禁止 `OFFSET` 扫描导致
  并发插入时遗漏或重复；
- batch size 是配置项，初始建议 500 行，必须根据实库锁时间、日志量和延迟压测
  调整，不能写死为容量承诺；
- 每批只处理 high-water mark 以内的行；之后的新写由双写或下一次回填覆盖；
- 映射版本、代码 SHA、源表范围和 cutoff 必须进入迁移证据。

### 5.2 单迁移者锁

默认只允许一个回填进程：

- MySQL：使用带超时的命名 `GET_LOCK`，连接释放即失效；
- SQLite：使用进程/文件锁，并在写批次使用 `BEGIN IMMEDIATE`；
- 锁获取失败应退出并告警，不能降级成无锁继续；
- MySQL 默认不启用多 worker；只有经过实库压测、锁等待分析和独立批准，才可评估
  `FOR UPDATE SKIP LOCKED` 的并行批处理。

锁只防止多个迁移者竞争，不能代替唯一约束、幂等键和事务。

### 5.3 每批事务

每个 batch 在单独短事务中完成：

1. 锁定或重新读取本批源行，确认仍位于冻结边界；
2. 解析身份和版本化语义映射；
3. 写目标对象、关联和本批对账证据；
4. 重新读取目标行，验证唯一键与结构化字段；
5. 提交后才推进外部 checkpoint。

MySQL 的 DML 批次使用真实事务；SQLite 串行写仅用于本地回归。遇到唯一冲突时应读取
已有目标并比较规范化结构：完全等价才计为幂等复用，不等价必须记为冲突并停止该
cohort，禁止 `INSERT IGNORE` 后把差异当成成功。

checkpoint 可存放在受控迁移证据存储中，但正确性不能依赖单个内存游标。重启应以
稳定源键和目标幂等键执行 anti-join/重读，因此在“提交成功但 checkpoint 未写”
的窗口也只会得到验证过的复用。迁移证据记录 batch 范围、读取数、创建数、复用数、
跳过数、冲突数、耗时和内容摘要，不新增第 16 张业务表。

## 6. 旧股票语义到通用契约的映射

旧系统的动作只有 `BUY`、`SELL`、`WATCH`，质量状态只有 `eligible`、
`degraded`、`rejected`。它没有通用契约中的已验证账户持仓、模型晋级、完整
`PredictionHead`、head spec 或合规能力快照。因此映射必须保守且版本化，例如
`stock-legacy-map-v1`。

### 6.1 候选研究观点

只有旧记录为 `eligible` 时，才允许按动作生成影子候选：

| 旧字段 | 候选 `market_view` | 候选 `normalized_direction` | 候选 `recommendation` | `position_context` | `trade_intent` |
| --- | --- | --- | --- | --- | --- |
| `BUY` | `BULLISH` | `LONG` | `BUY` | `UNKNOWN` | `NONE` |
| `SELL` | `BEARISH` | `SHORT` | `SELL` | `UNKNOWN` | `NONE` |
| `WATCH` | `NEUTRAL` | `NEUTRAL` | `HOLD` | `UNKNOWN` | `NONE` |

该表只描述 candidate，不声称 BUY 是开仓或 SELL 是平仓/开空。旧 `run_id`、持仓清单
或页面展示逻辑均不能被当作账户持仓证据。映射后的 `execution_disabled` 固定为
`true`。

质量和发布覆盖按以下规则：

- `eligible` → `quality_status=ELIGIBLE`；
- `degraded` → `quality_status=DEGRADED`，候选方向不直接发布；
- `rejected` → `quality_status=REJECTED`，发布
  `INDETERMINATE + AVOID + NONE + INSUFFICIENT_DATA`；
- 旧模型没有通用晋级证据，因此即使 eligible，普通用户发布也默认
  `INDETERMINATE + HOLD + NONE + RESEARCH_ONLY`；
- degraded 依据原因码发布 `HOLD` 或 `AVOID`，但动作、方向仍不得越过
  `ARCHITECTURE.md` 的高优先级覆盖规则；
- 旧质量原因、特征版本、策略版本、模型版本和 source snapshot hash 作为来源证据
  保留，未知字段保持 `null` 或明确的 `UNKNOWN`，不能补 0 或编造。

只有新模型注册表中对应股票 scope、head、horizon、policy/model/calibration 组合
已经正式晋级，且当前质量、许可和地区门禁通过，才可用通用真值表发布可行动研究
建议；历史兼容映射本身不能完成晋级。

### 6.2 概率与 outcome

旧 `buy_probability/sell_probability/watch_probability` 不能自动包装成通用
`PredictionHead`。只有另行批准的 `stock.legacy_signal_action` head 明确了
target definition、互斥完整 labels、scoreability rule、baseline、训练 cutoff、
校准证据和 `head_spec_hash` 后，才能迁移为可评分 head；否则概率保留为受限的
legacy evidence，不进入通用晋级统计。

旧 outcome 同样不得机械拆成多个新 outcome：

- 保留旧 `pending/partial/scored/unscorable` 状态及 1/5/20 日收益证据；
- 只有目标定义、入退价格口径、成本、基准、日历和成熟规则完全明确时，才映射到
  对应 `outcome_kind`；
- 无法证明同一 head spec 的记录留在旧表，由兼容层展示，不能混入新 Brier、胜率或
  模型晋级 cohort；
- 旧浮点结果和新 Decimal 结果按明确 tolerance 比较，不能要求二进制相等。

### 6.3 run、prediction 和直接关系

旧 prediction 直接持有可空 `run_id`；新契约要求 run 必须且只能来源于 task 或
schedule，并在 `asset_signal_runs.prediction_id/prediction_link_role` 上保存
`CREATED/REUSED` 审计事实。因此禁止复制旧 `run_id` 到新字段：

- 能从旧事实证明访问主体、task/schedule 来源、cutoff policy 和不可变输入时，才可
  创建对应新 run、prediction 和直接关系；
- 缺少新 run 来源契约的历史行保持 compatibility-only；
- 首次持久化 prediction 的服务路径写 `CREATED`，后续等价运行写 `REUSED`；
  prediction 的不可变唯一键和编排器冲突恢复负责该业务语义，数据库则强制每个 run 的终态
  基数和 FK 引用完整性；
- 创建或复用 prediction、写 direct relation 和把 run 置为 `SUCCEEDED` 必须同事务提交；
- 不得为提高搬迁率创建无主体、无来源或无 cutoff 的孤立 run。

## 7. 可选双写与切换策略

双写只适用于启用时刻之后的新股票记录，默认关闭；它不是历史回填的替代品。建议的
状态机为：

| 模式 | 旧写 | 新写 | 读取权威 | 失败处理 |
| --- | --- | --- | --- | --- |
| `OFF` | 是 | 否 | 旧表 | 保持当前行为 |
| `SHADOW` | 是 | 是 | 旧表 | 旧响应不被新写失败改变；新写失败必须告警和留证 |
| `ENFORCE` | 是 | 是 | 按 cohort 新读，旧读可回退 | 任一必需写失败则整体失败或走已批准 outbox |

具体要求：

- 同一数据库内的 ENFORCE 双写应位于一个业务事务；跨存储只能采用可追踪 outbox/
  inbox 和补偿流程，不能声称分布式原子性；
- SHADOW 不吞掉新写异常，需按租户、映射版本和错误码统计；
- `effective_from`、cohort、开关操作者和配置版本必须审计；
- 新旧写使用各自域的幂等键，不要求
  `stock_signal_predictions.prediction_key == asset_signal_predictions.prediction_key`；
- 切换新读前先满足第 8 节语义门禁；
- 出现未解释差异、错误预算超限或新路径依赖故障时，将新读和双写切回 `OFF`，旧表
  因未 contract 仍可继续服务；
- 何时从 SHADOW 进入 ENFORCE 是发布决策，不得由迁移脚本自动完成。

## 8. 结构化对账：比较语义，不比较异域哈希或生成文本

旧 `prediction_key` 的输入域是 source、owner scope、universe、symbol、
as-of date、feature version、decision policy version、model version；新
`decision_input_hash/prediction_key` 还包含规范身份、cutoff、horizon、持仓快照、
源快照、成本、head spec、capability、compliance 和多项版本。二者设计域不同，
**哈希相等不是验收条件**。

### 8.1 配对键

对账先用明确的 legacy reference，再按下列结构配对：

- 访问主体：owner scope 和 user/access principal；
- 规范股票身份及 identity version；
- source/universe；
- `as_of_at`、数据 `available_at` 和 cutoff；
- feature/policy/model 映射版本；
- 回填批次和 legacy mapping version。

多匹配或零匹配均是待解释结果，不能任取一行。

### 8.2 预测和结果比较

结构化 diff 至少比较：

- 身份、访问主体、as-of/cutoff 和数据可用时间；
- 质量状态、原因码和 source evidence；
- 旧动作与候选研究观点的映射；
- 发布动作是否正确执行 `RESEARCH_ONLY/INSUFFICIENT_DATA` 覆盖；
- `position_context=UNKNOWN`、`trade_intent=NONE`、
  `execution_disabled=true` 是否保持；
- 概率只在同一获批 head spec、标签映射和 tolerance 下比较；
- run/prediction 关联基数、幂等复用和权限隔离；
- outcome 的目标、horizon、价格口径、成本、成熟状态和数值 tolerance。

差异分类为：

1. `EXPECTED_MAPPING`：版本化语义映射导致的预期差异；
2. `NONDETERMINISTIC_PRESENTATION`：不影响事实的展示或 LLM 措辞差异；
3. `SOURCE_OR_TIMING`：输入快照或 cutoff 不同，需解释但不能强配；
4. `DEFECT`：身份、权限、质量、发布动作、数值口径或关联不变量错误。

发布门禁要求配置窗口和样本量内 `DEFECT=0`，其他类别都有原因、owner 和证据。
窗口长度、最小记录数和允许的非缺陷比例由上线审批确定，不以“两个版本”推定固定
四周或固定流量。

### 8.3 报告比较

报告不做 `content_hash` 相等或渲染文本逐字比较。应比较：

- 必需 section 的集合、顺序和 schema version；
- 结构化事实、数字、单位、日期、身份和 evidence ID；
- candidate/published 决策、质量和原因码；
- 权限裁剪、许可受限字段和候选概率是否正确隐藏；
- 导出/发布工件是否引用同一结构化报告版本；
- 对同一工件自身可用 content hash 校验存储完整性，但不跨旧新报告要求相等。

LLM 措辞、段落、标点或模板变化属于展示层差异；若它改变数字、证据归属、发布动作
或风险披露，则升级为 `DEFECT`。

## 9. 失败恢复、应用回退和 downgrade

### 9.1 应用层回退

最先使用可逆开关：

1. 停止新 cohort 放量；
2. 将通用股票新读切回旧读；
3. 将双写切为 `OFF`；
4. 保留已写通用事实，不就地修改或删除；
5. 记录失败时间窗和受影响 principal，离线对账后再决定修复或重放。

应用版本回退必须使用仍理解旧 schema 的构建；因为本迭代不 contract，旧路径保持
可用。若旧版本会误读新表，应先验证兼容矩阵再回退二进制。

### 9.2 Alembic downgrade

- 所有方言都要在一次性隔离库执行
  `upgrade head → downgrade 20260801_stock_signal_predictions → upgrade head`；
- downgrade 在链路中先恢复历史关联表并移除直接列，随后按子表到父表删除 15 张最终新表
  （及其回退时短暂恢复的关联表/索引），不触碰旧股票表；
- 生产 downgrade 只在尚无需要保留的新表数据，或数据已完整归档并获审批时执行；
- 有真实新事实后优先应用回退和 forward-fix，而不是破坏性 downgrade；
- contract 发布后的恢复不属于本迁移，必须使用其独立备份和恢复手册。

### 9.3 方言相关恢复

- MySQL：DDL 隐式提交后按实际 schema 进行 forward-repair 或备份恢复，禁止假设
  整体 rollback；必须演练“建到中间对象后失败”的重启；
- SQLite：升级前保留数据库文件副本；表重建失败时关闭写入、校验副本后原子替换，
  并重新启用、核验外键；它只服务本地回归，不构成发布回滚证据。

任意恢复路径都必须再次核对 Alembic revision、schema inventory、旧表行数、约束和
应用健康。revision 正确但对象不完整仍视为失败。

## 10. MySQL 真实验证矩阵

“真实验证”指实际数据库引擎和驱动，不是 mock，也不能用 SQLite 通过来代替
MySQL。测试环境不得包含生产凭据或生产个人数据。

| 场景 | MySQL（发布证据） | SQLite（仅本地回归） |
| --- | --- | --- |
| 唯一 head 与 revision 链 | 必测 | 必测 |
| 空库从 base upgrade 到 head | 一次性真实数据库 | 临时磁盘文件 |
| 现存父 head upgrade | 必测 | 可选 |
| 14 最终新表、旧关联表/触发器不存在和旧表保留 | 必测 | 必测 |
| 列、FK、CHECK、唯一约束、索引 | 实际 catalog 和拒绝用例 | `PRAGMA foreign_keys=ON` 后实测 |
| run-prediction 终态不变量 | 直接行 CHECK、FK 和服务组合实测 | CHECK/FK 和服务组合实测 |
| binary-log 触发器前置条件 | 不适用：本链不创建触发器 | 不适用 |
| upgrade/downgrade/upgrade | 必测 | 必测 |
| 中途失败、重启和幂等修复 | 必测，重点覆盖隐式提交 | 可选 |
| 批量锁、并发写和唯一冲突 | `GET_LOCK`/事务 | 串行 writer |
| OFF/SHADOW/ENFORCE 双写 | 必测 | 可选 |
| 旧股票 API/任务/结果回归 | 必测 | 可选 |
| 备份恢复 | dump/snapshot 恢复 | 文件副本恢复 |

每次验证证据至少包括：

- Git SHA、数据库产品/版本、驱动版本；
- revision 前后值和 `alembic heads` 输出；
- 15 张最终表、旧关联表/触发器不存在的 schema inventory，以及旧表 inventory；
- fresh/existing/downgrade/recovery 场景结果；
- 旧表行数和抽样主键范围前后对比；
- 约束拒绝用例、锁竞争和失败重启输出；
- 结构化对账摘要及每个 `DEFECT` 的处置；
- 备份恢复的开始/结束时间、数据核对和实测 RPO/RTO；
- 日志或报告的持久化 URI 与自身内容哈希。

MySQL 必须为 9.4.0，并匹配生产的 InnoDB、字符集、排序规则和时区设置；SQLite 使用
磁盘文件而不是只测内存库。

## 11. 实施后的命令与测试入口

以下命令在迁移代码和测试落地后执行；当前文档不把尚未实现的测试文件误报为已通过。
所有 Python/Alembic/pytest 命令使用项目要求的 Anaconda base 环境：

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base alembic heads
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base alembic current
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base alembic upgrade head
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base pytest -q \
  tests/asset_research/test_migration.py \
  tests/asset_research/test_mysql_contract.py
```

在一次性数据库上额外演练：

```bash
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base alembic downgrade \
  20260801_stock_signal_predictions
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base alembic upgrade head
```

真实 MySQL 9.4.0 URL 通过 CI secret 或受控环境变量注入，命令和测试日志不得打印密码。
测试应主动输出数据库产品和安全脱敏后的 server version，以证明没有静默回退到 SQLite。
真实直接关系合同可对已经迁移的受控 schema 执行；仅在一次性 CI 库中允许先执行 DDL：

```bash
ASSET_RESEARCH_MYSQL_SHARED_SCHEMA_URL='mysql+pymysql://…/codex_iter191_example' \
ASSET_RESEARCH_MYSQL_SHARED_SCHEMA_CONFIRM=yes \
  /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest -q \
  tests/asset_research/test_mysql_contract.py
```

上面的 shared-schema 合同只做 rollback-only 断言。`20260811` 的 runner 会创建并清理 task
夹具，因此只能在已经迁移到 head 的一次性库中附加下列显式确认，数据库名必须以
`codex_iter191_` 开头：

```bash
ASSET_RESEARCH_MYSQL_TASK_RUNNER_DISPOSABLE_URL='mysql+aiomysql://…/codex_iter191_example' \
ASSET_RESEARCH_MYSQL_TASK_RUNNER_DISPOSABLE_CONFIRM=yes \
  /Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest -q \
  tests/asset_research/test_mysql_contract.py
```

该测试实际验证一次原子领取、执行和释放租约，最终删除其精确 UUID 夹具；不得指向共享开发库、
业务库或生产库。

建议新增的自动化测试职责：

- `tests/asset_research/test_migration.py`：fresh、legacy create_all、15 张最终表、约束、
  历史关联回填以及 upgrade/downgrade/upgrade；
- `tests/asset_research/test_mysql_contract.py`：已经升级的 MySQL 9.4.0 schema、15 张最终表、
  旧关联表/触发器不存在、非法 run 状态和删除被引用 prediction 的拒绝；
- CI job：`asset-research-mysql-contract` 使用官方 `mysql:9.4.0` 一次性数据库，执行
  `test_migration.py` 和 `test_mysql_contract.py`；SQLite job 仅执行快速回归。该 job 已纳入
  `ci-summary` 的阻断质量门禁。

## 12. 上线 Go/No-Go 清单

只有以下条件全部满足才可上线 expand：

- [ ] 代码 SHA 和本文基线差异已评审；
- [ ] `alembic heads` 只有一个，首个新 revision 的 `down_revision` 指向执行时真实 head；
- [ ] `depends_on=None`，除非确有经评审的独立迁移分支；
- [ ] upgrade 准确创建 15 张最终通用表，列、约束、索引及旧关联表/触发器不存在符合架构；
- [ ] 未删除、重命名或改写任何旧股票表；
- [ ] fresh、existing、downgrade、部分失败和恢复场景均通过；
- [ ] MySQL 真实方言有 evidence，未用 mock/SQLite 替代发布证据；
- [ ] 备份已恢复演练，RPO/RTO 为实测而非估算；
- [ ] BUY/SELL/WATCH、质量、持仓未知和发布覆盖映射通过；
- [ ] 对账使用结构化身份、cutoff、动作、原因、证据和 outcome 语义；
- [ ] 未把旧新 prediction hash 相等或 LLM/report 文本相等设为门禁；
- [ ] 双写默认关闭，SHADOW/ENFORCE 有审计、错误预算和回退开关；
- [ ] 旧股票 API、调度、报告、outcome 和权限回归通过；
- [ ] 没有未解释的 `DEFECT`，所有预期差异都有映射版本和证据；
- [ ] 值班人、停止条件、恢复负责人和发布审批人已确认；
- [ ] contract 仍明确排除在迭代 191 之外。

任一项未满足即 No-Go。不得通过 stamp、忽略冲突、缩减方言矩阵或删除旧表来消除
验收失败。
