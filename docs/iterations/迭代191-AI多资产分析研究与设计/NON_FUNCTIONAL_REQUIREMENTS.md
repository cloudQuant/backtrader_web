# 迭代 191：非功能需求与运行基线

> 状态：T1 工程验收基线
> 性质：可测量的规划阈值，不是客户 SLA、生产 SLO 或收益承诺
> 关联文档：[总计划](./README.md) · [验收标准](./ACCEPTANCE.md) ·
> [交付治理](./DELIVERY_GOVERNANCE.md) · [总体架构](./ARCHITECTURE.md)

## 1. 范围与解释

本文规定迭代 191 在 T1 技术验收中必须测量的延迟、容量、韧性、生命周期、可观测性、
LLM 预算和前端状态一致性。它不替代：

- T2 的资产样本、模型稳定性、校准、漂移和模型风险审批；
- T3 的适当性、交易执行和监管要求；T3 当前不在本迭代范围；
- 具体部署环境经过测量后批准的生产 SLO/SLA。

文中的数值是首轮工程基线。首次实现必须按规定场景测量，不能把未测数值写成“已达到”。
连续三轮稳定测量后，SRE、QA 和技术负责人可用 C1 变更校准非破坏性阈值；降低安全、隔离、
授权、数据完整性或可恢复性要求按 C2 处理。

关键字含义：

- **必须**：T1 硬门禁，失败即 `NO-GO`；
- **应该**：默认实现，偏离需要记录理由和替代控制；
- **规划默认值**：上线前必须成为显式配置，并经对应责任人确认；
- **观测值**：外部数据源或 LLM 的实测结果，只用于容量和供应商决策，不构成客户承诺。

## 2. 测量方法

### 2.1 标准测试剖面

| 剖面 | 用途 | 数据与外部依赖 | 是否可判定 T1 |
| --- | --- | --- | --- |
| `FIXTURE` | 正确性和可重复延迟 | 固定 point-in-time fixture、固定时钟、LLM 固定响应 | 是 |
| `CAPACITY` | 并发、队列和资源上限 | 固定 fixture、LLM stub、固定 worker/数据库配置 | 是 |
| `FAILURE` | 超时、限流、中断、恢复和降级 | 故障注入，不调用不可控真实服务 | 是 |
| `FRONTEND` | 页面性能和状态一致性 | production build、固定 API fixture、真实浏览器 | 是 |
| `ONLINE-SMOKE` | provider 可用性和实际成本 | 受控真实来源/LLM，记录地域和时间窗 | 否；仅补充证据 |

在线验证不得替代固定 fixture。供应商延迟、网络波动和市场闭市会影响 `ONLINE-SMOKE`，因此
只报告分布和失败原因，不用单次在线成功或失败判定公共实现。

### 2.2 证据要求

每份结果必须记录：

```text
commit_sha
profile
started_at / timezone
host_cpu_memory
os_runtime_browser
database_vendor_version
schema_revision
worker_and_source_concurrency
config_hash_without_secrets
fixture_or_dataset_version
model_and_prompt_version
warmup_count / measured_count
raw_result_location
summary_p50_p95_p99_error_rate
```

通用规则：

- 延迟使用单调时钟，从调用入口到契约规定的完成点；
- 控制面 API 至少预热 10 次、测量 100 次；完整任务至少测量 30 次；
- 报告 p50、p95、p99、最大值和错误率，不能只报告平均值；
- 容量测试前后记录 CPU、RSS、数据库连接、队列深度和未终结任务数；
- 结果中排除的请求必须逐项给出原因，不能静默丢弃异常值；
- 测试必须使用用户 Anaconda 环境执行 Python 命令。

## 3. T1 延迟与前端体验基线

以下阈值只适用于对应的固定剖面，属于首轮工程验收值。

### 3.1 API 和任务

