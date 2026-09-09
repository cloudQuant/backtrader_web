# 迭代 197：数据范围与能力映射

> 本表是用户确认的“按两个页面当前支持的全部数据类型覆盖”的可执行解释。
> `M-*` 为资产覆盖项，`F-*` 为页面主题项。所有项均进入验收清单，不允许仅用一组股票样例结项。

## 1. 范围规则

1. 对已提供的数据操作，必须完成本地查询、缺口判定、可用来源补齐、持久化及再次复用。
2. 页面存在的概念标签不自动证明该业务数据已经提供。例如“风险曲面”卡片当前没有完整 IV/Greeks 曲面，“基金净值”字段提示当前也不能证明返回了净值。197 必须纠正标签与数据的关系，并保留已存在的关联表浏览功能。
3. S0 按本表记录每个资产、数据种类、市场、频率和 endpoint 的 `SUPPORTED/LOCAL_ONLY/UNSUPPORTED/PENDING_PROBE`。生产发布前不得遗留必需项 `PENDING_PROBE`。已有真实可用功能必须为 `SUPPORTED`，或在可追踪的真实外部阻塞下保持 `BLOCKED`，不能用改标 `UNSUPPORTED` 消除回归。
4. 输入精确标的不存在是该次请求的 `EMPTY_CONFIRMED/UNSUPPORTED_IDENTITY`，不是整类资产验收失败，也不是可用数据。七类验收必须各自另有有效标的的成功路径证据。
5. 不把“七类”扩展解释成全世界所有交易所、全部历史分钟数据或完整衍生品分析系统。支持市场以当前页面/后端功能、可验证存量表及获准来源能力共同冻结；新增市场可以登记但不替换现有市场覆盖。

## 2. 七类资产的主链

下列物理表均来自当前代码中的查询语句；未查询真实数据库，表是否存在、字段类型、主键和覆盖度需在 S0 导出核对。旧表通过 `DgDatasetStorage` 映射接入，只读适配器不执行旧 service 的样例回退。

| ID / 资产 | 当前本地查询对象 | 当前在线代码路径 | 197 必需结果 | OpenBB 接入边界 |
| --- | --- | --- | --- | --- |
| M-STOCK 股票 | `STOCK_ZH_A_SPOT_EM`、`STOCK_ZH_A_HIST`、现有动态个股历史表 | `stock_zh_a_hist`；失败分支 `stock_zh_a_hist_tx` | 指定股票快照/历史、成交量额、换手与已有估值字段；股票市场及复权明确 | `EquityHistorical`，候选 yfinance/FMP；A 股代码、交易所、复权和覆盖验证后才能备用 |
| M-FUTURES 期货 | `FUTURES_DAILY_MARKET` | `futures_zh_spot`、`futures_zh_daily_sina` | 指定合约的 OHLCV、结算/持仓；连续合约单列规则 | `FuturesHistorical` 的 Yahoo/Deribit 合约不等同中国期货，不能替代 RB/IF 等本地合约 |
| M-BOND 债券 | `BOND_ZH_HS_COV_SPOT`、`BOND_ZH_HS_COV_MIN` | `bond_zh_hs_cov_daily` | 当前可转债价格历史、快照、可用 bid/ask/成交额；分钟表按实际频率识别 | OpenBB 利率/国债收益率数据可登记为另一数据集，不作为中国可转债价格 fallback |
| M-FUND 基金 | `ETF_REALTIME_QUOTE_EM`、`ETF_FUND_HIST_EM`、`FUND_ETF_HIST_SINA` | `fund_etf_hist_em` | ETF 价格历史、快照、量额；本地已有其他基金表可浏览/登记 | `EtfHistorical` 需确认上市地与币种；开放式基金 NAV 不能由 ETF close 代替 |
| M-OPTION 期权 | `OPTION_CURRENT_EM` | `option_cffex_zz1000_list_sina`/`spot_sina`；按合约走沪深 300、上证 50、中证 1000、商品或 SSE 日历史 | 期权链和具体合约历史分别存储；执行价、到期日、方向、乘数明确 | `OptionsChains` 可来自 yfinance/CBOE/Deribit，限真实覆盖市场；国外期权不能替代 MO/中国 ETF 期权 |
| M-FX 外汇 | `FOREX_SPOT_EM`、`CURRENCY_BOC_SAFE` | `forex_spot_em`、`forex_hist_em` | 指定 base/quote 的行情快照与价格历史；银行牌价单独类型 | `CurrencyHistorical` 可作为相同币对/报价口径的备用；CNH/CNY 和 direct/inverse 不能混淆 |
| M-CRYPTO 数字货币 | `CRYPTO_JS_SPOT`、`CRYPTO_BITCOIN_CME` | `crypto_js_spot`、`crypto_bitcoin_cme` | 指定交易对快照，以及独立的 CME 持仓统计；如请求价格历史必须获得真实 bars | `CryptoHistorical` 用于匹配币对的价格数据；交易所现货、聚合现货、永续、期货分别登记 |

