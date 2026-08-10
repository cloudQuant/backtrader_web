# 迭代 191 计划改进建议

> 文档状态：历史审查输入，非迭代 191 的权威实施或验收依据。
>
> 该快照包含已被后续计划覆盖以及经代码核验不准确的判断。最终处置、事实纠正和
> 实施落点以 [改进建议处置结论](./IMPROVEMENT_REVIEW.md) 为准；请勿直接从本文件
> 创建任务或验收结论。
>
> 分析日期：2026-08-01
>
> 分析范围：README.md、RESEARCH.md、ARCHITECTURE.md、ACCEPTANCE.md 及六个子迭代全部文档，以及现有源代码（backend/app、frontend/src）
>
> 总体评价：这是一份质量很高的迭代计划，架构清晰、领域建模严谨、验收标准明确。以下建议结合了现有代码库的深度分析，旨在提升可执行性和降低实施风险，不改变计划的整体方向和设计决策。

---

## 0. 现有代码库对照分析（优先级：高 — 实施前必读）

本节基于对 `src/backend/app/` 和 `src/frontend/src/` 的完整审计，详细列出迭代 191 计划与现有代码之间的差距和需要关注的具体技术点。

### 0.1 现有资产数据基础设施

`MarketInstrumentService`（`src/backend/app/services/market_instrument.py`，2696 行）已实现：

- 7 类资产类型定义：`MarketAssetType = Literal["stock", "futures", "bond", "fund", "option", "fx", "crypto"]`
- 每类资产的 `list_instruments` 和 `lookup` 方法（仓库优先 + 在线回退模式）
- 统一的 `MARKET_INSTRUMENT_HISTORY_CACHE` 表（通用缓存层，含 `asset_type/symbol/period/date` 及 OHLCV 字段）
- 内置回退标的列表（`_BUILTIN_INSTRUMENTS`）

**关键发现：**

1. **可直接复用，但需要适配层**：`MarketInstrumentService` 的 `lookup()` 方法已经为每类资产返回 `{asset_type, symbol, name, market, snapshot, history}` 结构。迭代 191 的 `AssetResearchPlugin.collect_raw_snapshot()` 可以直接封装这些方法，但需要增加 `RawObservation` 的来源溯源字段（`source_id/observed_at/published_at/available_at/license_tag`），当前 `lookup()` 返回的 snapshot 没有这些元数据。

2. **债券数据覆盖范围不足**：当前 `_lookup_bond_warehouse` 只查询 `BOND_ZH_HS_COV_SPOT`（可转债现货）和 `BOND_ZH_HS_COV_MIN`（可转债分钟线），完全覆盖不到迭代 191 要求的国债、政策性金融债和信用债。需要新增中债估值、收益率曲线和银行间债券的数据源。

3. **基金数据只有 ETF**：当前 `_lookup_fund_warehouse` 只支持 `ETF_REALTIME_QUOTE_EM` 和 `ETF_FUND_HIST_EM`。迭代 191 要求支持开放式基金（按 NAV 估值），当前代码完全没有开放式基金的净值、持仓、基准数据。

4. **外汇数据使用 BOC 参考汇率**：`_lookup_fx_warehouse` 使用 `CURRENCY_BOC_SAFE`（中国银行外汇牌价），这是参考汇率而非可成交报价。迭代 191 计划明确要求区分"参考汇率"和"可成交报价"，但当前代码层面没有这个区分。

5. **数字货币只有 CME 数据**：`_lookup_crypto_warehouse` 使用 `CRYPTO_JS_SPOT` 和 `CRYPTO_BITCOIN_CME`，缺少链上数据、多交易场所报价和永续合约数据。

6. **期权解析依赖硬编码**：`_resolve_option_symbol` 只处理 MO（中证 1000 期权）的别名解析，对其他期权品种（IO/HO/商品期权）缺乏通用解析逻辑。

### 0.2 现有股票信号系统

