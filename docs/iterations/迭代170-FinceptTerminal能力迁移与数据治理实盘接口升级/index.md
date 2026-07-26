# 迭代 170 - FinceptTerminal 能力迁移与数据治理 / 实盘接口升级

> **文档状态**: 已完成（MVP 收口；剩余深化迁移转入迭代 171）
> **创建日期**: 2026-05-26
> **参考项目**: `/Users/yunjinqi/Documents/new_projects/FinceptTerminal`
> **前置基线**: 迭代 166-169 已完成 AI 可信度、AI 工程化、量化研究专业度、工程债务收尾
> **核心目标**: 在不构建 Qt 桌面应用的前提下，吸收 FinceptTerminal 中适合 Web/FastAPI 架构的金融终端能力，重点补齐「统一数据连接器治理、实时数据主题、独立组合账本、标准化实盘 Broker API、新闻情报、期权链与 AI 工具化执行」能力。
> **最新进度**: 已完成 `data_governance / data_topic_hub / ws_gateway / instruments / risk_free_rate / portfolio_ledger / equity_research / news_intelligence / options_chain / scanners / quant_tools` 后端 MVP、独立 `bt_api_py` broker contract 子包、前端 API wrapper / 路由 / 最小页面入口，以及 `8.3` 所需 guide / license 文档与 `.env.example` 占位补齐；并进一步补齐 DataTopicHub `list / refresh / stats(admin)` REST API、`/ws/data-topics` WebSocket 通道、`ws_gateway` fan-out 联动与前端 `DataTopicsPage` 入口，以及 BrokerConnectionProfile 的增强前后端闭环（后端 `/api/v1/brokers/profiles`、`health / accounts / positions / orders / quotes`、`enable-write` 管控、凭证脱敏、90 天轮换提醒、audit log 记录，并在命中现有 live-trading manual gateway runtime 时优先透传 runtime health / account / positions / orders / quote，同时支持显式 `runtime_gateway_key/runtime_account_id` 绑定优先；前端 `brokerProfilesApi`、`BrokerProfilesPage`、`/brokers` 路由与 AppLayout 菜单入口，并补齐手工表单录入、runtime binding 展示、rotation warning 展示，以及 enable-write 二次确认输入与幂等请求负载）；同时继续把 170B/170C 的契约缺口往前推进：Portfolio Ledger 已补齐 `GET /{id}`、`/transactions`、`/snapshots`、`/export` 与前端明细/导出展示，Scanner 已补齐 `/api/v1/scanners/tasks/{task_id}` 查询闭环，Options Chain 已补齐 richer payload 字段（`underlying/source/atm_strike/timestamp`、call/put `volume/iv`）及 `option:chain / fno:pcr / fno:max_pain / option:atm_iv` topic 发布。经本轮审计，170 可视为“适合 Web 架构的 Fincept 能力核心 MVP 已落地”，但尚未达到“所有应迁能力均已完整产品化”的程度，剩余深化迁移已转入迭代 171。

---

## 0. 背景与分析结论

FinceptTerminal 是一个 Qt/C++ 桌面金融终端，核心价值不在 Qt UI 本身，而在其产品能力组织方式：

| FinceptTerminal 能力 | 本地参考位置 | 当前项目状态 | 迭代 170 处理策略 |
|---|---|---|---|
| 100+ 数据连接器 | `fincept-qt/scripts/*.py`、`scripts/*_DATA_SOURCES.md` | 当前以 AkShare 数据治理为主，少量实时行情服务 | 扩展为通用数据源/接口注册中心，接口元数据入库 |
| DataHub 主题注册与 TTL 策略 | `fincept-qt/docs/DATAHUB_TOPICS.md`、`src/services/markets/MarketDataService.h` | 有 WebSocket manager 和 quote/cache，但缺少统一 topic registry | 新增 Web 版 `DataTopicHub`，统一 quote/history/news/broker/option topic |
| 独立组合账本 | `src/services/portfolio/PortfolioService.h` | 现有 `portfolio_api.py` 聚合实盘策略日志，不是独立组合账户/交易账本 | 新增 Portfolio/Holding/Transaction/Dividend/Snapshot 模型与 API |
| Equity Research | `src/services/equity/EquityResearchService.h` | 有策略/回测/风险分析，无股票研究工作台 | 基于数据治理接口新增股票研究查询 API 与前端页 |
| 新闻情报与 AI 摘要 | `src/services/news/NewsService.h` | 缺少新闻源、情绪、事件影响、AI 摘要 | 新增新闻源治理、RSS 拉取、情绪/风险分类和摘要 |
| 期权链 / F&O | `src/services/options/OptionChainService.h`、`DATAHUB_TOPICS.md` | 迭代 168 有风险/归因，但没有期权链、Greeks、PCR/max pain | 新增期权链 MVP，优先支持 AkShare/CBOE/券商适配 |
| Broker 接口注册与多账户流 | `fincept-qt/src/trading/*.h` | 实盘能力分散在 backend gateway/manual services；`src/bt_api_py` 基本空壳 | 把标准化 Broker API 合约与适配层放入 `bt_api_py` |
| Algo Trading scanner/deployment | `src/services/algo_trading/AlgoTradingService.h` | 有策略、回测、自动交易，但缺少通用条件扫描器 | 新增条件扫描 DSL 与扫描任务 API |
| AI Quant Lab / Agent 工具 | `AIQuantLabService.h`、`AgentService.h`、`MCP_TOOLS_GUIDE.md` | 已有 AI Chat/Prompt/模型路由，但缺少平台能力工具化调用 | 新增内部 Quant Tool Registry，先接入只读金融工具 |

### 0.1 关键约束

1. **不构建 Qt 桌面应用**：本迭代只吸收产品能力与服务设计，前端仍使用 Vue + Element Plus。
2. **实盘交易 API 继续放在 `src/bt_api_py/`**：后端 FastAPI 只做账户配置、鉴权、审计与编排，不把 Broker SDK 细节塞回 `app/services/manual_gateway_service.py`。
3. **数据接口进入数据库并纳入数据治理**：所有新增数据源、接口、参数、限频、缓存策略、目标表、质量规则都入库管理。
4. **不直接复制受限代码**：FinceptTerminal README 标明 AGPL/商业许可约束；默认采用 clean-room 迁移，借鉴能力与接口形态，重新按当前项目架构实现。
5. **行业最佳实践优先**：不确定处采用 provider registry、schema validation、secrets isolation、async task、rate limiting、idempotent ingestion、audit log、least privilege。

> **当前边界说明**：本节保留的是迭代 170 立项时的历史表述；当前生效边界已在迭代 171 中收口为：`broker` 统一能力继续沉淀在独立 `bt_api_py` 仓及后续 `bt_api_xx` 包中，`backtrader_web` 不再继续扩 broker registry / adapter / native-paper 实装平台。

### 0.2 Clean-room 迁移规范与许可证审计（P0 阻断项）

FinceptTerminal 采用 **AGPL-3.0 + 商业许可证双轨制**，`LICENSE` 第 47-49 行明确声明
「clone/fork/modification does not grant commercial or internal-use rights」。
本项目即便仅作内部使用也必须遵守以下硬约束，否则不得开始任何 T2 之后的编码工作：

1. **两人 clean-room 协议**
   - Reader：阅读 Fincept 头文件 / 文档，撰写中文规格 `docs/architecture/FINCEPT_*_SPEC.md`，规格只描述**能力与接口形态**，禁止贴源码片段。
   - Implementer：仅依据规格用 Python/FastAPI 重新实现，承诺整个 PR 期间不打开任何 Fincept 源码文件。
   - Reviewer：PR 阶段对照规格抽查实现，发现任何 C++ 残留命名、注释翻译、宏定义照搬 → 退回重写。
