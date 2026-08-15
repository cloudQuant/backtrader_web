# 191D AI 期权需求文档

## 1. 业务目标

用户输入一个精确期权合约后，系统结合标的方向、波动率、期权链、理论价值、Greeks、流动性和到期风险，分别给出标的观点、波动率观点、合约价值和持仓动作，生成研报并用真实双边报价验证。

## 2. 产品安全原则

- 单个“看涨/看跌分数”不足以描述期权；
- 买入看跌期权是合约买入但通常代表标的看空；
- `SELL` 在 v1 只允许卖出平掉已有期权多头；
- v1 禁止裸卖、无限损失建议和自动多腿执行；
- 标的方向正确不等于期权合约盈利；
- mid 和理论价不是默认可成交价格。

## 3. v1 范围

- 有完整合约主数据、同步标的、双边报价和足够期权链的境内股指/ETF 或商品期权；
- 欧式和美式按行权方式选择模型；
- 支持买入看涨、买入看跌、维持或平掉已有权利仓；
- 有限风险多腿策略只在报告中说明，作为未来独立原子对象实现；
- 0DTE、极近到期、裸卖和缺完整链合约默认研究或拒绝。

## 4. 身份和输入

精确合约至少包含：

```text
identity_level = CONTRACT
option_contract_id
exchange
underlying_instrument_id
underlying_contract_id
call_put
strike
expiry_at
last_trade_at
exercise_style
settlement_type
deliverable
contract_multiplier
quote_unit
tick_size
trading_calendar_id
automatic_exercise_rule
position_limit_rule
margin_rule_version
```

输入裸标的代码时只返回可筛选的到期和期权链，不自动选择某个行权价。用户必须确认 C/P、到期和行权价。

## 5. 功能需求

| 编号 | 需求 |
| --- | --- |
| OPT-FR-001 | 解析标的、到期、行权价、C/P、乘数、行权和结算方式。 |
| OPT-FR-002 | 加载与合约同步的标的价格、完整或合格覆盖的期权链和相邻到期。 |
| OPT-FR-003 | 按欧式/美式、现货/期货标的选择 Black-76、BSM 或提前行权模型。 |
| OPT-FR-004 | 计算 IV、Delta、Gamma、Theta、Vega、Rho、盈亏平衡和最大损失。 |
| OPT-FR-005 | 分析实现/隐含波动、期限结构、微笑、偏度和曲面质量。 |
| OPT-FR-006 | 检查价格边界、put-call parity、单调/凸性和跨期总方差。 |
| OPT-FR-007 | 分析 bid/ask、深度、成交量、持仓量、报价年龄和可执行成本。 |
| OPT-FR-008 | 输出标的观点、波动率观点、合约价值、BUY/SELL/HOLD/AVOID 和持仓意图。 |
| OPT-FR-009 | guard 校验完整 ResearchDecision 动作元组和同一 access principal、同一 canonical 合约的不可变持仓上下文快照；SHORT、`SELL + OPEN` 和无有效 LONG 上下文的 CLOSE 均 fail-closed，并由 Schema、服务、数据库三层拒绝。 |
| OPT-FR-010 | 生成十三个规定章节、期权链、IV 和盈亏图研报。 |
| OPT-FR-011 | 用独立预测 head 和 outcome kind 保存并评价标的方向、IV 方向和精确合约 P&L。 |
| OPT-FR-012 | 报价、IV、链、到期或风险不合格时拒绝可行动建议。 |
| OPT-FR-013 | 只对审批的精确 `CONTRACT` schedule 每日影子运行，支持锁、幂等、冻结具体合约补跑和晋级审计；选约规则仅可在配置阶段展开，不得在运行时选约。 |

## 6. 建议语义

资产专属研究 head：

```text
underlying_view: BULLISH | BEARISH | NEUTRAL
volatility_view: VOL_UP | VOL_DOWN | NEUTRAL
contract_edge: CHEAP | FAIR | RICH | UNKNOWN
```

