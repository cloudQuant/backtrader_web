# 191B AI 基金验收文档

## 1. T1 技术验收

### FUND-A00 原始采集与门控顺序

- [ ] `RawFundIdentityCandidate` 和 `RawFundSnapshot` 的 official benchmark、NAV、
  fees、holdings、dealing、market 叶子值均可为 `null`，每个叶子仍包含
  `provenance/observed_at/published_at/available_at/retrieved_at`；
- [ ] 测试数据库可证明 raw snapshot 的 append-only 提交发生在 quality gate、
  类型分析和特征计算之前；门控与重跑不能覆盖原始内容哈希；
- [ ] `PostGateFundSnapshot` 只在相应类型关键字段通过门控后构造；拒绝路径不尝试
  用必填字段模型重新解析 raw 数据；
- [ ] 固定参数化夹具分别移除 official benchmark、NAV、fees 和 holdings，任务
  创建/结果 API 返回正常业务响应而不是 Pydantic 422 或未捕获 500；
- [ ] 每个失败夹具均可按 `raw_snapshot_id` 回读审计证据，得到稳定
  `COMMON.BENCHMARK_MISSING`、`FUND.OFFICIAL_NAV_MISSING`、
  `FUND.FEE_SCHEDULE_MISSING` 或 `FUND.HOLDINGS_AS_OF_MISSING`，并发布
  `quality_status=REJECTED`、`actionability=INSUFFICIENT_DATA`、
  `market_view=INDETERMINATE`、`normalized_direction=INDETERMINATE`、
  `recommendation=AVOID`、`trade_intent=NONE`，持仓上下文独立保留；
- [ ] 杠杆/反向等已识别专属基金保留 raw snapshot，发布
  `quality_status` 为 `ELIGIBLE` 或 `DEGRADED`，
  `actionability=RESEARCH_ONLY/FUND.SPECIALIZED_MODEL_REQUIRED`、
  `trade_intent=NONE`，不退化到通用基金算法且不返回 422/500；
- [ ] GateResult 的 `quality_status` 只接受 `ELIGIBLE/DEGRADED/REJECTED`，
  `actionability` 只接受
  `ACTIONABLE/RESEARCH_ONLY/INSUFFICIENT_DATA/REGION_RESTRICTED`；构造
  `quality_status=RESEARCH_ONLY` 或 `actionability=NONE` 必须失败。

### FUND-A01 身份和类型

- [ ] 同一基金 A/C/I/ETF 份额解析为不同 `canonical_id` 和费率；
- [ ] `candidate_kind=FUND_PRODUCT` 只能搜索、不能持久化或分析，必须继续选择份额；
- [ ] `fund_identity_kind=SHARE_CLASS/LISTING` 均使用公共 `identity_level=PRODUCT`；
- [ ] 开放式 `SHARE_CLASS` 的 `venue=null` 且申赎通道、cutoff、NAV 日历完整；
- [ ] ETF/LOF/封闭式 `LISTING` 必须有 `venue`，缺失时不得创建任务；
- [ ] 多份额候选返回 `FUND.SHARE_CLASS_AMBIGUOUS`，不静默绑定；
- [ ] ETF、开放式、货币、债券、QDII 路由正确；
- [ ] 杠杆/反向/商品基金被专属类型拦截；
- [ ] 正式基准缺失时不能生成可行动建议。

### FUND-A02 NAV、费用和持仓

#### 当前已验证的离线子集（不替代本节全部 T1）

- [x] 基金在来源提供同日对齐的官方 NAV 与基准路径时，按逐期
  `(NAV + distribution) / prior_NAV` 复利计算含分红总回报、基准回报、超额和年化
  tracking error；ETF 的市场中间价/NAV 溢折价独立计算，见
  `tests/asset_research/fund/test_fund_metrics.py`；
- [x] 缺官方 NAV 返回 `null + FUND.OFFICIAL_NAV_MISSING`，不由市场价格或股票动量替代；
  插件把已验证字段及原因码写入 `FundResearchDetails`，见
  `tests/asset_research/fund/test_fund_plugin_metrics.py`。

> 费用分项、PCF/IOPV、开放式申赎窗口、QDII 双日历及真实来源 vintage 尚未验证，原始 T1 条目保持未勾选。

- [ ] 官方 NAV、估算净值和市场价不混用；
- [ ] 跨分红总回报包含分红再投资；
- [ ] 管理、托管、销售、申购/赎回和场内成本按份额正确；
- [ ] 过期持仓显示 `holdings_as_of`，不称当前持仓；
- [ ] 修订或晚披露数据不回灌旧预测。

### FUND-A03 ETF

- [ ] 溢折价等于 `market_mid / NAV - 1`；
- [ ] PCF、IOPV、申赎状态和跟踪质量字段正确；
- [ ] 当日 PCF 缺失、申购暂停、无双边报价或极端溢价时禁止 BUY；
- [ ] 即使价格动量为正，风险门控仍能覆盖建议。

