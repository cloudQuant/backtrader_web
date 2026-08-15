# AI 多资产分析调研报告

## 1. 调研方法

本报告以 2026-08-01 为检索基准日，优先采用监管机构、交易所、行业委员会、官方 API 文档和开源项目原始仓库。结论按“事实—推论—产品建议”分开：

- **事实**：来源直接说明的制度、字段、交易机制或技术能力；
- **推论**：结合本项目现状得出的工程或产品判断；
- **建议**：本迭代采用的设计选择。

涉及收益和风险的资料只用于定义研究框架，不构成投资建议。外部接口、许可证和法规在实施前必须再次核验。

## 2. 现有实现审计

本节以代码提交 `e7fd2d5151c86ba62173b8d19736983a0a379909` 为基线。它描述的是
可复用能力和缺口，不代表多资产研究功能已经实现。

### 2.1 已有可复用能力

- `src/backend/app/services/market_instrument.py` 已将资产类型定义为
  `stock/futures/bond/fund/option/fx/crypto`，并提供统一异步列表和查询入口。
  普通查询仓库优先；只有调用方显式传入 `refresh_online=true` 才执行在线刷新，
  不能把它描述为每次查询都会发生的自动 online fallback。
- 该服务已有粗粒度 `provider/data_source_table/update_time` 和独立仓库缓存，但没有
  研究所需的字段级 `observed_at/published_at/available_at/license_tag`；
  缓存表由运行时 DDL 管理，也不能替代业务 Alembic 快照表。
- `src/backend/app/services/options_chain.py` 已有期权链入口，可作为新的期权快照适配器输入。
- `src/backend/app/services/stock_analysis/` 已有异步任务编排、报告、导出、
  知识库保存和自然语言研报链路。`pipeline.run()` 已经是异步函数；
  改进点是为插件增加受控 `await` 边界，不是把“同步 pipeline 整体改成异步”。
- `src/backend/app/services/stock_signal/` 与 `stock_signal_predictions` 已有版本化决策、数据质量、历史预测和结果评分的基础模式。
- 股票 prediction 的可空 `run_id` 表示一个 run 可有多条 prediction，不是一对一；
  旧 `prediction_key` 还包含模型版本。可借鉴幂等模式，但不能复用旧哈希定义。
- 报告构建器消费已经确定的结构化 decision，LLM 层明确不能覆盖 signal；
  “报告生成器同时负责交易决策”不是当前代码事实。
- `src/frontend/src/views/investment/StockAnalysisPage.vue` 已有可参考的页面结构，
  也已拆出信号历史和质量面板，但主体仍超过 1,600 行。独立股票页支持导出；
  知识库/工作区保存位于 AI 聊天报告卡，不应误记为该页面自身能力。
- 仓库已有 OTLP tracing、`/metrics`、AI 调用统计、慢请求日志和通用
  `MonitoringService`。迭代 191 需要在这些基础上增加资产任务、来源、调度和评分
  指标，而不是再建一套互不相连的监控系统。

### 2.2 不可直接复制的部分

- `MarketInstrumentService.lookup()` 在部分非股票资产精确代码未命中时会返回最近任意
  样本。研究主链必须通过严格身份适配器复用，并禁止样本替代，否则会把错误资产
  写入不可变预测。
- 股票的公司简介、财务报表、同业比较和新闻情绪不适用于国债、期货合约、外汇货币对或去中心化资产。
- 股票 `BUY/SELL/WATCH` 不足以表达期货做多/做空、期权开仓/平仓、基金申购/赎回或外汇基础/报价方向。
- 股票以开盘价和 `1/5/20` 个交易日收益评分，不能覆盖债券应计利息、基金净值、期货展期、期权到期、外汇 carry 或永续资金费。
- 将所有缺失数据补成中性会制造虚假确定性；多资产版本必须将关键缺失变为 `AVOID`。

### 2.3 当前资产数据覆盖的准确边界

- 债券统一查询目前以可转债为主，但仓库还存在国债收益率、ChinaMoney 债券信息、
  NAFMII 和现券报价采集模块；缺口是统一身份、时点和许可接入，不是“代码完全没有”。