2. **许可证审计台账** `docs/architecture/FINCEPT_LICENSE_AUDIT.md`：逐条记录借鉴的产品能力、参考头文件路径、是否仅借接口形态、Implementer、提交 commit，便于法律评估和未来开源 / SaaS 发布审核。
3. **接口形态可借用，实现独立完成**：`TopicPolicy` 字段名、Producer 抽象、broker capability 枚举名可以一致，但代码必须从零写起，可以参照 Redis Pub/Sub、NATS、Eventuate 等开源 / 行业通用实现。
4. **Fincept Python 脚本一律不复制**：`fincept-qt/scripts/*.py` 同样在 AGPL 范围内。AkShare 部分本项目已有自有实现；其它 provider 必须依据 provider 官方文档独立实现，不读取 Fincept 代码。
5. **法律 checkpoint**：T1 完成后、首批 connector 上线前，须输出 `docs/architecture/FINCEPT_LICENSE_REVIEW.md`，由实施负责人签字声明「PR 中无 Fincept 原文片段」。若未来计划开放 SaaS / 商业发行，必须独立向 Fincept 商谈商业许可证，本迭代不做该假设。

---

## 1. 总目标

| 维度 | 当前状态 | 迭代 170 目标 |
|---|---|---|
| 数据接口治理 | AkShare 专项管理 | 通用 Data Connector Registry，支持 AkShare/Yahoo/FRED/DBnomics/CoinGecko/CBOE 等首批连接器 |
| 实时数据分发 | 分散在 quote/WebSocket/实盘服务 | DataTopicHub：topic + TTL + min_interval + cache + WS fan-out |
| 实盘 API | backend 服务直接处理较多网关细节，`bt_api_py` 空 | `bt_api_py` 定义 Broker 标准合约、注册表、mock/paper/现有网关 bridge |
| 组合管理 | 聚合实盘策略日志 | 独立组合账本：组合、持仓、交易、分红、快照、导入导出、基准对比 |
| 股票研究 | 缺少独立研究台 | 股票 quote/info/history/financials/technicals/peers/news 查询工作流 |
| 新闻情报 | 缺少新闻流与事件风险 | RSS 源管理、文章缓存、情绪/影响/威胁分类、AI 摘要 |
| 期权分析 | 缺失期权链 | Option Chain MVP：链、PCR、max pain、Greeks/IV、topic 发布 |
| AI 工具化 | AI Chat 能问答，但工具调用边界弱 | 内部 Quant Tool Registry，工具 schema 直接采用 MCP 兼容形态，让 AI 可安全调用行情/组合/风险/数据接口只读工具 |
| **共享底座（新增）** | 现状 | 迭代 170 目标 |
| Instrument / Symbol 字典 | 散落在 quote / akshare / live trading | 抽取 `app/services/instruments/`：canonical_symbol ↔ broker_symbol 映射、exchange、asset_class、currency |
| Risk-free Rate | 168 perf_attribution + 新增 option Greeks + 组合指标 各自取值 | 抽取 `app/services/risk_free_rate/`：FRED DGS10 + 24h cache + `.env` 兜底（默认 0.04）|
| WebSocket 网关 | 分散在 paper_trading / monitoring / backtest_enhanced / realtime_data / overfitting / strategy_version | 抽取 `app/services/ws_gateway/`：连接管理、心跳、订阅路由、与 DataTopicHub fan-out 串联 |
| 许可证治理 | 无 | 新增 `docs/architecture/FINCEPT_LICENSE_AUDIT.md` 台账，每个借鉴能力一条记录 |

---

## 2. 执行原则

### 2.1 可以做

1. 新增 `app/services/data_connectors/`、`app/services/data_topic_hub/`、`app/services/portfolio_ledger/`、`app/services/equity_research/`、`app/services/news_intelligence/`、`app/services/options_chain/`、`app/services/quant_tools/`。
2. 扩展现有 `app/models/akshare_mgmt.py` 或新增通用数据治理模型，保留现有 AkShare API 兼容层。
3. 在 `src/bt_api_py/` 新增 Broker API 合约、注册表、paper/mock adapter、现有 gateway bridge。
4. 复用迭代 167 的 AI Router / Prompt Registry / AI Call Log，复用迭代 168 的 risk_analytics / factor_lib / perf_attribution。
5. 复用现有 `ws_manager`、`quote_service`、`akshare_execution_service`、`paper_trading_service`、`manual_gateway` 拆分结果。
6. 新增 Vue 页面时优先以 API 封装 + 轻量表格/图表 MVP 落地，不追求 Fincept Qt 级复杂度。

### 2.2 不要做

1. 不要引入 Qt、C++、桌面打包或跨端桌面壳。
2. 不要把 FinceptTerminal 的 AGPL/商业许可代码整文件复制进当前项目；除非后续明确完成许可证审查。
3. 不要把 100+ 数据源一次性搬完；先做连接器注册机制和 6-8 个高价值连接器。
4. 不要把真实券商凭证明文存库；使用现有 `.env` / secrets 机制，数据库只存引用、脱敏元数据和启用状态。
5. 不要让数据同步任务阻塞请求线程；全部走异步任务、进度查询和可恢复执行。
6. 不要在 AI 工具中开放默认下单能力；读工具先行，交易工具必须显式确认、风险校验和审计。
7. **不要**在 170A 阶段触碰 `live_trading_manager` / `paper_trading_service` / 策略运行循环的写路径；broker adapter bridge 必须先以**只读模式**联调（健康检查、查持仓、查订单、查行情），下单写路径推迟到 170B 显式启用并经过双人审阅。

### 2.3 向后兼容不变量（必须由验收测试守住）

以下既有接口在迭代 170 全程**不得破坏**；新增能力必须通过新路由/新表实现并保留旧路由：

| 范围 | 保留路径 | 新增路径（不冲突） |
|---|---|---|
| Akshare 数据治理 | `/api/v1/data/*`、`/api/v1/akshare-*` | `/api/v1/data-governance/providers`、`/api/v1/data-governance/endpoints`、`/api/v1/data-governance/jobs` |
| 组合聚合（实盘日志维度） | `/api/v1/portfolio/*`（现 `portfolio_api.py` 全部端点） | `/api/v1/portfolio-ledger/*`（独立组合账本） |
| 实盘下单 / 手动网关 | `/api/v1/live-trading/*`、`/api/v1/paper-trading/*`、`manual_gateway_service` 内所有现有接口 | `/api/v1/brokers/*`（仅 read-only 第一阶段），写路径桥接到现有 service |
| 行情 / Quote | `/api/v1/quote/*`、`/api/v1/realtime/*` | `/api/v1/data-topics/*`、`/ws/data-topics/{topic}` |
| 数据库表 | `ak_data_scripts / ak_data_interfaces / ak_data_tables / ak_scheduled_tasks / ak_task_executions` | 中性化 `dg_provider / dg_endpoint / dg_endpoint_param / dg_ingest_job / dg_quality_rule`，旧表保留并由 VIEW 兜底（见 T2.5）|

**验收硬指标**：每个新模块必须附带至少 1 个回归测试断言旧接口仍 200 OK 且响应字段未减少；CI 中加入 `tests/test_backward_compat_iter170.py` 作为整体守门。

---

## 3. 任务分解

### 阶段一：Fincept 能力清单与通用数据治理底座（P0）

- [ ] **T1**: 迁移清单与许可边界固化
  - 新增 `docs/architecture/FINCEPT_TERMINAL_GAP_ANALYSIS.md`。
  - 记录 FinceptTerminal 可借鉴能力：DataHub、数据连接器、组合账本、新闻情报、期权链、Broker Registry、AI/MCP 工具。
  - 明确 clean-room 迁移原则：只迁移能力与接口设计，不复制受限实现。
  - 输出首批连接器优先级：AkShare、Yahoo Finance、FRED、DBnomics、CoinGecko、CBOE、CFTC、FMP/AlphaVantage（需要 key）。

- [ ] **T2**: 通用数据连接器模型
  - 新增或扩展模型：`DataProvider`、`DataEndpoint`、`DataEndpointParam`、`DataIngestionJob`、`DataQualityRule`。
  - 字段包括：provider、category、endpoint_name、function_path、params_schema、auth_type、api_key_env、rate_limit、cache_ttl_sec、target_database、target_table、normalization_profile、quality_profile、is_active。
  - 保持现有 AkShare `ak_*` 管理表/API 可用，新增兼容映射层，避免破坏 `/api/v1/data/*` 与 `/api/v1/akshare-*`。
  - **必须声明增量同步键**：每个 Endpoint 在注册时必须声明 `incremental_sync_key`（时间列 或 主键）；sync executor 对行数 > 100k 的表拒绝全列比较兑底（防止迭代 128 同步卡住问题复发）。

