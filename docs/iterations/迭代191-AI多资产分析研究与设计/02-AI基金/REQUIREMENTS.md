# 191B AI 基金需求文档

## 1. 业务目标

用户输入一只基金或基金份额后，系统先识别基金类型和交易机制，再以正式 NAV、业绩比较基准、费用、持仓、风险、管理稳定性和流动性为核心，生成买入、卖出、持有或暂不参与建议、中文研报及历史预测质量。

## 2. 首要原则

- ETF 场内交易、开放式基金申赎、货币基金和 QDII 不是同一种执行方式；
- 相同基金的 A/C/I/ETF 等份额类别是不同资产；
- 第三方估算净值不得代替官方 NAV；
- “基金长期质量”和“当前进入时点”分开评价；
- 短期研究信号不得包装成公开基金评级或未来收益保证。

## 3. v1 范围

### 3.1 支持

- 境内公募 ETF、LOF、普通开放式基金、货币基金、债券基金和 QDII；
- 美国注册 ETF，在取得合法价格、NAV、费用和持仓数据后开放；
- 指数基金与主动基金使用不同特征和基准逻辑。

### 3.2 仅研究

- 杠杆/反向 ETF、商品期货基金、复杂结构和私募基金；
- 成立不足 36 个月的基金可生成研究信号，但不得显示为平台评级；
- 正式基准、费用或份额身份缺失时只展示事实，主建议为 `AVOID`。

## 4. 身份和输入

规范身份：

```text
canonical_id
identity_level
jurisdiction
fund_id
share_class_id
share_class_name
venue_if_traded
ticker/local_code
fund_type
currency
manager
custodian
inception_date
official_benchmark_id
dealing_frequency
subscription_cutoff
redemption_cutoff
nav_calendar
```

搜索候选使用 `candidate_kind=FUND_PRODUCT/SHARE_CLASS/LISTING`；持久化身份使用公共
`identity_level=PRODUCT`，并通过 `fund_identity_kind` 保存基金专属类型：

- `candidate_kind=FUND_PRODUCT`：基金产品搜索结果，只用于继续选择份额或上市实例，
  不持久化为 `InstrumentIdentity`，不可启动分析；
- `fund_identity_kind=SHARE_CLASS`：开放式、货币、债券和 QDII 基金的具体份额类别；
  `venue` 必须为空，`dealing_channel`、申赎截止时间和 NAV 日历必填；
- `fund_identity_kind=LISTING`：ETF、LOF 和封闭式基金的场内实例，`venue` 必填。

用户输入代码、名称、管理人或全球标识后，系统必须展示份额类别、场所、费用和交易机制候选。不同份额不得按名称合并；同一产品存在 A/C/ETF 等多个候选时返回 `FUND.SHARE_CLASS_AMBIGUOUS`。规范 ID 示例为 `fund:share_class:CN:000001:A:CNY` 和 `fund:listing:XSHG:510300:ETF:CNY`。

### 4.1 预门控采集合同

搜索与采集先生成 `RawFundIdentityCandidate` 和 `RawFundSnapshot`。正式基准、官方 NAV 及 NAV 日期、费用各分项、持仓及 `holdings_as_of`、申赎状态、场内价格和 PCF/IOPV 在原始模型中均允许为空。每个叶子字段必须保存 `provenance`、`observed_at`、`published_at`、`available_at` 和 `retrieved_at`；来源没有事实发生或发布时间时前两者可以为空，缺失证据仍需记录来源、可用和获取时点。

原始候选/快照必须在门控前以内容哈希不可变落库。质量门控只读该快照并产出稳定、有序的 `COMMON.*` / `FUND.*` `ReasonCode`；只有类型所需关键字段通过后才构造非空 `PostGateFundSnapshot`。缺 official benchmark、NAV、fees 或 holdings 是业务质量结果，不得在原始 Pydantic 模型构造时返回 422 或冒泡为 500。

原始候选不改变现有映射：`FUND_PRODUCT` 仍只用于搜索；
`fund_identity_kind=SHARE_CLASS/LISTING` 都仍映射公共
`identity_level=PRODUCT`。门控失败时保留 `raw_candidate_id/raw_snapshot_id`，
并发布 `quality_status=REJECTED`、`actionability=INSUFFICIENT_DATA`、
`market_view=INDETERMINATE`、`normalized_direction=INDETERMINATE`、
`recommendation=AVOID`、`trade_intent=NONE`；杠杆/反向等已识别专属类型保持
`quality_status` 为 `ELIGIBLE` 或 `DEGRADED`，发布
`actionability=RESEARCH_ONLY`、
`trade_intent=NONE`。

