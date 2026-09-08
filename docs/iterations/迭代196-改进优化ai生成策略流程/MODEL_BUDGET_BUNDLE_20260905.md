# 模型 Token／金额联合预算：本地实现与验收边界

日期：2026-09-05。对应 FR-TASK-009、FR-PIPE-010、AC-QUOTA-001/002。

本批目标是在真实 generation factory 的外部调用前，同时封存请求、计算保守计费上界并原子预留两种资源。验证使用本地 HTTP transport seam 和合成计费契约，不是供应商账单或真实 Tokenizer 的验收。迭代整体仍为 **NO-GO**。

## 1. 实现范围与信任前提

候选代码位于 `/Users/yunjinqi/Downloads/backtrader_web/.worktrees/codex/iteration-196-ai-research-trust`，不是主 checkout 的运行服务；本批没有启用 feature flag、访问真实供应商、修改业务库或部署。

| 层 | 实现合同 |
| --- | --- |
| HTTP adapter | `prepare()` 无 IO，生成不可变 `PreparedProviderRequest`；`generate_prepared()` 校验 route/model/endpoint hash、字段白名单和输出 cap，只发送同一份 bytes，不重新序列化 |
| Accounting policy | `ModelAccountingPolicy` 严格校验 schema、版本、独立配置的 canonical hash pin、凭证摘要、模型/路由、有效窗及 all-inclusive 契约；未知字段、bool/float 金额、非 UTC 时间、空/错 hash 均拒绝 |
| Quote | 以契约声明的最大可计费输入 Token 为保守输入上界，加本次请求的输出 cap；与总 Token 限额、政策输出限额、32 位整数金额边界比较 |
| Quota | Token 与 `model_cost_microusd` 在同一事务预留；完整组在同一事务 claim、结算；缺项、旧 fencing、窗口/取消/阶段变化或第二项 CAS 失败均不能留下部分成功 |
| Gateway | 发送前重新准备并逐 bytes 比对请求、复核政策 pin/数据库时间、要求完整两项 receipt；同一 operation 只准 claim 一次 |
| Ledger | 每项 reservation 的 nullable JSON `reservation_context` 都保存同一个 quote 快照；request hash 是该快照的 canonical hash；调用摘要保存 quote/policy hash、reservation IDs 和计费口径 |
| Generation factory | 显式要求 ACCOUNTING_POLICY_JSON/HASH，缺失即构建失败；只选择当前 owner、quota policy 与时间窗口下唯一的 Token／金额 bucket，浏览器不能选择这些政策 |

**审核 pin 不是外部事实证明。** `evidence_hash` 与政策 hash 只绑定部署审核材料；程序不会因为填入一个 hash 或配置数字，就知道供应商是否实际遵守它们。正式启用前，部署负责人必须独立证明：

1. `max_billable_input_tokens` 是该精确 endpoint/model 的所有请求（包括失败请求）可计费输入上界，包含消息封装、供应商注入内容、缓存及其他收费类别；超限请求不能先产生超过上界的费用再拒绝；
2. `max_tokens` 对该模型约束所有可计费输出；存在未包含的隐藏 reasoning/tool/image 等计费类型时，该纯文本契约不能启用；
3. 输入/输出费率及固定费用覆盖所有附加项、最低收费、计费粒度及货币转换，且供应商按请求接受时的审核价格处理该调用；
4. 有效期、模型/端点变化和价格变更能触发新版本审核与旧政策失效；配置来源是受控部署制品，而非用户输入。

普通 context-window 数字或本地字符估算不能充当这份合同；聊天 Token 计数会随模型和请求格式改变。官方示例也把聊天计数列为估算，不能推导出所有供应商通用的硬保证。[OpenAI 官方计数示例](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb)

## 2. 单位、计算与结算口径

Token 资源固定 `model_tokens/tokens`；金额资源固定 `model_cost_microusd/microusd`，1 USD = 1,000,000 microUSD。额度和费率使用严格整数，拒绝 bool、float、非正预留和超出有符号 32 位列容量的值。

