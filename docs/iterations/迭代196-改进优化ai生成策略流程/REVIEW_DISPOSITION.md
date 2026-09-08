# 迭代 196 独立评审处置记录

> 评审来源：[REQUIREMENTS_REVIEW.md](REQUIREMENTS_REVIEW.md)
> 处置日期：2026-09-04
> 代码基线：`dev@a18bcf52`
> 性质：迭代治理决定；保留独立评审原文，不回写或改造评审者的论证

## 1. 总体结论

独立评审的核心判断合理：迭代 196 的可信性方向成立，但开工前仍需补齐容量裁决、部署能力、单 actor 语义、隐私生命周期、逐项追踪和迁移差异合同。16 项 finding 中：

- 直接采纳 11 项：A3、A4、B1、B2、B3、B4、B5、B6、B8、C2、C4；
- 部分采纳 5 项：A1、A2、B7、C1、C3；
- 整体不采纳 0 项。

评审中的三个事实需要校正：

1. 原需求集是 78 条 P0 FR、11 条 P0 NFR、6 条必需 MIG，共 95 个 P0 合同项；采纳新增/拆分项后，修订基线是 85 条 P0 FR、11 条 P0 NFR、6 条必需 MIG，共 102 个 P0 合同项；
2. 修订前设计表中明确标为 XL 的是 S3、Sandbox、S5 三项，不是四项；本次已将 Sandbox 正式命名为 S3b；
3. 多数据库契约是 `NFR-PORT-001`，不是 `NFR-COMP-001`。

这些校正不推翻评审指出的交付风险。

## 2. 逐项处置

| Finding | 处置 | 理由与边界 | 计划落点 |
| --- | --- | --- | --- |
| A1 范围过载 | **部分采纳** | 不立即凭空拆成两个迭代；S0 增加强制容量裁决、暂停判据、预签裁剪顺序和 Foundation Checkpoint。Foundation 只能声明“可审计、可恢复的探索地基”，不能称 `IMPLEMENTATION_ACCEPTED` 或可信 v2。容量不足时必须正式拆后续执行波次。 | README 8、DESIGN 13、AC-GOV-001 |
| A2 单人/自托管职责 | **部分采纳** | 项目没有证据证明“主部署通常单用户”；但 single-actor 语义确实缺失。冷却期、逐项挑战和证据哈希是补偿控制，不能创造独立审批。政策要求职责分离时，single actor 必须 BLOCKED。 | REQUIREMENTS 3、FR-GATE-010、DESIGN approval mode、AC-APP-002/005 |
| A3 部署拓扑与 DB | **采纳核心、校正实现** | 使用能力矩阵和运行时证据，不按数据库品牌绝对推断。SQLite 单进程默认不具备 DB-role 隔离；若不能证明等价的进程、存储和凭据边界，密封门必须 BLOCKED。 | FR-DEP-001～003、NFR-PORT-001、DESIGN capability registry、AC-DEP-001～002 |
| A4 账本与删除 | **采纳** | 不可变证据与删除请求必须预定义墓碑、artifact/证据失效、导出排除和密钥销毁语义；物理擦除时限由部署/法律政策决定。 | FR-PRIV-001（P1）、DESIGN retention policy、AC-PRIV-002 |
| B1 确认失效 | **采纳** | 规范化请求哈希是唯一权威；字段列表只能举例。 | FR-HYP-004、AC-HYP-002 |
| B2 i18n 孤儿验收 | **采纳** | 为现有 AC-I18N-001 增加直接需求。 | FR-UI-014 |
| B3 区间级追踪 | **采纳** | 新增逐 ID 矩阵，覆盖 FR/NFR/MIG；区间总览不能替代 G0 机器检查。 | TRACEABILITY_MATRIX.md、ACCEPTANCE 6 |
| B4 关键差异未定义 | **采纳** | 双写比较必须预注册 BLOCKING/NON_BLOCKING 分类与数值容差。 | MIG-002、AC-MIG-003 |
| B5 偏差流程 | **采纳** | 偏差需独立治理记录；不得把原 FAIL/BLOCKED 改写成 PASS，也不得把 `ACCEPTED_WITH_DEVIATION` 等同完整验收。 | FR-GATE-011、governance decision、AC-GOV-002 |
| B6 profile 迁移 | **采纳并加强** | 存量 YAML 没有 owner，不能自动归给触发迁移的当前用户；必须隔离并由管理员或用户显式认领。 | MIG-004、AC-MIG-005 |
| B7 命名一致性 | **部分采纳** | 现有 `ai_strategy_research_versions` 是兼容资产，不机械改名；保留旧表名，新 v2 表统一使用 `ai_research_`，并统一“前向观察（Forward Observation）”术语。 | DESIGN 5、S0 naming policy |
| B8 冷环境重放 | **采纳** | 100% 重放对象是冻结候选与证据链；LLM 生成阶段保证输入和谱系可追踪，不保证第三方模型逐字节输出一致。 | README 9、AC-REP-001 |
| C1 可用性护栏 | **部分采纳，P1** | 不用点击数鼓励隐藏必要确认；记录 v1 基线，关注完成率、主动操作时间、错误恢复率和必要确认负担。 | NFR-UX-002、AC-USAB-001 |
| C2 备份恢复 | **采纳，P1/G5** | 数据库、对象存储与 manifest 必须能一致恢复并重验哈希；不阻断本地 T1，但阻断声明具备生产证据恢复能力。 | NFR-DR-001、AC-DR-001 |
| C3 配额/限流 | **部分采纳** | LLM 与回测硬预算、原子预留和并发硬上限升为 P0；队列优先级、人工暂停和高级调度保留 P1。现有累计成本查询不足以证明并发不超支。 | FR-TASK-009～010、AC-QUOTA-001～002 |
| C4 “门”消歧/DSR 基准 | **采纳并校正** | 文档区分发布 Gate（G0～G5）与候选研究门禁；DSR 的派生 benchmark 方法、跨 trial 输入合同、频率/年化约定、估计器版本和概率阈值属于 versioned Promotion Policy。SR* 由试验账本和方法派生，不允许任意配置为有利数值。 | README、REQUIREMENTS 9、AC-STAT-001 |

