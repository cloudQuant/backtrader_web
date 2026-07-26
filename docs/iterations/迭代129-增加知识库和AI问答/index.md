# 迭代129 - 增加知识库和 AI 问答

> **文档状态**: 已优化，作为后续开发基线
> **最后更新**: 2026-04-23
> **迭代目标**: 在 backtrader_web 中引入知识库与 AI 问答能力，并保证方案与现有前后端架构一致

---

## 1. 迭代目标

本迭代目标不是把 ReqDocs 整体照搬进来，而是将其“知识库 + AI 问答”核心能力迁移并适配到 backtrader_web。

本轮交付必须满足：

1. **知识库入口位置正确**：位于侧边栏 **“账户管理”与“系统设置”之间**。
2. **AI问答入口位置正确**：位于侧边栏 **“首页”与“数据管理”之间**。
3. **核心业务闭环可用**：知识库管理 → 文档管理 → 文档索引 → AI 问答 → 引用展示。
4. **遵循现有代码规范**：前端路由、后端 API 注册、UUID 主键、认证与权限模式都要和现有项目保持一致。

---

## 2. 当前结论与重要前提

### 2.1 已确认事实

1. backtrader_web 当前前端主菜单位于：
   - `src/frontend/src/components/common/AppLayout.vue`
2. backtrader_web 当前主路由位于：
   - `src/frontend/src/router/index.ts`
3. backtrader_web 后端 API 统一通过以下方式挂载：
   - `src/backend/app/api/router.py`
   - `src/backend/app/main.py` 中 `app.include_router(api_router, prefix="/api/v1")`
4. 可选功能模块使用 `_register_optional_router()` 进行优雅注册。
5. 现有主模型大量采用 `String(36)` UUID 主键，用户表名为 `users`。

### 2.2 当前源码结论（已核对）

已确认 `ReqDocs` 源码位于 `backtrader_web` 同级目录，且以下模块真实存在：

- 后端 API：
  - `ReqDocs/backend/app/api/v1/rag.py`
  - `ReqDocs/backend/app/api/v1/kb_chat.py`
  - `ReqDocs/backend/app/api/v1/models.py`
- 后端服务：
  - `ReqDocs/backend/app/services/rag_service.py`
  - `ReqDocs/backend/app/services/kb_chat_service.py`
  - `ReqDocs/backend/app/services/embedding_service.py`
  - `ReqDocs/backend/app/services/surrealdb_service.py`
  - `ReqDocs/backend/app/services/ai_assistant.py`
- 前端页面/组件/API：
  - `ReqDocs/frontend/src/views/KnowledgeBase.vue`
  - `ReqDocs/frontend/src/views/ai/AIAssistant.vue`
  - `ReqDocs/frontend/src/components/KBChatPanel.vue`
  - `ReqDocs/frontend/src/components/RAGChatPanel.vue`
  - `ReqDocs/frontend/src/components/ModelSelector.vue`
  - `ReqDocs/frontend/src/api/kbChat.ts`
  - `ReqDocs/frontend/src/api/rag.ts`
  - `ReqDocs/frontend/src/api/models.ts`

### 2.3 关键迁移事实

1. ReqDocs 的“知识库”本质上是 **`projects + documents`** 语义，而非独立 `knowledge_base` 表。
2. ReqDocs 的 RAG 与 KB Chat 大量使用 **整数 ID**、`project_id`、`knowledge_base_id(int)`。
3. ReqDocs 后端是 **FastAPI + MySQL + MongoDB + Redis + Celery + SurrealDB**；
   backtrader_web 则应只迁移必要能力，不能照搬其基础设施复杂度。
4. ReqDocs 的 KB Chat 当前并非真正 RAG 驱动，而是更偏向“读取最近文档内容作为上下文”的知识库问答；
   真正 RAG 主流程在 `rag.py + rag_service.py + surrealdb_service.py` 中。
5. ReqDocs 前端知识库页 `KnowledgeBase.vue` 已内嵌知识库列表、文档树、导入、AI问答侧栏，是重要 UI 参考来源。

---

## 3. 范围划分

### 3.1 P0（本迭代必做）

| 模块 | 内容 |
|------|------|
| 知识库管理 | 知识库 CRUD、搜索、基础权限 |
| 文档管理 | 文档/文件夹 CRUD、树形组织、Markdown/TXT 优先 |
| 索引能力 | 文档分块、索引建立、索引状态管理 |
| AI问答 | 单知识库问答、多轮对话、引用展示 |
| 页面接入 | 侧边栏入口、主页面、路由、标题映射 |

### 3.2 P1（建议本迭代完成）

| 模块 | 内容 |
|------|------|
| AI助手 | 内容改进、质量检查 |
| 模型管理 | 模型列表、默认模型、启停配置、基础统计 |
| 文档导入增强 | PDF / DOCX / HTML |
| 检索增强 | hybrid search、rerank、思维链展示 |

### 3.3 本迭代不做

1. 与策略/回测/组合结果的深度联动
2. 多人协作与评论体系
3. 复杂 RBAC 与共享权限系统
4. 知识库版本管理
5. 异步任务编排中心与 Celery 体系

---

## 4. 推荐阅读顺序

### 面向产品 / 技术经理