- 基金统一查询目前以 ETF 为主，但仓库已有开放式基金净值、股票/债券持仓和基金
  基准字段；仍需份额类别、估值日历、费用和持仓披露时点的研究适配。
- 期权别名解析只对 MO 做了特殊处理，但精确 symbol 已能分发 IO、HO、MO、商品期权
  和上交所期权；缺口是无歧义合约身份、链快照和买方风险门控。
- 外汇同时使用 `FOREX_SPOT_EM` 和中国银行/SAFE 历史，并非只有参考价；仍缺
  可执行/参考报价语义、venue 和字段级 provenance。
- 数字货币同时有 `CRYPTO_JS_SPOT`、CME 比特币和持仓数据，并非只有 CME；
  仍缺多交易所、永续资金费、场所/网络身份和链上数据。

### 2.4 可复用原则

- `MarketInstrumentService` 和其缓存只作为接入参考，研究入口必须精确校验请求 symbol
  与返回身份，并写入新的 point-in-time 来源快照。
- StockSignal 的质量、结果和性能代码只复用算法骨架；股票动作、固定窗口和 freshness
  假设必须由资产插件替换。
- 导出器可复用 Markdown/HTML/DOCX/PDF 渲染，但股票标题、章节和路径必须参数化。
- 知识库保存可复用授权和建文档流程；新的 publication 审计对象仍是必要事实。
- 现有 `useStockAnalysisTask` 应泛化成统一任务状态机，不能在新工作台复制第三套轮询。

## 3. 权威资料结论

### 3.1 债券

事实：