- [ ] **T2.5**: 数据治理表中性化与兼容视图
  - 新增 `app/models/data_governance.py`：`DgProvider、DgEndpoint、DgEndpointParam、DgIngestJob、DgQualityRule`，表名以 `dg_*` 为前缀。
  - 保留现有 `ak_*` 表及 ORM，新增 Alembic 迁移在首次启动时从 `ak_*` 复制存量到 `dg_*`，后续写路径一律走 `dg_*`，避免双写。
  - 提供向后兼容 SQL VIEW：`CREATE VIEW ak_data_interfaces AS SELECT ... FROM dg_endpoint WHERE provider='akshare'`，避免现有 SQL 查询报错。
  - 验收：`tests/test_data_governance_compat.py` 查询 `ak_data_interfaces` 视图并断言现有 `/api/v1/akshare-interfaces` 返回记录数 ≥ 迁移前。
  - **不要**在本迭代删除 `ak_*` 表，仅设为 `read-only mirror`；删除推迟到其后一个迭代。

- [ ] **T3**: 数据连接器执行器与标准输出
  - 新增 `app/services/data_connectors/executor.py`。
  - 定义统一输出：`columns`、`rows`、`metadata`、`source_timestamp`、`provider_latency_ms`、`quality_warnings`。
  - 支持 sync/async Python callable、HTTP REST、已有 AkShare interface-backed execution 三类执行路径。
  - 所有结果可选择：预览返回、写入 `akshare_data`/timeseries DB、写入业务库治理表。

- [ ] **T4**: 首批数据源入库与前端治理入口
  - 从 Fincept 文档中选 6-8 个首批 provider：AkShare、Yahoo Finance、FRED、DBnomics、CoinGecko、CBOE、CFTC、FMP/AlphaVantage。
  - 后端新增 provider/endpoints CRUD API：`/api/v1/data-governance/providers`、`/endpoints`、`/jobs`。
  - 前端数据治理页新增“数据源/接口注册中心”tab。
  - 验收：能查询接口列表、查看参数 schema、执行预览、创建异步入库任务。

- [ ] **T4.5**: 共享底座 - Instrument Service + RiskFreeRateService
  - 新增 `app/services/instruments/`：`Instrument(canonical_symbol, broker_symbol, exchange, asset_class, currency, lot_size, tick_size, ...)`；提供 `resolve(canonical|broker_symbol, broker_id) -> Instrument` 与反向查找。
  - 首期数据源：复用现有 AkShare 股票 / 期货 符号表 + 人工在 `data/instruments_seed.csv` 维护 BrokerSymbol 映射；后续以连接器拉取。
  - 新增 `app/services/risk_free_rate/`：FRED `DGS10` 拉取 + 24h cache + `.env` 兑底 `RISK_FREE_RATE_DEFAULT=0.04`；提供 `get_rate(currency='USD'|'CNY'|'EUR') -> float`，主要指标统一调用同一根。
  - 168 迭代 `perf_attribution`、168 `risk_analytics` (Sharpe/Sortino)、本迭代 Option Greeks、Portfolio Ledger 指标计算 均应调用这个服务，**不得继续硬编码**。
  - 验收：`tests/test_instruments_service.py` (canonical ↔ broker symbol 来回) 与 `tests/test_risk_free_rate.py` (缓存 / 兜底 / FRED 接口必走 fakehttp)。

### 阶段二：Web 版 DataHub / DataTopicHub（P0）

- [ ] **T5**: DataTopicHub 核心服务
  - 新增 `app/services/data_topic_hub/`: `registry.py`、`cache.py`、`publisher.py`、`scheduler.py`、`policy.py`。
  - **TopicPolicy 完整字段**（参考 Fincept `TopicPolicy.h`，以能力形态为准重写）：
    - `ttl_ms`：缓存新鲜期。
    - `min_interval_ms`： refresh 频率下限。
    - `refresh_timeout_ms`： producer 卡死检测，超时后清 in_flight 并警告。
    - `push_only`：调度器不主动拉，仅 producer 主动推（WebSocket 类场景）。
    - `coalesce_within_ms`：高频 push 同窗口只保留最后一个值以限背压。
    - `drop_on_idle`：最后一个订阅者离开后丢弃 TopicState（agent run / per-session topic 防内存垃圾）。
    - `pause_when_inactive`：页面不可见时暂停 fan-out，默认 false。
  - Topic 命名规范（生产者主题为首段）：`market:quote:<sym>`、`market:history:<sym>:<period>:<interval>`、`news:symbol:<sym>`、`broker:<broker>:<account>:positions`、`option:chain:<broker>:<underlying>:<expiry>`。
  - **语义接口**：`peek(topic)` (TTL gate)、`peek_raw(topic)` (诊断用、返回最后值无 TTL)、`request(topic, force=False)` (刷新)、`subscribe(owner, topic|pattern, cb)` (含通配 `*` 后缀)、`subscribe_errors`、`retire_topic(topic)` (一次性 run 读取后退绑)。
  - **生产者抽象** `Producer`：topic_patterns()、refresh(topics)、max_requests_per_sec()；调度器遵守 `max_requests_per_sec` 节流。
  - 验收：`tests/test_data_topic_hub.py` 至少覆盖 TTL、coalesce、push_only、drop_on_idle、refresh_timeout、pattern 订阅、retire 后订阅仍在 7 个场景。

- [ ] **T6**: Topic API 与 WebSocket 通道
  - REST API：`GET /api/v1/data-topics`（列表+订阅者数+最后错误）、`GET /api/v1/data-topics/{topic}/peek`、`POST /api/v1/data-topics/{topic}/refresh`、`GET /api/v1/data-topics/stats` (admin only)。
  - WebSocket：`/ws/data-topics/{topic}` 以及 `/ws/data-topics?pattern=<glob>` 含鉴权 token。
  - 先接入 market quote/history、broker positions/orders 两类 producer；news/option 在 T14/T15 接入。
  - 验收：同一 symbol N 个订阅者仅触发一次上游调用；高频 push 场景 WS 输出 < `coalesce_within_ms` 频率。

- [ ] **T6.5**: WebSocket 网关统一抽取（DataTopicHub fan-out 的前置条件）
  - **背景**：项目当前无统一 `ws_manager`，WebSocket 代码分散在 `paper_trading.py / monitoring.py / backtest_enhanced.py / realtime_data.py / overfitting.py / strategy_version.py` 至少 6 处；DataTopicHub 如果直接上线会重复连接管理、心跳、鉴权逻辑。
  - 新增 `app/services/ws_gateway/`：
    - `connection.py`：连接生命周期管理、鉴权（复用 `auth_service`）、心跳 ping/pong、零负载重连背压。
    - `subscription_router.py`：client 带 `topics: ["market:quote:RB2510", "broker:*:*:positions"]`。
    - `metrics.py`：连接数、订阅数、消息吞吐、p95 延迟。
  - DataTopicHub publisher 调用 `ws_gateway.publish(topic, value)` 而不是各页面自己 broadcast。
  - 迁移策略：现有 6 处 WebSocket **暂不迁移**，仅作为迁移候选记录于 `docs/architecture/WS_GATEWAY_MIGRATION.md`；本迭代只保证 DataTopicHub 走新网关，未来迭代逐项迁移。
  - 验收：`tests/test_ws_gateway.py` 覆盖连接鉴权失败、心跳超时、订阅模式路由、publish 多订阅者 fan-out。

### 阶段三：`bt_api_py` 标准化实盘 Broker API（P0）

