# 191A AI 债券验收文档

## 1. T1 技术验收

### BOND-A00 原始采集与门控顺序

- [ ] `RawBondIdentityCandidate` 和 `RawBondSnapshot` 的 maturity、terms、prices、
  curve/benchmark 叶子值均可为 `null`，每个叶子仍包含
  `provenance/observed_at/published_at/available_at/retrieved_at`；
- [ ] 测试数据库可证明 raw snapshot 的 append-only 提交发生在 quality gate
  之前；门控和重跑不能覆盖原始内容哈希；
- [ ] `PostGateBondSnapshot` 只在关键字段通过门控后构造；拒绝路径不尝试用必填
  字段模型重新解析 raw 数据；
- [ ] 固定参数化夹具逐一移除普通债到期日、合同、价格、曲线和基准，任务创建/结果
  API 返回正常业务响应而不是 Pydantic 422 或未捕获 500；
- [ ] 上述每个失败夹具均能按 `raw_snapshot_id` 读取原始审计证据，并得到稳定
  `ReasonCode`、`quality_status=REJECTED`、`actionability=INSUFFICIENT_DATA` 及
  `market_view=INDETERMINATE`、`normalized_direction=INDETERMINATE`、
  `recommendation=AVOID`、`trade_intent=NONE`，持仓上下文独立保留；
- [ ] `is_perpetual=true + maturity=null` 保存审计快照并返回
  `quality_status` 为 `ELIGIBLE` 或 `DEGRADED`，
  `actionability=RESEARCH_ONLY/BOND.PERPETUAL_MODEL_REQUIRED`、
  `trade_intent=NONE`，不会退化为普通债定价，也不返回 422/500；
- [ ] GateResult 的 `quality_status` 只接受 `ELIGIBLE/DEGRADED/REJECTED`，
  `actionability` 只接受
  `ACTIONABLE/RESEARCH_ONLY/INSUFFICIENT_DATA/REGION_RESTRICTED`；构造
  `quality_status=RESEARCH_ONLY` 或 `actionability=NONE` 必须失败。

### BOND-A01 身份

- [ ] 同一代码存在两个市场时返回候选，不静默绑定；
- [ ] `candidate_kind=ISSUER` 只能搜索、不能持久化或分析，必须继续选择债项；
- [ ] `bond_identity_kind=ISSUE` 映射 `identity_level=ASSET`，只有跨场所官方估值
  研究时允许 `venue=null`，且强制 `actionability=RESEARCH_ONLY`；
- [ ] `bond_identity_kind=LISTING` 映射 `identity_level=PRODUCT`，本地代码、成交、
  bid/ask 和可执行结果都要求 `venue`；
- [ ] 合格多候选返回 `COMMON.INSTRUMENT_AMBIGUOUS` 并展示可用的 ISIN、市场、
  发行人、债项、币种、到期和票息；来源缺失字段保持 `null + provenance`，不伪造；
- [ ] 已到期/复杂不支持债券保留历史，但方向建议被拒绝。

### BOND-A02 现金流和估值

#### 当前已验证的离线子集（不替代本节全部 T1）

- [x] 固定利率债以冻结的现金流、净价、应计利息、日计数和付息频率计算
  `dirty_price/YTM/modified_duration/convexity/DV01`；零息黄金用例与闭式
  5% YTM、`1/1.05` 修正久期及 DV01 一致，见
  `tests/asset_research/bond/test_valuation.py`；
- [x] 显式 `ACT_365F` 应计及无未来现金流失败均保持 `null + BOND.*` 原因码；
  `ConfiguredAssetResearchPlugin` 仅在来源完整提供冻结估值输入时替换预计算字段，
  并将计算值及原因码写入 `BondResearchDetails`，见
  `tests/asset_research/bond/test_bond_plugin_analytics.py`。

> YTW、可赎回 schedule、跨付息/闰年和全部合同日计数仍未验证，故原始 T1 条目保持未勾选。

- [ ] 固定利率债满足 `clean + accrued = dirty`；
- [ ] 跨付息日、闰年和不同日计数的应计与黄金值一致；
- [ ] YTM、YTW、久期、凸性和 DV01 与独立黄金用例在规定精度内一致；
- [ ] 可赎回债显示 YTW；缺 call schedule 时为 `REJECTED`；
- [ ] 求解失败返回 `null + reason`，不返回 0。

### BOND-A03 数据和质量