1. `初始需求.md`
2. `实施计划.md`
3. `业务验收测试用例清单.md`

### 面向后端开发

1. `总体架构设计.md`
2. `数据模型设计.md`
3. `后端API设计.md`

### 面向前端开发

1. `总体架构设计.md`
2. `前端组件设计.md`
3. `业务验收测试用例清单.md`

---

## 5. 文档清单

| 文档 | 用途 | 当前状态 |
|------|------|----------|
| [初始需求.md](初始需求.md) | 需求边界、目标、约束、待澄清项 | ✅ 已优化 |
| [总体架构设计.md](总体架构设计.md) | 前后端模块边界、集成方式、迁移策略 | ✅ 已优化 |
| [数据模型设计.md](数据模型设计.md) | ORM / 表结构 / Schema / 索引建议 | ✅ 已优化 |
| [后端API设计.md](后端API设计.md) | API 资源设计、参数、错误码、优先级 | ✅ 已优化 |
| [前端组件设计.md](前端组件设计.md) | 页面、路由、组件、store、API 封装模式 | ✅ 已优化 |
| [实施计划.md](实施计划.md) | 阶段划分、里程碑、风险、交付与验证方式 | ✅ 已优化 |
| [业务验收测试用例清单.md](业务验收测试用例清单.md) | 产品验收与测试执行基线 | ✅ 已优化 |
| [开发准备与源实现核对清单.md](开发准备与源实现核对清单.md) | 正式编码前的环境、源实现、接口、数据模型核对清单 | ✅ 新增 |

---

## 6. 与现有系统的关键对齐点

### 6.1 前端对齐点

1. 修改 `AppLayout.vue` 增加菜单项时，需要同步：
   - 菜单顺序
   - `currentRoute` 的 prefix 匹配
   - `pageTitle` 映射
2. 修改 `router/index.ts` 时，应继续采用当前的嵌套路由结构。
3. API 封装应基于：
   - `src/frontend/src/api/index.ts`
4. store 应继续采用 Pinia setup store 风格。
5. ID 类型统一使用 `string`，不要沿用旧文档里的 `number` 示例。

### 6.2 后端对齐点

1. API 文件实际位于 `src/backend/app/api/`，不是 `app/api/v1/` 目录。
2. `/api/v1` 前缀由 `main.py` 统一添加，单个 router 文件只需定义业务前缀。
3. 新模块建议走 `_register_optional_router()` 方式注册，避免依赖未装齐时阻塞系统启动。
4. 新增 ORM 模型需遵循现有 UUID 主键与 SQLAlchemy 风格。
5. 外键应对齐现有表名，例如用户表使用 `users.id`。

---

## 7. 关键决策（已收敛）

| 主题 | 结论 | 说明 |
|------|------|------|
| 迁移策略 | **能力迁移 + 架构适配** | 不是机械复制 ReqDocs 文件，而是按 backtrader_web 现有结构落地 |
| 领域映射 | **Project → KnowledgeBase，Document → KBDocument** | ReqDocs 源实现以项目/文档体系为核心，迁移时需要语义重命名与结构裁剪 |
| 菜单入口 | **AI问答独立入口，知识库独立入口** | 满足用户指定的侧边栏位置要求 |
| AI助手定位 | **作为 P1 能力** | 可以作为 AI 问答页内扩展能力或独立二级页面，不阻塞 P0 |
| 向量存储 | **默认沿用 SurrealDB 方案** | 文档方案按 SurrealDB 设计，但需在开发前确认部署与依赖可行性 |
| 模型接入 | **SiliconFlow 统一接入** | 降低多模型维护复杂度 |
| 主键方案 | **UUID 字符串** | 与现有模型一致 |

---

## 8. 外部依赖与环境变量

### 8.1 建议新增依赖

| 依赖 | 用途 | 优先级 |
|------|------|--------|
| surrealdb | 向量数据库客户端 | P0 |
| tiktoken | 文档分块 Token 计算 | P0 |
| python-docx | DOCX 导入 | P1 |
| PyMuPDF | PDF 导入 | P1 |
| markdownify | HTML 转 Markdown | P1 |

### 8.2 建议新增环境变量

| 变量 | 说明 |
|------|------|
| SILICONFLOW_API_KEY | 模型调用密钥 |
| SURREAL_URL | SurrealDB 连接地址 |
| SURREAL_USER | SurrealDB 用户名 |
| SURREAL_PASS | SurrealDB 密码 |
| SURREAL_NAMESPACE | SurrealDB namespace |
| SURREAL_DATABASE | SurrealDB database |
| DEFAULT_CHAT_MODEL | 默认问答模型 |
| EMBEDDING_MODEL | 默认 embedding 模型 |

---

## 9. 开发前检查清单

在正式编码前，请先完成以下确认：

1. 已确认 ReqDocs 源实现存在，但仍需确认具体要迁移到哪个 commit/版本；
2. SurrealDB 是否作为本地开发和测试环境强依赖；
3. PDF / DOCX 导入是否纳入本次上线条件；
4. AI 助手是否并入 AI问答页，还是保留独立页面；
5. 模型管理是否对普通用户暴露，还是只做管理员能力。

如果上述问题未确认，则按本文档中的 **P0 最小闭环** 先行落地，不应因为 P1 争议阻塞整体开发。
