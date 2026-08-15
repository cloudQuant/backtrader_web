# 191E AI 外汇设计文档

## 1. 组件

```text
FxInstrumentResolver
  -> FxCalendar
  -> FxQuoteCollector
  -> FxMacroCollector
  -> FxCarryAnalyzer
  -> FxFeatureEngine
  -> FxQualityGate
  -> FxDecisionPolicy
  -> FxComplianceGate
  -> FxReportBuilder
  -> FxOutcomeEvaluator
  -> FxPromotionEvaluator

FxDailyShadowScheduler
  -> AssetResearchOrchestrator
```

## 2. 产品身份

[BIS 外汇调查定义](https://www.bis.org/statistics/triennialrep/2025survey_guidelinesoutstanding.pdf)区分即期、远期、FX swap、currency swap 和期权。规范 ID 示例：

```text
fx:ECB:EUR/USD:SPOT
fx:CFETS:USD/CNY:SPOT
fx:OFFSHORE:USD/CNH:SPOT
fx:VENUE:USD/CNY:NDF:3M
```

FX swap 是相反方向的近远端本金交换，不能与多期利息流 currency swap 混用。rolling CFD 不是标准即期，v1 拒绝进入 spot 路由。
未指定场所的参考货币对使用 `identity_level=ASSET`，只能输出不可执行研究；
指定场所的即期产品使用 `identity_level=PRODUCT`；远期/NDF 使用
`identity_level=CONTRACT`。`PRODUCT/CONTRACT` 必须包含 venue、报价/结算币和产品日历。

## 3. 时点

```python
class FxTimeContext(BaseModel):
    generated_at_utc: datetime
    data_cutoff_at: datetime
    session_date: date
    alignment_timezone: str
    bar_complete: bool
    market_status: Literal["OPEN", "CLOSED", "HOLIDAY", "MAINTENANCE"]
```

- 日线默认按 New York 17:00 完成，批次在 17:10 后；
- 夏令时对应北京时间次日 05:10，冬令时次日 06:10；
- 北京 19:00 任务是盘中快照，只读已完成 H1/H4；
- 周末标 `CLOSED`，不产生 stale 告警；
- 节假日使用两种货币和产品联合日历。

## 4. 特征

### 4.1 宏观

政策/OIS/国债曲线、实际利率、通胀、就业、增长、PMI、经常账户、贸易条件和事件意外值。修订数据保存 vintage，历史预测只读取当时版本。

### 4.2 carry

以实际远期点或远期价格计算净 carry，政策利率差只作为解释变量：

```text
forward_carry = direction * (forward_rate / spot_rate - 1)
net_carry = forward_carry - transaction_and_roll_cost
```

### 4.3 行情和微观结构

1/5/20/60 会话趋势、实现/下行/尾部波动、ATR、相关和风险状态；bid/ask、spread、深度、交易时段和流动性。COT 按实际发布时间入库。

## 5. 质量门控

### 5.1 `REJECTED`

- base/quote、产品、场所、价值日或时区不明；
- bid/ask 缺失、非正或 crossed；
- 当前 bar 未完成却被当成完成周期；
- 关键行情过期或异常 spread；
- 价格方向无法确认；
- 地区合规不允许方向建议。

### 5.2 `DEGRADED`

- 宏观、远期点、COT 或新闻缺失；
- 历史少于 252 根完整日线但高于研究下限；
- 只有参考汇率，没有具体 venue 双边报价；
- 交叉源偏差超过货币层级预警但未到拒绝阈值。

交叉源阈值按主要、次要、新兴货币版本化，不使用统一 bps。降级只输出中性/研究。

## 6. 决策、发布和策略

### 6.1 公共决策合同

外汇插件只产生公共字段和枚举：

```python
normalized_direction: Literal["LONG", "SHORT", "NEUTRAL", "INDETERMINATE"]
position_context: Literal["FLAT", "LONG", "SHORT", "UNKNOWN"]
trade_intent: Literal["OPEN", "ADD", "REDUCE", "CLOSE", "KEEP", "NONE"]
recommendation: Literal["BUY", "SELL", "HOLD", "AVOID"]
```

`market_view=NEUTRAL` 只能映射 `normalized_direction=NEUTRAL`，
`market_view=INDETERMINATE` 只能映射 `normalized_direction=INDETERMINATE`。质量为
`REJECTED` 时固定 `recommendation=AVOID`、
`normalized_direction=INDETERMINATE`、`trade_intent=NONE`。

### 6.1.1 `FxResearchDetails` 强类型 Schema

`ResearchDecision.asset_details` 在外汇分支只接受以下类型。总体架构最小字段保持原名
和语义，附加字段对应现有会话、双边报价、宏观、carry、事件、波动和成本页面：

```python
class FxResearchMetricReasonCodes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    carry_estimate: list[ReasonCode] = Field(default_factory=list)
    valuation_gap: list[ReasonCode] = Field(default_factory=list)
    spot_mid: list[ReasonCode] = Field(default_factory=list)
    forward_rate: list[ReasonCode] = Field(default_factory=list)
    forward_points: list[ReasonCode] = Field(default_factory=list)
    bid_ask_spread_bps: list[ReasonCode] = Field(default_factory=list)
    depth_notional: list[ReasonCode] = Field(default_factory=list)
    realized_volatility: list[ReasonCode] = Field(default_factory=list)
    policy_rate_differential: list[ReasonCode] = Field(default_factory=list)
    real_rate_differential: list[ReasonCode] = Field(default_factory=list)
    event_surprise: list[ReasonCode] = Field(default_factory=list)


class FxResearchDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["FX"]
    base_currency: str
    quote_currency: str
    product_type: Literal["SPOT", "FORWARD", "NDF"]
    quote_kind: Literal["EXECUTABLE_PROXY", "INDICATIVE", "REFERENCE"]
    carry_estimate: Decimal | None
    valuation_gap: Decimal | None
    liquidity_grade: Literal["MAJOR", "MINOR", "EMERGING", "UNKNOWN"]

    venue: str | None
    value_date: date | None
    session_date: date
    bar_complete: bool
    market_status: Literal["OPEN", "CLOSED", "HOLIDAY", "MAINTENANCE"]
    spot_mid: Decimal | None
    forward_rate: Decimal | None
    forward_points: Decimal | None
    bid_ask_spread_bps: Decimal | None
    depth_notional: Decimal | None
    realized_volatility: Decimal | None
    policy_rate_differential: Decimal | None
    real_rate_differential: Decimal | None
    event_surprise: Decimal | None
    macro_vintage_at: datetime | None
    metric_reason_codes: FxResearchMetricReasonCodes
```

Schema 校验器逐项要求：任何可空数值为 `null` 时，对应
`metric_reason_codes.<field>` 至少包含一个已注册 `COMMON.*` 或 `FX.*`；只有来源事实
确实为零时才能保存 `0`。缺远期点、宏观 vintage、深度或事件数据保持
`null + reason`，不得用零制造“无 carry/无风险/无事件”的结论。参考汇率可进入
`quote_kind=REFERENCE` 的研究详情，但不能冒充双边执行价。

该类型明确禁止 `market_view`、任何 `direction` 别名、`normalized_direction`、
`recommendation`、`position_context`、`trade_intent`、`confidence`、
`probabilities/prediction_heads`、`quality_status` 和 `actionability`。宏观、carry、
估值和趋势轴不能定义第二套外汇动作；权威动作与概率仍只属于公共
`ResearchDecision/PredictionHead`。

### 6.2 内部候选与发布投影

决策流水线先产生 `candidate_decision_json`，再由质量、晋级和地区门控产生
`published_decision_json`，两者不可互相覆盖：

```text
candidate = FxDecisionPolicy(features, point_in_time_snapshot)
published = FxPublishPolicy(candidate, quality, promotion_scope, compliance)
```

- `candidate_decision_json` 只能由影子评估器和授权管理员读取；
- `SHADOW/SUSPENDED/未登记` 均视为未晋级，普通用户固定收到
  `market_view=INDETERMINATE`、`actionability=RESEARCH_ONLY`、
  `recommendation=HOLD/AVOID`、`normalized_direction=INDETERMINATE`、
  `trade_intent=NONE`，且 `confidence/expected_return=null`、
  `primary_head_code=null`、`prediction_heads=[]`；
- 地区限制覆盖其他分支，固定收到
  `market_view=INDETERMINATE`、`actionability=REGION_RESTRICTED`、
  `recommendation=AVOID`、`normalized_direction=INDETERMINATE`、
  `trade_intent=NONE`，并写 `FX.REGION_RESTRICTED`；
- 只有精确 `promotion_scope_key` 为 `PROMOTED`，且质量为 `ELIGIBLE`、地区和产品
  capability 允许时，才将候选方向投影到普通用户结果；
- LLM、页面和导出只读取 `published_decision_json`，不能读取或猜测候选字段。

### 6.3 策略

```text
expected_net_return =
  macro_rate_edge
  + carry_edge
  + valuation_edge
  + trend_edge
  + positioning_edge
  - spread
  - slippage
  - financing
```

类别贡献、反方证据和风险分别保存。确定性策略先输出候选方向，再由质量、晋级和合规
依次覆盖发布投影。置信度来自样本外校准并受数据质量上限约束。

## 7. 结果

- `normalized_direction=LONG`：下一可执行 ask 入场、目标会话 bid 退出；
- `normalized_direction=SHORT`：下一可执行 bid 建仓、目标会话 ask 回补；
- 期限：1/5/20 个真实 FX session；
- 净收益包含 spread、滑点、佣金和 financing/roll；
- `normalized_direction=NEUTRAL` 是否正确由预测快照中的无交易带判断，与行动命中率分开；
- 按货币对、期限、流动性和波动状态分层。

参考汇率不能作为执行价。[ECB 数据说明](https://data.ecb.europa.eu/data/datasets/EXR/data-information)明确其信息用途。

### 7.1 多评价 head

同一预测、同一期限追加多个结果，禁止把所有指标塞进一个状态：

候选决定使用主 `PredictionHead` `fx.direction_pnl`，标签为
`LONG/SHORT/NEUTRAL`。`target_spec_version` 固定 base/quote、1/5/20
`FX_SESSION`、long 的 ask→bid、short 的 bid→ask、carry/roll/fee/slippage 和
版本化 no-trade band；`scoreability_rule_version` 固定缺报价、跨 session、假日和
最终化规则。head 同时冻结 `probability_model_version/probability_artifact_hash`、
`calibration_version/calibration_artifact_hash/training_cutoff_at`、
`baseline_code/baseline_version` 和 `primary_for_promotion=true`，并计算
`head_spec_hash`。`fx.action_utility`
和 `fx.risk_path` 是预注册经济结果 head，不参与该概率分布归一。

LONG/SHORT 分别要求对应方向成本后净收益超过冻结 no-trade band；否则标签为
NEUTRAL。不同 `head_spec_hash` 的结果不得合并到同一 Brier、基线或晋级 cohort。

| `outcome_kind` | 评价目标 | 主要输出 |
| --- | --- | --- |
| `fx.direction_pnl` | 成本后方向或无交易带是否正确 | realized class、Brier、命中和校准桶 |
| `fx.action_utility` | 候选动作相对 `KEEP/NONE` 基线的净效用 | bid/ask 收益、carry、成本、基准差 |
| `fx.risk_path` | 持有期路径风险 | 最大不利波动、最大有利波动、实现波动 |

唯一键为
`(prediction_id, horizon_code, outcome_kind, evaluator_version)`。每个 head 使用公共
`OutcomeStatus.PENDING/PARTIAL/SCORED/UNSCORABLE`；到期原因单列
`MaturityReason.HORIZON_REACHED`，不得使用 `MATURED` 作为状态。

- 未到目标会话为 `OutcomeStatus.PENDING`；
- 已到期但仍在等待允许延迟到达的组成数据时为 `OutcomeStatus.PARTIAL`，不进入指标分母；
- 字段齐全且公式完成为 `OutcomeStatus.SCORED`；
- 最终化 SLA 后仍缺可执行入/退价、carry 或风险路径时为
  `OutcomeStatus.UNSCORABLE`，并使用公共 `ReasonCode` 中的外汇命名空间码。

### 7.2 晋级作用域

```text
promotion_scope_key =
  SHA-256(canonical_json(PromotionScope))
```

注册表在 scope key 外独立冻结 `head_spec_hash`、target/scoreability/baseline、
模型与校准 artifact、training cutoff 和策略/模型/校准版本。

`INSTRUMENT_SPECIFIC` 只使用单一 `canonical_id`，需至少 200 条
`OutcomeStatus.SCORED` 行动信号。`POOLED` 只在产品、成本、特征和策略完全共享时使用，
需至少 5 个货币对、每个至少 20 条、总计至少 200 条，任一货币对不得超过 40%。
spot/forward/NDF/CFD 及 CNY/CNH 边界不可跨池。注册表、成绩单和发布开关都按完整 key
查询；不存在从池级或相邻货币对隐式继承晋级。

## 8. API 和页面

```json
{
  "asset_type": "fx",
  "canonical_id": "fx:ECB:EUR/USD:SPOT",
  "horizon_code": "5_fx_sessions",
  "position_context": "UNKNOWN",
  "bar_mode": "last_complete"
}
```

`FxPanel.vue` 显示 base/quote 大字说明、会话/cutoff、双边价、宏观差异、carry、事件、波动、成本和持仓动作矩阵。盘中分析带固定“未使用完整日线”标识。

普通用户 API 只序列化 `published_decision_json`。管理员影子证据接口须使用单独权限，
不得在相同 DTO、HTML、导出或客户端状态中携带 `candidate_decision_json`。

## 9. 合规门控

服务端按租户地区、运营主体和产品类型返回 `capability`。中国大陆模式：

- 允许汇率事实、宏观、估值和风险研究；
- 方向建议需独立法律批准开关；
- 禁止境外保证金平台开户、交易 API、密钥和订单；
- 不推荐杠杆或保证金规模。

地区拒绝的完整响应合同为：

```json
{
  "market_view": "INDETERMINATE",
  "recommendation": "AVOID",
  "actionability": "REGION_RESTRICTED",
  "normalized_direction": "INDETERMINATE",
  "position_context": "UNKNOWN",
  "trade_intent": "NONE",
  "confidence": null,
  "primary_head_code": null,
  "prediction_heads": [],
  "expected_return": null,
  "execution_disabled": true,
  "reason_codes": ["FX.REGION_RESTRICTED"]
}
```

`position_context` 原样保留请求中的公共枚举值；它不能改变其他固定字段。

[国家外汇管理局个人外汇管理办法](https://www.safe.gov.cn/safe/2022/0818/21330.html)和[网络炒汇风险提示](https://www.safe.gov.cn/beijing/2021/0928/1671.html)构成该门控的重要依据。

## 10. 来源

BIS、ECB、FRED/ALFRED、CFTC COT 为宏观/参考来源；具体可执行研究需合法 venue/dealer 双边数据。OANDA 等 API 的条款和再分发权单独登记；API 可访问不等于可商用展示。

## 11. 每日影子运行

`FxDailyShadowScheduler` 使用 `America/New_York`：

1. 审批静态清单在配置时展开成“一资产、一期限、一 schedule”，运行时不扫描市场；
2. 纽约 17:00 冻结 `analysis_cutoff_at` 和当日 `session_date`，17:10 触发检查；
3. 每个 schedule 以
   `run_key=SHA-256(schedule_id|schedule_version|scheduled_fire_at|cutoff|
   cutoff_policy_version|policy_version)` 去重并冻结完整配置；
4. 17:25、18:10 只重试该 schedule 的失败运行；
5. 20:00 对账和进程重启 catch-up 仍复用原 run/cutoff；只读
   `available_at <= analysis_cutoff_at` 的数据；
6. `decision_input_hash/prediction_key` 唯一冲突时返回已有不可变预测，不更新快照
   或决定；
7. 最终失败记录失败阶段、尝试次数和命名空间原因码。

周末和联合节假日不创建伪会话预测；调度缺口必须能从版本化日历审计。

## 12. `ReasonCode` 命名空间

外汇插件只返回公共注册表中的大写资产命名空间稳定码：
`FX.INSTRUMENT_AMBIGUOUS`、`FX.QUOTE_UNAVAILABLE`、`COMMON.DATA_STALE`、
`FX.QUOTE_INCONSISTENT`、`FX.BAR_INCOMPLETE`、
`FX.PRICE_CONVENTION_UNKNOWN`、`FX.CALENDAR_UNAVAILABLE`、
`FX.MACRO_INCOMPLETE`、`FX.FORWARD_POINTS_UNAVAILABLE`、
`COMMON.MODEL_NOT_PROMOTED`、`FX.REGION_RESTRICTED`、
`COMMON.SOURCE_LICENSE_BLOCKED`、`FX.RISK_NOT_MEASURABLE`。未知异常先映射到公共码并保留
内部诊断，不允许把异常文本或临时字符串写入 `reason_codes`。
