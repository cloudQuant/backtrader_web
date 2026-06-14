# AI Providers 配置指南

这份指南说明 AI for Trader 如何配置多 AI provider、如何接入 Ollama 本地模型，以及用户如何在 Settings 和 AI Chat 中选择模型。

## 支持范围

当前 provider registry 默认包含：

| Provider | 模型示例 | 配置方式 | 说明 |
|----------|----------|----------|------|
| `openai` | `gpt-4o`、`gpt-4o-mini` | `OPENAI_API_KEY` | 通过 LiteLLM 路由 |
| `anthropic` | `claude-3-5-sonnet-latest`、`claude-3-5-haiku-latest` | `ANTHROPIC_API_KEY` | 通过 LiteLLM 路由 |
| `ollama` | `ollama/qwen2.5-coder:7b`、`ollama/llama3.1:8b` | 本地 `base_url` | 默认 `http://localhost:11434` |
| `volcengine_ark` | `doubao-seed-2.0-code`、`doubao-seed-2.0-pro`、`minimax-m3`、`glm-5.1`、`deepseek-v4-pro`、`kimi-k2.6` | `VOLCENGINE_ARK_API_KEY` | 通过 OpenAI-compatible 路由，默认 `https://ark.cn-beijing.volces.com/api/coding/v3` |
| `siliconflow` | `deepseek-ai/DeepSeek-V4-Pro`、`deepseek-ai/DeepSeek-V4-Flash`、`moonshotai/Kimi-K2.6`、`zai-org/GLM-5.1` | `SILICONFLOW_API_KEY` | 通过 OpenAI-compatible 路由，默认 `https://api.siliconflow.cn/v1` |
| `together` | `together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo` | `TOGETHER_API_KEY` | 通过 LiteLLM 路由 |
| `groq` | `groq/llama-3.3-70b-versatile` | `GROQ_API_KEY` | 通过 LiteLLM 路由 |

旧的 OpenAI-compatible 配置仍然保留：

```bash
AI_CHAT_ENABLED=true
AI_CHAT_BASE_URL=https://api.openai.com/v1
AI_CHAT_API_KEY=replace-with-provider-key
AI_CHAT_MODEL=gpt-4o-mini
```

`AIChatService` 会优先使用会话级模型覆盖，其次使用用户偏好，最后回退到 `AI_CHAT_*` 兼容配置。

## AI_PROVIDERS 配置

`AI_PROVIDERS` 是 JSON 字符串，键是平台内 provider 名。

最小 Ollama 配置：

```bash
AI_PROVIDERS='{"ollama":{"base_url":"http://localhost:11434","api_key_env":null,"models":["ollama/qwen2.5-coder:7b","ollama/llama3.1:8b"]}}'
```

混合云端和本地：

```bash
AI_PROVIDERS='{"openai":{"base_url":null,"api_key_env":"OPENAI_API_KEY","models":["gpt-4o-mini"]},"ollama":{"base_url":"http://localhost:11434","api_key_env":null,"models":["ollama/qwen2.5-coder:7b"]}}'
OPENAI_API_KEY=replace-with-openai-key
```

火山方舟和硅基流动示例：

```bash
VOLCENGINE_ARK_API_KEY=replace-with-volcengine-ark-key
SILICONFLOW_API_KEY=replace-with-siliconflow-key
AI_PROVIDERS='{"volcengine_ark":{"display_name":"火山方舟","provider_type":"openai_compatible","base_url":"https://ark.cn-beijing.volces.com/api/coding/v3","api_key_env":"VOLCENGINE_ARK_API_KEY","models":["doubao-seed-2.0-code","doubao-seed-2.0-pro","doubao-seed-2.0-lite","doubao-seed-code","minimax-m2.7","minimax-m3","glm-5.1","deepseek-v4-flash","deepseek-v4-pro","kimi-k2.6"]},"siliconflow":{"display_name":"硅基流动","provider_type":"openai_compatible","base_url":"https://api.siliconflow.cn/v1","api_key_env":"SILICONFLOW_API_KEY","models":["deepseek-ai/DeepSeek-V4-Pro","deepseek-ai/DeepSeek-V4-Flash","moonshotai/Kimi-K2.6","zai-org/GLM-5.1"]}}'
```