`stock_signal/` 模块（`src/backend/app/services/stock_signal/`，12 个文件）已实现：

- `types.py`：`SignalAction = Literal["BUY", "SELL", "WATCH"]`、`SignalFeatures`、`DataQualityAssessment`、`SignalDecision`
- `service.py`：`StockSignalService` 含 `create_prediction`、预测幂等（`prediction_key` = SHA-256）、`owner_scope` 隔离
- `decision_policy.py`：`SignalPolicy` 决策策略
- `features.py`：`calculate_features` 特征计算
- `quality.py`：`DataQualityGate` 质量门控
- `outcomes.py`：`evaluate_outcome` 结果评分
- `performance.py`：`build_performance_summary` 成绩单
- `scheduler.py`：定时调度
- `batch.py`：批量运行
- `calendar.py`：交易日历
- `universe.py`：股票池

数据库模型（`src/backend/app/models/stock_signal.py`）：

- `StockSignalRun`：`run_key`（唯一）、`owner_scope`、`source`、`universe_code`、`as_of_date`、`status`、计数
- `StockSignalPrediction`：`prediction_key`（唯一）、`signal_action`（`BUY/SELL/WATCH`）、`confidence_score`、概率、`eligibility_status`、`outcome_status`（`PENDING/PARTIAL/SCORED/UNSCORABLE`）

**关键发现：**

1. **动作语义需要完全替换**：现有 `BUY/SELL/WATCH` 三元组无法表达迭代 191 的 `market_view/normalized_direction/recommendation/trade_intent` 六元组。现有的 `StockSignalPrediction.signal_action` 列只有一个值，而迭代 191 需要同时保存 `candidate_decision_json` 和 `published_decision_json`。这不是简单的字段扩展，而是概念模型的根本变化。

2. **预测与运行的关系模型不同**：现有代码中 `StockSignalPrediction.run_id` 是直接外键，一行预测只属于一个 run。迭代 191 使用 `asset_signal_run_predictions` 关联表（支持 `CREATED/REUSED` 两种角色）。这意味着现有的外键关系和唯一约束需要重新设计。

3. **现有特征计算是股票专用的**：`calculate_features()` 返回 `SignalFeatures`（含 `return_1/5/20/60`、`ma5/20_gap`、`rsi14`、`atr14` 等），这些对债券、外汇、数字货币不适用。迭代 191 需要为每类资产实现独立的特征计算。

4. **结果评分缺少多 head 支持**：现有 `evaluate_outcome` 只返回单一的 `OutcomeEvaluation`，没有 `outcome_kind` 概念。迭代 191 要求每类资产返回多个独立 head（如期权需要 `option.underlying_direction`、`option.iv_direction`、`option.exact_contract_net_profit` 三个独立 head）。

5. **缺少模型注册表和晋级系统**：现有代码没有任何模型注册表、晋级状态或审批历史。迭代 191 的 `asset_model_registry` 和 `asset_model_status_events` 两张表及相关逻辑需要从零构建。

6. **现有的幂等逻辑需要扩展**：当前 `prediction_key` 的哈希输入只包含 `source/owner_scope/universe_code/symbol/as_of_date/feature_version/decision_policy_version`。迭代 191 的 `decision_input_hash` 需要加入 `canonical_identity/metadata_version/horizon_spec/position_context/source_snapshot_hash/cost_snapshot/head_spec_set_hash/capability_snapshot/compliance_policy_version` 等大量新字段，这会导致所有现有预测的哈希值变化。

### 0.3 现有股票分析系统

`stock_analysis/` 模块（`src/backend/app/services/stock_analysis/`，8 个文件）：

- `pipeline.py`：同步分析流水线
- `data_collector.py`：股票数据采集
- `analysis_engine.py`：分析引擎
- `report_builder.py`：研报构建
- `signal.py`：信号生成
- `exporter.py`：导出（Markdown/HTML/DOCX/PDF）
- `tasks.py`：任务管理

**关键发现：**