## 5. 功能需求

| 编号 | 需求 |
| --- | --- |
| FUND-FR-001 | 解析基金、份额类别、交易场所、基金类型和正式基准。 |
| FUND-FR-002 | 按 ETF、开放式、货币、债券、QDII 和特殊基金路由分析。 |
| FUND-FR-003 | 计算 NAV 总回报、基准净超额、波动、回撤、Sortino/Sharpe 和滚动稳定性。 |
| FUND-FR-004 | 分析持仓集中、行业/国家/币种暴露、风格漂移及披露滞后。 |
| FUND-FR-005 | 分析管理人、基金经理任期、团队变化、规模和资金流。 |
| FUND-FR-006 | 按份额类别计算持续费用、申赎费用及场内点差/滑点。 |
| FUND-FR-007 | ETF 分析 NAV/IOPV、溢折价、PCF、申赎状态、流动性和跟踪质量。 |
| FUND-FR-008 | 输出结构质量分、战术进入分、建议、期限、概率、质量和失效条件。 |
| FUND-FR-009 | 生成十五个规定章节的研报，支持导出和保存。 |
| FUND-FR-010 | 门控前保存不可变原始候选和字段级来源快照，再保存每日预测及 ETF/开放式基金各自的真实执行和结果。 |
| FUND-FR-011 | 展示按基金类型、份额、基准、期限和策略版本分层的成绩单。 |
| FUND-FR-012 | 暂停申购/赎回、极端溢价、缺正式基准/NAV/费用/持仓或 NAV 过期时保留审计快照并返回 `quality_status=REJECTED + actionability=INSUFFICIENT_DATA + AVOID/NONE`；专属复杂基金使用 `ELIGIBLE/DEGRADED + RESEARCH_ONLY`，不得抛领域缺失型 422/500。 |
| FUND-FR-013 | 结构化决策只使用公共 `normalized_direction`、`position_context`、`trade_intent`、`recommendation` 枚举，并区分候选决策与面向普通用户的发布决策。 |
| FUND-FR-014 | 按基金类型保存 ETF 市场回报、开放式 NAV 回报、货币现金超额、QDII NAV/汇率和交易事件结果头，统一使用 `OutcomeStatus`、`MaturityReason` 和资产原因码。 |
| FUND-FR-015 | 按交易机制和地区截止时点每日运行影子分析；重跑、补 NAV 和历史回补必须幂等且遵守 point-in-time。 |
| FUND-FR-016 | 模型晋级按 `promotion_scope_key` 隔离池化与单基金范围，按经济基金产品计算样本集中度。 |
| FUND-FR-017 | 机器原因使用稳定 `ReasonCode`：通用原因属于 `COMMON.*`，基金专属原因属于 `FUND.*`，展示文案由原因码本地化。 |

## 6. 建议语义

`quality_status` 与 `actionability` 是正交公共字段，不得互相塞值：

```text
quality_status = ELIGIBLE | DEGRADED | REJECTED
actionability  = ACTIONABLE | RESEARCH_ONLY | INSUFFICIENT_DATA | REGION_RESTRICTED
```

- 地区禁止：保留独立数据质量值，`actionability=REGION_RESTRICTED`；
- 关键数据、许可或风险失败：`quality_status=REJECTED` 且
  `actionability=INSUFFICIENT_DATA`；
- 专属复杂基金、`DEGRADED` 或模型未晋级：质量只取
  `ELIGIBLE` 或 `DEGRADED`，`actionability=RESEARCH_ONLY`；
- 已晋级且质量合格：`quality_status=ELIGIBLE` 且
  `actionability=ACTIONABLE`。

发布覆盖优先级为 `REGION_RESTRICTED > INSUFFICIENT_DATA > RESEARCH_ONLY >
ACTIONABLE`。`NONE` 只允许作为 `trade_intent`，绝不是合法 `actionability`；
`RESEARCH_ONLY` 也绝不是合法 `quality_status`。

系统不得定义基金私有动作枚举。结构化决策只允许以下公共字段：