| ID | 场景 | 测量边界 | 初始阈值 |
| --- | --- | --- | --- |
| NFR-L01 | capabilities、task status、轻量 result 查询 | 应用入口至序列化完成，热缓存 | p95 ≤ 500 ms，p99 ≤ 1 s |
| NFR-L02 | ≤ 1 MiB 的完整 result 查询 | 应用入口至序列化完成 | p95 ≤ 1 s，p99 ≤ 2 s |
| NFR-L03 | 本地 identity search | 本地索引/数据库，不含在线刷新 | p95 ≤ 1 s，p99 ≤ 2 s |
| NFR-L04 | create、cancel、retry 控制请求 | 返回已持久化任务/run 标识 | p95 ≤ 750 ms，p99 ≤ 1.5 s |
| NFR-L05 | queue-to-running | 任务持久化至 worker 获得租约 | p95 ≤ 5 s，p99 ≤ 10 s |
| NFR-L06 | 固定完整分析任务 | 创建至终态，固定 fixture + LLM stub | p50 ≤ 15 s，p95 ≤ 60 s，p99 ≤ 120 s |
| NFR-L07 | 异步导出创建 | 请求至返回 export task ID | p95 ≤ 750 ms，p99 ≤ 1.5 s |
| NFR-L08 | 固定报告导出完成 | 任务创建至文件可下载 | Markdown p95 ≤ 10 s；PDF p95 ≤ 30 s |

`refresh_online=true`、真实 provider 和真实 LLM 的耗时只计入 `ONLINE-SMOKE`，必须分解为
排队、来源、LLM、存储和渲染阶段，不能把未知外部耗时隐藏到“应用延迟”中。

### 3.2 前端

生产构建在桌面 Chrome 的受控 `FRONTEND` 剖面中应满足：

| ID | 指标/场景 | 初始阈值 |
| --- | --- | --- |
| NFR-F01 | LCP | p75 ≤ 2.5 s |
| NFR-F02 | INP | p75 ≤ 200 ms |
| NFR-F03 | CLS | p75 ≤ 0.1 |
| NFR-F04 | 资产切换 | 下一渲染帧清空旧资产结果；旧请求不能回写 |
| NFR-F05 | 任务轮询 | 每个可见页面、每个当前 task 最多一个活动轮询 |
| NFR-F06 | 终态收敛 | 收到 `SUCCEEDED/FAILED/CANCELLED` 后一个轮询周期内停止 |
| NFR-F07 | 错误可恢复 | 网络恢复或用户重试后不刷新整页即可恢复 |

LCP/INP/CLS 是受控工程基线，不是公网真实用户 SLA。首次移动端或低配置设备放量前必须建立
独立剖面，不能沿用桌面结果推定通过。

## 4. 容量和资源上限

### 4.1 固定容量场景

| ID | 场景 | 负载 | 通过条件 |
| --- | --- | --- | --- |
| NFR-C01 | 控制面读取 | 50 个并发客户端持续 5 分钟 | 错误率 < 1%；满足 NFR-L01/L02；连接池无耗尽 |
| NFR-C02 | 任务创建突发 | 30 秒内 20 个 create 请求，含重复幂等键 | 只产生预期任务/run；无重复执行；请求满足 NFR-L04 |
| NFR-C03 | 多资产 worker | worker 并发 4、每来源并发 2，混合资产固定 fixture | 无越权、无卡死、无来源并发超限 |
| NFR-C04 | 影子调度批次 | 一个周期 100 个已批准标的，不做全市场扫描，不生成完整 LLM 报告 | 30 分钟内收敛到终态；失败可单独重试 |
| NFR-C05 | 前端观察者 | 50 个轮询客户端观察混合终态任务 | 服务稳定；终态停止轮询；指标标签无基数爆炸 |

规划默认值为：

```text
worker_concurrency = 4
per_source_concurrency = 2
scheduled_instruments_per_cycle = 100
```

