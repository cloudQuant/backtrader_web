# 迭代 196：可信 AI 策略研究流程实施计划

> 实施分支：`codex/iteration-196-ai-research-trust`  
> 需求基线：`docs/iterations/迭代196-改进优化ai生成策略流程/REQUIREMENTS.md`  
> 设计基线：`docs/iterations/迭代196-改进优化ai生成策略流程/DESIGN.md`  
> 验收基线：`docs/iterations/迭代196-改进优化ai生成策略流程/ACCEPTANCE.md`  
> 实施原则：P0 不降级；旧协议只读兼容；测试先行；缺失部署能力必须 fail-closed。

## 0. 目标与边界

将现有“生成—回测—迭代—模拟盘”链路升级为可预注册、可重放、可隔离、可否决的 v2 研究协议。实现不把单元测试或 SQLite 结果表述成生产隔离证据：`dev-single-process` profile 必须阻断真实密封评估、可信审批和生产启用。

旧 `investment_mandates`、`research_pipeline_events`、`ai_strategy_research_versions`、YAML 配置档案及历史 run 继续可读；任何旧 `out_of_sample` 只能显示为“迭代验证”，不得填充为 v2 密封留出 PASS。

## 1. 交付顺序与批次

| 批次 | 任务 | 对应切片 | 退出证据 |
| --- | --- | --- | --- |
| B0 | 0–2 | S0 | capability/profile、协议分流和旧路径只读事实可测 |
| B1 | 3–5 | S1 | 不可变假设、数据快照、候选冻结和任务身份落库 |
| B2 | 6–8 | S2 | trial、调用、工件、正确 DSR 与硬门可审计 |
| B3 | 9–10 | S3/S3b | 一次性密封授权、独立 evaluator、受限 runner 回执 |
| B4 | 11–13 | S4 | DB task、CAS lease、quota reservation、恢复/取消语义 |
| B5 | 14–15 | S5 | 证据工作台、确认/审批、竞态/可访问性/i18n |
| B6 | 16–18 | S6 | migration、影子读/双写、回滚与全量验收证据 |

每项均先添加一个能在现有基线上失败的测试，再实现最小行为使其通过；只在同一行为已绿后重构。每批结束运行该批 focused tests，再运行受到影响的既有 suite；B6 运行完整后端、前端 typecheck/test/build、迁移矩阵与可用的 T2/T3 环境验收。

## 2. 数据与协议基础

### 任务 0：建立 v2 术语、错误码、协议路由和 capability profile（B0）

**文件**

- 新增 `src/backend/app/services/research/protocol.py`
- 新增 `src/backend/app/services/research/capabilities.py`
- 新增 `src/backend/app/schemas/ai_research_v2.py`
- 新增 `src/backend/tests/test_ai_research_protocol.py`
- 新增 `src/backend/tests/test_ai_research_capabilities.py`

**测试先行**

1. 断言 v1 请求没有 `research_protocol_version=v2` 时只进入 legacy facade，且旧 OOS 显示 `ITERATION_VALIDATION`；
2. 断言 v2 请求缺 profile、profile 已过期、拓扑不满足 sealed/sandbox/approval 任一能力时返回结构化 `BLOCKED_TOPOLOGY_CAPABILITY`；
3. 断言 `dev-single-process` 永不签发真实 holdout authorization，不能由客户端布尔字段覆盖；
4. 断言 profile hash/version/expiry 进入 run、evaluation receipt 与 evidence package。

**实现**

- 定义 `ResearchProtocolVersion`、稳定错误码、`CapabilityProfile`、`CapabilityDecision` 和版本化 feature flag；
- capability 验证只接受服务端 registry 已签名且未过期的记录，不采信请求 payload；
- 在 API router 建立 `/ai-research/v2`，保留 `/ai-research/*` legacy route 和响应模型。

**验收**：AC-TRUTH-003、AC-DEP-001、AC-DEP-002、AC-PROTOCOL-001 的单元/API 合同部分。

### 任务 1：新增 v2 ORM 模型、迁移和 model 注册（B0/B1）

**文件**

- 新增 `src/backend/app/models/ai_research_v2.py`
- 修改 `src/backend/app/models/__init__.py`
- 新增实时 head 派生的 `src/backend/alembic/versions/<revision>_ai_strategy_research_trust.py`
- 新增 `src/backend/tests/test_ai_research_v2_models.py`
- 新增 migration smoke/round-trip 测试脚本和 SQLite/PostgreSQL/MySQL matrix 配置。