- [ ] **T7**: `bt_api_py` 包结构与 Broker 合约
  - 新增 `src/bt_api_py/brokers/types.py`、`base.py`、`registry.py`、`capabilities.py`、`errors.py`。
  - 标准类型：`BrokerAccount`、`Instrument`、`Quote`、`Bar`、`OrderRequest`、`OrderResult`、`Position`、`Holding`、`Balance`、`OrderStatus`、`MarketCalendarDay`、`MarketClock`、`OrderMargin`、`BasketMargin`、`GttOrder`、`BrokerCapabilities`。
  - **核心方法**（必选）：`connect`、`disconnect`、`health`、`list_accounts`、`get_balance`、`get_positions`、`get_holdings`、`get_orders`、`get_quote(s)`、`get_history`、`place_order`、`modify_order`、`cancel_order`。
  - **可选能力（默认 NotSupported）**：`get_calendar`、`get_clock`、`get_latest_bars`、`get_historical_bars`、`get_order_margins`、`get_basket_margins`、`gtt_*`（place / list / get / modify / cancel）、`subscribe_ticks (WS)`、`get_native_paper_account`。
  - `BrokerCapabilities`（能力位）：`supports_modify_order`、`supports_bracket_order`、`supports_cover_order`、`supports_gtt`、`supports_pretrade_margin`、`supports_basket_margin`、`supports_market_calendar`、`supports_native_paper`、`supports_streaming_quotes`、`supported_asset_classes`、`supported_exchanges`、`supported_product_types`。
  - 合约必须支持 async；所有外部错误转换为结构化 `BrokerError(code, message, retryable, cause)`，`code` 枚举至少含 `AUTH_FAILED / RATE_LIMITED / INSUFFICIENT_FUNDS / ORDER_REJECTED / NOT_SUPPORTED / NETWORK_ERROR / SDK_INTERNAL`。
  - **合约测试包** `src/bt_api_py/testing/contract_cases.py`：以 pytest 参数化 fixture 提供统一用例，每个 adapter 仅需依赖该 fixture 即可跑全部合约测试。

- [ ] **T8**: Mock/Paper adapter 与现有网关 bridge
  - 新增 `bt_api_py.brokers.mock.MockBrokerAdapter`：实现全部能力位，走内存序列化 fixture；作为合约测试达成 100% 方法覆盖。
  - 新增 `bt_api_py.brokers.paper.PaperBrokerAdapter`：包装当前 `PaperTradingService`。**读路径优先**：get_balance/positions/orders/quote；下单 / 取消最初仅代理现有 service 同名方法，不重写成交逻辑。
  - 新增 `bt_api_py.brokers.gateway_bridge.GatewayBridgeAdapter`：首期仅桥接 `manual_gateway_service` 的 read API（health / positions / orders / quotes）。下单写路径默认 `NotImplementedError("170B")`，需 170B 双人审阅并加载 feature flag `BT_API_PY_BRIDGE_ENABLE_WRITE=1` 后才能开启。
  - 验收：`tests/test_broker_contract.py` 使用 `contract_cases.py` fixture 跑完三个 adapter；MockBrokerAdapter 必须 100% 覆盖并为其他两个提供 xfail/skipif 能力位准入。

- [ ] **T9**: Broker 账户注册与安全治理
  - 后端新增 `BrokerConnectionProfile` 模型：broker_id、account_alias、capabilities、credentials_ref、enabled、last_health、created_by、`is_destructive_enabled` (默认 false)。
  - **凭证存取双重保护**：
    - 首选 `.env` 环境变量名引用 (`BT_BROKER_<ALIAS>_KEY`, `BT_BROKER_<ALIAS>_SECRET`)，数据库只存环境变量名。
    - 可选接 macOS Keychain / HashiCorp Vault 接口（接口预留不在本迭代实现）。
    - **严禁**在任何路径返回明文 secret；API 响应必须脱敏为 `***LAST4`。
  - **定期轮换提醒**：存储 `credentials_rotated_at`；超 90 天未轮换产出警告中心提示，但不主动禁用。
  - **destructive 操作双人确认**：企业启用实盘下单需管理员在该 profile 上显式击 `Enable Live Write` 记录 audit log。
  - API：`/api/v1/brokers/profiles`、`/health`、`/accounts`、`/positions`、`/orders`、`/quotes`、`/profiles/{id}/enable-write`。
  - 交易 API 保持显式确认与风险守卫：复用 `trading_risk_guard.py`；下单需 `idempotency_key`，服务端 24h 去重。

### 阶段四：独立组合账本与组合分析（P0）

- [ ] **T10**: Portfolio Ledger 数据模型
  - 新增模型：`Portfolio`、`PortfolioHolding`、`PortfolioTransaction`、`PortfolioDividend`、`PortfolioSnapshot`。
  - 支持三类组合来源：manual、imported、broker_linked。
  - 支持交易类型：buy、sell、dividend、cash_deposit、cash_withdrawal、fee、split_adjustment。
  - 支持 currency、benchmark_symbol、broker_profile_id、tags、notes。

- [ ] **T11**: 组合 CRUD / 导入导出 / 快照回填
  - **路由隔离**：新路由一律走 `/api/v1/portfolio-ledger/*`，不与现有「实盘日志聚合」路由 `/api/v1/portfolio/*` 冲突。
  - REST API：`POST /api/v1/portfolio-ledger`、`GET /api/v1/portfolio-ledger/{id}`、`/holdings`、`/transactions`、`/dividends`、`/snapshots`、`/import`、`/export`。
  - 导入支持 CSV/JSON，提供 dry-run 校验和冲突报告；导入走 `idempotency_key` (`SHA256(file)`) 避免重复上传。
  - 快照回填复用 DataTopicHub 的 history topic，生成 daily NAV；需以 `RiskFreeRateService` 统一计算 Sharpe / Sortino 年化。
  - 导出不得包含 secrets / broker 凭证；导出 JSON schema 需随文档发布以保证下轮迭代可反向调用。

- [ ] **T12**: 组合指标接入迭代 168 能力
  - 接入 `risk_analytics`：VaR/CVaR、Kelly、position sizing、benchmark metrics。
  - 接入 `perf_attribution`：Brinson / Fama-French 输入来自组合持仓与收益序列。
  - 新增组合相关性矩阵、基准对比、风险自由利率配置。
  - 前端新增 Portfolio Ledger 页面 MVP：组合列表、持仓、交易、绩效卡片、快照曲线。

### 阶段五：股票研究与新闻情报 MVP（P1）

- [ ] **T13**: Equity Research API
  - 新增 `app/services/equity_research/` 与 `app/api/equity_research.py`。
  - API：`search_symbols`、`quote`、`info`、`history`、`financials`、`technicals`、`peers`。
  - 数据来源统一走 Data Connector Registry，不在 service 中硬编码 provider。
  - 技术指标优先复用现有因子库/安全表达式；需要第三方库时按可选依赖处理。

- [ ] **T14**: News Intelligence MVP
  - 新增 `NewsSource`、`NewsArticle`、`NewsAnalysis`、`NewsCluster` 模型。
  - **文章字段目录**（参照 Fincept `NewsService.h`，独立实现）：
    - `id、headline、summary、source、url、region、lang(ISO)、published_at、fetched_at、hash`
    - `priority`：`FLASH | URGENT | BREAKING | ROUTINE`
    - `tier`：1=wire、2=major、3=specialty、4=blog
    - `source_flag`：`NONE | STATE_MEDIA | CAUTION`（可信度标签）
    - `sentiment`：`BULLISH | BEARISH | NEUTRAL` + `sentiment_score [-1, 1]`
    - `impact`：`HIGH | MEDIUM | LOW`
    - `threat`：`{level: CRITICAL|HIGH|MEDIUM|LOW|INFO, category: conflict|cyber|natural|market|regulatory|general, confidence}`
    - `tickers: List[str]、topics: List[str]、cluster_id`
  - **接入层**复用已有拉取 connector（T3 executor）：RSS 列表 + 简单 HTML fallback；拉取频率 / 限频走 `max_requests_per_sec`。
  - **去重**：URL canonicalize 后 SHA256 走 unique constraint；相似文章以 headline 6-gram MinHash 聚类为 `cluster_id`。
  - **分类三层**：优先规则引擎（关键词表 + tier 调权）→ 不确定时调用 AI Chat 走 167 迭代预算 / 日志 / Prompt Registry；同一 cluster 合并调用避免费用波动。
  - **Topic 发布**（DataTopicHub）：`news:general`、`news:symbol:<sym>`、`news:category:<cat>`、`news:cluster:<id>`（push-only）。
  - **Live feed 预留**：RSS 为首期实现，WebSocket live feed 接入紧急推送接口预留，推送走 ws_gateway。
  - 前端新增新闻情报页：列表、过滤（region/category/source_flag/priority/threat.level）、AI 摘要、关联 symbol、cluster 展开。
  - 验收：`tests/test_news_intelligence.py` 覆盖去重、分类、cluster、topic 发布、AI fallback 不可用时仍能返回 degraded 响应。

### 阶段六：期权链 / F&O 分析 MVP（P1）

