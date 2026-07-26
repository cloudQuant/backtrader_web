# 迭代 167 - AI 能力工程化

> **文档状态**: 已完成
> **创建日期**: 2026-05-24
> **隶属路线**: 世界一流 AI+量化投研平台跃迁 Phase 2
> **总览**: `docs/iterations/世界一流跃迁-迭代166-169-总览.md`
> **执行顺位**: 第 3 站（在迭代 169 后执行）
> **核心目标**: 让现有 AI 能力可管理、可扩展、可控成本 ——
> 建立"AI 调用全链路日志 + 多模型路由 + Token 预算 + Prompt 模板治理"四位一体的 AI 工程化底座。

---

## 0. 背景

迭代 166 把 AI 输出做成"可信"的，但 AI 调用本身仍然是黑盒：

- 谁在用？用了多少 Token？花了多少钱？— 没数据
- AI 失败时是什么原因？延迟多少？— 没监控
- 想换个模型（如本地 Ollama / Claude）？— 改代码
- Prompt 写错了想灰度回滚？— 不支持

这些是「能用」与「敢上线 / 敢放给企业用户」之间的关键差距。

**用户场景驱动**：
- 个人用户：「我今天 AI 用了多少次？还能用多少？」
- 团队管理员：「这个月谁用 AI 最多？花了多少钱？」
- 平台维护者：「最近 24h AI 失败率高，是哪个 endpoint 的问题？」
- 高级用户：「想用本地 Llama 70B 跑策略生成，能切换吗？」

---

## 1. 总目标

| 维度 | 现状 | 目标 |
|------|------|------|
| AI 调用日志 | ❌ 无 | ✅ 全链路日志（请求/响应/Token/耗时/成本/错误） |
| 成本可视化 | ❌ 无 | ✅ 看板：用量趋势、Top 用户、Top endpoint、失败率 |
| Token 预算 | ❌ 无 | ✅ 用户/全局双层配额；软预算（警告）/硬预算（拒绝）可配 |
| 多模型支持 | ⚠️ 单 OpenAI 兼容 endpoint | ✅ LiteLLM 统一抽象，OpenAI/Claude/Ollama/Together 同时可用 |
| 本地模型 | ❌ 不支持 | ✅ Ollama 适配（zero-cost、隐私优先） |
| 模型选择 UI | ❌ 全局配置 | ✅ 用户级别可选模型；管理员限制可选范围 |
| Prompt 治理 | ❌ 硬编码 | ✅ 模板版本化、灰度发布、A/B 测试 |

---

## 2. 执行原则

### 2.1 可以做

1. 新建 `app/models/ai_call_log.py`、`app/services/ai_observability/`、`app/services/ai_router/`、`app/services/prompt_registry/`
2. 在现有 AI 服务（`ai_chat_service.py` / `ai_trading_service.py` / `rag_service.py` / `strategy_explainer/llm_explainer.py` 等）注入调用日志中间件
3. 引入 `litellm` 包作为多模型抽象（已是行业标准，社区活跃，无锁定）
4. 新增数据库表 + 历史归档机制（按月分表，避免日志膨胀）
5. 新增前端 AI 可观测页面
6. 新增配置项支持「全局默认模型 / 用户级覆盖 / 管理员限制」三层

### 2.2 不要做

1. 不要修改既有 AI 服务的对外 API 签名
2. 不要在日志写入路径上引入同步阻塞（必须 fire-and-forget + bounded queue，参考迭代 165 audit_service 模式）
3. 不要做 AI 模型代理服务（不转发流量，仅路由配置）
4. 不要在本迭代实现按 Token 计费（仅记录成本，结算延后）
5. 不要把 Ollama 设为默认（保持当前 OpenAI 兼容 endpoint 默认值不变）
6. 不要在 Prompt 治理里做「自动 Prompt 优化」（人工托管即可）

---

## 3. 任务分解

### 阶段一: AI 调用全链路日志（P0）

> 现状：调用 AI 后只有 logger.info 一行；失败原因、Token、耗时全部丢失。
> 目标：每次 AI 调用都落库一条审计级别记录，可查可分析。

- [ ] **T1**: AI 调用日志模型 + Schema
  - 新增 `app/models/ai_call_log.py` ORM 模型，字段：
    - `id, user_id, request_id, service_name (ai_chat / rag / strategy_explainer / ai_trading), mode (knowledge_qa / strategy_generation / ...), model_name, provider`
    - `prompt_template_id, prompt_tokens, completion_tokens, total_tokens`
    - `estimated_cost_usd, latency_ms, status (success / failed / timeout), error_code, error_message`
    - `created_at, response_chars, prompt_hash (sha256)`
    - 不存原始 prompt/response 全文（隐私+体积），存 `prompt_hash` + 长度
  - 新增 `app/schemas/ai_observability.py`
  - Alembic 迁移文件

