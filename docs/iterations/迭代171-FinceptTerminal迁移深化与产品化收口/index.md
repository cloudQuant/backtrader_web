# 迭代 171 - FinceptTerminal 迁移深化与产品化收口

> **文档状态**: 进行中（已完成 T1 / T3 / T4 / T5 / T6 / T8 / T9 / T11 / T12，本轮剩余 T2 / T7 / T10 的进一步收口）
> **创建日期**: 2026-05-26
> **前置基线**: 迭代 170 已完成适合 Web/FastAPI 架构的核心 MVP 与关键验收件，但未完成完整产品化迁移
> **核心目标**: 将迭代 170 中仍停留在 MVP / placeholder / in-memory / hard-coded 层的 FinceptTerminal 能力继续迁移为可持续演进的 Web 产品能力，优先闭合 `data_connectors / portfolio_ledger / equity_research / news_intelligence / options_chain / scanners / ws_gateway migration / quant_tools` 的产品化缺口；`broker` 统一能力继续沉淀在 `bt_api_py` / `bt_api_xx` 生态中，由 `backtrader_web` 以统一消费方身份接入，而不是在本仓内继续扩 broker 产品层。

---

## 0. 审计结论

结论不是“FinceptTerminal 应迁能力已经全部完整迁移并且很好实现”，而是：

- 迭代 170 已经完成 **适合 Web/FastAPI 架构的核心能力 MVP 迁移**。
- 这些能力已经具备了 **最小后端闭环、最小前端入口、最小测试与文档**，因此可以视为一轮成功的 clean-room MVP 收口。
- 但多个模块仍明显停留在 **演示级 / 最小可验收级**，距离“完整迁移 + 产品化实现 + 可持续演进”还有差距。
- 因此，迭代 171 不应再重复搭底座，而应聚焦 **把 170 的 MVP 深化为真实产品能力**。
- **Broker 边界需要收口**：`backtrader_web` 不继续承接 broker adapter / registry / native integration 的产品化，相关能力转由 `bt_api_py` 及按交易所/券商拆分的 `bt_api_xx` 包演进。

同时要明确：**不是 FinceptTerminal 的所有内容都应该迁移**。以下内容继续排除在迁移范围外：

- Qt 桌面端 UI / 打包 / C++ 构建链
- Fincept 全量 250+ Python scripts 的逐文件搬运
- 全量 16 个券商原生适配一次性搬完
- 完整 AI Quant Lab（Qlib / RDAgent / RL / HFT）

---

## 1. 170 已完成什么，171 为什么还需要继续

### 1.1 已完成的 MVP 迁移

迭代 170 已经完成：

- Data Governance 中性模型、provider / endpoint / job 基础 API
- DataTopicHub + `ws_gateway` + `/ws/data-topics`
- Instrument / RiskFreeRate 共享底座
- 独立 `bt_api_py` 的 broker contract / mock / gateway bridge
- Broker profile 管理与 enable-write 确认链路
- Portfolio Ledger MVP
- Equity Research / News Intelligence / Options Chain / Scanner / Quant Tools MVP
- 前端 API wrapper 与最小页面入口
- 关键 8.4 验收件、向后兼容守门、独立 `bt_api_py` 的 MockBrokerAdapter 100% coverage gate

### 1.2 为什么还不能说“完全迁移完成”

以下证据说明当前仍属于“核心能力已落地，但很多模块还未产品化”：

