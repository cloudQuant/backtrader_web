# 原生股票分析能力整合进 AI 助手迭代计划

## 背景

目标是把 `http://localhost:3000/analysis/single` 代表的单股分析能力整合进当前 AI for Investor 的 AI 助手，但实现上必须完全摆脱 `TradingAgents-CN`。

这里的“摆脱”定义为：

- 不调用 `TradingAgents-CN` 的前端页面、后端 API 或运行时服务。
- 不依赖 `TradingAgents-CN` 的 MongoDB、Redis、任务队列、配置中心或数据目录。
- 不直接 import `TradingAgents-CN` 的 Python 包、`tradingagents` 模块或应用层代码。
- 可以参考并对齐其分析流程、阶段语义、结果字段和决策抽取规则，但当前仓库必须拥有独立的数据模型、服务、任务执行、报告生成和导出能力。

这里的“一致”定义为：

- 分析逻辑一致：保留 TradingAgents 的阶段顺序、角色职责、辩论/评审/交易/风控链路。
- 结果契约一致：保留 TradingAgents 的核心报告字段、最终交易决策、结构化 `decision` 字段和默认降级语义。
- 展示体验一致：用户看到的摘要、报告章节、投资倾向、置信度、风险评分、目标价等信息与 TradingAgents 结果含义一致。
- 工程实现独立：不复制或调用 TradingAgents-CN 代码，而是在当前项目中 clean-room 重建等价行为。
- 文本不承诺逐字一致：LLM 输出受模型、上下文、温度和数据源影响，验收以阶段、字段、决策语义和关键结论一致为准；如需尽量接近文本，应固定同模型、同 prompt 模板、同数据快照和低温度参数。

当前项目已有可复用基础：

- AI 助手：`AIChatPage.vue`、`kbChat.ts`、`KBChatService`、`RAGService`。
- 个股研究：`EquityResearchService` 已有搜索、行情、基本信息、历史、财务、技术因子、同行能力。
- 新闻情报：`NewsIntelligenceService` 已有新闻入库、情绪/影响/威胁分类。
- 行情服务：`QuoteService` 已有行情源和符号查询能力。
- AI 可观测：`AICallLog`、`AICallLogSink`、AI 用量统计已经可复用。
- 报告与知识库：知识库已有 markdown 内容、源文件预览和文档管理基础。

## 二次源码审阅结论

本轮重新阅读了 `TradingAgents-CN` 的 `frontend/src/views/Analysis/SingleAnalysis.vue`、`frontend/src/api/analysis.ts`、`app/routers/analysis.py`、`app/services/simple_analysis_service.py`、`app/utils/report_exporter.py`、`tradingagents/graph/trading_graph.py`，以及当前项目的 `AIChatPage.vue`、`kbChat.ts`、`KBChatService`、`EquityResearchService`、`NewsIntelligenceService`、`pyproject.toml`。

### 可以借鉴的能力契约

- 单股分析参数：股票代码、市场、分析日期、研究深度、分析模块、模型选择。
- 任务体验：提交后返回 `task_id`，展示 `pending/running/completed/failed`、进度、当前步骤、失败原因。
- 分析阶段：市场/技术、社媒情绪、新闻、基本面分析后，进入多空研究、研究经理、交易员、激进/保守/中性风险评估、风险经理终审。
- 报告分层：`market_report`、`sentiment_report`、`news_report`、`fundamentals_report`、`investment_plan`、`trader_investment_plan`、`final_trade_decision`。
- 结构化决策：从 `final_trade_decision` 抽取 `action`、`target_price`、`confidence`、`risk_score`、`reasoning`。
- 导出诉求：分析完成后从同一份报告导出 Markdown、HTML、DOCX、PDF。

### 必须避免迁移的实现

- 不复制 `SingleAnalysis.vue` 的独立页面和大表单布局，当前项目入口必须是 AI 助手。
- 不迁移 `simple_analysis_service.py`，该服务把 TradingAgentsGraph、MongoDB、Redis 进度、同步 Mongo 查询、本地文件报告、调试日志耦合在一起。
- 不迁移 `TradingAgentsGraph` 或 LangGraph 运行时，但需要原生重建等价的阶段链路和结果契约。
- 不迁移 `ReportExporter` 的 pandoc/pdfkit/wkhtmltopdf 路线，当前项目应从结构化报告直接渲染四种格式。
- 不沿用 `analysis_tasks`、`analysis_reports` 的 MongoDB 数据形态，全部进入当前项目 SQLAlchemy 数据库。

### 当前项目最佳落点

- AI 助手新增 `stock_analysis` 模式，是唯一的一等入口。
- `/stock-analysis/*` 仅作为 AI 助手的支撑接口，用于任务轮询、结果读取和文件导出，不新增 `/analysis/single` 风格页面。
- `KBChatService.send` 在 `assistant_mode=stock_analysis` 时走 `StockAnalysisAssistantService`，创建任务并写入聊天历史；普通知识问答仍走 `RAGService`。
- 前端沿用 `ChatMessageBubble` 的结构化附件模式，新增股票分析任务卡片和报告卡片，而不是把 TradingAgents-CN 的整页组件搬进来。

## 产品目标

在 AI 助手中新增“股票分析”模式。用户可以自然语言或 AI 助手右侧参数面板触发分析，例如：

> 分析 000001.SZ，A股，标准深度，重点看技术面、基本面、新闻风险和交易建议。

系统完成：