**测试先行**

1. `Base.metadata.create_all()` 包含每张 `ai_research_` 前缀 v2 表及唯一/检查约束；
2. hypothesis 版本、epoch selected candidate、holdout authorization、task idempotency、trial ordinal、quota reservation 不能写出重复或无效状态；
3. 三个 dialect migration 在升级、回读、降级/兼容路径中保留旧表；
4. migration 不修改/重命名历史 `20260718_ai_research_audit_schema.py`。

**实现**

- 模型覆盖 `hypothesis_versions`、`experiment_epochs`、`dataset_snapshots`、`runs`、`tasks`、`trials`、`model_invocations`、`evaluations`、`holdout_authorizations`、`gate_decisions`、`human_decisions`、`governance_decisions`、`stage_attempts`、`artifacts`、`quota_buckets`、`quota_reservations` 与 v2 append event；
- 使用 `DateTime(timezone=True)`、owner/user indexes、FK `ondelete=RESTRICT`、稳定 status enum/check constraints；
- 仅向旧 strategy version 增加兼容字段，不重命名或回填其历史结论。

**验收**：FR-HYP-001、FR-DATA-001、FR-LEDGER-001、FR-TASK-001、FR-QUOTA-001、MIG-001/002/006，AC-MIG-001/002/006。

### 任务 2：建立通用规范化、内容寻址和脱敏库（B1）

**文件**

- 新增 `src/backend/app/services/research/canonical.py`
- 新增 `src/backend/app/services/research/redaction.py`
- 新增 `src/backend/tests/test_ai_research_canonical.py`
- 新增 `src/backend/tests/test_ai_research_redaction.py`

**测试先行**

1. key 顺序、空值、timezone、decimal 表示差异不改变 canonical hash；受控字段变更必改变 hash；
2. recursive `password/token/secret/api_key/gateway credential`、嵌套 list/JSON/URL query 均不会出现在模型输入、日志、普通 API 或导出；
3. 不可信文本、路径/URL/tool 参数只能通过 typed allowlist，不能升级 role 或覆盖 gate。

**实现**

- 规范化 JSON（UTC、sorted keys、明确 null policy、decimal string policy）+ SHA-256；
- immutable content-addressed artifact descriptor，普通 API 仅暴露安全 ID/hash/size/media type；
- 单一递归 secret classifier/redactor，配合 taint metadata 和安全事件。

**验收**：AC-HYP-002、AC-LLM-001、AC-PRIV-001、AC-INJECTION-001/002、AC-TENANT-002。

## 3. 不可变研究身份、数据与候选

### 任务 3：实现 Hypothesis Registry 与确认语义（B1）

**文件**

- 新增 `src/backend/app/services/research/hypothesis_registry.py`
- 新增 `src/backend/app/api/strategy/research.py`
- 修改 `src/backend/app/api/strategy/__init__.py`
- 新增 `src/backend/tests/test_ai_research_hypothesis_registry.py`
- 新增 API tests `src/backend/tests/test_ai_research_v2_api.py`

**测试先行**

1. parse/create 只生成 `DRAFT`，确认必须来自认证 user；
2. 确认缺 research question、asset/time window、cost/execution、primary metric、falsification、search space 或 data policy 时拒绝；
3. 确认后 PATCH 不可改变 payload/hash；修改生成新版本并令旧投影 `SUPERSEDED`；
4. request hash 与确认 hash 不同、preflight stale 或跨租户引用时 409/404；
5. legacy mandate 能以显式 `legacy_source` 只读关联，不能假装 v2 CONFIRMED。

**实现**

- registry 是 hypothesis 状态唯一 writer；事务写 confirmation audit/event；
- API 划分 parse、draft update、confirm、read，不接收客户端 `confirmed_by`；
- run submit 引用 confirmed hypothesis version + request/preflight hash。

**验收**：FR-HYP-001～005，AC-HYP-001～005、AC-UI-002、AC-TENANT-001。

### 任务 4：实现 Dataset Policy/Snapshot Registry 与 PIT 分区（B1）

**文件**

- 新增 `src/backend/app/services/research/dataset_registry.py`
- 新增 `src/backend/tests/test_ai_research_dataset_registry.py`
- 修改适配层以复用 `asset_research/evaluation.py` 的 purge/embargo split。

**测试先行**