- [ ] **T2**: AI 调用日志中间件 + 异步 sink
  - 新增 `app/services/ai_observability/__init__.py`、`logger.py`、`cost_calculator.py`
  - `logger.py` 提供 `@log_ai_call(service_name, mode)` decorator 包装 AI 服务方法
  - 异步 sink：参考 165 `audit_service.py` 的 bounded queue 模式，失败 fail-open 不阻塞主请求
  - FastAPI lifespan 启动/关闭时管理 sink
  - `cost_calculator.py` 维护 `MODEL_PRICING` 配置（gpt-4o / claude-3.5 / ollama-local 等），按 token 估算 cost_usd

- [ ] **T3**: 现有 AI 服务接入日志
  - 改造 `app/services/ai_chat_service.py` 调用点 → 加 `@log_ai_call("ai_chat", mode=...)`
  - 改造 `app/services/rag_service.py` 调用点
  - 改造 `app/services/trading_intent_parser.py` 调用点
  - 改造 `app/services/strategy_explainer/llm_explainer.py` 调用点（来自迭代 166）
  - 改造 `app/services/ai_trading_service.py` 调用点
  - 每个改造点要保证：旧测试通过、新增至少 1 个测试验证日志写入
  - 不修改外部 API 行为

### 阶段二: AI 成本看板（P0）

- [ ] **T4**: 成本看板后端 API
  - 新增 `app/api/ai_observability.py`
  - GET `/api/v1/admin/ai/usage` - 用量统计（按时间/用户/模型/服务聚合）
  - GET `/api/v1/admin/ai/failures` - 失败率排行 + 错误码分布
  - GET `/api/v1/admin/ai/slow-calls` - P95/P99 延迟 Top 调用
  - GET `/api/v1/me/ai/usage` - 普通用户查看自己用量
  - 管理员端用 `Depends(get_current_admin_user)` 守卫
  - 复用 `app/api/deps_permissions.py` 已有权限装饰器

- [ ] **T5**: 成本看板前端
  - 新增 `src/frontend/src/views/AIObservabilityPage.vue`
  - 三个 tab：**用量趋势** / **失败诊断** / **慢调用排查**
  - 用量趋势：堆叠柱状图（按 service）+ Top10 用户表格 + 模型分布饼图
  - 失败诊断：按错误码 group + 时间趋势线图 + 最近 50 条失败记录
  - 慢调用：P95/P99 时序图 + Top 20 慢调用样本
  - 路由 `/admin/ai-observability`，管理员可见
  - 普通用户在 `SettingsPage.vue` 新增「我的 AI 用量」面板（仅自己数据）

### 阶段三: Token 预算控制（P1）

- [ ] **T6**: Token 预算系统
  - 新增 `app/services/ai_observability/budget.py`
  - 全局配置：`AI_BUDGET_DAILY_USD`（默认 None = 不限）
  - 用户配置：`User.ai_budget_daily_usd` 字段（None = 用全局）
  - 模式：**软预算**（超额仅警告，仍执行）、**硬预算**（超额直接拒绝 429）
  - 在 `@log_ai_call` decorator 中前置预算检查（before 调用，避免无效消耗）
  - 拒绝时返回结构化错误：`{reason_code: "budget_exceeded", limit_usd, used_usd, reset_at}`
  - 管理员可在管理界面配置每个用户的预算
  - Alembic 迁移：`User` 表加 `ai_budget_daily_usd / ai_budget_mode` 字段

### 阶段四: 多模型路由（P0）

- [ ] **T7**: 引入 LiteLLM + 路由层
  - `pyproject.toml` 添加 `litellm>=1.40,<2.0` 依赖（在 `[project.optional-dependencies] ai` 组）
  - 新增 `app/services/ai_router/__init__.py`、`router.py`、`providers.py`
  - `providers.py` 维护可用 provider 列表：OpenAI / Anthropic / Ollama / Together / Groq
  - 配置驱动：`app/config.py` 新增 `AI_PROVIDERS = {...}`，每个 provider 配 `base_url / api_key_env / models`
  - `router.py` 统一 `async def chat_completion(messages, model, **kwargs) -> ChatResponse` 接口
  - 现有调用点替换为 `ai_router.chat_completion(...)`，旧 OpenAI 兼容路径作为 fallback

- [ ] **T8**: Ollama 本地模型适配
  - 新增 `app/services/ai_router/ollama_adapter.py`
  - 默认 base_url：`http://localhost:11434`
  - 探活：`/api/tags` 检查 ollama 是否启动
  - 健康检查 endpoint：`GET /api/v1/admin/ai/providers/health` 返回每个 provider 的可用性
  - 文档说明用户如何安装 Ollama + 拉取模型（如 `qwen2.5-coder:7b`）

