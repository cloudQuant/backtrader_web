# 191C AI 期货验收文档

## 1. T1 技术验收

### FUT-A01 身份和规则

- [ ] 真实合约解析交易所、月份、乘数、tick、最后交易日和会话；
- [ ] 不依赖代码字符串补全未知字段；
- [ ] 已到期、停止交易或不允许持有窗口得到拒绝；
- [ ] 品种、合约和连续序列是不同身份。

### FUT-A02 连续映射

- [ ] 连续序列显示当时映射真实合约；
- [ ] 建议和评分只使用真实合约原始价格；
- [ ] 映射快照冻结 cutoff 可见的有序 `normalization_chain`、`chain_vintage_at`、
  mapping/normalization source hash 和 canonical chain hash；
- [ ] 换月记录旧/新合约、时点、规则、调整因子、来源记录哈希和 `available_at`；
- [ ] 固定 cutoff 夹具在追加未来量仓、换月和来源修订前后，mapped contract、
  normalization chain hash、feature value 与 feature hash 逐字节相同；
- [ ] 新 vintage 只追加新快照，旧映射/链/特征事实不可更新；链含 cutoff 后节点或
  source/hash 不匹配时强制拒绝。

### FUT-A03 会话

- [ ] 19:10 后有夜盘合约得到当晚真实开盘；
- [ ] 无夜盘合约得到下一日盘；
- [ ] 节前取消夜盘正确跳过；
- [ ] 当前未完成 bar 不进入特征；
- [ ] 所有日历来自品种规则而非普通工作日。

### FUT-A04 特征和质量

#### 当前已验证的离线子集（不替代本节全部 T1）

- [x] 只有明确冻结了 spot/futures 价格、到期日、报价单位、品质、地点和税口径时才计算
  `basis=futures-spot` 与年化 carry；品质或地点不一致时返回
  `null + FUTURES.BASIS_NOT_COMPARABLE`，见
  `tests/asset_research/futures/test_futures_term_structure.py`；
- [x] 期货插件将比较后的 basis、carry、距到期日及原因码写入强类型详情，见
  `tests/asset_research/futures/test_futures_plugin_term_structure.py`。

> 连续映射、库存/COT、涨跌停及真实市场会话仍未完成，原始 T1 条目保持未勾选。

- [ ] 固定曲线夹具得到设计公式的 carry 正负和数值；
- [ ] 基差的单位、品质、地点和税费不可比时不计算；
- [ ] 库存、仓单或 COT 缺失不补 0；
- [ ] 单边涨跌停、无双边报价、规则未知强制 AVOID；
- [ ] 聚合持仓不被描述为确定机构观点。

### FUT-A05 建议和报告

- [ ] 公共方向、持仓、建议和意图真值表逐行通过，不存在第二套持久化动作枚举；
- [ ] 不同持仓上下文得到正确动作矩阵；
- [ ] 空仓 SHORT 在 `short_open_research_allowed=true` 时为
  `SHORT + SELL + OPEN`，未批准时为 `SHORT + SELL + NONE`，两者均
  `execution_disabled=true`；
- [ ] 内部候选策略的正负夹具可产生 LONG/SHORT；
- [ ] `SHADOW` 下普通用户 API、页面和导出只能返回
  `INDETERMINATE + HOLD/AVOID + NONE`；
- [ ] 十三章节、图表、来源、cutoff 和版本完整；
- [ ] LLM 冲突不能改变方向和质量。

### FUT-A06 结果

- [ ] `futures.contract_pnl` 冻结 `target_spec_version`、
  `scoreability_rule_version`、版本化 neutral band、完整 HorizonSpec 和精确合约；
- [ ] 多头严格用 entry ask/exit bid，空头严格用 entry bid/exit ask；费用、滑点、
  乘数和其他冻结成本正确，bid/ask 已含点差且不重复扣除；
- [ ] `TRADING_SESSION` 把夜盘/日盘分别计数；`TRADING_DAY` 按交易所
  `trading_day` 去重且夜盘归属正确，不使用自然日；
- [ ] 固定数值黄金夹具分别唯一产生 `LONG`、`SHORT`、`NEUTRAL`，边界等于
  neutral band 时为 `NEUTRAL`；
- [ ] entry/exit 缺报价、目标 side 单边涨跌停得到 `UNSCORABLE`，不使用
  settlement/mid/连续价替代；