设 `I` 为契约输入上界，`O` 为本次不可变请求输出 cap；`Ri/Ro` 单位为 microUSD / 百万 Token，`F` 是每次调用固定 microUSD：

```text
Token 预留 = I + O
金额预留 = F + ceil(I × Ri / 1,000,000) + ceil(O × Ro / 1,000,000)
```

输入与输出分项向上取整，防止把两项先合并再取整时低估 1 microUSD。有效政策必须覆盖数据库当前时间到所配置 HTTP timeout 的窗口。claim 等待后会再次读取数据库时间检查；无法确认窗口仍有效时不会发送请求。后续进程调度/供应商行为仍需由受审部署时钟、请求截止和计费合同共同验证，不能把本地检查说成供应商已接受价格。

响应同时具有可信、非负整数的输入和输出计数，所有别名/总量一致，实际观察模型匹配 pin，且两个计数分别不超过各自上界时，按上述同一公式结算 Token 与金额。只有 `total_tokens` 不足以按差异化费率结算。

账本 `accounting_basis=CONSERVATIVE_TARIFF_BOUND` 和 `amount_microusd` 表示“已知用量 × 审核费率得到的保守记账额”，**不是供应商发票上的实际费用**。输入8/输出12、合成费率1,000,000/2,000,000、固定7的测试结算为20 Token与39 microUSD；这些是机制夹具，不是任何真实模型价格。

## 3. 原子性、重试和未知结果

```text
服务端重读输入 → 脱敏/封存 bytes → quote → Token+金额原子预留
  → 请求/政策重验 → 完整组一次性 claim → 同 bytes HTTP
  → 模型/用量验证 → 完整组原子结算 → 不可变调用记录 → typed materialization
```

- 同组以 task、stage attempt、idempotency key、quota policy、request hash 及相同快照绑定；少给任何 receipt 均不能派发或部分结算。
- 严格 gateway 必须显式设置 `require_reservation_context=True`，quota 在锁定组内要求非空 `model-budget-quote-v1` 快照、canonical 完全相同且 hash 相符；只有正确 request hash、却没有持久快照的组也拒绝派发。该 flag 仅接受真实 bool 且组内一致，generic 旧 None-context 路径保留兼容，不代表严格预算可以省略快照。
- 原子 claim 的每个 CAS 都重检数据库时间、bucket 窗口/资源/政策、task stage/lease/取消状态与 attempt stage/lease。SQLite 竞争测试使用文件库 + NullPool 的独立连接，不以共享内存连接模拟独立事务。
- 超时、响应丢失、非预期模型、缺失或矛盾 usage、某项用量越界，保持两项 `IN_FLIGHT`，不创建 candidate，不零计费，不以 lease 过期自动释放，不重复发 HTTP。
- 派发前请求或政策漂移：拒绝调用，已经建立的两项 `RESERVED` 仍保留；本批未新增“可证明未执行”的自动释放器，后续应由显式 no-op/reconciliation 流程处置。
- 原 single-resource API 为兼容已有注入式测试/其他资源而保留；真实 `generation:create_worker` 强制联合预算。不能由此宣称所有 legacy/improver/repair/Sandbox 入口已经统一迁移，AC-QUOTA-002 仍需逐入口完成。
- 独立审查发现旧逐笔 `resolve_reconciliation` 会先恢复一个 bucket、甚至允许同一 operation 的 Token／金额得出相互矛盾的结论。本批已禁止受绑定联合预算经旧单笔 claim/mark/settle/release/resolve API 处置，返回 `RESEARCH_QUOTA_BUNDLE_OPERATION_REQUIRED`，拒绝前后全组与 bucket 状态不变；完整 provider-readback/group reconciler 尚未交付，未知组只能保守保留，不能手动调两次旧接口冒充联合恢复。
- 外部调用、quota 结算、invocation append 与 candidate materialization 不是一个分布式事务；quota 到 ledger 的崩溃窗口需后续 operation readback/reconciler/outbox 合同闭合。本批持久化 pre-dispatch quote，未伪称已实现供应商自动对账。
- 当前 `provider_operation_id=llm:<reservation>:<fence>` 是本地识别符，没有发送为供应商幂等/查询键。超时后可能连 provider request ID 都未取得；body hash 只能辅助审计，不能证明供应商支持按该 hash 查询。后续必须为支持该能力的供应商设计受审 idempotency/readback adapter，不能靠本地 ID 模拟供应商已确认执行/未执行。