1. **流水线是同步的，不支持异步插件**：`pipeline.py` 是同步执行的，而迭代 191 的 `AssetResearchPlugin` 协议中 `collect_raw_snapshot` 和 `score_outcome` 都是 `async` 方法。需要将流水线改为异步架构。

2. **研报生成与决定耦合**：当前 `report_builder.py` 同时生成内容和决定，迭代 191 要求先独立生成 `ResearchDecision`（由策略/模型产生），再让 LLM 基于结构化决定生成研报文字。这需要拆分为两个独立步骤。

3. **缺少数据来源溯源**：当前 `data_collector.py` 不记录每个数据字段的来源、观测时间、发布时间和许可标签。迭代 191 要求每个字段都有 `RawObservation` 级别的溯源。

4. **导出和知识库保存已有基础**：`exporter.py` 和知识库保存逻辑可作为迭代 191 的 `exports.py` 和 `publications.py` 的起点。

### 0.4 现有前端代码

`StockAnalysisPage.vue`（`src/frontend/src/views/investment/StockAnalysisPage.vue`）：

- 使用 Element Plus UI 组件库
- 包含符号输入、市场选择、分析日期、模块选择、提交按钮
- 展示任务状态、进度、研报结果
- 支持导出和知识库保存

`stockAnalysis.ts` API 层（`src/frontend/src/api/stockAnalysis.ts`）：

- 定义了 `StockAnalysisTask`、`StockAnalysisResult`、`StockSignalAction` 等类型
- API 调用：`createTask`、`getTask`、`getResult`、`getLatest`、`exportReport`、`saveToKnowledgeBase`

**关键发现：**

1. **页面需要拆分为工作台壳 + 资产面板**：当前 `StockAnalysisPage.vue` 是一个单体组件（很可能超过 800 行），迭代 191 要求将其拆分为 `AssetAnalysisPage.vue`（壳）+ `{Bond,Fund,Futures,Option,Fx,Crypto}Panel.vue`（资产专属面板）。这个拆分工作本身就是一个不小的工程。

2. **路由兼容性**：需要新增 `/investment/ai-assets/:assetType` 路由，同时保留 `/investment/stock-analysis` 路由。现有路由注册在 `src/frontend/src/router/index.ts`，需要同步更新导航菜单。

3. **API 层需要新增 `assetResearch.ts`**：当前 `stockAnalysis.ts` 的接口与迭代 191 的 API 设计完全不同（任务创建参数、响应格式、信号字段）。需要新建 `src/frontend/src/api/assetResearch.ts` 并保持旧接口兼容。

4. **状态管理缺失**：当前 `StockAnalysisPage.vue` 使用组件内 `ref/reactive` 管理状态，没有独立的 Pinia store。迭代 191 涉及 6 类资产 + 搜索 + 身份确认 + 参数 + 结果 + 历史 + 成绩单，组件内状态管理将变得不可维护，需要抽取为 `useAssetAnalysis` composable 或 Pinia store。

5. **i18n 需要大量扩展**：当前 `src/frontend/src/i18n/locales/zh-CN.ts` 和 `en-US.ts` 中只有股票分析相关的翻译键。需要新增 6 类资产的专属翻译（估值术语、风险描述、建议文案等）。

### 0.5 现有数据库迁移

Alembic 迁移历史（`src/backend/alembic/versions/`）：

- 最新迁移：`20260801_stock_signal_predictions.py`（添加了 `stock_signal_predictions` 和 `stock_signal_runs` 表）
- 共有约 20 个迁移文件

**关键发现：**

1. **迁移文件命名不统一**：早期迁移使用数字编号（`0001_` 到 `0015_`），后期使用日期（`20260705_`、`20260801_`），迭代 191 计划中定为 `20260802_asset_research_foundation.py`。需要在迁移文件中明确 `depends_on` 指向最新迁移。