动作仍只以公共字段为权威：

| `position_context` | `normalized_direction` | `recommendation` | `trade_intent` |
| --- | --- | --- | --- |
| `FLAT` | `LONG` | `BUY` | `OPEN` |
| `LONG` | `LONG` | `HOLD` | `KEEP` |
| `LONG` | `NEUTRAL` | `SELL` | `CLOSE` |
| `FLAT` | `NEUTRAL` | `HOLD` | `NONE` |
| `UNKNOWN` | `LONG` | `BUY` | `NONE` |
| `UNKNOWN` | `NEUTRAL` | `HOLD` | `NONE` |
| 任意 | `INDETERMINATE` | `AVOID` | `NONE` |

`BUY_TO_OPEN` 和 `SELL_TO_CLOSE` 仅作为从公共字段与精确持仓派生的
`position_effect_label`，不进入请求枚举或数据库第二套状态。`SHORT`、
`SELL + OPEN` 和任何 `SELL_TO_OPEN` 路径在 Schema、服务和数据库均拒绝：

- `BUY + OPEN` 只能来自精确看涨或看跌合约的 `FLAT + LONG`；
  `UNKNOWN + LONG` 只能是 `BUY + NONE`，不声称开仓；
- `SELL + CLOSE` 只有冻结持仓快照证明已有该 canonical 精确合约多头时才是
  `LONG + NEUTRAL`；
- `FLAT/UNKNOWN + NEUTRAL` 均为 `HOLD + NONE`，页面显示“观望”；
- `position_context=SHORT`、`normalized_direction=SHORT`、`SELL + OPEN` 或无有效
  `LONG` 精确持仓上下文的 `CLOSE` 一律归一为
  `INDETERMINATE + AVOID + NONE`，外部非法请求/持久化同时在 Schema、服务和数据库
  CHECK 三层拒绝；
- 如果看涨合约不适合买入，只能提示不参与或可研究其他有限风险合约，不能自动变成裸卖看涨。

`position_context=LONG/FLAT` 必须来自 cutoff 可见且未过期的
`CanonicalOptionPositionContext`，至少冻结 `position_context_snapshot_id`、
`owner_scope`、`user_id`、由二者规范生成的 `access_principal`、
`identity_level=CONTRACT`、`canonical_option_contract_id`、`identity_version`、
long/short quantity、`as_of_at/available_at/expires_at`、来源哈希和不可变
`content_hash`。snapshot 的 `owner_scope/user_id/access_principal` 必须与本次
task、run、prediction 逐字段完全一致。只有 snapshot 满足
`available_at <= cutoff_at` 且 `cutoff_at < expires_at`、精确 canonical ID/identity
version 与预测相等且
`long_quantity > 0 && short_quantity == 0` 才是 `LONG`；相同精确合约且两个 quantity
均为零才是 `FLAT`；`short_quantity > 0` 是不支持的 `SHORT`。无 snapshot、跨
owner/user/access principal、跨合约、identity version 不同、cutoff 后才可见或已过期
均规范为 `UNKNOWN`，不得产生 `SELL + CLOSE`，且跨用户引用不能泄露目标快照是否存在。

prediction 的 `position_context_snapshot_id` 必须以
`ON DELETE RESTRICT` 外键引用 `asset_position_context_snapshots.id`，并冻结同一
`content_hash` 进入 `decision_input_hash`。快照只追加不更新。期权 prediction 若
`position_context=LONG` 或 `trade_intent=CLOSE`，数据库行级 CHECK 要求非空 FK；
跨表约束 trigger 再校验 snapshot 的 CONTRACT 身份、LONG 数量、cutoff 有效区间及
owner/user/access principal 与 task/run/prediction 全相等；MySQL 使用即时 insert/update
trigger；SQLite 的等价实现只用于本地回归，不能用跨表
能力不足的普通 CHECK 代替。

