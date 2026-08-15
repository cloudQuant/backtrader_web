# 191E AI 外汇实施计划

> 前置条件：P0 公共底座、地区合规能力和合法双边数据可用。若 Gate 未通过，仅允许
> 固定夹具、纯函数和 fail-closed 契约实现；不得启用 provider capability、接入真实来源、
> 创建真实影子调度、宣称 T1 可验收或公开方向性建议。

## 1. 文件所有权

```text
src/backend/app/services/asset_research/plugins/fx/
├── __init__.py
├── identity.py
├── calendar.py
├── quotes.py
├── macro.py
├── carry.py
├── features.py
├── quality.py
├── policy.py
├── compliance.py
├── publishing.py
├── scheduling.py
├── promotion.py
├── report.py
└── outcomes.py
src/backend/tests/asset_research/fx/
├── test_identity.py
├── test_calendar.py
├── test_quotes.py
├── test_point_in_time.py
├── test_quality.py
├── test_policy.py
├── test_compliance.py
├── test_publishing.py
├── test_scheduling.py
├── test_promotion.py
├── test_outcomes.py
└── test_api.py
src/frontend/src/components/asset-analysis/panels/FxPanel.vue
src/frontend/src/__tests__/asset-analysis/FxPanel.test.ts
```

## 1.1 任务依赖、并行条件与公共契约冻结点

本节只描述可验证产物之间的实施门槛，不要求在数据库、API 或任务模型中增加任务依赖
字段。外汇资产线只等待所列公共契约、合法数据与合规能力，不等待其他资产插件完成。

公共冻结点：

- `C1 身份与插件`：`AssetResearchPlugin` 方法签名、公共资产类型、产品身份、
  `canonical_id` 和 `identity_version`；
- `C2 证据与时点`：`RawObservation/RawAssetSnapshot`、来源注册、宏观 vintage、
  内容哈希和四类时点语义；
- `C3 质量与决策`：`GateResult`、公共枚举、`ReasonCode`、`ResearchDecision`、
  地区门控、候选/发布隔离和 `access_principal`；
- `C4 预测与结果`：`PredictionHead`、`HorizonSpec`、结果唯一键、`OutcomeStatus`、
  `MaturityReason` 和 `head_spec_hash`；
- `C5 调度与幂等`：schedule/run/prediction 生命周期、cutoff、租约、
  `run_key/decision_input_hash/prediction_key`；
- `C6 发布与晋级`：模型状态机、`PromotionScope`、报告/导出/知识库发布边界和审计。

| 任务 | 最小前置产物 | 可并行条件 | 开始前必须冻结 |
| --- | --- | --- | --- |
| 1 身份和日历 | P0 身份插件骨架、公共日历接口可用 | 产品身份与联合日历夹具可并行，汇合前冻结价值日语义 | `C1`、`C2` 的时点语义 |
| 2 行情和宏观 | 任务 1 的 pair/product 身份及日历 cutoff | venue 报价、参考源和宏观 vintage 适配器可并行；均写同一 raw envelope | `C1`、`C2` |
| 3 特征和质量 | 任务 2 的双边报价/宏观可空 Schema | 特征族和质量原因码可用冻结夹具并行，集成等待 freshness 矩阵 | `C3` |
| 4 策略和合规 | 公共地区能力、任务 1 的产品分类、任务 3 的可空特征 | 地区真值表与策略纯函数可并行，发布前统一 fail-closed 验证 | `C3` |
| 5 候选和发布 | 任务 4 的 GateResult 与策略输出 | API、报告和知识库过滤器可并行，共用 published decision 夹具 | `C3`、`C6` |
| 6 报告和页面 | 任务 5 的 published decision 与报告 envelope | 前后端在 DTO、证据 ID 冻结后并行 | `C3`、`C6` |
| 7 多 head 结果 | 任务 2 的 point-in-time 双边报价、任务 4 的成本/动作口径 | 各 horizon/outcome 评估器可并行，共用 head spec 黄金夹具 | `C4` |
| 8 调度和补跑 | 任务 1 的日历、任务 2 的 cutoff 数据、任务 5 的安全发布 | scheduler 可与任务 6/7 并行；启用前统一验证并发幂等和历史可见性 | `C5` |
| 9 晋级作用域 | 任务 7 的成熟结果、任务 8 的连续 SHADOW 证据 | pooled/specific scope 证据可并行，状态切换等待全部门槛 | `C4`、`C6` |

## 2. 任务

### 任务 1：身份和日历

- [ ] 先写 base/quote、CNY/CNH、spot/forward/NDF/CFD 分离测试；
- [ ] 建立规范 ID、价值日、结算和联合日历；
- [ ] 实现纽约 17:00 夏/冬令时和北京时间盘中语义；
- [ ] 周末/节假日不误报 stale。

### 任务 2：行情和 point-in-time 宏观

- [ ] 接入双边 venue 报价、完整 bar 和独立参考源；
- [ ] 接入政策、曲线、宏观和实际远期点；
- [ ] 保存宏观 vintage、COT 发布和新闻时点；
- [ ] 实现价格方向和交叉源校验。

### 任务 3：特征和质量

- [ ] 实现宏观、carry、估值、趋势、波动和微观结构；
- [ ] 实现主要/次要/新兴货币的版本化阈值；
- [ ] 覆盖未完成 bar、无 bid/ask、宏观缺失和异常 spread；
- [ ] 缺失值不补 0。

### 任务 4：策略和合规