这些值必须配置化，并受数据库连接池、provider 限流和 LLM 预算三者中最小上限约束。扩容前
必须重跑 `CAPACITY`；不得通过全市场扫描、无限队列或无界并发隐式扩大容量。

当前代码已将三个规划默认值落实为
`ASSET_RESEARCH_SCHEDULE_MAX_BATCH=100`、
`ASSET_RESEARCH_SCHEDULE_WORKER_CONCURRENCY=4` 和
`ASSET_RESEARCH_SOURCE_MAX_CONCURRENCY=2`：每轮已认领的 schedule 使用有界 worker
池执行，所有共享同一 server-declared source 的交互/调度采集共享来源 semaphore；动态或
未声明来源统一落入保守的 `UNDECLARED` bucket。`test_schedule_runner.py` 与
`test_source_concurrency.py` 覆盖这些上限。

2026-08-03（Asia/Shanghai）已使用本机 MySQL **9.4.0** 的一次性、已迁移至
`20260810_asset_research_option_context_binding` 的 schema 实测 NFR-C03/C04：
`scripts/ci/run_asset_research_capacity.py` 拒绝非 MySQL 或非
`codex_iter191_capacity_*` schema，并在固定 100 个批准期货合约、无 LLM 的夹具上经真实
schedule 持久化路径运行。结果记录于
[traceable capacity evidence](./evidence/2026-08-03-mysql-capacity-traceable.json)：100/100
`SUCCEEDED`，batch 为 1.210 s，完整 claim p50/p95/p99 为
0.0444/0.0473/0.0937 s，worker/source 峰值为 4/2，MySQL `Threads_connected` 为 1→1，
CPU user/system 增量为 0.798/0.064 s，RSS 峰值为 165,675,008→177,651,712 bytes；无 due、
lease、retry 或非终态 run，且没有交互 task/report。固定 provider 不使用缓存，因此 JSON
将 cache 明确记录为 `applicable=false`；300 条 `PENDING` outcome 作为评分积压被记录而未
隐藏。证据同时带有 runner、config、concurrency、orchestrator 和 scheduler 的 SHA-256，避免
将未提交工作树误记为仅由 `commit_sha` 覆盖。

该实测只完成固定夹具上的 NFR-C03/C04，**不是** NFR-C01/C02/C05、API/前端 SLA、真实
provider/LLM 成本、故障恢复或生产 SLO 的结论；这些项目仍需各自的受控剖面和审批。

### 4.2 资源保护

- 队列、响应体、上传、导出、外部响应和日志字段必须有显式尺寸上限；
- 单个用户、来源和资产类型必须支持并发/速率配额，管理员任务也不能绕过全局保护；
- worker 必须使用公平队列或等价机制，避免一个资产类型长期饿死其他资产；
- 大结果应分页或通过受控下载返回，不应占用 API worker 长时间传输；
- 容量超过已测上限时应排队、限流或拒绝，不能静默降低数据质量。

## 5. 韧性、幂等和恢复

### 5.1 外部调用策略

以下为规划默认值，上线前按来源注册表覆盖：

| 配置 | 默认值 | 规则 |
| --- | --- | --- |
| 连接超时 | 5 s | 必须小于总超时 |
| 读取超时 | 15 s | 大文件使用单独受控配置 |
| 单次总超时 | 30 s | 超时必须记录阶段和 source ID |
| 自动重试 | 最多 2 次 | 仅幂等调用；指数退避加抖动 |
| 断路触发 | 60 s 内连续 5 次失败 | source 维度，不按 symbol 建断路器 |
| 断路时间 | 60 s | 半开只允许一个探测请求 |

429 应遵循合法的 `Retry-After`，不得在同一请求中无限等待。认证失败、授权撤销、Schema
不兼容、输入错误和确定性质量失败不得自动重试。

