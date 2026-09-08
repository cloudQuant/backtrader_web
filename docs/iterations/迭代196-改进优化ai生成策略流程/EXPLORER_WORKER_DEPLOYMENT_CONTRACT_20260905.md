# 迭代 196：Explorer Worker 部署契约（2026-09-05）

> 状态：**T1 代码与静态部署契约已验证；不是 sealed evaluator、真实 sandbox 或生产拓扑能力证明。**

本文件只定义 protocol-v2 的独立 Explorer 进程如何安全启动。它落实 `FR-TASK-003` 的“完整执行器集在首次领取前显式注入”要求，不把尚未部署的 LLM、回测或 sandbox 伪装成可执行能力。

## 1. 已实现的启动边界

实现位于候选分支的以下文件：

- `src/backend/app/services/research/worker_process.py`：部署专用 bootstrap；
- `src/backend/scripts/run_ai_research_v2_worker.py`：容器/进程 CLI；
- `docker/compose/trusted-research-explorer.yml`：显式 opt-in 的 Explorer overlay。
- `src/backend/app/research_deployments/explorer.py` 与 `app/services/research/deterministic_executor.py`：经过测试的诊断 factory；默认配置不引用它。

启动顺序固定如下：

```text
两个 feature flag 已开启
  -> 解析受限 factory 名称
  -> factory 返回 ResearchProtocolWorker
  -> 校验 CLARIFY + GENERATE 完整 executor map
  -> recover expired leases / claim due tasks
  -> 执行当前 poll；TERM/INT 后停止下一次 claim
```

任何箭头处失败都发生在 `recover_expired_leases()` 或 `claim_due()` 之前。缺少执行器不会把排队中的用户任务逐个写成 `RESEARCH_STAGE_EXECUTOR_UNAVAILABLE`；它会以 `RESEARCH_WORKER_EXECUTORS_INCOMPLETE` 让 worker 进程退出，任务保持 `QUEUED`。

API 的 FastAPI lifespan 没有调用该 bootstrap，也没有默认 executor factory。API worker 数、重载或请求生命周期均不会代替 Explorer 领取任务。

## 2. 配置与 factory 合同

| 配置 | 默认值 | 含义 |
| --- | --- | --- |
| `AI_RESEARCH_PROTOCOL_V2_ENABLED` | `false` | v2 写入总开关；关闭时 CLI 正常退出且不加载 factory。 |
| `AI_RESEARCH_PROTOCOL_V2_WORKER_ENABLED` | `false` | 独立 Explorer 进程开关；关闭时不加载 factory、不恢复或领取任务。 |
| `AI_RESEARCH_PROTOCOL_V2_WORKER_FACTORY` | 空 | 必须是镜像内受审查的 `app.research_deployments.<module>:<callable>`。空值、非法格式、导入失败或非 callable 都失败关闭。 |
| `AI_RESEARCH_PROTOCOL_V2_WORKER_POLL_SECONDS` | `10.0` | `0.1–3600` 秒；仅控制完成一次 poll 后的等待，不绕过 lease/heartbeat。 |

factory 是零参数同步或异步 callable，且必须返回 `ResearchProtocolWorker`。其唯一职责是把部署侧已批准的 executor 注入 worker；不能从 task JSON、浏览器输入或任意 import 路径推导 executor。

候选分支已提供受限名称 `app.research_deployments.explorer:create_worker`，但它**不是策略生成 factory**：`CLARIFY` 只持久化一个 `NOT_CALLED/NOT_EXECUTED` 的确定性 receipt；`GENERATE` 同样持久化诊断 receipt 后以 `RESEARCH_GENERATION_NOT_EXECUTED` 失败。它不创建 candidate、不会调用 Provider/Sandbox/Backtest/Evaluator，也不会产生 market trial。该行为只验证 worker 的受控工件与失败回执链路，不能把任务显示为研究成功。

```python
app.research_deployments.explorer:create_worker
  -> DeterministicClarifyExecutor
  -> DeterministicGenerateExecutor
  -> GENERATE fails closed; no candidate is materialized
```

每个成功 stage 都必须含有 broker 生成、内容哈希/长度可复核且精确绑定到 owner/run/task/attempt/request hash 的工件；旧的无绑定成功 checkpoint 在恢复时 fail-closed。已终态 attempt 的 retry 不得再次推进 cursor。generic `GENERATE` 的绑定工件仍不足以证明 candidate、模型调用、sandbox 或评估，worker 会把它拒绝为 `RESEARCH_GENERATION_CONTRACT_UNAVAILABLE`；只有 typed `ProposedGeneration` 能经 server-owned materializer 重验对象身份与 binding 后写出 `MATERIALIZED_NOT_EXECUTED` candidate。该候选没有调用任何 Provider/Sandbox/Evaluator，仍不能当作研究执行成功。完整处置见 [IMPLEMENTATION_REVIEW_DISPOSITION_20260905.md](IMPLEMENTATION_REVIEW_DISPOSITION_20260905.md)。