2. **新增 12 张表需要依赖 `stock_signal_predictions` 表**：因为股票兼容迁移需要双读，新的通用表需要与 `stock_signal_predictions` 和 `stock_signal_runs` 共存。迁移文件必须声明对 `20260801_stock_signal_predictions` 的依赖。

3. **`ON DELETE RESTRICT` 约束需要验证**：计划中大量使用 `ON DELETE RESTRICT`，但现有数据库可能已有不同的外键策略。需要在迁移前审计现有外键约束。

### 0.6 现有代码可直接复用的部分

以下现有代码可以在迭代 191 中直接复用或作为起点：

| 现有模块 | 复用方式 | 需要的改动 |
| --- | --- | --- |
| `MarketInstrumentService.lookup()` | 作为 `AssetResearchPlugin.collect_raw_snapshot()` 的底层数据源 | 封装为返回 `RawObservation` 格式，增加溯源元数据 |
| `MARKET_INSTRUMENT_HISTORY_CACHE` 表 | 作为 `asset_source_snapshots` 的补充缓存层 | 增加 `source_id/license_tag/available_at` 列 |
| `StockSignalService.create_prediction()` | 参考其幂等逻辑和哈希计算模式 | 扩展 `decision_input_hash` 的输入字段 |
| `StockSignalService` 的 `owner_scope` 隔离 | 直接复用其用户隔离模式 | 扩展到 `asset_analysis_tasks` 和 `asset_signal_predictions` |
| `DataQualityGate.assess()` | 参考其质量门控模式 | 扩展为资产专属的 `QualityAssessment` |
| `evaluate_outcome()` | 参考其结果评分模式 | 重构为多 `outcome_kind` 架构 |
| `build_performance_summary()` | 参考其成绩单计算模式 | 扩展为多 head 分 cohort 统计 |
| `exporter.py` | 直接复用导出格式和逻辑 | 增加资产专属报告章节 |
| 知识库保存逻辑 | 直接复用 | 增加 `asset_report_publications` 审计 |
| `StockAnalysisPage.vue` | 拆分为工作台壳 | 提取共用部分，新增资产面板 |
| `stockAnalysis.ts` API 层 | 作为 `assetResearch.ts` 的参考 | 新增接口，保留旧接口兼容 |

---

## 1. 项目风险与依赖管理（优先级：高）

### 1.1 缺少独立的风险管理章节

当前 RESEARCH.md 第 7 节"反方证据和主要风险"仅有 6 条概括性风险，不足以支撑一个 12 周、涉及 6 类资产的复杂工程。

**建议：**

- 在 README.md 中新增"风险管理"章节，至少覆盖：
  - **数据源依赖风险**：AKShare 等第三方数据源的接口稳定性、许可证变更、数据质量下降。明确每个数据源的降级策略（缓存回退、备用源切换、人工介入）。
  - **外部接口变更风险**：交易所 API、中债估值、基金净值披露规则变更时的影响范围和应对时间。
  - **人员风险**：公共底座 + 6 个资产插件需要领域知识（固收、衍生品、外汇、数字货币），关键人员不可用时的备份方案。
  - **LLM 依赖风险**：LLM 服务不可用或质量下降时的降级策略（结构化模板回退）。
  - **时间风险**：12 周时间线紧张，明确哪些功能可以降级为"研究观察"而不影响其他模块上线。
  - **数据覆盖风险**（基于代码审查）：当前 `MarketInstrumentService` 的债券数据只覆盖可转债，基金只覆盖 ETF，外汇只使用 BOC 参考汇率。在实施前必须确认每类资产的完整数据源可获取。

### 1.2 缺少明确的资源与人力假设

整个计划没有提及需要多少开发人员、具备什么技能。

**建议：**

- 在 README.md 中增加"资源需求"小节，至少包括：
  - 后端开发人员数量及技能要求（Python/FastAPI/SQLAlchemy/量化金融）
  - 前端开发人员数量
  - 是否需要量化研究员支持（特征工程、模型校准）：基于代码审查，现有的 `calculate_features` 和 `SignalPolicy` 逻辑需要为每类资产重新实现，量化研究员的工作量不可低估。
  - 是否需要 DevOps 支持（数据库迁移、对象存储、调度系统）

