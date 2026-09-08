# 迭代 196 逐项追踪矩阵

> 状态：独立评审后建立的目标追踪基线；当前唯一 head 为 `20260908_ai_research_approval_authority`。2026-09-08 本地回归已冻结在 [当前六 worker 记录](REGRESSION_6_WORKERS_20260908.md)，但表中逐项 AC 仍须按主体、环境、真实依赖和负例分别回填，不能因横向回归批量改为 `PASS`。一次性 PostgreSQL 与实际 FastAPI 的历史隔离 HTTP T1 证据见 [HTTP_T1_EVIDENCE_20260905.md](HTTP_T1_EVIDENCE_20260905.md)，不改变当前逐项环境状态。对象 receipt 的本地重验未证明真实对象存储/IAM；candidate/evaluation/approval/sandbox 也尚无部署 worker/API 的生产端到端证据。
> 2026-09-07 历史补充：当时 claim/start 候选以互斥的六 worker 功能通道与串行性能通道覆盖 5,708 cases，其中 5,579 passed、129 skipped、0 failure/error，详见 [历史回归记录](REGRESSION_6_WORKERS_20260907.md)。该数字只属于当时冻结源码。
> 2026-09-07 holdout request 前置切片：11 文件身份下的 150 项六 worker T1 证明 server-owned command 的本地合同，详见 [HOLDOUT_REQUEST_COMMAND_20260907.md](HOLDOUT_REQUEST_COMMAND_20260907.md)。请求提交时为 `QUEUED/REQUEST_HOLDOUT` 且明确 0 authorization、0 evaluation；该历史范围不被后续证据倒填。
> 2026-09-07 holdout claim/start 切片：184 项六 worker focused T1 证明内部 claim-time 本地合同——恰好一个已消费的 JIT authorization、一个 `RUNNING` evaluation 和 generation-fenced lease；最终 6 worker 全量回归已重跑为 0 failure/error，详见 [HOLDOUT_CLAIM_START_20260907.md](HOLDOUT_CLAIM_START_20260907.md)。实际 sealed calculation、artifact checkpoint/finalize、独立 queue/IAM 与真实多数据库竞争仍未执行，因此下表任何 AC/需求行均不改为 `PASS`。
> 2026-09-08 增量：需求和验收已补入 terminal command graph、外部执行 journal/UNKNOWN 对账、默认关闭的 holdout worker、command-scoped evidence package v2、审批授权/拒绝围栏及浏览器安全投影。相关本地自动化即使通过，也只形成组件合同证据；真实 PostgreSQL/MySQL/MariaDB、独立 queue/IAM/object storage/Evaluator、受支持 Node 20 与 authenticated 当前 UI 仍须分别验收，不能批量回填本表为 `PASS`。
> 需求权威：[REQUIREMENTS.md](REQUIREMENTS.md)
> 设计权威：[DESIGN.md](DESIGN.md)
> 验收权威：[ACCEPTANCE.md](ACCEPTANCE.md)

## 1. 使用规则

- 每个 FR、NFR、MIG ID 必须且只能在本矩阵出现一次；需求族区间不能替代逐项映射；
- P0 行若缺设计组件、具名 AC 或实施切片，G0 必须 FAIL；
- P1 行允许 `DEFERRED_P1`，但仍须预定义验收场景，UI/API 不得宣称已实现；
- 本矩阵只证明合同闭环，不证明功能已实现、真实研究有效或生产可用；
- 实现 PR 必须引用本表中的 requirement ID、对应 AC 和 evidence 路径。

## 2. 功能需求