- [ ] 估值、曲线和基准属于分析截止时点可用版本；
- [ ] 国债没有公司财务仍可通过；
- [ ] 信用债法定披露过期时禁止 `BUY`；
- [ ] 最后成交过期但当日官方估值有效时只标“估值研究”；
- [ ] 交易和估值均过期时为 `AVOID/INSUFFICIENT_DATA`；
- [ ] 新闻为空只显示覆盖不足，不生成“无负面”。

### BOND-A04 建议

- [ ] 决策结构只含公共四字段，`normalized_direction` 仅为 `LONG/SHORT/NEUTRAL/INDETERMINATE`，无 `BondAction`；
- [ ] 正、负、无优势夹具按 `position_context` 得到规定四元组；
- [ ] 已有多头的 `SELL` 明确为 `REDUCE/CLOSE`，空仓负向候选不得发布 `SELL`；
- [ ] 风险或许可否决得到 `market_view=INDETERMINATE`、
  `normalized_direction=INDETERMINATE`、`recommendation=AVOID`、
  `trade_intent=NONE`，持仓上下文不被写入方向字段；
- [ ] 风险/许可否决同时为 `quality_status=REJECTED`、
  `actionability=INSUFFICIENT_DATA`；地区禁止为
  `actionability=REGION_RESTRICTED` 且优先覆盖其他发布结果；
- [ ] 模型未晋级或仅研究品种的 `quality_status` 为 `ELIGIBLE` 或 `DEGRADED`，
  `actionability=RESEARCH_ONLY`；已晋级且质量合格才为
  `ELIGIBLE + ACTIONABLE`；
- [ ] `position_context=UNKNOWN` 发布层不生成动作，输入 `SHORT` 返回 `COMMON.POSITION_CONTEXT_UNSUPPORTED`；
- [ ] SHADOW 候选层保存真实结果，普通 API/页面/导出/知识库只见 `HOLD/AVOID` 和 `COMMON.MODEL_NOT_PROMOTED`；
- [ ] 仅精确匹配已批准 `promotion_scope_key` 时，普通用户才可见候选方向；
- [ ] 同一快照和版本重放结果及哈希完全相同；
- [ ] 注入相反 LLM 文案不能读取候选层或改变动作、概率或质量。

### BOND-A05 报告和前端

- [ ] 十四个章节完整，重要数值可追溯到来源和日期；
- [ ] 现金流、曲线、久期、信用、流动性和三情景可视化正确；
- [ ] 官方估值旁有不可执行提示；
- [ ] 空、加载、失败和受限来源状态不会渲染虚假 0；
- [ ] 页面、API、Markdown、PDF 和知识库建议一致。

### BOND-A06 结果

- [ ] 可行动候选恰有一个 `bond.executable_total_return` 主预测 head，其目标、标签、
  `target_spec_version/scoreability_rule_version`、
  `probability_model_version/probability_artifact_hash`、
  `calibration_version/calibration_artifact_hash/training_cutoff_at`、
  `baseline_code/baseline_version` 完整，`head_spec_hash` 可复算；
- [ ] `head_spec_hash` 或 target、scoreability、概率/校准 artifact、基线版本不同的
  mixed-spec cohort 被聚合器拒绝，不进入 Brier、基线或晋级分母；
- [ ] `bond.credit_event` 概率与主 head 独立归一；仅估值研究不伪造可执行主 head；
- [ ] 20/60/120 日均按债券市场日历成熟；
- [ ] `bond.executable_total_return`、`bond.valuation_total_return`、`bond.credit_event` 可在同一期限并存且不覆盖；
- [ ] 唯一键为 `(prediction_id, horizon_code, outcome_kind, evaluator_version)`，同版本重跑无重复，新版本只追加；
- [ ] 每个结果头均可按冻结规则得到 `PENDING/PARTIAL/SCORED/UNSCORABLE`，部分现金流事实使用 `PARTIAL`；
- [ ] `MaturityReason` 与 `OutcomeStatus` 分离，提前赎回、到期和正常期限分别记录 `CALL/MATURITY/HORIZON_REACHED`；
- [ ] 跨付息、提前赎回和本金偿还包含真实现金流；
- [ ] 结果扣除点差、佣金、税费和汇率成本；
- [ ] 无可执行价格的估值结果不进入可执行命中率；
- [ ] 成绩单显示成熟数、可评分数、分母、置信区间和分层；
- [ ] 不同期限、评级、久期和流动性不被误合并。

### BOND-A07 调度、截止和幂等