## 4. 配置与迁移

新增静态配置（根目录与 backend `.env.example` 同步）：

```text
AI_RESEARCH_PROTOCOL_V2_GENERATION_ACCOUNTING_POLICY_JSON=
AI_RESEARCH_PROTOCOL_V2_GENERATION_ACCOUNTING_POLICY_HASH=
AI_RESEARCH_PROTOCOL_V2_GENERATION_RESERVED_TOKENS=0
```

最后一项现在明确为每调用输入＋输出总 Token 上限，而不是只约束输出或直接照抄为固定预留。两项 ACCOUNTING 设置默认为空，保持不能误启用的行为。政策详细字段以 `model_budget.py` 的严格 schema 为准，仓库不提供伪装成真实可用价格的默认合同。

工厂还要求 quota lease 至少为 `ceil(provider timeout) + 30 秒`；30 秒是显式的本地结算余量，不是数据库延迟 SLA。短于该范围的配置在构建时拒绝；仍需在部署压测中验证连接等待、续租和处理延迟，不能用这个下限取代 lease/operation 恢复设计。

新 head `20260905_ai_research_budget_context`，父版本 `20260905_ai_research_provider_model`，仅给 `ai_research_quota_reservations` 增加 nullable JSON `reservation_context`。历史 NULL 表示当时没有绑定证据，不按现价回填；真实部署前需更新数据库，再发布引用新字段的 worker。降级会移除非空 quote 快照，因此生产回退必须先停派发、导出并核对快照/未结操作，不能把 schema 可降级误说成审计证据可无损删除。

## 5. 验证证据与后续工作

TDD 已先观察到：缺少模型字段、缺少 prepare/预算接口、配置缺合同仍能构建、输入＋输出上限未检查、只产生一项 reservation、缺金额额度仍发 HTTP，以及正确 hash 但无持久快照仍发 HTTP 的失败；后续实现修复这些路径。负例还覆盖过期政策、封存后 input/price 漂移、部分 receipt、只有总 Token、单项用量超上界、双连接竞争、第二 claim CAS 拒绝和第二结算 bucket 更新拒绝后的完整回滚。

各次统一6-worker回归、源码摘要、JUnit 和当前迁移结果以 [回归记录](REGRESSION_6_WORKERS_20260905.md) 与 [迁移验收](CURRENT_HEAD_MIGRATION_20260905.md) 的本批条目为准，不拼接历史通过数量。

本地仍需继续：生成后的沙箱执行/独立 evaluator/审批任务图、完整统一调用入口、group reconciliation/外部账单 readback、全链 invocation 与 operation 崩溃恢复，以及当前候选 authenticated UI/API 重验。环境验收仍需真实供应商计数/费用契约及账单、PostgreSQL/MySQL 多连接联合预算故障矩阵、真实隔离执行、T2 冷重放与 T3 前向观察。**本批联合预算不能替代这些原 P0 或发布门禁。**

前端本批未修改：现有金额格式器只显示 actual-style `amount/total_cost`；新保守记账字段不会被误显示为真实账单，仍呈现“不可用”。后续工作台需要分别展示保守额度、用量与实际账单，并补当前 authenticated API/UI 验收；不能宣称本次已有新的费用界面交付。
