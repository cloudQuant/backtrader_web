# 191F AI 数字货币设计文档

## 1. 组件

```text
CryptoAssetResolver
  -> CryptoProductResolver
  -> VenueMarketCollector
  -> CompositeReferencePrice
  -> DerivativesCollector
  -> OnChainCollector
  -> TokenomicsCollector
  -> CryptoQualityGate
  -> CryptoDecisionPolicy
  -> CryptoComplianceGate
  -> CryptoReportBuilder
  -> CryptoOutcomeEvaluator
  -> CryptoPromotionEvaluator

CryptoDailyShadowScheduler
  -> AssetResearchOrchestrator
```

所有私有交易方法在本插件中不可注册。若使用 CCXT，只实例化公开市场数据能力。

## 2. 两级研究对象

### 2.1 资产级

`BTC` 等裸输入以 `identity_level=ASSET` 解析为 CAIP/网络资产，场所和报价币可为空，
展示跨场所参考、链上、tokenomics 和系统风险。
由于没有指定可交易 venue/product，普通用户发布结果必须
`actionability=RESEARCH_ONLY`、`normalized_direction=INDETERMINATE`、
`trade_intent=NONE`；资产级内部候选不得冒充产品级可执行评分。

### 2.2 产品级

只有 `venue + market_type + base + quote + settlement + expiry/contract` 完整时，才能计算产品级成本和结果。现货和永续使用 `identity_level=PRODUCT`，有到期日的交割合约使用 `identity_level=CONTRACT`；现货、线性永续、反向永续和交割合约使用不同 P&L。

衍生品风险使用服务端生成而非用户自由填写的标准化情景：

```python
class CryptoDerivativeRiskScenario(BaseModel):
    scenario_kind: Literal["STANDARDIZED_RESEARCH"]
    scenario_version: str
    side: Literal["LONG", "SHORT"]
    contract_quantity: Decimal
    notional: Decimal
    leverage: Decimal
    margin_mode: Literal["ISOLATED", "CROSS_REFERENCE_ONLY"]
    collateral_asset_id: str
    collateral_amount: Decimal
    initial_margin_rate: Decimal
    maintenance_margin_rate: Decimal
    risk_tier_id: str
    liquidation_formula_version: str
    mark_source_id: str
    mark_path_rule_version: str
    rules_available_at: datetime
```

情景值来自版本化风险政策和预测 cutoff 时已经可用的场所规则，不读取账户、余额或实际
仓位。`CROSS_REFERENCE_ONLY` 仍是标准研究近似，不声称模拟用户跨仓。情景、规则和
来源哈希全部进入 `asset_risk_scenario_snapshot_hash` 与 `decision_input_hash`。

## 3. 时点

```python
class CryptoTimeContext(BaseModel):
    generated_at_utc: datetime
    cutoff_at_utc: datetime
    bar_boundary: str
    venue_status: str
    maintenance: bool
    chain_height: int | None
    finalized_at: datetime | None
```

- 现货/永续日线 UTC 00:00 完成，日批次 00:10 UTC；
- 北京 19:10 是 intraday snapshot，只用完成 bar；
- 评分使用生成后经过时长 24h/7d/30d，而非下一交易日；
- CME 等交易所衍生品按自身时段和结算，不套 24×7；
- 链重组和提供方确认延迟按 `finalized_at`。

## 4. 特征

### 4.1 市场

跨 venue 价格、bid/ask、spread、1% 深度、成交、波动和集中度。复合参考价至少两个独立场所，否则标 venue-specific。

### 4.2 衍生品

funding、现货—永续基差、期限基差、OI、清算、long/short 和期权 IV/skew。mark/index 分字段，不能作为默认成交价。

### 4.3 链上

活跃地址、费用、转账量、实现市值/MVRV、交易所净流、持币结构和验证者/质押，仅对定义和数据覆盖合适的资产计算。提供方实体聚类属于模型输出，必须带 provider/version。

### 4.4 tokenomics 和事件

流通/最大供给、排放、解锁、质押、协议收入、治理、集中度、升级、fork、漏洞、监管和上下架。链上活动与价格方向不作单因子等价。

## 5. 质量门控

### 5.1 `REJECTED`