### FUND-A04 开放式和特殊基金

- [ ] 开放式基金使用下一适用 NAV，不读取开盘价；
- [ ] 暂停赎回时不能输出“开盘卖出”；
- [ ] QDII 使用境内外双日历和合同 NAV 延迟；
- [ ] 货币基金使用现金基准，不与股票/混合基金汇总；
- [ ] 成立不足 36 个月显示 `short_track_record` 且不显示平台评级。

### FUND-A05 建议和报告

- [ ] 结构质量与战术进入分别展示；
- [ ] 决策结构只含公共四字段，`normalized_direction` 仅为 `LONG/SHORT/NEUTRAL/INDETERMINATE`，无 `FundAction`；
- [ ] 正、负、无优势夹具按 `position_context` 得到规定四元组；
- [ ] 已有多头的 `SELL` 对应 `REDUCE/CLOSE`，空仓负向候选不得发布 `SELL`；
- [ ] `position_context=UNKNOWN` 发布层不生成动作，输入 `SHORT` 返回 `COMMON.POSITION_CONTEXT_UNSUPPORTED`；
- [ ] 数据/许可/风险否决为 `quality_status=REJECTED`、
  `actionability=INSUFFICIENT_DATA`；地区禁止为
  `actionability=REGION_RESTRICTED` 且优先覆盖其他发布结果；
- [ ] 模型未晋级、专属复杂基金或 DEGRADED 为
  `quality_status` 为 `ELIGIBLE` 或 `DEGRADED`、
  `actionability=RESEARCH_ONLY`；已晋级且质量合格才为
  `ELIGIBLE + ACTIONABLE`；
- [ ] SHADOW 候选层保存真实结果，普通 API/页面/导出/知识库只见 `HOLD/AVOID` 和 `COMMON.MODEL_NOT_PROMOTED`；
- [ ] 仅精确匹配已批准 `promotion_scope_key` 时，普通用户才可见候选方向；
- [ ] `BUY/SELL/HOLD/AVOID` 的执行语义随基金类型正确；
- [ ] 十五个章节、来源、日期、费用和基准完整；
- [ ] LLM 相反文本不能读取候选层或改变动作和质量；
- [ ] API、页面、Markdown、PDF 和知识库一致。

### FUND-A06 历史结果

- [ ] 每个候选按基金类型恰有一个收益主预测 head，其目标、标签、概率、
  `target_spec_version/scoreability_rule_version`、
  `probability_model_version/probability_artifact_hash`、
  `calibration_version/calibration_artifact_hash/training_cutoff_at`、
  `baseline_code/baseline_version` 完整且 `head_spec_hash` 可复算；
- [ ] cohort 中任一 `head_spec_hash` 不同，或 target、scoreability、概率模型、
  校准、基线版本混合形成 mixed-spec cohort 时，聚合与晋级必须返回稳定契约错误，
  不能合并分母；
- [ ] `fund.dealing_event` 概率与主 head 独立归一，不改变主 head 的 Brier 分母；
- [ ] 五个稳定 `outcome_kind` 只按适用基金类型生成，事件头可与主头并存且不覆盖；
- [ ] 唯一键为 `(prediction_id, horizon_code, outcome_kind, evaluator_version)`，同版本重跑无重复，新版本只追加；
- [ ] 每个结果头均可按冻结规则得到 `PENDING/PARTIAL/SCORED/UNSCORABLE`，部分 NAV/市场事实使用 `PARTIAL`；
- [ ] `MaturityReason` 与 `OutcomeStatus` 分离，正常期限和终止上市分别记录 `HORIZON_REACHED/DELISTING`；
- [ ] ETF 使用下一交易时段和 5/20/60 日价格、点差和分红；
- [ ] 开放式使用 cutoff 和 20/60/120 个估值日 NAV；
- [ ] 申赎费、销售服务费、场内成本正确进入结果；
- [ ] HOLD 不进入行动命中率，分母和成熟样本清晰；
- [ ] 结果按基金类型、份额、基准、期限和版本分层。

### FUND-A07 调度、截止和幂等

- [ ] 中国 ETF 按 19:10/19:00、开放式按 23:30/23:15、美国 ETF 按纽约 18:30/18:15 运行；
- [ ] 次日 08:30 catch-up 只处理缺官方 NAV 的任务，使用 08:15 新截止和新预测键，不改旧快照；
- [ ] QDII 合同允许的 NAV lag 不被标记为 `FUND.OFFICIAL_NAV_STALE`；
- [ ] 每条 schedule 只绑定一个 `canonical_id`，静态许可清单展开为多条 schedule，运行时无市场/宇宙扫描；
- [ ] 相同 `run_key` 的重复触发关联既有运行，schedule 版本、触发/截止时间、截止策略或策略版本变化产生新键；
- [ ] `access_principal=owner_scope|coalesce(user_id,"SYSTEM")`；只有相同
  `access_principal + decision_input_hash` 才复用 `prediction_key`；
