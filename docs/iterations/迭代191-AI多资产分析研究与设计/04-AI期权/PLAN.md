# 191D AI 期权实施计划

> 前置条件：P0、期货合约日历公共能力完成；取得完整历史期权链和双边报价。若 Gate
> 未通过，仅允许固定夹具、纯函数和 fail-closed 契约实现；不得启用 provider capability、
> 接入真实来源、创建真实影子调度、宣称 T1 可验收或公开方向性建议。

## 1. 文件所有权

```text
src/backend/app/services/asset_research/plugins/option/
├── __init__.py
├── identity.py
├── chain.py
├── collector.py
├── pricing.py
├── surface.py
├── greeks.py
├── quality.py
├── policy.py
├── guards.py
├── report.py
└── outcomes.py
src/backend/tests/asset_research/option/
├── test_identity.py
├── test_pricing.py
├── test_surface.py
├── test_quality.py
├── test_guards.py
├── test_policy.py
├── test_outcomes.py
└── test_api.py
src/frontend/src/components/asset-analysis/panels/OptionPanel.vue
src/frontend/src/__tests__/asset-analysis/OptionPanel.test.ts
```

## 1.1 任务依赖、并行条件与公共契约冻结点

本节只描述可验证产物之间的实施门槛，不要求在数据库、API 或任务模型中增加任务依赖
字段。期权只依赖公共的期货合约日历契约，不等待期货插件整体完成；日历契约冻结后可与
期货资产任务并行。

公共冻结点：

- `C1 身份与插件`：`AssetResearchPlugin` 方法签名、公共资产类型、精确 CONTRACT
  `canonical_id/identity_version`；
- `C2 证据与时点`：`RawObservation/RawAssetSnapshot`、来源注册、内容哈希和
  `observed_at/published_at/available_at/retrieved_at` 语义；
- `C3 质量与决策`：`GateResult`、公共枚举、`ReasonCode`、`ResearchDecision`、
  `CanonicalOptionPositionContext`、候选/发布隔离和 `access_principal`；
- `C4 预测与结果`：`PredictionHead`、`HorizonSpec`、结果唯一键、`OutcomeStatus`、
  `MaturityReason` 和 `head_spec_hash`；
- `C5 调度与幂等`：schedule/run/prediction 生命周期、cutoff、租约、固定
  CONTRACT 身份及 `run_key/decision_input_hash/prediction_key`；
- `C6 发布与晋级`：模型状态机、`PromotionScope`、报告/导出/知识库发布边界和审计。

| 任务 | 最小前置产物 | 可并行条件 | 开始前必须冻结 |
| --- | --- | --- | --- |
| 1 身份和链 | P0 身份插件骨架、公共期货合约日历契约 | 链采集与审批 manifest 夹具可并行；不等待期货插件其他任务 | `C1`、`C2` |
| 2 估值和 Greeks | 任务 1 的精确 CONTRACT 身份、双边报价 Schema | 三类定价模型和 solver 黄金测试可并行，共用冻结输入 envelope | `C2`、`C4` 的 observation/neutral-band 口径 |
| 3 曲面和质量 | 任务 2 的 IV/Greeks 可空输出 | 静态套利检查与报价质量门控可并行，拟合集成等待 solver 原因码 | `C3` |
| 4 策略和裸卖保护 | 任务 1 的精确身份、任务 2/3 的风险输出、公共持仓快照契约 | 持仓规范化、真值表和数据库保护可并行，发布前做端到端 fail-closed 验证 | `C3` |
| 5 报告和页面 | 任务 4 的 published decision 与报告 envelope | 链/Greeks/盈亏组件可在 DTO 和证据 ID 冻结后并行 | `C3`、`C6` |
| 6 结果 | 任务 1 的精确合约、任务 2 的 solver/价格、任务 4 的成本与动作口径 | 三个 head 和四类 outcome 评估器可并行，共用 exact-contract 黄金夹具 | `C4` |
| 7 head、调度和晋级 | 任务 1/4 的精确身份与安全发布；晋级另等待任务 6 | 固定合约 scheduler 可与任务 5/6 并行，晋级状态切换等待成熟结果 | `C4`、`C5`、`C6` |