| Requirement | Priority | 设计落点 | 具名验收 | 最早切片/发布边界 | 当前状态 |
| --- | --- | --- | --- | --- | --- |
| FR-HYP-001 | P0 | Hypothesis Registry；DESIGN 4.2.1/5.1 | AC-HYP-001 | S1 / Foundation | NOT_RUN |
| FR-HYP-002 | P0 | Hypothesis Registry canonical payload；DESIGN 5.1/9.4 | AC-HYP-005 | S1 / Foundation | NOT_RUN |
| FR-HYP-003 | P0 | Hypothesis confirmation audit；DESIGN 4.2.1/5.1 | AC-HYP-001 | S1 / Foundation | NOT_RUN |
| FR-HYP-004 | P0 | Canonical request hash；DESIGN 5.1/9.4 | AC-HYP-002 | S1 / Foundation | NOT_RUN |
| FR-HYP-005 | P0 | Hypothesis version/parent diff；DESIGN 4.2.1/5.1 | AC-HYP-002 | S1 / Foundation | NOT_RUN |
| FR-HYP-006 | P0 | Post-hoc artifact boundary；DESIGN 5.12/11.3 | AC-HYP-003 | S1 / Cut A | NOT_RUN |
| FR-HYP-007 | P0 | Dataset precheck + API precondition；DESIGN 8.2/9.4 | AC-HYP-004、AC-UI-002 | S1 / Cut A | NOT_RUN |
| FR-HYP-008 | P1 | Research memory/similarity service（后续） | AC-MEM-001 | P1 | DEFERRED_P1 |
| FR-DATA-001 | P0 | Dataset Policy/Snapshot；DESIGN 5.3/6.1 | AC-DATA-002、AC-T3-001 | S1 / Cut A | NOT_RUN |
| FR-DATA-002 | P0 | Snapshot manifest；DESIGN 5.3 | AC-DATA-002 | S1 / Cut A | NOT_RUN |
| FR-DATA-003 | P0 | Fold/purge/embargo；DESIGN 6.1 | AC-DATA-002、AC-DATA-003 | S1 / Cut A | NOT_RUN |
| FR-DATA-004 | P0 | Explorer permission boundary；DESIGN 3.1～3.3 | AC-DEP-001、AC-SEAL-001 | S3 / Cut A | NOT_RUN |
| FR-DATA-005 | P0 | Holdout Authorization；DESIGN 5.10 | AC-SEAL-002、AC-SEAL-003 | S3 / Cut A | NOT_RUN |
| FR-DATA-006 | P0 | Holdout access audit；DESIGN 5.10/5.13 | AC-SEAL-001、AC-SEAL-003 | S3 / Cut A | NOT_RUN |
| FR-DATA-007 | P0 | Zero-feedback information flow；DESIGN 3.1/7.2 | AC-SEAL-004、AC-INJECTION-001 | S3 / Cut A | NOT_RUN |
| FR-DATA-008 | P0 | Candidate/authorization invalidation；DESIGN 4.2.3/5.9～5.10 | AC-SEAL-002、AC-SEAL-005 | S3 / Cut A | NOT_RUN |
| FR-DATA-009 | P0 | Legacy evidence projection；DESIGN 12.2 | AC-SEAL-006 | S0 / Cut A | NOT_RUN |
| FR-DATA-010 | P0 | Experiment Epoch holdout budget；DESIGN 5.2/5.9 | AC-SEAL-003、AC-SEAL-005 | S3 / Cut A | NOT_RUN |
| FR-DATA-011 | P0 | Production data completeness；DESIGN 6.1/6.4 | AC-DATA-001 | S1 / Cut A | NOT_RUN |
| FR-DATA-012 | P0 | Execution Model；DESIGN 6.4/10.1 | AC-DATA-004、AC-SBX-004 | S3b / Cut A | NOT_RUN |
| FR-DATA-013 | P0 | Independent Evaluator/capability boundary；DESIGN 3.2～3.3 | AC-DEP-001、AC-DEP-002、AC-SEAL-001 | S3 / Cut A | NOT_RUN |
| FR-DATA-014 | P0 | Terminal holdout command graph；DESIGN 5.11.1/7.3 | AC-SEAL-007、AC-EVIDENCE-002 | S3 / Cut A | NOT_RUN |
| FR-LEDGER-001 | P0 | Experiment Ledger/Trial FSM；DESIGN 5.7 | AC-LEDGER-001 | S2 / Foundation | NOT_RUN |
| FR-LEDGER-002 | P0 | Trial identity/provenance；DESIGN 5.7/5.12 | AC-LEDGER-001、AC-LEDGER-002 | S2 / Foundation | NOT_RUN |
| FR-LEDGER-003 | P0 | Append-only event/correction；DESIGN 5.7/5.13 | AC-LEDGER-001、AC-AUD-001 | S2 / Foundation | NOT_RUN |
| FR-LEDGER-004 | P0 | Search counting contract；DESIGN 6.2 | AC-LEDGER-002 | S2 / Foundation | NOT_RUN |
| FR-LEDGER-005 | P0 | DSR input contract；DESIGN 6.3 | AC-STAT-001、AC-STAT-003 | S2 / Foundation | NOT_RUN |
| FR-LEDGER-006 | P0 | DSR adapter + production dependency；DESIGN 6.3/7.2 | AC-STAT-001 | S2 / Cut A | NOT_RUN |
| FR-LEDGER-007 | P0 | Independent hard-gate statuses；DESIGN 6.4 | AC-STAT-004 | S2 / Foundation | NOT_RUN |
| FR-LEDGER-008 | P0 | Versioned Promotion Policy；DESIGN 4.2.4/6.3 | AC-STAT-003、AC-GATE-001、AC-APP-003 | S2 / Cut A | NOT_RUN |
| FR-LEDGER-009 | P1 | CSCV/PBO；DESIGN 6.2～6.3 | AC-STAT-005 | P1 | DEFERRED_P1 |
| FR-LEDGER-010 | P1 | Effective trial count；DESIGN 6.2 | AC-STAT-002、AC-STAT-005 | P1 | DEFERRED_P1 |
| FR-PIPE-001 | P0 | Explorer search-space/budget policy；DESIGN 7.1/7.3 | AC-SEARCH-001、AC-QUOTA-001 | S2 / Foundation | NOT_RUN |
| FR-PIPE-002 | P0 | Model Invocation Ledger；DESIGN 5.8/7.1 | AC-TRUTH-001、AC-TRUTH-002、AC-LLM-001、AC-LLM-002 | S2 / Foundation | NOT_RUN |
| FR-PIPE-003 | P0 | Artifact/environment identity；DESIGN 5.12/10.1 | AC-SBX-004、AC-REP-001 | S3b / Cut A | NOT_RUN |
| FR-PIPE-004 | P0 | Candidate Registry/freeze；DESIGN 4.2.3/5.6 | AC-SEAL-002 | S1 / Cut A | NOT_RUN |
| FR-PIPE-005 | P0 | Evaluator authority boundary；DESIGN 3.1～3.3 | AC-SEAL-001、AC-SEAL-004 | S3 / Cut A | NOT_RUN |
| FR-PIPE-006 | P0 | Evaluation write boundary；DESIGN 5.9/7.3 | AC-SEAL-004、AC-FSM-001 | S3 / Cut A | NOT_RUN |
| FR-PIPE-007 | P0 | Robustness/cost/capacity gates；DESIGN 6.4 | AC-DATA-004、AC-STAT-004 | S2 / Cut A | NOT_RUN |
| FR-PIPE-008 | P0 | AI challenge is auxiliary only；DESIGN 6.4/10.2 | AC-AI-GATE-001 | S2 / Cut A | NOT_RUN |
| FR-PIPE-009 | P1 | Challenger model/method；DESIGN 10.2 | AC-CHALLENGER-001 | P1 | DEFERRED_P1 |
| FR-PIPE-010 | P0 | Research LLM Gateway；DESIGN 7.1/7.3 | AC-LLM-001、AC-PRIV-001、AC-QUOTA-002 | S2 / Foundation | NOT_RUN |
| FR-PIPE-011 | P0 | Origin/transformation/fallback provenance；DESIGN 5.8 | AC-TRUTH-001、AC-TRUTH-002 | S2 / Cut A | NOT_RUN |
| FR-PIPE-012 | P0 | Validated server execution graph or explicit prompt/display-only semantics；DESIGN 7.1/8.2 | AC-TRUTH-003 | S0/S2 / Cut A | NOT_RUN |
| FR-PIPE-013 | P0 | Cross-stage artifact/execution semantics；DESIGN 5.12/10.1 | AC-SBX-004、AC-REP-001 | S3b / Cut A | NOT_RUN |
| FR-PIPE-014 | P0 | Aggregate FSM/transaction owner；DESIGN 4 | AC-FSM-001 | S1～S4 / Cut A | NOT_RUN |
| FR-TASK-001 | P0 | Durable Task Runner；DESIGN 5.5/7.1 | AC-TASK-001、AC-TASK-003 | S4 / Foundation | NOT_RUN |
| FR-TASK-002 | P0 | Request idempotency；DESIGN 5.5/8.1 | AC-TASK-001 | S4 / Foundation | NOT_RUN |
| FR-TASK-003 | P0 | Lease/heartbeat/CAS；DESIGN 4.2.2/5.5 | AC-TASK-002、AC-TASK-003 | S4 / Foundation | NOT_RUN |
| FR-TASK-004 | P0 | Stage cursor/checkpoint；DESIGN 5.5/5.12/7.3 | AC-TASK-003、AC-TASK-007、AC-FSM-001 | S4 / Foundation | NOT_RUN |
| FR-TASK-005 | P0 | Persistent cancellation；DESIGN 4.2.2/5.5 | AC-TASK-004 | S4 / Foundation | NOT_RUN |
| FR-TASK-006 | P0 | Side-effect idempotency；DESIGN 7.3 | AC-TASK-005 | S4 / Cut A | NOT_RUN |
| FR-TASK-007 | P0 | Browser poll identity；DESIGN 9.2～9.3 | AC-UI-003、AC-UI-004 | S5 / Cut A | NOT_RUN |
| FR-TASK-008 | P0 | Cursor pagination/durable history；DESIGN 5.4～5.5/8.1 | AC-TASK-006 | S4 / Foundation | NOT_RUN |
| FR-TASK-009 | P0 | Atomic budget/quota reservation；DESIGN 5.15/7.1/7.3 | AC-QUOTA-001、AC-QUOTA-002 | S4 / Cut A | NOT_RUN |
| FR-TASK-010 | P1 | Priority/pause/fair scheduling；DESIGN 7.1 | AC-SCHED-001 | P1 | DEFERRED_P1 |
| FR-TASK-011 | P0 | External operation journal/UNKNOWN reconcile；DESIGN 5.11.1/7.3 | AC-TASK-008、AC-EVIDENCE-002 | S3/S4 / Cut A | NOT_RUN |
| FR-TASK-012 | P0 | Default-off restricted holdout factory, heartbeat and token-free UNKNOWN recovery；DESIGN 3.2～3.3/5.11.1/7.1/7.3 | AC-TASK-008、AC-DEP-001、AC-DEP-002 | S3/S4 / Cut A | NOT_RUN |
| FR-GATE-001 | P0 | Promotion Policy hard gates；DESIGN 4.2.4/6.4 | AC-GATE-001、AC-STAT-004 | S2/S5 / Cut A | NOT_RUN |
| FR-GATE-002 | P0 | Gate evidence record；DESIGN 5.11 | AC-GATE-001 | S2 / Cut A | NOT_RUN |
| FR-GATE-003 | P0 | Missing evidence fail-closed；DESIGN 4.2.4/6.3 | AC-STAT-003、AC-GATE-001 | S2 / Cut A | NOT_RUN |
| FR-GATE-004 | P0 | Server actor + domain permissions；DESIGN 5.11/9.4/10.3 | AC-APP-001、AC-APP-002 | S5 / Cut A | NOT_RUN |
| FR-GATE-005 | P0 | Verifiable challenge records；DESIGN 5.11/9.4 | AC-APP-001、AC-APP-005 | S5 / Cut A | NOT_RUN |
| FR-GATE-006 | P0 | Immutable human decision fields；DESIGN 5.11 | AC-APP-001、AC-APP-003、AC-APP-005 | S5 / Cut A | NOT_RUN |
| FR-GATE-007 | P0 | Approval invalidation；DESIGN 4.2.4/5.11 | AC-APP-003 | S5 / Cut A | NOT_RUN |
| FR-GATE-008 | P0 | Prepare is not order/start；DESIGN 4.2.4/8.2 | AC-APP-004、AC-T3-002 | S5 / Cut A | NOT_RUN |
| FR-GATE-009 | P1 | Four-eyes approval；DESIGN 5.11 | AC-APP-006 | P1 | DEFERRED_P1 |
| FR-GATE-010 | P0 | Actor-mode approval policy；DESIGN 3.3/5.11/9.4 | AC-APP-005 | S5 / Cut A | NOT_RUN |
| FR-GATE-011 | P0 | Governance deviation record；DESIGN 5.11 | AC-GOV-002 | S5 / Cut A | NOT_RUN |
| FR-GATE-012 | P0 | Command-scoped evidence package v2；DESIGN 5.11.1 | AC-EVIDENCE-002、AC-APP-003 | S3/S5 / Cut A | NOT_RUN |
| FR-GATE-013 | P0 | Server-owned approval request/decision authority；DESIGN 4.2.4/5.11.1/8.2 | AC-APP-008、AC-APP-009、AC-UI-008 | S5 / Cut A | NOT_RUN |
| FR-GATE-014 | P0 | Human-only grant, exact ISSUED/REVOKED audit and safe ACK-loss replay；DESIGN 5.11.1/10.3/12.1 | AC-APP-002、AC-APP-007、AC-APP-008、AC-MIG-007 | S5 / Cut A | NOT_RUN |
| FR-GATE-015 | P0 | Immutable denial fence + 1:19 invariant；SQLite `LOCAL_T1` service-lock layer + three online DB race lanes (`NOT_RUN_CURRENT_HEAD`)；DESIGN 5.11.1 | AC-APP-009、AC-APP-010 | S5 / Cut A | NOT_RUN |
| FR-UI-001 | P0 | Evidence Workbench；DESIGN 9.1 | AC-UI-001 | S5 / Cut A | NOT_RUN |
| FR-UI-002 | P0 | Candidate/epoch/budget status header；DESIGN 9.1 | AC-UI-001 | S5 / Cut A | NOT_RUN |
| FR-UI-003 | P0 | Actionable FAIL/UNKNOWN/BLOCKED；DESIGN 9.1/8.3 | AC-UI-001 | S5 / Cut A | NOT_RUN |
| FR-UI-004 | P0 | Precheck evidence UI；DESIGN 9.4 | AC-UI-002 | S5 / Cut A | NOT_RUN |
| FR-UI-005 | P0 | Confirmation diff/hash UI；DESIGN 9.4 | AC-HYP-002、AC-UI-002 | S5 / Cut A | NOT_RUN |
| FR-UI-006 | P0 | Scoped cancel/retry/continue；DESIGN 9.2～9.3 | AC-UI-003、AC-UI-005 | S5 / Cut A | NOT_RUN |
| FR-UI-007 | P0 | Profile allowlist/credential ref；DESIGN 9.4/10.3 | AC-TENANT-002、AC-MIG-005 | S5 / Cut A | NOT_RUN |
| FR-UI-008 | P0 | Legacy unsealed label；DESIGN 12.2 | AC-SEAL-006、AC-UI-001 | S0/S5 / Cut A | NOT_RUN |
| FR-UI-009 | P0 | Accessible state semantics；DESIGN 9.5 | AC-A11Y-001 | S5 / Cut A | NOT_RUN |
| FR-UI-010 | P1 | Evidence export/search；DESIGN 11.3 | AC-EVIDENCE-001 | P1 | DEFERRED_P1 |
| FR-UI-011 | P0 | Product provenance truth；DESIGN 5.8/9.1 | AC-TRUTH-001、AC-TRUTH-002 | S5 / Cut A | NOT_RUN |
| FR-UI-012 | P0 | Late-response isolation；DESIGN 9.2～9.3 | AC-UI-003、AC-UI-004 | S5 / Cut A | NOT_RUN |
| FR-UI-013 | P1 | Fork Draft/revalidation；DESIGN 9.4 | AC-FORK-001 | P1 | DEFERRED_P1 |
| FR-UI-014 | P0 | One authoritative exact frontend/backend error catalog；DESIGN 8.3/9.4～9.5 | AC-I18N-001、AC-UI-008 | S5 / Cut A | NOT_RUN |
| FR-UI-015 | P0 | Service-owned safe projection, strict hash types and exact browser intent；DESIGN 5.11.1/8.2～8.3/9.4 | AC-APP-008、AC-UI-005、AC-UI-008 | S5 / Cut A | NOT_RUN |
| FR-SEC-001 | P0 | Sandbox Runner；DESIGN 10.1 | AC-SBX-001、AC-SBX-002、AC-SBX-003、AC-SBX-004、AC-SBX-005 | S3b / Cut A | NOT_RUN |
| FR-SEC-002 | P0 | Untrusted content separation；DESIGN 10.2 | AC-INJECTION-001、AC-INJECTION-002 | S2/S3b / Cut A | NOT_RUN |
| FR-SEC-003 | P0 | Tool allowlist/authority boundary；DESIGN 3.1/10.2 | AC-INJECTION-001、AC-INJECTION-002、AC-SEAL-001 | S3/S3b / Cut A | NOT_RUN |
| FR-SEC-004 | P0 | Secret redaction；DESIGN 10.3 | AC-PRIV-001、AC-TENANT-002 | S2/S5 / Cut A | NOT_RUN |
| FR-SEC-005 | P0 | Tenant ownership；DESIGN 3.1/10.3 | AC-TENANT-001 | S1/S5 / Cut A | NOT_RUN |
| FR-SEC-006 | P0 | Provider purpose/minimization；DESIGN 5.8/10.3 | AC-LLM-001、AC-PRIV-001 | S2 / Cut A | NOT_RUN |
| FR-SEC-007 | P0 | Encryption/reference/export allowlist；DESIGN 10.3/11.3 | AC-PRIV-001 | S2/S5 / Cut A | NOT_RUN |
| FR-SEC-008 | P1 | Security red-team regression；DESIGN 10.2 | AC-REDTEAM-001 | P1 | DEFERRED_P1 |
| FR-SEC-009 | P0 | Real isolated execution；DESIGN 3.3/10.1 | AC-SBX-001、AC-SBX-002、AC-SBX-003、AC-SBX-004、AC-SBX-005、AC-T2-003 | S3b / Cut A | NOT_RUN |
| FR-SEC-010 | P0 | Deep allowlist/taint/redaction；DESIGN 7.1/10.2～10.3 | AC-PRIV-001、AC-INJECTION-001、AC-INJECTION-002 | S2 / Cut A | NOT_RUN |
| FR-SEC-011 | P0 | User/workspace scoped profile；DESIGN 10.3/12.2 | AC-TENANT-001、AC-TENANT-002、AC-MIG-005 | S1/S5 / Cut A | NOT_RUN |
| FR-DEP-001 | P0 | Deployment Capability Registry；DESIGN 3.3 | AC-DEP-001 | S0/S3 / Cut A | NOT_RUN |
| FR-DEP-002 | P0 | Capability fail-closed；DESIGN 3.3/8.3 | AC-DEP-002 | S0/S3 / Cut A | NOT_RUN |
| FR-DEP-003 | P0 | SQLite/PostgreSQL/MySQL/MariaDB four-lane core vs isolation contract；DESIGN 3.2～3.3/12.1 | AC-DEP-001、AC-DEP-002、AC-MIG-001、AC-MIG-007 | S0/S3 / Cut A | NOT_RUN |
| FR-PRIV-001 | P1 | Retention/Privacy Policy；DESIGN 5.14/10.3 | AC-PRIV-002 | P1 | DEFERRED_P1 |

