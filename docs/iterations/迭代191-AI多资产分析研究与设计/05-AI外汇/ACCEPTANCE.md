# 191E AI 外汇验收文档

## 1. T1 技术验收

### FX-A01 身份

#### 当前已验证的离线子集（不替代本节全部 T1）

- [x] FX 结果评分会把显式 `QUOTE_PER_BASE` 与 `BASE_PER_QUOTE` 来源约定归一为
  quote-per-base，并在倒数报价下正确交换/倒数 bid 与 ask；LONG/SHORT 都不取 mid，
  非相关约定或 crossed quote 返回稳定 `FX.*` 原因码，见
  `tests/asset_research/fx/test_fx_quotes.py` 与
  `tests/asset_research/fx/test_fx_outcome_evaluator.py`。

> 真实纽约切日、双货币日历、NDF/forward 价值日与跨源对账仍未完成，原始 T1 条目保持未勾选。

- [ ] `ASSET/PRODUCT/CONTRACT` 身份层级分别覆盖参考货币对、场所即期和远期/NDF，产品级与合约级身份缺场所、报价/结算币或日历时拒绝；
- [ ] EUR/USD 和 USD/EUR 的方向、收益符号正确；
- [ ] CNY/CNH 不合并；
- [ ] spot、forward、NDF、FX swap、future、CFD 为不同 ID；
- [ ] 裸代码不静默选择 dealer 或杠杆产品。

### FX-A02 会话

- [ ] 夏令时/冬令时均在纽约 17:00 正确切日；
- [ ] 北京 19:00 报告不读取未完成日线；
- [ ] 周末显示 CLOSED 而非过期；
- [ ] 双货币节假日和价值日按产品日历；
- [ ] 所有结果保存 UTC、session date 和 alignment timezone。

### FX-A03 数据和质量

- [ ] 缺 bid/ask 强制 REJECTED，不用 mid 生成可执行建议；
- [ ] 参考汇率只作交叉检查；
- [ ] 宏观/COT/新闻缺失降级且不补 0；
- [ ] 修订 CPI 等不回灌旧预测；
- [ ] 异常 spread 和交叉源偏差按货币层级门控。

### FX-A04 建议和合规

- [ ] `normalized_direction` 只接受
  `LONG/SHORT/NEUTRAL/INDETERMINATE`，且方向明确 base/quote；
- [ ] `position_context` 只接受 `FLAT/LONG/SHORT/UNKNOWN`，
  `trade_intent` 只接受 `OPEN/ADD/REDUCE/CLOSE/KEEP/NONE`，
  `recommendation` 只接受 `BUY/SELL/HOLD/AVOID`；
- [ ] 持仓上下文正确生成平多/平空/维持矩阵；
- [ ] 空仓 `SHORT` 仅在 `short_open_research_allowed=true` 时为
  `trade_intent=OPEN`，否则为 `NONE`；中国大陆固定为 `NONE`；
- [ ] 中国大陆模式无方向开关绕过、开户链接、API key、订单或杠杆；
- [ ] 地区限制精确返回
  `market_view=INDETERMINATE`、`normalized_direction=INDETERMINATE`、
  `recommendation=AVOID`、`trade_intent=NONE`、
  `actionability=REGION_RESTRICTED` 和 `FX.REGION_RESTRICTED`；
- [ ] LLM 不能改写结构化动作。

### FX-A05 候选和 SHADOW 发布

- [ ] `candidate_decision_json` 使用公共枚举并可供授权评估器评分；
- [ ] `SHADOW/SUSPENDED/未登记` 时普通用户只收到
  `market_view=INDETERMINATE`、`normalized_direction=INDETERMINATE`、
  `actionability=RESEARCH_ONLY`、`recommendation=HOLD/AVOID`、
  `trade_intent=NONE`；
- [ ] 普通用户 API、页面、浏览器状态、报告、导出和知识库均不包含候选方向、
  概率或预期收益；
- [ ] 精确 `promotion_scope_key` 未处于 `PROMOTED` 时返回
  `COMMON.MODEL_NOT_PROMOTED`；
- [ ] 管理员权限撤销后不能读取历史候选字段。

### FX-A06 报告和页面

- [ ] 十一个章节、来源和 cutoff 完整；
- [ ] 盘中报告显示未使用完整日线；
- [ ] dealer/venue、spread、financing 和结算风险可见；
- [ ] 页面、API、导出和知识库一致。

### FX-A07 多 head 结果