- [x] **T9**: 模型选择 UI
  - 后端 GET `/api/v1/me/ai/available-models` 返回当前用户可选的模型清单（当前由 provider registry 控制，管理员限制后续增强）
  - 后端 PATCH `/api/v1/me/ai/preferences` 保存用户偏好（默认模型 / 默认 provider）；POST `/api/v1/me/ai/preferences/test` 测试所选模型连通性
  - 前端 `SettingsPage.vue` 新增「AI 模型偏好」面板：选择默认模型 + 测试连通性按钮
  - 前端 `AIChatPage.vue` 输入框右侧加模型切换 dropdown（当前会话覆盖默认）
  - 管理员页面 `/admin/ai-models` 配置全局可用 provider + 限制每个用户可选范围（后续增强，当前使用 provider registry 返回可选模型）

### 阶段五: Prompt 模板治理（P1）

- [x] **T10**: Prompt 模板注册中心
  - 新增 `app/services/prompt_registry/__init__.py`、`registry.py`
  - 新增 `app/models/prompt_template.py`：`id, name, version, content, status (draft/active/archived), variables, created_at, created_by`
  - 每个 template 支持多版本，激活的版本只能有一个
  - API：
    - GET `/api/v1/admin/prompt-templates` 列表
    - POST `/api/v1/admin/prompt-templates` 新建
    - PATCH `/api/v1/admin/prompt-templates/{id}/activate` 激活某版本
    - POST `/api/v1/admin/prompt-templates/{id}/test` 试调（不影响线上）
  - 现有硬编码 prompt（`ai_chat_service._MODE_INSTRUCTIONS`、`ai_trading_service` 等）迁移到 registry，但**保留代码中的默认值作为 fallback**

- [x] **T11**: Prompt 灰度发布
  - 在 `PromptTemplate` 表加 `rollout_percentage`（0-100）
  - 调用时按 user_id hash % 100 < rollout_percentage 走新版本，否则走 active 版本
  - 调用日志 `ai_call_log.prompt_template_version` 记录实际使用版本，便于 A/B 分析
  - 管理界面提供「灰度滑块」UI 控件

### 阶段六: 文档与验证（P1）

- [x] **T12**: 文档
  - 新增 `docs/guides/AI_OBSERVABILITY.md` - 看板使用说明、字段定义、查询示例
  - 新增 `docs/guides/AI_PROVIDERS.md` - 多 provider 配置指南、Ollama 本地部署说明
  - 新增 `docs/guides/PROMPT_REGISTRY.md` - 模板治理流程、灰度发布最佳实践
  - 更新 `.env.example` 新增 `AI_PROVIDERS` / `AI_BUDGET_*` 配置示例

---

## 4. 推荐执行顺序

```
T1 → T2 → T3                    # 阶段一：日志先落，是所有功能的数据底层
T4 → T5                         # 阶段二：看板基于 T1-T3 数据
T6                              # 阶段三：预算依赖 T2 的 cost_calculator
T7 → T8 → T9                    # 阶段四：多模型路由独立可交付
T10 → T11                       # 阶段五：Prompt 治理独立可交付
T12                             # 阶段六：文档收尾
```

> T1-T3 必须先落（阻塞 T4-T6 和 T11）；T7-T11 之间可并行。

---

## 5. 验证命令

```bash
# 后端单元测试
cd src/backend
pytest tests/test_ai_call_log.py tests/test_ai_observability.py tests/test_ai_budget.py -v
pytest tests/test_ai_router.py tests/test_ollama_adapter.py -v
pytest tests/test_prompt_registry.py -v

# Ruff lint
ruff check app/services/ai_observability app/services/ai_router app/services/prompt_registry

# 覆盖率
pytest --cov=app.services.ai_observability --cov=app.services.ai_router --cov=app.services.prompt_registry \
  --cov-report=term-missing tests/test_ai_*.py tests/test_prompt_*.py

# 数据库迁移验证
cd src/backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head

# Ollama 健康检查（需本地启动 Ollama）
curl http://localhost:8000/api/v1/admin/ai/providers/health

# 前端
cd src/frontend
npm run typecheck
npm run test -- src/test/views/AIObservabilityPage.test.ts --run

# 维持迭代 165 + 166 基线
cd src/backend
ruff check --select B904 app/api
mypy app/utils app/schemas
```

---

## 6. 风险评估