## 3. 非功能需求

| Requirement | Priority | 设计落点 | 具名验收 | 发布边界 | 当前状态 |
| --- | --- | --- | --- | --- | --- |
| NFR-REL-001 | P0 | FSM/lease/idempotency；DESIGN 4/7.3 | AC-TASK-002、AC-TASK-004、AC-TASK-005、AC-FSM-001 | Foundation/Cut A | NOT_RUN |
| NFR-REL-002 | P0 | Durable Task Runner；DESIGN 4.2.2/5.5 | AC-TASK-003 | Foundation/Cut A | NOT_RUN |
| NFR-PERF-001 | P0 | Summary API/indexes；DESIGN 8/11.2 | AC-NFR-001 | Cut A | NOT_RUN |
| NFR-PERF-002 | P0 | Append path；DESIGN 5.7/5.13 | AC-NFR-002 | Cut A | NOT_RUN |
| NFR-SCALE-001 | P0 | Cursor pagination/indexes；DESIGN 5.4～5.7/8.1 | AC-TASK-006、AC-NFR-001 | Cut A | NOT_RUN |
| NFR-OBS-001 | P0 | Correlation/metrics；DESIGN 11.1～11.2 | AC-NFR-003 | Cut A | NOT_RUN |
| NFR-AUD-001 | P0 | Append-only evidence and exact issuance provenance；DESIGN 5.11.1/5.13/11.3 | AC-AUD-001、AC-APP-007、AC-REP-001 | Cut A | NOT_RUN |
| NFR-SEC-001 | P0 | Trust boundaries；DESIGN 3/10 | AC-DEP-002、AC-SEAL-001、AC-PRIV-001、AC-SBX-001、AC-SBX-002、AC-SBX-003、AC-SBX-004、AC-SBX-005 | Cut A | NOT_RUN |
| NFR-UX-001 | P0 | A11y semantics；DESIGN 9.5 | AC-A11Y-001 | Cut A | NOT_RUN |
| NFR-COMP-001 | P0 | v1/v2 compatibility；DESIGN 8.1/12 | AC-MIG-002、AC-MIG-003、AC-MIG-004 | Cut A | NOT_RUN |
| NFR-PORT-001 | P0 | Four independent DB lanes, exact reflected types + capability profiles；DESIGN 3.3/12.1 | AC-MIG-001、AC-MIG-007、AC-DEP-001、AC-DEP-002 | Cut A/G5 | NOT_RUN |
| NFR-UX-002 | P1 | Usability baseline；DESIGN 9 | AC-USAB-001 | P1 | DEFERRED_P1 |
| NFR-DR-001 | P1/G5 | Evidence backup/restore；DESIGN 5.14/11.3 | AC-DR-001 | G5 when claimed | DEFERRED_P1 |