---

## 2. 时间线与阶段划分（优先级：高）

### 2.1 P0 公共底座 2 周可能不足

P0 包含：通用表（12 张）、插件协议、API（20+ 端点）、工作台壳、来源注册表、合规门控、幂等/预测/run 关联、持仓上下文、调度器基础。从架构设计来看，这是一个非常厚重的公共层。

**基于代码审查的补充分析：**

P0 还需要额外处理以下现有代码的改造：

- 将 `StockAnalysisPage.vue` 拆分为工作台壳 + 资产面板（预估 3-5 天）
- 新建 `src/frontend/src/api/assetResearch.ts`（预估 2-3 天）
- 扩展 i18n 翻译文件（预估 1-2 天）
- 将 `pipeline.py` 从同步改为异步架构（预估 2-3 天）
- 建立 `asset_research` 目录结构并注册到 FastAPI router（预估 1 天）

这些额外的改造工作使 P0 的 2 周估算更加紧张。

**建议：**

- 考虑将 P0 拆分为 P0a（领域模型 + 数据库 + 插件协议）和 P0b（API + 前端壳 + 调度基础），各 1.5-2 周。
- 或者在 P0 中明确哪些是"必须完成"、哪些可以"P0 完成基础 + P1 补全"。
- 将前端 `StockAnalysisPage.vue` 的拆分工作纳入 P0 范围，而不是推迟到子迭代。

### 2.2 子迭代并行度假设过于乐观

计划中 191A/191B 可并行、191C/191E 可并行。但 P0 完成后，公共底座必然有 bug 和调整，同时开发 2 个资产插件会导致公共层修改冲突。

**基于代码审查的补充分析：**

191A（债券）和 191B（基金）实际上有数据依赖关系：

- 债券需要新增中债估值数据源（当前代码完全没有）
- 基金需要新增开放式基金 NAV 数据源（当前代码完全没有）
- 两者的数据采集器开发都需要修改 `MarketInstrumentService`，会产生代码冲突

**建议：**

- 在 P1 阶段的前半周设置"公共底座稳定期"，只允许公共层 bug 修复，不新增接口。
- 明确公共层接口冻结的时间点，以及子迭代开发者在冻结前可以提出哪些变更请求。
- 191A 和 191B 的数据采集器开发应串行或由同一人负责，避免对 `MarketInstrumentService` 的冲突修改。

### 2.3 P5 影子验证"持续运行"缺少终止条件

P5 描述为"第 11-12 周及持续运行"，但没有明确 12 周后的持续运行由谁负责、持续多久。

**建议：**

- 明确影子验证的运营归属（哪个团队/角色负责监控和晋级评估）。
- 设定影子验证的初始观察期（如 90 天），到期后评审是否转为正式运营或关闭。

---

## 3. 子迭代文档质量不均衡（优先级：中）

### 3.1 文档深度差异显著

对比各子迭代的文档体量：

| 子迭代 | 总文档大小 | 评估 |
| --- | --- | --- |
| 01-AI债券 | ~60 KB | 非常详细 |
| 02-AI基金 | ~65 KB | 非常详细 |
| 03-AI期货 | ~37 KB | 中等 |
| 04-AI期权 | ~47 KB | 中等 |
| 05-AI外汇 | ~37 KB | 中等 |
| 06-AI数字货币 | ~45 KB | 中等 |

债券和基金的文档量是期货/外汇的近 2 倍。这可能导致后四个子迭代在实施时发现未覆盖的边界情况。

**基于代码审查的补充分析：**

当前代码库中，债券和基金的数据覆盖最薄弱（债券仅可转债、基金仅 ETF），但文档却最详细。期货和外汇的数据覆盖相对较好（`FUTURES_DAILY_MARKET` 和 `FOREX_SPOT_EM` 表有较完整数据），但文档较薄。这种"数据弱但文档厚、数据强但文档薄"的不对称性意味着：