1. discovery、iteration validation、sealed holdout 边界时序不重叠，PIT/vintage/available-at 违规被拒绝；
2. forward observation 只能在 candidate frozen 后，不能把历史区间重命名为 forward；
3. Explorer 取数据时永远拿不到 sealed raw URI/token；
4. 交易成本、slippage、frequency、timezone、continuous contract / adjustment policy 缺证即 BLOCKED。

**实现**

- 版本化 dataset policy + immutable snapshot/fold manifest/artifact binding；
- client/read model 永不序列化 sealed storage URI；
- 所有 evaluation input 通过 snapshot ID/hash，禁止自由日期范围绕过。

**验收**：FR-DATA-001～006，AC-DATA-001～004、AC-SEAL-001、AC-SEAL-006。

### 任务 5：实现 Candidate Registry、epoch 和冻结（B1）

**文件**

- 新增 `src/backend/app/services/research/candidate_registry.py`
- 新增 `src/backend/tests/test_ai_research_candidate_registry.py`
- 修改 `src/backend/app/services/ai_strategy_research_version_service.py` 的 v2 adapter（保留 legacy 行为）。

**测试先行**

1. candidate hash 覆盖 code/params/dependency/environment/dataset/cost/fold；freeze 后任一变动被拒绝；
2. 一个 epoch 只能锁定一个 selected candidate，不能靠新 ID 重用 sealed budget；
3. 未通过 explorer hard gate、无完整 trial、或 non-confirmed hypothesis 都无法 freeze；
4. sealed rejection 不会回退 candidate 到 mutable，也不会创建同 epoch 的继续优化 command。

**实现**

- content hash、freeze receipt、immutable artifacts；
- epoch 的 selected/disclosed/closed 转移加 CAS/unique enforcement；
- legacy version 以 `legacy_evidence_class` 读模型展示。

**验收**：FR-CAND-001～006，AC-SEAL-002/003/005、AC-SEARCH-001、AC-PROTOCOL-001。

## 4. 账本、统计与硬门

### 任务 6：实现 append-only Experiment Ledger 与 artifact broker（B2）

**文件**

- 新增 `src/backend/app/services/research/experiment_ledger.py`
- 新增 `src/backend/app/services/research/artifact_broker.py`
- 新增 `src/backend/tests/test_ai_research_experiment_ledger.py`

**测试先行**

1. 成功、失败、取消、超时、无效市场尝试均创建 trial；无删除/覆盖路径；
2. 试验计数只使用 `counts_as_market_trial` 有理由的记录；技术 retry 不被静默当作市场 trial；
3. artifact path traversal、symlink、oversize、malicious serialization 和伪 MIME 被拒绝/隔离；
4. correction 追加事件不能篡改旧 trial hash。

**实现**

- transactional outbox + stage attempt idempotency；
- append event hash/sequence；受控 artifact URI 经 broker 解析；
- ledger 生成返回序列、参数、成本与运行收据完整 manifest。

**验收**：FR-LEDGER-001～006，AC-LEDGER-001/002、AC-SBX-005、AC-AUD-001。

### 任务 7：修复 DSR 语义、实现 Promotion Gate Engine（B2）

**文件**

- 修改 `src/backend/app/services/asset_research/evaluation.py`
- 新增 `src/backend/app/services/research/statistics.py`
- 新增 `src/backend/app/services/research/promotion.py`
- 新增 `src/backend/tests/test_ai_research_statistics.py`
- 新增 `src/backend/tests/test_ai_research_promotion.py`

**测试先行**

1. independent oracle 以跨 trial Sharpe 方差（不是候选 returns 方差）对照 DSR；
2. 相同 candidate returns 但不同真实 trial count 必产生不同 DSR/gate；
3. 缺 returns artifact、count、dataset/cost/environment 或 profile evidence 一律 `UNKNOWN/BLOCKED`；
4. AI review/quality score 永远无法把任何 hard gate 从 FAIL/UNKNOWN 改为 PASS；
5. policy version 变更/证据 hash 改变使 eligibility/approval 过期而不删除旧决定。

**实现**

- 适配 `purgedcv.deflated_sharpe_ratio` 的正确参数合同；
- hard gate all-pass policy、evidence input hash、deterministic error catalog；
- P1 PBO/CSCV 留接口但不宣称实现。

**验收**：FR-STAT-001～006、FR-GATE-001～004，AC-STAT-001～004、AC-AI-GATE-001、AC-APP-003。

### 任务 8：统一 LLM Gateway、模型谱系与工具调解（B2）

**文件**

