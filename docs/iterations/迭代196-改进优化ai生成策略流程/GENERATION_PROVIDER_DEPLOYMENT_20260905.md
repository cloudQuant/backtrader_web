# 迭代 196：模型生成部署接线与本地链路验收

日期：2026-09-05。实现仅位于候选工作树 `codex/iteration-196-ai-research-trust`，未提交、未部署。双 feature flag 默认关闭；没有读取生产凭据、调用真实供应商或重启常驻服务。

## 1. 本批交付与成功含义

新增 `OpenAICompatibleResearchProvider` 和显式 `app.research_deployments.generation:create_worker` 组合根。配置的固定模型、prompt、采样参数、quota policy 和受控文件 resolver 进入真实服务对象；组合根把同一个 DatasetRegistry 注入生成执行器和物化服务，不能漏装 materializer 后仍宣称生成成功。原 `explorer:create_worker` 保留诊断用途，没有自动切换。

本地连接测试通过公开 `worker.run_once()` 执行：

```text
已确认假设 + 文件 receipt + 预检 + 服务端 user quota
  → 持久任务领取 → CLARIFY 回执 → GENERATE
  → 实际 HTTP adapter（仅网络 transport 使用 MockTransport）
  → 模型身份/用量校验 → quota settlement → invocation 账本
  → 原子 candidate/artifact/materialization/checkpoint → 任务终态
```

正向终态只表示 **`MATERIALIZED_NOT_EXECUTED`**：候选仍为 `MUTABLE`，没有试验、回测、Evaluator、审批或 Sandbox 执行。负向模型不匹配时任务失败、无候选，reservation 保持 `IN_FLIGHT` 等待显式核对；再次轮询不重复派发。该测试使用真实本地 SQLite 事务与受控文件字节，但数据内容是测试样例，不是可研究的真实行情。

## 2. 模型调用与配置契约

| 边界 | 当前实现 |
| --- | --- |
| 路由 | 仅部署配置的 HTTPS `/chat/completions`；拒绝 URL 用户名/密码、query、fragment、异常端口/路径；请求不能重写模型或 endpoint |
| HTTP | 单次请求、不重试、不跟随重定向、不隐式使用环境代理；API key 只进入 Authorization header，SecretStr 不在配置 repr 中显示 |
| 上限 | 整体 deadline 与 HTTP 阶段 timeout；配置化请求/响应字节上限；拒绝压缩响应、非 JSON、异常 Content-Length、超大流；退出时关闭响应和客户端 |
| 采样 | 仅 `temperature/top_p/seed/max_tokens`；显式 null、非法类型和越界值在配置或 adapter 处拒绝；输出 cap 固定且不得超过 reservation |
| 输出 | 严格 JSON、单 choice、`finish_reason=stop`、非空文本；工具调用、函数调用、拒绝响应、重复 JSON key、NaN/Infinity 均不作为成功输出 |
| 模型身份 | 原 `resolved_model` 保留配置 pin；新增 nullable `provider_reported_model` 记录响应真实 `model` 字段；缺失/不匹配均拒绝成功，不能拿配置值冒充观察值 |
| 账本 | 保留响应 request ID 和 usage；缺失 usage/cost 是未知，绝不补成 0 或伪造美元价格；仅完整可信 token 数可进入既有结算协议 |
| 凭据保护 | 出站 system/input/sampling 递归拒绝携密字段名，发生在 claim 前；其他敏感值继续脱敏。只恢复经严格正整数校验的顶层 `max_tokens` 数值，不放宽通用凭据过滤 |