- [ ] 中国债券交易日 19:10 启动且只使用 19:00 前可用数据；
- [ ] 美国债券按纽约时区 18:30/18:15 运行，夏令时正确，许可缺失时任务不注册；
- [ ] 每条 schedule 只绑定一个 `canonical_id`，静态清单展开为多条 schedule，运行时无市场/宇宙扫描；
- [ ] 相同 `run_key` 的重复触发关联既有运行，schedule 版本、触发/截止时间、截止策略或策略版本变化产生新键；
- [ ] `access_principal=owner_scope|coalesce(user_id,"SYSTEM")`；只有相同
  `access_principal + decision_input_hash` 才复用 `prediction_key`；
- [ ] 相同 `owner_scope/decision_input_hash` 但不同 `user_id` 生成不同
  `prediction_key`，不得跨用户复用候选、发布决定或预测；系统影子任务稳定使用
  `SYSTEM` 主体；
- [ ] 同一主体下持仓、快照或任一输入版本变化生成新预测；
- [ ] 历史回补只读取当时 `available_at <= cutoff_at` 的版本，缺失时返回稳定 `COMMON.*` 或 `BOND.*`，不用当前修订补齐。

### BOND-A08 晋级范围和原因码

- [ ] `promotion_scope_key` 来自规范化 `PromotionScope`，包含范围模式、债券分类、
  币种、场所组、久期/信用桶、期限和主 head；策略/模型/校准版本使用注册表独立列；
- [ ] 两类 scope 均至少 200 个成熟可评分行动主头、60 个去重 `cutoff_date`、
  3 个冻结市场状态，并通过 walk-forward、purge/embargo 和 60 个交易日前瞻影子期；
- [ ] 池化范围额外覆盖至少 5 个债项实体组、政府债和信用债、3 个久期桶及
  3 个流动性桶，任一实体组不超过 40% 并报告 HHI；
- [ ] 同一债项跨场所只计一个实体组，不能通过重复上市稀释集中度；
- [ ] 单券范围键包含 `canonical_id`，允许 100% 单券样本但只解锁该券；只有一种
  债券类型、一个久期桶和一个流动性桶的合格单券证据包可以通过，不因缺少池化
  多样性而失败；
- [ ] 池化和单券证据、审批、发布和回退相互隔离；
- [ ] API 通用原因均为稳定 `COMMON.*`、债券专属原因均为 `BOND.*`，中文变化不改变原因码。

## 2. 需求追踪

| 需求 | 验收 |
| --- | --- |
| BOND-FR-001 | BOND-A00、A01 |
| BOND-FR-002 至 005 | BOND-A02、A03 |
| BOND-FR-006 | BOND-A03 |
| BOND-FR-007、011 | BOND-A00、A04 |
| BOND-FR-008 | BOND-A05 |
| BOND-FR-009、010 | BOND-A00、A06 |
| BOND-FR-012 | BOND-A03、总体验收 H 组 |
| BOND-FR-013 | BOND-A04 |
| BOND-FR-014 | BOND-A06 |
| BOND-FR-015 | BOND-A07 |
| BOND-FR-016 | BOND-A08 |
| BOND-FR-017 | BOND-A02 至 A08 |

## 3. 在线冒烟样例

- 境内固定利率国债：验证合同、曲线、官方估值和无公司财务要求；
- 普通信用债：验证评级和法定财务时点；
- 含权债：验证 YTW 和缺条款否决；
- 永续债和到期日未知普通债：分别验证
  `quality_status` 为 `ELIGIBLE` 或 `DEGRADED` 且
  `actionability=RESEARCH_ONLY`，以及
  `REJECTED + INSUFFICIENT_DATA + AVOID/NONE`，且均可回读原始审计快照；
- 故意使用过期报价：验证仅研究或拒绝。

在线结论可随市场变化，只验数据日期、计算恒等式、质量状态和报告一致性。

## 4. T2 模型晋级

模型候选层与发布层分开验收：T1 证明候选计算正确且普通用户看不到候选；T2 才允许精确范围发布。每个 scope 都必须满足 200 个成熟行动主结果头、60 个去重日期、3 个冻结市场状态、时间顺序验证、独立日期和前向影子门槛。

`POOLED` 才额外要求政府债/信用债、至少 3 个久期桶、3 个流动性桶和实体集中度；
`INSTRUMENT_SPECIFIC` 单券明确不套这些多样性条件，允许 100% 来自同一
`canonical_id`，但只能发布到该单券。`bond.executable_total_return` 的成本后含息
净超额为主指标，`bond.credit_event` 的召回和提前预警天数单独报告，不能替代主
head。任一适用门槛不满足时保持 `SHADOW`。