只有在来源授权、数据新鲜度和任务用途允许时才能使用旧缓存；结果必须显示 `as_of`、
`fetched_at`、`stale=true` 和降级原因。没有合规缓存时应返回“来源不可用”，不能生成看似
完整的数据。

### 5.2 任务一致性

- create 接口必须接受幂等键；同一用户、同一规范化请求和有效时间窗内不得重复执行；
- worker 用有期限租约认领 run，并记录 owner、heartbeat、attempt 和 lease expiry；
- 进程中断后，过期租约必须被恢复器判定为可重试或失败，不能永久停留在 `RUNNING`；
- retry 必须创建新的 run，保留原失败 run，不得覆盖审计事实；
- cancel 必须是可重复操作；进入终态后再次取消返回当前终态，不触发新副作用；
- 每次 run 固定 `cutoff_at`、输入 hash、数据快照、代码/配置/模型版本和来源版本；
- 写入结果和终态必须在可证明一致的事务边界内，发布和通知使用 outbox 或等价幂等机制。

### 5.3 恢复目标

T1 故障注入必须证明：

- worker 在来源调用前、调用后、结果写入前和终态写入后崩溃均不产生重复发布；
- 数据库短暂不可用后任务恢复，无法恢复时进入带 reason code 的 `FAILED`；
- 队列或调度器重启后，遗漏运行能被检测且不跨过冻结的 `cutoff_at`；
- LLM、导出和发布失败不删除已完成的确定性分析结果；
- 回滚后旧股票路径仍可读，双写差异可核对。

首次测量需记录恢复时间分布。生产 RTO/RPO 必须根据部署拓扑、备份和业务等级另行批准，
本文不预先承诺客户 RTO/RPO。

## 6. 可配置数据生命周期

### 6.1 规划默认值

所有持久化类别必须具有实际列 `retention_class`、`retention_expires_at`、
`legal_hold`、`tombstoned_at` 和来源/地域覆盖规则。`retention_expires_at` 不能复用
持仓上下文等领域对象的业务 `expires_at`。以下值是 P0b 的实现起点，须经安全、合规
和数据授权负责人批准后才能用于生产：

| 数据类别 | 热存储 | 归档/最长保留 | 规划默认处理 |
| --- | --- | --- | --- |
| 公共来源原始响应 | 90 天 | 365 天 | 加密归档；保留来源、hash 和时间 |
| 许可来源原始响应 | 不超过合同且默认 ≤ 90 天 | 仅合同明确允许时 | 取合同和配置的更短值 |
| 授权未知的原始响应 | 任务内临时 | 24 小时 | 默认不归档，暂停来源启用 |
| 规范化快照/特征 | 365 天 | 按模型复现需要批准延长 | 保留 lineage，不保留多余个人信息 |
| 任务、run、渲染报告和交互分析结果 | 365 天 | 经批准可延长 | 到期后删除用户交互内容，保留最小审计墓碑 |
| 预测、outcome、模型卡和决策审计 | 7 年 | 法规/政策要求的更长值 | 规划值，生产前必须合规确认 |
| 临时导出和下载令牌 | 30 天 | 不归档 | 到期撤销并删除文件 |
| trace | 14 天 | 不归档 | 对 ID 脱敏 |
| 聚合 metrics | 90 天 | 按容量趋势批准延长 | 禁止 symbol/user 高基数标签 |
| 应用错误/安全日志 | 30 天 | 事件 legal hold 可延长 | 敏感字段脱敏 |
| AI 调用元数据 | 90 天 | 不保存无必要的完整提示 | 保留 tokens、费用、版本和状态 |

若法规、用户删除权、数据合同或安全政策要求更短期限，采用更短期限；合法保全
`legal_hold=true` 时暂停删除，但必须记录批准人、原因和复核日期。

### 6.2 清理控制

生命周期任务必须：