HTTPX 的阶段 timeout 不等于整个操作的总期限，因此本实现另加整体 deadline；响应资源使用异步 context manager 关闭。[HTTPX 超时文档](https://www.python-httpx.org/advanced/timeouts/)、[HTTPX 异步接口](https://www.python-httpx.org/async/)。兼容接口的响应 `id/model/choices/usage` 字段分别解析，不复用会丢弃实际型号或为未知 usage 填 0 的旧 DTO。[Chat API 参考](https://developers.openai.com/api/reference/resources/chat)。

`provider_id` 是操作者配置的路由标识，不是供应商签名；响应 model 也不是模型权重的密码学证明。供应商静默更换同名模型仍需独立版本治理与外部证明。

配置项在根目录与 `src/backend/.env.example` 中对齐，以 `AI_RESEARCH_PROTOCOL_V2_GENERATION_` 为前缀，分为：

- `PROVIDER_ID/ENDPOINT_URL/MODEL_ALIAS/MODEL_ID/API_KEY`；
- `TIMEOUT_SECONDS/MAX_OUTPUT_TOKENS/MAX_RESPONSE_BYTES/MAX_REQUEST_BYTES`；
- `PROMPT_TEMPLATE_VERSION/PROMPT_CONTENT/PROMPT_CONTENT_HASH/SAMPLING_PARAMS_JSON`；
- `QUOTA_POLICY_VERSION/RESERVED_TOKENS/QUOTA_LEASE_SECONDS`；
- `MATERIALIZATION_POLICY_VERSION/ENVIRONMENT_MANIFEST_JSON`。

还必须显式配置 filesystem resolver 的对象根、receipt store 与字节上限，以及 v2/worker 两个 flag 和 deployment factory 引用。构建 worker 本身不查业务库、不建 quota、不调用供应商。开启这些配置不是本次验收的操作步骤；真实启用仍需单独环境授权及下述门禁。

## 3. TDD 与集成发现

1. Adapter 首次 21 项因实现缺失而 RED；严格模型身份 3 项、迁移 head 1 项分别 RED。实现后 adapter/gateway/migration 初次聚焦为 79 passed（17.30 秒），只是该时点证据。
2. 真正串起公开 worker 后发现 `max_tokens` 被通用脱敏改为 `[REDACTED]`，此前仅替身 Provider 的组件测试未发现。新增 6 项先 RED，修复只保留合法数值、拒绝 bool/null/非正值/字符串；没有将秘密字段整体加入白名单。
3. 实际 adapter→worker→materialization 的匹配/不匹配模型两例通过（2 passed，1.90 秒）。测试夹具曾误用不存在的 `ResearchStageAttempt.created_at`，修正为不依赖无关排序；该夹具错误不当作业务缺陷。
4. 独立审查发现出站映射键本身可携密；新增 system/input/sampling 三类输入 × 三种携密键共 9 项，均先复现失败，再补 claim 前递归拒绝。拒绝后 Provider 调用数为 0、无 invocation，reservation 仍为 `RESERVED`。
5. 阶段/物化/工件新写入统一以数据库 UTC 复核 lease；应用时钟快慢 10 分钟和操作中途过期负例已覆盖。完全相同的终态 checkpoint replay 仍只读。两条历史时间测试改用数据库时间，未放宽生产授权。详见 [派发与阶段租约记录](DISPATCH_SAFETY_20260905.md)。

统一 6 worker 与完整目录终态以 [回归记录](REGRESSION_6_WORKERS_20260905.md) 为准，不能把不同阶段的聚焦计数相加当成当前全量覆盖。

## 4. 数据迁移与回退

新唯一 head 为 `20260905_ai_research_provider_model`，父版本 `20260905_ai_research_dataset_identity`。仅增加可空 VARCHAR(256) 列；历史 invocation 不回填配置 pin，升级后 `provider_reported_model=NULL` 明确表示没有观察证据。

临时 SQLite 与 PostgreSQL 17.7 已实际验证旧 head 历史行→升级→check→降级→重升→check：新列 nullable、历史行保留、观察值仍 NULL、降级时列移除；没有关闭 FK 约束。PostgreSQL 仅 Unix socket，结束后已停止。详见 [迁移验收](CURRENT_HEAD_MIGRATION_20260905.md)。这不是生产运行中任务回滚；有新观察值的生产数据库降级会丢弃该列内容，必须先备份并另做回退授权。

## 5. 未完成项与验收结论

- 本地 adapter/factory 及生成物化连接不再是缺失实现；但生成后的 candidate→独立 evaluation→approval→sandbox 仍未形成部署运行链，属于需要继续开发的工作，不能全部归因于缺凭据。
- `max_output_tokens <= reserved_tokens` **不保证输入 + 输出总 token 或实际费用上界**。输入 token 估算/硬上界、价格版本、供应商账单 readback、共享 bucket 的未知操作对账以及故障恢复仍需完成；当前不能启用为费用安全的真实自主研究运行。
- 缺失/失败调用的模型账本、quota 和 stage 仍有跨事务崩溃窗口；不能宣称外部 exactly-once、完整调用溯源或费用已全部结清。
- MySQL 实际锁/迁移、多进程接管、真实凭据/IAM、不可变行情、独立 Evaluator/Sandbox 及前向窗口仍分别需要验证。
- 本次没有重做当前 authenticated HTTP/UI 演练；旧 UI/API 证据仍为 `HISTORICAL_T1`，没有改写成新 head 的界面验收。

整体保持 **`IMPLEMENTATION_ACCEPTED=NO-GO`、`PROTOCOL_PRODUCTION_ENABLED=NO-GO`**。以上新增本地证据不能提升 T2/T3 或发布门禁。

## 6. 下一批本地交付顺序（不改变原验收范围）

1. **FR-TASK-009 / FR-PIPE-010：派发前的总量与费用上界。** 本地联合预算、不可变 bytes、审核计费合同与 request/policy binding 已新增，详见 [预算交付记录](MODEL_BUDGET_BUNDLE_20260905.md)。下一步仍需 complete-group reconciliation、供应商 readback/账单核对与真实上界证据；不能把合成合同的本地生成链 PASS 写成供应商账单或全入口统一治理已完成。
2. **FR-SEC-001/009 / FR-PIPE-013：物化后的受控执行阶段。** 显式扩展服务端阶段图，lease/quota/fencing 及受证明 runner receipt 同时通过才能提交。能力或 runner 缺失即结构化阻断，不回退到 FastAPI/宿主执行。先做本地合同，再分别验真实容器/IAM。
3. **FR-DATA-005～007/013 / FR-PIPE-005～006：独立评估调度。** 候选/数据/epoch 精确绑定、授权一次性消费、Evaluator-only 输入、结果不得回流生成路径；先完成本地状态机和拒绝测试，再验独立服务身份/queue/storage。人工 evidence/approval 链仍须按原需求完整连接，不因这里分批而从目标删除。

以上顺序是落实既有 P0 的下一步，不是将整个迭代验收缩减为生成组件验收。