现有多资产研究的 AkShare adapters 也是可复用来源，例如其数字资产来源采用受控 OKX 标识；是否投入两页使用，需要在 G0 核对方法、身份、许可和延迟，不能仅根据类名启用。

### 2.1 首批逻辑数据集

保留迭代 189 的稳定名称：`market.stock_daily`、`market.futures_daily`、`reference.shfe_delivery_monthly`。其余建议登记 `market.bond_bars`、`market.fund_bars`、`market.option_bars`、`market.fx_bars`、`market.crypto_bars`；股票/期货分钟数据另有各自 bars 数据集，避免 `*_daily` 名称承载分钟含义。

跨资产规范种类为：`bars`、`quote_snapshot`、`option_chain`、`position_report`、`valuation_snapshot`、`reference_series`、`instrument_metadata`、`catalog_table`。业务数据集具有自己的 schema、主键和质量规则；共用种类不意味着共用来源、单位或许可。

`quote_snapshot` 可以含价格、bid/ask、量额、涨跌幅和估值等已存在字段。来自最后一根 bar 的展示值必须标记 `quote_kind=last_bar_close`，不能标成实时成交快照。缺失估值字段保留 null，不强制为行情查询发起全市场估值扫描。

### 2.2 来源路由样例

| 请求 | 合法路由 | 必须拒绝的替代 |
| --- | --- | --- |
| 深交所 000001，日线，同一 qfq 版本 | 本地规范数据 → 合格 legacy 数据 → AkShare；经验证等价的 OpenBB 供应商才可后备 | 上证指数 000001；另一只股票；不同复权版本直接拼接 |
| SHFE 具体 RB 合约，1h | 本地对应合约 → 获准分钟来源/已登记 CSV → 同语义聚合 | RB0 连续或其他到期月；美国 Yahoo 期货 |
| MO 某到期月期权链 | 本地同一 chain snapshot → 当前对应列表与链 endpoint | 取当前列表第一张链后仍声称请求的是原到期月 |
| USDCNH 行情 | 同 base/quote、报价口径和时间粒度的本地/AkShare/OpenBB 数据 | USDCNY；银行中间价；仅取倒数但不调整 OHLC |
| BTCJPY 价格历史 | 合格本地 → 实际支持 BTC-JPY 的来源 | BTC-USD、BTC-USDT 或 `crypto_bitcoin_cme` 持仓统计 |

备用源没有等价数据时保留可用本地部分并明确失败原因；供应商数量不是成功标准。

## 3. 页面 21 项主题覆盖

以下主题来自 `assetDataFamilySpecs`。它们全部纳入显示与能力映射验收；“目录主题”保留真实表浏览，并在没有语义数据集时显示“仅目录”，不自动触发所有相关采集脚本。

| ID | 资产 / 现有主题 | 197 数据语义与必验内容 |
| --- | --- | --- |
| F01 | 股票 / 实时与历史 | `quote_snapshot + bars`；来源、市场时间与历史窗口可见 |
| F02 | 股票 / 估值 | 有来源的 market_cap/float_market_cap/PE/PB 为 `valuation_snapshot` 或 quote 字段；未知值不冒充零 |
| F03 | 股票 / 流动性 | 量额换手来自 bars/quote；资金流关联表独立 `catalog_table/reference_series`，不把 volume 当资金流 |
| F04 | 期货 / 实时行情 | 合约级 quote/bars；连续合约标记 synthetic 及构造规则 |
| F05 | 期货 / 结算 | settle/previous_settle/OI；结算价不等同 close，缺字段显式告知 |
| F06 | 期货 / 库存仓单 | 当前主题字段仅 volume/OI，真实库存/仓单只来自对应已登记表；保留目录，禁止误报库存数据已到位 |
| F07 | 债券 / 实时与历史 | 当前可转债行情与可用量额；区分日线和分钟表 |
| F08 | 债券 / 报价 | bid/ask 与报价种类、时间对应；单档价差不表示完整订单簿 |
| F09 | 债券 / 固收 | 债券关联信息/收益率/曲线按独立数据集登记；价格不能冒充到期收益率 |
| F10 | 基金 / 实时与历史 | ETF 市场价格 bars/quote，份额/成交量单位明确 |
| F11 | 基金 / 流动性 | bars/quote 量额；资金流、规模、行业配置只按各自表的语义展示 |
| F12 | 基金 / 净值 | 只有真实 NAV/累计 NAV 才展示净值标签；ETF close 和 previous_close 保留市场价标签 |
| F13 | 期权 / 行情 | 合约 bars 与报价；到期状态和报价时间明确 |
| F14 | 期权 / 衍生品结构 | `option_chain`，按 underlying/expiry/strike/call-put/venue/snapshot 组织，不装入价格时间序列 |
| F15 | 期权 / 风险曲面 | 当前不具备完整曲面模型；保留已有字段与相关表。只有数据源真的给出 IV/Greeks 才展示，记录计算来源及假设 |
| F16 | 外汇 / 行情 | 价格快照和 bars；base/quote、bid/ask/mid、时区明确 |
| F17 | 外汇 / 宏观汇率 | 银行牌价、中间价与宏观 reference_series，各自发布日和可用时间；不能补市场 OHLC 缺口 |
| F18 | 外汇 / 区间 | 由同版本 bars 派生最高/最低/区间回报，输入版本可追踪 |
| F19 | 数字货币 / 实时 | 对应币对的 24h 字段与快照；24h volume 不直接累加成日线成交量 |
| F20 | 数字货币 / CME 持仓 | `position_report`；报告主体、报告日、类别和来源保留；与用户选中交易对分别呈现 |
| F21 | 数字货币 / 区间 | 若有真实 bars 才画价格区间；仅有持仓数据就画持仓结构，不能生成虚假的 K 线 |