模型处于 `SHADOW` 时，内部候选可以产生上述 `BUY/SELL`，普通用户
`published_decision` 只能返回 `INDETERMINATE + HOLD/AVOID + NONE`。

## 7. 必需数据

- 精确合约和标的主数据；
- 同步标的 bid/ask/last 和期权 bid/ask/trade；
- 同标的足够期权链和相邻到期；
- 利率曲线、分红或期货持有成本；
- 成交量、持仓量、深度、报价年龄；
- 行权、结算、调整、自动行权、停牌和到期规则；
- 估值模型、输入和数据时点。

预测使用三个独立、可重放的 `PredictionHead`：

| `head_code` | 标签 | `target_spec_version` 的目标定义 |
| --- | --- | --- |
| `option.underlying_direction` | `BULLISH/BEARISH/NEUTRAL` | 对期权身份冻结的精确 `underlying_instrument_id` 或 `underlying_contract_id`，按 `UnderlyingObservationSpec` 的来源、价格字段、公司行动/结算调整、入退时点计算收益；严格高于/低于版本化 neutral band 分别为 BULLISH/BEARISH，其余为 NEUTRAL。 |
| `option.iv_direction` | `VOL_UP/VOL_DOWN/NEUTRAL` | 对同一精确期权合约，在入退时点分别以有效 bid 和 ask、剩余期限及冻结模型输入通过版本化 solver 求 `iv_bid/iv_ask`；`exit_iv_bid - entry_iv_ask` 严格高于 band 为 VOL_UP，`entry_iv_bid - exit_iv_ask` 严格高于 band 为 VOL_DOWN，其余为 NEUTRAL。 |
| `option.exact_contract_net_profit` | `PROFIT/LOSS` | 同一精确合约以 entry ask 买入；期限前退出用 exit bid，到期则用交易所正式结算/行权价值；扣除佣金、交易费、滑点、资金、行权/结算和 target spec 声明的全部成本后，净利润严格大于零为 PROFIT，否则为 LOSS。 |

每个 head 均须冻结：

- 独立的 `target_spec_version`、`scoreability_rule_version`、HorizonSpec、标签边界/
  neutral band 版本和概率归一空间；
- `probability_model_version/probability_artifact_hash`；
- `calibration_version/calibration_artifact_hash/training_cutoff_at`；
- 同一 head、同一 target/scoreability cohort 的历史类别先验
  `baseline_code/baseline_version`，其 code/version 唯一解析不可变基线实现/制品；
- 公共层根据上述字段和 labels 计算的 `head_spec_hash`；
- `primary_for_promotion`，其中只有 `option.exact_contract_net_profit` 默认为 true。

`option.underlying_direction` 缺少规定入/退观测、标的停牌且无合法官方观测，或发生未被
冻结 adjustment spec 处理的公司行动时不可评分。`option.iv_direction` 任一时点缺
有效双边报价、期限 `<= 0`、bid/ask 任一 solver 不收敛，或合约先于目标期限到期时
不可评分；不得用 mid、ATM IV、曲面插值或其他执行价/到期替代。
`option.exact_contract_net_profit` 在入场窗口缺 ask 或非到期退出缺 bid 时不可评分；
到期时正式结算/行权价值优先于 bid，若结算规则、deliverable 或全部成本不完整则不可
评分。

三个 head 的 `head_spec_hash` 进入 `decision_input_hash`、结果与各自评分 cohort。
任一概率、结果或 cohort 混入不同 `head_spec_hash` 必须整批拒绝，不做隐式迁移。
三组概率各自归一，Brier/Brier Skill 仅在同 head、同 spec、同 `SCORED` 样本上与对应
baseline 比较；概率模型和校准器只使用 `training_cutoff_at` 以前的样本。