| 能力 | 当前状态 | 直接证据 | 171 处理方向 |
|---|---|---|---|
| Data Connector Registry | **部分迁移** | `app/services/data_connectors/executor.py` 在未注册 callable 时直接返回 mock rows；`app/api/data_governance.py` 只有 bootstrap/list/preview/create_job 最小接口 | 做真实 provider 执行、任务状态机、参数/质量规则治理、非 mock preview |
| Broker API / `bt_api_py` | **跨仓迁移项** | 独立仓当前只有 `base.py / types.py / errors.py / mock.py / gateway_bridge.py`，缺更完整的生态拆分与兼容层 | 在 `bt_api_py` 中继续统一 broker contract / `btapibroker` / compatibility layer，并将交易所/券商下沉到独立 `bt_api_xx` 包；`backtrader_web` 只消费稳定接口 |
| Broker Profiles | **存量 MVP（171 不扩张）** | `app/services/broker_profiles.py` 目前实际构造的是 `GatewayBridgeAdapter`，不是完整 registry 驱动的多 broker 体系 | 不在 `backtrader_web` 中继续扩 broker 产品层；现有 web 侧只保留兼容消费边界或后续收敛 |
| Portfolio Ledger | **部分迁移** | `app/services/portfolio_ledger.py` 纯内存字典实现，无 SQLAlchemy 模型；无 dividend / benchmark / tags / notes / richer cashflow typing | 做持久化账本、分红/现金流/基准/分析接入 |
| Equity Research | **部分迁移** | `app/services/equity_research.py` 只有 `search/quote/history/technicals`，且 quote/history 为硬编码示例数据；`app/api/equity_research.py` 无 `info/financials/peers` | 做真实数据源接入与详情接口补齐 |
| News Intelligence | **部分迁移** | `app/services/news_intelligence.py` 只维护内存 `_sources/_articles`，规则分类简单，无 RSS 拉取调度 / cluster 模型 / AI 摘要持久化 | 做真实 source/article/analysis/cluster 模型和抓取链路 |
| Options Chain | **部分迁移** | `app/services/options_chain.py` 用 spot 附近 3 个 strike 合成链条，Greeks 为简化公式，不是真实 provider 输出与缓存节流 | 接入真实 provider、IV/Greeks cache、更多 strike，并优先通过 Data Connector Registry 或外部统一市场数据能力读取 |
| Scanner DSL | **部分迁移** | `app/services/scanner_service.py` 只支持 `price/volume/change_pct` 的同步 AST 表达式 | 扩到 indicator/factor/news_sentiment/portfolio_exposure + async task engine |
| Quant Tool Registry | **部分迁移** | `app/services/quant_tools_runtime.py` 已具备协议能力，但部分 handler 仍是 placeholder，如 `risk.var_cvar` 描述即 lightweight placeholder、`endpoint_preview` 返回 mock preview | 拆模块、补真实 handler、接 AI Chat 更强闭环 |
| WebSocket migration | **部分迁移** | 170 已抽取 `ws_gateway`，但 170 计划中的 `docs/architecture/WS_GATEWAY_MIGRATION.md` 尚不存在，现有多处 WS 代码也未迁移 | 在 171 明确迁移清单与优先级，并开始逐项迁移 |
| Fincept gap analysis 文档 | **未完成** | 170 计划要求的 `docs/architecture/FINCEPT_TERMINAL_GAP_ANALYSIS.md` 尚不存在 | 171 第一项补齐正式 gap analysis |

---

## 2. 171 的范围定义

### 2.1 171 的目标

171 不是再“证明这些模块存在”，而是把 170 的 MVP 深化成：

- **真实数据驱动**，而不是示例 / seed / hard-coded 为主
- **持久化可恢复**，而不是纯内存态
- **通过 registry / adapter / job state machine 组合**，而不是单文件内聚合实现
- **前端可操作**，而不是 demo button / seed button / 单表格展示
- **验证闭环完整**，包含回归、性能、降级路径、权限与审计
- **broker 能力外置**，`backtrader_web` 不再长出自己的 broker 平台，而是消费 `bt_api_py` / `bt_api_xx` 的统一能力

### 2.2 171 不做什么

171 仍然不做：

- Qt 桌面 UI 复刻
- Fincept 脚本逐文件复制
- 一次性接全 16 个券商原生适配
- 不在 `backtrader_web` 中继续新增 broker registry / adapter / native/paper 实装
- MCP Server 对外暴露
- 完整 AI Quant Lab / 训练编排 / RL / HFT

这些内容继续留在后续迭代。

### 2.3 Broker 边界约束

- `bt_api_py` 继续作为统一 broker contract 与 `btapibroker` 的宿主。
- 一个交易所 / 券商对应一个独立 `bt_api_xx` 包，避免继续把接入实现堆进 `backtrader_web`。
- 新 broker 能力优先在 `bt_api_xx -> bt_api_py -> backtrader/btapibroker` 链路落地，不在 `backtrader_web` 内部复刻一套 broker 平台。
- `backtrader_web` 只保留统一消费、展示、调度、审计与边界文档，不继续承担 broker adapter 的主实现职责。
- 详细演进路线见：`docs/plans/2026-05-26-bt-api-ecosystem-design.md`。
- 实施计划见：`docs/plans/2026-05-26-bt-api-ecosystem-implementation-plan.md`。
- 首个扩展包规范见：`docs/plans/2026-05-26-first-bt-api-xx-package-spec.md`。

