# 191A AI 债券需求文档

## 1. 业务目标

用户输入一只债券后，系统识别具体债项和市场，以合同现金流、收益率曲线、信用利差、利率风险、流动性和含权条款为基础，给出指定期限的买入、卖出、持有或暂不参与研究建议，并生成可追溯研报和历史预测成绩单。

## 2. 目标用户与场景

- 研究员：比较债券相对同币种、同信用、同久期基准的价值；
- 普通投资者：理解票息、收益率、久期、信用和流动性风险；
- 风控/产品人员：检查建议使用了什么曲线、估值、条款和数据时点；
- 模型研究人员：用未来含息总回报验证历史建议。

## 3. v1 范围

### 3.1 可进入方向信号

- 境内交易所和银行间普通固定利率、零息国债；
- 政策性金融债；
- 有完整合同、估值、曲线、评级和财务披露的普通信用债；
- 美国国债；美国公司债仅在取得合法 TRACE/主数据授权后开放。

### 3.2 仅研究展示

- 浮息债、可赎回/可回售债：数据和模型完整时展示估值，方向模型保持影子；
- 可转债、永续债、违约/特定债、ABS/MBS、复杂分层和私募债：v1 不给可行动方向；
- 上述品种返回 `actionability=RESEARCH_ONLY` 和所缺专属模型，不退化到普通债券算法。

## 4. 输入和身份

用户可输入本地代码、ISIN、名称或发行人关键词。系统必须返回候选并要求确认，规范身份至少包括：

```text
canonical_id
identity_level
isin
local_code
venue
issuer
issue_name
currency
face_value
issue_date
accrual_start_date
maturity_date
remaining_principal
coupon_type
coupon_rate
payment_frequency
day_count
settlement_calendar
seniority
option_features
```

搜索候选使用 `candidate_kind=ISSUER/ISSUE/LISTING`；持久化后的公共
`identity_level` 只能使用总架构枚举，并通过 `bond_identity_kind` 保存债券专属类型：

- `candidate_kind=ISSUER`：发行人搜索结果，只用于继续选择债项，不持久化为
  `InstrumentIdentity`，不可启动分析；
- `bond_identity_kind=ISSUE`：唯一债项，映射 `identity_level=ASSET`。只有使用
  跨场所官方估值、且 `actionability=RESEARCH_ONLY` 时，`venue` 才允许为空；
- `bond_identity_kind=LISTING`：具体交易场所的上市/流通实例，映射
  `identity_level=PRODUCT`。使用本地代码、成交、双边报价或生成可执行结果时，
  `venue` 必填。

同一代码跨市场、同一发行人多期债券或同一债项存在多个可交易场所时不得静默选择，返回稳定原因码 `COMMON.INSTRUMENT_AMBIGUOUS`。规范 ID 示例为 `bond:issue:CND10001ABC2:CNY` 和 `bond:listing:XSHG:019547:CNY`。

### 4.1 预门控采集合同

搜索和采集必须先生成 `RawBondIdentityCandidate` 与 `RawBondSnapshot`。到期日、永续标识、合同条款、价格、曲线和基准在原始模型中均允许为空；每个叶子字段都必须同时保存 `provenance`、`observed_at`、`published_at`、`available_at` 和 `retrieved_at`。来源未给出事实发生或发布时间时，对应时点可以为空，但缺失事实本身仍有来源、可用时点和获取时点。

原始候选/快照必须先以内容哈希不可变落库，再由质量门控产出稳定、有序的 `COMMON.*` / `BOND.*` `ReasonCode`。只有门控确认关键输入完整后，才可构造字段非空的 `PostGateBondSnapshot` 并进入估值。普通债到期日缺失、合同不完整、价格/曲线/基准缺失都不能在原始 Pydantic 模型阶段形成 422 或未捕获 500。

原始候选不改变公共身份映射：`ISSUER` 仍只用于搜索；门控后的
`bond_identity_kind=ISSUE/LISTING` 仍分别映射公共
`identity_level=ASSET/PRODUCT`。已确认永续债允许
`maturity_date=null`，但 v1 必须返回
`quality_status` 为 `ELIGIBLE` 或 `DEGRADED`，
`actionability=RESEARCH_ONLY + BOND.PERPETUAL_MODEL_REQUIRED`；无法证明永续属性的
普通债缺到期日返回 `quality_status=REJECTED`、
`actionability=INSUFFICIENT_DATA + AVOID/NONE + BOND.MATURITY_MISSING`。两条路径都保留
`raw_candidate_id/raw_snapshot_id` 和可安全展示的来源事实。

## 5. 功能需求

