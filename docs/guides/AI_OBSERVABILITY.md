# AI 可观测与成本看板指南

这份指南说明 AI for Investor 如何记录 AI 调用、如何查看成本看板，以及管理员排查慢调用和失败调用时应该看哪些字段。

## 你能看到什么

管理员打开：

```text
/admin/ai-observability
```

可以看到三类数据：

- **用量趋势**：总调用数、成功/失败数、Token、估算成本、按服务/模型/用户聚合。
- **失败诊断**：失败率、错误码分布、最近失败调用。
- **慢调用排查**：P95/P99 延迟、按服务延迟聚合、Top 慢调用样本。

普通用户在系统设置页可以看到自己的 AI 用量摘要：

```text
/settings
```

普通用户接口只返回当前用户自己的数据，不返回 `by_user` 聚合。

## 数据如何产生

AI 调用进入 `AIChatService.generate_answer` 后，会写入 `ai_call_logs`。

关键写入字段：

| 字段 | 含义 |
|------|------|
| `user_id` | 当前用户 ID；匿名或系统调用可为空 |
| `service_name` | 调用来源，例如 `ai_chat` |
| `mode` | AI 模式，例如 `knowledge_qa`、`strategy_review` |
| `model_name` | 实际调用模型 |
| `provider` | 实际 provider，例如 `openai_compatible`、`litellm` |
| `prompt_template_id` | 实际使用的 Prompt 模板 ID；无模板时为空 |
| `prompt_template_version` | 实际使用的 Prompt 模板版本；用于灰度/A-B 分析 |
| `prompt_tokens` | prompt token 数；provider 未返回时为 0 |
| `completion_tokens` | completion token 数；provider 未返回时为 0 |
| `total_tokens` | 总 token 数 |
| `estimated_cost_usd` | 按当前成本表估算的美元成本 |
| `latency_ms` | 调用耗时 |
| `status` | `success`、`failed`、`timeout` |
| `error_code` | 失败类型，例如异常类名 |
| `error_message` | 截断后的错误信息 |
| `prompt_hash` | Prompt 的 SHA-256 hash，不保存原始 prompt |
| `response_chars` | 响应字符数 |

系统不保存原始 prompt 或完整 response，只保留 hash 与元数据。

## 管理员 API

### 用量统计

```http
GET /api/v1/admin/ai/usage
```

可选 query：

```text
start_at=2026-05-26T00:00:00Z
end_at=2026-05-27T00:00:00Z
user_id=<user-id>
service_name=ai_chat
model_name=gpt-4o-mini
```

返回结构：

```json
{
  "summary": {
    "total_calls": 12,
    "successful_calls": 10,
    "failed_calls": 2,
    "total_tokens": 18320,
    "estimated_cost_usd": 0.0842,
    "avg_latency_ms": 1420
  },
  "by_day": [],
  "by_service": [],
  "by_model": [],
  "by_user": []
}
```

### 失败诊断

```http
GET /api/v1/admin/ai/failures?limit=50
```

返回结构：

```json
{
  "summary": {
    "total_calls": 12,
    "failed_calls": 2,
    "failure_rate": 0.1666666667
  },
  "by_error_code": [
    {"error_code": "HTTPError", "failed_calls": 1}
  ],
  "by_service": [
    {"service_name": "ai_chat", "failed_calls": 1}
  ],
  "recent_failures": []
}
```

排查顺序：

1. 看 `failure_rate` 是否突然升高。
2. 看 `by_error_code` 是认证、超时、网络还是解析错误。
3. 看 `recent_failures[].model_name` 和 `provider` 是否集中在某个 provider。
4. 若错误集中在 Prompt 灰度期间，关联 `prompt_template_version` 和模板发布记录排查。

### 慢调用排查

```http
GET /api/v1/admin/ai/slow-calls?limit=20
```

返回结构：

```json
{
  "summary": {
    "total_calls": 20,
    "avg_latency_ms": 1600,
    "p95_latency_ms": 5400,
    "p99_latency_ms": 5400
  },
  "by_service": [],
  "top_calls": []
}
```

排查顺序：

1. 看 P95/P99 是否比平均延迟高很多。
2. 看 `top_calls` 是否集中在某个模型。
3. 如果慢调用集中在 Ollama，先检查本机 CPU/GPU 和模型大小。
4. 如果慢调用集中在云端 provider，检查网络代理、provider 状态与模型限流。

## 当前用户 API

```http
GET /api/v1/me/ai/usage
```

可选 query 与管理员 usage 相同，但后端强制限定 `current_user.id`。

响应不会包含 `by_user`。

## 成本预算字段

全局配置：

```bash
AI_BUDGET_DAILY_USD=5.0
AI_BUDGET_MODE=soft
```

用户级字段：

- `users.ai_budget_daily_usd`
- `users.ai_budget_mode`

预算模式：

| 模式 | 行为 |
|------|------|
| `soft` | 只记录预算状态，不阻断调用 |
| `hard` | 超过日预算时在 provider 调用前返回 429 |

当前成本为估算值。未知模型按 0 成本处理，后续可以通过成本表补充。

## 常见问题

### 为什么成本是 0？

常见原因：

- provider 没有返回 token 数。
- 模型不在成本估算表中。
- 调用失败发生在 provider 返回 token 前。

### 为什么没有 prompt 原文？

这是设计选择。系统只保存 `prompt_hash`，避免把用户数据、策略细节或私有上下文写入日志表。

### 如何看 Prompt 灰度效果？

调用日志已经写入：

- `prompt_template_id`
- `prompt_template_version`

第一版看板还没有单独的 Prompt A/B tab。临时分析可以直接查询 `ai_call_logs`，按 `prompt_template_version` 过滤成功率、失败率和延迟。

## 推荐运营节奏

- **每日**：看失败率、成本增长、P95 延迟。
- **发布新模型后**：按 `model_name` 看失败率和延迟。
- **发布 Prompt 灰度后**：按 `prompt_template_version` 对比失败率、响应长度和用户反馈。
- **预算告警前**：先看 `by_user` 和 `by_model`，确认是正常使用还是异常调用。