```text
normalized_direction = LONG | SHORT | NEUTRAL | INDETERMINATE
position_context     = FLAT | LONG | SHORT | UNKNOWN
trade_intent         = OPEN | ADD | REDUCE | CLOSE | KEEP | NONE
recommendation       = BUY | SELL | HOLD | AVOID
```

v1 为 long-only 研究产品：正优势与 `FLAT/LONG` 分别映射为 `LONG/.../OPEN|ADD/BUY`；负优势只有在 `position_context=LONG` 时映射为 `SHORT/LONG/REDUCE|CLOSE/SELL`；空仓负向候选只能保存为 `SHORT/FLAT/NONE/HOLD`，不得对普通用户发布 `SELL`；中性为 `NEUTRAL/.../KEEP|NONE/HOLD`；硬门控失败为 `INDETERMINATE/.../NONE/AVOID`。

`position_context=UNKNOWN` 时，候选层可以保存“若空仓/若持有”的条件分支，发布层 `trade_intent=NONE`。输入 `SHORT` 返回 `INDETERMINATE / SHORT / NONE / AVOID` 和 `COMMON.POSITION_CONTEXT_UNSUPPORTED`。所有结果固定 `execution_disabled=true`。

### 6.1 ETF/LOF

- `BUY/OPEN|ADD`：下一可交易时段买入或增持研究建议；
- `SELL/REDUCE|CLOSE`：减持/卖出已有份额；
- `HOLD/KEEP|NONE`：优势落入无交易区间、维持已有份额或空仓观望；
- `AVOID/NONE`：溢折价、流动性、PCF、申赎或数据门控失败。

### 6.2 普通开放式基金

- `BUY/OPEN|ADD`：在下一可申购估值日按适用 NAV 申购，不是开盘买入；
- `SELL/REDUCE|CLOSE`：在下一可赎回估值日赎回已有份额，不是盘中卖出；
- `HOLD/KEEP|NONE`：维持份额或空仓观望；
- 暂停申购/赎回时只给研究结论，`trade_intent=NONE`。

默认长期研究期限为 60 个基金估值日；ETF 可选 5/20/60 个交易日，开放式基金可选 20/60/120 个估值日。

### 6.3 影子发布双层合同

- `candidate_decision_json` 保存真实策略四元组，只供管理员、评估器和审计任务读取；
- 模型为 `SHADOW` 时，普通用户、LLM、前端、导出和知识库只能读取 `published_decision_json`；
- 影子候选若数据合格，发布层固定为
  `quality_status` 为 `ELIGIBLE` 或 `DEGRADED`、
  `actionability=RESEARCH_ONLY`、
  `INDETERMINATE / 原持仓上下文 / NONE / HOLD`，原因码为
  `COMMON.MODEL_NOT_PROMOTED`；
- 影子候选若硬门控失败，发布层为 `quality_status=REJECTED`、
  `actionability=INSUFFICIENT_DATA`、
  `INDETERMINATE / 原持仓上下文 / NONE / AVOID`；
- 只有与已批准 `promotion_scope_key` 完全匹配的模型可以把候选四元组发布给普通用户，任何接口都不得泄露影子候选。

## 7. 每日运行与结果合同

### 7.1 影子运行

| 分组 | 启动时间 | 数据截止 |
| --- | --- | --- |
| 中国 ETF/LOF | 每个交易日 `19:10 Asia/Shanghai` | 当日 19:00 |
| 中国开放式/货币/债券基金 | 每个 NAV 日 `23:30 Asia/Shanghai` | 当日 23:15 |
| 美国 ETF | 每个交易日 `18:30 America/New_York` | 当日 18:15 |

次日 `08:30 Asia/Shanghai` 只为前一轮缺少官方 NAV 的中国开放式任务执行 catch-up，截止时间为 08:15；它使用新的截止时间和预测键，不能回写原截止时间下的预测。QDII 按基金合同的境内外日历和 NAV 延迟运行，不把合同允许的延迟误判为过期。

v1 每条 schedule 只绑定一个已确认 `canonical_id`；有许可的静态基金清单只在配置阶段展开成多条 schedule，运行时不得扫描市场或按 `venue_scope/universe` 扩展。

公共访问主体固定为
`access_principal=owner_scope|coalesce(user_id,"SYSTEM")`。
`run_key=SHA-256(schedule_id_or_manual_scope_with_access_principal|schedule_version|scheduled_fire_at|cutoff_at|cutoff_policy_version|policy_version)`，重复触发只在同一访问主体内关联既有运行。冻结输入生成 `decision_input_hash`，`prediction_key=SHA-256(access_principal|decision_input_hash)`；只有访问主体和输入都相同时才复用预测，`owner_scope` 相同但 `user_id` 不同绝不能复用。任一快照、持仓上下文或版本变化时新增预测。历史回补显式传入历史截止时间，只读取当时已可用数据。