| 编号 | 需求 |
| --- | --- |
| BOND-FR-001 | 按代码、ISIN、名称搜索，展示市场、发行人、到期、票息和币种候选。 |
| BOND-FR-002 | 构建未来合同现金流，校验净价 + 应计利息 = 全价。 |
| BOND-FR-003 | 计算 YTM、YTW、Macaulay/修正久期、凸性、DV01，以及数据允许时的 Z-spread/OAS。 |
| BOND-FR-004 | 匹配同币种、同信用、同久期收益率曲线和财富指数基准。 |
| BOND-FR-005 | 分解 carry、roll-down、利率曲线、信用利差、含权、汇率、违约和成本贡献。 |
| BOND-FR-006 | 信用债分析发行人偿债能力、融资、评级、契约、违约和重大事件；政府债不要求公司财务。 |
| BOND-FR-007 | 输出 20/60/120 个债券交易日的方向、建议、概率、适用价格、质量和失效条件。 |
| BOND-FR-008 | 生成包含十四个规定章节的中文研报并支持导出和保存。 |
| BOND-FR-009 | 在门控前保存不可变原始候选和字段级来源快照，再保存预测、曲线/估值/策略版本和后续含息总回报。 |
| BOND-FR-010 | 展示分期限、债券类型、久期、评级和流动性层级的历史质量。 |
| BOND-FR-011 | 关键到期、现金流、曲线、基准或价格不可用时保留审计快照并返回 `quality_status=REJECTED + actionability=INSUFFICIENT_DATA + AVOID/NONE`；仅研究品种使用 `ELIGIBLE/DEGRADED + RESEARCH_ONLY`，不得抛领域缺失型 422/500。 |
| BOND-FR-012 | 数据许可只允许研究或禁止派生时，由服务端限制报告字段和导出。 |
| BOND-FR-013 | 结构化决策只使用公共 `normalized_direction`、`position_context`、`trade_intent`、`recommendation` 枚举，并区分候选决策与面向普通用户的发布决策。 |
| BOND-FR-014 | 每个期限分别保存可执行净超额、估值净超额和信用事件结果头，统一使用 `OutcomeStatus`、`MaturityReason` 和资产原因码。 |
| BOND-FR-015 | 按市场截止时点每日运行影子分析；重跑、故障续跑和历史回补必须幂等且遵守 point-in-time。 |
| BOND-FR-016 | 模型晋级按 `promotion_scope_key` 隔离池化与单券范围，并披露样本集中度。 |
| BOND-FR-017 | 机器原因使用稳定 `ReasonCode`：通用原因属于 `COMMON.*`，债券专属原因属于 `BOND.*`，展示文案由原因码本地化。 |

## 6. 建议语义

`quality_status` 与 `actionability` 是正交公共字段，不得互相塞值：

```text
quality_status = ELIGIBLE | DEGRADED | REJECTED
actionability  = ACTIONABLE | RESEARCH_ONLY | INSUFFICIENT_DATA | REGION_RESTRICTED
```

- 地区禁止：保留独立数据质量值，`actionability=REGION_RESTRICTED`；
- 关键数据、许可或风险失败：`quality_status=REJECTED` 且
  `actionability=INSUFFICIENT_DATA`；
- 永续/复杂品种、`DEGRADED` 或模型未晋级：质量只取
  `ELIGIBLE` 或 `DEGRADED`，`actionability=RESEARCH_ONLY`；
- 已晋级且质量合格：`quality_status=ELIGIBLE` 且
  `actionability=ACTIONABLE`。

发布覆盖优先级为 `REGION_RESTRICTED > INSUFFICIENT_DATA > RESEARCH_ONLY >
ACTIONABLE`。`NONE` 只允许作为 `trade_intent`，绝不是合法 `actionability`；
`RESEARCH_ONLY` 也绝不是合法 `quality_status`。

系统不得定义债券私有动作枚举。结构化决策只允许以下公共字段：

```text
normalized_direction = LONG | SHORT | NEUTRAL | INDETERMINATE
position_context     = FLAT | LONG | SHORT | UNKNOWN
trade_intent         = OPEN | ADD | REDUCE | CLOSE | KEEP | NONE
recommendation       = BUY | SELL | HOLD | AVOID
```

v1 为 long-only 研究产品，不支持裸做空，映射规则为：

| 策略判断 | 持仓上下文 | 结构化结果 |
| --- | --- | --- |
| 正优势 | `FLAT` | `LONG / FLAT / OPEN / BUY` |
| 正优势 | `LONG` | `LONG / LONG / ADD / BUY` |
| 负优势或信用恶化 | `LONG` | `SHORT / LONG / REDUCE` 或 `CLOSE / SELL` |
| 负优势 | `FLAT` | 候选层可记 `SHORT / FLAT / NONE / HOLD`，发布层不得给出 `SELL` |
| 无交易优势 | `LONG` | `NEUTRAL / LONG / KEEP / HOLD` |
| 无交易优势 | `FLAT` | `NEUTRAL / FLAT / NONE / HOLD` |
| 硬门控失败 | 任意 | `INDETERMINATE / 原上下文 / NONE / AVOID` |