---

## 3. 171 任务分解

### 3.0 当前收口状态（2026-05-27）

- **已完成**: T1、T3、T4、T5、T6、T8、T9、T11、T12
- **部分完成**: T2（迁移文档已补，遗留 WS 路由迁移尚未收口）、T7（source/article/analysis 持久化、canonicalize/去重/cluster/topic 扩展已落地，RSS 拉取与前端过滤/cluster 展开尚未收口）、T10（关键 handler 已产品化，模块进一步拆分待继续）
- **未完成**: 无完全未启动项

### 171A：底座补全与缺口文档化（P0）

- [x] **T1**: 补 `docs/architecture/FINCEPT_TERMINAL_GAP_ANALYSIS.md`
  - 输出“已迁移 / 部分迁移 / 明确不迁移”三类清单
  - 明确每项对应的当前代码位置、缺口与后续承接迭代

- [ ] **T2**: 补 `docs/architecture/WS_GATEWAY_MIGRATION.md`
  - 盘点当前未迁移的 WebSocket 路由
  - 给出优先级顺序与迁移策略
  - 171 至少迁移 2-3 个高价值 WS 入口到 `ws_gateway`
  - 当前状态：迁移文档已补，但 legacy WS 路由迁移仍待继续

- [x] **T3**: Data Connector Registry 产品化
  - 为 provider / endpoint / endpoint params / quality rule 补管理闭环
  - 执行器从 mock preview 升级到真实 callable / HTTP / AkShare-backed 路径
  - job 增加 queued / running / completed / failed / retryable 生命周期
  - 预览与异步入库不再依赖 fallback mock rows

- [x] **T4**: `bt_api_py / bt_api_xx` broker 生态协同（跨仓前置，不在本仓内直接实现 broker adapter）
  - `bt_api_py` 继续维护统一 broker contract、`btapibroker` 与兼容层
  - 各交易所 / 券商拆分为独立 `bt_api_xx` 包，而不是继续塞进 `backtrader_web`
  - 新包必须兼容现有 `bt_api_py` 模式与 backtrader 集成路径
  - `backtrader_web` 仅在接口消费点、配置映射点、文档边界上做最小配合

### 171B：组合与市场情报模块产品化（P0/P1）

- [x] **T5**: Portfolio Ledger 持久化与分析接入
  - 新增真实 SQLAlchemy 模型，不再只用内存字典
  - 补 `dividend / cash_deposit / cash_withdrawal / fee / benchmark_symbol / tags / notes`
  - 接入迭代 168 的 `risk_analytics / perf_attribution`
  - 维持 `portfolio-ledger` 路由不影响旧 `portfolio_api.py`
  - 当前状态：持久化模型、导入幂等、快照回填、mark-to-last-trade NAV 以及账本原生 `var-cvar / position-sizing / benchmark-metrics / brinson / fama-french` 适配已落地

- [x] **T6**: Equity Research 完整接口
  - 补 `info / financials / peers`
  - 数据读取走 Data Connector Registry，不继续硬编码示例行情
  - 前端增加详情面板 / 多 tab 展示，而不是仅搜索表格

- [ ] **T7**: News Intelligence 产品化
  - 新增 source / article / analysis / cluster 持久化模型
  - RSS 拉取、URL canonicalize、去重、cluster、AI 摘要持久化
  - topic 扩到 `news:general / news:symbol / news:category / news:cluster`
  - 前端增加过滤、cluster 展开、摘要展示，而不是示例 seed 按钮
  - 当前状态：source / article / analysis 持久化、canonicalize 去重、cluster_id 与摘要持久化、topic 扩展已落地；RSS 拉取与前端过滤/cluster 展开待继续

- [x] **T8**: Options Chain 产品化
  - 接入真实 provider priority：Data Connector Registry / 外部统一市场数据能力 → AkShare/CBOE → mock
  - Greeks / IV cache 与节流
  - batch strike 扩展，不再固定 3 档 strike
  - 前端增加 provider/source 选择、expiry 切换、更多指标展示