1. 识别股票代码、市场、分析日期、分析深度、分析模块。
2. 创建异步股票分析任务。
3. 在 AI 助手聊天流中显示任务进度卡片。
4. 任务完成后显示分析摘要、风险提示、分析倾向和详细报告。
5. 支持导出 `markdown`、`html`、`docx`、`pdf`。
6. 支持将报告沉淀到知识库或研究工作区。
7. 所有任务、结果、导出记录、AI 调用记录归属当前用户。
8. 不新增独立股票分析页面，所有用户可见工作流都收敛在 AI 助手聊天流和上下文面板里。
9. 分析阶段、报告字段和最终决策语义与 TradingAgents 原有结果保持兼容。

## 非目标

第一阶段不做：

- 批量股票分析。
- 实盘自动下单。
- 复刻 TradingAgents-CN 的 LangGraph、工具节点、记忆库、缓存、配置中心等运行时实现。
- 复制或翻译 `TradingAgents-CN` 的大段源码、组件、路由、服务或导出器。
- 引入 MongoDB 作为股票分析主存储。
- 引入 Redis 作为第一版必须依赖。
- 将股票分析结果宣称为投资建议。

所有输出必须明确标注：仅供研究参考，不构成投资建议。

## 总体架构

### 后端模块

新增模块建议：

- `app/schemas/stock_analysis.py`
- `app/models/stock_analysis.py`
- `app/services/stock_analysis/assistant_service.py`
- `app/services/stock_analysis/data_collector.py`
- `app/services/stock_analysis/indicators.py`
- `app/services/stock_analysis/analysis_engine.py`
- `app/services/stock_analysis/pipeline.py`
- `app/services/stock_analysis/report_builder.py`
- `app/services/stock_analysis/exporter.py`
- `app/services/stock_analysis/tasks.py`
- `app/api/stock_analysis.py`

核心设计：

```text
AI 助手 KBChatService
        |
        v
StockAnalysisAssistantService
        |
        +-- 参数解析 / 参数确认
        +-- StockAnalysisTaskService
        |
        v
StockAnalysisTaskService
        |
        +-- StockAnalysisDataCollector
        |      +-- EquityResearchService
        |      +-- NewsIntelligenceService
        |      +-- QuoteService
        |      +-- AkShare/Data Governance 数据表
        |
        +-- StockAnalysisPipeline
        |      +-- AnalystStage
        |      |      +-- MarketAnalyzer
        |      |      +-- SocialSentimentAnalyzer
        |      |      +-- NewsAnalyzer
        |      |      +-- FundamentalsAnalyzer
        |      +-- InvestmentDebateStage
        |      |      +-- BullResearcher
        |      |      +-- BearResearcher
        |      |      +-- ResearchManager
        |      +-- TraderDecisionStage
        |      +-- RiskDebateStage
        |      |      +-- RiskyRiskReviewer
        |      |      +-- ConservativeRiskReviewer
        |      |      +-- NeutralRiskReviewer
        |      |      +-- RiskManager
        |      +-- SignalExtractionStage
        |
        +-- StockAnalysisReportBuilder
        |
        +-- StockAnalysisExporter
               +-- Markdown
               +-- HTML
               +-- DOCX
               +-- PDF
```

设计约束：

- `StockAnalysisAssistantService` 是 AI 助手和股票分析领域之间的防腐层，负责把聊天请求转换为当前项目自己的任务模型。
- `StockAnalysisPipeline` 是当前项目原生流水线，不使用 `TradingAgentsGraph`、LangGraph 工具节点或 TradingAgents-CN 的配置字典，但阶段语义和输出契约要与 TradingAgents 对齐。
- `/api/v1/stock-analysis/*` 是支撑 API，只承担任务查询、结果读取、导出下载。创建任务优先从 `/api/v1/kb-chat/send` 的 `assistant_mode=stock_analysis` 进入。
- 模块命名可使用 `Analyzer/Researcher/Manager/Stage`，但必须实现为当前项目自己的服务类和 Pydantic 数据契约，不 import TradingAgents-CN。

### 前端模块

新增或扩展：

- `src/frontend/src/api/stockAnalysis.ts`
- `src/frontend/src/components/aichat/StockAnalysisTaskCard.vue`
- `src/frontend/src/components/aichat/StockAnalysisReportCard.vue`
- `src/frontend/src/composables/useStockAnalysisTask.ts`
- `src/frontend/src/stores/kbChat.ts`
- `src/frontend/src/api/kbChat.ts`
- `src/frontend/src/composables/useAIChatRendering.ts`
- `src/frontend/src/views/AIChatPage.vue`

不新增或迁移：

- 不新增 `src/frontend/src/views/Analysis/SingleAnalysis.vue`。
- 不把 TradingAgents-CN 的整页表单、卡片布局、进度面板整段搬入当前项目。
- 不新增 `/analysis/single` 前端路由。

AI 助手模式新增：

```ts
export type KBAssistantMode =
  | 'knowledge_qa'
  | 'strategy_idea'
  | 'backtrader_strategy'
  | 'strategy_review'
  | 'trading_execution'
  | 'stock_analysis'
```

`stockAnalysisApi` 只用于轮询、读取结果和导出：

- `getTask(taskId)`
- `getTaskResult(taskId)`
- `exportReport(reportId, format)`

任务创建优先通过 `kbChatApi.send({ assistant_mode: 'stock_analysis', ... })` 完成，以保证聊天历史、用户意图、任务卡片和报告卡片是一条连续对话。

## TradingAgents 行为兼容契约

这一节是实现时的硬约束。目标不是迁移 TradingAgents-CN 的源码，而是在当前项目中重建与原 TradingAgents 一致的分析逻辑和结果含义。

