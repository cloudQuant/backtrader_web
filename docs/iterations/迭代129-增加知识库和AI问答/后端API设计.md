# 迭代129 - 增加知识库和 AI 问答 - 后端 API 设计

> **文档状态**: 已优化，作为开发基线
> **最后更新**: 2026-04-23

---

## 1. 设计原则

1. API 统一由 `main.py` 挂载在 `/api/v1` 下；
2. 业务 router 文件实际位于 `src/backend/app/api/*.py`；
3. 所有业务接口默认要求 JWT 认证；
4. ID 类型统一使用 `string(UUID)`；
5. 资源列表接口优先采用现有项目常用的 `skip + limit` 风格；
6. P0 优先保证最小闭环，不引入过度复杂接口。

---

## 2. 模块划分

| 模块 | 路由前缀 | 优先级 |
|------|----------|--------|
| 知识库 | `/knowledge-base` | P0 |
| AI 问答对话 | `/kb-chat` | P0 |
| 检索 / 索引 | `/rag` | P0 |
| AI 助手 | `/ai-assistant` | P1 |
| 模型管理 | `/models` | P1 |

---

## 3. 知识库 API

### 3.1 知识库 CRUD

| 方法 | 路径 | 说明 | 优先级 |
|------|------|------|--------|
| GET | `/knowledge-base/` | 获取知识库列表 | P0 |
| POST | `/knowledge-base/` | 创建知识库 | P0 |
| GET | `/knowledge-base/{kb_id}` | 获取知识库详情 | P0 |
| PUT | `/knowledge-base/{kb_id}` | 更新知识库 | P0 |
| DELETE | `/knowledge-base/{kb_id}` | 删除知识库 | P0 |

#### 列表查询参数

| 参数 | 类型 | 说明 |
|------|------|------|
| skip | int | 跳过条数，默认 0 |
| limit | int | 返回条数，默认 20，建议最大 100 |
| search | string | 按名称/描述搜索 |

#### 示例响应

```json
{
  "items": [
    {
      "id": "36d7f9d4-8c1b-4333-8b0d-7fd9e1d2f6a1",
      "name": "量化策略知识库",
      "description": "沉淀量化策略说明、指标解释和操作手册",
      "owner_id": "9f2e5f5b-4e8f-43b7-9397-4fe8f9ecba2b",
      "document_count": 12,
      "is_public": false,
      "created_at": "2026-04-23T10:00:00Z",
      "updated_at": "2026-04-23T10:00:00Z"
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 20
}
```

### 3.2 文档管理

| 方法 | 路径 | 说明 | 优先级 |
|------|------|------|--------|
| GET | `/knowledge-base/{kb_id}/documents/` | 文档列表 | P0 |
| POST | `/knowledge-base/{kb_id}/documents/` | 创建文档/文件夹 | P0 |
| GET | `/knowledge-base/{kb_id}/documents/{doc_id}` | 文档详情 | P0 |
| PUT | `/knowledge-base/{kb_id}/documents/{doc_id}` | 更新文档 | P0 |
| DELETE | `/knowledge-base/{kb_id}/documents/{doc_id}` | 删除文档 | P0 |
| POST | `/knowledge-base/{kb_id}/documents/reorder` | 树结构/排序调整 | P1 |
| POST | `/knowledge-base/{kb_id}/documents/import` | 导入文档 | P0/P1 |

#### 创建文档请求示例

```json
{
  "title": "双均线策略",
  "content": "# 双均线策略\n\n策略说明...",
  "content_type": "markdown",
  "parent_id": null,
  "is_folder": false
}
```

#### 文档响应示例

```json
{
  "id": "840983ef-3b9d-4188-bcf9-95d90cf6b4dc",
  "knowledge_base_id": "36d7f9d4-8c1b-4333-8b0d-7fd9e1d2f6a1",
  "title": "双均线策略",
  "content": "# 双均线策略\n\n策略说明...",
  "content_type": "markdown",
  "is_folder": false,
  "parent_id": null,
  "sort_order": 0,
  "status": "draft",
  "index_status": "not_indexed",
  "indexed_at": null,
  "created_at": "2026-04-23T10:00:00Z",
  "updated_at": "2026-04-23T10:00:00Z"
}
```

#### 导入能力建议

| 格式 | 优先级 | 说明 |
|------|--------|------|
| Markdown / TXT | P0 | 作为首批必交付格式 |
| PDF / DOCX | P1 | 依赖解析库与测试结果 |

---

## 4. RAG / 索引 API

### 4.1 索引相关

| 方法 | 路径 | 说明 | 优先级 |
|------|------|------|--------|
| POST | `/rag/index` | 对单个文档建立索引 | P0 |
| POST | `/rag/batch-index` | 批量索引知识库文档 | P1 |
| DELETE | `/rag/index/{doc_id}` | 删除文档索引 | P1 |
| GET | `/rag/stats` | 查看索引统计 | P1 |

#### 单文档索引请求

```json
{
  "knowledge_base_id": "36d7f9d4-8c1b-4333-8b0d-7fd9e1d2f6a1",
  "document_id": "840983ef-3b9d-4188-bcf9-95d90cf6b4dc",
  "force_reindex": false
}
```

### 4.2 检索与问答

| 方法 | 路径 | 说明 | 优先级 |
|------|------|------|--------|
| POST | `/rag/search` | 纯检索接口 | P0 |
| POST | `/rag/ask` | 基于知识库的直接问答 | P0 |

