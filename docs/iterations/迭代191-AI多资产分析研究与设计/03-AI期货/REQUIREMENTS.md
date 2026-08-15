# 191C AI 期货需求文档

## 1. 业务目标

用户输入一个期货品种、具体合约或连续研究序列后，系统确认可交易合约、到期和下一有效交易时段，结合真实合约趋势、期限结构、基差、流动性和品种专属基本面，给出做多、做空或中性观点及买入、卖出、持有/观望建议，生成研报并按真实合约验证。

## 2. 核心约束

- 连续合约只能用于研究特征，不能用于建议价格、执行预览或结果评分；
- 同一品种不同月份是不同资产，合约属性不得靠代码字符串猜测；
- 19:10 后的下一时段可能是当晚夜盘，不统一等同次日开盘；
- 保证金收益与名义收益分别展示，不能用杠杆放大“预测质量”；
- 本迭代不执行开仓、换月、交割或保证金操作。

## 3. v1 范围

- 境内股指期货和有合法双边行情、合约主数据的高流动性商品期货；
- 商品、股指、国债和外汇期货分别路由；
- 国债期货必须具备可交割券、转换因子、CTD 和隐含回购逻辑才可晋级；
- 无合约日历、无历史双边报价或临近个人不可持有交割窗口的合约只做研究；
- 境外期货在取得交易所数据许可和合约日历后按插件能力开放。

## 4. 身份模型

```text
instrument_id
exchange
exchange_contract_id
product_code
contract_month
currency
quote_unit
contract_multiplier
tick_size
listing_at
last_trade_at
first_notice_at
delivery_start_at
delivery_end_at
settlement_type
delivery_type
price_limit_rule
exchange_margin_rule
trading_calendar_id
night_session_rule
source_version
```

公共身份分别使用 `identity_level=PRODUCT/CONTRACT/SERIES` 表示
期货产品、期货合约和连续研究序列。只有
`CONTRACT` 可以成为公开建议和合同级结果的研究对象；连续序列每个时点必须能还原真实合约、
输入快照和映射规则。

## 5. 功能需求

| 编号 | 需求 |
| --- | --- |
| FUT-FR-001 | 搜索品种、具体合约或连续序列并展示候选、月份、到期和交易时段。 |
| FUT-FR-002 | 维护版本化合约主数据、交易日历、夜盘、交割、保证金和涨跌停规则。 |
| FUT-FR-003 | 按分析 cutoff 保存连续序列到真实合约的 point-in-time 映射，以及当时可见的完整复权链、vintage、来源哈希和换月规则；未来换月不得改变历史特征或哈希。 |
| FUT-FR-004 | 计算真实合约趋势、波动、成交持仓、流动性和压力指标。 |
| FUT-FR-005 | 计算期限结构、曲线斜率/曲率、基差、carry 和流动性迁移。 |
| FUT-FR-006 | 按商品、股指、国债、外汇期货路由专属基本面。 |
| FUT-FR-007 | 用合约级日历计算下一可交易时段和建议有效期。 |
| FUT-FR-008 | 输出 `LONG/SHORT/NEUTRAL`、买入/卖出/持有、持仓动作矩阵、期限和风险。 |
| FUT-FR-009 | 生成十三个规定章节的研报和专属图表。 |
| FUT-FR-010 | 保存真实合约预测、完整决策输入哈希、映射、成本、保证金，以及 PredictionHead 的 target/scoreability、概率模型/校准制品、训练 cutoff、基线和 `head_spec_hash` 等精确公共字段。 |
| FUT-FR-011 | 同时提供合同级和明确展期规则下的 roll-aware 结果。 |
| FUT-FR-012 | 临近交割、单边涨跌停、无双边报价或规则未知时否决可行动建议。 |
| FUT-FR-013 | 对配置的影子资产清单按品种会话每日运行，支持锁、幂等、补跑和失败审计。 |

## 6. 建议语义

权威动作只使用公共字段：
`normalized_direction`、`position_context`、`trade_intent` 和 `recommendation`。
期货的 `normalized_direction` 为 `LONG/SHORT/NEUTRAL/INDETERMINATE`：