21 个主题的验收要同时检查 API 元数据与 UI 文案；关键词命中一张表不能使主题状态自动变成“历史齐全/实时可用”。

## 4. 频率与时间覆盖

| 消费入口 | 当前输入 | 197 规范化 | 完整性规则 |
| --- | --- | --- | --- |
| 行情页 | daily / weekly / monthly | `1d / 1w / 1mo` | 对 bars 按对应交易日历聚合；对 snapshot/chain/report 显示相应时间选择语义，周期不适用时禁用 |
| 策略页 | 1d / 1h / 30m / 5m | `1d / 1h / 30min / 5min` | 逐资产、市场及来源检查原生频率/可推导频率/保留窗口；保留全部现有选项 |
| 兼容代码 | 1m、1M、timeframe_n | 以入口语义区分；市场旧 period 的 1m=月，策略的 1m=分钟；内部只用明确枚举与 multiplier | 不允许先 lower() 再混淆月与分钟；不支持的倍数返回 422 |
| 本地 CSV | 原文件声称的频率 | 结合已登记 schema、时区与时间间隔验证 | 文件名不能单独证明频率；范围校验不得只用最大/最小时间 |

日线不能生成分钟线。5min → 30min/1h 必须有完整基础 bars、正确 session 边界和版本化聚合规则；不得跨午休、夜盘或夏令时拼接。周/月未结束的周期可以展示 `provisional`，严格研究默认只用已关闭周期。

### 4.1 七类最小验收单元

每类在 G0 固定至少一个身份完整、许可允许持久化的真实标的，采用当时有效的主数据版本和实际可请求时间窗：

- 股票：一只 A 股，日线及该资产已支持的分钟用例。
- 期货：一个具体中国期货合约；另加 RB0/IF0 连续合约的规则拒绝或正确构造用例。
- 债券：当前可转债覆盖内的一个确切标的。
- 基金：一个中国 ETF；净值与成交价格混淆的反例。
- 期权：一个有效具体合约及其对应到期月链；到期历史另测。
- 外汇：USDCNH 或主数据已确认的当前支持币对；银行牌价分离反例。
- 数字货币：当前可用报价交易对及独立 CME 持仓数据；OpenBB 若用于价格历史，币对必须确实匹配。

页面默认 `IM2606` 等示例可能在实施时到期。验收使用动态主数据选择的有效标的，不把默认示例可见当作当前有行情；到期标的应仍可查询实际保留的历史。

七类 × `1d/1h/30m/5m` 的策略数据准备全部需要能力响应契约测试。对已验证支持的组合必须跑成功取数/落库/工件路径；对不支持组合必须有拒绝证据。不能把 28 个能力响应均成功返回 HTTP 200 描述成 28 个频率都获得真实行情。

## 5. 数据目录扩大方式

1. 首批精确映射第 2 节的查询表、现有相关表浏览元数据，以及迭代 189 三个试点名称。
2. 未登记的其他 legacy 表继续走现有管理界面，标为 `unmapped_legacy`；不为每张表临时创建新规范 schema。
3. 已在两个页面被实际消费的额外表，必须进入 S0 清单并随同接入；不得利用第 2 条遗漏实际消费路径。
4. 每加一类业务数据先提供 schema、主键、时间/单位/权限/质量/来源映射和验收样例，再启用补齐。
5. ClickHouse、全市场分钟回填、完整财务 PIT 库、全量 IV 曲面、跨市场基金持仓等增量能力另行估算，不能用它们替换本迭代已有七类功能的交付。