### 7.2 多结果头

每个预测根据基金类型选择一个主结果头，并可附加事件结果：

```text
fund.etf_market_return
fund.open_end_nav_return
fund.money_market_cash_return
fund.qdii_nav_fx_return
fund.dealing_event
```

结果唯一键为 `(prediction_id, horizon_code, outcome_kind, evaluator_version)`。`fund.etf_market_return` 使用可执行市场价，`fund.open_end_nav_return` 使用 cutoff 对应 NAV，货币和 QDII 使用各自专属基准；不同结果头不得互相替代。

每个候选预测按基金类型只选择一个方向主 `PredictionHead`：
`fund.etf_market_return`、`fund.open_end_nav_return`、
`fund.money_market_cash_return` 或 `fund.qdii_nav_fx_return`。标签统一为
`POSITIVE_EXCESS/NEGATIVE_EXCESS/NEUTRAL`，并完整继承公共
`PredictionHead`：冻结 `target_spec_version/scoreability_rule_version`、
`probability_model_version/probability_artifact_hash`、
`calibration_version/calibration_artifact_hash/training_cutoff_at`、
`baseline_code/baseline_version` 和可复算 `head_spec_hash`。
`fund.dealing_event` 可作为独立
`EVENT/NO_EVENT` 非主 head，不能与方向概率混合。

任何 `head_spec_hash` 或 target、scoreability、概率/校准 artifact、基线版本不同的
记录必须分 cohort；聚合器遇到 mixed-spec cohort 必须拒绝，不能重贴标签后合并
Brier、基线或晋级分母。

每个结果头的 `OutcomeStatus` 统一为 `PENDING | PARTIAL | SCORED | UNSCORABLE`：未到成熟时点为 `PENDING`，已取得部分真实数据但尚不能完成全口径为 `PARTIAL`，完整评分为 `SCORED`，按预测时冻结规则永久无法取得合法结果为 `UNSCORABLE`。

成熟原因与结果状态分离，`MaturityReason` 使用 `HORIZON_REACHED | EXPIRY | MATURITY | CALL | REDEMPTION | ROLL | DELISTING` 等公共枚举。未成熟、价格/NAV、基准和 cutoff 缺失分别使用 `COMMON.OUTCOME_NOT_MATURED`、`COMMON.OUTCOME_PRICE_MISSING`、`COMMON.OUTCOME_BENCHMARK_MISSING`、`FUND.OUTCOME_CUTOFF_UNRESOLVED`。

### 7.3 晋级范围

```text
promotion_scope_key = SHA-256(canonical_json(PromotionScope {
  scope_type, asset_type=fund, instrument_class, canonical_id, venue,
  product_type, signal_head, horizon_code,
  scope_parameters={fund_type, jurisdiction, execution_mechanism, benchmark_family}
}))
```

- `policy_version/model_version/calibration_version` 是模型注册表唯一键的独立列；
- 两类 scope 都至少需要 200 个已成熟、可评分的行动主结果头、至少 60 个去重
  `cutoff_date`、3 个按冻结 `FundRegimeSpec` 确定的市场状态，并满足时间顺序
  walk-forward、purge/embargo 和至少 60 个交易日/估值日前瞻影子期；
- `POOLED`：额外覆盖至少 5 个经济基金产品组；任一组占比不超过 40%，同时报告
  HHI。同一产品的 A/C/I、ETF/联接或多场所实例不得重复放大样本；
- `INSTRUMENT_SPECIFIC`：键中必须包含具体 `canonical_id`，允许单基金占比 100%，
  不套 5 产品组和 40% 集中度，但晋级只解锁该份额/上市实例，不能外推；
- 两种范围的样本、指标、审批和回退互相隔离，且都必须满足总计划规定的前向影子期。

每个 scope 的晋级证据必须在读结果前冻结正式基准总回报
`regime_source_id`、数据 vintage 策略、日历、`evaluation_start/end`、状态算法及参数、
`regime_version`、主 head、朴素基线、成本模型和 bootstrap 参数。三个
`BULL/BEAR/SIDEWAYS` 状态各至少 20 个独立成熟日期；若发布声明为
`LONG_TERM_QUALITY`，冻结区间还必须各含一个至少连续 60 个适用估值日的 BULL 和
BEAR 段。短期模型登记为 `TACTICAL_SIGNAL`，即使晋级也不得显示为基金评级。