1. 先生成 dry-run 清单和预计释放量，不直接按模糊时间条件删除；
2. 验证 legal hold、数据来源合同、地域和关联模型复现要求；
3. 按导出/发布副本、报告、结果、特征、快照/原始数据的依赖顺序处理；
4. 分批、限速、可重入，记录扫描数、删除数、跳过数、失败数和原因；
5. 保存不含业务内容的最小审计墓碑；
6. 对失败批次告警并可安全重试；
7. 用到期、未到期、legal hold、授权撤销和跨方言 fixture 验收。

当前实现只提供 `AssetResearchRetentionService.plan_dry_run()`：它按表有界地读取已到期、
legal hold 和既有 tombstone 的分类，并发布不含 record/user/symbol 标签的汇总指标；**不会删除、
去标识化或回收对象存储内容**。真正的执行器必须先完成许可/地域/依赖检查、审批和专门的
跨方言验收，不能把 dry-run 视为已完成清理。

修改保留期必须走交付治理的变更控制，并评估备份、对象存储、搜索索引和已发布副本，不能只
删除主数据库记录。

## 7. 增量可观测性

### 7.1 复用现有能力

实现必须增量复用仓库现有能力，而不是建设第二套孤立监控：

- `src/backend/app/telemetry.py`：环境开关控制的 OpenTelemetry，已有 FastAPI、
  SQLAlchemy 和 httpx instrumentor；
- `src/backend/app/middleware/metrics.py` 与 `src/backend/app/api/metrics.py`：
  Prometheus 指标定义和 `/metrics` 暴露能力；
- `src/backend/app/services/monitoring_service.py` 与 `src/backend/app/api/monitoring.py`：
  通用运行监控和查询接口；
- `src/backend/app/api/ai_observability.py`：AI 调用次数、失败、延迟分位、token 和费用；
- `src/backend/app/middleware/logging.py`：请求性能和慢请求日志。

P0b 必须用启动测试证明 telemetry、metrics 和 monitoring 在目标部署中实际注册并可查询。
现有 Prometheus helper 或路由“文件存在”不等于已接线；若依赖可选，则部署清单必须显式安装
并在缺失时启动失败或明确关闭该能力，不能静默无指标运行。

### 7.2 Trace 和结构化日志

关键 span 至少包括：

```text
asset_research.task
asset_research.identity.resolve
asset_research.source.fetch
asset_research.plugin.normalize
asset_research.quality.gate
asset_research.feature.build
asset_research.decision
asset_research.report
asset_research.export
asset_research.publication
```

任务日志必须携带 `trace_id`、`task_id`、`run_id`、`user_scope`（不可逆标识）、`asset_type`、
`canonical_id`、`cutoff_at`、`source_id`、版本和 reason code。认证令牌、密钥、完整提示、
许可原文和不必要的个人信息不得进入日志。

当前 P0b 的日志边界会在所有 Loguru sink 写入前递归脱敏 message、context 和 exception 中的
常见凭据文本，并关闭错误 sink 的局部变量诊断；该措施与快照、公开报告、导出和知识库发布的
递归脱敏共同构成“不得持久化凭据”的代码门禁。它不替代生产密钥管理、trace 后端配置或真实
来源的许可验收。

### 7.3 指标

新增指标使用有界标签：

```text
asset_research_task_total{asset_type,status}
asset_research_task_duration_seconds{asset_type}
asset_research_queue_depth{asset_type}
asset_research_source_request_total{source_id,result}
asset_research_source_duration_seconds{source_id}
asset_research_schedule_run_total{asset_type,status}
asset_research_schedule_lateness_seconds{asset_type}
asset_research_prediction_reuse_total{asset_type}
asset_research_outcome_total{asset_type,status}
asset_research_outcome_backlog{asset_type}
asset_research_export_total{format,status}
asset_research_publication_total{target,status}
asset_research_llm_tokens_total{asset_type,stage,model_tier}
asset_research_llm_cost_usd_total{asset_type,stage,model_tier}
asset_research_llm_fallback_total{asset_type,fallback_stage,reason}
asset_research_migration_reconciliation_total{mapping_version,classification}
asset_research_lifecycle_total{retention_class,result}
```

