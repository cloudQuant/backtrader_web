# 迭代 197 候选实现与验收状态

> 记录日期：2026-09-08<br>
> 文档性质：隔离工作树中的候选实现审计，不是生产发布证明。<br>
> 设计基线：迭代 196 尚未冻结；本文件不解除两迭代的联合集成闸门。

## 1. 阅读规则和状态含义

本文件把候选工作树中已经存在的实现，与尚未完成的真实环境验收明确分开。`DONE` 只表示候选代码和其定向自动化验证已具备，不表示迁移、真实来源、生产数据库、浏览器 E2E 或策略工件验收已经完成。

| 状态 | 含义 |
| --- | --- |
| `DONE` | 候选工作树已有实现和对应离线/定向测试证据；仍可能有外部验收未运行。 |
| `IN_PROGRESS` | 已有基础或局部接线，但尚缺一个可安全启用的完整闭环。 |
| `NOT_CONFIGURED` | 有明确数据合同或需求，但没有经批准的 source policy/route；页面必须显示未配置，不得猜测回退。 |
| `BLOCKED` | 必须等待迭代 196、共享 migration head、真实环境授权或外部状态。 |
| `NOT_RUN` | 本次没有在真实 AkShare/OpenBB、共享数据库、浏览器或生产环境中执行；不能从 fixture、静态审计或历史日志推断成功。 |

提交后复核曾发现一项 PIT 回放测试不确定性：测试使用虚构的 13:00 cutoff，却让 publication 使用真实时钟，记录正确地在该 cutoff 后才可见。候选提交 `c474a57b` 仅为该测试注入固定的可信 publication clock，未改变生产语义。随后对 `tests/market_data_platform`、`tests/test_config.py`、`tests/test_market_instrument_api.py` 和 `tests/test_market_instrument_freshness.py` 的最终组合离线运行报告为 `357 passed, 32 warnings in 76.18s`；候选提交 `20e214dd` 已格式化本迭代引入的 9 个文件，Ruff 格式和规则检查通过，Alembic head 为 `20260908_market_data_shared_dataset_bindings`。前端相关验证按文件串行运行：`marketData.test.ts` 为 `12 passed`，`DataPage.test.ts` 为 `28 passed`，`StrategyPage.test.ts` 为 `100 passed`；`npm run typecheck` 与 `npm run build` 均通过。后端 warnings 来自已安装 Backtrader、Alembic 配置和 Starlette 的弃用提示；前端构建仍报告 Browserslist 数据陈旧及既有大 chunk 警告。它们都已记录，但不将本地结果升级为全量、真实数据或生产验收。

## 2. 候选实现总览

| 能力 | 候选状态 | 当前证据和边界 | 真实验收状态 |
| --- | --- | --- | --- |
| 精确 identity、catalog、canonical series、revision、publication/read-back | `DONE` | 候选实现采用规范化 `md_*` 模型、不可变来源快照、发布回读与 PIT 可见性边界。 | `NOT_RUN`：未在共享 MySQL/PostgreSQL 实例执行迁移和恢复演练。 |
| local-first 查询、singleflight、严格 PIT 和 cursor | `DONE` | 候选实现读取本地覆盖；已包含 follower 事务回滚后重读、refresh 不复用 local-first follower 的回归。 | `NOT_RUN`：未做真实并发、多进程、故障恢复压测。 |
| bars 的 AkShare 显式 route registry | `DONE` | 仅允许经审核的精确标的/市场/频率路线；拒绝 sample、邻近标的和隐式 provider fallback。 | `NOT_RUN`：没有真实 AkShare 账户/网络/限流/字段漂移验收。 |
| OpenBB 隔离 subprocess runner | `DONE` | JSON DTO、环境白名单、输出上限、超时进程组清理、raw payload 与规范化 records 的确定性投影均在候选中覆盖；重复字段、投影不一致与进程内过载稳定拒绝。当前仅准许 bars。 | `NOT_RUN`：未在 operator-owned OpenBB 环境、真实 extension、许可和凭据下执行；上限只覆盖单个 Python 进程。 |
| quote snapshot local-first 覆盖 | `DONE` | `SnapshotCoveragePlanner` 已避免把 quote 强行塞入交易日历；产品 SLA 以 `source_policy_version` 锚定，quote 响应会隐藏超过该 policy freshness 的记录。 | `NOT_RUN`：真实 snapshot feed、七资产 identity 映射和 freshness 行为尚未在真实来源验证。 |
| F1 市场页控制面 | `DONE` | `query-bundle` v1 覆盖 7×3 family；开关默认关闭；有效 bundle 中 `unconfigured/not_applicable` 不走 legacy lookup。 | `NOT_RUN`：未在浏览器、真实后端、真实数据状态下 E2E。 |
| F1 策略页严格本地预检 | `IN_PROGRESS` | 候选已通过 query-contract 接入严格本地预检，并区分 typed contract 未发放、404、V2 执行失败和 legacy fallback。 | `BLOCKED`：迭代 196 的研究/回测工件 schema、输入输出契约未冻结。 |
| F2 quote/valuation/settlement/NAV/reference | `IN_PROGRESS` | 已有离线 schedule/shadow snapshot importer 候选，但它未连接任何 provider route 或网络；各数据族仍保持 fail-closed。 | `NOT_RUN`：没有真实采集、回填或页面启用。 |
| 共享 binding migration、真实回填、页面灰度、生产开关 | `BLOCKED` | shared binding migration 仅存在于候选工作树；必须与 196 的 migration head、数据库 lease、工件版本共同治理，不能单独应用或合并。 | `NOT_RUN`。 |