- [ ] **T15**: Option Chain 服务
  - 新增 `app/services/options_chain/` 与 `app/api/options_chain.py`。
  - **输出结构**：`{underlying, expiry, spot, rows: [{strike, call: {oi, volume, iv, greeks}, put: {oi, volume, iv, greeks}}], pcr, max_pain, atm_strike, atm_iv, timestamp, source}`。
  - **数据源优先级**：已连接 broker (当 `supports_options=true`) → AkShare 期权接口 → CBOE connector → mock fixture。
  - **估值与 Greeks**：
    - 首期纯 Python Black-Scholes 实现 (`app/services/options_chain/pricing.py`)，依赖 `RiskFreeRateService`。
    - 可选 `py_vollib` 作为快路径，不可用时自动回退 BSM。
    - **节流与缓存**：每 strike 同一侧 (call/put) Greeks 重算不高于 1/500ms；未达阈值的请求走 IV/Greeks cache。
    - **性能预算**：BSM <=500ms / strike，py_vollib <=100ms / strike；单次请求最多 64 strike batch。
  - **Topic 发布**：`option:chain:<broker>:<underlying>:<expiry>`、`fno:pcr:<broker>:<underlying>`、`fno:max_pain:<broker>:<underlying>`、`option:atm_iv:<broker>:<underlying>`（衡量下游订阅压力以调节上游调用频率）。
  - **Spot 复用**：不要重复调用 broker quote，直接 `DataTopicHub.peek("market:quote:<underlying>")`。
  - 验收：`tests/test_options_chain.py` 覆盖 PCR/max_pain 计算、IV 缓存节流、insufficient_data degraded、topic 发布、不同 provider 同一接口一致输出。

### 阶段七：条件扫描器与 AI 工具化（P1）

- [ ] **T16**: Algo Scanner 条件 DSL
  - 参考 Fincept `algo_trading/scanner_engine.py` 思路，新增安全条件表达式 DSL。
  - 支持条件：price/volume/indicator/factor/news_sentiment/portfolio_exposure。
  - 支持 AND/OR、lookback_days、timeframe、symbols universe。
  - API：`POST /api/v1/scanners/run`、`GET /api/v1/scanners/tasks/{task_id}`。
  - 扫描结果可一键加入候选策略工作区，但不自动下单。

- [x] **T17**: Quant Tool Registry（MCP 形态兼容）
  - 新增 `app/services/quant_tools/registry.py`、`schema.py`、`audit.py`、`confirmation.py`。
  - **工具描述采用 MCP 兼容 JSON Schema** （未来趋势可直接暴露为 MCP server）：
    ```python
    QuantTool = {
      "name": "markets.get_quote",
      "description": "返回指定 symbol 的最新行情快照",
      "input_schema": {...},   # JSON Schema Draft-07
      "output_schema": {...},
      "auth_level": "user|trader|admin",
      "is_destructive": False,
      "requires_confirmation": False,
      "timeout_ms": 5000,
      "rate_limit_per_user_per_min": 30,
      "handler": Callable,
    }
    ```
  - **首批只读工具**：`markets.get_quote`、`markets.get_history`、`portfolio_ledger.get_summary`、`risk.var_cvar`、`factor.evaluate`、`news.latest`、`data_governance.endpoint_preview`、`data_topics.list`、`data_topics.peek`。
  - **destructive guard**：`is_destructive=True` 的工具调用需带 `confirmation_token`，该 token 由人类用户从前端 UI 点击生成，AI 不能自发；写表、下单、删除类工具进一步带额外 `idempotency_key`。
  - **审计与资源**：每次工具调用写 `ai_call_logs` + `audit_records`（input 脱敏、output 截断 4 KB）；复用迭代 167 budget 与 cost。
  - **限频**：每用户每工具默认 `30 req/min`，超过返回 `rate_limited`。
  - **当前落地说明**：已在 `app/services/quant_tools_runtime.py` 落地 MCP 风格元数据（`output_schema / auth_level / requires_confirmation / timeout_ms / rate_limit_per_user_per_min`）、最小 JSON Schema 子集校验、per-tool rate limit、admin 门控、timeout 保护、脱敏+4KB 截断审计，以及 `markets.get_history / portfolio_ledger.get_summary / risk.var_cvar / factor.evaluate / data_governance.endpoint_preview / data_topics.peek` 等首批工具；尚未进一步拆分为独立 `registry.py / schema.py / audit.py / confirmation.py` 文件。
  - 验收：`tests/test_quant_tools.py` 覆盖 schema validation、auth_level、超时、destructive guard、限频、审计写入；AI Chat 集成测试走 fake LLM 返回 tool call 验证闭环。

### 阶段八：前端集成、文档与验证（P0）

- [ ] **T18**: 前端 API 封装与路由
  - 新增 API 封装：`dataGovernance.ts`、`dataTopics.ts`、`brokers.ts`、`portfolioLedger.ts`、`equityResearch.ts`、`newsIntelligence.ts`、`optionsChain.ts`、`quantTools.ts`。
  - 新增或扩展页面：数据治理、Broker 管理、组合账本、股票研究、新闻情报、期权链。
  - 不追求复杂交易终端布局；先做可测试 MVP。

- [ ] **T19**: 文档
  - 新增 `docs/guides/DATA_CONNECTOR_REGISTRY.md`。
  - 新增 `docs/guides/BT_API_PY_BROKER_CONTRACT.md`。
  - 新增 `docs/guides/DATA_TOPIC_HUB.md`。
  - 新增 `docs/guides/PORTFOLIO_LEDGER.md`。
  - 更新 `.env.example`：新增可选 provider API key 变量占位，不提交真实 key。

- [ ] **T20**: 验证与回归
  - 后端：Ruff、mypy 范围至少覆盖新增 `app/schemas`、`app/services/data_connectors`、`bt_api_py/brokers`。
  - 后端测试：provider registry、DataTopicHub TTL、Broker adapter contract、portfolio ledger、news/option/scanner happy/degraded paths。
  - 前端测试：API wrapper URL/params/body、核心页面 smoke tests。
  - 避免单条长命令卡住；按模块分组运行，必要时使用 `pytest -n 8` 和 120s 超时脚本。

---

## 4. 子迭代拆分与执行顺序

**驱动原因**：20 个任务（含新增 T2.5 / T4.5 / T6.5，合计 23）一个迭代装下同步转交风险过大。参照迭代 166-169 子迭代的成功经验，拆为三个顺序子迭代：

### 170A：数据与 Broker 底座（P0、~2 周）

```text
T1 (许可证 + GAP 分析) → T2 / T2.5 (治理表) → T3 (执行器) → T4 (6 provider) → T4.5 (Instrument + RiskFree)
                                                                                          ↓
                                                                                       T6.5 (WS 网关)
                                                                                          ↓
                                                                                       T5 / T6 (DataTopicHub)
                                                                                          ↓
                                                                                       T7 / T8 / T9 (Broker 合约 + mock/paper/bridge 只读)
```

**170A 转交门槛**：验证 8.1 中「数据治理 + DataTopicHub + Mock Broker」二项可验收；MockBrokerAdapter 合约覆盖率 100%；许可证 review 签字。

### 170B：组合账本 + 股票研究 + 新闻情报（P0/P1、~2 周）

```text
T10 / T11 / T12 (Portfolio Ledger) → T13 (Equity Research) → T14 (News Intelligence)
                                                                       ↓
                                                            可选: PaperBroker 写路径、GatewayBridge 写路径
                                                            (必须双人审阅 + feature flag)
```

**170B 转交门槛**：Portfolio Ledger 能导入 1000 行 CSV 在 ≤2s、NAV 快照可调用 168 risk_analytics；Equity Research / News 页面可走 happy path。

### 170C：期权 / 扫描 / AI 工具化（P1、~1-2 周）

```text
T15 (Option Chain) ∥ T16 (Algo Scanner DSL) ∥ T17 (Quant Tool Registry)
         ↓
     T18 (前端) → T19 (文档) → T20 (验证与回归)
```

**170C 转交门槛**：AI Chat 能调用 ≥3 个只读工具且有 destructive 拒绝路径示例；Section 8.4 SLO 全部达标。

### 优先级总结