`symbol`、`canonical_id`、`task_id`、`run_id`、`user_id`、自由文本错误和 URL 不得作为指标标签；
它们只进入受控日志或 span。`source_id`、`target`、`stage`、`model_tier`、
`fallback_stage/reason`、`mapping_version/classification` 必须来自注册表或版本化受控枚举。
不可评分率由 `asset_research_outcome_total{status="UNSCORABLE"}` 除以同 cohort 的成熟结果
计算；LLM 回退率和迁移 `DEFECT` 率分别从上述专用 counter 计算，不能从自由文本日志估算。

当前 P0b 实现并已由单元测试覆盖的 series 为：任务/来源/调度/reuse/outcome/export/publication/
lifecycle 共十二项（不含 `asset_research_queue_depth`、LLM 与迁移对账）。导出和发布只在一项
新的终态工件操作完成后记一次，幂等命中不会重复计数；格式/目标均收敛到受控枚举或 `UNKNOWN`。
来源指标只在
`AssetSourceRegistryPolicy` 返回 `ACTIVE` 或已注册的 `BLOCKED` 来源时使用其 registry ID；
未注册来源统一记为 `UNREGISTERED`，而 URL、标的、用户和任务标识均会被拒绝作为标签。其余
series 仍是 T1 Gate，不能因指标名称已列在本文件而被视作已接线。

### 7.4 默认告警和仪表盘

以下是 T1 告警演练阈值，生产前按真实流量校准：

| 告警 | Warning | Critical | 首要动作 |
| --- | --- | --- | --- |
| 任务失败率（排除注入/用户取消） | 10 分钟 > 5% | 10 分钟 > 10% | 按 asset/source/reason 定位，暂停受影响插件 |
| 来源连续失败 | 3 次 | 60 秒内 5 次 | 断路并检查授权/Schema |
| 队列积压 | > worker 数 2 倍持续 10 分钟 | > worker 数 5 倍持续 10 分钟 | 限制创建，检查 worker/来源 |
| 调度遗漏 | 计划时间 + 5 分钟 | 连续 2 个周期 | 禁止追赶式全量并发，逐批恢复 |
| 评分积压 | oldest > 对应 evaluator SLA | oldest > 2 倍 SLA | 检查来源成熟、评分 worker 和日历 |
| 迁移结构化对账 | 任一非预期差异 | `classification=DEFECT` 任一条 | 停止 cohort 放量并回退新读/双写 |
| LLM 日/月预算 | 80% | 100% | 执行第 8 节降级/停止 |
| 生命周期任务 | 单批失败 | 连续失败或超期保留 | 停止清理，保护 legal hold，人工核对 |
| 指标/trace 缺口 | 关键指标 5 分钟无数据 | 10 分钟无数据且有业务流量 | 按监控故障处理，不视为业务健康 |

仪表盘至少展示任务吞吐/状态/延迟、队列、来源成功率/延迟、schedule lateness、
评分积压与不可评分率、LLM tokens/费用/回退率、迁移对账分类、导出/发布、生命周期
清理和各资产插件启停状态。每个 P0b/P0c Gate 要保存一次告警注入和恢复截图或机器可读记录。

## 8. LLM Token、费用和降级

### 8.1 每任务预算

按分析深度设置请求与响应的合计 token 上限：

| 深度 | 每任务总 token 规划上限 | 报告输出上限 | 用途 |
| --- | --- | --- | --- |
| `quick` | 12,000 | 2,000 | 摘要和确定性结果解释 |
| `standard` | 30,000 | 4,000 | 默认研究报告 |
| `deep` | 60,000 | 6,000 | 明确授权的深度研究 |