- [ ] LONG 使用 ask→bid，SHORT 使用 bid→ask；
- [ ] 1/5/20 个真实会话和周末跳转正确；
- [ ] spread、滑点、佣金和 roll/financing 完整；
- [ ] `normalized_direction=NEUTRAL` 与行动命中率分开；
- [ ] 同一预测/期限分别存在 `fx.direction_pnl`、`fx.action_utility`、
  `fx.risk_path`，且唯一键为
  `(prediction_id,horizon_code,outcome_kind,evaluator_version)`；
- [ ] 每个 head 只使用
  `OutcomeStatus.PENDING/PARTIAL/SCORED/UNSCORABLE`，正常到期另记
  `MaturityReason.HORIZON_REACHED`，不存在 `MATURED` 状态；
- [ ] `OutcomeStatus.PARTIAL`、`OutcomeStatus.UNSCORABLE` 不进入指标分母，
  原因使用公共 `FX.*`
  `ReasonCode`；
- [ ] 按 pair、horizon、regime 和版本展示样本、分母和区间。

### FX-A08 日批次、补跑和幂等

- [ ] 审批清单在配置阶段展开为单资产 schedule，运行时没有市场扫描；
- [ ] `America/New_York` 夏/冬令时均在 17:00 cutoff、17:10 启动；
- [ ] 相同 `schedule_id/schedule_version/scheduled_fire_at/cutoff_at/
  cutoff_policy_version/policy_version` 重复或并发触发只有一个 `run_key`；
- [ ] 17:25、18:10 重试和 20:00 对账只补该 schedule 的失败运行；
- [ ] 服务重启 catch-up 复用原 cutoff，任何
  `available_at > analysis_cutoff_at` 的数据均不进入预测；
- [ ] 相同 `decision_input_hash` 只生成一个不可变 `prediction_key`，任一冻结输入变化
  生成新预测，最终失败仍保留尝试和原因证据；
- [ ] `fx.direction_pnl` 主 head 的 target/scoreability 版本、标签、bid/ask/carry
  及 no-trade band、模型与校准 artifact、training cutoff、基线版本和概率完整且唯一；
- [ ] 不同 `head_spec_hash` 的记录不能混入同一 Brier 或晋级 cohort。

### FX-A09 晋级作用域

- [ ] `promotion_scope_key` 是规范化 `PromotionScope` 的 SHA-256，固定资产、
  产品/样本池、`signal_head` 和期限，版本列独立进入唯一约束；
- [ ] `INSTRUMENT_SPECIFIC` 只使用目标 pair，至少 200 条成熟行动信号；
- [ ] `POOLED` 至少 5 个 pair、每个至少 20 条、总计至少 200 条，单 pair
  不超过 40%；
- [ ] spot/forward/NDF/CFD、CNY/CNH 不跨池；
- [ ] 池级、单品种、相邻期限或新模型不能继承其他 key 的晋级状态。

## 2. 需求追踪

| 需求 | 验收 |
| --- | --- |
| FX-FR-001 | FX-A01 |
| FX-FR-002 | FX-A02 |
| FX-FR-003 至 007 | FX-A03 |
| FX-FR-008、012 | FX-A04 |
| FX-FR-013 | FX-A05 |
| FX-FR-009 | FX-A06 |
| FX-FR-010、011 | FX-A07、A09 |
| FX-FR-014 | FX-A08 |

## 3. 在线冒烟

- EUR/USD：主要货币、双边价和日线；
- USD/JPY：验证方向和小数精度；
- USD/CNY 与 USD/CNH：验证身份和地区差异；
- 周末/节假日时点；
- 缺远期点和过期宏观的降级用例。

## 4. T2 晋级补充

货币对和期限按完整 `promotion_scope_key` 分别晋级，至少覆盖趋势、震荡和风险事件状态。
成本必须含双边 spread 和 roll；仅用参考汇率或 mid 的回测不接受。

- `INSTRUMENT_SPECIFIC`：该货币对独立达到至少 200 条
  `OutcomeStatus.SCORED` 行动信号；
- `POOLED`：满足 FX-A09 的多样性规则，并同时报告聚合、各 pair 和最差充分样本切片；
- 三个评价 head 分别报告样本、覆盖、校准、净效用和风险，不用一个 head 的通过替代另一个；
- 至少完成 60 个真实 FX session 的每日影子运行，调度缺口和失败补跑有审计证据；
- 大陆方向能力还需要独立法律批准，即使模型 T2 通过也不自动开放。