主指标为成本后 `delta_net_utility=model-baseline`。机器通过条件为：模型平均成本后
净效用 `> 0`；10,000 次 95% moving-block bootstrap 的
`delta_net_utility` 区间下界 `>= 0`，block 至少覆盖最大标签重叠期；同 target、同
cohort 主概率 head 的 `Brier Skill Score > 0`；最大回撤不超过基线加预注册容忍度；
全部适用费用进入净效用，且 1.5 倍成本压力下平均净效用仍 `>= 0`。基线、seed、
block 长度、回撤容忍度、calibration gate 和风险切片阈值都必须版本化，不能验收时
人工解释。

## 8. 必需数据

本节字段是对应基金类型进入 `PostGateFundSnapshot` 和可行动分析的必需数据，不是
`RawFundSnapshot` 的构造前提。任何缺失都先保存原始审计快照，再由 gate 决定
`quality_status` 和 `actionability`。

- 基金、份额、类型、成立、管理人、托管人、经理和任期；
- 投资目标、范围、风险等级和正式业绩比较基准；
- 官方 NAV、累计 NAV、分红和拆分；
- 管理、托管、销售服务、申购和赎回费用；
- AUM、份额、资金流、申购/赎回/暂停状态；
- 招募说明书、合同、定期报告及版本；
- 持仓、资产配置和 `holdings_as_of`；
- 基准总回报。

ETF 额外要求 OHLCV、bid/ask、NAV、IOPV、溢折价、PCF、最小申赎单位、现金替代、申赎限制、指数和跟踪质量。

## 9. 研报要求

1. 基金身份、份额类别、类型和交易机制；
2. 建议、行动资格、持有期限和执行方式；
3. 投资目标、合同约束和正式基准；
4. NAV、累计 NAV、分红和场内价格；
5. 历史总回报与基准净超额；
6. 波动、回撤、下行和风险调整表现；
7. 持仓、配置、集中、风格和漂移；
8. 基金经理、团队、任期和组织变化；
9. 费用、税务和份额类别差异；
10. 规模、资金流、申赎和流动性；
11. ETF 溢折价、PCF、IOPV 和跟踪质量；
12. 情景、催化剂、风险和失效条件；
13. 数据质量、披露滞后和来源；
14. 历史预测和分层统计；
15. 合规风险提示。

## 10. 非功能与合规

- 官方 NAV、第三方估算和场内市价必须分字段显示；
- 同一原始载荷和 gate 版本必须产生相同 `ReasonCode` 顺序与安全发布结果；
- `prediction_key` 必须包含公共 `access_principal`；不同用户即使具有相同
  `owner_scope/decision_input_hash` 也不得复用预测、候选或发布决定；
- 原始快照接受领域字段空值；缺正式基准、官方 NAV、费用或持仓由质量门控处理，
  API 不得将来源缺失返回为 Pydantic 422 或未捕获 500；
- 所有持仓显示 `holdings_as_of`，不得称过期披露为“当前持仓”；
- 费用按具体份额类别和持有期计算；
- 服务端只保存稳定的 `COMMON.*` 或 `FUND.*` `ReasonCode`；人类可读中文由版本化映射生成，不把异常文本当机器码；
- 建议不得使用“保证、最好、稳赚、强烈买入”等误导性语言；
- 个性化资产配置、自动申赎和“适合你”表述不在 v1；
- 数据源、基金评价和投顾业务在上线前完成许可/备案评估。

## 11. 完成条件

- FUND-FR-001 至 017 全部有自动化验收；
- ETF、开放式、货币、债券和 QDII 各有受控样例；
- 缺正式基准、NAV、fees、holdings 的夹具先保存 raw 审计快照并发布
  `REJECTED + INSUFFICIENT_DATA + AVOID/NONE`；专属复杂基金的
  `quality_status` 为 `ELIGIBLE` 或 `DEGRADED` 且
  `actionability=RESEARCH_ONLY`，并且无领域缺失型 422/500；
- 不同交易机制的执行和评分不混用；
- 方向模型先以 `SHADOW` 运行并满足总计划晋级门槛。
