# Quant Tool Registry 指南

这份指南说明迭代 170 的 Quant Tool Registry 当前提供了哪些只读工具、如何做限频与 destructive guard、以及它与 AI 调用审计的关系。

## 当前实现位置

- `src/backend/app/services/quant_tools.py`
- `src/backend/app/services/quant_tools_runtime.py`
- `src/backend/app/api/quant_tools.py`
- `src/backend/tests/test_quant_tools.py`

## 设计目标

Quant Tool Registry 让 AI 与前端可以通过统一入口调用平台内部能力，而不是直接散落访问多个 service。

当前实现重点是：

- **工具列表统一暴露**
- **MCP 兼容元数据**（`output_schema / auth_level / requires_confirmation / timeout_ms / rate_limit_per_user_per_min`）
- **每用户每工具限频**
- **写操作确认与 admin 级权限门控**
- **写入 AI 调用日志与审计日志，且审计 payload 截断到 4 KB**

## 当前工具清单

当前首批工具包含：

- `markets.get_quote`
- `markets.get_history`
- `portfolio_ledger.get_summary`
- `risk.var_cvar`
- `factor.evaluate`
- `news.latest`
- `data_governance.endpoint_preview`
- `data_topics.list`
- `data_topics.peek`
- `portfolio_ledger.import_transactions`

### `markets.get_quote`

返回最新行情占位快照。

输入 schema：

```json
{
  "type": "object",
  "properties": {
    "symbol": {"type": "string"}
  },
  "required": ["symbol"]
}
```

### `data_topics.list`

列出当前 `DataTopicHub` 注册的 topics。

### `news.latest`

返回最新新闻项。

### `portfolio_ledger.import_transactions`

导入交易到账本。

这是当前唯一被标记为 destructive 的工具。

输入 schema 包含：

- `portfolio_id`
- `idempotency_key`
- `transactions`
- `confirmation_token`

## 后端 API

### 列出工具

```http
GET /api/v1/quant-tools
```

返回示例：

```json
{
  "tools": [
    {
      "name": "markets.get_quote",
      "description": "Get a latest market quote",
      "input_schema": {
        "type": "object",
        "properties": {
          "symbol": {"type": "string"}
        },
        "required": ["symbol"]
      },
      "output_schema": {
        "type": "object",
        "properties": {
          "symbol": {"type": "string"},
          "price": {"type": "number"}
        },
        "required": ["symbol", "price"]
      },
      "auth_level": "user",
      "destructive": false,
      "requires_confirmation": false,
      "timeout_ms": 5000,
      "rate_limit_per_user_per_min": 30
    }
  ]
}
```

### 调用工具

```http
POST /api/v1/quant-tools/call
Content-Type: application/json

{
  "tool_name": "markets.get_quote",
  "input": {
    "symbol": "RB2510"
  }
}
```

返回示例：

```json
{
  "status": "ok",
  "tool_name": "markets.get_quote",
  "result": {
    "symbol": "RB2510",
    "price": 100.0
  }
}
```

### 模拟 AI Chat 工具链路

```http
POST /api/v1/quant-tools/chat-simulate
Content-Type: application/json

{
  "tool_calls": ["markets.get_quote", "data_topics.list", "news.latest"]
}
```

返回示例：

```json
{
  "called_count": 3,
  "results": [
    {"tool_name": "markets.get_quote", "status": "ok"},
    {"tool_name": "data_topics.list", "status": "ok"},
    {"tool_name": "news.latest", "status": "ok"}
  ]
}
```

## 限频策略

`QuantToolRateLimiter` 当前默认策略：

- 维度：按 `user_id + tool_name`
- 窗口：`60s`
- 阈值：`30 req/min`

超限时：

```json
{
  "detail": "rate_limited"
}
```

HTTP 状态码：`429`

## Destructive Guard

当工具被标记为 `destructive=True` 时，如果没有提供：

- `confirmation_token`

则会直接拒绝：

```json
{
  "detail": "confirmation_required"
}
```

HTTP 状态码：`403`

当前 `portfolio_ledger.import_transactions` 属于这一类。

此外，部分工具会要求 `auth_level=admin`。当前实现里：

- `data_topics.peek`
- `data_governance.endpoint_preview`

如果普通用户调用，会返回：

```json
{
  "detail": "insufficient_auth_level"
}
```

## 审计与 AI 调用日志

每次工具调用进入 runtime 后，系统会写两类记录：

### `ai_call_logs`

关键字段：

- `service_name = "quant_tool"`
- `mode = <tool_name>`
- `provider = "internal"`
- `model_name = "tool-runtime"`
- `prompt_hash = sha256(f"{tool_name}:{payload}")`
- `response_chars` 按截断后的结果文本长度写入，最大 4096

### `audit_records`

关键字段：

- `event_type = "quant_tool.call"`
- `event_target = <tool_name>`
- `page_path = "/api/v1/quant-tools/call"`
- `event_data` 包含脱敏后的 `input/result/status`，并截断为 4 KB

## 前端入口

当前最小前端入口：

- 路由：`/quant-tools`
- 页面：`src/frontend/src/views/QuantToolsPage.vue`
- API wrapper：`src/frontend/src/api/marketIntel.ts`

当前页面支持：

- 加载工具列表
- 展示 `auth_level / timeout_ms / rate_limit_per_user_per_min / requires_confirmation`
- 触发 `markets.get_quote` 示例调用

## 与 MCP 兼容的边界

迭代规划希望采用 MCP 兼容 schema。当前实现已具备：

- `name`
- `description`
- `input_schema`
- `output_schema`
- `auth_level`
- `destructive`
- `requires_confirmation`
- `timeout_ms`
- `rate_limit_per_user_per_min`

但仍不是完整 MCP server，当前仍保留这些限制：

- 没有真正拆成 `registry.py / schema.py / audit.py / confirmation.py`
- schema 校验当前是内建的最小 JSON Schema 子集，不是完整 Draft-07 验证器
- `chat-simulate` 仍是 fake LLM 测试入口，不是真实模型 tool runtime
- destructive token 只校验存在性，不校验生命周期 / 签发来源

## 当前限制

- 当前工具注册仍由 runtime 内部 `_register_default_tools()` 完成，尚未拆出 registry 模块。
- `trader` 级别尚未引入真实角色映射；当前运行时主要区分 `user / admin`。
- `endpoint_preview`、`risk.var_cvar`、`factor.evaluate` 仍为占位只读实现。