- 债券和基金的"厚文档"可能包含大量需要在实施中验证的数据可用性假设
- 期货和外汇的"薄文档"可能遗漏了现有数据已经覆盖的边界场景

**建议：**

- 在进入实施前，对期货、外汇、期权和数字货币的 REQUIREMENTS.md 和 DESIGN.md 做一次对等审查，确保覆盖度与债券/基金一致。
- 特别关注期货的"连续合约映射"（当前代码中 `_lookup_futures_warehouse` 已实现基础的合约查询，但缺少 point-in-time 映射逻辑）和外汇的"多场所报价"（当前只有 BOC 参考汇率，缺少可成交报价源）等复杂场景是否有足够的边界用例。

### 3.2 期货 PLAN.md 缺少明确的实施顺序依赖

期货的实施计划中，任务 1-7 是平铺的，但合约主数据、日历映射、行情特征之间存在强依赖。

**建议：**

- 为每个子迭代的 PLAN.md 增加任务依赖图（可用 Mermaid 或简单的依赖表），明确哪些任务可以并行、哪些必须串行。

---

## 4. 非功能性需求缺失（优先级：中）

### 4.1 缺少性能/SLA 目标

整个计划没有定义任何性能指标。

**基于代码审查的补充分析：**

当前 `MarketInstrumentService.lookup()` 的仓库查询是异步的，但在线回退使用 `asyncio.to_thread()` 包装同步 AKShare 调用，这意味着在线查询的延迟取决于 AKShare 的响应时间（通常 2-10 秒）。如果迭代 191 的 `collect_raw_snapshot` 需要聚合多个数据源（如债券需要中债曲线 + 行情 + 条款），延迟会进一步增加。

**建议：**

- 在 ARCHITECTURE.md 或 README.md 中增加 SLA 目标，至少包括：
  - 单资产分析任务的目标延迟（P50/P95/P99）
  - 研报生成的超时时间
  - 每日影子调度的最大执行窗口
  - 前端页面首次加载和数据刷新的目标时间
  - API 并发处理能力

### 4.2 缺少数据保留与清理策略

虽然架构中提到了 `RawAssetSnapshot` 和对象存储，但没有明确数据保留策略。

**建议：**

- 在 ARCHITECTURE.md 第 4 节增加"数据生命周期"小节：
  - 原始快照的保留期限
  - 预测记录的保留期限
  - 结果数据的保留期限
  - 对象存储的清理策略
  - 用户删除数据的处理流程

### 4.3 缺少可观测性设计细节

架构中提到了 trace ID 和日志，但缺少监控和告警设计。

**基于代码审查的补充分析：**

当前代码库已有 `telemetry.py`（`src/backend/app/telemetry.py`）和 `ai_observability.py` API 端点，可以作为迭代 191 可观测性的基础。

**建议：**

- 增加"可观测性"小节，明确：
  - 关键指标（任务成功率、平均延迟、数据源可用性、调度执行率）
  - 告警规则（数据源连续失败 N 次、任务队列积压超过阈值、结果评分异常）
  - 仪表盘需求（按资产类型、按状态、按时间维度的运行概览）
  - 复用现有 `telemetry.py` 和 `ai_observability.py` 的基础设施

---

## 5. 技术细节补充（优先级：中）

### 5.1 LLM 成本估算缺失

计划大量使用 LLM 生成研报，但没有成本估算。

**建议：**

- 在 RESEARCH.md 或 ARCHITECTURE.md 中增加 LLM 成本估算：
  - 单次研报生成的预估 token 消耗
  - 每日影子调度的研报生成量
  - 月度/年度 LLM 成本预估
  - 成本控制策略（缓存、模板回退、模型选择）

### 5.2 数据库迁移策略不够详细

ARCHITECTURE.md 提到了 Alembic 迁移文件，但没有说明迁移策略。