- [ ] 期限越过 `last_trade_at` 时只在冻结的到期前窗口评分并记录 `EXPIRY`；无可执行
  报价则 `UNSCORABLE`，绝不续接下月；
- [ ] 主 head 冻结 `probability_model_version/probability_artifact_hash`、
  `calibration_version/calibration_artifact_hash/training_cutoff_at`、
  `baseline_code/baseline_version` 和公共 `head_spec_hash`；模型/校准训练样本不得晚于
  cutoff，baseline code/version 唯一解析同 spec 的不可变先验实现/制品；
- [ ] `head_spec_hash` 不同的概率、结果或 cohort 混合输入整批拒绝，不能隐式迁移；
  Brier/Brier Skill 只比较同 spec 主 head 和 baseline；
- [ ] 合同级和 roll-aware 结果分开；
- [ ] 到期不续接另一合约；
- [ ] 名义和保证金收益分开；
- [ ] `futures.close_avoided_loss` 与 `futures.contract_pnl` 不混算；
- [ ] 相同预测、期限和评估器可同时保存三个不同 `outcome_kind`；
- [ ] 每条结果的入场/退出/到期、报价、币种、成本、状态和成熟原因完整。

### FUT-A07 调度、幂等和晋级

- [ ] 审批静态清单只在配置阶段展开成版本化的单合约 schedule，不扫描全部市场；
- [ ] 每条 schedule 固定 `identity_level=CONTRACT`、`canonical_id` 和
  `identity_version`；runner 不接受主力/近月/连续序列等运行时 selector；
- [ ] 19:10 任务按品种日历选择下一夜盘或日盘，重复触发只产生一次运行；
- [ ] 失败补跑沿用原 cutoff、合约标识、schedule 配置、normalization chain
  vintage/source hash、head spec 和制品，且保持原 `canonical_id/identity_version`，
  不吸收后来换月、数据或模型；
- [ ] `decision_input_hash` 的持仓、真实合约、连续映射/chain hash、HorizonSpec、
  `target_spec_version/scoreability_rule_version` 及 target spec 内的 neutral band、
  成本、probability/calibration artifact、
  `training_cutoff_at`、`baseline_code/baseline_version`、`head_spec_hash` 或
  short capability 任一变化均产生新预测；
- [ ] `POOLED` 晋级执行单品种 40% 上限；`INSTRUMENT_SPECIFIC` 晋级改用
  合约月份和市场状态门槛；
- [ ] 晋级证据包含 `promotion_scope_key`、主预测 head、`head_spec_hash`、
  `target_spec_version/scoreability_rule_version`、模型/校准制品、`training_cutoff_at`、
  `baseline_code/baseline_version`、策略版本和审批历史。

## 2. 需求追踪

| 需求 | 验收 |
| --- | --- |
| FUT-FR-001、002 | FUT-A01 |
| FUT-FR-003 | FUT-A02 |
| FUT-FR-004 至 006 | FUT-A04 |
| FUT-FR-007 | FUT-A03 |
| FUT-FR-008、012 | FUT-A05、A04 |
| FUT-FR-009 | FUT-A05 |
| FUT-FR-010、011 | FUT-A06 |
| FUT-FR-013 | FUT-A07 |

## 3. 在线冒烟

- 一个中金所股指合约：验证日盘、指数基差和现金交割；
- 一个有夜盘商品合约：验证 19:10 到 21:00 会话和期限结构；
- 一个临近到期固定夹具：验证交割否决；
- 一个主力连续输入：验证真实合约、normalization chain/source hash 冻结，以及未来
  换月后相同 cutoff 的 feature/hash 不变；
- 三个数值化净收益夹具：分别验证 LONG、SHORT、NEUTRAL；
- missing quote、单边涨跌停、到期前退出和 mixed-spec 批次：验证
  `UNSCORABLE/EXPIRY/REJECTED` 的固定分支。

## 4. T2 晋级补充

`promotion_scope_key` 明确声明 `POOLED` 或 `INSTRUMENT_SPECIFIC`。`POOLED` 的商品、股指、
国债和外汇期货分别晋级，并执行单品种不超过 40% 的集中度门槛；
`INSTRUMENT_SPECIFIC` scope 不使用该比例，但至少覆盖三个合约月份和三个期限结构/波动状态。
主晋级 head 为 `futures.contract_pnl`。净 P&L 必须使用实际合约和成本，
任何连续复权回测结果不得作为晋级证据。