## 4. 迁移需求

| Requirement | Priority | 设计落点 | 具名验收 | 发布边界 | 当前状态 |
| --- | --- | --- | --- | --- | --- |
| MIG-001 | P0 | Protocol/schema version, principal kind and compat API；DESIGN 5.11.1/8.1/12.1 | AC-PROTOCOL-001、AC-MIG-001、AC-MIG-007 | Cut A | NOT_RUN |
| MIG-002 | P0 | Versioned dual-write diff policy；DESIGN 12.1 | AC-MIG-003 | Cut A/G5 | NOT_RUN |
| MIG-003 | P0 | Legacy workspace JSON read policy；DESIGN 12.2 | AC-MIG-002 | Cut A | NOT_RUN |
| MIG-004 | P0 | Profile quarantine/claim；DESIGN 12.2 | AC-MIG-005 | Cut A | NOT_RUN |
| MIG-005 | P0 | Operational rollback；DESIGN 12.3 | AC-MIG-004、AC-MIG-007 | Cut A/G5 | NOT_RUN |
| MIG-006 | P0 | Legacy write retirement deferred to explicit iteration；DESIGN 12.1/12.3 | AC-MIG-006 | Cut A | NOT_RUN |

## 5. 机器检查合同

文档 CI 至少应验证：