**基于代码审查的补充分析：**

当前数据库已有 `stock_signal_predictions` 和 `stock_signal_runs` 表（最新迁移 `20260801_stock_signal_predictions.py`）。迭代 191 的 12 张新表需要与这些现有表共存，且股票兼容迁移需要双读。具体的迁移风险包括：

- `StockSignalPrediction.run_id` 是直接外键，而迭代 191 使用 `asset_signal_run_predictions` 关联表。迁移时不能简单删除旧列。
- 现有 `prediction_key` 的哈希输入与迭代 191 的 `decision_input_hash` 不同，新旧预测的哈希值无法互通。
- 现有 `signal_action` 是 `BUY/SELL/WATCH`，而迭代 191 使用 `published_decision_json`（JSON 列），迁移时旧数据需要映射。

**建议：**

- 增加迁移策略说明：
  - 是否支持零停机迁移
  - 大表（如 `asset_source_snapshots`）的迁移方案
  - 回滚策略
  - 股票兼容迁移的验证标准（"连续两个版本零差异"的可测量定义）
  - 明确 `stock_signal_predictions` 到 `asset_signal_predictions` 的数据映射规则
  - 迁移脚本中需要包含旧数据验证步骤

### 5.3 缺少前端状态管理策略

前端文档只提到了路由和组件，没有说明状态管理方案。

**基于代码审查的补充分析：**

当前 `StockAnalysisPage.vue` 使用组件内状态管理（`ref/reactive`），但迭代 191 涉及：

- 资产类型切换（6 种资产 + 股票兼容）
- 搜索 → 身份确认 → 参数设置 → 分析 → 结果展示的 5 步流程
- 历史预测列表和成绩单
- 跨资产的共享状态（用户偏好、数据源状态）

**建议：**

- 在 ARCHITECTURE.md 第 7 节补充：
  - 状态管理方案（Pinia store 结构：`useAssetAnalysisStore`、`useAssetSearchStore`、`useSignalHistoryStore`）
  - 资产分析任务的状态机（与后端 `TaskStatus` 的映射：`QUEUED → RUNNING → SUCCEEDED/FAILED/CANCELLED`）
  - 轮询策略（任务进度更新方式：建议使用 `usePolling` composable，间隔 2-5 秒）
  - 错误处理和重试逻辑
  - 资产类型切换时的状态清理策略（防止跨资产残留）

### 5.4 资产专属 `ResearchDetails` 字段定义不完整

ARCHITECTURE.md 中 `BondResearchDetails`、`FundResearchDetails`、`FuturesResearchDetails`、`FxResearchDetails`、`CryptoResearchDetails` 仅有 `kind` 字段，没有具体内容。

**建议：**

- 在公共架构中至少给出每类 `ResearchDetails` 的字段骨架（即使详细字段由子迭代定义），确保公共层在做 discriminated union 校验时有基本的类型约束。

### 5.5 现有代码的渐进式迁移路径不明确（新增）

ARCHITECTURE.md 第 4.5 节提到"股票兼容迁移"的 5 步，但缺少具体的时间节点和验收标准。

**基于代码审查的具体建议：**

1. **第一阶段（P0 期间）**：创建 `StockResearchCompatibilityAdapter`，封装现有 `StockSignalService` 和 `stock_analysis` 流水线，使其实现 `AssetResearchPlugin` 协议。验证方法是：对同一股票、同一日期，新旧接口返回的 `signal_action` 和研报内容一致。

2. **第二阶段（P1-P2 期间）**：所有新预测双写（同时写入 `stock_signal_predictions` 和 `asset_signal_predictions`），通过 `decision_input_hash` vs `prediction_key` 的哈希对账验证一致性。

3. **第三阶段（P5 期间）**：连续两个版本（至少 4 周）的哈希对账零差异后，提交独立的数据迁移方案评审。

4. **明确迁移完成后的清理计划**：迁移完成后，`stock_signal_predictions` 和 `stock_signal_runs` 表是保留为只读历史表还是逐步废弃。