| 风险 | 影响 | 缓解 |
|------|------|------|
| 日志写入拖慢主请求 | 高 | 沿用 165 audit_service 已验证的 bounded queue 异步 sink；故障时 fail-open |
| 日志表膨胀（每天 N 万行） | 中 | 按月分表 + 自动归档脚本 + 看板查询限定时间窗 |
| LiteLLM 引入兼容问题 | 中 | 现有 OpenAI 兼容路径保留，路由层 fallback；只在新调用点用 LiteLLM |
| Ollama 本地模型质量参差 | 低 | 文档明确说明本地模型效果不如云端；保持默认指向云端 |
| 预算硬拒绝导致用户体验差 | 高 | 默认软预算（仅警告）；管理员显式开启硬预算；拒绝时返回明确的 reset_at |
| Prompt 灰度发布 bug 影响线上 | 中 | 必须保留硬编码 fallback；rollout=0 时完全走 fallback；测试覆盖新旧版本 |
| Token 计费口径不准 | 中 | cost_usd 标记为 estimated；提供管理员 override；保留 raw token 数 |

---

## 7. 不在本迭代范围内

1. **实际计费 / 支付集成** — 仅记录成本，结算在商业化迭代处理
2. **AI 模型微调 / 训练** — 平台不做训练，仅做编排
3. **多 Agent 协同** — TradingAgents 模式留到 Phase 2 后续
4. **Prompt 自动优化（DSPy / Prompt Engineering 自动化）** — 人工托管即可
5. **Token 流式计费 / 限速** — 当前按调用次数前置检查即可
6. **多租户隔离** — 维持单租户

---

## 8. 执行结果（持续更新）

### 8.1 完成内容

| 任务 | 状态 | 说明 |
|------|------|------|
| T1 | ✅ | AI 调用日志模型 + Schema + Alembic 迁移完成：新增 `ai_call_logs` 表，记录 user/request/service/mode/model/provider/token/成本/耗时/状态/错误/prompt_hash/response_chars；不存原始 prompt/response 全文 |
| T2 | ✅ | AI 调用日志中间件与异步 sink 完成：新增 `app/services/ai_observability/`，提供 bounded queue、fail-open 持久化、prompt hash、模型成本估算与 `log_ai_call` decorator；FastAPI lifespan 启动/关闭 sink |
| T3 | ✅ | 现有 AI 调用路径首轮接入完成：`AIChatService.generate_answer` 写入 AI 调用日志；`trading_intent_parser._call_llm` 改为复用 `generate_answer` 可观测入口；`strategy_explainer` 经 `AIChatService` 间接覆盖 |
| T4 | ✅ | 成本看板后端 API 完成：新增 `/api/v1/admin/ai/usage`、`/api/v1/admin/ai/failures`、`/api/v1/admin/ai/slow-calls`、`/api/v1/me/ai/usage`；管理员接口复用现有 admin 守卫，普通用户接口仅返回自己用量 |
| T5 | ✅ | 成本看板前端完成：新增管理员 `/admin/ai-observability` 页面，提供用量趋势、失败诊断、慢调用排查三个 tab；侧边栏仅管理员可见；`SettingsPage.vue` 新增「我的 AI 用量」面板 |
| T6 | ✅ | Token/成本预算控制完成：新增全局 `AI_BUDGET_DAILY_USD` / `AI_BUDGET_MODE` 配置、用户级 `ai_budget_daily_usd` / `ai_budget_mode` 覆盖字段、`AIBudgetService` 日预算快照与硬预算 429 结构化阻断；`log_ai_call` decorator 与 `AIChatService.generate_answer` 在 provider 调用前执行预算检查，KB Chat 路径透传当前用户 ID |
| T7 | ✅ | 多模型路由底座完成：新增 `app/services/ai_router/`，提供 provider registry、LiteLLM `acompletion` 优先路径、OpenAI-compatible fallback、统一 `ChatCompletionResponse`；`AIChatService` 已改为通过路由层调用 provider，并保留旧 OpenAI 兼容配置为默认路径 |
| T8 | ✅ | Ollama 本地模型适配完成：新增 `/api/tags` 探活 adapter、provider health service 与管理员接口 `GET /api/v1/admin/ai/providers/health`；云端 provider 以 API key 配置状态作为基础可用性，Ollama 返回本地模型清单与错误信息；新增 `docs/guides/AI_PROVIDERS.md` 配置指南 |
| T9 | ✅ | 模型选择 UI 与用户偏好完成：新增用户可选模型 API `GET /api/v1/me/ai/available-models`、偏好保存 API `PATCH /api/v1/me/ai/preferences`、连通性测试 API `POST /api/v1/me/ai/preferences/test`、用户级 `ai_preferred_provider` / `ai_preferred_model` 字段与迁移；`SettingsPage.vue` 支持默认 AI 模型偏好与连通性测试按钮，`AIChatPage.vue` 支持当前会话模型 dropdown 覆盖默认偏好，KB Chat/RAG/AIChatService 已透传并解析会话级 `model_id` |
| T10 | ✅ | Prompt 模板注册中心完成：新增 `prompt_templates` 表、`PromptRegistryService`、管理员模板 API（列表/新建/激活/试调）与 `AIChatService` active-template 接入；同名模板一次仅一个 active，旧 active 自动 archived；无 active 模板时保留 `_MODE_INSTRUCTIONS` 等代码默认值 fallback，AI 调用日志记录实际 `prompt_template_id` |
| T11 | ✅ | Prompt 灰度发布完成：`PromptTemplate.rollout_percentage` 支持 0-100 灰度比例，调用时按 `template_name:version:user_id` 稳定 hash 选择灰度模板，否则回退 active 版本；AI 调用日志新增 `prompt_template_version`，便于后续 A/B 分析；前端新增管理员 `/admin/prompt-templates` 页面与「灰度比例」滑块 |
| T12 | ✅ | 文档收尾完成：新增 `AI_OBSERVABILITY.md` 与 `PROMPT_REGISTRY.md`，扩写 `AI_PROVIDERS.md`，更新 `.env.example` 覆盖 `AI_CHAT_*`、`AI_BUDGET_*`、`AI_PROVIDERS` 与 provider API key 示例 |

