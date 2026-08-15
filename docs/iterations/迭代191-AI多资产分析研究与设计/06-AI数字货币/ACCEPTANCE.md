# 191F AI 数字货币验收文档

## 1. T1 技术验收

### CRYPTO-A01 身份

- [ ] 裸资产、现货/永续产品和有到期日的交割合约分别使用 `ASSET/PRODUCT/CONTRACT`，产品级与合约级身份缺场所、报价/结算资产或规则时拒绝；
- [ ] 同 ticker 不同 chain/contract 不合并；
- [ ] BTC/USD、BTC/USDT、spot、linear perpetual、inverse perpetual 和 delivery future 分别建档；
- [ ] 裸 BTC 返回资产级研究，不能静默选永续；
- [ ] linear/inverse 的结算币和 P&L 正确。

### CRYPTO-A02 时间和行情

- [ ] UTC 00:00 切日和 00:10 批次正确；
- [ ] 北京 19:10 不读取未完成日线；
- [ ] CME 产品使用自身日历；
- [ ] candle gap、序列丢失、维护和停牌可检测；
- [ ] 跨 venue 异常价和过期数据触发拒绝。

### CRYPTO-A03 质量

#### 当前已验证的离线子集（不替代本节全部 T1）

- [x] 多个独立 venue 的冻结 bid/ask 和 1% 深度生成深度加权合成价；单 venue 显式产生
  `CRYPTO.SINGLE_VENUE_REFERENCE`，不能冒充复合价，见
  `tests/asset_research/crypto/test_crypto_market_quality.py`；
- [x] USDT/USDC 报价使用明确的 USD 参考率并计算脱锚 bps，超过冻结阈值时插件为
  `REJECTED + CRYPTO.STABLECOIN_DEPEG`；结果事实和原因码会写入
  `CryptoResearchDetails`，见
  `tests/asset_research/crypto/test_crypto_plugin_market_quality.py`。

> 链上 provider、停机/断档、永续清算路径与真实 venue 许可仍未完成，原始 T1 条目保持未勾选。

- [ ] 复合价至少两个独立 venue，单 venue 明确标注；
- [ ] USDT/USDC 脱锚后不按 1:1；
- [ ] 1% 深度不足时即使方向分高也拒绝；
- [ ] 链上不支持显示 UNSUPPORTED，不填 0；
- [ ] 新上市、迁移、供给异常和交易暂停正确降级/拒绝。

### CRYPTO-A04 衍生品

- [ ] 清算分析明确标记 `STANDARDIZED_RESEARCH`，不读取账户或声称用户实际仓位；
- [ ] 情景冻结 side、quantity/notional、leverage、margin mode、collateral、
  initial/maintenance margin、risk tier、公式版本、mark source/path 和规则
  `available_at`；
- [ ] 正 funding 的 long 正确扣费，负 funding 方向相反；
- [ ] 到期后在允许延迟窗口内缺 funding 为
  `OutcomeStatus.PARTIAL`；超过最终化 SLA 为
  `OutcomeStatus.UNSCORABLE + CRYPTO.FUNDING_UNAVAILABLE`；
- [ ] mark/index 不作为默认成交价；
- [ ] 冻结情景在真实 mark path 触发清算时记录 `LIQUIDATED` 和完整情景损失；
- [ ] 缺任一情景/场所规则字段时为
  `UNSCORABLE + CRYPTO.LIQUIDATION_SCENARIO_INCOMPLETE`，不补默认杠杆；
- [ ] 到期不静默续到另一合约。

### CRYPTO-A05 动作和合规

- [ ] `normalized_direction` 只接受
  `LONG/SHORT/NEUTRAL/INDETERMINATE`，`position_context` 只接受
  `FLAT/LONG/SHORT/UNKNOWN`；
- [ ] `trade_intent` 只接受 `OPEN/ADD/REDUCE/CLOSE/KEEP/NONE`，
  `recommendation` 只接受 `BUY/SELL/HOLD/AVOID`；
- [ ] 现货 SELL 不变成裸空；
- [ ] 永续 SHORT 与现货 SELL 分开；空仓衍生品 SHORT 仅在
  `short_open_research_allowed=true` 时为 `trade_intent=OPEN`，中国大陆固定
  `NONE`；
- [ ] 大陆模式精确返回
  `market_view=INDETERMINATE`、`normalized_direction=INDETERMINATE`、
  `recommendation=AVOID`、`trade_intent=NONE`、
  `actionability=REGION_RESTRICTED` 和 `CRYPTO.REGION_RESTRICTED`；
- [ ] 修改前端地区、请求体或路由不能绕过；
- [ ] 页面、API、导出均无 BUY/SELL 概率、开户链接、API key、托管和订单；
- [ ] LLM 不能建议绕过或提供杠杆。

### CRYPTO-A06 候选和 SHADOW 发布

- [ ] `candidate_decision_json` 使用公共枚举，并只在批准隔离环境写入；
- [ ] `SHADOW/SUSPENDED/未登记` 时普通用户固定
  `market_view=INDETERMINATE`、`normalized_direction=INDETERMINATE`、
  `trade_intent=NONE`、`actionability=RESEARCH_ONLY` 和
  `recommendation=HOLD/AVOID`；
- [ ] 普通用户 API、页面、浏览器状态、报告、导出和知识库均不包含候选方向、
  概率或预期收益；
- [ ] 精确 `promotion_scope_key` 未处于 `PROMOTED` 时返回
  `COMMON.MODEL_NOT_PROMOTED`；
- [ ] 地区限制优先于 `PROMOTED`，管理员权限撤销后不能读取候选字段。