---

## 6. 验收与质量保障（优先级：中）

### 6.1 缺少集成测试策略

ACCEPTANCE.md 中的自动化测试命令只覆盖单元测试和 linter，没有集成测试。

**基于代码审查的补充分析：**

当前代码库已有大量测试（`src/backend/tests/` 下有 150+ 测试文件），包括 `test_stock_signal_service.py`、`test_stock_signal_outcomes.py`、`test_stock_signal_calendar.py` 等。迭代 191 的测试需要参照这些测试的模式。

**建议：**

- 增加集成测试层：
  - 数据库迁移 + 外键约束的集成测试（参考 `test_db.py` 的模式）
  - API 端到端测试（使用 TestClient + 测试数据库，参考 `test_stock_analysis_*.py` 的模式）
  - 插件协议的一致性测试（验证六个插件都实现了完整协议，可以通过参数化测试实现）
  - 幂等性和并发测试（参考 `test_stock_signal_service.py` 中的幂等测试模式）
  - 股票兼容性回归测试（确保现有股票分析功能不受影响）

### 6.2 在线冒烟验证依赖外部数据稳定性

ACCEPTANCE.md 第 12 节要求每类资产完成在线冒烟，但外部数据（AKShare、交易所 API）可能不稳定。

**建议：**

- 为在线冒烟增加"数据源不可用时的替代方案"：
  - 使用预录制的 HTTP 响应（VCR/fixture 模式）
  - 明确哪些冒烟项可以在数据源不可用时跳过
  - 设定在线冒烟的时间窗口和重试策略

### 6.3 缺少回归测试保障

股票兼容迁移（ARCHITECTURE.md 第 4.5 节）提到保留旧接口，但没有明确的回归测试套件。

**基于代码审查的补充：**

当前 `test_stock_analysis_*.py` 和 `test_stock_signal_*.py` 系列测试需要在每次迁移后保持通过。建议在 ACCEPTANCE.md 中增加：

- 现有股票分析功能的回归测试清单（具体到每个测试文件）
- `/stock-analysis` 路由的兼容性测试（请求/响应格式不变）
- 旧表 `stock_signal_predictions` 和 `stock_signal_runs` 的读写验证
- 在 CI 中同时运行新旧两套测试，直到迁移完成

---

## 7. 沟通与治理（优先级：低）

### 7.1 缺少评审和审批流程

计划中提到了合规审批（模型晋级），但没有项目级的评审节点。

**建议：**

- 在 README.md 中增加"评审节点"：
  - 每个阶段结束时的评审会议
  - P0 公共底座完成后的设计回顾
  - 每个子迭代 T1 验收后的 go/no-go 决策
  - 文档的评审人清单

### 7.2 缺少变更管理流程

当实施过程中发现设计需要调整时，如何同步更新总体架构和子迭代文档？

**建议：**

- 增加"变更管理"小节：
  - 文档变更的审批流程
  - 公共层变更对子迭代的影响评估机制
  - 版本化文档的更新规则

---

## 8. 总结

本迭代计划的核心设计（公共底座 + 资产插件、point-in-time 数据、预测闭环、模型晋级）是扎实的。基于对现有代码库的深度审查，以上建议主要集中在：

1. **代码库衔接**（新增）：明确了现有 `MarketInstrumentService`、`stock_signal`、`stock_analysis`、`StockAnalysisPage.vue` 与迭代 191 的差距和复用路径
2. **可执行性**：补充风险、资源、时间线的现实考量
3. **完整性**：补全非功能性需求、监控、数据生命周期
4. **一致性**：拉齐六个子迭代的文档深度
5. **可运维性**：增加 SLA、成本估算、迁移策略

建议在进入实施前，优先处理标记为"优先级：高"的改进项（代码库衔接分析、风险管理、资源假设、P0 时间线重新评估），其余可在各阶段推进时逐步完善。
