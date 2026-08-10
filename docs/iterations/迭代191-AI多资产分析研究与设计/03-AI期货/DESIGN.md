# 191C AI 期货设计文档

## 1. 组件

```text
FuturesInstrumentResolver
  -> ContractMasterService
  -> FuturesCalendar
  -> ContinuousMappingService
  -> FuturesSnapshotCollector
  -> FuturesTypeRouter
  -> FuturesQualityGate
  -> FuturesDecisionPolicy
  -> FuturesReportBuilder
  -> FuturesOutcomeEvaluator
```

`ContinuousMappingService` 只产生研究映射，不返回可交易对象；所有建议和结果必须引用
`identity_level=CONTRACT` 的真实期货合约。

解析结果使用公共 `InstrumentIdentity` 的 `identity_level=PRODUCT/CONTRACT/SERIES`
和期货专属字段联合校验。产品和连续序列可生成事实研究，公开动作、入场价和合同级结果
必须冻结为具体 `CONTRACT`。

## 2. 连续序列

```python
class FuturesMappingSnapshot(BaseModel):
    series_id: str
    as_of_at: datetime
    cutoff_at: datetime
    mapping_rule_version: str
    normalization_rule_version: str
    contract_depth: int
    mapped_contract_id: str
    roll_effective_at: datetime
    adjustment_factor: Decimal
    normalization_chain: tuple[NormalizationLeg, ...]
    chain_vintage_at: datetime
    source_observation_cutoff_at: datetime
    mapping_source_hash: str
    normalization_source_hash: str
    normalization_chain_hash: str
    input_snapshot_hash: str
```

`NormalizationLeg` 是按 `effective_from` 排序的不可变复权段，至少冻结
`from_contract_id/to_contract_id`、换月生效时点、加法或乘法方法、因子、因子观测时点、
来源记录哈希和 `available_at`。构链只允许读取 `available_at <= cutoff_at` 的映射、
量仓、结算和修订；`chain_vintage_at` 是本次可见链的 vintage，不是查询时的当前版本。
先对完整有序链做 canonical JSON，再生成 `normalization_chain_hash`。

