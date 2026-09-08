# 迭代 196：本地 T1 证据追踪（2026-09-05）

> 2026-09-06 最新增量见 [版本化发现工作流](DISCOVERY_WORKFLOW_20260906.md)：持久化新旧执行图、公开三阶段worker、trial/stage同事务、成功/失败恢复不重复调用以及模型JSON严格拒绝。最新完整目录的原始证据统一见 [六worker记录](REGRESSION_6_WORKERS_20260905.md)，不拼接任何历史跑次。显式freeze、未对账市场观察、独立密封评估/审批部署及真实环境仍有缺口，不提升原追踪矩阵的整体验收状态。

> 历史预算切片统一回归：完整后端5,216通过、129跳过、601.36秒，6 worker；379项 v2全过。修复后437项聚焦及首轮预算全量失败/中断分别保留。本批补不可变请求、完整资源组、持久 quote、严格缺快照拒绝及旧单笔恢复保护，见 [预算交付记录](MODEL_BUDGET_BUNDLE_20260905.md)。合成政策与 HTTP transport seam 不是真实供应商上界/账单/部署验收，下文数字保留各自历史范围。

> 这是一次本地、确定性实现验收的证据索引，不替代 [TRACEABILITY_MATRIX.md](TRACEABILITY_MATRIX.md) 的逐项发布状态，也不把 fixture/mock 结果写成真实数据、独立部署或生产启用证明。
>
> 后续增量：最新前端 147 文件/1,315 项全量通过，历史分页/直链/双流轮询证据见 [六 worker 记录](REGRESSION_6_WORKERS_20260905.md)；FR-PIPE-010/FR-TASK-004 的单次派发与结算 60 项聚焦见 [派发安全记录](DISPATCH_SAFETY_20260905.md)，其中 ProviderResponse 非 Mapping 账本缺口已修复并经 52 项联合聚焦验证，见 [响应验证记录](PROVIDER_RESPONSE_VALIDATION_20260905.md)；FR-DATA-002 的实际文件字节、持久 receipt 与 API factory 接线见 [文件 resolver 记录](FILESYSTEM_DATASET_RESOLVER_20260905.md)。下文早期 156 项及 HTTP/UI 数字是各自历史跑次，不代表后续源码已完成整体验收。

## 1. 状态语义

- `T1_PASS`：具名代码契约已由本地自动化覆盖并通过；
- `T1_PARTIAL`：代码/fixture 的可验证部分已覆盖，但原 AC 还要求真实拓扑、浏览器、性能或外部系统证据；
- `BLOCKED_ENVIRONMENT`：本机没有可授权执行该场景所需的真实环境；
- `NOT_RUN`：尚未执行。

因此，主追踪矩阵中的 P0 行仍不批量改写为 `PASS`。只有某个 AC 的全部前提、负例和要求的证据等级均完成后，才可以由负责验收人逐项回填。

## 2. 已通过的本地契约映射

本批 FR-TASK-009／FR-PIPE-010／AC-QUOTA-001 的增量由 `test_ai_research_model_budget.py`、`test_ai_research_quota_bundle.py`、`test_ai_research_quota_bundle_reconciliation.py`、`test_ai_research_generation_http_pipeline.py` 和 gateway/factory 测试共同覆盖：契约与封存 bytes、缺钱/缺快照零派发、完整组竞争/CAS 回滚、未知用量保留、旧单笔恢复拒绝。本地机制为 `T1_PASS`，AC 整体仍为 `T1_PARTIAL`：真实费用/Token上界、全入口预算、group readback、跨数据库竞争和账单恢复尚未完成。不能将下表宽泛需求组的历史 `T1_PASS` 解释成这些剩余项也通过。