结果使用 `option.underlying_direction`、`option.iv_direction`、
`option.exact_contract_net_profit` 和 `option.close_avoided_loss` 四个
`outcome_kind`。
`OutcomeStatus` 统一为 `PENDING/PARTIAL/SCORED/UNSCORABLE`；到期完成评分使用
`OutcomeStatus.SCORED + MaturityReason.EXPIRY`。

## 8. 研报要求

1. 精确合约身份和标的；
2. 标的、波动、合约价值和持仓动作；
3. 条款、行权和结算；
4. 标的行情和催化剂；
5. 期权链流动性；
6. IV 期限、微笑/偏度和曲面质量；
7. 理论价、市场价和模型误差；
8. Greeks 风险；
9. 到期盈亏、盈亏平衡、最大损失和压力；
10. 策略适用性与有限风险替代；
11. 到期、行权、指派、流动性和保证金风险；
12. 历史预测和三个 head 的独立准确率及四类经济结果；
13. 来源、估值时点、模型和策略版本。

## 9. 非功能与合规

- 数值求解结果在支持区间内与 QuantLib/py_vollib 黄金用例交叉验证；
- IV 不收敛必须为 `null + reason`；
- Greeks、曲面和理论价带模型和输入版本；
- 期权链和标的的时间偏差有产品级上限；
- 服务端强制裸卖保护，前端隐藏不能替代；
- 正式公众建议前完成投资咨询、适当性、风险披露和数据许可审查。

## 10. 每日影子运行和晋级作用域

- v1 schedule 只允许 `identity_level=CONTRACT` 的明确
  `canonical_option_contract_id + identity_version`，运行时不接受裸标的、链查询或
  selector；
- DTE/delta/行权价/流动性等选约规则只能在配置阶段对冻结链解析，经审批后产出不可变
  manifest，并展开为每个精确合约一条 schedule；manifest 保存 rule version/hash、
  resolution cutoff、候选及排序证据和批准人，但运行时不得再次选约；
- 到期或不再合格的 schedule 必须停用；替代合约需重新解析、审批并创建新的精确
  CONTRACT schedule，禁止自动滚动；
- 交易所日盘收盘并取得完整链后触发，cutoff 按交易所和产品配置；
- 调度使用 `schedule_id + schedule_version + scheduled_fire_at + cutoff_at +
  cutoff_policy_version + policy_version` 生成 `run_key`，以租约锁去重并冻结完整
  schedule 配置；补跑固定原 cutoff、具体 canonical 合约、identity version、
  schedule 配置、链/标的/持仓快照和全部 head spec，禁止重跑 selector；
- `decision_input_hash` 包含精确合约、exact canonical position context、
  `position_context_snapshot_id/content_hash/access_principal`、
  链/标的快照、三个 head 的 `target_spec_version/scoreability_rule_version` 及各自
  target spec 内的 neutral band、
  probability/calibration artifact、`training_cutoff_at`、
  `baseline_code/baseline_version/head_spec_hash`、曲面、成本和策略版本；
- `promotion_scope_key` 至少包含标的类型、call/put、期限、DTE/delta/IV/
  流动性范围和主预测 head；
- `POOLED` scope 执行单一标的不超过 40%；`INSTRUMENT_SPECIFIC` 模型则覆盖多个到期、
  行权价和市场状态，并使用专属最小样本门槛。

## 11. 完成条件

- OPT-FR-001 至 013 全部通过；
- 欧式 call、欧式 put、美式合约和链不完整各有测试；
- ask 入场/bid 退出、到期结算和无退出报价完整验证；
- 三个 head 的全部黄金标签、solver/期限/缺失分支及 mixed-spec 拒绝完整验证；
- 动作白名单、exact canonical position context、三层拒绝和配置期 CONTRACT schedule
  展开/补跑冻结完整验证；
- 无 snapshot、跨用户/owner、跨合约、cutoff 后可见和过期快照均降为 UNKNOWN 且不能
  CLOSE，并有不可变 FK/hash 和数据库约束验收；
- 默认只在影子模式。