1. **P0必做**：170A 全部（T1-T9 + T2.5 + T4.5 + T6.5）、170B 中 T10-T12、所有 170C 的 T18-T20。
2. **P1 强烈建议**：T13/T14/T15/T16/T17（允许 170C 部分任务顺延迭代 171）。
3. **P2 延后**：完整 AI Quant Lab（Qlib/RDAgent/RL/HFT）、几十个 Broker 原生适配、复杂 Qt 风格桌面布局、移动端 / 云同步。

---

## 5. 架构落点

### 5.1 后端新增路径

```text
src/backend/app/models/
  data_governance.py        # T2.5 Dg* 中性化模型（复用原 akshare_mgmt 为兼容层）
  data_topic.py             # 可选、topic 纯内存时可不落库
  broker_profile.py
  portfolio_ledger.py
  news_intelligence.py
  option_chain.py
  instrument.py             # T4.5 Instrument Service

src/backend/app/schemas/
  data_governance.py
  data_topic.py
  broker.py
  portfolio_ledger.py
  equity_research.py
  news_intelligence.py
  option_chain.py
  quant_tools.py
  instrument.py
  risk_free_rate.py

src/backend/app/services/
  data_connectors/          # T3 executor + provider/endpoint loader
  data_topic_hub/           # T5/T6 registry/cache/publisher/scheduler/policy
  ws_gateway/               # T6.5 连接管理、订阅路由、metrics
  instruments/              # T4.5
  risk_free_rate/           # T4.5
  portfolio_ledger/
  equity_research/
  news_intelligence/
  options_chain/
  quant_tools/

src/backend/app/api/
  data_governance.py        # /api/v1/data-governance/*
  data_topics.py            # /api/v1/data-topics/* + /ws/data-topics/*
  brokers.py                # /api/v1/brokers/*
  portfolio_ledger.py       # /api/v1/portfolio-ledger/*（不与现 portfolio_api.py 冲突）
  equity_research.py
  news_intelligence.py
  options_chain.py
  scanners.py
  quant_tools.py
  instruments.py
  risk_free_rate.py
```

### 5.2 `bt_api_py` 新增路径

```text
src/bt_api_py/
  __init__.py
  brokers/
    __init__.py
    types.py
    base.py
    registry.py
    capabilities.py
    errors.py
    mock.py
    paper.py
    gateway_bridge.py
  testing/
    __init__.py
    contract_cases.py       # pytest 参数化 fixture
    fixtures.py             # mock 订单 / 行情 / 仓位 样例
  configs/                  # 现有、保留 ibkr_cookies.json
```

### 5.3 前端新增路径

```text
src/frontend/src/api/
  dataGovernance.ts
  dataTopics.ts
  brokers.ts
  portfolioLedger.ts
  equityResearch.ts
  newsIntelligence.ts
  optionsChain.ts
  quantTools.ts

src/frontend/src/views/data/
  DataConnectorRegistryPage.vue
  DataTopicHubPage.vue

src/frontend/src/views/
  BrokerProfilesPage.vue
  PortfolioLedgerPage.vue
  EquityResearchPage.vue
  NewsIntelligencePage.vue
  OptionsChainPage.vue
```

---

## 6. 数据模型原则

### 6.1 数据接口入库原则

- Provider 是数据供应商或脚本族，不等于单个接口。
- Endpoint 是可执行接口，必须声明参数 schema、认证方式、限频和缓存。
- Job 是一次执行记录，必须可重试、可取消、可恢复、可审计。
- 目标表必须显式声明，不允许执行器根据外部返回随意建表。
- 对大型表同步必须记录主键/唯一键策略，避免全列比较导致卡死。

### 6.2 Broker API 原则

- `bt_api_py` 是实盘 API 合约和适配层的唯一归属。
- backend 不直接依赖某个券商 SDK，只依赖 `bt_api_py.brokers.base.BrokerAdapter`。
- 下单前必须经过风险守卫、权限检查和显式确认。
- 所有实盘状态流通过 DataTopicHub 暴露，不由页面直接轮询 SDK。

### 6.3 AI 工具原则

- 默认只读。
- 每个工具有 schema validation、auth_level、timeout、audit。
- 交易、删除、写库等 destructive 工具必须 `ExplicitConfirm`。
- 工具结果不应泄露 secrets、原始凭证或未脱敏账户信息。

---

## 7. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| **Fincept AGPL-3.0 使用越界**（项目进入商业/SaaS 后后发现依赖了带 AGPL 限制的文件） | 法律响应 + 产品需重写 | 0.2 两人 clean-room + LICENSE_AUDIT.md 台账 + T1 后法律 checkpoint；SaaS 升级额外商业许可谈判 |
| **现有 `portfolio_api.py` 路由冲突** | API 破坏、前端不可用 | T11 明确切到 `/api/v1/portfolio-ledger/*`；增加 `test_backward_compat_iter170.py` |
| **WebSocket 网关缺失导致 DataTopicHub fan-out 重复造轮** | 架构倒退 | T6.5 抽取 `ws_gateway`；现有 6 处 WS 代码不动，仅新能力走网关 |
| **数据同步卸死**（迭代 128 发生过） | 质量下降 | T2 强制 endpoint 声明 `incremental_sync_key`；>100k 表拒绝全列比较兑底 |
| **Broker 凭证泄露** | 资金损失 | T9 双重保护：env 变量名引用 + 响应脱敏 `***LAST4` + 90 天轮换提醒 + destructive double-confirm |
| **实盘 Broker 适配影响现有网关** | 实盘风险 | T8 GatewayBridge 首期仅连接读接口；写路径需 `BT_API_PY_BRIDGE_ENABLE_WRITE=1` feature flag |
| **20+ 任务一迭代装不下** | 迭代动荡 / 进度逾期 | Section 4 拆为 170A/170B/170C 三子迭代，每个子迭代独立可发布 |
| **验收命令卡住**（AGENTS.md 明确 cancel-twice 重写规则） | 人手浪费 | 8.2 重构为带 120s 超时脚本包装、每组 ≤ 10 分钟 |
| **数据源过多导致迭代失控** | 交付延期 | 首批 6-8 个 provider，机制优先，连接器数量延后 |
| **`sync_service.py` 已很大** | 可维护性下降 | 新增 `data_connectors/` 与 `data_topic_hub/`，不继续塞进 `sync_service.py` |
| **外部接口限频/不稳定** | 用户体验差 | TopicPolicy.min_interval + max_requests_per_sec + degraded 响应 + provider health |
| **新闻/AI 摘要成本失控** | 成本风险 | 接入迭代 167 AI budget；news cluster_id 同序合并调用；默认规则分类优先 |
| **期权 Greeks 依赖复杂** | 安装风险 | 纯 Python BSM fallback，可选 `py_vollib`；每 strike 1/500ms 节流 |

---

## 8. 验收标准

### 8.1 功能验收

- 数据治理页面能看到多个 provider，至少 6 个 provider 有接口元数据。
- 任一数据 endpoint 可预览、异步入库、查看执行历史。
- DataTopicHub 支持 peek/refresh/WebSocket subscribe，并能服务 quote/history topic。
- `bt_api_py` 有可运行的 mock broker contract tests。
- 后端下单/查询路径至少有一条通过 `bt_api_py` adapter bridge。
- Portfolio Ledger 支持创建组合、导入交易、生成持仓和 NAV 快照。
- Equity Research 能查询 symbol 的 quote/info/history/technicals 基础数据。
- News Intelligence 能管理 RSS 源、拉取文章、展示情绪/影响/摘要。
- Option Chain 能返回链、PCR、max pain、基础 Greeks。
- Quant Tool Registry 能被 AI Chat 以只读方式调用至少 3 个工具。

### 8.2 技术验收（全部分组执行、包 120s 超时，AGENTS.md cancel-twice 规则适用）

首推脚本包装器 `scripts/run_iter170_checks.py`（在 T1 编写）：每个命令独立 subprocess + 120s timeout + 超时 SIGTERM 后 SIGKILL。手动验证时按 170A/B/C 分组跑：