1. `REQUIREMENTS.md` 中每个 FR/NFR/MIG ID 在本表恰好出现一次；
2. 本表引用的每个 AC ID 在 `ACCEPTANCE.md` 有唯一标题定义；
3. P0 行不含空设计、空验收或 `DEFERRED_P1`；
4. P1 未实施行必须是 `DEFERRED_P1`，且产品文案无对应能力已可用声明；
5. 新增/删除/改优先级时，矩阵和 G0 evidence 同一 PR 更新；
6. `ACCEPTANCE.md` 的每个具名 AC 必须被需求行引用，或在下表登记为不引入产品行为的发布/测试基础设施场景。

## 6. 非需求级交叉场景登记

| 验收场景 | 所属门/证据层 | 不映射单一需求的理由 |
| --- | --- | --- |
| AC-GOV-001 | G0 / S0 readiness | 验证迭代容量、owner 与暂停裁决，是交付治理证据，不新增产品行为 |
| AC-T2-001 | G5 / T2 | 验证批准 scope 的新鲜真实数据 pilot，是证据新鲜度等级，不是通用功能需求 |
| AC-T2-002 | G5 / T2 | 验证真实 provider 调用谱系，是外部依赖新鲜证据，不替代对应功能的 T1 合同 |
| AC-UI-006 | G1 / 前端 API 回归 | 对多个已映射 endpoint 的请求/响应/错误/所有权测试做完整性盘点，不定义新 endpoint |
| AC-UI-007 | G1 / 前端测试基础设施 | 防止组件 stub/console warning 造成假绿，不改变用户可见行为 |