- ticker 对应多个链/合约而未确认；
- venue/product 不存在或交易暂停；
- bid/ask 缺失、过期或 crossed；
- 当前 bar 未完成；
- 跨 venue 价格异常且不能解释；
- quote 稳定币显著脱锚；
- 1% depth 低于版本化目标名义金额；
- 地区或数据许可禁止；
- 永续缺 index/mark/funding 规则。

### 5.2 `DEGRADED`

- 单一 venue，无法构造复合参考；
- 新上市/历史不足；
- token migration、供给异常或解锁数据不完整；
- 链上 provider 不支持；
- 次要事件或市场指标缺失。

链上不支持显示 `UNSUPPORTED`，不能解释为零活动。稳定币换算使用实时风险折价，不固定 1:1。

## 6. 决策、发布和策略

### 6.1 公共决策合同

数字货币插件只使用公共枚举：

```python
normalized_direction: Literal["LONG", "SHORT", "NEUTRAL", "INDETERMINATE"]
position_context: Literal["FLAT", "LONG", "SHORT", "UNKNOWN"]
trade_intent: Literal["OPEN", "ADD", "REDUCE", "CLOSE", "KEEP", "NONE"]
recommendation: Literal["BUY", "SELL", "HOLD", "AVOID"]
```

`market_view=NEUTRAL` 映射 `normalized_direction=NEUTRAL`；
`market_view=INDETERMINATE` 映射 `normalized_direction=INDETERMINATE`。
`REJECTED` 固定为 `recommendation=AVOID`、
`normalized_direction=INDETERMINATE`、`trade_intent=NONE`。

现货空仓 `SHORT` 不映射开空。永续/交割空仓 `SHORT` 仅在服务端
`short_open_research_allowed=true` 时映射 `recommendation=SELL`、
`trade_intent=OPEN`，否则 `trade_intent=NONE`；中国大陆 capability 固定为 false。

### 6.1.1 `CryptoResearchDetails` 强类型 Schema

`ResearchDecision.asset_details` 在数字货币分支只接受以下类型。总体架构最小字段保持
原名和语义，附加字段按现有市场、衍生品、链上、tokenomics、稳定币和标准化风险情景
页面分组，但不保存账户或实际仓位：

```python
class CryptoResearchMetricReasonCodes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    funding_rate: list[ReasonCode] = Field(default_factory=list)
    basis: list[ReasonCode] = Field(default_factory=list)
    composite_reference_price: list[ReasonCode] = Field(default_factory=list)
    composite_venue_count: list[ReasonCode] = Field(default_factory=list)
    best_bid: list[ReasonCode] = Field(default_factory=list)
    best_ask: list[ReasonCode] = Field(default_factory=list)
    spread_bps: list[ReasonCode] = Field(default_factory=list)
    depth_1pct: list[ReasonCode] = Field(default_factory=list)
    stablecoin_conversion_rate: list[ReasonCode] = Field(default_factory=list)
    depeg_bps: list[ReasonCode] = Field(default_factory=list)
    open_interest: list[ReasonCode] = Field(default_factory=list)
    mark_price: list[ReasonCode] = Field(default_factory=list)
    index_price: list[ReasonCode] = Field(default_factory=list)
    chain_height: list[ReasonCode] = Field(default_factory=list)
    active_addresses: list[ReasonCode] = Field(default_factory=list)
    transfer_volume: list[ReasonCode] = Field(default_factory=list)
    mvrv: list[ReasonCode] = Field(default_factory=list)
    exchange_netflow: list[ReasonCode] = Field(default_factory=list)
    staking_ratio: list[ReasonCode] = Field(default_factory=list)
    circulating_supply: list[ReasonCode] = Field(default_factory=list)
    max_supply: list[ReasonCode] = Field(default_factory=list)
    next_unlock_ratio: list[ReasonCode] = Field(default_factory=list)


class CryptoResearchDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["CRYPTO"]
    network: str | None
    venue: str | None
    product_type: Literal["ASSET", "SPOT", "PERPETUAL", "DELIVERY_FUTURE"]
    quote_currency: str | None
    funding_rate: Decimal | None
    basis: Decimal | None
    onchain_regime: Literal["EXPANDING", "CONTRACTING", "MIXED", "UNAVAILABLE"]
    venue_risk_grade: Literal["LOW", "MEDIUM", "HIGH", "UNKNOWN"]

    asset_id: str
    base_asset: str
    settlement_currency: str | None
    contract_formula: Literal["NOT_APPLICABLE", "LINEAR", "INVERSE", "UNKNOWN"]
    composite_reference_price: Decimal | None
    composite_venue_count: int | None
    best_bid: Decimal | None
    best_ask: Decimal | None
    spread_bps: Decimal | None
    depth_1pct: Decimal | None
    stablecoin_conversion_rate: Decimal | None
    depeg_bps: Decimal | None
    open_interest: Decimal | None
    mark_price: Decimal | None
    index_price: Decimal | None
    standardized_risk_scenario: CryptoDerivativeRiskScenario | None
    risk_scenario_snapshot_hash: str | None
    chain_height: int | None
    finalized_at: datetime | None
    active_addresses: Decimal | None
    transfer_volume: Decimal | None
    mvrv: Decimal | None
    exchange_netflow: Decimal | None
    staking_ratio: Decimal | None
    circulating_supply: Decimal | None
    max_supply: Decimal | None
    next_unlock_ratio: Decimal | None
    metric_reason_codes: CryptoResearchMetricReasonCodes
```