### CRYPTO-A07 报告和多 head 结果

- [ ] 十二章节、风险、来源、cutoff、资产和产品身份完整；
- [ ] 现货结果含 bid/ask、fee、slippage 和 quote 换算；
- [ ] 永续结果另含每期 funding；
- [ ] 24h/7d/30d 成熟正确；
- [ ] 现货包含 `crypto.spot_pnl`、`crypto.benchmark_excess`、
  `crypto.risk_path`，衍生品包含 `crypto.derivative_pnl`、
  `crypto.liquidation_risk`、`crypto.risk_path`；
- [ ] `crypto.liquidation_risk` 的场所、产品、情景 JSON、规则快照哈希和
  `SURVIVED/LIQUIDATED` 标签可重放，页面固定显示非实际仓位提示；
- [ ] 唯一键为
  `(prediction_id,horizon_code,outcome_kind,evaluator_version)`；
- [ ] 每个 head 只使用
  `OutcomeStatus.PENDING/PARTIAL/SCORED/UNSCORABLE`；到期另记
  `MaturityReason.HORIZON_REACHED/EXPIRY/ROLL/DELISTING`，不存在
  `MATURED` 状态；
- [ ] `OutcomeStatus.PARTIAL`、`OutcomeStatus.UNSCORABLE` 不进入分母，
  缺口原因使用公共
  `CRYPTO.*` `ReasonCode`；
- [ ] venue/product/horizon 分组显示分母、区间、校准和回撤；
- [ ] API、页面和允许的导出内容一致。

### CRYPTO-A08 日批次、补跑和幂等

- [ ] 审批清单在配置阶段展开为单产品 schedule，运行时没有市场扫描；
- [ ] 每个 UTC 自然日 00:00 cutoff、00:10 启动，24×7 无本地时区漂移；
- [ ] 相同 `schedule_id/schedule_version/scheduled_fire_at/cutoff_at/
  cutoff_policy_version/policy_version` 重复或并发触发只有一个 `run_key`；
- [ ] 00:25、01:10 重试和 03:00 对账只补该 schedule 的失败运行；
- [ ] 重启 catch-up 复用原 cutoff，`available_at/finalized_at > cutoff` 的数据不进入
  旧预测；
- [ ] 相同 `decision_input_hash` 只生成一个不可变 `prediction_key`，冻结输入变化
  生成新预测，维护和最终失败保留尝试证据；
- [ ] 标准风险情景、margin tier、清算公式或 mark path rule 版本变化会改变
  `asset_risk_scenario_snapshot_hash` 并生成新预测；
- [ ] 北京 19:10 快照不进入 UTC 日批次 cohort 或 T2 分母。
- [ ] 产品级只有一个主预测 head，target/scoreability 版本、标签、P&L/成本 band、
  模型与校准 artifact、training cutoff、基线版本和概率完整；资产级研究 head 列表为空；
- [ ] venue/product/quote、风险情景或 `head_spec_hash` 不同的记录不能混入同一
  Brier 或晋级 cohort。

### CRYPTO-A09 晋级作用域

- [ ] `promotion_scope_key` 是规范化 `PromotionScope` 的 SHA-256，固定资产、
  venue/product/quote 样本池、`signal_head` 和期限，版本列独立进入唯一约束；
- [ ] `INSTRUMENT_SPECIFIC` 只使用目标产品，至少 200 条成熟行动信号；
- [ ] `POOLED` 至少 5 个产品、每个 20 条、总计 200 条且单一产品不超过 40%；
- [ ] spot/perpetual/delivery、linear/inverse、法币/稳定币报价不跨池；
- [ ] 聚合、每个充分样本产品和最差风险切片分别报告；
- [ ] venue、产品、期限或版本不同的 key 不能继承晋级。

## 2. 需求追踪

| 需求 | 验收 |
| --- | --- |
| CRYPTO-FR-001、002 | CRYPTO-A01 |
| CRYPTO-FR-003、004 | CRYPTO-A02、A03 |
| CRYPTO-FR-005 | CRYPTO-A04 |
| CRYPTO-FR-006 至 008 | CRYPTO-A03、A07 |
| CRYPTO-FR-009、012 | CRYPTO-A05 |
| CRYPTO-FR-013 | CRYPTO-A06 |
| CRYPTO-FR-010、011 | CRYPTO-A07 |
| CRYPTO-FR-014 | CRYPTO-A08、A09 |

## 3. 在线冒烟

仅在批准环境运行：

- BTC/USD 现货与 BTC/USDT 现货；
- 同一场所线性与反向永续；
- 同 ticker 跨链代币；
- 稳定币脱锚固定夹具；
- 低深度、维护、缺 funding 和链上不支持样例；
- 中国大陆地区拒绝样例。

## 4. T2 晋级和发布 Gate

- 现货、永续、交割按完整 `promotion_scope_key` 分开晋级；
- 至少连续 90 个自然日前瞻影子数据；
- 成本、funding、标准化清算情景、稳定币和场所失败均纳入；
- `INSTRUMENT_SPECIFIC` 独立达到至少 200 条
  `OutcomeStatus.SCORED` 行动信号；
- `POOLED` 满足 CRYPTO-A09 的产品多样性，且聚合、充分样本产品和最差风险切片均
  不劣于基线；
- 各 `outcome_kind` 分别报告样本、覆盖、校准、净效用和风险，不能用一个 head
  的通过替代另一个；
- 90 日 UTC 调度完整性、失败补跑和幂等审计通过；
- 法律 Gate 与模型 T2 是两个独立必需条件；
- 中国大陆未取得书面批准时，即使 T2 通过也不开放公众方向建议。