- [ ] 只使用公共 `normalized_direction=LONG/SHORT/NEUTRAL/INDETERMINATE`、
  `position_context`、`trade_intent` 和 `recommendation` 枚举；
- [ ] 用 `short_open_research_allowed` 决定空仓 `SHORT` 的
  `trade_intent=OPEN/NONE`，中国大陆固定为 `NONE`；
- [ ] 成本后预期回报和概率由结构化策略产生；
- [ ] 实现服务端地区/产品能力门控；
- [ ] 地区限制固定
  `INDETERMINATE + AVOID + NONE + REGION_RESTRICTED`，原因码为
  `FX.REGION_RESTRICTED`；
- [ ] 确保无开户链接、API key、杠杆和订单路径。

### 任务 5：候选信号和安全发布

- [ ] 分离不可变 `candidate_decision_json` 与 `published_decision_json`；
- [ ] `SHADOW/SUSPENDED/未登记` 时普通用户只收到
  `market_view=INDETERMINATE`、`normalized_direction=INDETERMINATE`、
  `actionability=RESEARCH_ONLY`、`recommendation=HOLD/AVOID`、
  `trade_intent=NONE`；
- [ ] 候选方向、概率、预期收益只对影子评估器和授权管理员开放；
- [ ] 未晋级使用 `COMMON.MODEL_NOT_PROMOTED`，数据过期和许可阻断分别使用
  `COMMON.DATA_STALE`、`COMMON.SOURCE_LICENSE_BLOCKED`；
- [ ] API、页面、报告、导出和知识库只消费发布决定；
- [ ] 使用公共 `ReasonCode` 注册表中的 `FX.*` 稳定码，禁止自由文本原因码。

### 任务 6：报告和页面

- [ ] 实现十一个章节、base/quote、宏观、carry、事件和成本；
- [ ] 盘中/日终状态醒目展示；
- [ ] 历史成绩单按 pair/horizon/regime 分层；
- [ ] 验证导出和证据一致。

### 任务 7：多 head 结果

- [ ] 实现 ask→bid、bid→ask 和 1/5/20 会话；
- [ ] 计入融资/roll 和实际时段；
- [ ] 覆盖周末、节假日、缺退出报价和修订数据；
- [ ] 为 `fx.direction_pnl`、`fx.action_utility`、`fx.risk_path` 独立落结果；
- [ ] 增加唯一键
  `(prediction_id,horizon_code,outcome_kind,evaluator_version)`；
- [ ] 只使用公共
  `OutcomeStatus=PENDING|PARTIAL|SCORED|UNSCORABLE`，正常到期单列
  `MaturityReason.HORIZON_REACHED`，不得使用 `MATURED` 状态；
- [ ] 每个 head 独立成熟、失败和计分，只有 `SCORED` 进入相应指标分母。

### 任务 8：每日影子调度和补跑

- [ ] 将审批静态清单配置时展开为单资产 schedule，禁止运行时扫描市场；
- [ ] 使用 `America/New_York` 在有效会话 17:00 冻结 cutoff、17:10 启动；
- [ ] 冻结 `schedule_version/cutoff_policy_version`，建立唯一 `run_key` 和
  `decision_input_hash/prediction_key`；
- [ ] 17:25、18:10 重试失败项，20:00 对账，重启后在下一 cutoff 前 catch-up；
- [ ] 所有补跑复用原 cutoff，拒绝 `available_at > cutoff` 的数据；
- [ ] 重复触发、并发触发和补跑只产生一条预测，最终失败保留 `FX.*` 原因码。

### 任务 9：晋级作用域

- [ ] 注册 `fx.direction_pnl` 主 `PredictionHead` 的目标、标签、
  target/scoreability 版本、bid/ask/carry/no-trade band、模型与校准 artifact、
  training cutoff、基线版本和 `head_spec_hash`；
- [ ] 不同 `head_spec_hash` 的 cohort 拒绝混算和事后改标签；
- [ ] 将公共 `PromotionScope` 规范化后计算 `promotion_scope_key`，固定资产、
  产品/样本池、`signal_head` 和期限；版本列独立参与注册表唯一约束；
- [ ] `INSTRUMENT_SPECIFIC` 以单一货币对至少 200 条成熟行动信号验收；
- [ ] `POOLED` 仅合并同产品/成本/特征/策略，至少 5 个货币对、每个 20 条、
  总计 200 条且单一货币对不超过 40%；
- [ ] 禁止 spot/forward/NDF/CFD 互池，禁止用 CNY 样本替代 CNH；
- [ ] 在批准地区进入 `SHADOW`，只有精确 scope 通过 T2 才可切换
  `PROMOTED`。

## 3. 测试命令

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base pytest -q \
  tests/asset_research/fx
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base ruff check \
  app/services/asset_research/plugins/fx \
  tests/asset_research/fx

cd ../../src/frontend
npm run typecheck
npm run test -- --run src/__tests__/asset-analysis/FxPanel.test.ts
```

## 4. 退出条件

- [ ] FX-FR-001 至 014 全部实现；
- [ ] [验收文档](./ACCEPTANCE.md)T1 全部通过；
- [ ] 地区与数据许可登记完成；
- [ ] 中国大陆方向建议开关默认关闭；
- [ ] 全球允许地区仍先运行 `SHADOW`，且普通用户不可见候选方向；
- [ ] 日批次幂等、补跑、多 head 评分和两种晋级 scope 均有自动化证据。
