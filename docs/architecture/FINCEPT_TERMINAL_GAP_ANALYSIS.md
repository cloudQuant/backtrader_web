# FinceptTerminal Gap Analysis

本文档用于回答一个更精确的问题：

- **哪些 FinceptTerminal 能力已经在 backtrader_web 中完成 Web 化迁移？**
- **哪些只是 MVP，尚未产品化？**
- **哪些明确不属于当前项目应迁范围？**

本分析以当前项目实际代码、测试、迭代 170/171 文档为准，而不是以上游项目是否“有该功能”为准。

---

## 1. 判断口径

### 1.1 已迁移

满足以下条件中的大多数：

- 后端服务和 API 已存在
- 前端至少有可用入口
- 具备基本测试与文档
- 不是纯 placeholder / demo-only

### 1.2 部分迁移

满足“最小闭环”，但仍存在以下任一问题：

- 以 in-memory / hard-coded / seed data 为主
- 缺关键模型或持久化
- 缺 provider / adapter / registry 产品化结构
- 仅覆盖 happy path / demo path
- 前端仍以示例按钮或单表格展示为主

### 1.3 明确不迁移

- Qt 桌面端 UI/打包/C++ 运行时
- Fincept 全量脚本逐文件复制
- 全量 native broker 一次性铺开
- 在 `backtrader_web` 内继续扩 broker registry / adapter / native integration 平台
- 完整 AI Quant Lab / 训练与 RL/HFT 工作流

---

## 2. 能力清单

| 能力 | 当前结论 | 代码依据 | 说明 |
|---|---|---|---|
| Data Connector Registry / Data Governance | 部分迁移 | `app/models/data_governance.py`、`app/services/data_connectors/*`、`app/api/data_governance.py` | 模型已在，但执行器与任务仍偏 MVP，preview 仍有 mock fallback |
| DataTopicHub | 已迁移（MVP） | `app/services/data_topic_hub.py`、`app/api/data_topics.py`、`app/services/ws_gateway/*` | Topic/TTL/refresh/WS 已有，但现有旧 WS 路由尚未全面迁移 |
| WebSocket Gateway | 部分迁移 | `app/services/ws_gateway/*`、`app/api/data_topics.py` | 新网关已可用，但历史 WS 入口尚未统一切换 |
| Instrument / RiskFreeRate | 已迁移（底座） | `app/services/instruments/*`、`app/services/risk_free_rate/*` | 已形成共享底座，可继续扩展 |
| Broker Contract (`bt_api_py`) | 跨仓迁移项 | 独立 `bt_api_py/bt_api_py/brokers/*` | broker 统一能力继续沉淀在 `bt_api_py`，后续按交易所/券商拆到独立 `bt_api_xx` 包；不在 `backtrader_web` 内继续产品化 |
| Broker Profiles | 存量兼容能力 | `app/models/broker_profile.py`、`app/services/broker_profiles.py`、`app/api/brokers.py` | 当前仅作为 170 存量 MVP / 兼容入口，171 不再把它扩成 web 内 broker 平台 |
| Portfolio Ledger | 部分迁移 | `app/services/portfolio_ledger.py`、`app/api/portfolio_ledger.py` | 账本 API 已在，但当前实现为 in-memory MVP |
| Equity Research | 部分迁移 | `app/services/equity_research.py`、`app/api/equity_research.py` | 有 search/quote/history/technicals，但无 info/financials/peers，且数据偏示例 |
| News Intelligence | 部分迁移 | `app/services/news_intelligence.py`、`app/api/news_intelligence.py` | 有 source/article/analyze 最小闭环，但仍是内存态 + 规则分类 MVP |
| Options Chain | 部分迁移 | `app/services/options_chain.py`、`app/api/options_chain.py` | 有 PCR/max pain/Greeks/Topic，但链条和 Greeks 仍属简化实现 |
| Scanner DSL | 部分迁移 | `app/services/scanner_service.py`、`app/api/scanners.py` | 安全 DSL 最小可用，但支持维度仍非常有限 |
| Quant Tool Registry | 部分迁移 | `app/services/quant_tools_runtime.py`、`app/api/quant_tools.py` | 协议层较完整，但部分 handler 仍为 placeholder/mock 级接线 |
| Fincept Gap / Migration 文档 | 本次补齐 | 本文档、`WS_GATEWAY_MIGRATION.md` | 170 原计划文档缺口在 171 起手阶段补齐 |

---

## 3. 当前最主要的未完成迁移项

### 3.1 底座/架构层

- Data Connector Registry 仍未形成完整 provider/endpoint/quality/job 产品治理闭环
- `bt_api_py` 生态仍需继续演进，但这部分属于跨仓迁移：统一能力保留在 `bt_api_py`，交易所/券商能力拆到 `bt_api_xx` 包
- `ws_gateway` 尚未统一接管旧 WS 路由

### 3.2 产品能力层

- Portfolio Ledger 仍缺持久化、dividend、benchmark 与更完整现金流建模
- Equity Research 仍缺 `info/financials/peers`
- News Intelligence 仍缺真实 RSS 抓取、cluster、AI 摘要持久化
- Options Chain 仍缺真实 provider 优先级、cache、throttle、多 strike 深化
- Scanner DSL 仍缺 factor/news/portfolio 维度
- Quant Tool Registry 仍缺真实 handler 深化和模块拆分

### 3.3 前端层

以下页面仍带明显 MVP / demo 特征：

- `PortfolioLedgerPage.vue`
- `EquityResearchPage.vue`
- `NewsIntelligencePage.vue`
- `OptionsChainPage.vue`
- `ScannerPage.vue`
- `QuantToolsPage.vue`

---

## 4. 结论

backtrader_web **已经完成了适合 Web 架构的 FinceptTerminal 核心能力迁移第一阶段**，但还**没有完成所有应迁能力的完整产品化迁移**。

因此：

- 迭代 170 应被视为 **MVP 收口完成**
- 迭代 171 应被视为 **产品化深化与迁移缺口收口**
- 其中 broker 相关深化迁移不在 `backtrader_web` 仓内继续展开，而是转由 `bt_api_py / bt_api_xx` 生态承接

后续所有与 FinceptTerminal 相关的新工作，应默认优先对照本清单，避免重复造方向或误判“已经迁完”。
