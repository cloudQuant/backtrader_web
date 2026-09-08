# 迭代 196：审批权威实现与验收记录（2026-09-08）

> 结论：审批权威的本地代码终审为 P0/P1/P2 = 0；human-only run-scoped grant、数据库时间窗、不可变拒绝围栏、历史决定重放、提交结果不确定和公开错误目录均形成了 fail-closed 合同。该结论仅是本地 `LOCAL_T1` 组件证据；真实 PostgreSQL/MySQL/MariaDB 多进程竞争、部署身份和 authenticated 当前 UI 尚未运行，不构成生产职责隔离证明。

## 1. 冻结范围

- 实现工作树：`/Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust`；
- 分支：`codex/iteration-196-ai-research-trust`；
- 基础/当前提交：`a18bcf52682686c30d919fe02d6fd734ee4271b9`；
- 主要后端落点：`src/backend/app/services/research/approval.py`、`approval_authority.py`、`src/backend/app/api/strategy/research.py`；
- 主要合同测试：`test_ai_research_approval.py`、`test_ai_research_approval_authority.py`、`test_ai_research_approval_api.py`；
- 工作树仍有大量未提交变更，`G0 provenance/candidate seal=NO-GO`。

## 2. 权威与职责隔离合同

1. 审批 actor 只来自认证上下文，客户端不能提交或覆盖 actor。
2. `users.principal_kind` 由服务端管理；应用新建人类用户使用 `HUMAN`，迁移/数据库默认和历史回填使用保守的 `UNKNOWN`。`SERVICE` 与 `UNKNOWN` 均不能获得人工审批权。
3. 普通 ADMIN 不自动拥有 `APPROVE_RESEARCH` 或 `MANAGE_APPROVAL_GRANTS`。专用 `RESEARCH_APPROVAL_ADMIN` 只能管理 grant，不能直接批准；审批者仍须满足 run/candidate/evidence/policy scope、角色、主体种类和有效 grant。
4. 批准、拒绝和要求修改均由服务端锁定当前候选、请求、证据包、gate 材料和拒绝围栏后决定。`APPROVED` 额外要求 `can_approve=true`；有决定权限但无批准权限的主体仍可按授权做 `REJECTED/REQUESTED_CHANGES`。
5. 所有 hard gate 必须逐项 PASS；未知、缺失、漂移或客户端提供的伪造摘要都 fail-closed。

## 3. grant 当前有效性与历史重放

当前批准只接受一个精确有效的 grant：主体和签发者必须为 `HUMAN`，scope/角色/材料摘要完全匹配，数据库时间位于有效期内，grant 未撤销，并且存在唯一、字段完整且完全匹配的 `ISSUED` audit。重复、孤立、篡改或缺失 audit 均拒绝。

历史批准重放使用决定发生时的事实，而不是要求 grant 在今天仍有效：

```text
issued_at <= decided_at < expires_at
```

若 grant 后来被撤销，还必须满足：

```text
decided_at < revoked_at
```

并存在唯一、完整、与 grant 和撤销材料精确匹配的 `REVOKED` audit。决定前撤销、决定恰好等于过期时刻、缺失/篡改/重复撤销 audit 均不能重放；决定之后的合法撤销或仅因当前墙钟已过期，不会抹除当时合法的历史决定。签发者后来 inactive 可以保留历史重放，但其 principal kind 仍必须是 `HUMAN`。

## 4. 并发、拒绝围栏和 ACK-loss