## 3. 当前 21 个页面数据族

“当前候选”描述 `market-data-family-bundle-v1` 的实际控制面状态。`*.realtime` 中的 `DONE（bars 兼容）` 只代表有 `market.bars` 的日/周/月 K 线兼容桥，不代表该页面已经有真实 quote snapshot。

第 2 节所列离线 schedule/shadow snapshot importer 的 `IN_PROGRESS` 只表示通用离线基础设施已存在；它不会把下表任何 `NOT_CONFIGURED` family 变成已批准的 provider route，也不构成真实采集或页面可用性证据。

| family | 当前候选合同/状态 | F2 预期产品 | F2 实施状态 | 当前不能宣称的能力 |
| --- | --- | --- | --- | --- |
| `stock.realtime` | `DONE`：`market.bars` / `bars` / 1d、1w、1mo | `market.quote_snapshot` / snapshot | `NOT_CONFIGURED` | 实时逐笔/盘口或源 tick 时间。 |
| `stock.valuation` | `NOT_CONFIGURED`：`market.valuation` / reference / 1d | 市值、PE、PB、as-of | `NOT_CONFIGURED` | 用局部字段或历史 bars 补齐估值。 |
| `stock.liquidity` | `NOT_CONFIGURED`：`market.liquidity` / reference / 1d | volume、turnover、turnover rate | `IN_PROGRESS`：已有安全 exact route 设计 | 无 route 前的在线获取。 |
| `futures.realtime` | `DONE`：`market.bars` / 1d | `market.quote_snapshot` / snapshot | `NOT_CONFIGURED` | 现货 bid/ask、当前 OI。 |
| `futures.settlement` | `NOT_CONFIGURED`：`market.settlement` / reference / 1d | settle、previous settle、OI | `IN_PROGRESS`：legacy bridge 设计 | 不带 `MARKET` 的旧表查询或由日线猜昨结。 |
| `futures.inventory` | `NOT_CONFIGURED`：`market.inventory` / inventory report | 仓单、库存、交割数量 | `NOT_CONFIGURED` | 将不同来源库存/仓单拼成一条报告。 |
| `bond.realtime` | `DONE`：`market.bars` / 1d | `market.quote_snapshot` / snapshot | `NOT_CONFIGURED` | 一般债券实时行情。 |
| `bond.orderbook` | `NOT_CONFIGURED`：`market.quote_snapshot` / snapshot | bid、ask、volume、turnover | `NOT_CONFIGURED` | 以可转债宽表冒充全部债券 order book。 |
| `bond.fixed_income` | `NOT_CONFIGURED`：`market.bond_reference` / reference / 1d | YTM、coupon、maturity | `NOT_CONFIGURED` | 用短名称或收益率曲线当单券 reference。 |
| `fund.realtime` | `DONE`：`market.bars` / 1d、1w、1mo | ETF `market.quote_snapshot` | `NOT_CONFIGURED` | 开放式基金 NAV 或实时 ETF quote。 |
| `fund.liquidity` | `NOT_CONFIGURED`：`market.liquidity` / reference / 1d | ETF volume、turnover | `IN_PROGRESS`：已有安全 exact route 设计 | 用 NAV 模拟成交量。 |
| `fund.nav` | `NOT_CONFIGURED`：`market.fund_nav` / reference / 1d | unit NAV、cumulative NAV、daily growth | `IN_PROGRESS`：组合式 importer 设计 | 直接把 ETF K 线当 NAV。 |
| `option.realtime` | `DONE`：`market.bars` / 1d | contract `quote_snapshot` | `NOT_CONFIGURED` | 实时报价或期权链。 |
| `option.derivative` | `NOT_CONFIGURED`：`market.option_chain` / snapshot | chain、IV、OI、strike、expiry | `NOT_CONFIGURED` | 以单合约或宽表的部分字段宣称全链。 |
| `option.risk_surface` | `NOT_CONFIGURED`：`market.option_risk_surface` / snapshot | IV、Greeks、model version | `NOT_CONFIGURED` | 用单个 IV 或无模型版本值构造风险面。 |
| `fx.realtime` | `DONE`：`market.bars` / 1d | `market.quote_snapshot` | `NOT_CONFIGURED` | 交易所/报价源实时 FX quote。 |
| `fx.macro_fx` | `NOT_CONFIGURED`：`market.fx_reference` / reference / 1d | official/central rate reference | `NOT_CONFIGURED` | 将中间价混作交易 FX pair。 |
| `fx.range` | `NOT_CONFIGURED`：`market.bars` / 1d | exact FX OHLC range | `IN_PROGRESS`：已有安全 exact route 设计 | 周/月/分钟或未验证的 pair mapping。 |
| `crypto.realtime` | `NOT_CONFIGURED`：`market.quote_snapshot` / snapshot | venue/pair quote | `NOT_CONFIGURED` | 无 venue、base、quote 映射的通用加密行情。 |
| `crypto.cme_position` | `NOT_CONFIGURED`：`market.position_report` / report | long、short、net、OI | `NOT_CONFIGURED` | 将 CME 比特币成交量报告称为持仓报告。 |
| `crypto.range` | `NOT_CONFIGURED`：`market.bars` / 1d | approved provider historical bars | `NOT_CONFIGURED` | AkShare 或 OpenBB 的无配置全局 fallback。 |