### 阶段顺序

默认阶段顺序与 TradingAgents 保持一致：

1. `MarketAnalyzer`
   - 对齐 TradingAgents 的 `Market Analyst`。
   - 生成 `market_report`。

2. `SocialSentimentAnalyzer`
   - 对齐 TradingAgents 的 `Social Analyst`。
   - 生成 `sentiment_report`。
   - A 股数据源不足时允许 degraded，但字段仍保留。

3. `NewsAnalyzer`
   - 对齐 TradingAgents 的 `News Analyst`。
   - 生成 `news_report`。

4. `FundamentalsAnalyzer`
   - 对齐 TradingAgents 的 `Fundamentals Analyst`。
   - 生成 `fundamentals_report`。

5. `InvestmentDebateStage`
   - 对齐 `Bull Researcher`、`Bear Researcher`、`Research Manager`。
   - 生成 `bull_researcher`、`bear_researcher`、`research_team_decision`、`investment_plan`。

6. `TraderDecisionStage`
   - 对齐 TradingAgents 的 `Trader`。
   - 输入分析师报告和 `investment_plan`。
   - 生成 `trader_investment_plan`。

7. `RiskDebateStage`
   - 对齐 `Risky Analyst`、`Safe Analyst`、`Neutral Analyst`、`Risk Judge`。
   - 生成 `risky_analyst`、`safe_analyst`、`neutral_analyst`、`risk_management_decision`、`final_trade_decision`。

8. `SignalExtractionStage`
   - 对齐 TradingAgents 的 `process_signal` 行为。
   - 从 `final_trade_decision` 抽取结构化 `decision`。

`selected_modules` 第一版应映射到 TradingAgents 的 `selected_analysts` 语义：

- `market` -> `market_report`
- `social` -> `sentiment_report`
- `news` -> `news_report`
- `fundamentals` -> `fundamentals_report`

即使用户只选择部分分析师，后续多空研究、交易员、风险评审和最终决策仍应执行，只是基于已生成的报告和 degraded 占位报告进行综合。

### 兼容输出字段

规范化报告仍使用当前项目自己的 `StockAnalysisReportPayload`，但必须提供 TradingAgents 兼容字段：

```json
{
  "tradingagents_compat": {
    "market_report": "...",
    "sentiment_report": "...",
    "news_report": "...",
    "fundamentals_report": "...",
    "bull_researcher": "...",
    "bear_researcher": "...",
    "research_team_decision": "...",
    "investment_plan": "...",
    "trader_investment_plan": "...",
    "risky_analyst": "...",
    "safe_analyst": "...",
    "neutral_analyst": "...",
    "risk_management_decision": "...",
    "final_trade_decision": "..."
  }
}
```

页面、导出和知识库保存可以使用更友好的章节名，但内容必须来自这些兼容阶段输出，避免生成一套与 TradingAgents 含义不同的新报告。

### 决策抽取兼容

`SignalExtractionStage` 输出必须兼容 TradingAgents 的 `decision`：

```json
{
  "action": "买入|持有|卖出",
  "target_price": 12.34,
  "confidence": 0.7,
  "risk_score": 0.5,
  "reasoning": "..."
}
```

兼容规则：

- `action` 只允许中文 `买入`、`持有`、`卖出`，英文 BUY/HOLD/SELL 必须映射。
- `confidence` 和 `risk_score` 必须限制在 `0-1`。
- A 股目标价按人民币，港股/美股按对应市场货币，币种判断要与当前符号规范一致。
- 无法抽取决策时默认 `持有`，`confidence=0.5`，`risk_score=0.5`，并在 `reasoning` 中说明降级原因。
- `summary` 优先来自 `final_trade_decision` 的前段摘要，`recommendation` 来自结构化 `decision`，保持 TradingAgents 结果展示语义。

### 一致性验收口径

- 强一致：阶段顺序、字段存在性、结构化 `decision`、默认降级、报告章节来源。
- 语义一致：同一份数据和同一模型配置下，最终 `action`、风险方向、主要理由应一致或可解释地接近。
- 不要求：LLM 生成文本逐字一致、日志格式一致、内部运行时对象一致。
- 如需要更接近原 TradingAgents 文本，应固定模型、temperature、数据快照、分析日期和 prompt 模板版本，并维护 golden case 对比。

## 数据模型

### stock_analysis_tasks

用于记录任务生命周期。

字段建议：

- `id`
- `user_id`
- `conversation_id`
- `assistant_message_id`
- `source`
- `symbol`
- `symbol_name`
- `market_type`
- `analysis_date`
- `research_depth`
- `selected_modules`
- `request_text`
- `status`
- `progress`
- `current_step`
- `message`
- `step_events_json`
- `parameters_json`
- `data_quality_json`
- `error_message`
- `created_at`
- `started_at`
- `completed_at`
- `updated_at`

说明：

- `source` 第一版固定为 `ai_assistant`，用于避免后续误加独立页面入口时混淆来源。
- `assistant_message_id` 用于聊天历史恢复时定位任务卡片。
- `step_events_json` 保存轻量步骤日志，替代 TradingAgents-CN 的 Redis 进度流。
- `data_quality_json` 保存数据完整度、缺失数据、降级原因，避免报告伪装为全量分析。

状态枚举：

- `pending`
- `running`
- `completed`
- `failed`
- `cancelled`

### stock_analysis_reports

用于保存规范化报告。

字段建议：