上述每任务预算用于交互报告或明确批准的报告任务。每日影子批处理默认
`llm_full_report_enabled=false`，完整 LLM 报告 token 预算为 0；它只保存结构化预测、证据、
质量原因和后续 outcome 所需输入。若要对受控样本生成完整报告，必须显式配置样本 cohort、
批准模型、单任务及日/月预算，并按交互报告计费和观测，不能改变影子批处理的默认行为。

所有环境还必须设置非零的用户日预算、环境日预算和环境月预算。具体金额由产品/SRE/财务批准，
不得把无限额或供应商默认额度作为配置。输入、输出、重试、失败请求和降级请求全部计费并
计入预算。

### 8.2 调用控制

- 每个阶段在调用前估算 token；预计超预算时不得先调用再截断；
- 相同 `report_input_hash + prompt_version + approved_model_version` 可复用合规缓存；
- 瞬时 429/5xx 最多自动重试 1 次；确定性输入/授权/内容错误不重试；
- 输出必须受结构化 Schema 和最大 token 限制，解析失败不得循环重问；
- 模型、prompt、输入 hash、tokens、费用、延迟、缓存命中和降级原因接入现有 AI observability；
- LLM 只能解释已记录的数据与确定性结论，不能修改 identity、质量门禁、动作真值或模型状态。

### 8.3 降级阶梯

```text
首选已批准模型
  → 同治理等级的低成本已批准模型
  → 基于确定性结果的结构化模板报告
  → 返回可重试的明确失败（保留已完成分析）
```

只有模型风险批准人允许的模型才能出现在第一、二级。预算达到 80% 时停止非必要扩写和深度
模式；达到 100% 时停止新的 LLM 调用，但继续提供确定性指标、质量原因和模板报告。任何降级
都必须在结果和报告中可见，不能用占位文本伪装成完整 AI 分析。

## 9. 前端任务状态机

### 9.1 单一状态所有权

现有 `src/frontend/src/composables/useStockAnalysisTask.ts` 已实现 2.5 秒轮询、终态停止和错误
处理。多资产实现必须从它提取/泛化通用内核，例如 `useAssetAnalysisTask`，旧 composable
保留为兼容包装；不得在 `AssetAnalysisPage.vue` 或资产面板中再写第二套 `setInterval`。

任务状态属于 composable。只有跨路由偏好、最近历史或共享缓存需要 Pinia；页面局部展示状态
不应为了“统一”全部迁入全局 store。

### 9.2 状态及转换

前端 UI 状态：

```text
IDLE
  → RESOLVING → READY
  → SUBMITTING → QUEUED → RUNNING
  → SUCCEEDED | FAILED | CANCELLED
```

允许从 `FAILED/CANCELLED` 经显式 retry 回到 `SUBMITTING`，retry 返回新 run/task 标识后再进入
`QUEUED`。不允许从任意旧请求直接覆盖新资产的 `READY/RUNNING/SUCCEEDED`。

兼容映射：

| 旧股票状态 | 公共状态 |
| --- | --- |
| `pending` | `QUEUED` |
| `running` | `RUNNING` |
| `completed` | `SUCCEEDED` |
| `failed` | `FAILED` |
| `cancelled` | `CANCELLED` |

未知状态必须进入可见错误并停止轮询，不得默认解释为 `RUNNING`。

### 9.3 轮询和竞争控制

- 默认轮询间隔保持现有基线 2.5 秒，并配置化；
- 连续网络错误采用 2.5、5、10、20 秒上限退避，成功后恢复默认；
- 页面隐藏时暂停轮询；恢复可见时立即查询一次，再恢复周期；
- 终态、组件卸载、用户取消、切换资产或开始新任务时必须停止旧计时器；
- 每次切换生成新的 request generation，并用 `AbortController` 或等价机制取消旧请求；
- 响应写入前必须同时校验 `asset_type + canonical_id + task_id/run_id + generation`；
- 切换资产后先清空结果、错误和导出/保存上下文，再开始 identity resolve；
- cancel/retry 按钮必须防双击，并显示服务端确认后的状态；
- composable 对外暴露只读状态和 `resolve/create/cancel/retry/reset` 动作，页面不能直接改任务终态。