### 8.2 修改文件清单

- `src/backend/app/models/ai_call_log.py`
- `src/backend/app/models/__init__.py`
- `src/backend/app/models/user.py`
- `src/backend/app/models/prompt_template.py`
- `src/backend/app/config.py`
- `src/backend/app/db/database.py`
- `src/backend/app/middleware/rate_limit_headers.py`
- `src/backend/app/api/ai_observability.py`
- `src/backend/app/api/prompt_templates.py`
- `src/backend/app/api/router.py`
- `src/backend/app/schemas/ai_observability.py`
- `src/backend/app/services/ai_observability/__init__.py`
- `src/backend/app/services/ai_observability/budget.py`
- `src/backend/app/services/ai_observability/cost_calculator.py`
- `src/backend/app/services/ai_observability/logger.py`
- `src/backend/app/services/ai_observability/stats.py`
- `src/backend/app/services/ai_router/__init__.py`
- `src/backend/app/services/ai_router/health.py`
- `src/backend/app/services/ai_router/ollama_adapter.py`
- `src/backend/app/services/ai_router/preferences.py`
- `src/backend/app/services/ai_router/providers.py`
- `src/backend/app/services/ai_router/router.py`
- `src/backend/app/services/prompt_registry/__init__.py`
- `src/backend/app/services/prompt_registry/registry.py`
- `src/backend/app/services/ai_chat_service.py`
- `src/backend/app/services/kb_chat_service.py`
- `src/backend/app/services/rag_service.py`
- `src/backend/app/services/trading_intent_parser.py`
- `src/backend/app/main.py`
- `src/backend/alembic/versions/0006_add_ai_call_logs.py`
- `src/backend/alembic/versions/0007_add_ai_budget_fields.py`
- `src/backend/alembic/versions/0008_add_ai_model_preferences.py`
- `src/backend/alembic/versions/0009_add_prompt_templates.py`
- `src/backend/alembic/versions/0010_add_prompt_rollout_fields.py`
- `src/backend/tests/test_ai_call_log.py`
- `src/backend/tests/test_ai_budget.py`
- `src/backend/tests/test_ai_observability.py`
- `src/backend/tests/test_ai_router.py`
- `src/backend/tests/test_ai_chat_service.py`
- `src/backend/tests/test_ai_trading.py`
- `src/backend/tests/test_ai_observability_api.py`
- `src/backend/tests/test_prompt_registry_api.py`
- `src/backend/tests/test_prompt_registry_ai_chat.py`
- `src/backend/tests/test_rate_limit_headers.py`
- `src/backend/tests/test_main_lifespan_and_websocket.py`
- `src/frontend/src/api/aiObservability.ts`
- `src/frontend/src/api/promptTemplates.ts`
- `src/frontend/src/stores/kbChat.ts`
- `src/frontend/src/views/AIChatPage.vue`
- `src/frontend/src/views/AIObservabilityPage.vue`
- `src/frontend/src/views/PromptTemplatesPage.vue`
- `src/frontend/src/views/SettingsPage.vue`
- `src/frontend/src/router/index.ts`
- `src/frontend/src/components/common/AppLayout.vue`
- `src/frontend/src/test/api/aiObservability.test.ts`
- `src/frontend/src/test/api/promptTemplates.test.ts`
- `src/frontend/src/test/stores/kbChat.test.ts`
- `src/frontend/src/test/views/AIChatPage.test.ts`
- `src/frontend/src/test/views/AIObservabilityPage.test.ts`
- `src/frontend/src/test/views/PromptTemplatesPage.test.ts`
- `src/frontend/src/test/views/SettingsPage.test.ts`
- `src/frontend/src/test/router/index.test.ts`
- `src/frontend/src/test/components/common/AppLayout.test.ts`
- `docs/guides/AI_PROVIDERS.md`
- `docs/guides/PROMPT_REGISTRY.md`
- `docs/guides/AI_OBSERVABILITY.md`
- `.env.example`

