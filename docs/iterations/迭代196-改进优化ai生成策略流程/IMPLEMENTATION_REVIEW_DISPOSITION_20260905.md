# 迭代 196：实现完整性评审处置（2026-09-05）

> 结论：评审提出的“不能把任意阶段回执或诊断工件升级为研究成功”判断合理。阶段提交时钟、HTTP adapter/generation 组合根现已补齐；303 项聚焦通过（v2 299 + config 4），包括公开 worker 的本地 HTTP seam 物化链与出站携密键拒绝。完整目录终态见 [回归记录](REGRESSION_6_WORKERS_20260905.md)。后续独立评估/审批/沙箱执行图和总 token/费用上界仍有本地实现工作；真实供应商/拓扑另行验收，结论保持 NO-GO。详见 [本批部署合同](GENERATION_PROVIDER_DEPLOYMENT_20260905.md)。

## 1. 处置范围

本次只审查候选工作树中的 protocol-v2 Explorer worker、stage receipt、受控工件和部署启动边界。它不重写 [REQUIREMENTS_REVIEW.md](REQUIREMENTS_REVIEW.md) 的独立需求评审，也不把本地修复外推为 T2/T3 或生产证据。

| 编号 | 评审发现 | 处置 | 当前合同 |
| --- | --- | --- | --- |
| CR-01 | `SUCCEEDED` 可没有受控工件 | 已修复 | `StageExecutionOutcome` 与 `ResearchStageAttemptService.complete()` 均要求成功输出提供非空、精确绑定且内容可验证的工件。 |
| CR-02 | lease recovery 可采纳无工件成功 checkpoint | 已修复 | `resume_succeeded_checkpoint()` 会重新校验工件 ID、owner/run/task/attempt binding 与内容完整性；旧的无绑定成功行 fail-closed。 |
| CR-03 | 终态 retry 可用新的 `next_stage` 改写 cursor | 已修复 | 已终态 attempt 的 retry 只验证并读取，不再推进 task/run cursor。 |
| CR-04 | 内容存在不等于内容仍未被篡改 | 已修复 | 完成和恢复前重新计算 blob 的 SHA-256 与长度，并核对 metadata；不一致返回 `RESEARCH_STAGE_ATTEMPT_ARTIFACT_CONTENT_INTEGRITY_INVALID`。 |
| CR-05 | 工件 URI 可经 percent-encoding 绕过路径检查 | 已修复 | descriptor 对路径段 decode 后拒绝 `.`、`..`、编码分隔符、反斜杠、NUL 与残余 `%`。 |
| CR-06 | broker 未独立校验 run owner/request hash | 已修复 | stage-output 写入锁定并核验 `ResearchRun`、task 与 context 的 owner/run/request hash；错误上下文被拒绝。 |
| CR-07 | 任意绑定 `GENERATE` 工件仍可能把 task 置为成功 | 已修复为 typed 能力门 | generic `GENERATE` 成功仍改写为 `RESEARCH_GENERATION_CONTRACT_UNAVAILABLE`。只有 typed `ProposedGeneration` 才由服务端重验 binding/对象身份后原子物化 candidate、manifest、artifact binding 和 receipt；结果固定为 `MATERIALIZED_NOT_EXECUTED`，不构成策略执行或研究成功。 |
| CR-08 | deterministic receipt 把“已生成”与“未调用模型”混用 | 已修复 | receipt 使用 `transformation_chain=["receipt_persisted"]` 和 `fallback_chain=["deterministic_factory_selected","model_provider_not_invoked"]`。 |
| CR-09 | Compose disabled 语义与 CLI 不一致 | 已修复 | overlay 允许空 factory；仅在两个 flag 同时开启时，bootstrap 才在 recover/claim 前以 `RESEARCH_WORKER_FACTORY_REFERENCE_REQUIRED` fail-closed。 |
| CR-10 | heartbeat 与终态提交可用陈旧 ORM `event_sequence` 重复写事件 | 已修复 | 每次 append 都以数据库行的原子递增分配序号；陈旧 task 快照不能覆盖或复用已提交的 sequence，SQLite `RETURNING` cursor 会在 commit 前关闭。 |