- 新增 `src/backend/app/services/research/llm_gateway.py`
- 新增 `src/backend/app/services/research/tool_broker.py`
- 新增 `src/backend/tests/test_ai_research_llm_gateway.py`
- 新增 `src/backend/tests/test_ai_research_tool_broker.py`

**测试先行**

1. 所有 generator/repair/challenger/fallback path 都通过 gateway，直接 provider 调用被测试拒绝；
2. requested/resolved model revision、request ID、sampling、input/output hashes、tokens/cost、origin/fallback chain 全部落账；
3. alias drift 可见且冻结 run 不因 alias 改变重写谱系；
4. prompt injection 不可请求 secret/sealed data/shell/network/approval，tool schema/ownership 再次鉴权。

**实现**

- gateway 接受已脱敏的 typed input，强制 quota reservation；
- origin 标明 LLM/RAG/template/repair/fallback，不把 deterministic template 伪装成 LLM；
- tool broker only allowlisted operation and resource scope。

**验收**：FR-LLM-001～005、FR-SEC-001～004，AC-TRUTH-001/002、AC-LLM-001/002、AC-INJECTION-001/002。

## 5. 密封评估和受限执行

### 任务 9：实现一次性 Holdout Authorization 与 Independent Evaluator（B3）

**文件**

- 新增 `src/backend/app/services/research/holdout_authorization.py`
- 新增 `src/backend/app/services/research/independent_evaluator.py`
- 新增 `src/backend/tests/test_ai_research_holdout_authorization.py`
- 新增 `src/backend/tests/test_ai_research_independent_evaluator.py`

**测试先行**

1. Explorer identity 直接、间接、猜测 ID 均无法读 sealed data/result；拒绝本身留安全/ledger event；
2. 只有 frozen selected candidate + active profile 可签发 opaque authorization；原 token 不出普通日志；
3. authorization 仅一次、绑定 epoch/candidate/snapshot/policy/evaluator identity，重复/过期/错 worker 失败；
4. result 只写 evaluation/gate evidence，禁止写 candidate/prompt/LLM/Explorer queue；
5. holdout failed/unknown 后 epoch close，不产生变体改进 command。

**实现**

- evaluator command 只传 opaque refs；受控 credential/queue adapter 接口；
- enforce role/service identity in service + integration harness; deployment tests verify actual rejection paths；
- record evaluator image/policy/profile receipt。

**验收**：FR-SEAL-001～007，AC-SEAL-001～005、AC-DEP-001/002。

### 任务 10：实现独立 Sandbox Runner 和同工件执行合同（B3）

**文件**

- 新增 `src/backend/app/services/research/sandbox_runner.py`
- 新增 `src/backend/app/services/research/sandbox_policy.py`
- 新增 `src/backend/tests/test_ai_research_sandbox_runner.py`
- 新增 real-container harness under `src/backend/tests/integration/` and signed image/policy manifests.

**测试先行**

1. runner request 必有 approved image digest, policy version, frozen artifact hash, bounded resources and reservation receipt；
2. no network/read-only input/output-only artifact contract is asserted in fake and real-container test interfaces；
3. timeout/cancel kills process group and writes failure code; untrusted output cannot escape artifact broker；
4. preflight/train/validation/sealed/paper receipts reference the same code/dependency/execution-model hashes unless deliberate version fork starts a new candidate.

**实现**

- API/backend never mount Docker socket; implement runner client interface and separate runner deployment contract；
- restrict CPU/memory/PID/wall/output/network/filesystem; persist image/policy/worker receipt；
- production profile remains blocked until real-container AC-SBX tests execute in target environment.

**验收**：FR-SBX-001～006，AC-SBX-001～005、AC-T2-003。

## 6. 持久任务与预算

### 任务 11：实现 Durable Research Task Runner（B4）

**文件**

- 新增 `src/backend/app/services/research/task_repository.py`
- 新增 `src/backend/app/services/research/task_runner.py`
- 新增 `src/backend/tests/test_ai_research_task_runner.py`
- 修改 `src/backend/app/services/ai_strategy_research_task_manager.py` 为 legacy read-only adapter/feature-routed facade。

**测试先行**

1. 20 个同 user/idempotency key/same hash 并发 submit 只有一个 task/run；同 key different hash 409；
2. 双 worker CAS claim 只有一个 lease owner；heartbeat/terminal update 携带 lease token；
3. SIGKILL/expired lease 恢复只重放安全 checkpoint，外部副作用无重复有效结果；
4. cancel-complete race 仅一个终态；历史不被 50 条 snapshot 截断；
5. four aggregates 各由指定 owner 写入，orchestrator 通过 outbox/commands 协调。