| 需求/验收组 | 主要自动化证据 | 本地状态 | 尚未替代的证据 |
| --- | --- | --- | --- |
| AC-HYP-001～005、AC-HYP-007、AC-UI-002 | `test_ai_research_hypothesis_registry.py`、`test_ai_research_data_precheck.py`、`test_ai_research_v2_api.py`、`TrustedResearchWorkbench.test.ts`、`useAiResearchV2.test.ts`、[HTTP_T1_EVIDENCE_20260905.md](HTTP_T1_EVIDENCE_20260905.md) | `T1_PASS` | 解锁设备上的人工焦点、屏幕阅读器与辅助技术验证。 |
| FR-DATA-001～003、011～012；AC-DATA-001～004 的确定性部分 | `test_ai_research_dataset_integrity.py`、`test_ai_research_dataset_registry.py`、`test_ai_research_data_precheck.py`、`test_ai_research_task_runner.py`、`test_ai_research_generation_materialization.py`、`test_ai_research_forward_observation.py`、`test_ai_research_sandbox_runner.py` | `T1_PASS` | opaque receipt、服务器签发对象版本/摘要/大小/identity、legacy 拒绝、任务/物化重验和 forward receipt 均为本地受控 resolver 证据；仍缺批准数据源、真实对象存储/IAM、真实执行模型/容量及隔离容器全链路。 |
| FR-DATA-004～010；AC-SEAL-002～005 的逻辑部分 | `test_ai_research_candidate_registry.py`、`test_ai_research_holdout_authorization.py`、`test_ai_research_independent_evaluator.py`、`test_ai_research_hypothesis_registry.py` | `T1_PASS` | Explorer/Evaluator 的真实独立 credential、queue、对象存储拒绝测试。 |
| 同族留出预算 | `test_v2_epoch_derives_family_hash_server_side_and_rejects_client_selected_hash`、`test_disclosed_family_cannot_open_a_second_epoch` | `T1_PASS` | 迁移后的目标数据库并发压力和已授权真实研究运行。 |
| FR-LEDGER-001～008、FR-PIPE-004、FR-GATE-001～003 | `test_ai_research_experiment_ledger.py`、`test_ai_research_statistics.py`、`test_ai_research_promotion.py`、`test_ai_research_evidence_package.py` | `T1_PASS` | 冷环境重放、实际数据/依赖镜像和性能基线。 |
| FR-PIPE-012、AC-TRUTH-003 的 legacy prompt/display 分支 | `test_ai_strategy_research_request_generates_prompt_from_structured_fields`、`test_ai_strategy_research_workflow_steps_schema_marks_them_as_prompt_display_only`、`test_ai_strategy_research_pipeline_marks_legacy_workflow_steps_as_prompt_display_only`、`StrategyPage.test.ts` | `T1_PASS` | 证明旧字段未被伪装成执行图；真实 v2 stage 的实际执行仍须由独立 worker、stage attempt 和 artifact 证据证明。 |
| FR-PIPE-001～003、010～014；FR-SEC-002～004、006、010 | `test_ai_research_llm_gateway.py`、`test_ai_research_tool_broker.py`、`test_ai_research_artifact_broker.py`、`test_ai_research_canonical.py` | `T1_PASS` | 真实 Provider 调用、深层攻击语料和目标运行环境秘密边界。 |
| FR-TASK-001～009、NFR-REL-001～002 | `test_ai_research_task_runner.py`、`test_ai_research_stage_attempt.py`、`test_ai_research_workflow_worker.py`、`test_ai_research_generation_materialization.py`、`test_ai_research_worker_process.py`、`test_ai_research_artifact_broker.py`、`test_ai_research_deterministic_executor.py`、`test_ai_research_quota.py`、[HTTP_T1_EVIDENCE_20260905.md](HTTP_T1_EVIDENCE_20260905.md)、[EXPLORER_WORKER_DEPLOYMENT_CONTRACT_20260905.md](EXPLORER_WORKER_DEPLOYMENT_CONTRACT_20260905.md) | `T1_PASS` | 包含成功 output 的强制 binding/内容重验、旧无绑定 checkpoint recovery 拒绝、终态 retry 不可改 cursor、编码 URI/run request-hash 拒绝、heartbeat、poll loop/factory/default-disabled 边界及 typed proposal 的原子 candidate materialization。diagnostics factory 的 `GENERATE` 与 generic terminal success 均 fail-closed；正向 materialization 仅为 `MATERIALIZED_NOT_EXECUTED`，不证明有效策略。仍缺多进程/多数据库 crash takeover、部署的 evaluator/approval/sandbox 链、外部 Provider/runner reconciliation 和真实 Explorer 身份/IAM；HTTP 只覆盖同 key 的创建幂等和未启动外部副作用。 |
| FR-GATE-004～010、FR-SEC-005、011 | `test_ai_research_approval.py`、`test_ai_research_profile_migration.py`、`test_ai_research_capability_registry.py` | `T1_PASS` | 真实多角色身份、职责分离和 staging 审批演练。 |
| FR-GATE-011、AC-GOV-002 | `test_ai_research_governance.py`、`test_ai_research_orchestrator.py`、`test_ai_research_v2_api.py`、`EvidencePanel.test.ts` | `T1_PASS` | 服务器 allowlist 仅接受性能类目标；安全目标即使被写入 allowlist 也拒绝。允许项保持原 `FAIL/BLOCKED/NOT_RUN`，写入/撤销可审计且幂等；workbench 以 actor+scope 过滤并不提升 `evidence_class`，普通 DOM 不渲染自由文本。仍缺真实治理角色、独立审批和 staging 演练。 |
| FR-UI-001～009、011～014 | `TrustedResearchWorkbench.test.ts`、`EvidencePanel.test.ts`、`useAiResearchV2.test.ts`、`StrategyPage.test.ts`、`locale-completeness.test.ts`、`e2e/a11y/trusted_ai_research.spec.ts`、`e2e/a11y/trusted_ai_research.real.spec.ts`；静态 Chromium axe 全组；[HTTP_T1_EVIDENCE_20260905.md](HTTP_T1_EVIDENCE_20260905.md) | `T1_PARTIAL` | 候选 UI 的已认证真实 API E2E 与 axe 已覆盖基本链路；仍缺真实轮询、解锁设备上的人工焦点与辅助技术验证。 |
| MIG-001、MIG-004 的 schema/失败关闭部分 | `test_iteration_184_migrations.py`、`test_ai_research_v2_migration.py`、`tests/asset_research/test_migration.py`；临时 SQLite 与 PostgreSQL 17.7 `upgrade head → check`，PostgreSQL v2 `downgrade parent → upgrade head → check` | `T1_PARTIAL` | MySQL 升级、双写/影子读、运行中任务的生产回滚演练。 |