## 4. F2 数据来源分级结论

### 4.1 可以作为 request-time exact fallback 的路线

这些 route 必须仍经 catalog、identity、source policy、provider receipt、publication 和本地回读，不是允许页面直接调用 AkShare。

| F2 family | 方法 | 必要 identity 和时间语义 | 设计状态 |
| --- | --- | --- | --- |
| `stock.liquidity` | `ak.stock_zh_a_hist(symbol, period, start_date, end_date, adjust)` | 精确 CN-SSE/SZSE listing + response code；交易日 close；`1d`。 | `IN_PROGRESS`：可增加 `akshare-stock-liquidity-v1`。 |
| `fund.liquidity` | `ak.fund_etf_hist_em(symbol, period, start_date, end_date, adjust)` | 精确 ETF listing + CN venue；`1d`。 | `IN_PROGRESS`：可增加 `akshare-fund-liquidity-v1`。 |
| `fx.range` | `ak.forex_hist_em(symbol)` | 精确 provider code 与 frozen FX pair mapping；只批准 `1d`。 | `IN_PROGRESS`：现有 bars adapter 可复用，但 family/profile 尚未启用。 |

现有 bars compatibility 路线也属于候选 `DONE` 范围，但只覆盖其已声明的精确 asset、venue、频率和字段；它们不自动扩大为 F2 quote、valuation、settlement、NAV 或 report 能力。

### 4.2 只能作为 scheduled collector importer 的宽表来源

宽表没有单标的 provider 请求形状，不能塞进当前 `MarketDataProviderRequest`，更不能在每个页面请求中重复抓取整个市场。候选中已有离线 schedule/shadow snapshot importer，但它尚未配置任何 approved `feed_id`、provider route 或网络调用；因此不是已启用采集能力。真正启用前仍需服务端 `feed_id`、feed-level singleflight、身份映射冻结、payload/row 上限、未知行 quarantine、raw snapshot 证据和发布后本地回读。

| 来源 | 方法和关键 source key | 可规划的产品 | 当前状态 |
| --- | --- | --- | --- |
| A 股宽表 | `stock_zh_a_spot_em()`；`代码`，无输出交易所和逐行时间 | stock quote、stock valuation | `NOT_CONFIGURED`：可在冻结 `(venue, code)` 映射后做 collector-observed snapshot。 |
| ETF 宽表 | `fund_etf_spot_em()`；`代码`、数据日期、更新时间 | ETF quote | `NOT_CONFIGURED`：先验证更新时间原始单位/时区和 listing 映射。 |
| 开放式基金净值 | `fund_open_fund_info_em()` 的“单位净值走势”与“累计净值走势” | fund NAV | `NOT_CONFIGURED`：不是 `[start,end)` exact API；仅可做有行数上限的双收据定时 importer。 |
| 期货结算 legacy bridge | `FUTURES_DAILY_MARKET`，需 settle/previous settle/OI | futures settlement | `NOT_CONFIGURED`：只按 `(MARKET,SYMBOL,TRADE_DATE)` 导入，原表不是运行时查询源。 |