- `id`
- `task_id`
- `user_id`
- `symbol`
- `market_type`
- `analysis_date`
- `title`
- `summary`
- `recommendation_label`
- `confidence_score`
- `risk_level`
- `technical_score`
- `fundamental_score`
- `news_score`
- `risk_score`
- `source_snapshot_json`
- `data_quality_json`
- `report_json`
- `markdown_content`
- `html_content`
- `created_at`
- `updated_at`

说明：

- `source_snapshot_json` 保存生成报告时使用的行情、财务、新闻、技术因子摘要，保证导出与页面展示可复现。
- `report_json` 是唯一事实来源，`markdown_content` 和 `html_content` 是缓存产物，可以重建。

### stock_analysis_exports

用于记录导出文件。

字段建议：

- `id`
- `report_id`
- `user_id`
- `format`
- `file_name`
- `file_path`
- `content_type`
- `file_size`
- `status`
- `error_message`
- `created_at`

## 报告结构

后端应先生成统一结构化报告，再从该报告派生多种导出格式。

建议 `StockAnalysisReportPayload`：

```json
{
  "meta": {
    "symbol": "000001.SZ",
    "symbol_name": "平安银行",
    "market_type": "A股",
    "analysis_date": "2026-06-15",
    "generated_at": "2026-06-15T10:00:00+08:00",
    "research_depth": "标准"
  },
  "executive_summary": "...",
  "decision": {
    "label": "持有",
    "confidence_score": 0.62,
    "risk_level": "中等",
    "reasoning": "..."
  },
  "sections": [
    {
      "id": "technical",
      "title": "技术分析",
      "summary": "...",
      "findings": [],
      "score": 68
    },
    {
      "id": "fundamental",
      "title": "基本面分析",
      "summary": "...",
      "findings": [],
      "score": 72
    },
    {
      "id": "news",
      "title": "新闻与情绪",
      "summary": "...",
      "findings": [],
      "score": 55
    },
    {
      "id": "risk",
      "title": "风险评估",
      "summary": "...",
      "findings": [],
      "score": 61
    }
  ],
  "tradingagents_compat": {
    "market_report": "...",
    "sentiment_report": "...",
    "news_report": "...",
    "fundamentals_report": "...",
    "bull_researcher": "...",
    "bear_researcher": "...",
    "research_team_decision": "...",
    "investment_plan": "...",
    "trader_investment_plan": "...",
    "risky_analyst": "...",
    "safe_analyst": "...",
    "neutral_analyst": "...",
    "risk_management_decision": "...",
    "final_trade_decision": "..."
  },
  "data_sources": [],
  "source_snapshot": {},
  "data_quality": {
    "status": "ok",
    "missing_fields": [],
    "degraded_reasons": []
  },
  "assumptions": [],
  "limitations": [],
  "disclaimer": "本报告仅供研究参考，不构成投资建议。"
}
```

## 导出能力设计

### 支持格式

必须支持：

- `markdown`
- `html`
- `docx`
- `pdf`

API：

```http
GET /api/v1/stock-analysis/reports/{report_id}/export?format=markdown
GET /api/v1/stock-analysis/reports/{report_id}/export?format=html
GET /api/v1/stock-analysis/reports/{report_id}/export?format=docx
GET /api/v1/stock-analysis/reports/{report_id}/export?format=pdf
```

Content-Type：

- markdown: `text/markdown; charset=utf-8`
- html: `text/html; charset=utf-8`
- docx: `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- pdf: `application/pdf`

### 导出实现

推荐使用“统一报告模型 -> Markdown -> HTML/DOCX/PDF”的管线。

```text
StockAnalysisReportPayload
        |
        v
Markdown template
        |
        +-- markdown response
        +-- HTML renderer
        +-- DOCX renderer
        +-- PDF renderer