## 3. 新增或变更合同

| 合同 | 优先级 | 决策 |
| --- | --- | --- |
| `FR-DEP-001～003` | P0 | 拓扑档案、能力矩阵、能力不足 fail-closed |
| `FR-GATE-010` | P0 | single/multi actor 审批语义与残余风险 |
| `FR-GATE-011` | P0 | 偏差治理记录，不改写原门状态 |
| `FR-UI-014` | P0 | i18n/error catalog 合同 |
| `FR-TASK-009` | P0 | 原子硬预算与并发上限 |
| `FR-TASK-010` | P1 | 队列优先级、暂停/恢复和高级调度 |
| `FR-PRIV-001` | P1 | 删除墓碑与证据失效策略 |
| `NFR-UX-002` | P1 | 可用性回归护栏 |
| `NFR-DR-001` | P1/G5 | 证据备份恢复与哈希校验 |

## 4. 修订后独立终审处置

对修订稿执行两轮逐需求追踪与可实施性审查，未发现 Critical，共发现并接受 6 项 Important：

| 终审发现 | 处置 | 落点 |
| --- | --- | --- |
| FR-HYP-002、FR-PIPE-001、MIG-001 原映射没有直接验证完整语义 | 增加直接具名场景，矩阵不再用相邻场景代替覆盖 | AC-HYP-005、AC-SEARCH-001、AC-PROTOCOL-001、TRACEABILITY_MATRIX |
| P0 的 AI 不得改门禁依赖 P1 challenger 场景 | 新增 P0 负例，P1 challenger 只覆盖增强能力 | AC-AI-GATE-001；FR-PIPE-008/009 映射拆分 |
| 原子预算只有 service 名称，无法指导跨 worker 防超卖 | 增加 bucket/reservation 持久模型、唯一约束、lease/fencing/CAS/reconcile 和三数据库并发合同 | DESIGN 5.15、S4、AC-QUOTA-001～002 |
| Sandbox 是 P0/XL，却没有正式切片和 Cut A 退出合同 | 新增 S3b，明确 owner、依赖、交付、验收、退出与回滚；矩阵所有 Sandbox 边界统一映射到 S3b | README 8、DESIGN 13 S3b、TRACEABILITY_MATRIX |
| 外部调用响应丢失时，仅靠本地 fencing 回收仍可能造成真实计费超卖 | 增加 `IN_FLIGHT/RECONCILING/BLOCKED_UNKNOWN`、operation read-back、未知结果保守结算/阻断和多资源全成全败锁序 | FR-TASK-009、DESIGN 5.15、AC-QUOTA-001 |
| MIG-006 仍由 JSON/回滚场景间接映射，未证明本迭代保留旧写路径 | 增加旧写路径/flag/rollback smoke 和后续 retirement decision 的直接负例 | AC-MIG-006、TRACEABILITY_MATRIX |

## 5. 开工裁决（历史记录）