collector 无法获得可信 provider row time 时，`event_at` 只能被明确标记为 `collector_observed`；`available_at` 是本系统收到并发布证据的时间。它不得冒充交易所 tick 时间，也不得用于历史严格 PIT 在线补数。

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

候选前端已做到：有效 bundle 中，只有 `ready + bars` 才能进入 v2 query；`unconfigured/not_applicable` 不会回落到 legacy lookup；V2 contract 已发放后的查询失败被标为 error，不会再次走 legacy。默认 feature flag 关闭也避免未经灰度的接线影响现网。对于已配置的 quote，候选响应按 `source_policy_version` 对应的 freshness SLA 过滤并隐藏 stale records；这项行为尚未经过真实 snapshot 来源验证。

仍存在一个产品语义风险：页面 family 名称使用“实时”，而 bars compatibility 可能展示日线/周线/月线 close。F2 未完成前，页面不得把该 close 的 `event_at` 或本地 `available_at` 展示为“实时价格/实时更新时间”。启用 quote 前至少要满足以下条件：

1. UI 同时显示 `data_kind`、frequency 和 `time_basis`；bars 必须标为历史/收盘序列。
2. quote 采用 bundle v2 的独立 product，不能把 v1 `market.bars` 原地替换为 snapshot。
3. quote 不可用时显示未配置或错误；不得将旧 bars 静默改名为实时 quote。
4. 策略页只能把 `strict_local` 的已 sealed 数据用于研究预检；`legacy_fallback` 仍只是兼容路径，不能产生带 197 provenance 的研究/回测工件。

该项状态为 `IN_PROGRESS`，并且需要浏览器 E2E 才能关闭。

## 6. 验收清单与不可替代的外部证据

| 验收项 | 状态 | 必需证据 |
| --- | --- | --- |
| 候选后端及市场接口兼容总回归 | `DONE`（`357 passed, 32 warnings`） | `market_data_platform`、配置、市场接口和 freshness 套件的提交后组合输出；不等价于生产验收。 |
| 候选代码格式、规则和 migration head | `DONE`（Ruff format/check、`alembic heads`） | 48 个目标 Python 文件格式通过，规则检查通过，head 为 `20260908_market_data_shared_dataset_bindings`；未运行真实迁移。 |
| 前端相关单元、类型和构建门禁 | `DONE`（`12 + 28 + 100` 单元测试、`vue-tsc --noEmit`、Vite build） | 按文件串行的本地验证；Browserslist 与 bundle-size 警告已记录，不等价于浏览器 E2E。 |
| 真实 AkShare exact route | `NOT_RUN` | 每条 route 的实际请求/回执、字段和身份 mismatch 反例、限流与错误码证据。 |
| F2 collector 宽表刷新 | `IN_PROGRESS` | 离线 schedule/shadow snapshot importer 候选已存在，但没有 route 或网络调用；真实 feed-level singleflight、raw snapshot、ambiguous-row quarantine、首次导入后第二次同请求零网络仍为 `NOT_RUN`。 |
| OpenBB operator runner | `NOT_RUN` | 独立环境、provider allow-list、extension 版本、许可证/凭据、子进程隔离和真实 data receipt。 |
| 真实数据库迁移与 PIT | `BLOCKED` | 196/197 共同 migration head、MySQL 精度/索引检查、升级/降级或恢复演练、publication recovery。 |
| `/data/market` 浏览器灰度 | `NOT_RUN` | V1/V2 双路径、未配置展示、bars 非实时标签、网络观察和回滚。 |
| `/investment/strategies` 工件绑定 | `BLOCKED` | 196 工件 schema 冻结后，严格 local provenance manifest/hash、回放和权限验证。 |
| 生产验收 | `NOT_RUN` | 上述全部完成后，另行签署；本候选没有生产验收结论。 |

## 7. 与迭代 196 的交接条件

在下列条件未满足前，197 候选只能存在于隔离工作树，不能合并共享 migration、启用页面或宣称策略消费已经切换：

1. 196 冻结研究/回测输入、输出、artifact schema 和版本兼容窗口。
2. 196/197 确定唯一 Alembic head、迁移顺序、lease/fencing、备份与恢复路径；当前 shared binding migration 仅为候选，不能作为共享数据库迁移依据。
3. 数据中台输出固定 provenance manifest hash、dataset/identity/policy version、source snapshot IDs、visibility anchor 和 artifact fingerprint。
4. 真实数据库、AkShare/OpenBB、浏览器和策略链路全部按本文件第 6 节重跑，并保存新鲜证据。

在这些前置条件完成前，整体状态为 `BLOCKED`；候选代码和局部测试不改变这一结论。