## 2. 任务

### 任务 1：精确身份和链

- [ ] 先写 call/put、到期、行权价、欧/美式和未知字段测试；
- [ ] 扩展现有期权链适配器，加入规范身份、时点和覆盖；
- [ ] 同步标的、合约和相邻到期；
- [ ] 裸标的交互输入只返回候选，不自动选合约；
- [ ] selector 只在配置阶段对冻结链解析，以 stable tie-break 产出审批 manifest，并
  展开为每个 canonical 精确合约一条 v1 CONTRACT schedule；运行器不含选约接口。

### 任务 2：估值和 Greeks

- [ ] 为 Black-76、BSM 和美式模型编写黄金测试；
- [ ] 实现精确合约 bid/ask IV solver、Greeks、盈亏平衡和最大损失，冻结 solver、
  day-count、模型输入和缺失/不收敛原因；
- [ ] 锁定 QuantLib/py_vollib 版本并记录模型输入；
- [ ] 求解失败返回稳定原因。

### 任务 3：曲面和质量

- [ ] 实现价格边界、parity、单调、凸性和日历套利检查；
- [ ] 实现报价年龄、同步、价差、深度和链覆盖；
- [ ] 只在支持区间内拟合/展示；
- [ ] 实现全部拒绝和降级规则。

### 任务 4：策略和裸卖保护

- [ ] 分别计算标的、IV、合约 edge 和风险；
- [ ] 只保存公共方向、建议、持仓和意图，派生 BUY_TO_OPEN/SELL_TO_CLOSE 标签；
- [ ] 对同一 `canonical_id/identity_version` 合约聚合出的
  `long_quantity=0` 且 `short_quantity=0`，必须规范化为
  `position_context=FLAT`，不得落为 `UNKNOWN`、`LONG` 或 `SHORT`；
- [ ] 建立 append-only exact `CanonicalOptionPositionContext`，冻结
  `position_context_snapshot_id/content_hash`、`owner_scope/user_id/access_principal`、
  `identity_level=CONTRACT`、canonical ID/identity version、数量和 cutoff 有效区间；
- [ ] task、run、prediction 与 position snapshot 的 owner/user/access principal 必须
  逐字段全等；无 snapshot、跨用户/owner、跨合约、cutoff 后可见或过期均为 UNKNOWN，
  不得 CLOSE；
- [ ] guard 接收完整 `ResearchDecision` 和精确持仓上下文，逐项测试
  `FLAT+LONG=BUY+OPEN`、`LONG+LONG=HOLD+KEEP`、
  `LONG+NEUTRAL=SELL+CLOSE`、`FLAT+NEUTRAL=HOLD+NONE`、
  `UNKNOWN+LONG=BUY+NONE`、`UNKNOWN+NEUTRAL=HOLD+NONE`；
- [ ] 验收测试必须从同一合约的原始 `long_quantity=0/short_quantity=0` 构造持仓快照，
  先断言规范化结果为 `FLAT`，再断言
  `FLAT+NEUTRAL=HOLD+NONE` 且不产生 CLOSE 或裸卖路径；
- [ ] SHORT context/direction、`SELL + OPEN`、无有效 LONG context 的 CLOSE 和白名单外
  元组统一 fail-closed 为 `INDETERMINATE + AVOID + NONE`，并在 Schema、服务、数据库
  三层拒绝；
- [ ] prediction 的 `position_context_snapshot_id` 以 `ON DELETE RESTRICT` 外键引用
  `asset_position_context_snapshots`；实现行级 LONG/CLOSE 非空 FK CHECK、跨表约束
  trigger 和快照不可变约束，并在真实 MySQL 验证发布行为；SQLite 仅验证本地等价回归；
- [ ] 内部候选可产生 BUY/SELL，SHADOW 普通用户发布决定固定为 HOLD/AVOID；
- [ ] 断言 LLM 和前端参数均不能绕过。

