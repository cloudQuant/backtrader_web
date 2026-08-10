# 191F AI 数字货币需求文档

## 1. 业务目标

在法律允许的地区和隔离研究环境中，用户输入一个数字资产或具体市场产品后，系统明确代币、网络、合约地址、交易场所、报价币和现货/永续/交割类型，结合跨场所市场、衍生品、链上、tokenomics、安全和监管风险，生成研究观点、研报和可验证历史记录。

## 2. 实施前置 Gate

[中国人民银行等部门 2021 年通知](https://m.safe.gov.cn/safe/2021/0924/19911.html)对虚拟货币兑换、定价、信息中介、衍生品和境外平台向境内居民提供服务设定了严格禁止性边界。因此：

- 中国大陆租户普通用户响应固定为
  `market_view=INDETERMINATE`、`normalized_direction=INDETERMINATE`、
  `recommendation=AVOID`、`trade_intent=NONE`、
  `actionability=REGION_RESTRICTED`，并关闭平台开户、交易所链接、API key、
  托管和订单功能；
- 仅允许隔离的内部研究、风险教育或合规审查模式；
- 面向公众上线方向建议前必须取得针对运营主体、地区和产品的书面法律意见；
- 技术实现完成不能替代该 Gate，也不能自动开启功能。

## 3. 核心原则

- `BTC`、`ETH` 或 ticker 不是足够身份；同名 token 用网络和合约地址区分；
- 同一资产的 USD/USDT、不同交易所、现货、线性/反向永续和交割合约均是不同产品；
- mark/index 用于风险和结算，不冒充可成交 bid/ask；
- 稳定币是独立风险资产，不固定按 1 USD；
- 24×7 日线使用 UTC 切日；在北京时间 19:10 运行只能称快照；
- 链上指标不支持时显示缺失，不能补 0；
- v1 不推荐杠杆、不接私有 API、不执行交易。

## 4. 身份

资产身份：

```text
identity_level = ASSET
caip_asset_id
chain_id
contract_address_or_native_asset
symbol
decimals
issuer_or_protocol
token_standard
```

产品身份：

```text
identity_level = PRODUCT | CONTRACT
venue
market_type = SPOT | PERPETUAL | DELIVERY_FUTURE
base_asset_id
quote_asset_id
settlement_asset_id
expiry
linear_or_inverse
contract_multiplier
margin_mode
trading_status
```

输入裸 `BTC` 时返回资产级综合研究，不静默选择交易所或永续；只有确认 venue/product 后才进入产品级可成交评分。[CAIP 标准](https://github.com/ChainAgnostic/CAIPs)作为链和资产标识候选。
现货和永续属于 `PRODUCT`，有到期日的交割合约属于 `CONTRACT`；产品/合约身份必须包含场所、报价/结算资产和适用规则。`ASSET` 可不含场所和报价币，但不得产生产品级可执行评分。

衍生品不读取账户或实际仓位。清算分析只能使用服务端版本化的
`STANDARDIZED_RESEARCH` 风险情景，冻结 `scenario_version/side/contract_quantity/
notional/leverage/margin_mode/collateral_asset/collateral_amount/initial_margin_rate/
maintenance_margin_rate/risk_tier/liquidation_formula_version/mark_source/
mark_path_rule_version`。页面必须标为标准化压力情景，不得称为用户实际清算价或杠杆建议。

## 5. 功能需求

| 编号 | 需求 |
| --- | --- |
| CRYPTO-FR-001 | 解析链、合约地址、资产、场所、报价币、现货/永续/交割和结算。 |
| CRYPTO-FR-002 | 支持资产级综合研究与场所产品级研究，严格区分可执行性。 |
| CRYPTO-FR-003 | 收集场所 bid/ask/trade/OHLCV/order book、状态和跨场所参考价格。 |
| CRYPTO-FR-004 | 分析现货趋势、波动、spread、深度、市场集中和稳定币换算风险。 |
| CRYPTO-FR-005 | 永续/期货分析 index、mark、funding、basis、OI、期限和版本化标准清算压力情景。 |
| CRYPTO-FR-006 | 对支持资产分析链上活动、费用、流量、供给、持币和验证者/质押。 |
| CRYPTO-FR-007 | 分析 tokenomics、解锁、排放、协议收入、治理、升级和集中度。 |
| CRYPTO-FR-008 | 分析攻击、fork、bridge/oracle、交易所、监管和生态事件。 |
| CRYPTO-FR-009 | 按现货/衍生品只使用公共 `normalized_direction/position_context/trade_intent/recommendation` 枚举输出建议。 |
| CRYPTO-FR-010 | 生成十二个规定章节的研报。 |
| CRYPTO-FR-011 | 保存预测，并按 24h/7d/30d 为现货和衍生品生成多个含费用、滑点、funding 和风险路径的 `outcome_kind`。 |
| CRYPTO-FR-012 | 服务端强制地区、深度、脱锚、停牌、身份和许可门控，并按公共安全发布合同返回。 |
| CRYPTO-FR-013 | 分离内部候选决定和普通用户发布决定；`SHADOW` 期间不得向普通用户暴露候选方向、概率或预期收益。 |
| CRYPTO-FR-014 | 每个 UTC 自然日运行可补跑且幂等的 00:00 cutoff 影子批次，并按精确 `promotion_scope_key` 管理晋级。 |

## 6. 建议和发布语义

### 6.1 公共枚举

本插件不得定义资产私有动作值：

| 字段 | 允许值 | 数字货币语义 |
| --- | --- | --- |
| `normalized_direction` | `LONG/SHORT/NEUTRAL/INDETERMINATE` | `LONG/SHORT` 为产品方向，`NEUTRAL` 为无方向，`INDETERMINATE` 为不得发布方向。 |
| `position_context` | `FLAT/LONG/SHORT/UNKNOWN` | 用户声明的现货或具体衍生品持仓。 |
| `trade_intent` | `OPEN/ADD/REDUCE/CLOSE/KEEP/NONE` | 只解释研究建议，不执行动作。 |
| `recommendation` | `BUY/SELL/HOLD/AVOID` | `SELL` 不自动等于裸空，`AVOID` 为风险、数据、许可或地区否决。 |

`market_view=NEUTRAL` 映射 `normalized_direction=NEUTRAL`；
`market_view=INDETERMINATE` 映射 `normalized_direction=INDETERMINATE`。

### 6.2 现货

- `position_context=FLAT + normalized_direction=LONG` 在能力允许时映射
  `BUY + OPEN`；
- `position_context=LONG + normalized_direction=SHORT` 映射
  `SELL + CLOSE/REDUCE`，不暗示裸空；
- 同向持仓默认 `HOLD + KEEP`；`position_context=UNKNOWN` 时
  `trade_intent=NONE`；
- 现货 `position_context=FLAT + normalized_direction=SHORT` 不得映射开空，
  `trade_intent=NONE`；
- 场所、网络、身份、深度、稳定币、安全或合规否决时为 `AVOID + NONE`。

### 6.3 永续/交割合约

- 衍生品 `normalized_direction=LONG/SHORT/NEUTRAL` 与现货信号分开；
- 空仓 `SHORT` 只有 `short_open_research_allowed=true` 时映射
  `SELL + OPEN`，否则 `trade_intent=NONE`；中国大陆固定不允许；
- v1 不连接账户或执行动作；funding、保证金和清算风险只基于冻结的
  `STANDARDIZED_RESEARCH` 情景，不能冒充用户实际仓位；
- 现货 SELL 与永续 SHORT 不得合并统计。

### 6.4 候选、SHADOW 和地区发布

1. 只有批准的隔离评估环境可以写完整 `candidate_decision_json`，且其所有动作仍使用公共枚举；
2. `SHADOW/SUSPENDED/未登记` 或精确 `promotion_scope_key` 未晋级时，普通用户
   `published_decision_json` 固定为 `market_view=INDETERMINATE`、
   `normalized_direction=INDETERMINATE`、`trade_intent=NONE`、
   `actionability=RESEARCH_ONLY`，质量允许时 `recommendation=HOLD`，否则
   `AVOID`，并包含 `COMMON.MODEL_NOT_PROMOTED`；
3. 只有 `PROMOTED` 且地区、产品、数据和风险门控均通过，才可发布候选方向；
4. 中国大陆或其他受限地区始终固定为
   `market_view=INDETERMINATE`、`normalized_direction=INDETERMINATE`、
   `recommendation=AVOID`、`trade_intent=NONE`、
   `actionability=REGION_RESTRICTED`、
   `confidence/expected_return=null`、`primary_head_code=null`、
   `prediction_heads=[]`、
   `execution_disabled=true`，并包含 `CRYPTO.REGION_RESTRICTED`。该分支优先于
   `PROMOTED`。

## 7. 数据要求

- 无歧义资产/链/合约地址及 venue product；
- venue bid/ask、trades、OHLCV、order book、状态和维护窗口；
- 多场所参考价格和报价币法币换算；
- 永续/期货 index、mark、funding、OI、到期和结算规则；
- 市值、流通/最大供给、解锁、排放和 tokenomics；
- 支持资产的链上、协议、安全和治理事件；
- 来源、时间、条款版本、原始哈希和许可。

`reason_codes` 只使用公共 `ReasonCode` 注册表中的大写资产命名空间稳定码。v1
至少登记：`CRYPTO.INSTRUMENT_AMBIGUOUS`、`CRYPTO.PRODUCT_UNSUPPORTED`、
`CRYPTO.QUOTE_UNAVAILABLE`、`COMMON.DATA_STALE`、
`CRYPTO.QUOTE_INCONSISTENT`、`CRYPTO.BAR_INCOMPLETE`、
`CRYPTO.DEPTH_INSUFFICIENT`、`CRYPTO.STABLECOIN_DEPEG`、
`CRYPTO.VENUE_UNAVAILABLE`、`CRYPTO.FUNDING_UNAVAILABLE`、
`CRYPTO.ONCHAIN_UNSUPPORTED`、`CRYPTO.CHAIN_UNFINALIZED`、
`COMMON.MODEL_NOT_PROMOTED`、`CRYPTO.REGION_RESTRICTED`、
`COMMON.SOURCE_LICENSE_BLOCKED`、`CRYPTO.RISK_NOT_MEASURABLE` 和
`CRYPTO.LIQUIDATION_SCENARIO_INCOMPLETE`。API 传输层
错误码与 `ReasonCode` 分开，禁止自由文本原因码。

## 8. 研报要求

1. 资产、链、合约地址、场所和产品；
2. 方向、建议、期限、置信度和持仓；
3. 跨场所价格、趋势和流动性；
4. 波动、深度和微观结构；
5. funding、basis、OI、清算和期权状态；
6. 链上活动、供给和持币结构；
7. tokenomics、收入、治理、升级和解锁；
8. 新闻、监管、攻击和生态事件；
9. 托管、场所、稳定币、oracle、bridge 和合约风险；
10. 情景、催化剂、失效和风险预算；
11. 数据质量、来源、cutoff 和资产解析；
12. 历史信号、分产品/期限质量和样本。

## 9. 非功能和安全

- 日线 UTC 00:00 切分，批次不早于 00:10 UTC；其他时点只用已完成 bar；
- 保存维护、链暂停、重组、区块高度和 `finalized_at`；
- 公开数据适配器不接受私钥或有交易权限的 API key；
- 交易所、聚合器、链上商和指标算法版本进入来源注册表；
- 代码许可不等于行情再分发许可；
- 中国大陆能力由服务端拒绝，不能靠隐藏前端控制。

### 9.1 每日影子调度和幂等

- 版本化审批产品清单只在配置阶段展开为“一产品、一期限、一 schedule”，运行时
  不发现交易所新品或扫描市场；
- 每个 UTC 自然日以 00:00:00 为 `analysis_cutoff_at`，00:10 运行版本化
  schedule；北京时间 19:10 快照不进入该日 schedule cohort；
- `run_key=SHA-256(schedule_id|schedule_version|scheduled_fire_at|cutoff|
  cutoff_policy_version|policy_version)` 全局唯一，运行冻结完整 schedule 配置；
- 初次失败在 00:25、01:10 重试，03:00 对账；进程重启在下一 cutoff 前对同一
  `run_key` catch-up，维护中的产品只失败该 schedule；
- 所有重试冻结原 cutoff，只读取 `available_at <= analysis_cutoff_at`，不得用后来
  出现的价格、链上 finality、funding 或事件改写候选决定；
- `decision_input_hash/prediction_key` 唯一冲突返回已有不可变预测；任一冻结产品、
  快照、capability 或版本变化形成新预测；最终失败记录尝试次数、阶段和原因码。

### 9.2 多 head 结果

产品级候选决定恰有一个主 `PredictionHead`：现货使用
`crypto.spot_pnl`，永续/交割使用 `crypto.derivative_pnl`，标签均为
`LONG/SHORT/NEUTRAL`；head 冻结 target/scoreability 版本、P&L/成本/no-trade
band、概率模型与 artifact、校准 artifact/training cutoff、基线版本和
`head_spec_hash`。
资产级无 venue/product 的研究没有可评分 head，主 head 为 `null`。

现货预测至少生成 `crypto.spot_pnl`、`crypto.benchmark_excess` 和
`crypto.risk_path`；永续/交割预测至少生成 `crypto.derivative_pnl`、
`crypto.liquidation_risk` 和 `crypto.risk_path`。各 head 独立使用公共
`OutcomeStatus=PENDING|PARTIAL|SCORED|UNSCORABLE`，到期原因单列
`MaturityReason`：

`crypto.liquidation_risk` 仅评价预测时冻结的标准化情景：按真实 mark 路径和当时
场所公式判断 `SURVIVED/LIQUIDATED`，触发时以情景抵押品损失计入，不声称用户发生清算。
风险情景及规则快照哈希进入 `normalized_asset_request_options`、
`asset_risk_scenario_snapshot_hash` 和 `decision_input_hash`；缺风险 tier、维持保证金、
公式或 mark 路径时为 `UNSCORABLE + CRYPTO.LIQUIDATION_SCENARIO_INCOMPLETE`，
不得用默认杠杆补齐。

- 正常 24h/7d/30d 为 `MaturityReason.HORIZON_REACHED`；
- 交割合约提前终止为 `MaturityReason.EXPIRY`；
- 预测快照已明确允许的滚动为 `MaturityReason.ROLL`；
- 场所永久下架为 `MaturityReason.DELISTING`。

不得使用 `MATURED` 状态。只有 `OutcomeStatus.SCORED` 进入对应 head 的指标分母；
等待允许延迟到达的数据为 `PARTIAL`，超过最终化 SLA 后缺可执行价格、funding 或
风险路径为 `UNSCORABLE`，并保存 `CRYPTO.*` `ReasonCode`。

### 9.3 晋级作用域和样本

`promotion_scope_key` 是规范化公共 `PromotionScope` 的 SHA-256，scope 至少固定
资产、venue/product/quote 样本池、`signal_head` 和期限；head spec、
target/scoreability/baseline、风险情景、策略、模型、artifact 与校准版本由注册表
唯一键/证据的独立列固定：

- `INSTRUMENT_SPECIFIC`：单一 `canonical_id` 至少 200 条成熟行动信号；
- `POOLED`：仅同 venue/product family、现货或同类衍生品、报价/结算约定、成本和策略合同
  可合并；至少 5 个产品、每个至少 20 条、总计至少 200 条，任一产品不超过 40%；
- spot/perpetual/delivery、linear/inverse、法币/稳定币报价不得跨池；
- 聚合、每个充分样本产品和最差风险切片均须通过；一个 key 的晋级不得传播到另一
  venue、产品、期限或版本；
- 每个 scope 还必须完成连续 90 个 UTC 自然日的前瞻影子运行。

## 10. 完成条件

- CRYPTO-FR-001 至 014 全部技术验收；
- 同 ticker 跨链、现货/永续、线性/反向、资金费、稳定币脱锚和场所异常均有测试；
- 全球方向模型保持影子且普通用户只看安全发布结果；中国大陆 Gate 未获书面批准时
  固定 `actionability=REGION_RESTRICTED`、`recommendation=AVOID`、
  `normalized_direction=INDETERMINATE`、`trade_intent=NONE`。
