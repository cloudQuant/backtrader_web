# 191E AI 外汇需求文档

## 1. 业务目标

用户输入一个货币对和产品后，系统明确基础/报价方向、交易时段和结算方式，结合利差与 carry、宏观、估值、趋势、波动、流动性和事件，生成做多、做空或中性观点及买入、卖出、持有/观望建议、中文研报和历史质量。

## 2. 核心原则

- 报价统一为“1 单位 base 等于多少 quote”；
- `EUR/USD` 做多表示买 EUR、卖 USD；
- CNY/CNH、即期/远期/NDF/FX swap/期货/rolling CFD 都是不同产品；
- ECB 等参考汇率用于估值交叉检查，不是可执行价格；
- 24×5 日线必须有明确会话切点，周末停市不是数据过期；
- v1 不推荐杠杆、不连接境外保证金账户、不创建订单。

## 3. v1 范围

- 有合法双边报价、独立参考源和日历的主要可交割即期货币对；
- 远期和 NDF 在有远期点、价值日和结算规则后以专属能力开放；
- FX swap、currency swap、交易所外汇期货和 rolling spot CFD 不走即期策略；
- 中国大陆模式只开放汇率研究和依法批准产品的只读分析；买卖建议展示受服务端合规开关控制。

## 4. 身份和输入

```text
identity_level = ASSET | PRODUCT | CONTRACT
base_currency
quote_currency
instrument_type
venue
settlement_type
value_date
expiry
contract_multiplier
settlement_currency
price_convention
calendar_id
timezone
```

用户输入 `EURUSD` 时返回 `EUR/USD` 候选及产品/场所，不自动选择 OTC dealer、CFD 或期货。CNY/CNH 不合并。
未指定场所的参考货币对属于 `ASSET`，只能做不可执行研究；指定场所的即期产品属于
`PRODUCT`；有价值日或到期日的远期/NDF 属于 `CONTRACT`。`PRODUCT/CONTRACT`
必须同时具备场所、报价/结算币和产品日历。

## 5. 功能需求

| 编号 | 需求 |
| --- | --- |
| FX-FR-001 | 解析 base/quote、即期/远期/NDF/其他产品、场所、价值日和结算。 |
| FX-FR-002 | 维护 24×5 会话、时区、夏令时、节假日和产品日历。 |
| FX-FR-003 | 收集 bid/ask、已完成 OHLC、spread、参考汇率和市场状态。 |
| FX-FR-004 | 分析两国政策利率、曲线、通胀、增长、就业、经常账户和事件。 |
| FX-FR-005 | 以实际远期点/价格分析 carry、期限结构和跨币种基差。 |
| FX-FR-006 | 分析趋势、实现/尾部波动、相关、时段和微观流动性。 |
| FX-FR-007 | 按真实发布时间使用 COT、央行和宏观数据，修订值不回填。 |
| FX-FR-008 | 只使用公共 `normalized_direction/position_context/trade_intent/recommendation` 枚举输出方向、建议和持仓动作矩阵。 |
| FX-FR-009 | 生成十一个规定章节的中文研报。 |
| FX-FR-010 | 保存预测，并以 ask/bid、carry 和成本为每个 1/5/20 会话期限生成多个 `outcome_kind` 评价 head。 |
| FX-FR-011 | 展示按货币对、期限、波动状态、策略版本和 `promotion_scope_key` 分层的质量。 |
| FX-FR-012 | 身份、双边报价、完整 bar、时区、地区或许可失败时按公共安全发布合同拒绝建议。 |
| FX-FR-013 | 区分内部候选决定和普通用户发布决定；`SHADOW` 期间不得向普通用户暴露候选方向、概率或预期收益。 |
| FX-FR-014 | 每个纽约会话日执行可重放、可补跑且幂等的影子批次，固定 cutoff，不使用补跑时才出现的数据。 |

## 6. 建议和发布语义

### 6.1 公共枚举

本插件不得定义 `FLAT/NONE` 等资产私有方向值，只能使用总架构的公共枚举：

| 字段 | 允许值 | 外汇语义 |
| --- | --- | --- |
| `normalized_direction` | `LONG/SHORT/NEUTRAL/INDETERMINATE` | `LONG` 为买 base 卖 quote，`SHORT` 为卖 base 买 quote，`NEUTRAL` 为无方向，`INDETERMINATE` 为不得发布方向。 |
| `position_context` | `FLAT/LONG/SHORT/UNKNOWN` | 用户声明的当前持仓，不由模型推断。 |
| `trade_intent` | `OPEN/ADD/REDUCE/CLOSE/KEEP/NONE` | 只解释研究建议，不创建订单。 |
| `recommendation` | `BUY/SELL/HOLD/AVOID` | `SELL` 不自动等于新开空头；`AVOID` 表示数据、风险、许可或地区否决。 |