### 171C：扫描器、工具化与前端收口（P1）

- [x] **T9**: Scanner DSL v2
  - 支持 `indicator / factor / news_sentiment / portfolio_exposure / lookback_days / timeframe`
  - 改为异步 task 模型，保留 `/tasks/{task_id}` 查询链路
  - 结果支持进入候选策略工作区

- [ ] **T10**: Quant Tool Registry 产品化
  - 将 `quant_tools_runtime.py` 拆为 `registry / schema / audit / confirmation`
  - 补齐 placeholder handler 的真实服务接入
  - AI Chat 至少完成 5+ 工具只读闭环，并保留 destructive guard
  - 当前状态：`risk.var_cvar` 与 `data_governance.endpoint_preview` 已接入真实逻辑，模块化进一步拆分待继续

- [x] **T11**: 前端去 demo 化
  - `PortfolioLedgerPage / EquityResearchPage / NewsIntelligencePage / OptionsChainPage / ScannerPage / QuantToolsPage` 从示例按钮升级为真实可操作流程
  - 补更完整的 Vitest 页面交互测试

- [x] **T12**: 验证与回归
  - 后端：Ruff / targeted mypy / pytest / perf slices
  - 前端：API wrapper tests / view tests / typecheck
  - 向后兼容：保留 `tests/test_backward_compat_iter170.py` 并新增 171 相关守门

---

## 4. 171 验收标准

### 4.1 功能验收

- Data Governance 不再依赖 mock preview 才能演示 provider 能力
- `backtrader_web` 不新增 broker adapter / registry / native/paper 实装，broker 能力继续由 `bt_api_py` / `bt_api_xx` 生态提供
- `bt_api_py` 继续承担统一 broker contract 与 `btapibroker`，新增交易所/券商扩展遵循 `bt_api_xx` 独立包模式并兼容现有接入方式
- Portfolio Ledger 数据可持久化、支持 dividend 与 benchmark
- Equity Research 支持 `search / quote / info / history / financials / technicals / peers`
- News Intelligence 支持真实 source / ingest / cluster / summary / filter
- Options Chain 支持真实 provider 返回链条，非固定 3 strike demo
- Scanner DSL 支持多维条件，不只 `price/volume/change_pct`
- Quant Tools 的关键 handler 不再是 placeholder/mock
- 前端主要页面不再依赖“创建示例”“载入示例新闻”“获取示例期权链”这类 demo 入口

### 4.2 技术验收

- 不破坏 170 的向后兼容基线
- 不在 `backtrader_web` 内新增与 `bt_api_py` 职责重复的 broker 平台代码
- 新增持久化模型都有迁移 / schema 兜底
- 新增接口都具备测试与类型约束
- 需要外部 provider 的路径都有 degraded fallback
- 高风险能力继续要求显式确认、审计与限频

---

## 5. 与迭代 170 的关系

170 的定位应调整为：

- **已完成核心 MVP 迁移与关键验收闭环**
- **未承诺 FinceptTerminal 适配能力已全部产品化完成**

171 的定位则是：

- **把 170 中尚未完成产品化的 FinceptTerminal 能力继续迁移并收口**
- **其中 broker 相关深化迁移转由 `bt_api_py / bt_api_xx` 生态承接，`backtrader_web` 只保留统一消费边界**

因此，171 不是新方向，而是 170 的自然延续与深化。

---

## 6. 后续建议

若 171 完成后仍有余量，再进入：

- **迭代 172**：`bt_api_xx` 首批 14 个券商扩展包落地，优先完成 `Tradier / Saxo / Zerodha / Upstox / Angel One / Fyers / Dhan / Shoonya / AliceBlue / 5paisa / IIFL / Kotak / Motilal / Groww` 的独立包规划与分批实现，主实施仓为独立 `bt_api` 生态，`backtrader_web` 继续保持 consumer-only 边界。
- **迭代 173**：`MetaTrader4 / MetaApi` 等桥接型 broker、`Quant Tool Registry` MCP server 化、AI Quant Lab 深化，以及更多全球市场扩展 / 更复杂终端工作台。

但在 171 完成前，不建议继续扩散范围。