factory 所在模块必须随经过评审的 **Explorer 专用镜像** 一起发布。通用 API 镜像没有默认 factory；不得通过 task payload、环境变量中的任意 Python 路径或运行时下载代码来扩大可执行集合。

## 3. 可选 Compose overlay

以下命令只渲染/启动 Explorer process，且需显式选择 profile：

```bash
docker compose \
  -f docker/docker-compose.yml \
  -f docker/compose/prod.yml \
  -f docker/compose/trusted-research-explorer.yml \
  --profile trusted-research-explorer up -d
```

overlay 的安全基线为：无 host port、无 host volume、`read_only` root filesystem、非 root UID、`cap_drop: ALL`、`no-new-privileges`、受限 `/tmp`、`init: true` 和 `restart: "no"`。日志仅写入该受限 tmpfs 下的 `/tmp/logs`，不以可写根目录或宿主日志挂载规避只读约束。最后一项故意让错误配置以退出码 `2` 暴露给编排/告警，而不是无限 crash-loop。

它仍不是完整的 sealed topology：当前 MySQL/Redis 网络和通用数据库身份不能证明 Explorer 无密封数据路径；overlay 也不包含 Evaluator、专用 queue/object-store credential、真实 Sandbox Runner 或签名镜像。因此不得为它登记 `sealed_evaluation` 或 `sandbox` capability，也不得把 Compose YAML 视为 IAM/网络拒绝测试证据。

## 4. 本轮可复核证据

| 检查 | 结果 |
| --- | --- |
| 完整目录六 worker 回归内的 v2 子集；`backend-full-6-load.xml` | 156 项在最新完整回归内全部通过（JUnit 逐项核对）；含 opaque object receipt/URI 拒绝、对象版本/摘要/identity 重验、legacy snapshot/forward receipt 边界、typed materialization 漂移负例，以及受控输出绑定、无工件 success 拒绝、旧 checkpoint recovery、内容篡改/编码路径/错误 request hash、终态 cursor、generic terminal success 拒绝、诊断 factory 和 event sequence/MySQL fallback。真实对象存储、MySQL/InnoDB 并发及外部执行仍属环境门禁。 |
| `ruff check` / `ruff format --check`（v2 backend 实现与测试） | 通过。 |
| 实际 CLI，两个 flag 均关闭 | 正常退出 `0`，记录“不加载 factory”。 |
| 实际 CLI，两个 flag 开启但 factory 为空 | 退出 `2`，稳定错误 `RESEARCH_WORKER_FACTORY_REFERENCE_REQUIRED`；在连接数据库前失败。 |
| `docker compose ... config --quiet`（placeholder 非秘密环境变量） | 通过；overlay 的 factory 现在可在双 flag 关闭时留空，开启后仍由 bootstrap fail-closed。仅验证 Compose 语法/变量展开，不验证 Docker daemon、镜像、网络或权限。 |

这组证据补充 [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) 与 [ACCEPTANCE_REPORT_20260905.md](ACCEPTANCE_REPORT_20260905.md)，不覆盖它们列出的 T2/T3 或生产 NO-GO。

## 5. 启用前仍必须补齐的外部条件

1. 在独立 Explorer service identity 下提供经评审的真实 `CLARIFY`/`GENERATE` factory，并证明它只访问 Discovery/Iteration Validation 数据与最小凭据。当前 deterministic factory 只证明受控诊断 receipt，不能替代此项。
2. 将已验证的 typed candidate materialization/provenance contract（候选、代码/依赖、模型调用摘要、受证明数据与 artifact binding）接入真实 factory、Sandbox 与评估链；generic success 继续固定失败。随后将实际 provider、代码 artifact、回测和 runner 接入完整 quota/fencing/operation-reconciliation 合同。
3. 部署独立 Evaluator identity、专用 queue、对象存储权限与网络拒绝规则，完成 Explorer 读取 sealed 对象/API/URI/工具全部拒绝的实际测试。
4. 部署真实 Sandbox Runner，完成 `AC-SBX-001～005`：断网、只读、无宿主 credential、资源/进程组清理、恶意输出和镜像/工件语义验证。
5. 用真实 Docker/目标编排环境验证 `TERM`、kill/recovery、日志/告警、回滚与 capability profile 证据；本机 Docker daemon 不可用时该项保持 `BLOCKED_ENVIRONMENT`。

## 6. 回滚

1. 将 `AI_RESEARCH_PROTOCOL_V2_WORKER_ENABLED=false`，停止新 poll；等待当前 lease 按已存在的 heartbeat/CAS/unknown-outcome 合同收口。
2. 如需完全关闭写入，再将 `AI_RESEARCH_PROTOCOL_V2_ENABLED=false`；保留 task、stage attempt、artifact 和审计记录为只读证据。
3. 停止 Explorer overlay，撤销其 factory 对应的专用凭据；不要把任务退回 API 进程、宿主子进程或 legacy 生成流程执行。

不删除 v2 表、不回写历史状态、不把已产生的密封/未知结果当作 legacy 成功结果。