如果火山方舟控制台里使用的是专属 Endpoint ID，也可以直接把 Endpoint ID 放入 `models` 列表中，前端会按 `volcengine_ark::模型或Endpoint` 传给后端。

字段说明：

| 字段 | 说明 |
|------|------|
| `base_url` | provider base URL；云端 provider 可为 `null` |
| `api_key_env` | 从哪个环境变量读取 API key；本地 Ollama 可为 `null` |
| `models` | 用户可选模型列表 |

## Ollama 本地模型

安装并拉取模型：

```bash
ollama pull qwen2.5-coder:7b
ollama pull llama3.1:8b
```

确认服务可访问：

```bash
curl http://localhost:11434/api/tags
```

后端健康检查会访问 `/api/tags`，并把返回的 `models[].name` 与配置中的模型列表一起用于可用性判断。

如果后端运行在 Docker 中，而 Ollama 在宿主机上，`base_url` 可能需要改成宿主机可访问地址，例如：

```bash
AI_PROVIDERS='{"ollama":{"base_url":"http://host.docker.internal:11434","api_key_env":null,"models":["ollama/qwen2.5-coder:7b"]}}'
```

## Provider 健康检查

管理员接口：

```http
GET /api/v1/admin/ai/providers/health
```

返回示例：

```json
{
  "summary": {"total": 7, "available": 1, "unavailable": 6},
  "providers": [
    {
      "name": "ollama",
      "display_name": "Ollama",
      "provider_type": "litellm",
      "available": true,
      "base_url": "http://localhost:11434",
      "models": ["ollama/qwen2.5-coder:7b"],
      "error": null
    }
  ]
}
```

云端 provider 当前以 API key 环境变量是否配置作为基础健康状态。Ollama 使用本地 `/api/tags` 探活。

## 用户模型偏好

用户侧接口：

```http
GET   /api/v1/me/ai/available-models
PATCH /api/v1/me/ai/preferences
POST  /api/v1/me/ai/preferences/test
```

Settings 页面提供默认模型选择和连通性测试：

```text
/settings
```

AI Chat 页面提供当前会话模型 dropdown：

```text
/ai-chat
```

优先级：

1. AI Chat 当前会话 `model_id`。
2. 用户保存的 `ai_preferred_provider` / `ai_preferred_model`。
3. 后端 `AI_CHAT_*` fallback。

`model_id` 格式：

```text
provider::model
```

示例：

```text
ollama::ollama/qwen2.5-coder:7b
openai::gpt-4o-mini
```

## 成本预算

全局预算配置：

```bash
AI_BUDGET_DAILY_USD=5.0
AI_BUDGET_MODE=soft
```

`AI_BUDGET_MODE` 可选：

| 模式 | 行为 |
|------|------|
| `soft` | 不阻断调用，适合初期观察 |
| `hard` | 超过日预算时阻断 provider 调用并返回 429 |

用户级预算字段可以覆盖全局配置：

- `users.ai_budget_daily_usd`
- `users.ai_budget_mode`

## 常见问题

### 健康检查显示云端 provider 不可用

检查对应 API key 环境变量是否存在，例如 `OPENAI_API_KEY`、`VOLCENGINE_ARK_API_KEY` 或 `SILICONFLOW_API_KEY`。

### Ollama 能 curl，但后端不可用

确认后端进程访问的地址是否正确。Docker 内部通常不能直接访问宿主机的 `localhost`。

### 模型出现在列表里但调用失败

模型列表只说明平台允许选择。真实调用仍可能因为 provider 限流、模型不存在、API key 权限或网络代理失败。优先使用 Settings 页的「测试连通性」按钮验证。
