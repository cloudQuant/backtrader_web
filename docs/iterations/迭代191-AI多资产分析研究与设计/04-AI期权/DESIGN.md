# 191D AI 期权设计文档

## 1. 组件

```text
OptionIdentityResolver
  -> OptionChainCollector
  -> SynchronizedUnderlyingCollector
  -> OptionPricingRouter
  -> OptionSurfaceAnalyzer
  -> OptionQualityGate
  -> OptionDecisionPolicy
  -> NakedShortGuard
  -> OptionReportBuilder
  -> OptionOutcomeEvaluator
```

现有 `app/services/options_chain.py` 可作为数据入口适配，但新的快照必须增加规范身份、同步时点、来源、链覆盖和质量。
公共身份固定为 `identity_level=CONTRACT`；裸标的输入只属于解析/筛选请求，
不能成为期权建议的预测身份。

## 2. 模型路由

| 合约 | 模型 |
| --- | --- |
| 欧式期货期权 | Black-76 |
| 欧式现货/指数期权 | BSM 或基于远期的适当模型 |
| 美式期权 | 二叉树或有限差分 |

模型输入包含估值时间、标的/远期、行权价、期限、利率、分红/持有成本、波动率、行权和结算。模型选择由合约元数据决定，不能按市场名称猜测。