```

依赖建议：

- Markdown 渲染：先用 Jinja2 模板直接生成 `.md`，不需要新依赖。
- HTML 渲染：Jinja2 模板生成完整 HTML，复用统一 CSS。
- DOCX 渲染：新增 `python-docx`，直接从 `StockAnalysisReportPayload` 写入文档结构。
- PDF 渲染：优先使用 headless Chromium/Playwright 从 HTML 打印为 PDF；若运维不接受浏览器依赖，再评估 WeasyPrint。

建议在 `src/backend/pyproject.toml` 新增可选依赖组：

```toml
[project.optional-dependencies]
reports = [
    "python-docx>=1.1.0",
    "playwright>=1.45.0",
]
```

实现边界：

- 不使用 TradingAgents-CN 的 `app/utils/report_exporter.py`。
- 不强依赖 pandoc、pypandoc、pdfkit、wkhtmltopdf。
- DOCX 和 PDF 生成失败只影响对应导出请求，不改变分析任务的 `completed` 状态。
- 若运行环境未安装 `reports` 依赖，导出接口返回明确的 `501/503` 风格错误和安装提示，Markdown/HTML 仍可用。

PDF 选择理由：

- HTML 是报告主展示格式，Chromium 打印能最大程度复用 HTML/CSS。
- 避免维护两套版式。
- 可在 CI 中用一个最小报告做 smoke test。

导出文件建议存储在：

```text
data/exports/stock-analysis/{user_id}/{report_id}/
```

文件命名：

```text
{symbol}_{analysis_date}_stock_analysis.{ext}
```

验收：

- 四种格式均可下载。
- 导出的内容包含相同章节、风险提示和生成时间。
- 文件名、Content-Type、中文字符、表格和标题层级正确。
- PDF 至少能在 macOS Preview、Chrome、Adobe Reader 中打开。

## API 设计

### AI 助手创建入口

```http
POST /api/v1/kb-chat/send
```

请求：

```json
{
  "knowledge_base_id": "kb_id",
  "conversation_id": "optional",
  "assistant_mode": "stock_analysis",
  "question": "分析 000001.SZ，A股，标准深度，重点看技术面、基本面、新闻风险和交易建议。",
  "model_id": "volcengine_ark::deepseek-v4-pro",
  "stock_analysis_params": {
    "symbol": "000001.SZ",
    "market_type": "A股",
    "analysis_date": "2026-06-15",
    "research_depth": "标准",
    "selected_modules": ["technical", "fundamental", "news", "risk"],
    "include_sentiment": true,
    "include_risk": true,
    "language": "zh-CN"
  }
}
```

响应：

```json
{
  "conversation_id": "uuid",
  "answer": "已创建 000001.SZ 的股票分析任务。",
  "assistant_mode": "stock_analysis",
  "stock_analysis_task": {
    "task_id": "uuid",
    "status": "pending",
    "symbol": "000001.SZ",
    "progress": 0
  }
}
```

说明：

- `stock_analysis_params` 是建议新增字段；如果第一版希望改动更小，也可以把右侧面板参数序列化进 `question`，由后端解析。
- `KBChatService.send` 根据 `assistant_mode` 分流，`stock_analysis` 不走普通 RAG 回答，而是调用 `StockAnalysisAssistantService.create_task_from_chat()`。
- 直接 `POST /api/v1/stock-analysis/tasks` 可以作为内部调试接口或后续开放接口，但不是第一版用户入口。

### 查询任务状态

```http
GET /api/v1/stock-analysis/tasks/{task_id}
```

响应：

```json
{
  "task_id": "uuid",
  "status": "running",
  "progress": 45,
  "current_step": "fundamental_analysis",
  "message": "正在生成基本面分析"
}
```

### 获取结果

```http
GET /api/v1/stock-analysis/tasks/{task_id}/result
```

响应：

```json
{
  "task_id": "uuid",
  "report_id": "uuid",
  "status": "completed",
  "report": {}
}
```

### 导出报告

```http
GET /api/v1/stock-analysis/reports/{report_id}/export?format=pdf
```

### 支撑 API 边界

- 不提供 `/api/analysis/single` 兼容路由。
- 不提供 TradingAgents-CN 风格的 `/api/analysis/tasks/{id}/status` 和 `/api/analysis/tasks/{id}/result` 兼容层。
- 不把导出格式设计成 TradingAgents-CN 的 `pdf/excel/json`，第一版只支持用户要求的 `markdown/html/docx/pdf`。

## AI 助手集成方式

### 用户体验

AI 助手新增“股票分析”模式。

右侧上下文面板在该模式下显示：

- 股票代码
- 市场类型
- 分析日期
- 深度：快速 / 基础 / 标准 / 深度 / 全面
- 模块：技术面 / 基本面 / 新闻情绪 / 风险
- 模型选择
- 导出格式快捷入口

聊天流中显示：

1. 用户问题。
2. 助手确认分析参数。
3. 股票分析任务卡片。
4. 完成后的报告摘要卡片。
5. 导出按钮：Markdown / HTML / DOCX / PDF。

### 消息结构扩展

`KBAskResponse`、`KBHistoryMessage`、`KBChatMessage` 建议新增：

```ts
stockAnalysisTask?: {
  taskId: string
  symbol: string
  status: string
  progress: number
  currentStep?: string
}