## 3. 本轮新增的闭环

1. **family 不再由客户端选择。** `ExperimentEpochRegistry` 从确认后的规范化假设中派生 family hash；epoch 创建 API 拒绝 `family_hash` 额外字段，浏览器 API 也不再发送该字段。
2. **同族留出预算不可重建。** 同一用户与 family 在数据库层唯一；完全相同、仍为 `OPEN` 的请求只返回原 epoch，任何已选择/揭盲/关闭 family 或不同请求均返回 `EXPERIMENT_EPOCH_FAMILY_ALREADY_EXISTS`。旧库若存在重复 family，迁移明确失败，要求先人工对账，绝不静默合并。
3. **预检失败可安全重试。** 页面保留同一不可变 hypothesis/dataset/epoch 启动绑定，重新请求服务端 precheck，而不是新建研究 family；过期或 `BLOCKED/FAIL` receipt 不会启动 run。
4. **页面前置条件收紧。** capability profile ID 与版本属于创建草稿的必填项；默认 information cutoff 晚于研究窗口，避免客户端时区导致的伪阻断。
5. **目标页面的静态浏览器闭环已执行。** 对生产构建 preview 的 `/investment/strategies`，Chromium fixture E2E 验证了草稿前置条件、确认、`BLOCKED → retry → PASS` 的同一预检绑定、键盘 Enter 操作及启动请求顺序；全量静态 axe 套件为 14 passed、1 skipped（显式真实环境用例默认跳过），serious/critical 为 0。该测试明确拦截 v2 API，故仅是 T1 静态浏览器证据。
6. **默认主题的关键对比度已修复。** 主色回退、侧栏激活态与策略分类选中态改用满足白字/前景色对比度的色值；修复前静态 axe 报出的 3 个 serious `color-contrast` 项现已清零。
7. **PostgreSQL schema drift 与 v2 schema rollback 已闭合。** 临时 PostgreSQL 17.7 验收库从基线全链升级到当前 head 后，`alembic check` 起初发现两个历史 paper-runtime 表的重复唯一性声明没有被 ORM 完整表达；模型现显式保留同列唯一约束和唯一索引，且新增回归测试。随后 v2 已成功降级到 `20260811_asset_research_task_leases`（v2 表不存在）并升级回 head、再次通过 `alembic check`。这只是空验收库的 schema 演练，不替代有运行中任务的 operational rollback。
8. **实际 HTTP/数据库协议链路已验证。** 一次性 PostgreSQL 17.7 与实际 FastAPI 进程完成了认证、草稿/确认、服务端 family hash、预检、幂等 run、脱敏和跨 owner 拒绝；另以唯一允许的 `NFR-PERF-001` 实测治理例外创建、敏感说明/控制项响应脱敏、撤销后保留原始 `BLOCKED` 结论。数据库回读证明没有 model invocation 或 stage attempt，因此不把队列受理误报为策略执行；独立默认配置进程还证明已认证 v2 写入返回稳定 `409 AI_RESEARCH_PROTOCOL_V2_DISABLED`。详见 [HTTP_T1_EVIDENCE_20260905.md](HTTP_T1_EVIDENCE_20260905.md)。
9. **真实候选 UI/API 链路已验证且可复跑。** `e2e/a11y/trusted_ai_research.real.spec.ts` 在显式隔离环境中以实际认证会话访问候选 Vite 的 `/investment/strategies`，没有拦截任何 v2 API；空库首次因缺少 capability profile 按设计 fail-closed 为 `BLOCKED`，随后仅登记 `protocol_v2` 能力的时限开发 profile。草稿、确认、dataset、epoch、`PASS` precheck、提交和 workbench 返回均成功：基线复跑为 1 passed（7.7 秒），最终代码复验为 1 passed（5.5 秒）；提交后 axe 的 serious/critical 为 0，页面和 v2 响应均无受控 URI。该证据仍不替代屏幕阅读器和人工焦点验证；详见 [HTTP_T1_EVIDENCE_20260905.md](HTTP_T1_EVIDENCE_20260905.md)。
10. **成功检查点接管不重放已闭合。** v2 worker 的服务端核心图为 `CLARIFY → GENERATE → terminal`；stage 的成功回执与 task/run 游标推进同一事务提交。若旧 lease 在此前后失效，新 lease 只会原子采纳同 task/stage 的既有成功回执，而不会重放该 stage 副作用；执行器伪造/越级的后继会以 `RESEARCH_STAGE_TRANSITION_INVALID` 失败。
11. **worker 生命周期、工件完整性与部署启动边界已收紧。** 每个 success 必须带有受控、绑定且重新哈希验证的输出；恢复拒绝旧无绑定 checkpoint，终态 retry 不能更改 cursor。poll loop 继续要求完整 `CLARIFY/GENERATE` map；deployment bootstrap 继续要求双 flag 和受限 factory。当前 `explorer:create_worker` 只写确定性诊断 receipt，`GENERATE` 失败，generic terminal success 也会被 candidate-contract guard 拦截。task event 的 sequence 不再从可能过期的 ORM 快照分配：支持 `UPDATE RETURNING` 的方言原子递增，其他方言在同一事务内锁定当前 task 后递增。相关回归现纳入 156 项 v2 后端契约；真实 MySQL/InnoDB 并发、Provider/身份、Evaluator/Sandbox 与 Docker/IAM 证据仍未完成，见 [EXPLORER_WORKER_DEPLOYMENT_CONTRACT_20260905.md](EXPLORER_WORKER_DEPLOYMENT_CONTRACT_20260905.md) 与 [IMPLEMENTATION_REVIEW_DISPOSITION_20260905.md](IMPLEMENTATION_REVIEW_DISPOSITION_20260905.md)。
12. **legacy workflow 语义已对齐。** 旧 `workflow_steps` 不再暗示会改变服务端执行图：schema、运行摘要、生成目标和配置页统一声明 `prompt_display_only`，并由 168 项后端服务回归、98 项前端页面回归、类型检查和构建验证；实际执行阶段仍只能由服务端 run/stage 记录证明。
13. **偏差不再是假 PASS 的旁路。** `governance-deviations` 仅允许服务器 policy 配置的 `NFR-PERF-###` 目标；服务端持久保存原状态、actor、scope、理由、风险、补偿控制和生效/到期/撤销时间，并以确定性 ID 处理同一 actor 的重试。安全目标会被拒绝；撤销不删除记录；工作台的查询再次绑定 actor，且治理摘要不改变 `evidence_class` 或原 hard gate。前端只展示目标、原状态和有效性，避免将自由文本作为常规页面内容；创建/撤销接口与工作台对 secret-like 理由和补偿控制均使用同一结构化脱敏，且没有返回 actor 或 scope。
14. **页面共用的 legacy data-trust PostgreSQL 503 已修复。** 空 PostgreSQL 验收库的实际 `/api/v1/data/trust/precheck` 曾因 `asset_specs` 的无时区 timestamp 接收了 aware UTC 默认值而映射为 `503`。四个相关模型现统一使用项目既有的 `utc_now_naive()` helper；新增默认值回归加上 data-trust/coverage 测试共 39 项通过，实际认证 HTTP 请求返回 `200/failed` 与 `RB0` 规格。这个 `failed` 是缺少覆盖行情的业务结论，不是对数据质量的 PASS，也不属于 v2 runner 或 T2/T3 证据。
15. **数据对象身份已从 URI/声明元数据收回服务器。** API/UI 只接受 opaque receipt，`DatasetRegistry` 经受控 resolver 生成逻辑对象、版本、摘要、大小、校验 receipt 和 snapshot identity。预检、任务创建与 materialization 在关键写入前重新核验，legacy snapshot 被标记 `LEGACY_UNVERIFIED` 并在严格路径拒绝；forward observation 也不再接收 raw URI。156 项 v2 回归包含同逻辑对象版本/摘要漂移、未知 receipt、URI 输入和 resolver 缺失等负例。该层为 in-memory resolver 的本地 T1 合同，不替代真实对象存储/IAM、不可变性或跨服务权限证明。
16. **生成回执可以被受控地物化，但没有被冒充为执行成功。** 只有 typed `ProposedGeneration` 经服务器验证 stage/run/data binding 与输出哈希后，才在单一事务内写 candidate、代码/参数/依赖/模型谱系 manifest、artifact binding 和 materialization receipt；任何对象漂移或无 resolver 均不写 candidate。generic terminal receipt 保持失败关闭，默认 diagnostics factory 仍不生成策略。正向结果明确为 `MATERIALIZED_NOT_EXECUTED`，尚未触发 Provider、Sandbox、回测、Evaluator、审批或前向市场试验。

