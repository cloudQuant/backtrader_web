# Command-scoped Evidence Package v2 本地证据（2026-09-08）

> 判定：`LOCAL_T1_PASS`，覆盖 command-wide 绑定、并发唯一性、withdraw 串行化、ACK-loss 读回和迁移合同。
> 发布边界：整体与生产启用继续 `NO-GO`；真实对象存储/IAM、独立 Evaluator、当前 authenticated UI 与多数据库 online 证据未运行。
> 需求/验收：`FR-DATA-014`、`FR-GATE-012`、`AC-SEAL-007`、`AC-EVIDENCE-002`、`AC-MIG-007`。

## 1. 为什么不能继续使用 candidate-wide 包

旧 evidence package 可以按 candidate 聚合，存在把不同 evaluation 的 gate 拼成一个“完整”包、把 legacy iteration-validation 当作 sealed holdout、或在 withdraw 竞争中复活旧包的风险。v2 将审批证据的最小权威单位改为一个已经成功终结的 holdout command。

一个 `ACTIVE` v2 package 必须精确绑定同一条不可分割图：

```text
run + candidate + freeze receipt + epoch
  -> holdout command + consumed authorization + evaluation
  -> result artifact + terminal ACCEPTED audit
  -> exactly 13 ordered PASS gates
  -> promotion policy/material + capability profile/material
  -> manifest_hash + approval_binding_hash
```

任一节点缺失、重复、错绑、状态不符、内容哈希漂移或出现额外未绑定 gate，构建都 fail-closed。七项 gate 与另一个 evaluation 的六项 gate不能拼成 13 项；同 candidate 的 legacy evaluation 不会改变 command-scoped 选择结果。

## 2. 并发、撤回与不确定提交

- 20 个并发 build 对同一完整 terminal command 收敛为一个 package；唯一键只是最后防线，已有包仍须完整重验；
- build 与 withdraw 对同一 package 行使用数据库锁串行；withdraw 成功后旧包不能再次变回 `ACTIVE`；
- commit ACK 丢失时只允许按完整 material/manifest/binding hash 读回精确 winner；无法证明时不得返回假成功；
- 恢复后的 lease/new worker 只能使用已持久化 terminal transition audit，不能绕过 command graph；
- `manifest-v1` 永远不能成为 v2 approval authority；
- wrong user、unknown command 和非 owner 查询统一失败，不能用响应差异探测内部 command/evaluation；
- owner 公共轮询只返回安全 command receipt；内部 `evaluation_id` 仅保留在 evidence/approval server-side graph，不进入该轮询 schema。

## 3. 迁移完整性

`20260908_ai_research_evidence_command` 为 evidence package 增加 command/evaluation/authorization 等全有或全无绑定、每 command 唯一 ACTIVE 身份、v2 manifest/binding hash 及严格 downgrade guard。迁移的 PostgreSQL guard 采用 current-schema relation/function OID 与完整函数 body/trigger definition/refcount 判断：

- 精确已有对象允许 partial re-entry；
- 同名 orphan、错误 relation、漂移 body 或被其他 trigger 引用的函数一律冲突失败；
- 不使用 `CREATE OR REPLACE` 覆盖无法证明所有权的函数；
- 非空 v2 evidence 在 downgrade 前被阻断，不能静默删证。

该规则已经由 catalog mock/DDL 合同和 SQLite 路径测试，但没有在真实 PostgreSQL/MySQL/MariaDB 当前 head 上执行，故三种 online 状态仍为 `NOT_RUN_CURRENT_HEAD`。

## 4. 已执行证据

证据包核心回归：

```text
39 passed, 0 failed/error, 23.30 seconds, 6 workers
```

覆盖 v2 全链路 migration 文件的回归（包含 evidence command 的 collision/partial re-entry/downgrade 负例）：

```text
96 passed, 0 failed/error, 24.80 seconds, 6 workers
```

同时通过 scoped Ruff、format check、Python compile 和 `git diff --check`。测试期间没有运行真实 evaluator、对象存储、IAM 或三数据库在线迁移。最终冻结源码的横向结果以 [2026-09-08 六 worker回归记录](REGRESSION_6_WORKERS_20260908.md) 为准；源码摘要不一致时不得用本页旧局部绿灯补齐。

## 5. 验收判定

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| exact terminal graph/material validation | `LOCAL_T1_PASS` | 覆盖正负绑定与篡改 |
| 20-way build/withdraw/ACK-loss | `LOCAL_T1_PASS` | 同进程/受控 DB，不等于生产并发 |
| v2 migration contract | `LOCAL_T1_PASS` | catalog mock + SQLite；online 多库未运行 |
| PostgreSQL/MySQL/MariaDB online | `NOT_RUN_CURRENT_HEAD` | 阻断 AC-MIG-007 完整 PASS |
| 真实证据包可重放/生产保存 | `NOT_RUN` | 无对象存储/IAM/备份恢复证据 |