[QuantLib](https://github.com/QuantLib/QuantLib)提供欧式/美式数值引擎；[py_vollib](https://github.com/vollib/py_vollib)可作为欧式价格、IV 和 Greeks 的 MIT 许可交叉验证。二者都不能替代市场数据质量。

## 3. 链和曲面

清洗顺序：

1. 价格理论上下界；
2. `bid <= ask` 且目标动作一侧可成交；
3. 报价年龄和标的同步；
4. 零 bid、过宽价差和深度不足；
5. put-call parity 容差；
6. 同到期执行价单调性、凸性；
7. 跨到期总方差日历套利；
8. 清洗后的覆盖和支持区间。

v1 使用分到期稳健插值，只在有效行权价范围内展示微笑；不为视觉完整而外推缺失曲面。曲面至少需两个有效到期，每个到期的有效 OTM 点数达到产品注册配置。

## 4. 特征

- 标的趋势、事件、实现波动和未来情景；
- ATM IV、IV-实现波动差、期限结构；
- 25-delta risk reversal、butterfly、put/call skew；
- 理论价与可成交 ask/bid 的 edge；
- Delta/Gamma/Theta/Vega/Rho；
- 到期盈亏平衡、最大损失、情景 P&L；
- spread/mid、spread/tick、深度、成交量、持仓量和报价年龄。

```text
long_contract_edge =
  conservative_fair_value
  - executable_ask
  - fees
  - slippage
```

理论价不直接作为入场价格。

## 5. 质量门控

### 5.1 `REJECTED`

- 标的、C/P、行权价、到期、行权或结算未知；
- 已到期/停止交易；
- 标的与期权不是同步有效快照；
- crossed/过期报价或目标一侧不可成交；
- DTE 低于产品安全阈值且未启用专属短期限模型；
- IV 不收敛；
- `SELL` 会形成未批准裸空；
- 多腿任一腿缺有效报价；
- `position_context=SHORT`、`normalized_direction=SHORT`、`SELL + OPEN`、无同一
  canonical 合约 LONG 上下文的 CLOSE，或不在 v1 动作白名单中的任意元组；
- 持仓上下文快照缺失、cutoff 后才可见、已过期，或其 owner/user/access principal、
  CONTRACT canonical ID、identity version 与 task/run/prediction 不一致；
- prediction、结果批次或晋级 cohort 混入不同 `head_spec_hash`。

### 5.2 `DEGRADED`

- 单个合约有效但链不足，无法分析 skew/curve；
- 只有结算价，无双边报价；
- 利率、分红或持有成本过期；
- 清洗后曲面覆盖不足；
- 流动性低或价差超过产品门槛。

降级的发布决定只能输出 `INDETERMINATE + HOLD/AVOID + NONE`，不得用理论价
生成可行动 BUY。内部候选仍可用于受限影子评价。

## 6. 决策

决策不是简单把四个分数相加：

1. 判断标的和波动场景；
2. 检查该精确合约是否提供有限风险且有正可执行 edge；
3. 评估 Theta、Gamma、Vega、流动性和到期压力；
4. 质量和裸卖保护覆盖动作；
5. 根据持仓返回公共
   `normalized_direction/recommendation/trade_intent`，再派生只读的
   `BUY_TO_OPEN/SELL_TO_CLOSE` 标签。

决策前先把 cutoff 可见的精确持仓快照规范化为唯一动作上下文。v1 只允许以下完整元组：

```text
(FLAT,    LONG,          BUY,   OPEN)
(LONG,    LONG,          HOLD,  KEEP)
(LONG,    NEUTRAL,       SELL,  CLOSE)
(FLAT,    NEUTRAL,       HOLD,  NONE)
(UNKNOWN, LONG,          BUY,   NONE)
(UNKNOWN, NEUTRAL,       HOLD,  NONE)
(*,       INDETERMINATE, AVOID, NONE)
```

这里顺序固定为
`(position_context, normalized_direction, recommendation, trade_intent)`。
`SHORT` position context、`normalized_direction=SHORT`、`SELL + OPEN`、无有效
LONG context 的 CLOSE 和其他组合均先归一为
`INDETERMINATE + AVOID + NONE`，再写拒绝原因。

预测保存三个独立 `PredictionHead`，并使用公共字段的精确名称：

```text
option.underlying_direction:
  target_spec_version = option.underlying_direction.v1
  scoreability_rule_version = option.underlying_direction.scoreability.v1
  labels = BULLISH | BEARISH | NEUTRAL
option.iv_direction:
  target_spec_version = option.iv_direction.v1
  scoreability_rule_version = option.iv_direction.scoreability.v1
  labels = VOL_UP | VOL_DOWN | NEUTRAL
option.exact_contract_net_profit:
  target_spec_version = option.exact_contract_net_profit.v1
  scoreability_rule_version = option.exact_contract_net_profit.scoreability.v1
  labels = PROFIT | LOSS
  primary_for_promotion = true
```

`option.underlying_direction` 冻结一个 `UnderlyingObservationSpec`：

```text
canonical_underlying_id
underlying_identity_version
observation_type = CASH_OFFICIAL_ADJUSTED_CLOSE | FUTURES_OFFICIAL_SETTLEMENT
price_field
source_id/source_snapshot_hash
calendar_id/timezone
entry_observation_rule/entry_observation_window
exit_observation_rule/exit_observation_window
corporate_action_or_settlement_adjustment_version
neutral_band = {value, unit, comparator, neutral_band_version}
```

期货标的必须是精确 underlying contract，不得使用连续序列。按
`underlying_return = (exit_observation - entry_observation) / entry_observation`
计算；严格大于 band 为 `BULLISH`，严格小于 `-band` 为 `BEARISH`，否则为
`NEUTRAL`。规定观测缺失、标的停牌且无 target spec 允许的官方观测，或公司行动/
结算调整版本不完整时 `UNSCORABLE`，不得改用 last/mid 或今天的调整因子。

`option.iv_direction` 只观察预测身份中的同一个精确期权合约。冻结定价模型、solver
版本、容差/边界、剩余期限 day-count、利率/分红/持有成本和标的输入；在入退时点分别
对有效 bid 与 ask 求解：

```text
entry_iv_bid = solve_iv(entry_bid, entry_time_to_expiry, frozen_inputs)
entry_iv_ask = solve_iv(entry_ask, entry_time_to_expiry, frozen_inputs)
exit_iv_bid = solve_iv(exit_bid, exit_time_to_expiry, frozen_inputs)
exit_iv_ask = solve_iv(exit_ask, exit_time_to_expiry, frozen_inputs)

VOL_UP   if exit_iv_bid - entry_iv_ask > iv_neutral_band
VOL_DOWN elif entry_iv_bid - exit_iv_ask > iv_neutral_band
NEUTRAL  otherwise
```

neutral band 的值、单位、严格比较符和版本属于 target spec。任一时点缺有效双边报价、
剩余期限 `<= 0`、任一 bid/ask solver 不收敛，或精确合约在 horizon 前到期时
`UNSCORABLE`；不得以 mid、ATM IV、曲面插值或邻近合约替代。

`option.exact_contract_net_profit` 冻结同一精确合约、entry/exit window 和全部成本：

```text
entry_value = entry_ask * multiplier * lots
regular_exit_value = exit_bid * multiplier * lots
expiry_exit_value = official_settlement_or_exercise_value * multiplier * lots
net_profit =
  selected_exit_value - entry_value
  - commissions - exchange_fees - entry_exit_slippage
  - funding_cost - exercise_or_settlement_cost - other_frozen_costs
label = PROFIT if net_profit > 0 else LOSS
```

期限前退出选 `regular_exit_value`；到期早于或等于 horizon 时，按自动行权、
settlement type 和 deliverable 冻结规则使用 `expiry_exit_value` 并记
`SCORED + EXPIRY`。入场窗口缺 ask 或非到期退出缺 bid 时 `UNSCORABLE`；到期正式
结算/行权价值优先于 bid，结算规则、deliverable 或任一成本缺失时 `UNSCORABLE`。
不得续接其他合约。

每个 head 分别冻结以下公共字段：

```text
probability_model_version
probability_artifact_hash
calibration_version
calibration_artifact_hash
training_cutoff_at
baseline_code
baseline_version
head_spec_hash
```

概率模型和校准器只能使用 `training_cutoff_at` 以前的 eligible 样本；
`baseline_code/baseline_version` 唯一解析同 spec 类别先验的不可变实现/制品。
公共层按 target、scoreability、labels、模型/校准、training cutoff 和 baseline 字段
生成 `head_spec_hash`，并将其写入 `decision_input_hash`、outcome 和评分 cohort。
任何 head 的概率不能与其他 head 混合归一；同一指标批次发现 mixed
`head_spec_hash` 时整批拒绝。Brier/Brier Skill 只在同 head、同 spec 的 `SCORED`
样本上与该 head baseline 比较；主晋级 head 仍为
`option.exact_contract_net_profit`。

## 7. 结果评分

### 7.1 买入合约

```text
entry = first_valid_ask_in_frozen_entry_window
exit = valid_bid_in_frozen_exit_window
net_pnl =
  (exit - entry) * multiplier * lots
  - commissions - exchange_fees - slippage - funding - other_frozen_costs
return_on_max_loss = net_pnl / initial_premium_and_cost
```

### 7.2 卖出平多

- 信号质量用“如果继续持有该合约，成本后收益是否为负”评价规避损失；
- 只有存在同一精确 canonical 合约、cutoff 可见且未过期的 LONG 研究持仓快照才记录
  `option.close_avoided_loss`，不得声称已验证账户成交；
- 不假定裸空并计算空头收益。

### 7.3 到期

- 到期前使用真实 bid；
- 到期时按交易所正式结算、自动行权、settlement type 和 deliverable 计算价值，并扣除
  行权/结算及其他全部冻结成本；
- 到期早于目标期限时标记
  `OutcomeStatus.SCORED + MaturityReason.EXPIRY`；
- 不续接其他期权；
- 非到期目标窗口无有效退出 bid 时为 `status=OutcomeStatus.UNSCORABLE` 并给出
  命名空间原因码；到期使用上方正式结算规则。

结果分别使用 `option.underlying_direction`、`option.iv_direction`、
`option.exact_contract_net_profit` 和 `option.close_avoided_loss` 四个
`outcome_kind`；
它们与 `prediction_id + horizon_code + evaluator_version` 联合唯一。每条结果
列化入场/退出/到期时点、价格口径、币种、成本口径、状态和成熟原因。
成绩单按 call/put、DTE、delta、IV 分位、流动性和版本分层。

## 8. 裸卖保护

```python
class CanonicalOptionPositionContext(BaseModel):
    position_context_snapshot_id: UUID
    owner_scope: str
    user_id: UUID | None
    access_principal: str
    identity_level: Literal["CONTRACT"]
    canonical_option_contract_id: str
    identity_version: str
    long_quantity: Decimal
    short_quantity: Decimal
    as_of_at: datetime
    available_at: datetime
    expires_at: datetime
    source_snapshot_hash: str
    content_hash: str


def guard_option_decision(
    candidate: ResearchDecision,
    target_contract: InstrumentIdentity,
    position: CanonicalOptionPositionContext | None,
    task_access: AccessPrincipalContext,
    run_access: AccessPrincipalContext,
    prediction_access: AccessPrincipalContext,
    cutoff_at: datetime,
) -> ResearchDecision:
    exact_context = normalize_exact_position_context(
        position=position,
        target_contract=target_contract,
        task_access=task_access,
        run_access=run_access,
        prediction_access=prediction_access,
        cutoff_at=cutoff_at,
    )
    candidate_tuple = (
        exact_context,
        candidate.normalized_direction,
        candidate.recommendation,
        candidate.trade_intent,
    )
    if candidate_tuple not in OPTION_V1_ALLOWED_TUPLES:
        return avoided_decision(
            position_context=exact_context,
            normalized_direction="INDETERMINATE",
            recommendation="AVOID",
            trade_intent="NONE",
            reason_code="OPTION.ACTION_TUPLE_BLOCKED",
        )
    return candidate.model_copy(update={"position_context": exact_context})
```

`AccessPrincipalContext.access_principal` 规范为
`owner_scope + "|" + coalesce(user_id, "SYSTEM")`。task、run 和 prediction 三者的
`owner_scope/user_id/access_principal` 必须先逐字段相等，position snapshot 也必须与
三者完全相等；可空 `user_id` 在 MySQL 使用 null-safe equality（`<=>`；SQLite 本地回归
使用 `IS`），不能让两个不同主体因普通 NULL 比较而绕过。只有 snapshot 为
`identity_level=CONTRACT`，canonical option contract
ID 和 identity version 与本次预测完全相同，`available_at <= cutoff_at < expires_at`
且 `long_quantity > 0 && short_quantity == 0` 时才规范为 `LONG`。同合约两个 quantity
均为零才是 `FLAT`；无 snapshot、跨 owner/user/access principal、cutoff 后可见、过期、
跨合约或 identity version 不同均规范为 `UNKNOWN`，不得 CLOSE，也不得泄露其他用户
snapshot 是否存在。任意 `short_quantity > 0` 是不受支持的 `SHORT` 并 fail-closed。
guard 必须接收完整 `ResearchDecision`，不能只校验 direction 或 intent 后重新拼接
recommendation。

`asset_position_context_snapshots` 是 append-only 事实表。`content_hash` 对 owner、
user、access principal、CONTRACT 身份、数量、有效区间和来源哈希的 canonical JSON
计算；数据库拒绝更新 hash 输入字段。prediction 保存
`position_context_snapshot_id` 和同一 `content_hash`，前者
`ON DELETE RESTRICT` 外键到快照表，二者都进入 `decision_input_hash`。

数据库约束不能只写一个无法跨表查询的 CHECK。实现采用两层数据库不变量：

1. 行级 CHECK：期权 prediction 的 `position_context=LONG` 必须有非空
   `position_context_snapshot_id`；decision JSON 出现 `trade_intent=CLOSE` 时也必须
   同时为 LONG 且 FK 非空；
2. 跨表约束 trigger：插入或修改 prediction 时按 FK 读取不可变 snapshot，断言
   `identity_level=CONTRACT`、canonical ID/identity version、cutoff 有效区间、
   LONG 数量及 `owner_scope/user_id/access_principal` 与 task、run、prediction 全等；
   MySQL 使用即时 insert/update trigger，SQLite 的等价实现只用于本地回归。

MySQL 迁移提供发布所需的 trigger，并由真实一次性 MySQL 契约夹具验证；SQLite 等价实现
只用于本地回归。这样
`LONG + NEUTRAL + SELL + CLOSE` 只有绑定当前 principal、当前精确合约且 cutoff 有效的
LONG snapshot 才能落库；其他情况在服务层为 UNKNOWN，绕过服务直写数据库也会失败。

API Schema 拒绝客户端提交的 `SELL_TO_OPEN`、`SHORT` 和非法公共元组；服务层按上述
白名单与精确持仓 fail-closed；数据库 CHECK 拒绝 `SHORT`、`SELL + OPEN` 和白名单外
元组，并用 position snapshot 外键/约束保证 CLOSE 对应同一 canonical 合约的有效 LONG
快照。三层任一失败均不得降格写入可行动决定。`BUY_TO_OPEN` 和 `SELL_TO_CLOSE`
只是输出标签，报告模板不能建议绕过限制。

## 9. API 和页面

```json
{
  "asset_type": "option",
  "canonical_id": "option:SSE:10008156:CALL:2026-09-23:CNY",
  "horizon_code": "5_sessions",
  "position_context": "UNKNOWN"
}
```

`OptionPanel.vue` 包含期权链、IV smile/term、Greeks、盈亏图、到期倒计时和醒目动作语义。买入 put 显示“合约买入 / 标的看空”，不能显示为“买入标的”。

普通用户 API、页面和导出只读取 `published_decision`；管理员影子页才可读取
`candidate_decision`。预测幂等使用规范化 `decision_input_hash`，覆盖精确合约、
完整 canonical position context、`position_context_snapshot_id/content_hash`、
`owner_scope/user_id/access_principal`、同步链/标的快照、三个 head 的
`target_spec_version/scoreability_rule_version` 及 target spec 内的 neutral band、
`probability_model_version/probability_artifact_hash`、
`calibration_version/calibration_artifact_hash/training_cutoff_at`、
`baseline_code/baseline_version/head_spec_hash`，以及曲面、成本和策略版本。

## 10. 每日影子调度

v1 的 `OptionScheduleTarget` 只能是审批后的
`canonical_option_contract_id + identity_version`，并冻结交易所日历、cutoff 和
schedule version。DTE/delta/行权价/流动性 selector 只在配置阶段对冻结链运行，输出
包含 rule version/hash、resolution cutoff、候选排序、stable tie-break、精确合约清单
和审批证据的不可变 selection manifest；系统随后为每个精确合约展开一条 CONTRACT
schedule。运行器不接收 selector，也不扫描链选择或滚动合约。

收盘且目标精确合约所需链可用后运行；`run_key` 由
`schedule_id + schedule_version + scheduled_fire_at + cutoff_at +
cutoff_policy_version + policy_version` 生成，以租约锁去重并冻结完整 schedule 配置。
没有合格候选时配置阶段返回 `NO_ELIGIBLE_CONTRACT`，不创建 schedule。合约到期或需替换
时必须重新解析和审批。失败补跑继续使用原 cutoff、原 canonical 合约/identity version、
原 schedule 配置及冻结的链/标的/持仓快照 ID/hash/access principal 和 head spec，
禁止重跑 selector、跨用户重绑持仓、自动换约或用事后完整链修补旧预测。

## 11. 来源

合约和规则优先交易所/OCC，生产链和双边报价使用合法授权源。Cboe、CME 和境内交易所数据遵循各自许可；AKShare 只可原型。OCC 风险披露是必读风险资料：[Options Disclosure Document](https://www.theocc.com/company-information/documents-and-archives/options-disclosure-document)。
