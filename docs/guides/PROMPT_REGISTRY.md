# Prompt Registry 治理指南

Prompt Registry 用来把 AI Chat 的系统提示词和模式提示词从代码里移到数据库中管理。它支持版本、激活、试调和灰度发布，同时保留代码默认 prompt 作为 fallback。

## 入口

管理员页面：

```text
/admin/prompt-templates
```

后端 API：

```http
GET    /api/v1/admin/prompt-templates
POST   /api/v1/admin/prompt-templates
PATCH  /api/v1/admin/prompt-templates/{id}/activate
POST   /api/v1/admin/prompt-templates/{id}/test
```

所有接口都需要管理员权限。

## 模板字段

| 字段 | 含义 |
|------|------|
| `id` | 模板版本 ID |
| `name` | 模板名，通常对应 `assistant_mode` |
| `version` | 版本号，例如 `stable`、`v2`、`canary-20260526` |
| `content` | 模板内容，支持 `{{variable}}` 占位符 |
| `status` | `draft`、`active`、`archived` |
| `variables` | 变量名列表 |
| `rollout_percentage` | 灰度比例，0-100 |
| `created_at` | 创建时间 |
| `created_by` | 创建人 |

同一个 `name + version` 只能创建一次。

## 推荐模板名

当前 `AIChatService` 按 `assistant_mode` 查找模板。推荐使用这些名字：

| 模板名 | 用途 |
|--------|------|
| `knowledge_qa` | 知识库问答 |
| `strategy_idea` | 策略想法扩展 |
| `backtrader_strategy` | Backtrader 策略草案生成 |
| `strategy_review` | 策略审查 |
| `trading_execution` | 交易意图解析 |

如果找不到 active 或灰度命中的模板，系统会回退到代码中的 `_MODE_INSTRUCTIONS` 默认提示词。

## 可用变量

`AIChatService` 渲染模板时传入这些变量：

| 变量 | 含义 |
|------|------|
| `question` | 用户问题，已做基础 normalize |
| `context_text` | 知识库上下文块 |
| `diagnostics_text` | 检索诊断信息 |
| `assistant_mode` | 当前回答模式 |
| `reasoning_hint` | 是否启用 thinking mode 的回答要求 |
| `quant_focus` | 知识库设置中的量化侧重点 |

示例模板：

```text
你是 Backtrader Web 的知识库助手。

当前问题：
{{question}}

知识库上下文：
{{context_text}}

回答要求：
- {{reasoning_hint}}
- 明确区分知识库事实和推断。
- 不要承诺收益。
```

## 创建模板

```http
POST /api/v1/admin/prompt-templates
Content-Type: application/json
```

```json
{
  "name": "knowledge_qa",
  "version": "canary-20260526",
  "content": "你是知识库助手。问题：{{question}}\n上下文：{{context_text}}",
  "variables": ["question", "context_text"],
  "rollout_percentage": 10
}
```

默认状态是 `draft`。

## 试调模板

试调不会影响线上调用。

```http
POST /api/v1/admin/prompt-templates/{id}/test
Content-Type: application/json
```

```json
{
  "variables": {
    "question": "什么是均线策略？",
    "context_text": "均线交叉策略通过短均线上穿长均线生成买入信号。"
  }
}
```

返回：

```json
{
  "template_id": "tpl-1",
  "name": "knowledge_qa",
  "version": "canary-20260526",
  "rendered_prompt": "你是知识库助手。问题：什么是均线策略？\n上下文：均线交叉策略通过短均线上穿长均线生成买入信号。",
  "missing_variables": []
}
```

如果模板声明了变量但试调时没有传入，`missing_variables` 会列出缺失变量，渲染结果中对应占位符会变成空字符串。

## 激活版本

```http
PATCH /api/v1/admin/prompt-templates/{id}/activate
```

同一 `name` 只会有一个 active 版本。激活新版本时，旧 active 版本会自动变成 `archived`。

## 灰度发布

灰度模板不需要设为 active。只要它：

- `status != archived`
- `rollout_percentage > 0`
- 与当前 `assistant_mode` 同名

调用时就可能被选中。

分流规则：

```text
crc32("{template_name}:{template_version}:{user_id}") % 100 < rollout_percentage
```

行为：

| 灰度比例 | 行为 |
|----------|------|
| `0` | 永不命中灰度模板 |
| `1-99` | 按用户稳定 hash 分流 |
| `100` | 有 `user_id` 时全部命中灰度模板 |

如果没有 `user_id`，系统不会走灰度候选，会回退 active 版本。

## 发布流程建议

### 1. 新建 draft/canary 模板

创建新版本，设置 `rollout_percentage = 0`。

### 2. 试调变量

用 `/test` 接口验证：

- 变量是否完整
- 输出结构是否稳定
- JSON 模式是否只返回 JSON
- 是否包含收益承诺等禁用表述

### 3. 小流量灰度

设置 `rollout_percentage = 5` 或 `10`。

观察：

- AI 调用失败率
- JSON 解析失败
- `response_chars`
- 用户反馈
- `prompt_template_version` 对应的调用分布

### 4. 扩大灰度

逐步提升到 `25`、`50`、`100`。

### 5. 激活为 stable

确认稳定后，激活该版本。旧 active 会归档。

## 回滚方式

如果灰度模板异常：

1. 把灰度模板的 `rollout_percentage` 调回 `0`。
2. 如果已经激活了新版本，重新激活旧版本。
3. 查看 `ai_call_logs.prompt_template_version` 定位受影响请求。

## 风险清单

- **JSON 输出模式**：`backtrader_strategy` 和 `trading_execution` 必须保持“只输出 JSON”。
- **投资建议表述**：不要承诺收益，不要给确定性交易建议。
- **上下文依赖**：模板必须明确要求基于知识库上下文回答。
- **变量缺失**：上线前必须用 `/test` 检查 `missing_variables`。
- **灰度比例**：不要直接从 0 跳到 100，除非只是无风险文案微调。

## 与观测日志联动

每次 AI 调用会记录：

- `prompt_template_id`
- `prompt_template_version`

这两个字段用于分析某个模板版本的表现。第一版管理界面还没有独立 A/B 分析页，可以直接通过数据库查询或后续看板扩展实现。