**实现**

- 按 `AssetResearchTaskRunner` 的 CAS/lease 结构复用但修正 recovery/side-effect readback；
- v2 DB tables 是权威，workspace JSON 只作摘要缓存；
- cancel intent、stage cursor、retry_of、trace ID、outbox and receipt binding。

**验收**：FR-TASK-001～007，AC-TASK-001～006、AC-FSM-001、AC-AUD-001。

### 任务 12：实现原子 Quota Reservation 与 reconciler（B4）

**文件**

- 新增 `src/backend/app/services/research/quota.py`
- 新增 `src/backend/app/services/research/quota_reconciler.py`
- 新增 `src/backend/tests/test_ai_research_quota.py`

**测试先行**

1. 多资源预留必须 all-or-none，20 并发不能超 hard limit/concurrency limit；
2. 同 stage/idempotency key 回到同一 reservation，不会重复扣减；
3. 无 reservation/fencing token 的 LLM/sandbox/evaluator command 不执行；
4. lease 过期但 external operation unknown 进入 `RECONCILING/BLOCKED_UNKNOWN`，绝不静默 release；
5. confirmed no-op/terminated internal runner 才能 release，旧 token/repeated settle/release fail。

**实现**

- stable-order row lock/CAS and version/fencing token; SQLite short write semantics; provider operation ID readback;
- bucket aggregates and reservation lifecycle auditable; conservative settlement on uncertainty。

**验收**：FR-QUOTA-001～006，AC-QUOTA-001/002、AC-SCHED-001。

### 任务 13：接入 v2 orchestration 与 legacy compatibility（B4）

**文件**

- 新增 `src/backend/app/services/research/orchestrator.py`
- 修改 `src/backend/app/services/ai_strategy_research_service.py`
- 修改 `src/backend/app/api/strategy/base.py`（仅 feature-routed compatibility seams）
- 新增 end-to-end API service tests.

**测试先行**

1. v2 workflow stages 真正执行所配置步骤/receipts；legacy work flow unaffected;
2. v2 run refuses stale confirmed hash/data preflight/invalid profile;
3. output read model can combine v1 history and v2 records, visibly labelling evidence class;
4. no v2 route writes legacy task snapshots as authoritative state.

**实现**

- no universal updater: use registry/task/evaluator/promotion command boundaries;
- expand service only as routing facade; keep legacy public endpoint contracts.

**验收**：AC-TRUTH-003、AC-PROTOCOL-001、AC-MIG-003/004/006。

## 7. 决定、前端与迁移

### 任务 14：实现服务端审批、前向观察和 prepare hard gate（B5）

**文件**

- 新增 `src/backend/app/services/research/approval.py`
- 新增 `src/backend/app/services/research/forward_observation.py`
- 新增 `src/backend/tests/test_ai_research_approval.py`
- 修改 legacy live handoff adapters only to enforce protocol branching.

**测试先行**

1. client `approver`、`passed`、disabled gate 均不能影响 server decision; actor comes from auth context;
2. multi-actor separation/RBAC and single-actor risk acknowledgement enact policy; AI never self-approves;
3. evidence/policy hash changes expire approval; prepare never equals running/order submit;
4. forward observations only append after freeze and meet time/event/data quality policy.

**实现**

- append human decision/challenge/governance deviation; policy ignores deviation when computing original gate;
- transition only after all hard gate PASS and explicit authenticated decision.

**验收**：FR-APP-001～006、FR-FWD-001～004、AC-GATE-001、AC-APP-001～005、AC-T3-001/002。

### 任务 15：拆分前端 Evidence Workbench 和可信交互（B5）

**文件**

- 新增 `src/frontend/src/components/aiResearch/`：`HypothesisPanel.vue`、`DataPanel.vue`、`LedgerPanel.vue`、`EvidencePanel.vue`、`DecisionPanel.vue`
- 新增 `src/frontend/src/composables/useAiResearchV2.ts`
- 修改 `src/frontend/src/views/investment/Strategies.vue`（按实际现有路径校正）
- 修改 API client/types/i18n；新增 Vitest/Playwright tests。

**测试先行**