Schema 校验器逐项要求：任何可空数值为 `null` 时，对应
`metric_reason_codes.<field>` 至少包含一个已注册 `COMMON.*` 或 `CRYPTO.*`；只有来源
事实确实为零时才能保存 `0`。链上不支持、无复合参考、无 funding/OI、稳定币换算未知
或 tokenomics 缺失一律保持 `null + reason`，不能解释成零活动或零风险。衍生品风险
情景只有完整时才整体出现；否则
`standardized_risk_scenario/risk_scenario_snapshot_hash=null` 并由外层 gate 原因解释。

该类型明确禁止 `market_view`、任何 `direction` 别名、`normalized_direction`、
`recommendation`、`position_context`、`trade_intent`、`confidence`、
`probabilities/prediction_heads`、`quality_status` 和 `actionability`。
`standardized_risk_scenario.side` 只是服务端冻结的压力路径维度，不是候选或发布方向，
不得覆盖公共 `ResearchDecision`，也不得派生杠杆/订单建议。

### 6.2 候选与安全发布

```text
candidate = CryptoDecisionPolicy(features, point_in_time_snapshot)
published = CryptoPublishPolicy(candidate, quality, promotion_scope, compliance)
```

- `candidate_decision_json` 只在批准的隔离环境生成，只供影子评估器和授权管理员；
- `SHADOW/SUSPENDED/未登记` 时，普通用户固定收到
  `market_view=INDETERMINATE`、`actionability=RESEARCH_ONLY`、
  `normalized_direction=INDETERMINATE`、`trade_intent=NONE`，
  `recommendation=HOLD/AVOID`，并包含 `COMMON.MODEL_NOT_PROMOTED`；
- 地区限制优先级最高，固定收到
  `market_view=INDETERMINATE`、`actionability=REGION_RESTRICTED`、
  `normalized_direction=INDETERMINATE`、`recommendation=AVOID`、
  `trade_intent=NONE`，并包含 `CRYPTO.REGION_RESTRICTED`；
- 只有精确 `promotion_scope_key` 状态为 `PROMOTED`，且质量、产品、地区和许可均通过，
  才可将候选方向投影为普通用户发布决定；
- API、前端、研报和导出只消费 `published_decision_json`。

### 6.3 策略

现货和衍生品使用独立策略：

```text
spot_expected_net_return =
  macro_liquidity_edge
  + spot_market_edge
  + onchain_edge
  + tokenomics_edge
  - spread
  - fee
  - slippage
  - quote_asset_risk

perp_expected_net_return =
  spot_direction_edge
  + basis_edge
  + positioning_edge
  - spread
  - fee
  - slippage
  - expected_funding
  - liquidation_risk_penalty
```

`liquidation_risk_penalty` 只来自冻结的 `STANDARDIZED_RESEARCH` 情景；不得从
缺失的用户杠杆或保证金猜测，也不得反向生成杠杆建议。

场所、安全、托管、oracle、bridge、监管和深度风险可直接覆盖为 AVOID。LLM 不生成价格目标、概率或杠杆。

## 7. 结果

### 7.1 现货

- `normalized_direction=LONG`：ask 入场、bid 退出；
- SELL 只评价持有资产的规避损失；
- 包含交易费、滑点和报价币换算；
- altcoin 同时提供相对现金和 BTC/ETH 基准。