映射可按持仓量、成交量、距最后交易日和双日确认组合，具体规则版本化。预测和特征事实
外键到该不可变快照；相同 cutoff 的重放必须得到相同 mapped contract、chain hash、
feature value 和 feature hash。后续换月或来源修订只能追加新的 mapping snapshot，
不得更新旧链。特征哈希至少覆盖 `series_id + cutoff_at + mapped_contract_id +
normalization_chain_hash + input_snapshot_hash + feature_version`。历史重放只能使用当时
已经可用的量仓数据。[QuantConnect 的期货文档](https://www.quantconnect.com/docs/v2/writing-algorithms/universes/futures)同样区分连续调整序列与实际映射合约。

## 3. 公共特征

- 原始合约 1/5/20/60 日收益、均线、突破、ATR 和实现波动；
- 成交量、持仓量、量仓变化、bid-ask、深度和主次流动性迁移；
- 近月/次近月/远月曲线斜率、曲率和变化；
- 现货基差和标准化 basis；
- 保证金、价格限制、距最后交易/通知/交割日；
- COT/会员排名只作为聚合证据，不解释为确定机构方向。

期限 carry 统一定义：

```text
annualized_curve_carry =
  ln(F_near / F_far) * 365 / (D_far - D_near)
```

正值表示 backwardation，负值表示 contango；单位、交割品质和时间不可比时不计算。

### 3.1 `FuturesResearchDetails` 强类型 Schema

`ResearchDecision.asset_details` 在期货分支只接受以下 CONTRACT 级类型。总体架构最小
字段保持不变，附加字段覆盖期限结构、映射、会话、量仓、流动性、保证金和交割页面：

```python
class FuturesResearchMetricReasonCodes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    basis: list[ReasonCode] = Field(default_factory=list)
    annualized_carry: list[ReasonCode] = Field(default_factory=list)
    margin_ratio: list[ReasonCode] = Field(default_factory=list)
    curve_slope: list[ReasonCode] = Field(default_factory=list)
    curve_curvature: list[ReasonCode] = Field(default_factory=list)
    bid_ask_spread: list[ReasonCode] = Field(default_factory=list)
    market_depth: list[ReasonCode] = Field(default_factory=list)
    volume: list[ReasonCode] = Field(default_factory=list)
    open_interest: list[ReasonCode] = Field(default_factory=list)
    realized_volatility: list[ReasonCode] = Field(default_factory=list)


class FuturesResearchDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["FUTURES"]
    contract_code: str
    mapped_from_series: bool
    days_to_expiry: int
    basis: Decimal | None
    annualized_carry: Decimal | None
    roll_state: Literal["NORMAL", "ROLL_WINDOW", "NEAR_EXPIRY", "UNKNOWN"]
    margin_ratio: Decimal | None

    exchange: str
    product_code: str
    mapping_snapshot_id: UUID | None
    normalization_chain_hash: str | None
    last_trade_at: datetime
    delivery_date: date | None
    session_type: Literal["NIGHT", "DAY"]
    next_eligible_session_open: datetime
    curve_state: Literal["BACKWARDATION", "CONTANGO", "FLAT", "UNAVAILABLE"]
    curve_slope: Decimal | None
    curve_curvature: Decimal | None
    bid_ask_spread: Decimal | None
    market_depth: Decimal | None
    volume: Decimal | None
    open_interest: Decimal | None
    realized_volatility: Decimal | None
    price_limit_state: Literal[
        "NORMAL", "LIMIT_UP", "LIMIT_DOWN", "LOCKED", "UNKNOWN"
    ]
    liquidity_grade: Literal["HIGH", "MEDIUM", "LOW", "UNKNOWN"]
    metric_reason_codes: FuturesResearchMetricReasonCodes
```

`days_to_expiry`、`last_trade_at` 和下一会话只在合约主数据及日历门控通过后存在；缺少
这些必需事实时 `asset_details=null` 并由外层 gate 原因解释，禁止填入 `0` 或当前日期。
其余可空数值为 `null` 时，相应 `metric_reason_codes.<field>` 必须包含已注册
`COMMON.*` 或期货原因码；只有真实观测/计算恰好为零时才允许 `0`。未映射自连续序列时
`mapping_snapshot_id/normalization_chain_hash=null` 是结构事实，不伪造映射。

该类型明确禁止 `market_view`、任何 `direction` 别名、`normalized_direction`、
`recommendation`、`position_context`、`trade_intent`、`confidence`、
`probabilities/prediction_heads`、`quality_status` 和 `actionability`。曲线状态、
roll 状态或价格限制只作为研究事实，`OPEN_LONG/CLOSE_LONG` 等展示标签仍只能从公共
动作字段派生。

## 4. 类型路由

### 4.1 商品期货

期限结构、现货基差、仓单、库存、季节、生产、进口、消费和天气。仓单与全社会库存分字段，任何缺失不补 0。

### 4.2 股指期货

标的指数趋势/宽度/波动、现货基差、利率、预期分红、理论持有成本和到期收敛。

### 4.3 国债期货

曲线、久期/DV01、可交割券、转换因子、CTD、隐含回购和交割选择权。缺 CTD 输入时降级为研究。

### 4.4 外汇期货

即期、利差、远期点、基差、央行事件和波动；方向来源可复用外汇事实快照，但期货估值和结果独立。

## 5. 会话和新鲜度

`FuturesCalendar` 返回：

```text
analysis_as_of_at
market_data_available_at
next_eligible_session_open
next_trading_day
session_type = NIGHT | DAY
```

- 有夜盘品种的 19:10 任务可以指向当晚 21:00；
- 无夜盘品种指向下一日盘；
- 节假日前取消夜盘时跳到下一真实会话；
- CFFEX、SHFE、DCE、CZCE、GFEX 按品种规则，不用统一时刻；
- 当前未完成 bar 不能进入日终特征。

## 6. 质量门控

### 6.1 `REJECTED`

- 交易所、到期、乘数、tick、会话或交割方式不明；
- 已到期、停止交易或进入不允许持有窗口；
- 连续序列无当时真实合约映射；
- 建议或评分试图使用连续复权价格；
- normalization chain 含 `available_at > cutoff_at` 的节点、缺少 vintage/source hash，
  或链哈希与 canonical 内容不一致；
- 目标时段无有效双边报价、不可成交或单边涨跌停；
- 行情晚于预测时间；
- 保证金/价格限制规则版本未知；
- 同一个 prediction、评分批次或晋级 cohort 混入不同 `head_spec_hash`。

### 6.2 `DEGRADED`

- 期限结构少于所需有效月份；
- 现货基差单位、品质、税费或时点不能完全对齐；
- 库存、仓单、排名或 COT 过期；
- 只有交易所最低保证金，没有经纪商实际保证金；
- 品种专属基本面覆盖不足。

降级默认发布 `INDETERMINATE + HOLD/AVOID + NONE`，候选方向仅进入受限影子字段。

## 7. 策略

公共趋势、carry、流动性和风险因子先标准化，再进入按类别独立版本化策略。不同类别不共享未经验证的权重。

```text
expected_net_return =
  directional_edge
  + curve_carry
  + basis_convergence
  + type_specific_edge
  - spread
  - slippage
  - fees
  - expected_roll_cost
```

`LONG/SHORT` 仅在预期净收益超过置信区间和成本门槛且质量合格时产生。保证金压力、
交割或涨跌停门控可将候选决定覆盖为
`INDETERMINATE + AVOID + NONE`。公共动作真值表是唯一权威；
`OPEN_LONG/CLOSE_LONG` 等文字只从 `position_context + normalized_direction +
trade_intent` 派生。

策略输出一个主 `PredictionHead`，并将目标契约作为不可变元数据冻结：

```text
head_code = futures.contract_pnl
target_spec_version = futures.contract_pnl.v1
scoreability_rule_version = futures.contract_pnl.scoreability.v1
target_contract = exact identity_level=CONTRACT
labels = LONG | SHORT | NEUTRAL
neutral_band = {value, unit, comparator, neutral_band_version}
probability_model_version = futures.contract_pnl.model.v1
probability_artifact_hash = <sha256>
calibration_version = futures.contract_pnl.calibration.v1
calibration_artifact_hash = <sha256>
training_cutoff_at = <datetime>
baseline_code = futures.cohort_label_prior
baseline_version = futures.cohort_label_prior.v1
head_spec_hash = <公共 canonical PredictionHead spec hash>
primary_for_promotion = true
```

目标的可执行价格和标签算法固定为：

```text
long_net_pnl =
  (exit_bid - long_exit_slippage - entry_ask - long_entry_slippage)
  * contract_multiplier * lots
  - commissions_and_exchange_fees - other_frozen_costs

short_net_pnl =
  (entry_bid - short_entry_slippage - exit_ask - short_exit_slippage)
  * contract_multiplier * lots
  - commissions_and_exchange_fees - other_frozen_costs

long_net_return =
  long_net_pnl / abs(entry_ask * contract_multiplier * lots)
short_net_return =
  short_net_pnl / abs(entry_bid * contract_multiplier * lots)

label =
  LONG     if long_net_return  > neutral_band
  SHORT    elif short_net_return > neutral_band
  NEUTRAL  otherwise
```

使用 ask/bid 已包含可执行点差，`spread_cost` 只做从 mid 到 side 的归因展示，不能再次
从上述净 P&L 扣除。v1 `neutral_band.unit=NOTIONAL_RETURN`，其值、严格比较符和版本随
target spec 冻结。
同一可执行价格路径和非负成本下 LONG/SHORT 不会同时成立；若输入违反该不变量则拒绝，
不能任意挑一个标签。

`HorizonSpec` 的计数也属于 target spec：

- `TRADING_SESSION` 按 `FuturesCalendar.session_id` 计数，夜盘和日盘是不同 session；
  入场取预测后下一合格 session 的冻结开盘窗口首个有效双边报价，退出取第 N 个合格
  session 冻结收盘窗口的最后有效双边报价；
- `TRADING_DAY` 按交易所 `trading_day` 标签去重，归属同一 trading day 的夜盘和日盘
  合计一天；入场规则相同，退出取第 N 个 trading day 的冻结退出窗口；
- entry/exit window、calendar/timezone、N 和 unit 全部进入 `horizon_spec_json`，不得
  用自然日、bar 数或当前日历替代。

冻结的 `scoreability_rule` 规定：入场窗口无双边报价、入退场单边涨跌停且目标 side
不可成交，或规定退出窗口无目标 side 报价时返回 `UNSCORABLE`；不得用 settlement、
mid、连续复权价或下一合约代替。若期限越过 `last_trade_at`，在 target spec 指定的
最后可交易退出窗口按相同 bid/ask 口径评分并记 `MaturityReason.EXPIRY`；该窗口仍无
可执行报价则 `UNSCORABLE`。

概率模型和校准 artifact hash 指向只使用 `training_cutoff_at` 之前样本的不可变制品。
`baseline_code/baseline_version` 唯一解析相同 promotion cohort、标签和
target/scoreability spec 的历史类别先验实现/制品。公共层对 target、scoreability、
labels、模型/校准制品、training cutoff 和 baseline 字段计算 `head_spec_hash`；该哈希
进入 `decision_input_hash`、outcome 和 cohort，聚合器发现 mixed-spec 必须整批拒绝。
连续序列、合同级、平仓规避和 roll-aware 不是四组竞争概率，而是同一候选决定的不同
结果口径。

## 8. 结果

```text
long_gross_executable_pnl = (exit_bid - entry_ask) * multiplier * lots
short_gross_executable_pnl = (entry_bid - exit_ask) * multiplier * lots
net_pnl = gross_executable_pnl - fees - slippage - other_frozen_costs
notional_return = net_pnl / abs(entry_side_price * multiplier * lots)
```

- 入场/退出严格使用主 head 冻结的窗口、side 和成本口径；
- 期限为 1/5/20 个真实 `TRADING_SESSION` 或 `TRADING_DAY`，unit 不得省略且定义随
  target spec 保存；
- 原合约到期前退出，不静默续到下月；
- 策略明确展期时，另算真实两笔交易的 roll-aware 结果；
- 名义收益为跨品种主指标，保证金收益单独展示；
- `futures.contract_pnl` 保存实际合约方向净 P&L；
- `futures.close_avoided_loss` 保存 `trade_intent=CLOSE` 的规避损失；
- `futures.roll_aware_pnl` 保存明确展期规则下的真实换月净 P&L；
- 三者使用不同 `outcome_kind`，并与 `prediction_id + horizon_code +
  evaluator_version` 一起构成唯一结果身份；
- `SELL + CLOSE` 的规避损失与 `SELL + OPEN` 的空头 P&L 分开。
- `OutcomeStatus` 只允许 `PENDING/PARTIAL/SCORED/UNSCORABLE`；正常期限完成、
  到期和换月分别使用 `MaturityReason.HORIZON_REACHED`、
  `MaturityReason.EXPIRY` 和 `MaturityReason.ROLL`。

## 9. API 和前端

```json
{
  "asset_type": "futures",
  "canonical_id": "futures:CFFEX:IF2609:CNY",
  "horizon_code": "5_sessions",
  "position_context": "UNKNOWN"
}
```

`FuturesPanel.vue` 新增真实合约和连续序列双标识、期限结构图、换月、基差/库存、保证金压力、交割倒计时、下一会话和持仓动作矩阵。

普通用户只能读取 `published_decision`；管理员影子页才可读取
`candidate_decision`。提交预测时使用公共
`decision_input_hash`，其规范化输入必须包含请求、持仓上下文、冻结真实合约、
连续映射、normalization chain hash/vintage/source hash、来源快照、HorizonSpec、
`target_spec_version/scoreability_rule_version` 及 target spec 内的 neutral band、
成本、策略、
`probability_model_version/probability_artifact_hash`、
`calibration_version/calibration_artifact_hash/training_cutoff_at`、
`baseline_code/baseline_version` 和 `head_spec_hash`。任何一个字段变化都产生新预测。

## 10. 每日影子调度

`asset_signal_schedules` 为单个期货合约登记身份、时区、日历、cutoff 策略和版本。
中国期货默认任务在 19:10 读取完整日盘数据；是否指向当晚夜盘由
`FuturesCalendar` 决定。运行以 `schedule_id + schedule_version +
scheduled_fire_at + cutoff_at + cutoff_policy_version + policy_version` 生成
`run_key`，加租约锁去重并冻结完整 schedule 配置；补跑继续使用原
`cutoff_at`、原合约标识、normalization chain vintage/source hash、head spec 和
冻结的 schedule 配置，不得吸收补跑时才发布的数据、未来换月或新训练制品。

## 11. 来源和许可

合约规则优先使用 CFFEX、SHFE、DCE、CZCE、GFEX 等交易所；生产实时行情使用合法 CTP/期货公司或商业数据。CME/Cboe 等境外数据依其授权。AKShare 只用于研发回退，MIT 代码许可不覆盖数据权利。