- [中债收益率曲线编制说明](https://valuation.chinabond.com.cn/cbweb-mn/int/int_yield_syl_doc)体现了债券估值必须结合曲线和期限，而不是只看价格 K 线。
- [中债收益率曲线页面](https://yield.chinabond.com.cn/cbweb-pbc-web/pbc/more?locale=cn_zh)按工作日发布多类曲线；数据可用时间必须进入 point-in-time 快照。
- [中债数据使用提示](https://yield.chinabond.com.cn/cbweb-mn/yield_main?locale=CN)对派生产品、基准和相关用途设置许可要求。
- [美国财政部日度利率数据](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve)和[官方 XML/API 说明](https://home.treasury.gov/treasury-daily-interest-rate-xml-feed)可作为海外无风险曲线的权威来源。
- FINRA 的[债券尽调](https://www.finra.org/investors/insights/bond-investing-due-diligence)、[收益率与回报](https://www.finra.org/investors/insights/bond-yield-return)和[久期风险](https://www.finra.org/investors/alerts/duration-what-interest-rate-hike-could-do-your-bond-portfolio)强调票息、到期收益率、赎回条款、信用、流动性和利率风险。

推论：

债券建议必须以现金流、净价/全价、应计利息、YTM/YTW、久期、凸性、DV01、曲线、信用利差、流动性和条款为核心；仅用涨跌和新闻无法形成合格结论。

产品建议：

v1 支持有明确现金流和可靠估值的固定利率国债、政策性金融债和高质量信用债；可转债、浮息债、资产支持证券和复杂含权债分阶段开放。

### 3.2 基金

事实：

- [SEC 基金与 ETF 费用公告](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/mutual-fund-and-etf-fees-and-expenses-investor-bulletin)说明费用和交易成本会降低投资回报。
- [SEC ETF 网站披露要求](https://www.sec.gov/about/divisions-offices/division-investment-management/accounting-disclosure-information/adi-2025-15-website-posting-requirements)要求关注 NAV、市场价格、溢折价和买卖价差。
- [基金股东报告指南](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/updated-investor-bulletin-how-read-mutual-fund-or-etf-shareholder-report)覆盖长期收益、基准、持仓、换手和费用。
- [指数基金说明](https://www.investor.gov/introduction-investing/investing-basics/investment-products/mutual-funds-and-exchange-traded-4)指出追踪误差与成本会使基金偏离指数。
- 中国基金业协会的[公募基金高质量发展行动方案](https://www.amac.org.cn/xwfb/zjyw/202505/t20250508_26645.html)强调长期考核、基准约束和投资者盈亏，不鼓励短期排名。
- [证监会公募基金运作管理办法](https://www.csrc.gov.cn/csrc/c106256/c1653978/content.shtml)和[信息披露办法](https://www.csrc.gov.cn/csrc/c100028/c1000938/content.shtml)构成境内公募产品边界。

推论：

基金研究应先区分场内 ETF、开放式基金、货币基金、债券基金、指数基金和主动基金。ETF 可分析盘中价格和流动性；开放式基金只能按已公布 NAV 估值，不能伪造盘中可成交价格。

产品建议：

基金主期限采用 3/6/12 个月，报告展示费用后收益、基准超额、回撤、风格漂移、持仓集中和经理/规模稳定性；短期信号只能标记为“战术观察”，不得包装为基金评级。

### 3.3 期货

事实：

- [CME 期货入门](https://www.cmegroup.com/education/courses/introduction-to-futures.html)说明合约规格、到期、结算、最小变动和保证金是产品基本属性。
- [CME 逐日盯市说明](https://www.cmegroup.com/education/courses/introduction-to-futures/mark-to-market)体现了期货损益和现金流的逐日结算特征。
- [CFTC COT](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm)按交易者类别公布持仓；报告时点通常晚于统计时点，回测必须按实际发布时间使用。
- [CFTC 市场数据入口](https://www.cftc.gov/MarketReports/index.htm)和[COT 解释说明](https://www.cftc.gov/MarketReports/CommitmentsofTraders/ExplanatoryNotes/index.htm)可用于定义持仓数据语义。
- [中国金融期货交易所风险控制办法](https://www.cffex.com.cn/cn/ssxz/20230414/43079.html)体现涨跌停、保证金、持仓和强平等风险控制。

推论：

期货研究的对象必须是具体合约。连续合约可用于特征，不可直接作为评分成交标的；结果必须保存实际合约、换月规则、结算价和成本。

产品建议：

信号展示 `LONG/SHORT/NEUTRAL` 并映射为买入/卖出/持有；到期临近、流动性迁移、涨跌停或保证金数据缺失时统一 `AVOID`。

### 3.4 期权

事实：

- [OCC 期权风险披露文件](https://www.theocc.com/company-information/documents-and-archives/options-disclosure-document)是交易所期权风险的基础披露材料。
- [中金所股指期权合约交易细则](https://www.cffex.com.cn/cn/ssxz/20221214/43100.html)规定合约、保证金、行权与结算。
- [上交所期权交易规则](https://www.sse.com.cn/lawandrules/sselawsrules2025/option/c/c_20250610_10781448.shtml)覆盖到期、行权价调整、数据和交易规则；[风险披露与适当性文件](https://www.sse.com.cn/lawandrules/sselawsrules2025/option/c/c_20250610_10781469.shtml)要求明确复杂风险。
- [Cboe 期权计算器](https://www.cboe.com/optionsinstitute/tools/options-calculator/)和[Options Industry Council 的 IV/Greeks 资料](https://www.optionseducation.org/news/may-office-hours-faqs)体现隐含波动率、Delta、Gamma、Theta、Vega 等核心风险量。

推论：

“分析某个期权”必须确定标的、到期日、行权价、认购/认沽、合约乘数、行权方式和结算方式。期权价格方向不等于标的方向，不能用标的收益判断期权建议是否正确。

产品建议：

v1 只建议风险有限的单腿买方交易或平掉已有多头，禁止裸卖；建议由理论价值、IV/偏斜、Greeks、时间价值、流动性、盈亏平衡点和最大损失共同决定。

### 3.5 外汇

事实：

- [FX Global Code](https://www.globalfxc.org/fx-global-code/)当前版本提供覆盖伦理、治理、执行、信息共享、确认结算和风险管理的全球良好实践。
- [BIS 2025 三年期外汇调查](https://www.bis.org/statistics/rpfx25.htm)将外汇市场区分为即期、远期、掉期和期权，不应把它们作为同一种产品。
- [ECB 参考汇率](https://data.ecb.europa.eu/key-figures/ecb-interest-rates-and-exchange-rates/exchange-rates)和[数据说明](https://data.ecb.europa.eu/data/datasets/EXR/data-information)明确参考汇率是信息用途，不是可成交报价。

推论：

货币对必须明确基础货币/报价货币；做多 EUR/USD 是买 EUR、卖 USD。即期、远期、掉期和 CFD 的成本、期限和监管边界不同。

产品建议：

v1 先支持主要可交割即期货币对，使用可成交代理报价完成评分；参考汇率只做估值交叉检查。宏观利差、carry、估值、趋势、波动和事件风险分别评分。

### 3.6 数字货币

事实：

- [中国人民银行等部门 2021 年通知](https://m.safe.gov.cn/safe/2021/0924/19911.html)明确虚拟货币相关业务活动的境内监管边界。
- [CFTC 虚拟货币风险公告](https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/understand_risks_of_virtual_currency.html)提示高波动、市场操纵、平台、网络安全、欺诈和杠杆风险。
- [Coinbase Exchange API](https://docs.cdp.coinbase.com/exchange/introduction/welcome)将公开市场数据和需鉴权的交易 API 分离；[订单簿说明](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-book)强调序列、深度和 WebSocket 的实时性。
- [Kraken 市场分析 API](https://docs.kraken.com/api/docs/futures-api/charts/market-analytics)公开资金费、基差、持仓、清算、订单簿和波动等衍生品指标。
- [Bitcoin Core RPC](https://developer.bitcoin.org/reference/rpc/)与[Ethereum JSON-RPC](https://ethereum.org/developers/docs/apis/json-rpc/)提供可验证的链上节点数据入口。
- [CoinGecko API](https://docs.coingecko.com/index)可作为跨场所聚合元数据和历史数据来源，但不能替代具体交易场所报价。

推论：

同一代币在不同网络、交易所和产品上的价格、流动性、资金费和风险不同；`BTC` 不是足够的可交易资产标识。链上活跃度也不能直接等价为价格方向。

产品建议：

v1 区分 `token + network + venue + product_type + quote_currency`。现货和永续合约使用不同插件；中国大陆模式仅展示教育性研究且默认不生成可执行动作。

## 4. 开源项目评估

| 项目 | 可借鉴能力 | 许可证判断 | 本迭代用法 |
| --- | --- | --- | --- |
| [QuantLib](https://github.com/lballabio/QuantLib) | 固收现金流、曲线、期权定价和风险量 | [BSD 风格许可](https://raw.githubusercontent.com/lballabio/QuantLib/master/LICENSE.TXT) | 可作为算法参考或依赖候选，仍需 Python 运行和数值验收 |
| [AKShare](https://github.com/akfamily/akshare) / [文档](https://akshare.akfamily.xyz/) | 境内股票、基金、债券、期货、期权、外汇和数字货币数据适配 | MIT；接口稳定性和数据授权需逐接口核验 | 保留在适配器边界，加入契约测试、缓存、重试和备用源 |
| [OpenBB](https://github.com/OpenBB-finance/OpenBB) | 多提供方注册、标准化模型和扩展架构 | [AGPLv3](https://raw.githubusercontent.com/OpenBB-finance/OpenBB/develop/LICENSE) | 仅参考架构，未经法务批准不复制或集成代码 |
| [OpenFIGI](https://www.openfigi.com/api/documentation) | 全球证券标识映射 | API 条款和限流适用 | 全球标识预留当前 v3 适配，不作为中国 MVP 强依赖 |
| [py_vollib](https://github.com/vollib/py_vollib) | Black、Black-Scholes、BSM、IV 和 Greeks | MIT | 期权数值交叉验证候选，生产仍需边界和精度测试 |
| [CCXT](https://github.com/ccxt/ccxt) | 多交易所统一公开/私有 API | [MIT](https://raw.githubusercontent.com/ccxt/ccxt/master/LICENSE.txt) | 仅使用公开市场数据适配；本迭代不启用私有交易接口 |
| [Freqtrade](https://github.com/freqtrade/freqtrade) | 回测、dry-run、前视检测和费用建模模式 | [GPLv3](https://raw.githubusercontent.com/freqtrade/freqtrade/develop/LICENSE) | 仅参考验证方法，未经法务批准不集成代码 |

## 5. 六类资产差异矩阵

| 维度 | 债券 | 基金 | 期货 | 期权 | 外汇 | 数字货币 |
| --- | --- | --- | --- | --- | --- | --- |
| 唯一身份 | 代码+市场+发行人+到期 | 代码+份额类别+交易/销售场所 | 品种+交易所+合约月 | 标的+到期+行权价+方向+交易所 | 基础/报价+产品+场所 | 代币+网络+场所+产品+报价币 |
| 主要价值来源 | 票息、曲线、信用、条款 | 净值、持仓、基准、费用、经理 | 现货预期、基差、展期、供需 | 标的、波动率、时间、Greeks | 利差、carry、宏观、资本流动 | 采用、流动性、资金费、链上、代币经济 |
| 主要价格 | 净价/全价/估值 | NAV；ETF 市价 | 成交/结算价 | bid/ask/mid 与理论价 | 双边报价 | 场所特定双边报价 |
| 时间机制 | 付息、到期、赎回 | 净值公布、申赎；ETF 交易时段 | 到期、换月、逐日结算 | 到期、行权、Theta 衰减 | 24x5、交割日和隔夜 | 24x7、资金费、链上确认 |
| 默认结果 | 含息总回报/曲线超额 | 费用后 NAV 总回报/基准超额 | 可交易合约净收益/风险预算 | 实际 bid/ask 平仓或到期 P&L | 含 carry 的双边净收益 | 含费用/资金费的场所净收益 |
| 首要否决 | 条款/现金流/信用数据缺失 | NAV/基准/份额类型不清 | 合约/到期/流动性不清 | 合约链/报价/Greeks 不可靠 | 方向/报价时点/可交割性不清 | 场所/网络/产品/合规不清 |

## 6. 信号质量研究方法

### 6.1 防止虚假准确率

- 时间序列训练和验证必须保持先后顺序。[TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)明确指出普通随机切分会造成用未来训练、过去验证的问题。
- 重叠持有期使用 purge 和 embargo；发生修订的数据按实际发布时间入库。
- 每一次参数搜索和策略版本都进入试验注册表，不能只报告最优结果。
- 标签边界、入退价格、日历、缺失处理、基线、模型和校准 artifact 均在预测时版本化；
  不同 `head_spec_hash` 的样本不得事后混合或重贴标签。
- 采用简单基线：总是持有、总是观望、同期限动量、资产基准。
- 结果包含费用、点差、滑点、税费、展期、资金费、申赎或应计利息。

### 6.2 不能只看胜率

[scikit-learn 概率校准说明](https://scikit-learn.org/stable/modules/calibration.html)指出 Brier 和 log loss 同时反映校准与区分能力，因此需要联合查看：

- 行动信号精确率、召回率和样本数；
- 覆盖率、弃权率和不可评分率；
- Brier、log loss、可靠性图和置信度分箱；
- 平均/中位净收益、基准超额、最大回撤和尾部损失；
- 不同品种、期限、市场状态、流动性和成本分组的稳定性。

## 7. 反方证据和主要风险

1. **多资产并不意味着更多有效信号。** 数据覆盖扩张会同步扩大修订、许可、时区和标识错误。
2. **LLM 研报更流畅不代表预测更准确。** 数值结论必须来自可复现策略，LLM 只负责解释。
3. **免费数据可用于原型，不等于可用于商业生产。** 中债、交易所、聚合商和 API 均可能有再分发限制。
4. **单一“胜率”容易被观望比例和类别不平衡操纵。** 必须展示覆盖率、分母和净效用。
5. **衍生品方向正确仍可能亏损。** 时间价值、波动率、杠杆、保证金和基差会使标的方向与合约 P&L 分离。
6. **数字货币的地区合规可能直接否决产品能力。** 技术可实现不代表可以面向特定地区提供建议或交易导流。

## 8. 调研结论

行业最佳实践不是为六类资产复制一套股票提示词，而是建立统一的审计和报告框架，再为每类资产实现独立、可测试的领域插件。优先级应为：

1. 先解决身份、时点、数据许可和质量否决；
2. 再完成资产专属估值与风险；
3. 后生成可解释建议和研报；
4. 最后用真实未来数据、成本和基准决定是否开放方向信号。
