# 191B AI 基金设计文档

## 1. 设计依据

[SEC ETF 披露要求](https://www.sec.gov/about/divisions-offices/division-investment-management/accounting-disclosure-information/adi-2025-15-website-posting-requirements)要求关注 NAV、市场价、溢折价和价差；[基金股东报告指南](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/updated-investor-bulletin-how-read-mutual-fund-or-etf-shareholder-report)覆盖长期回报、基准、持仓、换手和费用。中国基金业协会强调长期和基准评价，因此 v1 不复制股票短周期财务/新闻模型。

## 2. 类型路由

```text
FundIdentitySourceAdapter
  -> RawFundIdentityCandidate
  -> FundDataCollector
  -> ImmutableRawFundSnapshotStore
  -> FundQualityGate
      -> PostGateFundSnapshot（仅关键字段通过）
      -> GateResult + RawFundSnapshot（拒绝或仅研究）
  -> FundTypeRouter
      -> EtfAnalyzer
      -> OpenEndFundAnalyzer
      -> MoneyMarketFundAnalyzer
      -> BondFundAnalyzer
      -> QdiiAnalyzer
      -> ResearchOnlySpecialFundAnalyzer
  -> FundDecisionPolicy
  -> FundPublicationPolicy
  -> FundReportBuilder
  -> FundOutcomeEvaluator

FundShadowScheduler -> AssetResearchRunService -> 上述流水线
```

原始候选和原始快照在任何质量判断、类型分析或特征计算前不可变落库。门控从已提交快照识别交易机制；无法识别类型时产出稳定拒绝原因，不运行“通用基金算法”。

## 3. 核心数据结构

```python
T = TypeVar("T")

class FieldProvenance(BaseModel):
    source_id: str
    source_record_id: str | None
    source_version: str | None
    license_policy_version: str
    payload_hash: str

class RawField(BaseModel, Generic[T]):
    value: T | None = None
    provenance: FieldProvenance
    observed_at: datetime | None
    published_at: datetime | None
    available_at: datetime
    retrieved_at: datetime

class RawFundIdentityCandidate(BaseModel):
    raw_candidate_id: UUID
    candidate_kind: RawField[Literal["FUND_PRODUCT", "SHARE_CLASS", "LISTING"]]
    candidate_id: RawField[str]
    display_name: RawField[str]
    fund_id: RawField[str]
    share_class_id: RawField[str]
    local_code: RawField[str]
    fund_type: RawField[str]
    venue: RawField[str]
    currency: RawField[str]

class RawFundSnapshot(BaseModel):
    raw_snapshot_id: UUID
    raw_candidate_id: UUID
    cutoff_at: datetime
    official_benchmark: RawField[str]
    nav: dict[str, RawField[Any]]
    fees: dict[str, RawField[Any]]
    holdings: dict[str, RawField[Any]]
    dealing: dict[str, RawField[Any]]
    market: dict[str, RawField[Any]]

class EligibleFundIdentity(BaseModel):
    canonical_id: str
    identity_level: Literal["PRODUCT"]
    fund_identity_kind: Literal["SHARE_CLASS", "LISTING"]
    fund_id: str
    share_class_id: str
    fund_type: str
    venue: str | None
    dealing_channel: str | None
    nav_calendar_id: str
    subscription_cutoff: time | None
    redemption_cutoff: time | None

class PostGateFundSnapshot(BaseModel):
    raw_snapshot_id: UUID
    identity: EligibleFundIdentity
    official_benchmark_id: str
    nav: Decimal
    nav_date: date
    accumulated_nav: Decimal | None
    market_bid: Decimal | None
    market_ask: Decimal | None
    iopv: Decimal | None
    holdings_as_of: date
    fees: FeeSchedule
    dealing_status: DealingStatus
    benchmark: BenchmarkSnapshot

class EligibleEtfSnapshot(PostGateFundSnapshot):
    market_bid: Decimal
    market_ask: Decimal
    pcf: PcfSnapshot

class FundGateResult(BaseModel):
    raw_snapshot_id: UUID
    quality_status: Literal["ELIGIBLE", "DEGRADED", "REJECTED"]
    reason_codes: list[ReasonCode]
    post_gate_snapshot_id: UUID | None
    actionability: Literal[
        "ACTIONABLE", "RESEARCH_ONLY", "INSUFFICIENT_DATA", "REGION_RESTRICTED"
    ]
```

这些类型是公共 `RawObservation/RawAssetSnapshot/EligibleAssetSnapshot` 的基金强类型
扩展，不替代公共定义；`FieldProvenance` 细化公共 source、revision、license 和
payload hash 字段，`PostGateFundSnapshot` 对应公共 `EligibleAssetSnapshot`。

`RawField.value` 在采集阶段允许为空；每个已注册叶子键都必须带 `provenance` 和 `observed_at/published_at/available_at/retrieved_at`。来源没有事实发生或发布时间时，前两者可以为空，后两者仍记录缺失何时可见及何时获取。NAV 的数值、日期和官方/估算属性，费用各分项，持仓内容与 `holdings_as_of` 都是独立 `RawField`，不能共享一个对象级时间戳。

原始模型不把缺 official benchmark、NAV、fees、holdings、交易状态或场内价格视为 Pydantic 请求错误。无法规范化的来源值保留原始载荷哈希，规范值为 `null`，由 `FundQualityGate` 生成稳定 `ReasonCode`。`PostGateFundSnapshot` 只在 `quality_status` 为 `ELIGIBLE` 或 `DEGRADED` 且通用关键字段通过后构造，ETF 再构造更严格的 `EligibleEtfSnapshot`；`quality_status=REJECTED` 只引用 `RawFundSnapshot`，不会触发必填字段校验。`RESEARCH_ONLY` 只属于 `actionability`，不能写入 `quality_status`。

身份创建任务前执行条件校验，公共映射保持不变：

- `candidate_kind=FUND_PRODUCT` 只作为搜索容器，不持久化为 `InstrumentIdentity`，
  不可创建分析任务；
- `fund_identity_kind=SHARE_CLASS` 使用公共 `identity_level=PRODUCT`，必须有具体份额、
  申赎通道、cutoff 和 NAV 日历，且 `venue=null`；
- ETF、LOF 和封闭式基金必须解析为 `fund_identity_kind=LISTING`，同样使用
  `identity_level=PRODUCT`，且 `venue` 必填；
- 同一产品出现 A/C/I/ETF 等多个候选时返回 `FUND.SHARE_CLASS_AMBIGUOUS`，禁止默认首项；
- 规范 ID 使用 `fund:share_class:{jurisdiction}:{fund_id}:{share_class}:{currency}` 或 `fund:listing:{venue}:{local_code}:{kind}:{currency}`。

歧义搜索只不可变保存 `RawFundIdentityCandidate` 列表和查询审计，不创建
`InstrumentIdentity`、分析任务或伪 `RawFundSnapshot`；用户确认唯一份额/实例后，
后续来源字段缺失才进入 raw snapshot 与 quality gate。

| `candidate_kind.value` | `fund_identity_kind` | 公共 `identity_level` | 结果 |
| --- | --- | --- | --- |
| `FUND_PRODUCT` | 不创建 | 不创建 | 只继续选择份额/实例 |
| `SHARE_CLASS` | `SHARE_CLASS` | `PRODUCT` | `venue=null`，通道/cutoff/日历完整后可分析 |
| `LISTING` | `LISTING` | `PRODUCT` | `venue` 非空后可分析 |

### 3.1 `FundResearchDetails` 强类型 Schema

`ResearchDecision.asset_details` 在基金分支只能序列化以下类型。总体架构的最小字段保持
原名和原语义，`analysis_route` 与附加事实用于驱动现有 ETF、开放式、货币、债券基金
和 QDII 页面，不扩展公共动作：

```python
class FundResearchMetricReasonCodes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expense_ratio: list[ReasonCode] = Field(default_factory=list)
    tracking_error: list[ReasonCode] = Field(default_factory=list)
    nav_premium_discount: list[ReasonCode] = Field(default_factory=list)
    style_drift_score: list[ReasonCode] = Field(default_factory=list)
    nav: list[ReasonCode] = Field(default_factory=list)
    accumulated_nav: list[ReasonCode] = Field(default_factory=list)
    iopv: list[ReasonCode] = Field(default_factory=list)
    benchmark_excess_return: list[ReasonCode] = Field(default_factory=list)
    max_drawdown: list[ReasonCode] = Field(default_factory=list)
    holdings_concentration: list[ReasonCode] = Field(default_factory=list)
    manager_stability_score: list[ReasonCode] = Field(default_factory=list)
    aum: list[ReasonCode] = Field(default_factory=list)
    portfolio_duration: list[ReasonCode] = Field(default_factory=list)
    portfolio_yield_to_worst: list[ReasonCode] = Field(default_factory=list)
    wam_days: list[ReasonCode] = Field(default_factory=list)
    wal_days: list[ReasonCode] = Field(default_factory=list)
    qdii_nav_lag_days: list[ReasonCode] = Field(default_factory=list)
    fx_effect: list[ReasonCode] = Field(default_factory=list)


class FundResearchDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["FUND"]
    fund_type: Literal["ETF", "LOF", "OPEN_END", "MONEY_MARKET", "OTHER"]
    benchmark_code: str | None
    expense_ratio: Decimal | None
    tracking_error: Decimal | None
    nav_premium_discount: Decimal | None
    style_drift_score: Decimal | None
    liquidity_grade: Literal[
        "HIGH", "MEDIUM", "LOW", "NOT_APPLICABLE", "UNKNOWN"
    ]

    analysis_route: Literal[
        "ETF", "OPEN_END", "MONEY_MARKET", "BOND_FUND", "QDII", "SPECIAL"
    ]
    share_class_code: str
    nav: Decimal | None
    accumulated_nav: Decimal | None
    nav_as_of: date | None
    holdings_as_of: date | None
    dealing_status: Literal[
        "OPEN", "SUBSCRIPTION_SUSPENDED", "REDEMPTION_SUSPENDED",
        "FULLY_SUSPENDED", "UNKNOWN"
    ]
    pcf_available: bool | None
    iopv: Decimal | None
    benchmark_excess_return: Decimal | None
    max_drawdown: Decimal | None
    holdings_concentration: Decimal | None
    manager_stability_score: Decimal | None
    aum: Decimal | None
    portfolio_duration: Decimal | None
    portfolio_yield_to_worst: Decimal | None
    wam_days: Decimal | None
    wal_days: Decimal | None
    qdii_nav_lag_days: Decimal | None
    fx_effect: Decimal | None
    metric_reason_codes: FundResearchMetricReasonCodes
```

Schema 校验器按 `analysis_route` 检查字段组合，并逐项保证：可空数值为 `null` 时，
相应 `metric_reason_codes.<field>` 至少包含一个已注册的 `COMMON.*` 或 `FUND.*`；
只有官方或可追溯计算结果确实为零时才能保存 `0`。不适用、披露缺失、过期或无法计算
均保持 `null + reason`，不得把缺 NAV、IOPV、持仓、费用、久期、WAM/WAL 或汇率影响
补成零。字段级原因码是外层 `ResearchDecision.reason_codes` 的子集。

该类型明确禁止 `market_view`、任何 `direction` 别名、`normalized_direction`、
`recommendation`、`position_context`、`trade_intent`、`confidence`、
`probabilities/prediction_heads`、`quality_status` 和 `actionability`。基金结构质量、
溢折价、跟踪、久期或 QDII 汇率事实不能形成 `FundAction`，也不能覆盖公共
`ResearchDecision/PredictionHead`。

### 3.2 原始快照状态转换

1. 每次截止时点采集先以内容哈希 append-only 写入 `RawFundSnapshot`，数据库提交成功
   前不得运行 quality gate。
2. gate 只读该快照，按冻结优先级产出 `FundGateResult`；重跑不得补写或覆盖 raw。
3. `ELIGIBLE/DEGRADED` 且类型所需关键字段齐全时才构造对应
   `PostGateFundSnapshot`；构造失败属于内部契约测试失败，不得转成用户 422。
4. `quality_status=REJECTED` 的关键数据/许可/风险失败映射
   `actionability=INSUFFICIENT_DATA`，安全发布
   `market_view=INDETERMINATE`、`normalized_direction=INDETERMINATE`、
   `recommendation=AVOID`、`trade_intent=NONE`；专属复杂基金保持
   `quality_status` 为 `ELIGIBLE` 或 `DEGRADED`，映射
   `actionability=RESEARCH_ONLY`、
   `trade_intent=NONE`。两者都返回 `raw_snapshot_id`。

公共映射与发布覆盖优先级固定如下，`trade_intent=NONE` 是动作枚举，不能误写成
`actionability=NONE`：

| 条件 | `quality_status` | `actionability` | 发布 |
| --- | --- | --- | --- |
| 地区禁止 | 独立保留数据质量值 | `REGION_RESTRICTED` | `INDETERMINATE/AVOID/NONE` |
| 关键数据、许可或风险失败 | `REJECTED` | `INSUFFICIENT_DATA` | `INDETERMINATE/AVOID/NONE` |
| 专属复杂基金、DEGRADED 或模型未晋级 | `ELIGIBLE` 或 `DEGRADED` | `RESEARCH_ONLY` | `INDETERMINATE + HOLD 或 AVOID + NONE` |
| 已晋级且质量合格 | `ELIGIBLE` | `ACTIONABLE` | 按公共持仓真值表 |

## 4. 特征

### 4.1 公共长期质量

- 1/3/5 年及成立以来 NAV 总回报；
- 正式基准净超额、滚动胜率和信息比率；
- 波动、最大回撤、下行波动、Sharpe、Sortino；
- 牛/熊/震荡状态的相对表现；
- 持仓集中、行业/国家/币种偏离和风格漂移；
- 经理任期、团队变化、AUM、资金流和费用。

```text
structural_quality_score =
  benchmark_consistency
  + risk_adjusted_excess
  + drawdown_resilience
  + portfolio_consistency
  + organization_stability
  - fee_drag
```

每项保留原始值和贡献，不用分数替代披露事实。

### 4.2 战术进入

ETF：

```text
premium_discount = market_mid / nav - 1
tracking_difference = fund_total_return - index_total_return
```

结合溢折价、价差、流动性、资金流、标的估值和趋势。

开放式基金结合净值趋势、基准状态、资金流和风格环境，但短期动量权重不得覆盖结构质量。

```text
net_excess_return =
  forecast_fund_total_return
  - official_benchmark_total_return
  - share_class_cost
```

## 5. 专属逻辑

- ETF：当日 PCF、IOPV、申赎状态、溢折价、做市流动性、跟踪误差；
- 主动基金：正式基准、经理任期、持仓和风格漂移；
- 指数基金：复制方法、跟踪差异/误差和总费用；
- 债券基金：组合久期、信用质量、YTW 和利差风险；
- 货币基金：万份收益、七日年化、WAM/WAL 和流动性资产；
- QDII：境内外日历、汇率和合同规定的 NAV 延迟；
- 杠杆/反向和商品基金：`actionability=RESEARCH_ONLY`，转专属衍生逻辑。

## 6. 新鲜度和门控

### 6.1 `quality_status=REJECTED`

- `FUND.SHARE_CLASS_AMBIGUOUS` / `FUND.TYPE_UNKNOWN` / `COMMON.BENCHMARK_MISSING`：份额类别、基金类型或正式基准不明；
- `FUND.OFFICIAL_NAV_MISSING` / `FUND.OFFICIAL_NAV_STALE`：官方 NAV 缺失、过期或第三方估算试图覆盖 NAV；
- `FUND.FEE_SCHEDULE_MISSING`：费用表缺失，无法计算净回报；
- `FUND.DEALING_SUSPENDED`：暂停申购/赎回且请求动作需要该通道；
- `FUND.PCF_MISSING` / `COMMON.PRICE_UNAVAILABLE` / `FUND.EXTREME_PREMIUM`：ETF 当日 PCF 缺失、停牌、无有效 bid/ask 或极端溢价；
- `FUND.HOLDINGS_AS_OF_MISSING`：持仓披露时间未知；

### 6.2 `actionability=RESEARCH_ONLY`

- `FUND.SPECIALIZED_MODEL_REQUIRED`：杠杆/反向、商品或复杂结构基金需要专属模型，
  不进入普通策略。

### 6.3 `quality_status=DEGRADED`

- `FUND.HOLDINGS_STALE`：定期持仓存在但披露滞后；
- `FUND.MANAGEMENT_EVIDENCE_LOW`：经理/团队的次要信息缺失；
- `FUND.SECONDARY_MARKET_DATA_PARTIAL`：资金流或 IOPV 不可用，但 ETF NAV、价格和 PCF 完整；
- `FUND.SHORT_TRACK_RECORD`：轨迹不足 36 个月。

成立不足 36 个月的记录带 `short_track_record`，可显示事实但不展示平台评级，概率受质量上限限制。

`ReasonCode` 只保存稳定码：通用原因属于 `COMMON.*`，基金专属原因属于 `FUND.*`。中文说明由版本化码表生成；异常消息进入诊断日志，不得成为 API 原因码。

门控优先级冻结为 `许可/截止时间 -> 份额身份 -> 基金类型 -> 正式基准 -> 官方 NAV -> 费用 -> 持仓时点 -> 交易机制专属字段 -> 次要证据`。同一快照可以保存多个有序原因码，但主原因和最终状态在相同 gate 版本下稳定。缺基准、NAV、fees 或 holdings 都必须先保存审计快照再安全发布，不得因 Pydantic 校验返回 422，也不得冒泡为 500。

## 7. 决策

```text
edge_threshold = max(
  1.5 * investor_cost,
  forecast_interval_60pct_half_width,
  type_specific_minimum_edge
)
```

策略先生成正向、负向、中性或拒绝候选，再按公共 `position_context` 映射公共四元组：

- 正优势 + `FLAT` -> `LONG/FLAT/OPEN/BUY`；
- 正优势 + `LONG` -> `LONG/LONG/ADD/BUY`；
- 负优势 + `LONG` -> `SHORT/LONG/REDUCE|CLOSE/SELL`；
- 负优势 + `FLAT` -> 候选为 `SHORT/FLAT/NONE/HOLD`，long-only 发布层不得输出空仓 `SELL`；
- 中性 -> `NEUTRAL/{position_context}/KEEP|NONE/HOLD`；
- 拒绝或不支持 `SHORT` 持仓 -> `market_view=INDETERMINATE`、
  `normalized_direction=INDETERMINATE`、`recommendation=AVOID`、
  `trade_intent=NONE`，原持仓上下文单独保留。

`position_context=UNKNOWN` 时，候选层保存“若空仓/若持有”条件分支，发布层 `trade_intent=NONE`。四个字段只使用公共枚举，不增加 `FundAction` 或别名。ETF 的 `OPEN/CLOSE` 指下一可交易窗口，开放式基金则指 cutoff 对应的下一适用 NAV；所有结果 `execution_disabled=true`。

模型状态为 `SHADOW` 时：

```text
candidate_decision_json = 真实策略四元组
published_decision_json =
  INDETERMINATE / position_context / NONE / HOLD
  + COMMON.MODEL_NOT_PROMOTED
```

若质量、许可或风险硬拒绝，发布建议为 `AVOID`。`candidate_decision_json` 仅管理员、评估器和审计任务可读；LLM、普通 API、页面、导出和知识库只接收 `published_decision_json`。仅当请求的 `promotion_scope_key` 与已批准记录完全相同时，发布策略才可透传候选结果。

LLM 不能将高结构质量解释成必须立即买入，也不能忽略 ETF 极端溢价。

## 8. 结果评分

每个基金类型选择一个主结果头，并可附加事件头；稳定 `outcome_kind` 只使用：

| `outcome_kind` | 适用类型 | 主要口径 |
| --- | --- | --- |
| `fund.etf_market_return` | ETF/LOF | 可执行市场价总回报减正式基准和成本 |
| `fund.open_end_nav_return` | 普通开放式/债券基金 | cutoff 对应 NAV 总回报减正式基准和份额费用 |
| `fund.money_market_cash_return` | 货币基金 | 基金收益减现金基准和费用 |
| `fund.qdii_nav_fx_return` | QDII | 合同 NAV、双日历和汇率后的基准净超额 |
| `fund.dealing_event` | 全类型附加头 | 暂停、恢复、合并、清盘或终止上市事件 |

结果唯一键为 `(prediction_id, horizon_code, outcome_kind, evaluator_version)`。相同评估器重跑执行 upsert-no-change；新评估器版本只追加结果，不覆盖旧行。

候选决定按基金类型从四个收益 outcome 中选择且只选择一个主
`PredictionHead`，标签为 `POSITIVE_EXCESS/NEGATIVE_EXCESS/NEUTRAL`，冻结
公共 `target_spec_version/scoreability_rule_version`、
`probability_model_version/probability_artifact_hash`、
`calibration_version/calibration_artifact_hash/training_cutoff_at`、
`baseline_code/baseline_version`，并计算 `head_spec_hash`。
`fund.dealing_event` 可作为独立二分类非主 head；不同 head 的概率分别归一。

结果和晋级 cohort 必须按 `head_spec_hash` 隔离；target、scoreability、概率/校准
artifact 或基线版本任一不同都属于 mixed-spec cohort，聚合器默认拒绝而不是合并。

### 8.1 ETF/LOF

- 入场：下一可交易日规定开盘窗口的 ask/VWAP；
- 退出：第 5/20/60 个交易日 bid/VWAP；
- 回报：复权市场价格总回报，包含现金分红；
- 成本：点差、滑点、佣金、税费和溢折价变化；
- 基准：正式业绩基准总回报。

### 8.2 开放式基金

- 入场：根据信号时间、申购 cutoff 和基金日历确定下一适用 NAV；
- 退出：第 20/60/120 个估值日的适用赎回 NAV；
- 包含分红再投资和具体份额申赎/销售服务成本；
- 暂停状态延后或标记不可评分，不能用交易所开盘价。

货币基金按现金基准和流动性稳定性单独评分。QDII 使用合同日历和汇率。所有结果按类型分层。

每个结果头都使用完整公共 `OutcomeStatus=PENDING|PARTIAL|SCORED|UNSCORABLE`：未成熟为 `PENDING`，取得部分 NAV/市场事实但无法完成全口径为 `PARTIAL`，完整评分为 `SCORED`，按冻结规则永久无法取得合法结果为 `UNSCORABLE`。

`MaturityReason` 与结果状态分开存储，使用 `HORIZON_REACHED | EXPIRY | MATURITY | CALL | REDEMPTION | ROLL | DELISTING` 等公共枚举。不可评分原因使用 `COMMON.OUTCOME_PRICE_MISSING`、`COMMON.OUTCOME_BENCHMARK_MISSING`、`FUND.OUTCOME_CUTOFF_UNRESOLVED`；尚未成熟使用 `COMMON.OUTCOME_NOT_MATURED`，不得伪装为 `UNSCORABLE`。

## 9. 调度、幂等与回补

| 分组 | 影子启动 | 数据截止 |
| --- | --- | --- |
| 中国 ETF/LOF | 每个交易日 `19:10 Asia/Shanghai` | 当日 19:00 |
| 中国开放式/货币/债券基金 | 每个 NAV 日 `23:30 Asia/Shanghai` | 当日 23:15 |
| 美国 ETF | 每个交易日 `18:30 America/New_York` | 当日 18:15 |

次日 08:30 的 catch-up 只处理上一轮缺官方 NAV 的中国开放式任务，使用 08:15 截止和新的 `run_key/prediction_key`，不得修改原截止时点的快照。QDII 读取合同规定的 NAV lag、境内外日历和汇率 fixing；合法延迟不触发 `FUND.OFFICIAL_NAV_STALE`。

v1 每条 schedule 固定一个已确认 `canonical_id`；有许可的静态基金清单仅在配置阶段展开为多条 schedule，运行时不扫描市场或按 `venue_scope/universe` 扩展。

```text
access_principal = owner_scope | coalesce(user_id, "SYSTEM")
run_key = SHA-256(
  schedule_id_or_manual_scope_with_access_principal
  | schedule_version | scheduled_fire_at | cutoff_at
  | cutoff_policy_version | policy_version
)
prediction_key = SHA-256(access_principal | decision_input_hash)
```

规范化身份、截止时间、期限、持仓上下文、请求选项、数据/成本快照及所有能力、合规、特征、策略、模型和校准版本共同生成 `decision_input_hash`。相同 `access_principal` 且输入哈希不变时才关联已有预测；即使 `owner_scope` 相同，不同 `user_id` 也必须生成不同 `prediction_key`，不得跨用户复用候选、发布决定或预测。系统影子运行以 `coalesce(user_id, "SYSTEM")` 得到稳定主体。重试保留独立运行审计；快照或任一输入版本变化时创建新预测。

历史回补必须显式历史截止时间并满足 `available_at <= cutoff_at`；缺历史数据时返回 `COMMON.SOURCE_UNAVAILABLE`，不得使用当前修订。

## 10. 晋级范围与样本集中度

```text
promotion_scope_key = SHA-256(canonical_json(PromotionScope {
  scope_type, asset_type=fund, instrument_class, canonical_id, venue,
  product_type, signal_head, horizon_code,
  scope_parameters={fund_type, jurisdiction, execution_mechanism, benchmark_family}
}))
```

- 策略、模型和校准版本由注册表唯一键的独立列冻结；
- 两类 scope 都至少有 200 个已成熟、可评分的行动主结果头、至少 60 个去重
  `cutoff_date`、3 个冻结市场状态，且通过 walk-forward、purge/embargo 和至少
  60 个交易日/估值日前瞻影子验证；
- `POOLED` 额外要求至少 5 个经济基金产品组；任一产品组不超过 40%，报告最大
  占比和 HHI；
- 同一产品的 A/C/I 份额、ETF/联接或多场所实例归并为一个经济产品组，不能借重复份额增加独立样本；
- `INSTRUMENT_SPECIFIC` 必须在键中写入具体 `canonical_id`，允许该份额/实例占比
  100%，不要求 5 个产品组或 40% 集中度，但只解锁精确标的；
- 池化与单基金的样本、指标、审批、回退互不借用；二者都需满足总计划的前向影子天数和基准改进门槛。

独立日期按对应交易/NAV 日历的 `cutoff_date` 计算；同一
`canonical_id/head_spec_hash/horizon_code/cutoff_date` 的重试或多次用户触发只计
一个成熟行动信号，不能用同日重复运行补足 200 或 60 的门槛。

### 10.1 冻结的 regime 与统计证据

每次候选晋级先登记不可变 `FundPromotionEvidenceSpec`：

```python
class FundRegimeSpec(BaseModel):
    regime_source_id: str
    benchmark_family: str
    source_vintage_policy: str
    calendar_id: str
    evaluation_start: date
    evaluation_end: date
    algorithm_id: str
    algorithm_artifact_hash: str
    algorithm_parameters: dict[str, Decimal | int | str]
    required_labels: tuple[Literal["BULL", "BEAR", "SIDEWAYS"], ...]
    min_independent_dates_per_label: int
    min_contiguous_sessions: int
    regime_version: str

class FundPromotionEvidenceSpec(BaseModel):
    promotion_scope_key: str
    publication_claim: Literal["TACTICAL_SIGNAL", "LONG_TERM_QUALITY"]
    primary_head: str
    baseline_id: str
    baseline_version: str
    regime_spec_id: str
    cost_model_version: str
    evaluation_start: date
    evaluation_end: date
    bootstrap_method: Literal["MOVING_BLOCK"]
    bootstrap_samples: Literal[10000]
    confidence_level_bps: Literal[9500]
    block_length_sessions: int
    random_seed: int
    drawdown_tolerance: Decimal
    cost_stress_multiplier: Decimal
```

`regime_source_id` 必须是 scope 正式基准族的授权总回报序列；算法、参数、区间、数据 vintage、日历和 `regime_version` 在读取结果前冻结。默认要求三个 label 各至少 20 个独立成熟日期。`publication_claim=LONG_TERM_QUALITY` 还要求冻结区间内至少有一个连续 BULL 段和一个连续 BEAR 段，且每段不短于 `min_contiguous_sessions=60`；这是“覆盖完整牛熊”的机器判定。`TACTICAL_SIGNAL` 仍需三个状态，但不因通过而获得“基金评级”文案。

主经济指标固定为：

```text
delta_net_utility =
  model_net_utility_after_all_costs
  - baseline_net_utility_after_all_costs
```

晋级程序必须同时满足以下布尔条件：

- `mean(model_net_utility_after_all_costs) > 0`；
- 对 `delta_net_utility` 做 10,000 次 95% moving-block bootstrap，区间下界
  `>= 0`；`block_length_sessions` 至少覆盖该 head 的最大标签重叠期；
- 注册主概率 head 相对同 target、同 cohort 朴素基线的
  `Brier Skill Score > 0`，并通过冻结 calibration gate；
- `model_max_drawdown <= baseline_max_drawdown + drawdown_tolerance`；
- 费用、点差、滑点、申赎费和销售服务费全部进入净效用，且在
  `cost_stress_multiplier=1.5` 的成本压力下平均净效用仍 `>= 0`；
- 三个 regime 与每个预注册风险切片均不触发未批准的尾部损失、覆盖率或数据失败率
  退化。

bootstrap seed、样本数、block 长度、基线、成本模型、容忍度和全部尝试版本进入证据包。`POOLED` 在聚合、每个充分样本产品组和最差风险切片报告结果；`INSTRUMENT_SPECIFIC` 只评估目标 `canonical_id`，不得借池化样本、指标或审批。

## 11. API 和页面

请求示例：

```json
{
  "asset_type": "fund",
  "canonical_id": "fund:listing:XSHG:510300:ETF:CNY",
  "horizon_code": "60_exchange_sessions",
  "position_context": "UNKNOWN"
}
```

`FundPanel.vue` 根据 `fund_type` 条件显示：

- 公共：NAV、基准、回撤、费用、持仓、经理、规模；
- ETF：市价/NAV/IOPV、溢折价、PCF、跟踪和流动性；
- 债券基金：久期、信用和 YTW；
- 货币基金：WAM/WAL 和流动性；
- QDII：双日历、汇率和 NAV 延迟。

## 12. 数据来源和许可

境内主来源为基金管理人/托管人官网、交易所、证监会、基金业协会和指数公司；美国使用 SEC EDGAR/N-PORT、发行人官网和授权交易所数据。AKShare、OpenBB 和 yfinance 只可作为原型或架构参考，代码许可证不授予上游数据商用权。记录 `access_principal`、`run_key`、`prediction_key`、`quality_status`、`actionability`、`promotion_scope_key`、NAV/持仓版本及注册的 `COMMON.*` / `FUND.*`，禁止把异常文本当机器原因码。