stockAnalysisReport?: {
  reportId: string
  symbol: string
  summary: string
  decisionLabel: string
  riskLevel: string
  confidenceScore?: number
  exportFormats: Array<'markdown' | 'html' | 'docx' | 'pdf'>
}
```

后端对应字段建议使用 snake_case：

```py
stock_analysis_task: StockAnalysisTaskCard | None = None
stock_analysis_report: StockAnalysisReportCard | None = None
```

聊天历史恢复：

- `ChatMessage` 需要能够保存结构化附件。推荐新增 `metadata_json` 或明确字段，而不是把卡片数据塞进 `content`。
- 历史加载时，如果任务未完成，前端继续轮询 `GET /stock-analysis/tasks/{task_id}`。
- 历史加载时，如果报告已完成，前端直接展示 `StockAnalysisReportCard` 并保留导出按钮。

### 触发方式

第一版采用 AI 助手显式模式触发：

- 用户切换到“股票分析”模式。
- 输入问题或填写右侧参数面板。
- 前端调用 `kbChatApi.send()`，传入 `assistant_mode: 'stock_analysis'`。
- 后端解析参数、创建任务、返回任务卡片。
- 前端通过 `stockAnalysisApi.getTask()` 轮询状态，通过 `stockAnalysisApi.getTaskResult()` 获取报告。

第二版再做自然语言自动识别：

- 在普通问答中识别“分析 000001.SZ”。
- 弹出参数确认。
- 用户确认后创建任务。

### 前端交互边界

- 右侧参数面板只在 `stock_analysis` 模式出现。
- 消息卡片使用现有 `ChatMessageBubble` 的扩展点挂载，不新增独立页面。
- 导出按钮位于报告卡片内，点击后调用 `stockAnalysisApi.exportReport()`。
- 聊天输入区不出现大段说明文字，避免把股票分析做成落地页式交互。

## 原生分析引擎设计

### 分析模块

第一版建议实现与 TradingAgents 行为一致的 8 个阶段：

1. `AnalystStage`
   - 输入：股票、日期、市场、数据快照、用户选择的分析师。
   - 输出：`market_report`、`sentiment_report`、`news_report`、`fundamentals_report`。

2. `InvestmentDebateStage`
   - 输入：四类分析师报告。
   - 输出：`bull_researcher`、`bear_researcher`、`research_team_decision`、`investment_plan`。

3. `TraderDecisionStage`
   - 输入：`investment_plan` 和四类分析师报告。
   - 输出：`trader_investment_plan`。

4. `RiskDebateStage`
   - 输入：交易员计划、分析师报告、风险数据。
   - 输出：`risky_analyst`、`safe_analyst`、`neutral_analyst`、`risk_management_decision`、`final_trade_decision`。

5. `SignalExtractionStage`
   - 输入：`final_trade_decision`、股票市场信息。
   - 输出：结构化 `decision`。

6. `ReportNormalizationStage`
   - 输入：所有阶段输出和 `decision`。
   - 输出：当前项目的 `StockAnalysisReportPayload`。

7. `ExportRenderingStage`
   - 输入：`StockAnalysisReportPayload`。
   - 输出：Markdown、HTML、DOCX、PDF。

8. `KnowledgePersistenceStage`
   - 输入：报告 payload。
   - 输出：知识库/研究工作区沉淀结果。

阶段内可以用规则和当前项目数据服务实现数据准备，但最终报告生成逻辑必须以 TradingAgents 的阶段结果为主线，而不是直接生成一份全新的通用股票报告。

### Clean-room 实现规则

- 复用 TradingAgents 的行为契约，不复制 TradingAgents-CN 的源码。
- 不调用 `TradingAgentsGraph.propagate()` 或导入 `tradingagents` 模块。
- 不复制 `process_signal` 代码，但需要实现 `StockSignalExtractor`，保持等价输入、输出、默认值和中英文动作映射。
- 可以保留 `market_report`、`sentiment_report`、`final_trade_decision` 等兼容字段作为 `tradingagents_compat` 输出，但数据库主模型仍使用当前项目的 `sections`、`decision`、`data_quality`。
- 每个阶段输入输出都用 Pydantic schema 固定，便于测试和降级。
- 多空研究、研究经理、交易员、风险评审、风险经理必须作为显式阶段存在；可以先用单轮实现，不需要复制 LangGraph 条件边和递归机制。

### AI 调用原则

- 每个模块先用规则和结构化数据生成基础结论。
- AI 负责生成 TradingAgents 等价阶段的报告、辩论观点、交易员计划和风险终审，不直接伪造数据。
- Prompt 必须写入 Prompt 治理或本地模板，便于版本化；模板应以 TradingAgents 阶段职责为蓝本做 clean-room 改写。
- 第一版推荐固定低 temperature，并记录模型、模板版本、数据快照和分析日期，便于与 TradingAgents 结果做 golden case 对比。
- 每次 AI 调用写入 `AICallLog`。
- AI 失败时任务不一定失败，但 degraded 报告仍要保留 TradingAgents 兼容字段和阶段占位，不能退化成另一套报告结构。

## 迭代拆分

### 迭代 1：AI 助手契约与原生任务骨架

目标：先把“股票分析是 AI 助手能力”这条主线固定下来，并建立完全独立的原生任务闭环。

改动：

- `KBAssistantMode` 增加 `stock_analysis`。
- `KBChatRequest` 增加可选 `stock_analysis_params`，或约定第一版从 `question` 解析参数。
- `KBChatResponse`、`ChatMessageResponse`、前端 `KBChatMessage` 增加 `stock_analysis_task` 和 `stock_analysis_report` 结构化附件。
- `KBChatService.send` 增加 `assistant_mode=stock_analysis` 分支，调用 `StockAnalysisAssistantService`。
- 新增 `stock_analysis_tasks`、`stock_analysis_reports`、`stock_analysis_exports` 模型和 Alembic 迁移。
- 新增 Pydantic schemas。
- 新增 `StockAnalysisTaskService`。
- 新增 `GET /stock-analysis/tasks/{id}`、`GET /stock-analysis/tasks/{id}/result`。
- 任务执行先使用同步后台任务或轻量 `asyncio.create_task`，后续再接统一队列。

验收：

- 在 AI 助手里选择 `stock_analysis` 并发送问题后，可以创建任务。
- `kb-chat/send` 返回任务卡片数据。
- 任务归属当前用户。
- 状态从 `pending` 到 `running` 到 `completed`。
- 不依赖 `TradingAgents-CN`。
- 不新增 `/analysis/single` 页面或兼容路由。

### 迭代 2：TradingAgents 兼容流水线与数据采集

目标：先建立与 TradingAgents 阶段顺序和输出字段一致的原生流水线，确保即使数据或 AI 降级，结果结构仍与原 TradingAgents 兼容。

改动：

- 新增 `StockAnalysisPipeline` 和各阶段 Pydantic 输入/输出 schema。
- 新增 `AnalystStage`、`InvestmentDebateStage`、`TraderDecisionStage`、`RiskDebateStage`、`SignalExtractionStage` 的空实现/规则实现。
- 新增 `StockAnalysisDataCollector`。
- 复用 `EquityResearchService` 获取行情、历史、财务、技术、同行。
- 复用 `NewsIntelligenceService` 获取相关新闻和情绪。
- 新增技术指标计算：收益率、波动率、均线、动量、最大回撤。
- 新增基础评分器：市场/技术评分、基本面评分、新闻评分、情绪评分、风险评分。
- 新增 `StockSignalExtractor`，实现 TradingAgents `decision` 的等价字段、默认值和动作映射。

验收：

- `000001.SZ` 可以生成包含 `tradingagents_compat` 全字段的结构化报告。
- 报告字段至少包含 `market_report`、`sentiment_report`、`news_report`、`fundamentals_report`、`investment_plan`、`trader_investment_plan`、`final_trade_decision`、`decision`。
- `decision.action` 只出现 `买入/持有/卖出`，默认降级与 TradingAgents 语义一致。
- 数据缺失时生成 degraded 报告，不让任务崩溃。

### 迭代 3：TradingAgents 等价 AI 阶段与综合决策

目标：用当前项目 AI 调用基础设施生成与 TradingAgents 阶段职责一致的中文分析结果。

改动：

- 新增 `StockAnalysisEngine`。
- 新增各阶段 prompt 模板：市场、社媒情绪、新闻、基本面、多头研究、空头研究、研究经理、交易员、激进风险、保守风险、中性风险、风险经理、信号抽取。
- 通过当前 AI 调用基础设施调用模型，不引入 TradingAgents-CN 的模型配置中心。
- 记录 AI 调用到 `AICallLog`。
- 增加预算检查和超时控制。
- 固定模型参数、模板版本和数据快照，支持 golden case 对比。

验收：

- AI 可用时按 TradingAgents 阶段输出完整中文报告，不跳过多空研究、交易员和风险终审。
- 同一数据快照下，最终 `action`、风险方向、核心理由与 TradingAgents 参考结果语义一致或差异可解释。
- AI 不可用时生成 degraded 兼容报告，字段不缺失。
- AI 可观测页面可筛选 `service_name=stock_analysis`。

### 迭代 4：报告生成与四格式导出

目标：分析完成后可导出 Markdown、HTML、DOCX、PDF。

改动：

- 新增 `StockAnalysisReportBuilder`。
- 新增 `StockAnalysisExporter`。
- 新增 markdown/html/docx/pdf renderer。
- 新增导出 API。
- 新增导出文件记录表。
- 报告卡片增加导出按钮。

验收：

- 四种格式均可导出。
- 中文标题、表格、风险提示正常。
- 导出内容与页面报告一致。
- 导出失败有明确错误，不影响报告查看。
- 未安装 DOCX/PDF 可选依赖时，Markdown/HTML 仍正常。

### 迭代 5：AI 助手前端集成

目标：把单股分析完整落到 AI 助手工作台，而不是独立页面。

改动：

- 增加 `stock_analysis` 助手模式。
- 增加股票分析右侧参数面板。
- 增加 `StockAnalysisTaskCard`。
- 增加 `StockAnalysisReportCard`。
- 增加任务轮询 composable。
- 聊天历史支持恢复报告卡片。
- 只扩展 `AIChatPage.vue`、`ChatMessageBubble.vue` 和 aichat 子组件，不新增股票分析页面路由。

验收：

- 在 AI 助手中可以创建股票分析任务。
- 进度卡片自动刷新。
- 完成后展示报告摘要和导出按钮。
- 刷新页面后任务和报告仍可恢复。
- 代码审查确认没有从 TradingAgents-CN 复制整段组件结构。

### 迭代 6：知识库与研究工作区沉淀

目标：分析结果能继续驱动当前平台工作流。

改动：

- 报告保存到知识库文档。
- 报告添加到研究工作区。
- 从报告一键生成策略构思 prompt。
- 从报告一键进入 Backtrader 策略生成模式。

验收：

- 报告能保存为知识库 markdown 文档。
- 后续 AI 问答能引用该报告。
- 用户可以从股票分析继续进入策略生成链路。

### 迭代 7：稳定性、权限与质量门禁

目标：达到可演示和可试点状态。

改动：

- 任务并发限制。
- 用户级权限隔离。
- 任务取消。
- 失败重试。
- 日志脱敏。
- 导出文件清理策略。
- E2E 验收脚本。

验收：

- 并发任务不会拖垮 AI 助手。
- 非本人无法访问任务、报告、导出文件。
- PDF/DOCX 生成失败不会导致任务失败。
- CI 覆盖后端 API、导出器、前端卡片。

## 测试计划

后端：

- `tests/test_stock_analysis_api.py`
- `tests/test_stock_analysis_service.py`
- `tests/test_stock_analysis_exporter.py`
- `tests/test_stock_analysis_permissions.py`
- `tests/test_kb_chat_stock_analysis_mode.py`
- `tests/test_stock_analysis_tradingagents_compat.py`
- `tests/fixtures/stock_analysis/tradingagents_golden_cases/*.json`

前端：

- `src/__tests__/api/stockAnalysis.test.ts`
- `src/__tests__/api/kbChatStockAnalysis.test.ts`
- `src/__tests__/components/aichat/StockAnalysisTaskCard.test.ts`
- `src/__tests__/components/aichat/StockAnalysisReportCard.test.ts`
- `src/__tests__/views/AIChatPage.test.ts`

E2E：

- 登录。
- 进入 AI 助手。
- 切换“股票分析”。
- 提交 `000001.SZ`。
- 等待任务完成或 mock 完成。
- 展示报告。
- 下载 markdown/html/docx/pdf。

TradingAgents 一致性测试：

- 使用固定数据快照、固定分析日期、固定模型参数或 mock LLM 响应生成 golden case。
- 校验阶段顺序与 TradingAgents 一致。
- 校验 `tradingagents_compat` 全字段存在且非空或明确 degraded。
- 校验 `decision` 字段、默认值、动作映射、目标价抽取和风险评分范围。
- 对真实 LLM 输出只做语义断言，不做逐字字符串断言。

防迁移检查：

- `rg -n "TradingAgents|tradingagents|TradingAgentsGraph|SingleAnalysis|/analysis/single|analysis_tasks|analysis_reports" src/backend src/frontend` 不应命中新功能代码。
- `rg -n "pypandoc|pdfkit|wkhtmltopdf|MongoClient|get_mongo_db|RedisProgressTracker" src/backend/app/services/stock_analysis src/backend/app/api/stock_analysis.py` 不应命中。
- 新增股票分析组件不应包含从 TradingAgents-CN 大段复制的模板结构、类名或样式名。

## 验收标准

功能验收：

- AI 助手里有“股票分析”模式。
- 用户可以提交单股分析任务。
- 任务有进度、当前步骤和失败信息。
- 任务完成后生成结构化报告。
- 支持 markdown、html、docx、pdf 导出。
- 分析阶段和结果字段与 TradingAgents 兼容。
- 报告可保存到知识库。
- 不依赖 `TradingAgents-CN`。
- 用户不需要离开 AI 助手即可完成分析、查看结果和导出。

技术验收：

- 无 `TradingAgents-CN` API 调用。
- 无 `tradingagents` 包 import。
- 无 `TradingAgentsGraph`、`SingleAnalysis.vue`、`/analysis/single` 兼容代码。
- 无 MongoDB 强依赖。
- 无 Redis 第一版强依赖。
- 所有新增数据进入当前项目数据库。
- 所有 AI 调用进入当前项目 AI 可观测。
- 新增代码通过当前项目自有 `Stage/Analyzer/Researcher/Manager/Pipeline` 接口组织，不复制 TradingAgents-CN 服务实现。
- `tests/test_stock_analysis_tradingagents_compat.py` 覆盖阶段顺序、兼容字段和 `decision` 抽取。
- Ruff、pytest、typecheck、frontend tests 通过。

安全与合规验收：

- 报告中包含免责声明。
- 任务和报告按用户隔离。
- Prompt 不保存敏感原文，只记录 hash 或模板 ID。
- 导出文件路径不能被用户输入穿透。
- 下载接口校验用户权限。

## 风险与对策

| 风险 | 影响 | 对策 |
| --- | --- | --- |
| PDF 生成依赖较重 | 部署复杂 | 先用 HTML/Markdown 打通，PDF 使用 Playwright Chromium；部署不接受时切换 WeasyPrint |
| 数据源不完整 | 报告质量不稳定 | 报告增加 `data_quality` 和 `limitations`，缺失时 degraded 输出 |
| AI 调用超时 | 用户等待时间长 | 任务异步化，AI 失败降级为 TradingAgents 兼容 degraded 报告 |
| 多格式导出版式不一致 | 用户体验差 | 统一报告模型和模板，所有格式从同一 payload 派生 |
| 分析结果被误解为投资建议 | 合规风险 | 页面、报告、导出文件均加免责声明 |
| 直接迁移 TradingAgents-CN 代码导致依赖污染 | 工程风险 | 只做 clean-room 原生实现，不 import、不调用、不复用运行时，并在 PR 中执行防迁移检查 |
| 入口变成独立股票分析页 | 产品割裂 | 第一版只在 AI 助手暴露入口，支撑 API 不配独立页面 |
| `kb-chat/send` 继续只支持 RAG | 集成不完整 | 为 `stock_analysis` 增加明确分支和结构化附件，保持普通 RAG 模式不受影响 |
| 原生实现结果偏离 TradingAgents | 产品风险 | 建立 TradingAgents 行为兼容契约、golden case、阶段字段快照和语义一致性测试 |
| LLM 文本无法逐字一致 | 预期管理风险 | 验收以阶段、字段、决策语义一致为准；需要更接近时固定模型、数据快照、模板版本和低 temperature |

## 推荐排期

| 迭代 | 内容 | 预估 |
| --- | --- | --- |
| 1 | AI 助手契约和任务骨架 | 1-2 天 |
| 2 | TradingAgents 兼容流水线与数据采集 | 2-4 天 |
| 3 | TradingAgents 等价 AI 阶段与综合决策 | 3-5 天 |
| 4 | 四格式导出 | 2-3 天 |
| 5 | AI 助手前端完整集成 | 2-3 天 |
| 6 | 知识库/工作区沉淀 | 1-2 天 |
| 7 | 稳定性、权限、E2E | 2-3 天 |

完整第一版约 13-23 个工作日。若先做演示版，可压缩为：

1. AI 助手 `stock_analysis` 模式和任务模型。
2. TradingAgents 兼容流水线和 degraded 阶段输出。
3. AI 助手任务卡片和报告卡片。
4. markdown/html/docx/pdf 导出。

演示版约 6-10 个工作日。

## 第一版交付清单

- `stock_analysis_tasks` 表。
- `stock_analysis_reports` 表。
- `stock_analysis_exports` 表。
- `kb-chat/send` 的 `stock_analysis` 分支。
- TradingAgents 兼容流水线。
- `tradingagents_compat` 报告字段。
- `StockSignalExtractor` 决策抽取。
- 股票分析任务支撑 API。
- 股票分析报告 API。
- 报告导出 API。
- AI 助手“股票分析”模式。
- 任务进度卡片。
- 报告摘要卡片。
- markdown/html/docx/pdf 导出按钮。
- 权限测试。
- 导出器测试。
- TradingAgents 兼容契约测试。
- AI 助手前端测试。
- 一条本地验收脚本或 E2E 用例。
- 一条防迁移检查命令记录。