## 4. 仍未完成、不能降级的环境门禁

| 场景 | 状态 | 阻断原因 |
| --- | --- | --- |
| AC-DEP-001～002、AC-SEAL-001 | `BLOCKED_ENVIRONMENT` | 没有真实的 Explorer/Evaluator 独立身份、队列、数据库/对象存储 credential。 |
| AC-SBX-001～005、AC-T2-003 | `BLOCKED_ENVIRONMENT` | 本机 Docker CLI 无法连接 Docker daemon；fixture runner 不能替代真实断网/资源/进程隔离。 |
| AC-MIG-001 的 SQLite/PostgreSQL fresh upgrade/schema-check 部分；空库 v2 schema rollback 部分 | `T1_PASS` | 临时 SQLite 与 PostgreSQL 17.7 库均完成 `upgrade head → check`；PostgreSQL 检出的历史 ORM metadata drift 已修复并有回归测试，且已完成 `downgrade parent → upgrade head → check`。 |
| AC-MIG-001 的 MySQL 部分；AC-MIG-003；AC-MIG-004 的运行中任务 staging 演练 | `BLOCKED_ENVIRONMENT` | 未取得安全的 MySQL 验收凭据，也未授权执行双写或运行中任务的 rollback drill。 |
| AC-NFR-001～003、AC-REP-001 | `NOT_RUN` | 缺少定义好的容量基线、目标部署和冷重放对象。 |
| AC-UI-001～007、AC-A11Y-001 的真实轮询/辅助技术部分 | `BLOCKED_ENVIRONMENT` | 候选 headless Chromium 已以真实身份/真实服务完成基本 UI/API 与 axe T1 链路；但 macOS 当前锁屏，无法完成真实轮询、屏幕阅读器与人工焦点证据。 |
| AC-T2-001～003、AC-T3-001～002 | `BLOCKED_ENVIRONMENT` | 没有获授权的真实数据/Provider、冻结后观察窗口或 staging 审批/回滚环境。 |

## 5. 决策

本地 T1 范围可作为默认关闭的实现候选证据；`IMPLEMENTATION_ACCEPTED` 和 `PROTOCOL_PRODUCTION_ENABLED` 仍均为 `NO-GO`。要改变该决定，必须按 [ACCEPTANCE.md](ACCEPTANCE.md) 取得每个上述阻断场景的原始证据与签署，不得用本文件替代。