表中四元组依次为 `normalized_direction / position_context / trade_intent / recommendation`。`position_context=UNKNOWN` 时，可以在受限候选层保存条件性判断，但发布层 `trade_intent=NONE`，文字必须写成“若空仓/若持有”。输入 `SHORT` 在 v1 返回 `INDETERMINATE / SHORT / NONE / AVOID` 和 `COMMON.POSITION_CONTEXT_UNSUPPORTED`。

`BUY` 表示成本后含息总回报相对匹配基准有足够正优势且全部门控通过；`SELL` 只表示减持或退出已有多头；`HOLD` 表示保持当前状态或空仓观望；`AVOID` 表示关键数据、可执行性、许可或风险门控失败。违约、停牌或无报价债券不得把“无法退出”伪装为正常可执行 `SELL`。所有结果固定 `execution_disabled=true`。

默认持有期限为 60 个债券交易日，用户可以选择 20 或 120 日。所有建议都显示使用的净价/全价、估值日期及“官方估值不等于可成交报价”。

### 6.1 影子发布双层合同

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

- 中国债券交易日于 `19:10 Asia/Shanghai` 启动，分析截止时间固定为当日 19:00；
- 美国债券交易日于 `18:30 America/New_York` 启动，截止时间为 18:15；未取得所需许可时该能力关闭；
- v1 每条 schedule 只绑定一个已确认 `canonical_id`；审批静态清单只在配置阶段展开成多条 schedule，运行时不得扫描市场或按 `venue_scope/universe` 扩展；
- 公共访问主体固定为
  `access_principal=owner_scope|coalesce(user_id,"SYSTEM")`；
- `run_key=SHA-256(schedule_id_or_manual_scope_with_access_principal|schedule_version|scheduled_fire_at|cutoff_at|cutoff_policy_version|policy_version)`，重复触发只在同一访问主体内关联既有运行；
- 冻结输入生成 `decision_input_hash`，
  `prediction_key=SHA-256(access_principal|decision_input_hash)`；只有访问主体和输入都
  相同时才复用预测，`owner_scope` 相同但 `user_id` 不同绝不能复用；
- 历史回补必须显式传入历史 `as_of_date/cutoff_at`，只读取当时已可用数据，不允许用当前修订值补旧预测。

### 7.2 多结果头

每个预测和期限允许保存：

```text
bond.executable_total_return
bond.valuation_total_return
bond.credit_event
```

`bond.executable_total_return` 是方向信号主结果头；无可执行报价时可以生成估值研究头，但不得进入可执行命中率。结果唯一键为 `(prediction_id, horizon_code, outcome_kind, evaluator_version)`。

可行动候选预测必须包含主 `PredictionHead`
`bond.executable_total_return`，标签为
`POSITIVE_EXCESS/NEGATIVE_EXCESS/NEUTRAL`，并完整继承公共 `PredictionHead`：
冻结 `target_spec_version/scoreability_rule_version`、
`probability_model_version/probability_artifact_hash`、
`calibration_version/calibration_artifact_hash/training_cutoff_at`、
`baseline_code/baseline_version` 和可复算 `head_spec_hash`。信用债可
另带非主 head `bond.credit_event`，
标签为 `EVENT/NO_EVENT`；两组概率独立归一。仅有官方估值、没有可执行报价时，
不伪造主 head，`primary_head_code=null`。

任何 `head_spec_hash` 或 target、scoreability、概率/校准 artifact、基线版本不同的
记录必须分 cohort；聚合器遇到 mixed-spec cohort 必须拒绝，不能重贴标签后合并
Brier、基线或晋级分母。

每个结果头的 `OutcomeStatus` 统一为 `PENDING | PARTIAL | SCORED | UNSCORABLE`：未到成熟时点为 `PENDING`，已取得部分真实数据但尚不能完成全口径为 `PARTIAL`，完整评分为 `SCORED`，按预测时冻结规则永久无法取得合法结果为 `UNSCORABLE`。

成熟原因与结果状态分离，`MaturityReason` 使用 `HORIZON_REACHED | EXPIRY | MATURITY | CALL | REDEMPTION | ROLL | DELISTING` 等公共枚举。未成熟、价格缺失、基准缺失、现金流不完整等分别使用 `COMMON.OUTCOME_NOT_MATURED`、`COMMON.OUTCOME_PRICE_MISSING`、`COMMON.OUTCOME_BENCHMARK_MISSING`、`BOND.OUTCOME_CASHFLOW_INCOMPLETE`。

### 7.3 晋级范围

```text
promotion_scope_key = SHA-256(canonical_json(PromotionScope {
  scope_type, asset_type=bond, instrument_class, canonical_id, venue,
  product_type, signal_head, horizon_code,
  scope_parameters={currency, venue_group, duration_bucket, credit_bucket}
}))
```

