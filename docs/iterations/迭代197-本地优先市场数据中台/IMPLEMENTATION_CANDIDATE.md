# 迭代 197 候选实现与验收状态

> 记录日期：2026-09-10<br>
> 文档性质：当前 `dev` 候选实现审计，不是生产发布证明。<br>
> 设计基线：迭代 196 已冻结并已接入 `dev`；本候选尚未进入 release 签收，本文件不解除真实数据、数据库、浏览器和部署验收闸门。

## 1. 阅读规则和状态含义

本文件把当前 `dev` 候选中已经存在的实现，与尚未完成的真实环境验收明确分开。`DONE` 只表示候选代码和其定向自动化验证已具备，不表示迁移、真实来源、生产数据库、浏览器 E2E 或策略工件验收已经完成。

| 状态 | 含义 |
| --- | --- |
| `DONE` | 当前候选已有实现和对应离线/定向测试证据；仍可能有外部验收未运行。 |
| `IN_PROGRESS` | 已有基础或局部接线，但尚缺一个可安全启用的完整闭环。 |
| `NOT_CONFIGURED` | 有明确数据合同或需求，但没有经批准的 source policy/route；页面必须显示未配置，不得猜测回退。 |
| `BLOCKED` | 必须等待真实环境授权、外部服务或尚未实现的数据模型；不把本地候选代码当作解除条件。 |
| `NOT_RUN` | 本次没有在真实 AkShare/OpenBB、共享数据库、浏览器或生产环境中执行；不能从 fixture、静态审计或历史日志推断成功。 |

