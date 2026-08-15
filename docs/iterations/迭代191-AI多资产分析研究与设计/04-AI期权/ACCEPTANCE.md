# 191D AI 期权验收文档

## 1. T1 技术验收

### OPT-A01 身份

- [ ] 相同行权价和月份的 call/put 为不同合约；
- [ ] 标的、到期、行权价、乘数、欧/美式和结算完整；
- [ ] 裸标的不静默选择合约；
- [ ] 到期/停止交易合约拒绝新建议。

### OPT-A02 定价

- [ ] 欧式期货期权使用 Black-76；
- [ ] 欧式现货/指数使用 BSM/远期模型；
- [ ] 美式使用支持提前行权的模型；
- [ ] 价格、IV 和 Greeks 与黄金用例在精度内一致；
- [ ] 同一精确合约 bid/ask IV 分别使用冻结 solver、day-count、剩余期限和模型输入；
- [ ] bid/ask 缺失、期限非正或任一 IV 不收敛返回 `null + reason`，不得使用 mid、
  ATM IV、曲面或邻近合约替代。

### OPT-A03 链和质量

- [ ] 输入单合约仍加载同步标的和足够链；
- [ ] 标的/期权时点不一致触发降级/拒绝；
- [ ] crossed、过期、零 bid、过宽价差和深度不足按配置过滤；
- [ ] 静态套利清洗后覆盖不足时不生成曲面方向；
- [ ] 理论价不能替代可成交报价。

### OPT-A04 动作安全

- [ ] 买入 put 显示“合约买入、标的看空”；
- [ ] 同一精确合约的原始持仓输入 `long_quantity=0` 且 `short_quantity=0` 时，
  `CanonicalOptionPositionContext` 唯一规范化为 `FLAT`，不能成为 `LONG/SHORT/UNKNOWN`；
- [ ] 完整动作元组黄金表逐行通过：
  `FLAT + LONG + BUY + OPEN`、`LONG + LONG + HOLD + KEEP`、
  `LONG + NEUTRAL + SELL + CLOSE`、`FLAT + NEUTRAL + HOLD + NONE`、
  `UNKNOWN + LONG + BUY + NONE`、`UNKNOWN + NEUTRAL + HOLD + NONE`；
- [ ] guard 的输入是完整 `ResearchDecision` 与
  `CanonicalOptionPositionContext`，不会只凭 direction/intent 或聚合数量拼接动作；
- [ ] position snapshot 冻结 `position_context_snapshot_id/content_hash`、
  `owner_scope/user_id/access_principal`、`identity_level=CONTRACT`、canonical option
  contract ID/identity version、数量、`available_at/expires_at` 和来源哈希；
- [ ] `access_principal=owner_scope|coalesce(user_id,"SYSTEM")`，snapshot 与 task、run、
  prediction 的 owner/user/access principal 必须逐字段全等；
- [ ] 只有 `available_at <= cutoff_at < expires_at`、精确 CONTRACT 身份全匹配且
  long quantity 为正、short quantity 为零的快照才能得到 LONG；
- [ ] 无 snapshot、跨用户/owner/access principal、跨合约、identity version 不同、
  cutoff 后可见或过期均为 UNKNOWN，不能 CLOSE，且响应不泄露其他用户快照是否存在；
- [ ] 仅上述精确 LONG 上下文的 `NEUTRAL + SELL + CLOSE` 页面才派生
  `SELL_TO_CLOSE`；
- [ ] SHORT context、`normalized_direction=SHORT`、`SELL + OPEN`、`SELL_TO_OPEN`、
  无有效 LONG context 的 CLOSE 和任何白名单外元组均得到
  `INDETERMINATE + AVOID + NONE`；
- [ ] 上述非法输入在 API Schema、服务 guard、数据库 CHECK/精确持仓约束三层各有独立
  拒绝夹具；
- [ ] prediction 的 `position_context_snapshot_id` 是
  `asset_position_context_snapshots.id ON DELETE RESTRICT` 外键，保存的 hash 与快照
  canonical 内容一致，引用后修改/删除快照失败；
- [ ] 真实 MySQL 验证行级 LONG/CLOSE 非空 FK CHECK 和跨表约束 trigger；SQLite 仅保留
  本地回归。绕过服务直写跨用户、跨合约、过期或非 LONG snapshot 的 CLOSE 均失败；
- [ ] 内部候选正负夹具可产生 BUY/SELL；
- [ ] `SHADOW` 普通用户 API、页面和导出只能返回
  `INDETERMINATE + HOLD/AVOID + NONE`；
- [ ] 风险否决能覆盖普通 HOLD；
- [ ] LLM 不能改变动作。

### OPT-A05 报告和页面

- [ ] 十三章节、链、IV、Greeks、盈亏图、最大损失和到期完整；
- [ ] 模型、利率/分红、曲面质量和时间戳可见；
- [ ] 无链/无 IV/无报价显示原因，不显示 0；
- [ ] 页面、API 和导出一致。

### OPT-A06 结果

- [ ] 三个 head 分别冻结 `target_spec_version/scoreability_rule_version`、
  HorizonSpec、标签/neutral-band 边界、
  `probability_model_version/probability_artifact_hash`、
  `calibration_version/calibration_artifact_hash/training_cutoff_at`、
  `baseline_code/baseline_version` 和公共 `head_spec_hash`；
- [ ] underlying 黄金夹具固定 observation object 和 adjustment spec，分别唯一产生
  `BULLISH/BEARISH/NEUTRAL`；缺观测、停牌无官方观测或公司行动版本缺失时
  `UNSCORABLE`；