## 7. 历史本地证据与 2026-09-08 当前验收结果

逐项发布状态继续以本表的 `NOT_RUN/PASS/FAIL/BLOCKED` 回填为准。四份核心合同当前精确覆盖 **122 项需求、其中 110 项 P0、104 个具名 AC**；矩阵逐需求一一映射且不以横向测试数替代具名 AC。[LOCAL_T1_TRACEABILITY_20260905.md](LOCAL_T1_TRACEABILITY_20260905.md) 与 [2026-09-07 六 worker 分层回归](REGRESSION_6_WORKERS_20260907.md) 保留各自当时的历史证据；后者的 AI research 735/735 只属于其冻结源码/依赖。

2026-09-08 当前本地候选的后端 Python 来源摘要为 `03513ad1302d16e567ec180705181ac85be7d18fd25b88f5a13669de80988ec1`，跑前/功能后/性能后一致。固定 6 worker 功能通道为 6,131 passed、123 skipped、0 failure/error；串行性能通道为 18 passed、6 skipped、0 failure/error；互斥并集为 6,278 cases，其中 6,149 passed、129 skipped。AI research classname 为 1,303/1,303，approval 为 299/299。前端固定 6 worker 为 1,556/1,556，但 Node 25 超出 `>=20 <25`，只记 `LOCAL_PASS_UNSUPPORTED_RUNTIME`。完整证据见 [当前回归](REGRESSION_6_WORKERS_20260908.md)、[审批权威](APPROVAL_AUTHORITY_20260908.md) 与 [前端工作台](APPROVAL_WORKBENCH_FRONTEND_20260908.md)。这些本地横向绿灯不批量改变本表的真实环境状态；129 个 skip 也不是 PASS。