### 8.3 验证结果

- T1 RED：`pytest tests/test_ai_call_log.py -q --tb=short` 初始失败于缺少 `app.models.ai_call_log`、`app.schemas.ai_observability` 与 `0006_add_ai_call_logs.py`
- T1 GREEN：`pytest tests/test_ai_call_log.py -q --tb=short` 通过（6 passed）
- T2 RED：`pytest tests/test_ai_observability.py -q --tb=short` 初始失败于缺少 `app.services.ai_observability`
- T2 GREEN：`pytest tests/test_ai_observability.py -q --tb=short` 通过（6 passed）
- T3 RED：`pytest tests/test_ai_chat_service.py::TestAIChatServiceGenerateAnswer::test_generate_answer_records_ai_call_log -q --tb=short` 初始失败，日志表为空
- T3 GREEN：`pytest tests/test_ai_chat_service.py -q --tb=short` 通过（41 passed）
- T3 trading path：`pytest tests/test_ai_trading.py -q --tb=short` 通过（49 passed）
- Lifespan：`pytest tests/test_main_lifespan_and_websocket.py::test_lifespan_runs_startup_and_shutdown -q --tb=short` 通过
- T1-T3 targeted：`ruff check app/models/ai_call_log.py app/schemas/ai_observability.py app/services/ai_observability app/services/ai_chat_service.py app/services/trading_intent_parser.py app/main.py tests/test_ai_call_log.py tests/test_ai_observability.py tests/test_ai_chat_service.py tests/test_ai_trading.py tests/test_main_lifespan_and_websocket.py alembic/versions/0006_add_ai_call_logs.py` 通过；对应 targeted pytest 通过（103 passed）
- T4 RED：`pytest tests/test_ai_observability_api.py -q --tb=short` 初始失败于 4 个接口均返回 404
- T4 GREEN：`pytest tests/test_ai_observability_api.py -q --tb=short` 通过（4 passed）
- T4 targeted：`ruff check app/api/ai_observability.py app/api/router.py app/services/ai_observability tests/test_ai_observability_api.py tests/test_ai_observability.py tests/test_ai_chat_service.py tests/test_ai_trading.py` 通过；对应 targeted pytest 通过（100 passed）
- T5 RED：`npm run test -- src/test/api/aiObservability.test.ts src/test/views/AIObservabilityPage.test.ts src/test/views/SettingsPage.test.ts src/test/router/index.test.ts src/test/components/common/AppLayout.test.ts --run` 初始失败于缺少 `@/api/aiObservability`、`AIObservabilityPage.vue`、管理员菜单/标题、Settings AI 用量面板
- T5 GREEN：同一组 targeted Vitest 通过（5 files / 50 tests passed）
- T5 targeted lint：`npx eslint src/api/aiObservability.ts src/views/AIObservabilityPage.vue src/views/SettingsPage.vue src/router/index.ts src/components/common/AppLayout.vue src/test/api/aiObservability.test.ts src/test/views/AIObservabilityPage.test.ts src/test/views/SettingsPage.test.ts src/test/router/index.test.ts src/test/components/common/AppLayout.test.ts` 通过
- T5 full typecheck：`npm run typecheck` 当前仍失败（exit code 2），错误位于既有文件 `BacktestHistoryTable.vue`、`LogViewer.vue`、`Workspace*`、`auth.ts`、`DashboardPage.vue`、`KnowledgeBase*`、`QuotePage.vue`、`StrategyPage.vue`、`WorkspaceListPage.vue` 等；未指向本次 T5 新增/修改的 AI observability 文件
- T6 RED：`pytest tests/test_ai_budget.py tests/test_ai_chat_service.py::TestAIChatServiceGenerateAnswer::test_generate_answer_blocks_provider_when_hard_budget_exceeded -q --tb=short` 初始失败于缺少 `app.services.ai_observability.budget`
- T6 GREEN：同一组 targeted pytest 通过（5 passed）
- T6 targeted 回归：`pytest tests/test_ai_budget.py tests/test_ai_observability.py tests/test_ai_chat_service.py tests/test_ai_observability_api.py tests/test_rate_limit_headers.py::TestRateLimitResponseStandardization -q --tb=short` 通过（60 passed）
- T6 targeted lint：`ruff check app/models/user.py app/config.py app/db/database.py app/middleware/rate_limit_headers.py app/services/ai_observability app/services/ai_chat_service.py app/services/rag_service.py tests/test_ai_budget.py tests/test_ai_observability.py tests/test_ai_chat_service.py tests/test_ai_observability_api.py tests/test_rate_limit_headers.py alembic/versions/0007_add_ai_budget_fields.py` 通过
- T7 RED：`pytest tests/test_ai_router.py tests/test_ai_chat_service.py::TestAIChatServiceGenerateAnswer::test_generate_answer_uses_ai_router_completion -q --tb=short` 初始失败于缺少 `app.services.ai_router`
- T7 GREEN：`pytest tests/test_ai_router.py tests/test_ai_chat_service.py tests/test_config.py -q --tb=short` 通过（50 passed）
- T7 targeted lint：`ruff check app/services/ai_router app/services/ai_chat_service.py app/config.py tests/test_ai_router.py tests/test_ai_chat_service.py tests/test_config.py pyproject.toml` 通过
- T8 RED：`pytest tests/test_ai_router.py::test_ollama_health_check_reads_local_tags tests/test_ai_router.py::test_ollama_health_check_reports_unavailable_on_transport_error tests/test_ai_observability_api.py::test_admin_ai_provider_health_reports_configured_providers tests/test_ai_observability_api.py::test_non_admin_cannot_access_admin_ai_provider_health -q --tb=short` 初始失败于缺少 `app.services.ai_router.ollama_adapter`、`app.services.ai_router.health`，provider health API 返回 404
- T8 GREEN：同一组 targeted pytest 通过（4 passed）
- T7-T8 targeted 回归：`pytest tests/test_ai_router.py tests/test_ai_chat_service.py tests/test_config.py tests/test_ai_observability_api.py -q --tb=short` 通过（58 passed）
- T8 targeted lint：`ruff check app/services/ai_router app/services/ai_chat_service.py app/api/ai_observability.py app/config.py tests/test_ai_router.py tests/test_ai_chat_service.py tests/test_config.py tests/test_ai_observability_api.py pyproject.toml` 通过
- T9 RED：`pytest tests/test_ai_observability_api.py::test_my_ai_available_models_returns_models_and_current_preferences tests/test_ai_observability_api.py::test_my_ai_preferences_can_be_saved_and_returned tests/test_ai_observability_api.py::test_my_ai_preferences_reject_unknown_model -q --tb=short` 初始失败于 `/me/ai/available-models` 与 `/me/ai/preferences` 返回 404；`AIChatService` 会话级覆盖测试初始失败于不接收 `model_id`；前端 targeted Vitest 初始失败于缺少 API wrapper、Settings 偏好面板与 AIChatPage 会话模型选择
- T9 GREEN：后端偏好 API targeted pytest 通过（3 passed）；`AIChatService` 用户默认偏好与会话级模型覆盖测试通过（2 passed）；前端 `npm run test -- src/test/api/aiObservability.test.ts src/test/views/SettingsPage.test.ts src/test/views/AIChatPage.test.ts src/test/stores/kbChat.test.ts --run` 通过（4 files / 36 tests passed）
- T7-T9 targeted 回归：`pytest tests/test_ai_router.py tests/test_ai_chat_service.py tests/test_ai_observability_api.py tests/test_config.py tests/test_iteration129_kb_chat_api.py -q --tb=short` 通过（73 passed）
- T9 targeted lint：`ruff check app/services/ai_router/preferences.py app/services/ai_chat_service.py app/services/rag_service.py app/services/kb_chat_service.py app/api/ai_observability.py app/models/user.py tests/test_ai_chat_service.py tests/test_ai_observability_api.py` 通过；`npx eslint src/api/aiObservability.ts src/stores/kbChat.ts src/views/SettingsPage.vue src/views/AIChatPage.vue src/test/api/aiObservability.test.ts src/test/stores/kbChat.test.ts src/test/views/SettingsPage.test.ts src/test/views/AIChatPage.test.ts` 通过
- T10 RED：`pytest tests/test_prompt_registry_api.py tests/test_prompt_registry_ai_chat.py -q --tb=short` 初始失败于缺少 `app.models.prompt_template` / `app.services.prompt_registry` / 管理端 prompt template API
- T10 GREEN：同一组 targeted pytest 通过（5 passed）
- T10 targeted 回归：`pytest tests/test_prompt_registry_api.py tests/test_prompt_registry_ai_chat.py tests/test_ai_chat_service.py tests/test_ai_observability_api.py tests/test_ai_trading.py tests/test_strategy_explainer_api.py tests/test_strategy_explainer_ast.py -q --tb=short` 通过（119 passed）
- T10 targeted lint：`ruff check app/models/prompt_template.py app/services/prompt_registry app/api/prompt_templates.py app/api/router.py app/db/database.py app/services/ai_chat_service.py alembic/versions/0009_add_prompt_templates.py tests/test_prompt_registry_api.py tests/test_prompt_registry_ai_chat.py` 通过
- T11 RED：后端 `pytest tests/test_prompt_registry_api.py tests/test_prompt_registry_ai_chat.py -q --tb=short` 初始失败于缺少 `rollout_percentage` / `prompt_template_version`；前端 `npm run test -- src/test/api/promptTemplates.test.ts src/test/views/PromptTemplatesPage.test.ts src/test/router/index.test.ts src/test/components/common/AppLayout.test.ts --run` 初始失败于缺少 API wrapper、页面、路由和菜单
- T11 GREEN：后端 `pytest tests/test_prompt_registry_api.py tests/test_prompt_registry_ai_chat.py -q --tb=short` 通过（9 passed）；前端 targeted Vitest 通过（4 files / 47 tests passed）
- T11 targeted 后端回归：`pytest tests/test_prompt_registry_api.py tests/test_prompt_registry_ai_chat.py tests/test_ai_chat_service.py tests/test_ai_observability.py tests/test_ai_observability_api.py tests/test_ai_call_log.py -q --tb=short` 通过（76 passed）
- T11 targeted lint：`ruff check app/models/prompt_template.py app/models/ai_call_log.py app/schemas/ai_observability.py app/services/prompt_registry app/services/ai_observability/logger.py app/api/prompt_templates.py app/api/router.py app/db/database.py app/services/ai_chat_service.py alembic/versions/0010_add_prompt_rollout_fields.py tests/test_prompt_registry_api.py tests/test_prompt_registry_ai_chat.py` 通过；`npx eslint src/api/promptTemplates.ts src/views/PromptTemplatesPage.vue src/router/index.ts src/components/common/AppLayout.vue src/test/api/promptTemplates.test.ts src/test/views/PromptTemplatesPage.test.ts src/test/router/index.test.ts src/test/components/common/AppLayout.test.ts` 通过
- T12 docs/config：新增 `docs/guides/AI_OBSERVABILITY.md`、`docs/guides/PROMPT_REGISTRY.md`，扩写 `docs/guides/AI_PROVIDERS.md`，更新 `.env.example` AI 配置示例
- T12 targeted 验证：Python 脚本检查 `AI_OBSERVABILITY.md`、`AI_PROVIDERS.md`、`PROMPT_REGISTRY.md` 必要 endpoint/字段，并校验 `.env.example` 中 `AI_PROVIDERS` 为合法 JSON 且包含 openai/ollama 示例，结果通过
- 迭代结束后端 lint/type 基线：`ruff check app/`、`ruff check --select B904 app/api/`、`mypy app/utils app/schemas` 均通过；改动测试文件 targeted `ruff check` 通过
- 迭代结束后端测试基线：`pytest tests/ -q --tb=short` 单次全量在 120 秒内未完成，因此按 12 个文件批次执行；12 批均通过（累计结果：chunk1 225 passed / 4 skipped；chunk2 121 passed / 25 skipped；chunk3 275 passed；chunk4 211 passed / 5 skipped；chunk5 427 passed / 2 skipped；chunk6 184 passed；chunk7 261 passed / 1 skipped；chunk8 294 passed / 1 skipped；chunk9 168 passed / 6 skipped；chunk10 241 passed / 7 skipped；chunk11 151 passed；chunk12 297 passed）
- 迭代结束测试隔离修复：全量后端验证中发现测试会恢复本机真实手动网关并触发 CTP/MT5 后台线程，已在 `tests/conftest.py` 中禁用测试环境的真实 gateway restore；同时重置 response cache，修复跨测试缓存污染
- 迭代结束前端基线：`npm run test -- --run --coverage` 通过；`npm run typecheck` 仍失败（exit code 2），错误为既有 Element Plus/类型债务，涉及 `BacktestHistoryTable.vue`、`LogViewer.vue`、`Workspace*`、`auth.ts`、`DashboardPage.vue`、`KnowledgeBase*`、`QuotePage.vue`、`StrategyPage.vue`、`WorkspaceListPage.vue` 等，不涉及 `PromptTemplatesPage.vue`、`promptTemplates.ts` 或 T12 文档改动
- 迭代结束仓库卫生：`git ls-files` artifact 检查通过，无 tracked `coverage.xml` / `coverage.json` / `backtrader.db` / `.DS_Store`

### 8.4 剩余风险与下一轮建议

- 迭代 167 T1-T12 已完成；下一步建议进入迭代 168（量化研究专业度：VaR/CVaR、因子库、绩效归因、市场状态识别）
- T4 聚合当前在服务层使用 Python 侧聚合，适合第一版管理看板；若日志量增长到高频生产规模，后续可迁移为数据库侧聚合/物化统计
- 当前 token 成本为估算值；未知模型按 0 处理，预算控制第一版基于调用前已有日累计成本执行，尚未对本次调用的预测 token 做预扣
- 前端 full typecheck 存在既有 Element Plus 类型兼容/未使用导入问题，本次 T5 已通过 targeted lint + targeted Vitest；建议在 T6 前后单独安排一次前端类型债务清理

---

> 📝 本迭代完成后，平台具备「AI 能力工程化基线」，可进入迭代 168 (量化研究专业度) 或迭代 169 (工程债务接续)。