- `policy_version/model_version/calibration_version` 是模型注册表唯一键的独立列，
  不重复写入 scope key；
- 两类 scope 都至少需要 200 个已成熟、可评分的行动主结果头、至少 60 个去重
  `cutoff_date`、3 个按冻结规则确定的市场状态，并满足时间顺序 walk-forward、
  purge/embargo 和至少 60 个交易日前瞻影子日；
- `POOLED`：额外覆盖至少 5 个经济实体组、政府债和信用债、至少 3 个久期桶及
  3 个流动性桶；任一组占比不超过 40%，同时报告 HHI。相同债项跨场所按一个经济
  实体组统计；
- `INSTRUMENT_SPECIFIC`：键中必须包含具体 `canonical_id`，允许单券占比 100%，
  但晋级只解锁该券，不能外推到其他债券；不要求政府债/信用债并存，也不要求
  3 个久期桶、3 个流动性桶或 5 个实体组；
- 两种范围的样本、指标、审批和回退互相隔离，且都必须满足总计划规定的前向影子期。

## 8. 必需数据

本节字段是进入 `PostGateBondSnapshot` 和可行动分析的必需数据，不是
`RawBondSnapshot` 的构造前提。任何缺失都先落原始审计快照，再由门控决定
`quality_status` 和 `actionability`。

### 8.1 合同和主数据

- ISIN、市场、币种、面值、起息、到期、剩余本金；
- 票息、付息频率、日计数、结算日历；
- 偿还、call/put/回售/提前偿还安排；
- 受偿顺序、担保、抵押和契约。

### 8.2 市场和基准

- 净价、应计利息、全价、bid/ask、成交和官方估值；
- 收益率曲线 ID、曲线日期和期限点；
- 同币种、同信用、同久期财富指数；
- 交易量、最后成交时间和流动性标签。

### 8.3 信用

- 债项/主体评级、机构、日期、展望和观察名单；
- 法定财务披露时间、现金、短债、总债务、利息保障、经营/自由现金流；
- 付息、展期、违约、交叉违约、诉讼和评级事件。

新闻为空只降低证据覆盖率，不能解释为“没有负面事件”。

## 9. 研报要求

研报固定包含：

1. 债券身份、市场和关键条款；
2. 建议、行动资格、期限和适用价格；
3. 数据日期、来源和完整性；
4. 净价/全价、YTM/YTW 和相对估值；
5. 曲线、carry 和 roll-down；
6. 久期、凸性、DV01 和利率情景；
7. 信用、偿债、契约和评级变化；
8. 流动性、bid-ask、成交与估值可执行性；
9. 含权和提前偿还风险；
10. 宏观与近期事件；
11. 牛/基准/熊总回报情景；
12. 正方、反方证据和失效条件；
13. 历史预测、成熟样本和质量；
14. 风险提示与方法版本。

## 10. 非功能和合规要求

- 相同快照和版本重放必须产生相同结构化建议；
- 同一原始载荷和 gate 版本必须产生相同 `ReasonCode` 顺序与安全发布结果；
- `prediction_key` 必须包含公共 `access_principal`；不同用户即使具有相同
  `owner_scope/decision_input_hash` 也不得复用预测、候选或发布决定；
- 原始快照接受领域字段空值；缺到期、合同、价格、曲线或基准由质量门控处理，
  API 不得把这些来源缺失返回为 Pydantic 422 或未捕获 500；
- 计算金额使用 `Decimal`，日期使用债券市场和支付日历；
- 重要数值与 QuantLib 或独立黄金用例交叉验证；
- LLM 不计算现金流、不覆盖建议和置信度；
- 服务端只保存稳定的 `COMMON.*` 或 `BOND.*` `ReasonCode`；人类可读中文由版本化映射生成，不把异常文本当机器码；
- 中债、外汇交易中心、交易所、TRACE 等数据在生产使用前完成授权；
- 未完成投资咨询和适当性审查前只提供研究信号，不执行交易或承诺收益。

## 11. 需求完成条件

- BOND-FR-001 至 017 均有自动化测试和验收映射；
- 至少一个国债、一个普通信用债、一个含权债、一个已确认永续债和一个到期日未知
  的普通债固定样例；
- 跨付息、提前赎回和过期估值结果可重复；
- 永续样例保存审计快照，发布时 `quality_status` 为 `ELIGIBLE` 或 `DEGRADED` 且
  `actionability=RESEARCH_ONLY`；缺到期/合同/价格/曲线/基准样例发布
  `REJECTED + INSUFFICIENT_DATA + AVOID/NONE`，且接口无领域缺失型 422/500；
- 技术验收通过后先进入影子模式，模型晋级按总计划执行。