```bash
# 后端、工作目录 src/backend、每条 < 120s

# 170A 底座
ruff check app/models/data_governance.py app/services/data_connectors app/services/data_topic_hub app/services/ws_gateway app/services/instruments app/services/risk_free_rate
mypy app/services/data_connectors app/services/data_topic_hub app/services/ws_gateway
pytest tests/test_data_governance_compat.py tests/test_data_connectors.py tests/test_data_topic_hub.py tests/test_ws_gateway.py tests/test_instruments_service.py tests/test_risk_free_rate.py -n 8 --tb=short --timeout=60

# bt_api_py 合约
ruff check src/bt_api_py
pytest tests/test_broker_contract.py -n 4 --tb=short --timeout=60
# MockBrokerAdapter coverage 需在独立 bt_api_py 仓执行；当前 src/backend/.coveragerc 仅统计 app

# 170B 组合 + 股票研究 + 新闻
ruff check app/services/portfolio_ledger app/services/equity_research app/services/news_intelligence app/api/portfolio_ledger.py app/api/equity_research.py app/api/news_intelligence.py
pytest tests/test_portfolio_ledger.py tests/test_equity_research.py tests/test_news_intelligence.py -n 8 --tb=short --timeout=60

# 170C 期权 + 扫描 + AI 工具
ruff check app/services/options_chain app/services/quant_tools app/api/options_chain.py app/api/scanners.py app/api/quant_tools.py
pytest tests/test_options_chain.py tests/test_scanners.py tests/test_quant_tools.py -n 8 --tb=short --timeout=60

# 向后兼容守门
pytest tests/test_backward_compat_iter170.py -n 4 --tb=short --timeout=60

# 前端、工作目录 src/frontend
npm run test -- src/test/api/iteration170.test.ts --run
npm run test -- src/test/views/PortfolioLedgerPage.test.ts src/test/router/index.test.ts src/test/components/common/AppLayout.test.ts --run
npm run typecheck
```

### 8.2.1 本轮有界验证记录（2026-05-26）

- 后端新增切片：`python` 包装器运行 `pytest tests/test_data_topic_hub.py tests/test_broker_contract.py tests/test_data_governance_compat.py tests/test_instruments_service.py tests/test_risk_free_rate.py tests/test_ws_gateway.py tests/test_portfolio_ledger.py tests/test_equity_research.py tests/test_news_intelligence.py tests/test_options_chain.py tests/test_scanners.py tests/test_quant_tools.py tests/test_backward_compat_iter170.py -q --tb=short`，**23 passed**。
- 向后兼容守门回放：`python` 包装器运行 `pytest tests/test_backward_compat_iter170.py -q --tb=short`，**1 passed**。
- Broker contract 守门回放：`python` 包装器运行 `pytest tests/test_broker_contract.py -q --tb=short`，**2 passed**；`bt_api_py.brokers.mock` 当前来自 editable 独立仓 `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py`，且 `src/backend/.coveragerc` 的 `source=app` 仅统计 backend `app` 包，因此 `backtrader_web` 仓内不再把 `--cov=bt_api_py.brokers.mock` 视作稳定验收命令。
- 独立 `bt_api_py` coverage 守门回放：在 `/Users/yunjinqi/Documents/new_projects/bt_api/bt_api_py` 新增 `tests/test_broker_contract.py` 最小 contract smoke 后，执行 `pytest tests/test_broker_contract.py --cov=bt_api_py.brokers.mock --cov-report=term-missing -q --tb=short`，**10 passed，MockBrokerAdapter 100.00% coverage**。
- 后端静态检查：`python -m ruff check ...`（覆盖新 API / service / model / tests），**All checks passed**。
- 前端最小入口验证：`npm run test -- src/test/api/iteration170.test.ts src/test/views/PortfolioLedgerPage.test.ts src/test/router/index.test.ts src/test/components/common/AppLayout.test.ts --run`，**47 passed**。
- 前端类型检查：`npm run typecheck`，**通过**。
- 独立 `bt_api_py` 烟测：执行 `MockBrokerAdapter` + `run_broker_contract_cases` 返回 `passed=True`，`GatewayBridgeAdapter.health()` 返回 `adapter='gateway_bridge'`，说明当前环境已可从 `backtrader_web` 导入新 broker contract 子包。
- 8.4 / 170C 收口验证：`python` 包装器运行 `pytest tests/test_options_chain.py tests/test_news_classifier.py tests/test_quant_tools.py tests/perf/test_data_topic_hub_perf.py tests/perf/test_ws_gateway_perf.py tests/perf/test_portfolio_import_perf.py tests/perf/test_option_pricing_perf.py -q`，**12 passed**；benchmark 表输出覆盖 DataTopicHub `peek/fan-out`、WS gateway broadcast、portfolio import、single-strike greeks。
- 170C 前端补强验证：`npm run test -- src/test/api/iteration170.test.ts src/test/views/PortfolioLedgerPage.test.ts src/test/views/ScannerPage.test.ts src/test/views/OptionsChainPage.test.ts src/test/views/QuantToolsPage.test.ts --run`，**9 passed**。

### 8.3 文档验收

- `docs/guides/DATA_CONNECTOR_REGISTRY.md` 覆盖 provider/endpoint/job/quality rule。
- `docs/guides/BT_API_PY_BROKER_CONTRACT.md` 覆盖 adapter contract、错误码、凭证处理、安全确认。
- `docs/guides/DATA_TOPIC_HUB.md` 覆盖 topic 命名、TTL/coalesce/push_only/drop_on_idle、刷新、WebSocket、degraded 状态。
- `docs/guides/PORTFOLIO_LEDGER.md` 覆盖组合账本、交易导入、快照、指标口径、risk-free rate 来源。
- `docs/guides/QUANT_TOOL_REGISTRY.md` 覆盖工具 schema、auth_level、destructive guard、MCP 未来兼容路径。
- `docs/architecture/FINCEPT_LICENSE_AUDIT.md` 及同名 `LICENSE_REVIEW.md` 覆盖每个借鉴能力。
- `.env.example` 只包含 key 名称占位，不包含真实 secret；新增 `RISK_FREE_RATE_DEFAULT`、`BT_API_PY_BRIDGE_ENABLE_WRITE`、`BT_BROKER_<ALIAS>_KEY` 示例。

### 8.4 量化 SLO / 验收指标（必须达成才能关闭子迭代）

| 指标 | 阈值 | 量度方式 |
|---|---|---|
| DataTopicHub `peek` p95 | ≤ 5ms（缓存命中、不触发外部调用） | `tests/perf/test_data_topic_hub_perf.py` 使用 pytest-benchmark |
| DataTopicHub fan-out p95 | ≤ 20ms / 100 订阅者 | 同上 |
| WebSocket gateway broadcast p95 | ≤ 50ms / 500 连接 | `tests/perf/test_ws_gateway_perf.py` |
| Broker MockAdapter 合约套件覆盖率 | 100% 方法 + 能力位 | 在独立 `bt_api_py` 仓执行 `pytest --cov=bt_api_py.brokers.mock` |
| Portfolio Ledger CSV 导入 1000 行 | ≤ 2s | `tests/perf/test_portfolio_import_perf.py` |
| News Sentiment 规则引擎准确率 | ≥ 70%（标注 200 样本） | `tests/test_news_classifier.py` + golden 集 `data/news_labelled_200.csv` |
| Option `max_pain` 计算误差 | ± 1 strike（对比手算样例） | `tests/test_options_chain.py::test_max_pain_against_manual` |
| Option BSM Greeks 单 strike 耗时 | ≤ 500ms | `tests/perf/test_option_pricing_perf.py` |
| Quant Tool 每用户限频 | 30 req/min 后 `429` | `tests/test_quant_tools.py::test_rate_limited` |
| 向后兼容验收 | 所有旧路由 200 OK 且响应字段集 ⊇ 迁移前 | `tests/test_backward_compat_iter170.py` |
| AI Chat 调用只读工具闭环 | ≥3 个工具可调 | `tests/test_quant_tools.py::test_chat_integration` |
| **许可证 review** | LICENSE_REVIEW.md 由实施人签字 | 文档检查 |

> **当前状态补充**：本轮已补齐 `tests/perf/test_data_topic_hub_perf.py`、`tests/perf/test_ws_gateway_perf.py`、`tests/perf/test_portfolio_import_perf.py`、`tests/perf/test_option_pricing_perf.py`、`tests/test_news_classifier.py` 与 `data/news_labelled_200.csv`，`tests/test_backward_compat_iter170.py` 已重新回放，且独立 `bt_api_py` 仓的 `MockBrokerAdapter` coverage gate 已通过 `tests/test_broker_contract.py` 收口到 **100.00% coverage**。

