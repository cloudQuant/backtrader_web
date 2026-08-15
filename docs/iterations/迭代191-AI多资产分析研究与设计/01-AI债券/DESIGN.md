# 191A AI 债券设计文档

## 1. 设计依据

中债公开估值包含全价、应计利息、净价、收益率、久期、凸性、基点价值、利差久期、流动性和隐含评级，这些应是债券领域的一等字段。[中债估值](https://valuation.chinabond.com.cn/cbweb-mn/val/val_query_list?locale=zh_CN)和[中债指数编制说明](https://valuation.chinabond.com.cn/cbweb-mn/int/int_yield_zs_doc)也说明历史结果应使用包含现金流再投资的财富/总回报口径。

## 2. 组件

```text
BondIdentitySourceAdapter
  -> RawBondIdentityCandidate
  -> BondTermsCollector
  -> BondMarketCollector
  -> YieldCurveResolver
  -> ImmutableRawBondSnapshotStore
  -> BondQualityGate
      -> PostGateBondSnapshot（关键字段通过）
      -> GateResult + RawBondSnapshot（拒绝或仅研究）
  -> BondValuationEngine
  -> BondCreditAnalyzer
  -> BondDecisionPolicy
  -> BondPublicationPolicy
  -> BondReportBuilder
  -> BondOutcomeEvaluator

BondShadowScheduler -> AssetResearchRunService -> 上述流水线
```

所有收集器的每个叶子字段均输出来源和四类时点。原始候选与原始快照先不可变持久化，质量门控只能引用它们，不能回写补值。估值引擎只接收门控后的强类型快照，是不访问网络和数据库的纯函数。

## 3. 数据结构

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

class RawBondIdentityCandidate(BaseModel):
    raw_candidate_id: UUID
    candidate_kind: RawField[Literal["ISSUER", "ISSUE", "LISTING"]]
    candidate_id: RawField[str]
    display_name: RawField[str]
    isin: RawField[str]
    local_code: RawField[str]
    venue: RawField[str]
    currency: RawField[str]
    issuer: RawField[str]
    issue_name: RawField[str]

class RawBondSnapshot(BaseModel):
    raw_snapshot_id: UUID
    raw_candidate_id: UUID
    cutoff_at: datetime
    maturity: RawField[date]
    is_perpetual: RawField[bool]
    terms: dict[str, RawField[Any]]
    prices: dict[str, RawField[Decimal]]
    curve: dict[str, RawField[Any]]
    benchmark: dict[str, RawField[Any]]

class EligibleBondIdentity(BaseModel):
    canonical_id: str
    identity_level: Literal["ASSET", "PRODUCT"]
    bond_identity_kind: Literal["ISSUE", "LISTING"]
    isin: str | None
    local_code: str | None
    venue: str | None
    currency: str
    issue_id: str | None

class EligibleBondTerms(BaseModel):
    face_value: Decimal
    remaining_principal: Decimal
    coupon_type: str
    coupon_rate: Decimal | None
    payment_frequency: int
    day_count: str
    business_day_convention: str
    accrual_start_date: date
    maturity_date: date
    redemption_schedule: list[CashflowTerm]
    embedded_options: list[EmbeddedOption]

class PostGateBondSnapshot(BaseModel):
    raw_snapshot_id: UUID
    identity: EligibleBondIdentity
    terms: EligibleBondTerms
    clean_price: Decimal | None
    accrued_interest: Decimal
    dirty_price: Decimal
    bid: Decimal | None
    ask: Decimal | None
    official_valuation: Decimal | None
    last_trade_at: datetime | None
    valuation_date: date
    curve_id: str
    curve_date: date
    benchmark_id: str

class BondGateResult(BaseModel):
    raw_snapshot_id: UUID
    quality_status: Literal["ELIGIBLE", "DEGRADED", "REJECTED"]
    reason_codes: list[ReasonCode]
    post_gate_snapshot_id: UUID | None
    actionability: Literal[
        "ACTIONABLE", "RESEARCH_ONLY", "INSUFFICIENT_DATA", "REGION_RESTRICTED"
    ]
```

这些类型是公共 `RawObservation/RawAssetSnapshot/EligibleAssetSnapshot` 的债券强类型
扩展，不替代公共定义；`FieldProvenance` 细化公共 source、revision、license 和
payload hash 字段，`PostGateBondSnapshot` 对应公共 `EligibleAssetSnapshot`。

`RawField.value` 在采集阶段一律允许为空；`provenance` 和四个时点键始终存在，其中来源没有给出事实发生或发布时间时，`observed_at/published_at` 可以为空，`available_at/retrieved_at` 仍记录“发现缺失”何时可见和何时获取。`terms/prices/curve/benchmark` 的每个已注册叶子键都使用 `RawField`，不得把整个来源对象塞入一个无字段级时点的 JSON。

原始模型只校验系统生成 ID、证据信封和枚举的已知值，不以到期日、合同、价格、曲线或基准缺失为 Pydantic 请求错误。不能解析的来源值保存原始载荷哈希，并把规范值记为 `null`；领域缺失由门控生成稳定 `ReasonCode`。`PostGateBondSnapshot` 只在 `quality_status` 为 `ELIGIBLE` 或 `DEGRADED` 且定价关键字段通过后构造，只有这里才收紧必需字段；`quality_status=REJECTED` 不构造该模型，继续引用已经落库的 `RawBondSnapshot`。`RESEARCH_ONLY` 只属于 `actionability`，不能写入 `quality_status`。

身份解析先返回原始候选，再按以下约束创建任务；公共映射保持不变：

- `candidate_kind=ISSUER` 只是搜索容器，不能持久化为 `InstrumentIdentity` 或创建分析任务；
- `bond_identity_kind=ISSUE` 映射公共 `identity_level=ASSET`，只有在跨场所官方估值
  研究时允许 `venue=null`，并强制 `actionability=RESEARCH_ONLY`；
- `bond_identity_kind=LISTING` 映射公共 `identity_level=PRODUCT`，本地代码、成交、
  bid/ask 和可执行结果都要求 `venue`；
- 多候选返回 `COMMON.INSTRUMENT_AMBIGUOUS`，不采用第一条或默认市场；
- 规范 ID 分别使用 `bond:issue:{isin}:{currency}` 和 `bond:listing:{venue}:{local_code}:{currency}`。

歧义搜索只不可变保存 `RawBondIdentityCandidate` 列表和查询审计，不创建
`InstrumentIdentity`、分析任务或伪 `RawBondSnapshot`；用户确认唯一候选后，后续
来源字段缺失才进入 raw snapshot 与 quality gate。

映射表是门控后唯一合法转换：

| `candidate_kind.value` | `bond_identity_kind` | 公共 `identity_level` | 结果 |
| --- | --- | --- | --- |
| `ISSUER` | 不创建 | 不创建 | 只继续搜索 |
| `ISSUE` | `ISSUE` | `ASSET` | 仅跨场所估值研究可空 `venue` |
| `LISTING` | `LISTING` | `PRODUCT` | `venue` 非空才可分析 |

### 3.1 `BondResearchDetails` 强类型 Schema

`ResearchDecision.asset_details` 在债券分支只能序列化以下类型。前八个字段与总体
`ARCHITECTURE.md` 的最小骨架一致，其余字段只承载本设计的现金流、曲线、信用和页面
展示事实：

```python
class BondResearchMetricReasonCodes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    yield_to_maturity: list[ReasonCode] = Field(default_factory=list)
    yield_to_worst: list[ReasonCode] = Field(default_factory=list)
    modified_duration: list[ReasonCode] = Field(default_factory=list)
    dv01: list[ReasonCode] = Field(default_factory=list)
    credit_spread_bps: list[ReasonCode] = Field(default_factory=list)
    clean_price: list[ReasonCode] = Field(default_factory=list)
    dirty_price: list[ReasonCode] = Field(default_factory=list)
    accrued_interest: list[ReasonCode] = Field(default_factory=list)
    convexity: list[ReasonCode] = Field(default_factory=list)
    spread_duration: list[ReasonCode] = Field(default_factory=list)
    z_spread_bps: list[ReasonCode] = Field(default_factory=list)
    oas_bps: list[ReasonCode] = Field(default_factory=list)


class BondResearchDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["BOND"]
    price_basis: Literal["EXECUTABLE", "OFFICIAL_VALUATION", "INDICATIVE"]
    yield_to_maturity: Decimal | None
    yield_to_worst: Decimal | None
    modified_duration: Decimal | None
    dv01: Decimal | None
    credit_spread_bps: Decimal | None
    liquidity_grade: Literal["HIGH", "MEDIUM", "LOW", "UNKNOWN"]

    clean_price: Decimal | None
    dirty_price: Decimal | None
    accrued_interest: Decimal | None
    convexity: Decimal | None
    spread_duration: Decimal | None
    z_spread_bps: Decimal | None
    oas_bps: Decimal | None
    is_perpetual: bool
    curve_id: str | None
    benchmark_code: str | None
    valuation_date: date | None
    cashflow_hash: str | None
    credit_risk_grade: Literal[
        "SOVEREIGN", "INVESTMENT_GRADE", "HIGH_YIELD", "DISTRESSED", "UNKNOWN"
    ]
    metric_reason_codes: BondResearchMetricReasonCodes
```

Schema 校验器逐项保证：任何可空数值为 `null` 时，相应
`metric_reason_codes.<field>` 至少有一个已注册的 `COMMON.*` 或 `BOND.*`；只有来源
事实确实为零时才能保存数值 `0`，缺数据、求解失败或模型不适用不得补零。字段级原因码
同时是外层 `ResearchDecision.reason_codes` 的子集，不建立第二套原因命名空间。

该类型明确禁止 `market_view`、任何 `direction` 别名、`normalized_direction`、
`recommendation`、`position_context`、`trade_intent`、`confidence`、
`probabilities/prediction_heads`、`quality_status` 和 `actionability`。这些字段仅由公共
`ResearchDecision/PredictionHead` 承载；净价/全价、收益率、久期、DV01、信用与曲线
事实不能推导出第二套债券动作。

### 3.2 原始快照状态转换

1. 收集器完成一次截止时点采集后，先以内容哈希写入 append-only
   `RawBondSnapshot`；数据库提交成功前不得调用质量门控。
2. `BondQualityGate` 只读该快照，按固定优先级产出
   `BondGateResult.quality_status/actionability/reason_codes`。
3. `ELIGIBLE/DEGRADED` 且定价关键字段通过后才解包并构造
   `PostGateBondSnapshot`；构造失败是内部契约测试失败，不能改写成用户输入 422。
4. `quality_status=REJECTED` 的关键数据/许可/风险失败映射
   `actionability=INSUFFICIENT_DATA`，安全发布
   `market_view=INDETERMINATE`、`normalized_direction=INDETERMINATE`、
   `recommendation=AVOID`、`trade_intent=NONE`；仅研究路径保持
   `quality_status` 为 `ELIGIBLE` 或 `DEGRADED`，映射
   `actionability=RESEARCH_ONLY`、
   `trade_intent=NONE`。两者都保留 `raw_snapshot_id`。
5. 已识别永续债的 `is_perpetual=true` 且 `maturity.value=null` 是合法原始事实，
   产出的 `quality_status` 为 `ELIGIBLE` 或 `DEGRADED`，
   `actionability=RESEARCH_ONLY + BOND.PERPETUAL_MODEL_REQUIRED`；普通债券到期日缺失
   产出 `quality_status=REJECTED`、
   `actionability=INSUFFICIENT_DATA + BOND.MATURITY_MISSING`，不能由 schema 先抛异常。

公共映射与发布覆盖优先级固定如下，`trade_intent=NONE` 是动作枚举，不能误写成
`actionability=NONE`：

| 条件 | `quality_status` | `actionability` | 发布 |
| --- | --- | --- | --- |
| 地区禁止 | 独立保留数据质量值 | `REGION_RESTRICTED` | `INDETERMINATE/AVOID/NONE` |
| 关键数据、许可或风险失败 | `REJECTED` | `INSUFFICIENT_DATA` | `INDETERMINATE/AVOID/NONE` |
| 永续/复杂品种、DEGRADED 或模型未晋级 | `ELIGIBLE` 或 `DEGRADED` | `RESEARCH_ONLY` | `INDETERMINATE + HOLD 或 AVOID + NONE` |
| 已晋级且质量合格 | `ELIGIBLE` | `ACTIONABLE` | 按公共持仓真值表 |

## 4. 估值和特征

### 4.1 现金流一致性

```text
dirty_price = clean_price + accrued_interest
```

允许的数据源舍入误差为面值的 `1e-6`；超过时标记 `BOND.PRICE_IDENTITY_MISMATCH`。现金流日按合同日计数和营业日调整。

### 4.2 风险量

- YTM：使未来合同现金流现值等于全价的内部收益率；
- YTW：所有可执行赎回/回售场景中的最低合法收益率；
- 修正久期和凸性：用同一曲线、结算日和现金流计算；
- DV01：收益率平行移动 1 bp 的价格变化；
- Z-spread/OAS：只有曲线和含权模型满足条件时计算，否则为 `null + reason`。

QuantLib 采用 BSD 风格许可，可作为现金流和定价内核候选；引入后锁定版本并用固定现金流黄金用例验证。[QuantLib](https://github.com/lballabio/QuantLib)

### 4.3 预期总回报

```text
projected_dirty_total_return =
    carry
  + roll_down
  + rate_curve_effect
  + credit_spread_effect
  + option_value_effect
  + fx_effect
  - expected_credit_loss

net_excess_return =
    projected_dirty_total_return
  - matched_benchmark_total_return
  - round_trip_cost
```

所有贡献单独保存。阈值为：

```text
edge_threshold = max(
  1.5 * estimated_round_trip_cost,
  forecast_interval_60pct_half_width,
  bucket_minimum_edge
)
```

`bucket_minimum_edge` 随币种、久期、评级和流动性版本化，不在代码中散落常量。

## 5. 信用分析

政府债路由不要求公司财务。普通信用债计算：

- 现金/短债、总债务/EBITDA、利息保障；
- 经营现金流和自由现金流；
- 再融资到期墙、受限资产和融资渠道；
- 主体/债项评级变化、展望、观察名单；
- 违约、展期、交叉违约、回售和重大诉讼。

关键披露是否过期按发行人法定报告期和实际披露截止日计算，不用一个固定天数覆盖所有发行人。

## 6. 质量门控

### 6.1 `quality_status=REJECTED`

- `BOND.MATURITY_MISSING`：非永续债的到期日无法确定；
- `BOND.TERMS_INCOMPLETE`：日计数、票息、偿还或剩余本金缺失；
- `COMMON.DATA_STALE` / `BOND.CURVE_MISSING`：最近完成交易日没有合法估值/价格或匹配曲线；
- `COMMON.BENCHMARK_MISSING`：基准无法确定；
- `BOND.OPTION_SCHEDULE_MISSING`：含权债缺执行日或执行价格；
- `COMMON.DATA_AFTER_CUTOFF`：数据来自分析截止时间之后；
- `COMMON.SOURCE_LICENSE_BLOCKED`：数据许可不允许当前用途；
- `BOND.PRICE_IDENTITY_MISMATCH`：现金流或净价/全价恒等式无法解释地不一致。

### 6.2 `actionability=RESEARCH_ONLY`

- `BOND.PERPETUAL_MODEL_REQUIRED`：已确认永续结构，`maturity=null` 合法，但 v1
  不具备永续债方向模型；
- `BOND.SPECIALIZED_MODEL_REQUIRED`：可转债、违约/特定债、ABS/MBS 或复杂分层
  需要专属模型。

### 6.3 `quality_status=DEGRADED`

- `BOND.VALUATION_NOT_EXECUTABLE`：有官方估值但没有可执行 bid/ask；
- `COMMON.EVIDENCE_COVERAGE_LOW`：新闻、持仓结构或可选宏观数据缺失；
- `BOND.PEER_DATA_INCOMPLETE`：信用债的次要比较债数据不足；
- `COMMON.DATA_STALE`：最后成交过期但当日官方估值有效；
- `BOND.CREDIT_DISCLOSURE_STALE`：信用债法定披露已过适用截止期。

`DEGRADED` 只允许 `HOLD/AVOID`，报告标记“估值研究，非可执行报价”。

`ReasonCode` 只保存稳定码：通用原因属于 `COMMON.*`，债券专属原因属于 `BOND.*`。中文说明由版本化码表生成；异常消息进入诊断日志，不得成为 API 原因码。

门控优先级冻结为 `许可/截止时间 -> 身份 -> 品种支持 -> 到期与合同 -> 价格 -> 曲线 -> 基准 -> 一致性 -> 次要证据`。一次快照可以有多个原因码，但排序、主原因和状态在相同 gate 版本下稳定。任何关键值为空都走 `BondGateResult` 和安全发布，不得因 Pydantic 校验转换为 422，也不得冒泡为 500。

## 7. 决策策略

```text
positive_candidate if net_excess_return > +edge_threshold
                       and downside_credit_gate_passed
                       and quality_status == ELIGIBLE
negative_candidate if net_excess_return < -edge_threshold
                       or versioned_credit_deterioration_rule_triggered
neutral_candidate  if abs(net_excess_return) <= edge_threshold
reject_candidate   otherwise
```

策略引擎不返回债券私有动作。它根据公共 `position_context` 生成公共四元组：

- 正优势 + `FLAT` -> `LONG/FLAT/OPEN/BUY`；
- 正优势 + `LONG` -> `LONG/LONG/ADD/BUY`；
- 负优势 + `LONG` -> `SHORT/LONG/REDUCE|CLOSE/SELL`；
- 负优势 + `FLAT` -> 候选为 `SHORT/FLAT/NONE/HOLD`，long-only 发布层不得输出空仓 `SELL`；
- 中性 -> `NEUTRAL/{position_context}/KEEP|NONE/HOLD`；
- 拒绝或不支持 `SHORT` 持仓 -> `market_view=INDETERMINATE`、
  `normalized_direction=INDETERMINATE`、`recommendation=AVOID`、
  `trade_intent=NONE`，原持仓上下文单独保留。

`position_context=UNKNOWN` 时，候选层保存条件分支，发布层只能给 `trade_intent=NONE` 并用“若空仓/若持有”解释。四个字段的枚举来自公共契约，不增加 `BondAction` 或别名。所有结果 `execution_disabled=true`。

模型状态为 `SHADOW` 时：

```text
candidate_decision_json = 真实策略四元组
published_decision_json =
  INDETERMINATE / position_context / NONE / HOLD
  + COMMON.MODEL_NOT_PROMOTED
```

若质量、许可或风险硬拒绝，发布建议为 `AVOID`。`candidate_decision_json` 仅管理员、评估器和审计任务可读；LLM、普通 API、页面、导出和知识库只接收 `published_decision_json`。仅当请求的 `promotion_scope_key` 与已批准记录完全相同时，发布策略才可透传候选结果。

置信度为样本外校准后的动作正确概率，并乘以 `data_quality_cap` 和 `liquidity_cap`。没有已晋级模型时 `confidence=null`，不得由规则分数或 LLM 冒充概率。

## 8. 结果评分

期限为 20/60/120 个债券交易日。每个期限可以有三个稳定 `outcome_kind`，不得混用名称或覆盖彼此：

| `outcome_kind` | 用途 | 是否方向主结果头 |
| --- | --- | --- |
| `bond.executable_total_return` | 可执行价格、真实现金流和成本后的基准净超额 | 是 |
| `bond.valuation_total_return` | 仅有官方估值时的研究结果 | 否 |
| `bond.credit_event` | 违约、展期、评级/信用事件预警 | 否 |

结果唯一键为 `(prediction_id, horizon_code, outcome_kind, evaluator_version)`，同一评估器重跑执行 upsert-no-change；新评估器版本只能追加新行。

有可执行报价的候选决定以 `bond.executable_total_return` 作为唯一主
`PredictionHead`，标签为 `POSITIVE_EXCESS/NEGATIVE_EXCESS/NEUTRAL`，冻结
公共 `target_spec_version/scoreability_rule_version`、
`probability_model_version/probability_artifact_hash`、
`calibration_version/calibration_artifact_hash/training_cutoff_at`、
`baseline_code/baseline_version`，并计算 `head_spec_hash`。信用债可附加
`bond.credit_event` 二分类 head，但不得与总回报概率混合。只有估值研究时不生成
可执行主 head，`primary_head_code=null`。

结果和晋级 cohort 必须按 `head_spec_hash` 隔离；target、scoreability、概率/校准
artifact 或基线版本任一不同都属于 mixed-spec cohort，聚合器默认拒绝而不是合并。

```text
bond_total_return =
  (ending_dirty_price
   + coupons_received
   + principal_or_call_payments
   - starting_dirty_price)
  / starting_dirty_price

net_excess = bond_total_return
           - matched_wealth_index_return
           - spread_commission_tax_fx_cost
```

- 跨付息、提前赎回和本金偿还按真实事件计算；
- 无可执行价格但有估值时可以生成“估值结果”，不能计入可执行成绩；
- 长期无成交的最后价不能作为入场；
- 不同期限、评级和流动性桶不混成单一成功率。

每个结果头都使用完整公共 `OutcomeStatus=PENDING|PARTIAL|SCORED|UNSCORABLE`：未成熟为 `PENDING`，取得部分现金流/市场事实但无法完成全口径为 `PARTIAL`，完整评分为 `SCORED`，按冻结规则永久无法取得合法结果为 `UNSCORABLE`。

`MaturityReason` 与结果状态分开存储，使用 `HORIZON_REACHED | EXPIRY | MATURITY | CALL | REDEMPTION | ROLL | DELISTING` 等公共枚举。不可评分原因使用 `COMMON.OUTCOME_PRICE_MISSING`、`COMMON.OUTCOME_BENCHMARK_MISSING`、`BOND.OUTCOME_CASHFLOW_INCOMPLETE`；尚未成熟使用 `COMMON.OUTCOME_NOT_MATURED`，不得伪装为 `UNSCORABLE`。

## 9. 调度、幂等与回补

| 市场 | 影子启动 | 数据截止 |
| --- | --- | --- |
| 中国债券 | 每个交易日 `19:10 Asia/Shanghai` | 当日 19:00 |
| 美国债券 | 每个交易日 `18:30 America/New_York` | 当日 18:15 |

美国任务在许可未就绪时不注册。v1 每条 schedule 固定一个已确认 `canonical_id`；审批静态清单仅在配置阶段展开为多条 schedule，运行时不扫描市场或按 `venue_scope/universe` 扩展。

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

回补接口要求显式历史 `as_of_date/cutoff_at` 和版本，收集器只能读取 `available_at <= cutoff_at` 的版本。历史材料不存在时返回 `COMMON.SOURCE_UNAVAILABLE` 或相应不可评分原因，不得读取当前修订值。结果成熟任务只追加对应 `outcome_kind/evaluator_version`。

## 10. 晋级范围与样本集中度

```text
promotion_scope_key = SHA-256(canonical_json(PromotionScope {
  scope_type, asset_type=bond, instrument_class, canonical_id, venue,
  product_type, signal_head, horizon_code,
  scope_parameters={currency, venue_group, duration_bucket, credit_bucket}
}))
```

- 策略、模型和校准版本由注册表唯一键的独立列冻结；
- 两类范围都至少有 200 个已成熟、可评分的行动主结果头、至少 60 个去重
  `cutoff_date`、3 个由冻结 regime 规则标注的市场状态，并满足 walk-forward、
  purge/embargo 和至少 60 个交易日前瞻影子日；
- `POOLED` 额外要求至少 5 个经济实体组、政府债和信用债、至少 3 个久期桶及
  3 个流动性桶；任一实体组不超过 40%，报告最大占比和 HHI；
- 同一债项的不同交易场所归并为一个经济实体组，防止重复上市放大样本；
- `INSTRUMENT_SPECIFIC` 必须在键中写入具体 `canonical_id`，允许该单券占比
  100%，但只解锁精确单券；它不要求同时出现政府债/信用债，也不要求 3 个久期桶、
  3 个流动性桶或 5 个实体组；
- 池化与单券的样本、指标、审批、回退互不借用；二者都需满足总计划的前向影子天数和基准改进门槛。

独立日期按债券市场日历的 `cutoff_date` 计算；同一
`canonical_id/head_spec_hash/horizon_code/cutoff_date` 的重试、重复运行或重复场所
映射只计一个成熟行动信号，不能用同日重复触发补足 200 或 60 的门槛。

## 11. API 和前端扩展

`POST /api/v1/asset-research/tasks` 的债券请求增加：

```json
{
  "asset_type": "bond",
  "canonical_id": "bond:listing:XSHG:019547:CNY",
  "horizon_code": "60_bond_sessions",
  "position_context": "UNKNOWN",
  "price_basis": "official_valuation"
}
```

前端 `BondPanel.vue` 展示现金流时间轴、净价/全价、收益率与曲线、久期/DV01、信用指标、条款、流动性和三情景总回报。`price_basis=official_valuation` 时在结论旁固定展示非可执行提示。

## 12. 可观测性

记录 `access_principal`、`run_key`、`raw_candidate_id`、`raw_snapshot_id`、原始内容哈希、raw 落库提交时间、gate 版本、`post_gate_snapshot_id`、`quality_status`、`actionability`、`prediction_key`、`promotion_scope_key`、`bond_terms_version`、`curve_id/date`、`valuation_provider/date`、`benchmark_id`、现金流哈希、估值引擎版本、曲线构建警告、`ReasonCode` 和计算耗时。任何 YTM/IV 求解失败均有注册的 `COMMON.*` 或 `BOND.*` 稳定码，禁止仅记录异常文本。