### 7.2 永续

- 按线性/反向公式计算，不共用一个 P&L；
- 累计每个 funding interval；
- 到期后仍在允许延迟窗口等待 funding 时为 `OutcomeStatus.PARTIAL`；超过最终化 SLA
  仍缺 funding 时为 `OutcomeStatus.UNSCORABLE` 和
  `CRYPTO.FUNDING_UNAVAILABLE`；
- 标准化情景按冻结的维持保证金、risk tier、清算公式和真实 mark 路径评价；
- 情景触发清算即判定该情景完整失败，不删除样本，也不声称用户实际清算；
- mark 只用于清算/风险，入退仍用可成交双边价。

### 7.3 交割

到期正式结算或按预测快照中的明确 roll 规则；不静默跨合约。

不同 venue、quote、spot/perp、linear/inverse 不合并成绩单。

### 7.4 多评价 head 和成熟

| 产品 | `outcome_kind` | 评价内容 |
| --- | --- | --- |
| 现货 | `crypto.spot_pnl` | ask→bid 后的费用、滑点和报价币换算净收益 |
| 现货 | `crypto.benchmark_excess` | 相对现金及预测快照指定 BTC/ETH 基准的超额收益 |
| 永续/交割 | `crypto.derivative_pnl` | 线性/反向 P&L、费用、滑点、funding 和结算 |
| 永续/交割 | `crypto.liquidation_risk` | 冻结标准情景的保证金、清算和 mark 风险路径 |
| 全部 | `crypto.risk_path` | 最大不利/有利波动、实现波动和场所中断 |

唯一键为 `(prediction_id, horizon_code, outcome_kind, evaluator_version)`。每个 head
独立使用 `OutcomeStatus.PENDING/PARTIAL/SCORED/UNSCORABLE`；到期事件单列：

产品级候选决定只注册一个主 `PredictionHead`：现货为 `crypto.spot_pnl`，
永续/交割为 `crypto.derivative_pnl`，标签均为 `LONG/SHORT/NEUTRAL`；分别冻结
`target_spec_version/scoreability_rule_version`、现货或线性/反向 P&L 公式、
bid/ask/fee/slippage/funding/quote 换算、版本化 no-trade band、概率模型与
artifact、校准 artifact/training cutoff、基线版本和 `head_spec_hash`。其余
outcome kind 是预注册经济
结果 head，不参与主概率分布归一。资产级无 venue/product 研究的 head 列表为空。
不同 `head_spec_hash`、venue/product/quote 或风险情景的样本不得混入同一 Brier、
基线或晋级 cohort。

- 24h/7d/30d：`MaturityReason.HORIZON_REACHED`；
- 交割合约终止：`MaturityReason.EXPIRY`；
- 快照已声明的滚动：`MaturityReason.ROLL`；
- 永久下架：`MaturityReason.DELISTING`。

不得使用 `MATURED` 状态。仅 `OutcomeStatus.SCORED` 进入相应指标分母；
`OutcomeStatus.PARTIAL`、`OutcomeStatus.UNSCORABLE` 的数量、字段缺口和
`CRYPTO.*` 原因码必须展示。

### 7.5 晋级作用域

```text
promotion_scope_key =
  SHA-256(canonical_json(PromotionScope))
```

注册表在 scope key 外独立冻结 `head_spec_hash`、target/scoreability/baseline、
模型与校准 artifact、training cutoff、风险情景及策略/模型/校准版本。

`INSTRUMENT_SPECIFIC` 只使用单一 `canonical_id`，至少 200 条成熟行动信号。
`POOLED` 仅允许同 venue/product family、产品/P&L 类型、报价与结算约定、成本和策略
完全共享的产品合并；至少 5 个产品、每个 20 条、总计 200 条，任一产品不超过 40%。
spot/perpetual/delivery、linear/inverse、法币/稳定币报价不跨池。成绩单同时报告聚合、
每个充分样本产品和最差风险切片；晋级状态不得传播到其他 key。

`crypto.liquidation_risk` 的 outcome 保存完整 scenario JSON、规则快照哈希和
`SURVIVED/LIQUIDATED` 标签。缺 leverage、quantity/notional、collateral、margin
tier、维持保证金、公式或合法 mark path 时返回
`OutcomeStatus.UNSCORABLE + CRYPTO.LIQUIDATION_SCENARIO_INCOMPLETE`，不能使用
今天的场所规则补算旧预测。