### 任务 5：报告和页面

- [ ] 实现十三章节、链、IV、Greeks、盈亏和倒计时；
- [ ] 明确“合约动作 ≠ 标的方向”；
- [ ] 历史成绩单分别展示三个概率 head 和四类 outcome 结果；
- [ ] 验证导出、知识库和页面一致。

### 任务 6：结果

- [ ] exact-contract profit 按 ask 入场、bid 退出或正式到期结算，并扣除佣金、交易费、
  滑点、资金、行权/结算及 target spec 的全部成本；
- [ ] underlying head 冻结精确标的 observation spec 和 neutral band；IV head 冻结同一
  精确合约 bid/ask solver、期限和 IV neutral band；
- [ ] 覆盖三个 head 的全部黄金标签，以及 entry ask/exit bid 缺失、solver 不收敛、
  期限非正、提前到期、停牌、公司行动/结算缺失和已有多头平仓；
- [ ] 不续接其他合约，不构造裸空收益；
- [ ] 用四个 `outcome_kind` 保存标的、IV、合约 P&L 和平仓规避结果；
- [ ] 用统一结果状态、成熟原因和列化价格/成本口径保存证据。

### 任务 7：预测 head、调度和晋级

- [ ] 三个 head 分别注册 `target_spec_version/scoreability_rule_version`、
  `probability_model_version/probability_artifact_hash`、
  `calibration_version/calibration_artifact_hash/training_cutoff_at`、
  `baseline_code/baseline_version` 和公共 `head_spec_hash`；合约净盈利 head 为默认
  晋级主 head；
- [ ] mixed `head_spec_hash` 的概率、结果或 cohort 整批拒绝；
- [ ] 只建立审批后的精确 CONTRACT schedule、日历 cutoff 和租约锁；到期替代合约必须
  重新配置期解析/审批，运行时禁止 selector；
- [ ] 原时点补跑冻结具体 canonical 合约、identity version、schedule、链/标的/持仓
  snapshot ID/hash/access principal 和 head spec，不重新选约或跨用户重绑持仓；
- [ ] `decision_input_hash` 覆盖 exact position context、链、标的、三个 head spec、
  `position_context_snapshot_id/content_hash`、`owner_scope/user_id/access_principal`、
  `target_spec_version/scoreability_rule_version` 及 target spec 内的 neutral band、
  probability/calibration artifact、`training_cutoff_at`、
  `baseline_code/baseline_version/head_spec_hash` 和全部曲面/成本/策略版本；
- [ ] 建立 `POOLED` 或 `INSTRUMENT_SPECIFIC` `promotion_scope_key` 和不可变审批历史；
- [ ] 影子验证并准备 T2 证据。

## 3. 测试命令

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base pytest -q \
  tests/asset_research/option
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base ruff check \
  app/services/asset_research/plugins/option \
  tests/asset_research/option

cd ../../src/frontend
npm run typecheck
npm run test -- --run src/__tests__/asset-analysis/OptionPanel.test.ts
```

## 4. 退出条件

- [ ] OPT-FR-001 至 013 全部实现；
- [ ] 不存在任何裸卖路径；
- [ ] 三个 head 的可复现目标、黄金标签、scoreability、校准/基线和四类 outcome 完整；
- [ ] v1 运行记录不存在 selector 输入，补跑命中同一精确 CONTRACT；
- [ ] 同一精确合约 `long_quantity=short_quantity=0` 的端到端夹具稳定规范化为 `FLAT`，
  并通过 `FLAT+NEUTRAL=HOLD+NONE` 验收；
- [ ] 跨用户/owner、跨合约、cutoff 后可见、过期和缺失快照均为 UNKNOWN 且无法 CLOSE，
  直接数据库写入也被 FK/CHECK/trigger 拒绝；
- [ ] [验收文档](./ACCEPTANCE.md)T1 全部通过；
- [ ] 无完整历史链和双边报价时不得申请 T2。