- [ ] IV 黄金夹具用 entry/exit bid/ask 的保守区间规则分别唯一产生
  `VOL_UP/VOL_DOWN/NEUTRAL`；缺双边报价、期限非正、solver 不收敛或 horizon 跨到期
  时 `UNSCORABLE`；
- [ ] exact-contract profit 用 entry ask、正常 exit bid，扣除佣金、交易费、滑点、
  资金及其他冻结成本，黄金夹具分别产生 `PROFIT/LOSS`；
- [ ] entry window 缺 ask 或正常 exit window 缺 bid 时为 `UNSCORABLE`，不得使用
  mid、理论价或其他合约替代；
- [ ] 到期早于/等于 horizon 时正式结算/行权价值优先于 bid，并计入自动行权、
  settlement、deliverable 和全部行权/结算成本；到期为 `SCORED + EXPIRY` 且不续约；
- [ ] 正常退出无 bid，以及到期结算规则/deliverable/成本不完整时
  `OutcomeStatus.UNSCORABLE` 且带原因码；
- [ ] 三个 head 的概率各自归一；`head_spec_hash` 不同的概率、结果或 cohort 混合输入
  整批拒绝，不做隐式迁移；
- [ ] Brier/Brier Skill 只比较同 head、同 spec、同 `SCORED` 集合和对应 baseline，
  概率模型和校准样本均不晚于 `training_cutoff_at`；
- [ ] `option.close_avoided_loss` 只评价规避损失，不构造空头收益；
- [ ] 四个 `outcome_kind` 可在同一预测、期限和评估器下并存；
- [ ] 每类结果列化时点、价格、币种和成本口径；
- [ ] 按 call/put、DTE、delta、IV、流动性和版本分层。

### OPT-A07 调度、幂等和晋级

- [ ] v1 schedule target 只接受审批的
  `canonical_option_contract_id + identity_version`；运行请求和 run 配置中没有
  selector、裸标的或自动滚动字段；
- [ ] DTE/delta/行权价/流动性 selector 只在配置阶段对冻结链解析，manifest 冻结 rule
  version/hash、resolution cutoff、候选排序、stable tie-break 和审批证据，并展开为
  每个精确合约一条 schedule；
- [ ] 配置阶段 `NO_ELIGIBLE_CONTRACT` 不创建 schedule；到期替代合约必须重新解析和
  审批，不能运行时换约；
- [ ] 交易所收盘且完整链可用后运行，重复触发只产生一次调度运行；
- [ ] 失败补跑使用原 cutoff、同一 canonical 合约/identity version、schedule 配置、
  链/标的/持仓 snapshot ID/hash/access principal 和 head spec；断言未调用 selector、
  未跨用户重绑持仓且不吸收事后数据；
- [ ] 精确合约、exact canonical position context、链/标的快照、任一 head 的
  `position_context_snapshot_id/content_hash`、`owner_scope/user_id/access_principal`、
  `target_spec_version/scoreability_rule_version` 及 target spec 内的 neutral band、
  probability/calibration artifact、
  `training_cutoff_at`、`baseline_code/baseline_version/head_spec_hash` 或其他曲面/
  成本/策略版本变化会改变 `decision_input_hash`；
- [ ] `POOLED` scope 执行单一标的 40% 上限；`INSTRUMENT_SPECIFIC` scope
  改验多个到期、
  行权价和市场状态；
- [ ] 晋级审计固定 `promotion_scope_key`、主 head、`head_spec_hash`、
  `target_spec_version/scoreability_rule_version`、模型/校准制品、
  `training_cutoff_at`、`baseline_code/baseline_version`、策略版本、审批人和证据 URI。

## 2. 需求追踪

| 需求 | 验收 |
| --- | --- |
| OPT-FR-001、002 | OPT-A01、A03 |
| OPT-FR-003、004 | OPT-A02 |
| OPT-FR-005 至 007 | OPT-A03 |
| OPT-FR-008、009、012 | OPT-A04 |
| OPT-FR-010 | OPT-A05 |
| OPT-FR-011 | OPT-A06 |
| OPT-FR-013 | OPT-A07 |

## 3. 在线冒烟

- 一个高流动性欧式 call 和 put；
- 一个美式商品期权；
- 一个链覆盖不足合约；
- 动作白名单六行、SHORT context/direction、SELL+OPEN，以及缺 snapshot、跨用户/owner、
  跨合约、cutoff 后可见和过期持仓 CLOSE 的安全夹具；
- 三个 head 的全部标签、missing/solver/期限、mixed-spec 和到期结算固定夹具；
- 一个配置期 selector 展开为精确 schedule，并用原具体合约成功补跑且 selector
  零调用的固定夹具。

## 4. T2 晋级补充

`promotion_scope_key` 必须声明 `POOLED` 或 `INSTRUMENT_SPECIFIC`，并登记主预测 head。
call/put、DTE、delta、IV 和流动性桶均需覆盖；`POOLED` scope 的单一标的不超过
40%，`INSTRUMENT_SPECIFIC` scope 则覆盖多个到期、行权价和市场状态。
`option.exact_contract_net_profit` 未通过时，即使标的方向 head 通过也不得晋级。
没有完整 point-in-time 链、双边报价和真实成本，方向建议保持 `SHADOW`。
三个 head 的晋级证据均按各自 `head_spec_hash` 和 baseline 分 cohort；mixed-spec
样本不得合并。