## 8. 合规和 API

请求：

```json
{
  "asset_type": "crypto",
  "canonical_id": "crypto:coinbase:BTC-USD:spot:bitcoin",
  "horizon_code": "7d",
  "position_context": "UNKNOWN"
}
```

中国大陆响应强制：

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
  "reason_codes": ["CRYPTO.REGION_RESTRICTED"]
}
```

`position_context` 原样保留请求中的公共枚举值。前端不能通过修改地区参数绕过，合规
判断来自可信租户配置和服务端策略。

## 9. 页面

`CryptoPanel.vue` 显示资产/链/合约地址、场所/产品、跨场所价、深度、
funding/basis/OI、链上、tokenomics、安全、稳定币和地区风险。清算卡固定标注
“标准化研究压力情景，非实际仓位或杠杆建议”，并展示 scenario version；大陆模式
隐藏方向概率并显示研究教育限制，不展示交易链接。

## 10. 来源和开源

- [Coinbase 公开市场 API](https://docs.cdp.coinbase.com/exchange/introduction/welcome)和其他合法 venue 用于具体市场；
- [Kraken 市场分析](https://docs.kraken.com/api/docs/futures-api/charts/market-analytics)可提供 funding/basis/OI 等；
- [Bitcoin Core RPC](https://developer.bitcoin.org/reference/rpc/)和[Ethereum JSON-RPC](https://ethereum.org/developers/docs/apis/json-rpc/)提供可验证链上入口；
- CoinGecko 只作聚合参考；
- CCXT 为 MIT，公开市场适配候选；Freqtrade 为 GPLv3，只参考 dry-run/前视检测；
- 每个交易所和数据商的存储、展示、再分发条款独立审批。

## 11. 每日影子运行

1. 审批静态清单在配置阶段展开为“一产品、一期限、一 schedule”，运行时不扫描市场；
2. 每个 UTC 自然日 00:00 冻结 `analysis_cutoff_at`，00:10 触发检查；
3. 每个 schedule 以
   `run_key=SHA-256(schedule_id|schedule_version|scheduled_fire_at|cutoff|
   cutoff_policy_version|policy_version)` 去重并冻结完整配置；
4. 00:25、01:10 只重试该 schedule 的失败运行；
5. 03:00 对账和服务重启 catch-up 仍复用原 run/cutoff，下一 UTC cutoff 后不改写旧
   candidate；
6. 补跑只读 `available_at <= analysis_cutoff_at`，包括价格、funding、链上
   `finalized_at` 和事件；
7. 相同 `decision_input_hash/prediction_key` 冲突时返回已有不可变预测；
8. 场所维护只失败对应 schedule，最终失败保留阶段、尝试次数和原因码；
9. 北京 19:10 盘中快照使用独立 run type，不进入每日 00:00 cohort 或 T2 分母。

## 12. `ReasonCode` 命名空间

数字货币插件只返回公共注册表中的大写资产命名空间稳定码：
`CRYPTO.INSTRUMENT_AMBIGUOUS`、`CRYPTO.PRODUCT_UNSUPPORTED`、
`CRYPTO.QUOTE_UNAVAILABLE`、`COMMON.DATA_STALE`、
`CRYPTO.QUOTE_INCONSISTENT`、`CRYPTO.BAR_INCOMPLETE`、
`CRYPTO.DEPTH_INSUFFICIENT`、`CRYPTO.STABLECOIN_DEPEG`、
`CRYPTO.VENUE_UNAVAILABLE`、`CRYPTO.FUNDING_UNAVAILABLE`、
`CRYPTO.ONCHAIN_UNSUPPORTED`、`CRYPTO.CHAIN_UNFINALIZED`、
`COMMON.MODEL_NOT_PROMOTED`、`CRYPTO.REGION_RESTRICTED`、
`COMMON.SOURCE_LICENSE_BLOCKED`、`CRYPTO.RISK_NOT_MEASURABLE`、
`CRYPTO.LIQUIDATION_SCENARIO_INCOMPLETE`。未知异常映射到
公共稳定码并保留内部诊断，不得把异常文本或临时字符串写入 `reason_codes`。