当前唯一 migration head 为 `20260908_ai_research_approval_authority`；独立 migration suite 135/135 与 SQLite/PostgreSQL/MySQL/MariaDB 四个离线 SQL lane 通过。审批终审 P0/P1/P2=0，历史 grant 重放、ACK-loss、类型校验、48 项公开错误目录和真实 1+19 SQLite 入口 barrier 在本地合同层通过。全仓 `ruff check`、compileall、`git diff --check` 与冲突扫描通过，但全仓 `ruff format --check` **失败：16 files would reformat**，不得写成全静态绿。工作树仍未提交，Backtrader 1.3.0 不满足声明 `>=1.9.78.123`，所以 G0/candidate seal 与依赖来源保持 `NO-GO`。

AC-MIG-007 还要求 SQLite、PostgreSQL、MySQL、MariaDB 四个独立 lane；MariaDB 不得复用 MySQL PASS。真实 online 反射分别证明 unique constraint/index 配对、MySQL/MariaDB index type/visibility、`VARCHAR`、PostgreSQL `timestamptz` 默认 precision、MySQL/MariaDB `DATETIME(fsp=None)`、SQLite `DATETIME/VARCHAR/TEXT` 区分、partial re-entry 的全列元数据、quote-aware CHECK 比较和合法历史 decision 时序。SQLite、catalog mock、离线 SQL 或六 worker 本地绿灯不得代替 PostgreSQL/MySQL/MariaDB 三个 online 引擎证据。request + claim/start 只是实现线索；真实 service identity/queue/IAM/object storage/Evaluator、authenticated 当前 UI、Provider、生产容器、operational rollback 与 T2/T3 仍未闭合，相关行保持 `NOT_RUN/BLOCKED`。

AC-APP-010 的竞争证据同样分层：SQLite `LOCAL_T1` 已用入口 barrier 同时放行 1 个拒绝与 19 个批准请求，验证同进程 `ApprovalService._operation_lock` 线性化、唯一拒绝 fence 与零 current approval；PostgreSQL、MySQL、MariaDB 的 20 个独立 process/connection 锁与 commit 竞争必须在各自真实 online lane 独立取证，当前均为 `NOT_RUN_CURRENT_HEAD`。前者 PASS 不得提升或代填后三者状态。

真实对象存储/IAM、queue/Evaluator/Provider、authenticated current UI、Node 20、T2/T3 与 operational rollback 均为 `NOT_RUN/BLOCKED`。因此 `IMPLEMENTATION_ACCEPTED=NO-GO`、`PROTOCOL_PRODUCTION_ENABLED=NO-GO`，candidate research/promotion 仍为 `BLOCKED/NO-GO`。