- 同一 candidate 的决定按确定锁序处理，拒绝围栏是不可变的最终否决事实；更换 idempotency key 不能绕过。
- 本地 SQLite `LOCAL_T1` 使用真正的入口 barrier 同时放行 1 个 REJECTED 与 19 个 APPROVED 请求，验证同进程 `ApprovalService._operation_lock` 的线性化语义：最终只有一个拒绝围栏且 current approval 为 0，预先存在的 pending 请求也不能绕过。
- 该 SQLite 结果不代表 PostgreSQL/MySQL/MariaDB 的数据库锁和跨进程 commit 竞争。三个引擎各自的 20 个独立 process/connection lane 均为 `NOT_RUN_CURRENT_HEAD`。
- request、decision、grant issue/revoke 对 commit ACK 丢失采用权威读回：若读回证明提交已生效，则返回幂等结果；若提交未生效、读回不可用、audit 不完整或材料漂移，则返回稳定的 outcome-unknown，不重复发起副作用。
- grant issue/revoke 的读回异常统一转换为 `APPROVAL_GRANT_COMMIT_OUTCOME_UNKNOWN`；不会把内部 `RuntimeError` 或存储细节泄露到 API。

## 5. 输入与错误合同

- gate hash、evidence hash、idempotency key 等先做类型检查再做格式验证；非字符串不会触发未处理的正则 `TypeError`，统一为 `APPROVAL_IDEMPOTENCY_OR_EVIDENCE_INVALID`。
- 后端以 48 项排序 tuple 作为公开错误权威，每项固定 `code/http_status/retryable`；版本为 `ai-research-approval-errors/v1`，规范摘要为 `6dd9f6ce55ec595c9441ae08e26f6cc0845549eb1c950a6a28481ad973870d53`。
- 前端用 versioned JSON + TypeScript 读取同一目录，全仓 strict verifier 比较 backend/frontend 的版本、48 项完整内容和摘要。
- API 优先读取真实 envelope 的 `details.code`，同时保留 legacy `detail` 兼容；冲突、内部或未知 code 均投影为通用失败。只有 `APPROVAL_CHALLENGE_INCOMPLETE:<fields>` 后缀被归一为公开 `APPROVAL_CHALLENGE_INCOMPLETE`。
- 公开目录以外的 `APPROVAL_DECISION_INTENT_INVALID`、`APPROVAL_DENIAL_FENCE_CONFLICT` 等内部诊断不会原样泄漏。

## 6. 已执行证据

| 证据 | 结果 | 边界 |
| --- | --- | --- |
| 审批三文件聚焦回归 | 164/164 passed | 本地服务/API 合同 |
| API/hypothesis 相关回归 | 61/61 passed，固定 6 worker | 路由、schema、错误投影与相邻 hypothesis 合同 |
| 最终功能 JUnit approval 子集 | 299/299 passed | 属于完整 6 worker 功能通道 |
| 后端最终功能通道 | 6,131 passed、123 skipped、0 failure/error | 详情见 [REGRESSION_6_WORKERS_20260908.md](REGRESSION_6_WORKERS_20260908.md) |
| scoped mypy | mypy 1.16.1：3 files，0 error | 项目锁定 1.20.2 未执行，`NOT_RUN_PINNED_VERSION` |
| Ruff/scoped format/diff | PASS | 全仓 format 仍有 16 文件未通过，不得扩大声明 |
| 独立代码终审 | P0=0、P1=0、P2=0 | 真实部署/在线环境不在该终审证据内 |

## 7. 尚未验收与判定

- PostgreSQL、MySQL、MariaDB 独立连接和跨进程 1:19 竞争：`NOT_RUN_CURRENT_HEAD`；
- 真实 queue/Evaluator 身份、对象存储/IAM、生产审批管理员与审计导出：`NOT_RUN/BLOCKED_ENVIRONMENT`；
- authenticated current UI 与真实错误 envelope 端到端旅程：`NOT_RUN`；
- T2/T3、灰度和 operational rollback：`NOT_RUN/BLOCKED_ENVIRONMENT`。

因此审批权威的本地实现和合同回归可以判 `LOCAL_T1 PASS`，但不能判定生产职责隔离已经成立；总体 `IMPLEMENTATION_ACCEPTED` 与 `PROTOCOL_PRODUCTION_ENABLED` 仍为 `NO-GO`。