---

## 9. 不纳入本迭代

1. Qt 桌面端构建、C++ 代码编译、桌面安装包。
2. FinceptTerminal 全量 250+ Python scripts 迁移。
3. Qlib/RDAgent/RL/HFT 完整 AI Quant Lab；本迭代只做工具注册和部分只读模块入口。
4. 16 个券商全部原生适配；本迭代先做标准合约、mock/paper/bridge。
5. 自动实盘交易策略部署；条件扫描结果只作为候选，不自动下单。
6. 付费数据源默认启用；需要 API key 的 provider 默认 disabled。
7. 多租户、计费、订阅等级、token/wallet 经济系统。

---

## 10. 后续迭代建议

- **迭代171**：承接 170 中仍停留在 MVP / placeholder / in-memory / hard-coded 层的 Fincept 能力，重点包括：`Data Connector Registry` 产品化、`Portfolio Ledger` 持久化与分析接入、`Equity Research / News Intelligence / Options Chain / Scanner` 从 demo/MVP 提升为真实产品能力，以及补齐 `FINCEPT_TERMINAL_GAP_ANALYSIS.md` 与 `WS_GATEWAY_MIGRATION.md` 并启动现有 WS 路由向 `ws_gateway` 的逐项迁移；`broker` 相关深化迁移转由 `bt_api_py / bt_api_xx` 生态承接，不在 `backtrader_web` 内继续扩 broker 平台。
- **迭代172**：`bt_api_xx` 首批 14 个券商扩展包落地，优先完成 `Tradier / Saxo / Zerodha / Upstox / Angel One / Fyers / Dhan / Shoonya / AliceBlue / 5paisa / IIFL / Kotak / Motilal / Groww` 的独立包规划与分批实现，主实施仓为独立 `bt_api` 生态，`backtrader_web` 只保留消费边界与文档协同。
- **迭代173**：Qt 桌面应用可行性评估与 UI 复刻路线，基于稳定后的 Web 产品能力选择是否建设桌面端。
- **迭代174**：另类数据与全球宏观情报（地缘、航运、卫星、政府开放数据）产品化。
- **迭代175**：删除 `ak_*` 表（取消 T2.5 双写兼容层），完全切到 `dg_*`。

---

## 11. TDD / 验证协议（每个任务必走）

每个 T 任务在编码前必须经历 RED → GREEN → REFACTOR 三步，结果以脚本输出形式留痕于 PR description。

### 11.1 任务模板

```
任务: T<N>
模块: app/services/<module>/  +  app/api/<module>.py  +  tests/test_<module>.py

[RED]    先写 tests/test_<module>.py 中的关键断言；运行：
         pytest tests/test_<module>.py -n 4 --tb=short --timeout=60
         期望：失败（缺少实现）

[GREEN]  写最小实现让所有断言通过；运行同一条 pytest 命令；期望全绿

[REFACTOR] 跑 ruff + mypy + 性能基线（如有 SLO）；提交 PR；
           PR 模板填写「RED 失败截断」「GREEN 通过截断」「REFACTOR 静态检查」三段
```

### 11.2 强制项

1. **不得跳过 RED**：先有失败断言再写实现；防止 happy path 假绿。
2. **不得删除已有测试**：迭代 165 规则。如必须改动现有断言，需在 PR 中以「测试契约更新」标签解释。
3. **每条 pytest 命令必须能在 120s 内结束**；否则改为按测试类切分或 `--collect-only` 先确认范围。
4. **AGENTS.md cancel-twice 规则**：同一条命令被用户取消两次以上 → 立即重写命令、缩小范围、或换成 Python 脚本。
5. **新增 ORM 模型必须配 Alembic 迁移 + ensure_schema_compatibility 兜底**（对齐迭代 167/168 实践）。
6. **新增 API 必须配前端 API wrapper + Vitest URL/params/body 测试**（对齐迭代 168 quantResearch 实践）。
7. **新增依赖必须先评估是否可作为可选依赖**：例如 py_vollib、feedparser；写入 `pyproject.toml` 的 `[project.optional-dependencies]`，并提供 fallback。

### 11.3 评审 checklist（PR 模板）

- [ ] 任务 ID + 子迭代 (170A/B/C)
- [ ] 已运行 RED → GREEN → REFACTOR 三段并粘贴输出尾部
- [ ] 文档变更（guides / iteration index 状态行）
- [ ] 向后兼容回归测试通过
- [ ] 涉及 Fincept 借鉴的，已在 `FINCEPT_LICENSE_AUDIT.md` 添加一条
- [ ] 涉及 secret 的，已检查 `.env.example` 与日志脱敏
- [ ] 涉及 SLO 的，性能基线脚本已运行并在 PR 中贴指标

---

## 12. 决策日志 / 未决问题

### 12.1 已决策（本计划默认采纳）

| ID | 决策 | 理由 |
|---|---|---|
| D-1 | 不构建 Qt 桌面端 | 用户明确要求；Qt 不在 Web 架构中带来收益 |
| D-2 | 实盘接口归口 `bt_api_py` | 用户明确要求；与 backend 解耦 |
| D-3 | 数据接口元数据全部入库 | 用户明确要求；可治理化 |
| D-4 | Fincept 代码 clean-room，禁止 copy-paste | LICENSE 第 47-49 行 |
| D-5 | 拆 170A/170B/170C 三个子迭代 | 20+ 任务一迭代风险过大 |
| D-6 | 新组合账本走 `/api/v1/portfolio-ledger/*` | 与现有 `portfolio_api.py` 解耦 |
| D-7 | DataTopicHub 走新 `ws_gateway`，现有 6 处 WS 不动 | 控制 blast radius |
| D-8 | Quant Tool Registry schema 采用 MCP 兼容 JSON Schema | 未来可暴露 MCP，零成本前置 |
| D-9 | Bridge 写路径默认 NotImplementedError，需 feature flag | 资金安全 |
| D-10 | 首批 6-8 个 provider；100+ 数据源后续逐步加 | 控制范围 |

### 12.2 待用户确认（建议在 T1 前回应）

| ID | 问题 | 选项 |
|---|---|---|
| Q-1 | 是否在 170A 内强制启用 `dg_*` 写路径并冻结 `ak_*` 写入？ | A. 立即冻结（推荐，避免双写）；B. 双写 1 个迭代过渡 |
| Q-2 | RiskFreeRateService 默认基准是 FRED DGS10 (USD)。CNY 应使用什么基准？ | A. 中债 10Y（无公开免费 API，需 connector）；B. 沿用 USD 0.04 兜底；C. 用户在 `.env` 设 `RISK_FREE_RATE_CNY_DEFAULT` |
| Q-3 | News 拉取首批默认源是否包含付费 RSS？ | A. 仅免费源（推荐）；B. 包含付费但默认 disabled |
| Q-4 | Option Chain 国内市场首批支持哪个交易所？ | A. 仅上交所/深交所 ETF 期权（AkShare 可拉）；B. 加 50ETF + 300ETF + 沪深 300 股指期权 |
| Q-5 | Quant Tool 的 `confirmation_token` UI 表现形式？ | A. 弹窗 + 二次确认按钮；B. 命令行式 `/confirm <hash>`；C. 双因素验证（OTP） |
| Q-6 | 是否计划在 170 结束后即将 `ak_*` 表删除？ | A. 175 删除（推荐）；B. 永久保留 |
| Q-7 | 现有 WS 6 处迁移到 `ws_gateway` 的优先级排序？ | A. realtime_data > paper_trading > monitoring > 其它；B. 用户自定义 |

### 12.3 风险跟踪表（每周更新）

| 项 | 当前状态 | 负责人 | 下一步 |
|---|---|---|---|
| Fincept LICENSE_AUDIT 台账 | 未启动 | 待分配 | T1 期间建立 |
| WS gateway 设计文档 | 未启动 | 待分配 | T6.5 前完成 |
| Instrument seed CSV | 未启动 | 待分配 | T4.5 前导入 AkShare 现存符号 |
| RiskFreeRateService FRED key | 未申请 | 待分配 | T4.5 前申请并写 `.env.example` |
| Broker 凭证策略评审 | 未启动 | 待分配 | T9 前与运维 + 安全评审 |