`market_view=NEUTRAL` 映射 `normalized_direction=NEUTRAL`；
`market_view=INDETERMINATE` 映射 `normalized_direction=INDETERMINATE`。

### 6.2 持仓解释

- `position_context=FLAT + normalized_direction=LONG` 在产品和地区允许时为
  `BUY + OPEN`；
- `position_context=LONG + normalized_direction=SHORT` 优先为 `SELL + CLOSE`，
  `position_context=SHORT + normalized_direction=LONG` 优先为 `BUY + CLOSE`；
- 同向已有仓默认 `HOLD + KEEP`；只有独立风险规则允许时才使用 `ADD/REDUCE`；
- `position_context=UNKNOWN` 时必须为 `trade_intent=NONE`；
- `position_context=FLAT + normalized_direction=SHORT` 只有
  `short_open_research_allowed=true` 时才可为 `SELL + OPEN`；否则
  `trade_intent=NONE`。中国大陆 FX capability 固定不允许开空研究动作。

所有组合均保持 `execution_disabled=true`，不推荐杠杆，也不连接账户或订单。

### 6.3 候选、SHADOW 和普通用户发布

1. 内部策略可以生成使用上述公共枚举的完整 `candidate_decision_json`，仅评估器和授权管理员可读；
2. 模型注册状态为 `SHADOW` 或该 `promotion_scope_key` 未晋级时，普通用户
   `published_decision_json` 固定为
   `market_view=INDETERMINATE`、`actionability=RESEARCH_ONLY`、
   `normalized_direction=INDETERMINATE`、`trade_intent=NONE`，质量允许时
   `recommendation=HOLD`，否则 `recommendation=AVOID`，并包含
   `COMMON.MODEL_NOT_PROMOTED`；
3. 只有精确作用域状态为 `PROMOTED`，且数据、产品和地区门控全部通过时，才可发布候选方向；
4. 地区限制优先级最高，普通用户响应必须固定为
   `market_view=INDETERMINATE`、`actionability=REGION_RESTRICTED`、
   `recommendation=AVOID`、`normalized_direction=INDETERMINATE`、
   `trade_intent=NONE`、`confidence/expected_return=null`、
   `primary_head_code=null`、`prediction_heads=[]`、
   `execution_disabled=true`，并包含 `FX.REGION_RESTRICTED`。

## 7. 数据要求

- 规范货币对、产品、场所、价格方向和日历；
- 新鲜 bid/ask、完整 OHLC、spread 和市场状态；
- 至少一个独立参考源；
- 政策利率、OIS/国债曲线、通胀、就业、增长、PMI、经常账户和事件；
- 实际远期点/价格用于 carry；
- COT、新闻、来源、发布时间和修订版本；
- dealer/venue、费用、融资/roll 和结算风险。

OTC 经纪商 tick volume 不得称全市场成交量，政策利率差不得冒充可交易远期点。

`reason_codes` 只引用公共 `ReasonCode` 注册表中的外汇命名空间稳定码。v1 至少登记：
`FX.INSTRUMENT_AMBIGUOUS`、`FX.QUOTE_UNAVAILABLE`、`COMMON.DATA_STALE`、
`FX.QUOTE_INCONSISTENT`、`FX.BAR_INCOMPLETE`、`FX.PRICE_CONVENTION_UNKNOWN`、
`FX.CALENDAR_UNAVAILABLE`、`FX.MACRO_INCOMPLETE`、
`FX.FORWARD_POINTS_UNAVAILABLE`、`COMMON.MODEL_NOT_PROMOTED`、
`FX.REGION_RESTRICTED`、`COMMON.SOURCE_LICENSE_BLOCKED` 和
`FX.RISK_NOT_MEASURABLE`。API 传输层错误码仍使用总体架构定义的大写错误码，
不得把二者混成新的自由文本状态。

## 8. 研报要求

1. 产品身份、报价方向和结算；
2. 方向、建议、期限、置信度和持仓；
3. 趋势、波动和技术状态；
4. 两国宏观与货币政策差异；
5. carry、远期曲线和基差；
6. 机构头寸、事件和新闻；
7. 流动性、spread、融资和可执行成本；
8. 多头/基准/空头情景、催化剂和失效；
9. 杠杆、对手方、结算和地区合规；
10. 数据质量、来源和截止时间；
11. 历史预测、期限质量和样本。