| `position_context` | `normalized_direction` | `recommendation` | `trade_intent` |
| --- | --- | --- | --- |
| `FLAT` | `LONG` | `BUY` | `OPEN` |
| `FLAT` | `SHORT` | `SELL` | 产品批准开空研究时为 `OPEN`，否则 `NONE` |
| `LONG` | `SHORT` | `SELL` | `CLOSE` |
| `SHORT` | `LONG` | `BUY` | `CLOSE` |
| `LONG` | `LONG` | `HOLD` | `KEEP` |
| `SHORT` | `SHORT` | `HOLD` | `KEEP` |
| `LONG/SHORT` | `NEUTRAL` | `HOLD` | `KEEP` |
| `UNKNOWN` | `LONG/SHORT` | `BUY/SELL` | `NONE` |
| 任意 | `INDETERMINATE` 或质量拒绝 | `AVOID` | `NONE` |

`OPEN_LONG`、`CLOSE_LONG`、`CLOSE_SHORT` 和 `MAINTAIN_LONG` 等文字只能由上述字段
派生用于展示，不得保存为第二套动作状态。页面必须同时显示观点和持仓动作矩阵；
未提供持仓时不能声称已生成账户操作，且所有研究动作保持 `execution_disabled=true`。
`short_open_research_allowed` 由服务端产品/地区 capability 决定并版本化；
未批准时空仓 SHORT 只显示看空研究观点，不形成开仓意图。

模型处于 `SHADOW` 时，内部 `candidate_decision` 可以产生 `LONG/SHORT` 和
`BUY/SELL`；普通用户 API、页面和导出只返回 `published_decision` 的
`INDETERMINATE + HOLD/AVOID + NONE`。两层决定不得混用。

## 7. 数据要求

- 合约主数据、交易/夜盘/节假日日历、最后交易/通知/交割日；
- 原始真实合约 bid/ask/trade/settlement、成交量、持仓量和深度；
- 至少近月、次近月和可用远月的期限结构；
- 现货基准、单位、品质、地点、税费和基差可比说明；
- 保证金、涨跌停和持仓/交割限制；
- 商品库存/仓单/产销/季节，股指现货/利率/分红，国债期货 CTD/DV01，外汇期货利差/远期；
- COT/会员排名的统计日和实际发布时间。

主预测必须包含一个可独立重放的 `PredictionHead`：

- `head_code=futures.contract_pnl`，标签全集固定为互斥完备的
  `LONG/SHORT/NEUTRAL`；
- `target_spec_version` 冻结精确 `CONTRACT`、`HorizonSpec`、入退场窗口、
  报价边、成本模型和版本化 `neutral_band`。多头使用入场 ask、退出 bid；
  空头使用入场 bid、退出 ask，二者均扣除佣金、交易费、滑点和
  `cost_snapshot` 声明的其他全部成本；
- 若多头净收益严格高于 neutral band，标签为 `LONG`；否则若空头净收益严格高于
  neutral band，标签为 `SHORT`；其余为 `NEUTRAL`。band 的值、单位、比较符和
  `neutral_band_version` 是 target spec 的组成部分；v1 单位固定为
  `NOTIONAL_RETURN`，历史预测不得读取当前配置；
- `HorizonSpec.unit=TRADING_SESSION` 时，一个 session 是交易所日历中的一个
  `session_id`（夜盘和日盘分别计数），在第 N 个合格 session 的冻结退出窗口成熟；
  `TRADING_DAY` 按交易所 `trading_day` 标签去重计数，同一 trading day 下的夜盘和
  日盘只计一天，并在第 N 个交易日的冻结退出窗口成熟。两者不得互换或用自然日替代；
- `scoreability_rule_version` 冻结缺失双边报价、单边涨跌停、停牌、到期和最后交易日
  的处理。入场或规定退出/到期窗口没有可执行报价时为 `UNSCORABLE`；期限跨过
  `last_trade_at` 时按 target spec 的到期前退出规则在最后合格窗口评分并记录
  `MaturityReason.EXPIRY`，该窗口仍无报价则为 `UNSCORABLE`，不得换成连续价或下月合约；
- 概率模型、校准器和同目标朴素基线分别冻结公共字段
  `probability_model_version/probability_artifact_hash`、
  `calibration_version/calibration_artifact_hash`、
  `training_cutoff_at` 和 `baseline_code/baseline_version`。基线 code/version
  唯一解析其不可变实现和制品，且只使用同一 cohort、同一标签规则的历史类别先验，
  不能跨 target 或 scoreability spec 借样本；