## 2. 保留的能力边界

`app.research_deployments.explorer:create_worker` 仅是显式 opt-in 的确定性诊断工厂：

```text
CLARIFY -> 写入并绑定 NOT_CALLED / NOT_EXECUTED receipt -> 成功进入 GENERATE
GENERATE -> 写入并绑定 NOT_CALLED / NOT_EXECUTED receipt -> FAILED(RESEARCH_GENERATION_NOT_EXECUTED)
```

它不会创建 candidate，不调用模型、不运行 sandbox/backtest/evaluator、不产生 market trial，也不允许任务伪装为“AI 已生成有效策略”。即使后续有第三方 executor 返回 generic `GENERATE` success，也会被 `RESEARCH_GENERATION_CONTRACT_UNAVAILABLE` 拦截；只有单独接入 typed materializer 的受证明 proposal 才能写出 `MATERIALIZED_NOT_EXECUTED` candidate，仍不启动这些外部能力。

## 3. 本地验证

- TDD 负例先行：无工件 success、无绑定 checkpoint recovery、encoded traversal、run request-hash 伪造及 generic terminal success 均先得到预期失败，再完成实现；对应聚焦组已转绿。
- 6 核完整回归：`pytest -p no:rerunfailures -q -n 6 --dist load --durations=15 tests`，4,993 passed、129 skipped、174 warnings、536.50 秒；JUnit 中 156 项 v2 用例全部通过。补入 freeze、holdout 签发/消费、evaluator、evidence 与 approval 的 resolver 重验、独立连接心跳夹具与本地 CLI 来源断言。两项回归夹具修复经独立只读 review 无阻断，生产脚本和 5 秒时限未改，未用自动重试或文件排除隐藏失败。详见 [六进程回归记录](REGRESSION_6_WORKERS_20260905.md)。
- task-runner/worker 聚焦与静态质量检查通过；当前 Alembic head 已推进为 `20260905_ai_research_provider_model`，SQLite/PostgreSQL 实际迁移证据见 [迁移验收](CURRENT_HEAD_MIGRATION_20260905.md)。MySQL/InnoDB 的真实锁与事务仍须在具备授权凭据的环境验证。
- 前端 task/event 合同：`npm run typecheck` 通过；3 个聚焦文件 39 项通过。
- Compose 仅做静态展开：带 placeholder 非秘密变量的 `docker compose ... config --quiet` 通过；未连接 Docker daemon，也没有任何容器/IAM/网络隔离结论。

## 4. 验收处置

后续只读复核补充：单次派发/结算和实际文件 resolver 的局部修复及红绿证据分别见 [DISPATCH_SAFETY_20260905.md](DISPATCH_SAFETY_20260905.md)、[FILESYSTEM_DATASET_RESOLVER_20260905.md](FILESYSTEM_DATASET_RESOLVER_20260905.md)。最新复核仍保留两个明确待修项：Provider 非 Mapping 用量/成本可能导致调用账本缺失；期限生成用应用时钟而派发检查用 DB 时钟，尚未证明跨主机时钟偏差下的租约语义。当前完整回归的绿色结果不能消除这两个覆盖缺口，进入真实 Provider/独立部署前必须修复并复验。

本项评审使 T1 的“本地失败关闭、对象身份与 typed materialization 合同”更强，但不改变 [ACCEPTANCE.md](ACCEPTANCE.md) 的逐项 `NOT_RUN/BLOCKED` 责任，也不改变 `IMPLEMENTATION_ACCEPTED=NO-GO`、`PROTOCOL_PRODUCTION_ENABLED=NO-GO`。进入真实启用前仍须完成真实对象存储 resolver/IAM、materialized candidate 到 evaluator/approval/sandbox 的部署链、T2 Provider/数据冷重放、T3 前向观察、独立身份/存储/网络拒绝和 Sandbox/Evaluator 证据。