历史候选提交后的复核曾发现一项 PIT 回放测试不确定性：测试使用虚构的 13:00 cutoff，却让 publication 使用真实时钟，记录正确地在该 cutoff 后才可见。历史候选提交 `c474a57b` 仅为该测试注入固定的可信 publication clock，未改变生产语义。随后对 `tests/market_data_platform`、`tests/test_config.py`、`tests/test_market_instrument_api.py` 和 `tests/test_market_instrument_freshness.py` 的最终组合离线运行报告为 `357 passed, 32 warnings in 76.18s`；历史候选提交 `20e214dd` 已格式化当时引入的 9 个文件，Ruff 格式和规则检查通过，Alembic head 为 `20260908_market_data_shared_dataset_bindings`。当时的前端相关验证按文件串行运行：`marketData.test.ts` 为 `12 passed`，`DataPage.test.ts` 为 `28 passed`，`StrategyPage.test.ts` 为 `100 passed`；`npm run typecheck` 与 `npm run build` 均通过。后端 warnings 来自已安装 Backtrader、Alembic 配置和 Starlette 的弃用提示；前端构建仍报告 Browserslist 数据陈旧及既有大 chunk 警告。以上 SHA、分支、计数和结论均是历史快照，**不覆盖本次 completion candidate 的 capability、cache-fill 或策略 bridge 增量**；该增量必须在冻结候选上按 [验收文档](ACCEPTANCE.md#4-必须执行的自动化回归) 复跑后才能记入新的执行记录。它们都不将本地结果升级为全量、真实数据或生产验收。

## 2. 候选实现总览

| 能力 | 候选状态 | 当前证据和边界 | 真实验收状态 |
| --- | --- | --- | --- |
| 精确 identity、catalog、canonical series、revision、publication/read-back | `DONE` | 候选实现采用规范化 `md_*` 模型、不可变来源快照、发布回读与 PIT 可见性边界。 | `NOT_RUN`：未在共享 MySQL/PostgreSQL 实例执行迁移和恢复演练。 |
| local-first 查询、singleflight、严格 PIT 和 cursor | `DONE` | 候选实现读取本地覆盖；已包含 follower 事务回滚后重读、refresh 不复用 local-first follower 的回归。 | `NOT_RUN`：未做真实并发、多进程、故障恢复压测。 |
| bars 的 AkShare 显式 route registry | `DONE` | 仅允许经审核的精确标的/市场/频率路线；拒绝 sample、邻近标的和隐式 provider fallback。 | `NOT_RUN`：没有真实 AkShare 账户/网络/限流/字段漂移验收。 |
| OpenBB 隔离 subprocess runner | `DONE` | JSON DTO、环境白名单、输出上限、超时进程组清理、raw payload 与规范化 records 的确定性投影均在候选中覆盖；父进程只接受绝对 Python + `-I -S` + 绝对 runner 脚本，runner 在 manifest/metadata/import 前 fail closed。重复字段、投影不一致与进程内过载稳定拒绝。协议候选只建模 bars；当前 permit matrix 为空，**没有**启用的 OpenBB route。 | `NOT_RUN`：未在 operator-owned OpenBB 环境、真实 extension、许可和凭据下执行；上限只覆盖单个 Python 进程，且 Python 启动参数不是 OS/容器隔离证明。 |
| quote snapshot local-first 覆盖 | `DONE` | `SnapshotCoveragePlanner` 已避免把 quote 强行塞入交易日历；产品 SLA 以 `source_policy_version` 锚定，quote 响应会隐藏超过该 policy freshness 的记录。 | `NOT_RUN`：真实 snapshot feed、七资产 identity 映射和 freshness 行为尚未在真实来源验证。 |
| F1 市场页控制面 | `DONE`（L-197-15，本地候选） | 已认证 capability 文档是 v2/bundle 唯一前端开关；有效 bundle 中 `unconfigured/not_applicable` 不走 legacy lookup，旧服务明确兼容错误才走无 bundle v2。静止候选的 capability API、cache 矩阵、选择器竞态和页面 v2 回归已通过。 | `NOT_RUN`：未在浏览器、真实后端、真实数据状态下 E2E。 |
| F1 策略页严格本地预检 | `DONE`（L-197-15，本地候选） | 普通预检只读 `local_only + research + strict`；只有显式缓存补齐受 `query_v2 + online_fetch + cache_fill` 有效 capability 控制，独立于 bridge，成功后允许 strict 本地 v2 复读但不产生工件。bridge marker 从同一次提交的 symbol 快照派生，bridge 禁用时在同步/异步持久化前失败关闭；同步/异步拒绝与研究链全量回归已通过。 | `NOT_RUN`：未在真实数据、浏览器和部署环境完成工件回放。 |
| F2 quote/valuation/settlement/NAV/reference | `IN_PROGRESS` | `stock.liquidity`、`fund.liquidity`、`fund.nav` 和 `fx.range` 已具 request-time 候选 contract/route；其中 NAV 仅为 CN ETF 日线源报告净值。A 股估值已落地为默认关闭的私有 `market.stock_valuation_captured_snapshot / valuation_snapshot / snapshot` 离线批次 collector：无 fetch/HTTP/route/public family，精确 capture instant、封装 hash、quarantine 与写前证据预算均有本地回归。公开 `stock.valuation` 仍未配置。其余 quote、valuation、settlement、宽表 importer 和多记录产品保持 fail-closed。 | `NOT_RUN`：没有真实采集、回填或页面灰度验收。 |
| 共享 binding migration 与 server capability 代码整合 | `DONE`（代码整合） | 196/197 migration chain 与 binding consumer 已进入集成基线；server capability 接线不改变默认关闭状态。真实回填、页面灰度和生产开关不属于这一行的完成声明。 | `NOT_RUN`：未在可恢复真实数据库、页面灰度或生产部署执行。 |

## 3. 当前 21 个页面数据族

“当前候选”描述 `market-data-family-bundle-v1` 的实际控制面状态。`*.realtime` 中的 `DONE（bars 兼容）` 只代表有 `market.bars` 的日/周/月 K 线兼容桥，不代表该页面已经有真实 quote snapshot。

第 2 节所列离线 schedule/shadow snapshot importer 的 `IN_PROGRESS` 只表示通用离线基础设施已存在；它不会把下表任何 `NOT_CONFIGURED` family 变成已批准的 provider route，也不构成真实采集或页面可用性证据。

| family | 当前候选合同/状态 | F2 预期产品 | F2 实施状态 | 当前不能宣称的能力 |
| --- | --- | --- | --- | --- |
| `stock.realtime` | `DONE`：`market.bars` / `bars` / 1d、1w、1mo | `market.quote_snapshot` / snapshot | `NOT_CONFIGURED` | 实时逐笔/盘口或源 tick 时间。 |
| `stock.valuation` | `NOT_CONFIGURED`：`market.valuation` / reference / 1d | 市值、PE、PB、`as_of`（公开合同仍未配置） | 私有 `market.stock_valuation_captured_snapshot / valuation_snapshot / snapshot` collector 已完成离线候选与 139 条聚焦回归；`event_at` 仅为精确 `collector_observed` capture instant，无 source `as_of`，无 public family/route/page | 将私有批次、历史 bars 或 collector 时间表述为实时、日线完整覆盖、来源 `as_of` 或页面可用。 |
| `stock.liquidity` | `DONE`（候选 `ready`）：`market.liquidity` / reference series / 1d | volume、turnover、turnover rate | 候选 exact route；已执行真实零行子用例为 `FAIL`，其余真实验收仍 `NOT_RUN` | 真实来源、完整覆盖或写回已经通过。 |
| `futures.realtime` | `DONE`：`market.bars` / 1d | `market.quote_snapshot` / snapshot | `NOT_CONFIGURED` | 现货 bid/ask、当前 OI。 |
| `futures.settlement` | `NOT_CONFIGURED`：`market.settlement` / reference / 1d | settle、previous settle、OI | `IN_PROGRESS`：legacy bridge 设计 | 不带 `MARKET` 的旧表查询或由日线猜昨结。 |
| `futures.inventory` | `NOT_CONFIGURED`：`market.inventory` / inventory report | 仓单、库存、交割数量 | `NOT_CONFIGURED` | 将不同来源库存/仓单拼成一条报告。 |
| `bond.realtime` | `DONE`：`market.bars` / 1d | `market.quote_snapshot` / snapshot | `NOT_CONFIGURED` | 一般债券实时行情。 |
| `bond.orderbook` | `NOT_CONFIGURED`：`market.quote_snapshot` / snapshot | bid、ask、volume、turnover | `NOT_CONFIGURED` | 以可转债宽表冒充全部债券 order book。 |
| `bond.fixed_income` | `NOT_CONFIGURED`：`market.bond_reference` / reference / 1d | YTM、coupon、maturity | `NOT_CONFIGURED` | 用短名称或收益率曲线当单券 reference。 |
| `fund.realtime` | `DONE`：`market.bars` / 1d、1w、1mo | ETF `market.quote_snapshot` | `NOT_CONFIGURED` | 开放式基金 NAV 或实时 ETF quote。 |
| `fund.liquidity` | `DONE`（候选 `ready`）：`market.liquidity` / reference series / 1d | ETF volume、turnover | 候选 exact route；真实验收 `NOT_RUN` | 用 NAV 模拟成交量，或将真实来源误称为验收通过。 |
| `fund.nav` | `DONE`（候选 `ready`）：`market.fund_nav` / reference series / 1d | CN ETF 的 unit NAV、cumulative NAV、daily growth | `fund_etf_fund_info_em` 候选 exact route；真实验收 `NOT_RUN` | 直接把 ETF K 线当 NAV，或扩大为开放式基金宽表采集。 |
| `option.realtime` | `DONE`：`market.bars` / 1d | contract `quote_snapshot` | `NOT_CONFIGURED` | 实时报价或期权链。 |
| `option.derivative` | `NOT_CONFIGURED`：`market.option_chain` / snapshot | chain、IV、OI、strike、expiry | `NOT_CONFIGURED` | 以单合约或宽表的部分字段宣称全链。 |
| `option.risk_surface` | `NOT_CONFIGURED`：`market.option_risk_surface` / snapshot | IV、Greeks、model version | `NOT_CONFIGURED` | 用单个 IV 或无模型版本值构造风险面。 |
| `fx.realtime` | `DONE`：`market.bars` / 1d | `market.quote_snapshot` | `NOT_CONFIGURED` | 交易所/报价源实时 FX quote。 |
| `fx.macro_fx` | `NOT_CONFIGURED`：`market.fx_reference` / reference / 1d | official/central rate reference | `NOT_CONFIGURED` | 将中间价混作交易 FX pair。 |
| `fx.range` | `DONE`（候选 `ready`）：`market.bars` / 1d | exact FX OHLC range | 候选 exact route；真实验收 `NOT_RUN` | 周/月/分钟或未验证的 pair mapping。 |
| `crypto.realtime` | `NOT_CONFIGURED`：`market.quote_snapshot` / snapshot | venue/pair quote | `NOT_CONFIGURED` | 无 venue、base、quote 映射的通用加密行情。 |
| `crypto.cme_position` | `NOT_CONFIGURED`：`market.position_report` / report | long、short、net、OI | `NOT_CONFIGURED` | 将 CME 比特币成交量报告称为持仓报告。 |
| `crypto.range` | `NOT_CONFIGURED`：`market.bars` / 1d | approved provider historical bars | `NOT_CONFIGURED` | AkShare 或 OpenBB 的无配置全局 fallback。 |

## 4. F2 数据来源分级结论

### 4.1 可以作为 request-time exact fallback 的路线

这些 route 必须仍经 catalog、identity、source policy、provider receipt、publication 和本地回读，不是允许页面直接调用 AkShare。

| F2 family | 方法 | 必要 identity 和时间语义 | 设计状态 |
| --- | --- | --- | --- |
| `stock.liquidity` | `ak.stock_zh_a_hist(symbol, period, start_date, end_date, adjust)` | 精确 CN-SSE/SZSE listing + response code；交易日 close；`1d`。 | `DONE`（候选 `akshare-stock-liquidity-primary-v1`）；真实 route 验收仍 `NOT_RUN`，且历史零行子用例保留 `FAIL`。 |
| `fund.liquidity` | `ak.fund_etf_hist_em(symbol, period, start_date, end_date, adjust)` | 精确 ETF listing + CN venue；`1d`。 | `DONE`（候选 `akshare-fund-liquidity-primary-v1`）；真实 route 验收 `NOT_RUN`。 |
| `fund.nav` | `ak.fund_etf_fund_info_em(fund, start_date, end_date)` | 精确 CN-SSE/CN-SZSE ETF `LISTING`；冻结 identity 必须为 `product_type=ETF` 与 `fund_identity_kind=LISTING`，半开窗口转换为来源包含式日期；`nav/cumulative_nav/daily_growth_rate`；`source_reported + nav + CNY + fund_share`。 | `DONE`（候选 `akshare-fund-nav-primary-v1`）；policy、compatibility bridge 和 adapter 均在 I/O 前拒绝 LOF、REIT、share class 或缺失身份；真实 provider → store → `local_only` 验收 `NOT_RUN`。 |
| `fx.range` | `ak.forex_hist_em(symbol)` | 精确 provider code 与 frozen FX pair mapping；只批准 `1d`。 | `DONE`（候选 route）；真实 route 验收 `NOT_RUN`。 |

现有 bars compatibility 路线也属于候选 `DONE` 范围，但只覆盖其已声明的精确 asset、venue、频率和字段；它们不自动扩大为 F2 quote、valuation、settlement、NAV 或 report 能力。

### 4.2 只能作为 scheduled collector importer 的宽表来源

宽表没有单标的 provider 请求形状，不能塞进当前 `MarketDataProviderRequest`，更不能在每个页面请求中重复抓取整个市场。候选中已有离线 schedule/shadow snapshot importer，但它尚未配置任何 approved `feed_id`、provider route 或网络调用；因此不是已启用采集能力。真正启用前仍需服务端 `feed_id`、feed-level singleflight、身份映射冻结、payload/row 上限、未知行 quarantine、raw snapshot 证据和发布后本地回读。

| 来源 | 方法和关键 source key | 可规划的产品 | 当前状态 |
| --- | --- | --- | --- |
| A 股宽表 | `stock_zh_a_spot_em()`；`代码`，无输出交易所和逐行时间 | stock quote、stock valuation | `IN_PROGRESS`：仅估值的私有离线 collector 已落地，输入必须是已捕获批次；固定 envelope/hash、冻结 `(venue, code)` mapping、`collector_observed` capture instant、unknown quarantine、2 MiB/10 MiB/16-target 写前边界、共享 UTF-8 BLOB 引用和 durable-prefix 语义均有本地回归。它没有 provider route 或网络调用，公开 `stock.valuation` 保持 `NOT_CONFIGURED`。 |
| ETF 宽表 | `fund_etf_spot_em()`；`代码`、数据日期、更新时间 | ETF quote | `NOT_CONFIGURED`：先验证更新时间原始单位/时区和 listing 映射。 |
| 开放式基金净值 | `fund_open_fund_info_em()` 的“单位净值走势”与“累计净值走势” | fund NAV | `NOT_CONFIGURED`：不是 `[start,end)` exact API；仅可做有行数上限的双收据定时 importer。 |
| 期货结算 legacy bridge | `FUTURES_DAILY_MARKET`，需 settle/previous settle/OI | futures settlement | `NOT_CONFIGURED`：只按 `(MARKET,SYMBOL,TRADE_DATE)` 导入，原表不是运行时查询源。 |

collector 无法获得可信 provider row time 时，`event_at` 只能被明确标记为 `collector_observed`；`available_at` 是本系统收到并发布证据的时间。捕获 UTC 日期不是来源 `as_of`，不得伪造、推断或写入该字段。它不得冒充交易所 tick 时间，也不得用于历史严格 PIT 在线补数。

#### 4.2.1 A 股估值预捕获批次候选

已落地的 `StockValuationCollector` 不是页面 fallback。它只持久化私有 `market.stock_valuation_captured_snapshot / valuation_snapshot / snapshot`，由受控 scheduler 或测试夹具交付已捕获的 AkShare 宽表；默认入口零 fetch、零 HTTP、零 request-time provider route，且没有 public family、API、freshness 或 legacy bridge。处理前冻结 CN-SSE/CN-SZSE `(venue, code) → canonical identity` map、目标集合、四字段 profile、`local_only + display` 语义以及精确 aware `captured_at` 的一微秒选择窗口。宽表没有可信逐行来源事件时间，故 observation `event_at` 只表示 `collector_observed` capture instant，receipt 明确记录 `source_event_time=null` 和 `source_as_of=null`；它不能改写为交易所时间、日线 close、日历 event 或公开 `as_of`。

capture envelope 固定 provider、`stock_zh_a_spot_em` endpoint、空 args/kwargs、collector version、受审核并精确固定为 `akshare.stock_zh_a_spot_em:captured-batch-v1` 的 source revision、captured_at、time basis 和自排除 batch SHA-256；构造时递归冻结 raw payload。内部调用者即使同时伪造 revision、envelope 和 hash，也会在任何 Store I/O 前因 descriptor mismatch 拒绝。已知 target 的 identity、重复、缺字段或规范化错误会整批零写入；未知结构有效的代码只留在 quarantine 与每个 target 的紧凑 receipt manifest。写入前严格限制 2 MiB source envelope、16 target 和 10 MiB 完整 target receipt。Store 从完整 receipt 自行提取唯一允许的 `source_batch` 段，按 canonical JSON UTF-8 字节建立或复用一条 `md_source_payloads` BLOB，并用 `md_source_snapshot_payload_refs` 关联每个 target snapshot；不同字节绝不共用一行。先用字节重算 BLOB `content_sha256` 和 `payload_bytes`，再把 JSON 解码的 BLOB 放回 manifest `receipt_payload`，规范化后的完整 receipt 必须重新得到 target snapshot 的 `payload_sha256`。共享内容不拥有 publication 或公开读取入口，publication、授权、quarantine 和部分发布语义仍逐 target 落在 source snapshot 上。完整预检后各 target 独立 publication，后续失败返回 durable prefix；只有 publication 后的 Store `local_only` 重读才构成本地持久化证据。

复用 shared BLOB 前 Store 强制从数据库重读，避免长期 Session 复用已缓存的被篡改字节。迁移只增 child evidence 表；普通 MySQL `BLOB` 或 `LONGBLOB` 被识别为与 `MEDIUMBLOB` 不同的 drift。非空表 downgrade 仍失败关闭；PostgreSQL 在证明空表和 DROP 前锁定两张 child 表，真实 MySQL/PostgreSQL 演练保持 `NOT_RUN`。

本地 139 条聚焦 pytest 已覆盖默认关闭、网络防护、身份、封装、时间语义、quarantine、预算、部分发布、递归冻结和 Store 回读。真实 AkShare、scheduler、许可、calendar、MySQL/PostgreSQL、浏览器与策略/回测仍为 `NOT_RUN`；即使内部候选通过离线回归，公开 `stock.valuation` 仍不是可用能力。

### 4.3 必须保持 `NOT_CONFIGURED` 的来源和 family

| 项目 | 原因 |
| --- | --- |
| `futures_zh_spot` 对当前 CFFEX realtime | `market="CF"` 的语义与 CFFEX contract mapping 未经验证，`time` 不是完整可审计时点。 |
| futures inventory/warehouse | 各接口仅给库存、变动或按日仓单；没有一个来源同时满足 receipt/inventory/delivery 的合同。 |
| `bond_zh_hs_cov_spot` 的通用债券 quote/orderbook | 它是可转债宽表；legacy `symbol/code/ticktime` 的原始 schema、时间和 listing 映射仍无受控 fixture。 |
| `bond_spot_quote/deal`、`bond_china_yield` | 分别依赖债券简称或日期×期限曲线，无法证明单券 ISIN/coupon/maturity identity。 |
| `option_current_em`、`option_value_analysis_em` | 无经验证的 source time；不能提供完整 option chain 或 risk surface。 |
| `forex_spot_em`、`currency_boc_safe` | 前者无 venue/time，后者是中间价 reference 且当前 identity 无 rate-type selector。 |
| `crypto_js_spot` | `市场/交易品种` 不能直接证明 venue、base、quote、market type。 |
| `crypto_bitcoin_cme` | 是成交量报告，缺 long/short/net position。 |
| OpenBB 的 quote/chain/valuation | 当前 runner 和默认 policy 只批准 bars；任何扩展必须走新的协议版本和 operator 配置审计。 |

## 5. DataPage、legacy 兼容与“历史 bars 被当作实时”的风险

当前 v1 bundle 有意把六个 `*.realtime` family 标为 `market.bars` compatibility，并且 required field 只保证 `close`。这使页面在旧数据源未迁移时仍可获得有限历史行情，但它不是 quote snapshot。

候选前端已做到：已授权服务端 capability 是 v2/bundle 唯一准入；有效 bundle 中，用户明确选择的 `ready + calendar_grid + 无维度 + bars/reference_series` family 才能进入 v2 query；`unconfigured/not_applicable` 不会回落到 legacy lookup；V2 contract 已发放后的查询失败被标为 error，不会再次走 legacy。页面初始化、路由 tab 切换和资产切换一律发 `local_only`，只有显式查询才发 `local_first`；本地覆盖不足且在线补齐关闭时显示明确状态而不伪称缓存命中。即使服务端已记录一条或多条来源回执，只要 coverage 不是 `complete`，页面也显示“本地覆盖不足”而不显示“已获取并入库”。NAV 与流动性按合同字段展示，`fund.nav` 不把 `price`、`close` 或 K 线替代为净值。能力接口失效时只保留遗留本地兼容读取，浏览器 feature flag 不能改变该行为。对于已配置的 quote，候选响应按 `source_policy_version` 对应的 freshness SLA 过滤并隐藏 stale records；这项行为尚未经过真实 snapshot 来源验证。

本轮 P0 收口后，legacy `market-instruments/lookup` 只允许本地读取；任何 `refresh_online=true` 会在 warehouse/provider I/O 前以 HTTP 409 / `MARKET_DATA_LEGACY_ONLINE_REFRESH_DISABLED` 拒绝。股票历史也只从 `STOCK_ZH_A_HIST` 按精确代码读取，不再按日期扫描 `000001` / `600000` 专表。缺少 durable fetch-lease manager 的 v2 coverage gap 同样只返回本地状态和 `FETCH_LEASE_MANAGER_UNAVAILABLE`，不会激活 route、调用 provider 或持久化。L-197-22 的 682 项中台/配置与 119 项焦点回归只证明这些本地边界。

`md_capability_ledger_entries` 已把逐 route 的 `declared / installed / verified / authorized / effective` lifecycle 作为 append-only durable evidence 落库，并以 descriptor/evidence hash 和有效窗口 fail closed；迁移不会 seed 活动记录，公开 API 也没有写入路径。环境变量、静态 policy、provider active、candidate artifact 与测试替身只能进一步收窄，不能替代该证据或单独启用 route。完整 source policy 继续控制本地事实重读，台账计算的 `online_route_ids` 只限制 provider I/O；所以当前没有运维记录时，所有 online route 仍默认关闭，OpenBB permit matrix 继续为空。`MarketDataQueryService` 的 lease 注入 seam 只用于受控测试组合，生产 API 由 `MarketDataStore.fetch_lease_manager()` 组成；下一轮应收紧该构造边界。旧 raw AkShare helper 图仍留在 `MarketInstrumentService` 内但已无 public `lookup` 调用边，未来必须删除、隔离或以同一拒绝边界封住，不能重新接线为 online fallback。

仍存在一个产品语义风险：页面 family 名称使用“实时”，而 bars compatibility 可能展示日线/周线/月线 close。F2 未完成前，页面不得把该 close 的 `event_at` 或本地 `available_at` 展示为“实时价格/实时更新时间”。启用 quote 前至少要满足以下条件：

1. UI 同时显示 `data_kind`、frequency 和 `time_basis`；bars 必须标为历史/收盘序列。
2. quote 采用 bundle v2 的独立 product，不能把 v1 `market.bars` 原地替换为 snapshot。
3. quote 不可用时显示未配置或错误；不得将旧 bars 静默改名为实时 quote。
4. 策略页只能把 `strict_local` 的已 sealed 数据用于研究预检；`legacy_fallback` 仍只是兼容路径，不能产生带 197 provenance 的研究/回测工件。

该项状态为 `IN_PROGRESS`，并且需要浏览器 E2E 才能关闭。

## 6. 验收清单与不可替代的外部证据

| 验收项 | 状态 | 必需证据 |
| --- | --- | --- |
| 历史候选后端及市场接口兼容总回归 | 历史记录（`357 passed, 32 warnings`） | `market_data_platform`、配置、市场接口和 freshness 套件的历史提交后组合输出；不覆盖本次 completion candidate，也不等价于生产验收。 |
| 历史候选代码格式、规则和 migration head | 历史记录（Ruff format/check、`alembic heads`） | 当时 48 个目标 Python 文件格式通过，规则检查通过，head 为 `20260908_market_data_shared_dataset_bindings`；不描述当前 head，且未运行真实迁移。 |
| 历史候选前端相关单元、类型和构建门禁 | 历史记录（`12 + 28 + 100` 单元测试、`vue-tsc --noEmit`、Vite build） | 当时按文件串行的本地验证；不覆盖本次 capability/bridge 增量，Browserslist 与 bundle-size 警告已记录，不等价于浏览器 E2E。 |
| 本次 capability/cache-fill/bridge guard 增量 | `PASS`（L-197-15，本地） | 静止候选已完成 capability API、cache 状态矩阵、同步/异步 bridge 拒绝、symbol 快照竞态和四份前端 v2 测试；不替代浏览器、真实数据或部署证据。 |
| 当前 ETF NAV identity/coverage/runner 增量 | `PASS`（L-197-16、L-197-19，本地） | 646 条后端回归、21 条 runner 回归、71 条行情页前端回归、typecheck/build 与目标 Ruff 均通过；`fund.nav` 仅接受 ETF `LISTING`，coverage 不完整时页面不显示成功。G1 fixture 即使通过，仍因其它 formal gates pending 返回 `NOT_RUN` 进程状态；G2/G3/G4 模式映射也只能对应正式 required gate。此记录不替代真实 route、数据库或浏览器验收。 |
| unified matrix live gate | `BLOCKED`（L-197-17） | 没有 external approval 或 approved source manifest 时，在 provider I/O 前返回 `ACCEPTANCE_EXTERNAL_APPROVAL_REQUIRED`；这是 fail-closed 证明。 |
| large-file ratchet | `BLOCKED / NO-GO`（L-197-18） | 当前 38 项超限，未改写 baseline；该全仓质量闸门恢复前不得作发布签收。 |
| 真实 AkShare exact route | `NOT_RUN` | 每条 route 的实际请求/回执、字段和身份 mismatch 反例、限流与错误码证据。 |
| F2 collector 宽表刷新 | `IN_PROGRESS` | 离线 schedule/shadow snapshot importer 候选已存在，但没有 route 或网络调用；真实 feed-level singleflight、raw snapshot、ambiguous-row quarantine、首次导入后第二次同请求零网络仍为 `NOT_RUN`。 |
| A 股 `stock.valuation` 预捕获宽表采集候选 | `PASS`（L-197-21，本地开发回归） | 私有 `market.stock_valuation_captured_snapshot / valuation_snapshot / snapshot` 默认关闭 collector 已验证零 fetch/HTTP、封装 hash、递归冻结、精确 collector-observed capture instant、unknown quarantine、2 MiB/10 MiB/16-target 写前限制、每宽表一份 canonical UTF-8 BLOB、target receipt 重建 hash、部分发布与 Store 回读；公开 `stock.valuation` 仍非 `ready`。真实 source/database/browser/scheduler 仍 `NOT_RUN`。 |
| OpenBB operator runner | `NOT_RUN` | 独立环境、provider allow-list、extension 版本、许可证/凭据、子进程隔离和真实 data receipt。 |
| 真实数据库迁移与 PIT | `BLOCKED` | 196/197 共同 migration head、MySQL 精度/索引检查、升级/降级或恢复演练、publication recovery。 |
| `/data/market` 浏览器灰度 | `NOT_RUN` | V1/V2 双路径、未配置展示、bars 非实时标签、网络观察和回滚。 |
| `/investment/strategies` 工件绑定 | `BLOCKED` | 196 工件 schema 冻结后，严格 local provenance manifest/hash、回放和权限验证。 |
| 生产验收 | `NOT_RUN` | 上述全部完成后，另行签署；本候选没有生产验收结论。 |

## 7. 与迭代 196 的交接条件

迭代 196 已冻结，196/197 的代码与迁移整合已接入 `dev`。下列条件仍限制页面灰度和生产启用，而不是限制当前候选提交：

1. 在可恢复 MySQL/PostgreSQL 副本确认唯一 Alembic head、迁移顺序、lease/fencing、备份与恢复路径。
2. 数据中台输出固定 provenance manifest hash、dataset/identity/policy version、source snapshot IDs、visibility anchor 和 artifact fingerprint，并用批准的真实数据重放。
3. 对每条 AkShare/OpenBB route 以及浏览器/API/策略链路完成本文件第 6 节的新鲜证据；OpenBB 仍受空 permit matrix、隔离运行器和许可证审查阻断。

在这些外部前置条件完成前，生产验收状态为 `NOT_RUN` / `NO-GO`；本地候选代码和局部测试不改变这一结论。