在本次文档修订完成后，迭代仍处于“设计基线，尚未实施”。S1 开工前必须先完成 S0 容量与拓扑裁决；若 owner、容量、隔离拓扑或安全前置不明确，结论是 `BLOCKED`，不能用缩短验收或放松密封/沙箱/租户/密钥要求来换取名义上的完成。

## 6. 实施状态更新（2026-09-05）

第 5 节是开工时的治理裁决，保留其历史语义，不应被回溯改写。本轮随后完成了默认关闭的本地协议候选实现，并将预注册绑定、服务端数据预检、候选/holdout 完整性重验、租约未知结果保护和前端分阶段确认纳入 T1 契约验证。

后续代码审计把 `FR-TASK-004` 与 `FR-PIPE-012` 收紧为可执行合同：成功 stage 回执与 task/run 游标推进同事务；旧 lease 接管不得重放已提交副作用；执行器越级跳转必须拒绝。本轮进一步要求 freeze、holdout 签发/消费、independent evaluator、evidence package 与 approval 在写入前重验真实 resolver 绑定，缺 resolver 仍 fail-closed。本轮不排除文件的完整后端回归使用 `-n 6 --dist load --durations=15`，终态为 `4993 passed, 129 skipped, 174 warnings in 536.50s`，退出码 0。JUnit 共 5,122 项、0 failure/error，其中 156 项 v2 用例全部通过且无跳过。原心跳 StaticPool 夹具、Darwin 全机 PID 扫描依赖和本地 CLI 导入遮蔽问题已修复；没有用自动重试、旧绿灯或排除文件补齐本轮结果。完整命令、失败历史、修复边界和 JUnit 摘要见 [REGRESSION_6_WORKERS_20260905.md](REGRESSION_6_WORKERS_20260905.md)。129 项跳过仍保留其原有条件，不代表对应环境场景通过。

这不改变原有的发布边界：真实阶段执行器、独立隔离 runner、多服务凭据/存储边界、授权真实数据与 Provider、前向观察及灰度回滚仍未提供 T2/T3/G5 证据。因此 `IMPLEMENTATION_ACCEPTED` 和 `PROTOCOL_PRODUCTION_ENABLED` 仍为 `NO-GO`；权威的最新执行记录见 [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) 与 [ACCEPTANCE_REPORT_20260905.md](ACCEPTANCE_REPORT_20260905.md)。

## 7. 评审合理性复核后的计划加固（2026-09-08）

后续实现与独立代码审查进一步验证了原评审的核心方法是合理的：评审没有把“功能存在”误判为“可信边界成立”，而是要求把权限、幂等、外部副作用、迁移和逐项证据写成可否证合同。实现审查同时发现，原 102 项基线仍没有直接覆盖 terminal command 全图绑定、外部执行结果未知时的 inspect/reconcile、独立 worker 启动合同、command-scoped 证据包、人工授权签发/撤销、不可覆盖的拒绝结论，以及浏览器对审批回执的安全精确对账。

这些不是对独立评审原文的回写，也不改变 16 项 finding 的历史统计；它们是按同一评审原则形成的后续增量。因此计划新增 8 条 P0 FR：

| 新合同 | 计划落点 | 不能替代的环境证据 |
| --- | --- | --- |
| `FR-DATA-014` | terminal command/evaluation/authorization/artifact/audit/gate 全图与 `AC-SEAL-007` | 真实密封数据、独立身份与对象存储 |
| `FR-TASK-011～012` | operation journal、`UNKNOWN→inspect/reconcile`、默认关闭 worker、heartbeat/recovery 与 `AC-TASK-008` | 真实网络 ACK 丢失、独立 queue/IAM、跨进程竞争 |
| `FR-GATE-012～015` | evidence package v2、服务端请求/决定权威、grant issue/revoke、denial fence 与 `AC-EVIDENCE-002/AC-APP-007～010` | 真实多主体 RBAC、staging 决策和生产审计 |
| `FR-UI-015` | 安全响应投影、作用域隔离、幂等恢复和精确 intent hash 对账与 `AC-UI-008` | 受支持 Node 20、authenticated 实际 UI、axe/键盘人工验收 |

当前基线由 85 条 P0 FR 增至 93 条；加上 11 条 P0 NFR 与 6 条必需 MIG，共 110 个 P0 合同项。`REQUIREMENTS.md`、`DESIGN.md`、`ACCEPTANCE.md` 与 `TRACEABILITY_MATRIX.md` 已按这些 ID 更新。任何本地六 worker 绿灯仍只能作为组件合同证据；真实 PostgreSQL/MySQL/MariaDB、外部 Evaluator/Provider/Sandbox、对象存储/IAM、当前 authenticated UI、T2/T3 和灰度回滚没有新鲜证据时，整体继续 `NO-GO`。