### 9.4 前端验收场景

至少覆盖：

1. A 资产慢响应后切换 B，A 响应不能覆盖 B；
2. 任务从 `QUEUED → RUNNING → SUCCEEDED`，只存在一个计时器且终态停止；
3. 取消和重试产生正确的新 run，不复用旧终态；
4. 429/500/断网触发退避，恢复后无需整页刷新；
5. 页面隐藏/显示不产生额外计时器；
6. 未知状态、无权限和已删除任务显示明确错误；
7. 旧 `/investment/stock-analysis` 页面及旧状态映射保持兼容。

## 10. 安全、隐私和可访问性

T1 还必须满足：

- 所有 task/result/report/export/monitoring 查询均按用户或授权租户隔离；
- 外部 URL 只允许注册来源的协议、域名和地址范围，并限制重定向、响应尺寸和并发；
- 密钥只来自密钥管理或环境配置，不写入数据库业务字段、日志、trace、前端 bundle 或报告；
- 导出下载使用短期、单用途授权；过期后不可访问；
- 错误返回 reason code 和安全摘要，不回显堆栈、SQL、token 或 provider 凭据；
- 表单、状态、错误、图表摘要和操作按钮支持键盘导航、可见焦点和语义标签；
- 不能只用颜色区分成功、失败、风险或 stale；动态状态通过可访问 live region 通知；
- 七个现有 locale 至少保证键完整；未完成专业翻译时可回退英文，但不得显示裸 key。

## 11. 验收与证据

### 11.1 最低执行集

实际测试路径以当前仓库为准；Python 命令必须使用 Anaconda：

```bash
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base \
  pytest src/backend/tests -m "not e2e"

/Users/yunjinqi/opt/anaconda3/bin/conda run -n base \
  ruff check src/backend

cd src/frontend
npm run typecheck
npm run test
npm run build
```

还必须单独执行并归档：

- 目标 MySQL 9.4.0（InnoDB）的 Alembic upgrade/downgrade、约束和并发验收；
- `FIXTURE`、`CAPACITY`、`FAILURE` 和 `FRONTEND` 四类剖面的原始报告；
- `/metrics` 抓取、trace 贯通、monitoring 查询和告警注入；
- 生命周期 dry-run/删除/legal hold；
- LLM 80%/100% 预算与模型不可用降级；
- 旧股票页面、API、状态、历史结果、导出和保存回归。

仓库的通用 pytest 若通过 fixture 把会话替换为 SQLite，只能证明对应应用逻辑，不能替代
MySQL 9.4.0 的迁移、外键、唯一约束、锁和事务语义验收。

### 11.2 T1 完成清单

- [ ] NFR-L01 至 L08 在规定剖面达到阈值并保存分位原始数据；
- [ ] NFR-C01 至 C05 通过，资源和未终结任务无持续增长；
- [ ] 超时、断路、租约恢复、幂等、取消、重试和回滚均有失败注入证据；
- [ ] 生命周期所有类别均有显式配置、批准人和清理测试；
- [ ] 现有 telemetry/metrics/monitoring 已接线，新增指标无高基数标签；
- [ ] 默认告警和仪表盘经过触发与恢复演练；
- [ ] LLM 每任务/日/月预算、费用统计和四级降级链已验证；
- [ ] 前端只使用一个任务状态机，资产切换、终态和网络恢复场景通过；
- [ ] 用户隔离、外部访问、密钥、导出和可访问性检查通过；
- [ ] 所有偏差按 [交付治理](./DELIVERY_GOVERNANCE.md)登记并完成 Gate 复判。