## 9. 非功能与合规

- 所有时点存 UTC，同时保存 `session_date` 和 `alignment_timezone`；
- 纽约 17:00 日线考虑夏令时；北京时间 19:00 分析只能用已完成 H1/H4 并标盘中；
- 缺宏观/COT/新闻不得补 0；
- 双边报价和方向计算用 `Decimal`；
- 遵循 [FX Global Code](https://www.globalfxc.org/fx-global-code/)的良好实践和风险披露；
- 中国大陆不接入境外保证金平台开户、API key、交易或导流，上线买卖建议前完成法律审查。

### 9.1 每日影子调度和幂等

- 版本化审批货币对清单只用于配置时展开为“一资产、一期限、一 schedule”，运行时
  不发现或扫描全市场；
- 调度器使用 `America/New_York` 时区，每个有效 FX `session_date` 以纽约
  17:00 为 `analysis_cutoff_at`，17:10 触发检查；夏令时由时区数据库处理，
  不写死 UTC 偏移；
- `run_key=SHA-256(schedule_id|schedule_version|scheduled_fire_at|cutoff|
  cutoff_policy_version|policy_version)` 全局唯一，运行冻结完整 schedule 配置；
- 初次失败在 17:25、18:10 重试，20:00 对账只补该 schedule 的失败运行；
  服务重启在下一 cutoff 前执行同一 `run_key` 的 catch-up；
- 补跑保持原 `analysis_cutoff_at` 和 point-in-time 过滤，只允许
  `available_at <= analysis_cutoff_at`，不得用补跑期间发布的数据改写候选结论；
- 相同 `decision_input_hash/prediction_key` 使用唯一约束和幂等 upsert，只返回已有
  不可变预测；持仓、产品、快照、capability 或版本变化必须形成新预测；
  最终失败保留运行证据和命名空间 `ReasonCode`，不得伪造成功样本。

### 9.2 多 head 结果和晋级作用域

每个候选预测至少包含一个主 `PredictionHead`：
`head_code=fx.direction_pnl`，标签为 `LONG/SHORT/NEUTRAL`，并冻结目标定义、
`target_spec_version/scoreability_rule_version`、价格/成本/no-trade band、
概率模型与 artifact、校准 artifact/训练 cutoff、基线版本和 `head_spec_hash`。
非空 head 集合只能有一个
`primary_for_promotion=true`，`primary_head_code` 必须指向它。

每个预测和期限至少生成 `fx.direction_pnl`、`fx.action_utility`、
`fx.risk_path` 三个 `outcome_kind`；后两者是预注册经济结果 head，不与方向概率混合。
各结果独立使用公共
`OutcomeStatus=PENDING|PARTIAL|SCORED|UNSCORABLE`，到期原因另存
`MaturityReason`；1/5/20 会话正常到期使用
`MaturityReason.HORIZON_REACHED`，不得创造 `MATURED` 状态。任何成绩分母只含
`OutcomeStatus.SCORED`，并公开 `OutcomeStatus.PARTIAL`、
`OutcomeStatus.UNSCORABLE` 的数量和原因。

`promotion_scope_key` 是规范化公共 `PromotionScope` 的 SHA-256，scope 至少固定
资产、产品/样本池、`signal_head` 和期限；head spec、target/scoreability/baseline、
策略、模型、artifact 与校准版本由注册表唯一键/证据的独立列固定：

- `promotion_scope_type=INSTRUMENT_SPECIFIC`：只使用该 `canonical_id` 的至少 200 条成熟行动信号；
- `promotion_scope_type=POOLED`：仅允许同一产品类型、价格/成本规则、特征合同和策略共享的货币对合并；
  至少 200 条成熟行动信号、至少 5 个货币对、每个至少 20 条且任一货币对不超过 40%；
- spot、forward、NDF、CFD 不得互池，CNY 与 CNH 不得互相替代；
- 聚合和各个满足最小样本的货币对切片均须报告；任一作用域晋级不得自动传播到其他 key。

## 10. 完成条件

- FX-FR-001 至 014 全部验收；
- EUR/USD、USD/JPY、CNY/CNH、盘中/日终、夏/冬令时和周末场景覆盖；
- 技术完成后在允许地区以影子模式运行，普通用户仍只看到安全发布结果。