- [ ] 相同 `owner_scope/decision_input_hash` 但不同 `user_id` 生成不同
  `prediction_key`，不得跨用户复用候选、发布决定或预测；系统影子任务稳定使用
  `SYSTEM` 主体；
- [ ] 同一主体下持仓、快照或任一输入版本变化生成新预测；
- [ ] 历史回补只读取当时 `available_at <= cutoff_at` 的版本，缺失时返回稳定 `COMMON.*` 或 `FUND.*`。

### FUND-A08 晋级范围和原因码

- [ ] `promotion_scope_key` 来自规范化 `PromotionScope`，包含范围模式、基金类型、
  地区、执行机制、基准族、期限和主 head；策略/模型/校准版本使用注册表独立列；
- [ ] 两类 scope 均至少 200 个成熟可评分行动主头、60 个去重 `cutoff_date`、
  3 个冻结市场状态，并通过 walk-forward、purge/embargo 和 60 个交易日/估值日
  前瞻影子期；
- [ ] 池化范围额外包含 5 个经济基金产品组，任一产品组不超过 40% 并报告 HHI；
- [ ] A/C/I、ETF/联接和多场所实例按同一产品合并，不能借重复份额稀释集中度；
- [ ] `INSTRUMENT_SPECIFIC` 单基金范围键包含 `canonical_id`，允许 100% 单标的
  样本、不套 5 产品组和 40% 集中度，但只解锁该份额/实例；
- [ ] 证据包冻结 `regime_source_id`、vintage、日历、算法/参数、区间、
  `regime_version`，BULL/BEAR/SIDEWAYS 各至少 20 个独立成熟日期；
- [ ] `LONG_TERM_QUALITY` 的冻结区间各含一个连续至少 60 个适用估值日的 BULL 和
  BEAR 段；`TACTICAL_SIGNAL` 的已晋级响应仍无“基金评级”声明；
- [ ] 主指标是成本后 `delta_net_utility=model-baseline`：模型平均净效用 `> 0`，
  10,000 次 95% moving-block bootstrap CI 下界 `>= 0`，block 不短于最大标签
  重叠期且 seed/长度被冻结；
- [ ] 同 target、同 cohort 主 head 的 `Brier Skill Score > 0`；最大回撤不超过基线
  加预注册容忍度，1.5 倍成本压力下平均净效用 `>= 0`；
- [ ] 池化和单基金证据、审批、发布和回退相互隔离；
- [ ] API 通用原因均为稳定 `COMMON.*`、基金专属原因均为 `FUND.*`，中文变化不改变原因码。

## 2. 需求追踪

| 需求 | 验收 |
| --- | --- |
| FUND-FR-001、002 | FUND-A00、A01 |
| FUND-FR-003 至 006 | FUND-A02、A04 |
| FUND-FR-007 | FUND-A03 |
| FUND-FR-008、012 | FUND-A00、A03 至 A05 |
| FUND-FR-009 | FUND-A05 |
| FUND-FR-010、011 | FUND-A00、A06 |
| FUND-FR-013 | FUND-A05 |
| FUND-FR-014 | FUND-A06 |
| FUND-FR-015 | FUND-A07 |
| FUND-FR-016 | FUND-A08 |
| FUND-FR-017 | FUND-A01 至 A08 |

## 3. 在线冒烟

- 一只高流动性 ETF：验证价格、NAV、PCF、溢折价和基准；
- 同一基金 A/C 两类：验证身份、费用和结果不合并；
- 一只开放式基金：验证 cutoff 和下一 NAV；
- 一只 QDII：验证 NAV 延迟和双日历；
- 缺正式基准、官方 NAV、费用和持仓日期的四个固定夹具：验证 raw snapshot 可回读、
  稳定原因码及 `REJECTED + INSUFFICIENT_DATA + AVOID/NONE`；
- 一只暂停申购或固定失败夹具：验证风险否决。

## 4. T2 晋级补充

模型候选层与发布层分开验收：T1 证明候选计算正确且普通用户看不到候选；T2 才允许精确范围发布。ETF、主动权益、指数、债券、货币和 QDII 使用各自冻结的 `promotion_scope_key`、正式基准族和结果 head，不互借证据。

两类 scope 都执行 FUND-A08 的 200 个成熟主结果、60 个去重日期、3 个冻结 regime
和前向影子门槛；只有 `POOLED` 执行 5 产品组、40% 与 HHI，
`INSTRUMENT_SPECIFIC` 允许 100% 目标 `canonical_id`。`LONG_TERM_QUALITY` 的周期覆盖只由冻结
`FundRegimeSpec` 的区间、算法、version 和连续段条件判定；基线改进只由成本后
净效用为正、moving-block bootstrap 95% CI 下界非劣、Brier Skill、回撤及
成本压力 guardrail 判定。`TACTICAL_SIGNAL` 即使通过也只能展示“战术信号”，不能
称基金评级；任一适用布尔条件失败即保持 `SHADOW`。