#### `/rag/search` 请求示例

```json
{
  "knowledge_base_id": "36d7f9d4-8c1b-4333-8b0d-7fd9e1d2f6a1",
  "query": "双均线策略的开仓条件",
  "top_k": 10,
  "min_similarity": 0.3,
  "search_mode": "vector"
}
```

#### `/rag/ask` 请求示例

```json
{
  "knowledge_base_id": "36d7f9d4-8c1b-4333-8b0d-7fd9e1d2f6a1",
  "question": "双均线策略的开仓条件是什么？",
  "conversation_id": null,
  "top_k": 8,
  "min_similarity": 0.3,
  "include_citations": true,
  "model_id": "deepseek-ai/DeepSeek-V3.2",
  "thinking_mode": false
}
```

#### `/rag/ask` 响应示例

```json
{
  "answer": "双均线策略在短期均线上穿长期均线时开多，下穿时离场或反向处理。",
  "citations": [
    {
      "document_id": "840983ef-3b9d-4188-bcf9-95d90cf6b4dc",
      "document_title": "双均线策略",
      "chunk_id": "2cb0a671-cc14-4d73-a064-f906d0b126c7",
      "chunk_index": 2,
      "similarity": 0.8523
    }
  ],
  "context_chunks_used": 3,
  "tokens_used": 1250,
  "model_id": "deepseek-ai/DeepSeek-V3.2",
  "reasoning": null
}
```

---

## 5. AI 问答对话 API

### 5.1 对话管理

| 方法 | 路径 | 说明 | 优先级 |
|------|------|------|--------|
| GET | `/kb-chat/conversations` | 获取对话列表 | P0 |
| POST | `/kb-chat/conversations` | 新建对话 | P0 |
| GET | `/kb-chat/conversations/{conversation_id}` | 获取对话详情 | P1 |
| DELETE | `/kb-chat/conversations/{conversation_id}` | 删除对话 | P0 |
| GET | `/kb-chat/history/{conversation_id}` | 获取历史消息 | P0 |
| POST | `/kb-chat/send` | 发送消息并生成回答 | P0 |

#### 创建对话请求

```json
{
  "knowledge_base_id": "36d7f9d4-8c1b-4333-8b0d-7fd9e1d2f6a1",
  "title": "关于双均线策略的讨论",
  "model_id": "deepseek-ai/DeepSeek-V3.2"
}
```

#### 发送消息请求

```json
{
  "knowledge_base_id": "36d7f9d4-8c1b-4333-8b0d-7fd9e1d2f6a1",
  "conversation_id": "a0c7d0d2-3016-4bb4-b9db-1b01e65c021f",
  "question": "这个策略适合什么行情？",
  "model_id": "deepseek-ai/DeepSeek-V3.2",
  "thinking_mode": false
}
```

---

## 6. AI 助手 API（P1）

| 方法 | 路径 | 说明 | 优先级 |
|------|------|------|--------|
| POST | `/ai-assistant/improve` | 内容改进 | P1 |
| POST | `/ai-assistant/quality-check` | 质量检查 | P1 |

#### 内容改进请求示例

```json
{
  "content": "策略描述...",
  "document_type": "requirement",
  "model_id": "deepseek-ai/DeepSeek-V3.2"
}
```

#### 质量检查响应示例

```json
{
  "score": 85,
  "issues": [
    {"level": "warning", "message": "缺少验收标准"},
    {"level": "info", "message": "建议增加边界场景说明"}
  ],
  "suggestions": ["补充验收标准", "增加异常路径说明"]
}
```

---

## 7. 模型管理 API（P1）

| 方法 | 路径 | 说明 | 优先级 |
|------|------|------|--------|
| GET | `/models/` | 模型列表 | P1 |
| GET | `/models/categories` | 分类列表 | P1 |
| PUT | `/models/{model_id}` | 更新模型启停与默认配置 | P1 |
| GET | `/models/usage/stats` | 模型调用统计 | P1 |

---

## 8. 错误处理规范

| 场景 | HTTP 状态码 | 建议消息 |
|------|-------------|----------|
| 未登录或 token 无效 | 401 | 登录已失效，请重新登录 |
| 无权访问私有知识库 | 403 | 无权访问该知识库 |
| 知识库不存在 | 404 | 知识库不存在 |
| 文档不存在 | 404 | 文档不存在 |
| 对话不存在 | 404 | 对话不存在 |
| 导入格式不支持 | 422 | 当前文件格式暂不支持 |
| 请求参数非法 | 422 | 请求参数错误 |
| 向量索引失败 | 500 | 文档索引失败，请稍后重试 |
| 模型服务不可用 | 503 | AI 服务暂时不可用，请稍后重试 |

说明：前端现有 `src/frontend/src/api/index.ts` 已对 401 / 403 / 404 / 500 做统一消息处理，新增接口应尽量复用这一错误风格。

---

## 9. 开发注意事项

1. 示例中的 ID 一律为 UUID 字符串，不要使用 `number`；
2. 如果某些能力（如 `ai-assistant` / `models`）未在本期落地，允许先保留文档设计，不应阻塞 P0 主流程；
3. 若 SurrealDB 环境未就绪，开发计划应先验证连接性，再进入大规模索引和问答实现；
4. 所有列表接口建议在第一版就统一成 `items + total + skip + limit`，避免后续风格漂移。