- 系统按公共规则对 `target_spec_version`、`scoreability_rule_version`、labels、
  模型/校准制品、训练 cutoff 和基线字段计算 `head_spec_hash`；该哈希进入
  `decision_input_hash`、结果和评分 cohort。同一 cohort、概率向量或结果批次混入
  不同 `head_spec_hash` 时整批拒绝，不做隐式转换；
- T2 的 Brier/Brier Skill 只使用注册表声明的主 head 及同 spec 基线，不把展期或
  平仓规避结果混入概率分母。

后续结果按 `outcome_kind` 分开保存：

- `futures.contract_pnl`：实际合约方向净 P&L；
- `futures.close_avoided_loss`：平掉已有多头或空头后规避的损失；
- `futures.roll_aware_pnl`：明确版本化换月策略的两笔或多笔真实交易。

每条结果均需记录入场、退出/到期时点、报价口径、币种、成本口径、状态和成熟原因。
`OutcomeStatus` 只允许 `PENDING/PARTIAL/SCORED/UNSCORABLE`；正常期限完成、到期和换月分别使用
`MaturityReason.HORIZON_REACHED`、`MaturityReason.EXPIRY` 和
`MaturityReason.ROLL`，不得把成熟原因扩展成新的结果状态。

## 8. 研报要求

1. 观点、动作、置信度和资格；
2. 真实合约、连续序列、映射和换月；
3. 趋势、波动、成交和持仓；
4. 期限结构、基差和 carry；
5. 现货、库存、仓单、供需和季节；
6. 会员持仓/COT 及局限；
7. 品种专属基本面；
8. 保证金、涨跌停、杠杆和压力情景；
9. 到期、交割、换月和流动性；
10. 催化剂和新闻证据；
11. 结论和持仓条件动作矩阵；
12. 历史预测、样本和成本后表现；
13. 数据、时点、策略和模型版本。

## 9. 非功能与合规

- 价格、乘数和 P&L 使用 `Decimal`；
- 合约日历由交易所规则驱动，不用普通工作日；
- 任何连续合约映射和复权均可按 cutoff 重放；每次预测冻结当时可见的有序
  `normalization_chain`、`chain_vintage_at`、映射/行情来源哈希及链哈希，
  `available_at > cutoff_at` 的换月或修订不可见；
- 连续特征哈希必须包含 cutoff、真实映射合约、normalization chain hash、来源快照
  hash 和 feature version；未来持仓量、换月或新 vintage 只能产生新快照，不能改写
  相同 cutoff 的历史 feature value/hash；
- 交易所、CTP/期货公司和商业数据在生产前完成授权；
- 报告以概率和情景表达，不作确定性判断；
- 投资咨询、适当性、交割资格、持仓限额和真实执行另行审批。

## 10. 每日影子运行和晋级作用域

- 审批静态清单只在配置阶段展开为单合约 schedule，运行时不扫描全部市场；
- 中国期货默认在北京时间 19:10 形成日盘后快照，并根据品种日历决定下一夜盘或日盘；
- `run_key` 由 `schedule_id + schedule_version + scheduled_fire_at + cutoff_at +
  cutoff_policy_version + policy_version` 生成，单次运行使用租约锁并冻结 schedule
  配置；
- 重复触发读取相同冻结快照、normalization chain vintage 和 head spec，并命中相同
  `decision_input_hash`；失败可按原 cutoff 补跑，补跑不得读取后来换月、修订或制品；
- `promotion_scope_key` 至少包含期货类别、研究品种池、期限和主预测 head；
  策略、模型和校准版本由注册表唯一键的独立列冻结；
- `POOLED` scope 的任一品种成熟样本占比不得超过 40%；若未来采用
  `INSTRUMENT_SPECIFIC` 模型，
  则豁免该比例，但需覆盖至少三个合约月份和三个市场状态，并满足单品种专属最小样本门槛。

## 11. 完成条件

- FUT-FR-001 至 013 全部验收；
- 至少一个股指和一个有夜盘商品合约完整走通；
- 连续/真实合约、夜盘/日盘、到期/换月场景均有固定测试；
- LONG、SHORT、NEUTRAL 黄金标签和 missing/limit/expiry、mixed-spec 拒绝均有固定夹具；
- 技术验收后保持影子模式。