1. 五区块显示 pre-registration、dataset/partition、full ledger、PASS/FAIL/UNKNOWN evidence 和 human decision；old run 标记 legacy;
2. request hash/preflight/confirmation mismatch disables UI and server rejects intercepted submit;
3. cancel A then start B, late A response cannot write B; route/unmount abort and response identity guards;
4. uncertain mutating outcome supports idempotency lookup/retry instead of double submit;
5. real Element Plus components resolve; console errors/warnings are zero for affected journeys; keyboard/focus/ARIA and i18n error codes covered.

**实现**

- request scoped `AbortController`, task/run tokens, pinia/composable state isolation;
- never render secrets/sealed URI/host path; actors/evidence hash server supplied;
- typed API schemas and error catalog mapped to localized user action.

**验收**：FR-UI-001～009、AC-UI-001～007、AC-A11Y-001、AC-I18N-001。

### 任务 16：配置档案安全迁移、双写/影子读和旧运行只读（B6）

**文件**

- 修改 `src/backend/app/services/ai_strategy_research_config_profiles.py`
- 新增 `src/backend/app/services/research/profile_migration.py`
- 新增 migration/audit tests and runbook scripts.

**测试先行**

1. user A/B cross-resource profile/hypothesis/run/candidate/evidence/approval read/write/delete returns non-enumerating 403/404;
2. old YAML containing credentials cannot migrate into v2; rejected fields are listed safely; only `credential_ref/gateway_profile_id` persists;
3. shadow read compares legacy/v2 derived read model but no old evidence gains sealed PASS; dual write divergence metric/fail policy works;
4. feature rollback prevents new v2 submits safely while existing v2 records stay readable and auditable.

**实现**

- user-scoped DB profiles + allowlisted import/export; data migration log and rollback switch;
- stage rollout feature flags and migration state/metrics.

**验收**：AC-TENANT-001/002、AC-MIG-003～006、AC-PROTOCOL-001。

### 任务 17：可复现研究包、观测与性能（B6）

**文件**

- 新增 `src/backend/app/services/research/evidence_package.py`
- 新增 `src/backend/tests/test_ai_research_reproducibility.py`
- 修改 research metrics/health endpoints and dashboards/runbooks.

**测试先行**

1. cold replay reads frozen code/dependencies/data snapshot/cost/fold/seed/execution/gate inputs and reproduces declared deterministic result;
2. third-party LLM generation only claims lineage, not byte-identical generation;
3. query and append latency tests use target data volumes; metrics have low-cardinality labels and never secrets;
4. audit/dependency evidence missing blocks promotion and emits traceable alert.

**实现**

- evidence package hash references canonical artifacts and profile; signed/controlled export only after redaction;
- metrics for ledger completeness, unauthorized attempts, duplicate transition, quota unknown, profile expiry, gate blocks and replay result.

**验收**：AC-REP-001、AC-NFR-001～003、AC-AUD-001、AC-EVIDENCE-001。

### 任务 18：正式验收、真实环境证据和发布判定（B6）

**执行清单**

1. 后端 focused + full suite: `/Users/yunjinqi/opt/anaconda3/bin/conda run -n base python -m pytest`；
2. 前端: `npm run typecheck`, `npm run test -- --run`, `npm run build`, affected Playwright journeys；
3. Alembic head, upgrade/downgrade/upgrade on SQLite, PostgreSQL, MySQL; readback constraints;
4. concurrency fault injection, worker kill/recovery, cancel/complete, quota external unknown;
5. real separation rejection tests for the target capability profile; real container no-network/filesystem/resource tests;
6. T2 real data/provider and T3 forward/staging approval only with authorized non-test credentials/environments; otherwise report explicit `BLOCKED_ENVIRONMENT`, not PASS;
7. execute rollback/feature-flag drill, record G0–G5 independently, and attach evidence manifest including commit/image/config/profile hashes.

**Completion rule**

`IMPLEMENTATION_ACCEPTED` requires all P0 automated/contract checks and migration proof. `PROTOCOL_PRODUCTION_ENABLED` additionally requires target deployment profile rejection evidence, sandbox proof, authorized T2/T3 evidence, grey rollout and rollback drill. Candidate promotion is a separate decision. No baseline green suite substitutes for these conditions.

## 8. Review checkpoints

After B1, B2, B4, B5 and B6: inspect `git diff --check`, focused tests, affected legacy tests, exact migration head, and requirements traceability. Before a commit: use a task-owned allowlist, inspect `git diff --name-status` and preserve all unrelated user changes. Before final completion: request independent code review and re-run full verification after its fixes.
