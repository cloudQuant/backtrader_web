# 迭代 196 服务端 GENERATE 执行器增量

日期：2026-09-05。候选工作树 `codex/iteration-196-ai-research-trust`，未提交。当前结论：**执行器组件已实现并通过本地测试，部署 factory/真实 Provider 尚未接通**。

## 1. 组件合同

新增 `app/services/research/generation_executor.py`，公共入口为：

- `GenerationExecutorPolicy(model_alias, prompt_template_version, prompt_content, prompt_content_hash, sampling_params, quota_policy_version, reserved_tokens, quota_lease_seconds=900)`。
- `ResearchGenerationExecutor(gateway=..., dataset_registry=..., policy=...)`。
- `await executor.execute(StageExecutionContext(...))`。

模型 alias、完整 prompt 内容/版本/hash、采样配置与预算由部署政策固定，不读取浏览器 model/bucket 选择、用户 AI 偏好或动态 active prompt。prompt hash 定义为 `content_hash({"prompt": prompt_content})`；采样配置深度快照并冻结，外部随后改写嵌套字典不会改变已创建执行器的请求。

执行顺序：

1. 从数据库重读 owner/run/task/attempt/request hash/lease/status/cancellation，拒绝错误阶段、过期或跨 owner 的上下文。
2. 校验已确认 hypothesis、绑定 dataset/epoch、当前 capability 与有效预检；通过同一个 `DatasetRegistry` 重验服务器证明的数据对象。漂移时保留 `FAILED` 完整性隔离状态，不调用 Provider。
3. Explorer 只接受 `DISCOVERY` 与 `ITERATION_VALIDATION`；`SEALED_HOLDOUT` 和 `FORWARD_OBSERVATION` 均不能用于重新生成。即使通用数据预检支持前向分区，此生成入口也必须拒绝。
4. 只选择当前 user、token 资源、指定 policy、ACTIVE 状态与数据库当前窗口内的唯一 quota bucket；无、多个或额度不足均拒绝，不创建 bucket、不选其他 owner 的预算。
5. reservation 绑定当前 stage attempt，调用注入的 `LlmGateway`。模型接收受控研究元数据，不接收 storage URI 或密封数据字节。
6. 仅接受 `research-generation-v1` 的 JSON 草稿字段（`strategy_code`、`dependency_lock`、`params`）。返回携 invocation ID 和原样输出的 `GenerationMaterializationProposal`，由现有 stage-completion 服务物化；执行器自身不创建 candidate，不执行代码，也没有模板 fallback。

Gateway/Provider 异常统一转换为 `RESEARCH_GENERATION_GATEWAY_FAILED`，避免把供应商异常文本当作 stage/API 错误码透出；具体调用失败在 gateway 账本保留。不得据此推断预算已释放、已重试或调用未发生。

## 2. 本地证据

新增 `tests/test_ai_research_generation_executor.py` 共 9 项：正向 typed proposal、跨 owner、过期 lease、数据漂移、前向分区拒绝、预算不足、错误输出 schema、Provider 异常脱敏、嵌套 sampling 配置不可变。测试使用真实本地 DB、配额、gateway、服务器文件数据证明及预检服务；只有 Provider transport 使用受控测试替身。

首次缺模块 RED 为 7 项；后续供应商异常及 forward 分区负例也先复现，再修复。独立聚焦最终 9 passed、1 个既有依赖告警；两个新增文件 Ruff check/format 通过。Root 冻结源码后的完整 v2 回归包含这 9 项：**241 passed、23 warnings，38.76 秒，6 worker，0 failure/error/skip**；详见 [六 worker 回归记录](REGRESSION_6_WORKERS_20260905.md)。

正向测试证明 provider seam → gateway 账本/配额结算 → typed proposal；它未执行完整 worker checkpoint/materialization，也没有真实外部模型调用。现有 materialization 和 worker 测试仍分别验证各自合同，不能把这些不同组件测试拼成真实端到端运行证据。

## 3. 后续接线与门禁（执行器首次交付时的缺口）

> 后续更新：本节列出的 adapter、部署组合根及阶段时钟本地实现现已补齐，见 [生成部署与连接测试](GENERATION_PROVIDER_DEPLOYMENT_20260905.md)。公开 worker 的完整本地生成物化链已增加 HTTP transport seam 正反测试；原 9 项仍保留为独立组件证据。以下缺口描述保留其首次交付时点，不代表 adapter/factory 当前仍缺失。真实外部调用和后续评估执行图仍未验收。

部署组合根需要显式同时提供：

- 真实、版本固定、保留供应商/实际模型/request ID、正确报告未知 usage 的 adapter-backed `LlmGateway`；需补 transport 体积/超时及费用约束，不复用会默认为 0 用量或丢失实际型号的旧 DTO。
- 同一个 deployment resolver 配置派生的 `DatasetRegistry`，供预检、执行器和 materializer 使用。
- 固定 `GenerationExecutorPolicy`、合法且可用的 user token bucket、环境 manifest 与 materialization policy。
- `ResearchStageAttemptService(generation_materializer=ResearchGenerationMaterializer(...))`，以及 worker 的 `CLARIFY`/`GENERATE` 映射。不得只替换 executor 而漏装物化服务。

**当前 `explorer:create_worker` 仍是确定性诊断 factory，默认 feature flags 未开启。** 本次未修改 config/explorer、未配置或调用真实模型、未使用生产凭据或业务库、未部署/重启常驻服务。无 adapter/factory 的本地接线属于未完成实现，不能全部归因于外部环境；实际凭据调用、真实行情、隔离 Evaluator/Sandbox、审批和前向窗口另外按 T2/T3 验收。

此外，`generation_materialization.py` 仍有应用时钟的 lease expiry 检查；quota/task 数据库时钟修复不能替代阶段提交端的跨组件时钟审查。当前整体验收保持 `NO-GO`。
