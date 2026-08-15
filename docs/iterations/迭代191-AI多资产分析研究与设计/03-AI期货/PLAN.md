# 191C AI 期货实施计划

> 前置条件：P0 公共底座完成；合约日历和行情许可可用。若 Gate 未通过，仅允许
> 固定夹具、纯函数和 fail-closed 契约实现；不得启用 provider capability、接入真实来源、
> 创建真实影子调度、宣称 T1 可验收或公开方向性建议。

## 1. 文件所有权

```text
src/backend/app/services/asset_research/plugins/futures/
├── __init__.py
├── identity.py
├── contract_master.py
├── calendar.py
├── mapping.py
├── collector.py
├── features.py
├── commodity.py
├── equity_index.py
├── rates.py
├── fx_future.py
├── quality.py
├── policy.py
├── report.py
└── outcomes.py
src/backend/tests/asset_research/futures/
├── test_identity.py
├── test_calendar.py
├── test_mapping.py
├── test_curve.py
├── test_quality.py
├── test_policy.py
├── test_outcomes.py
└── test_api.py
src/frontend/src/components/asset-analysis/panels/FuturesPanel.vue
src/frontend/src/__tests__/asset-analysis/FuturesPanel.test.ts
```

## 1.1 任务依赖、并行条件与公共契约冻结点

本节只描述可验证产物之间的实施门槛，不要求在数据库、API 或任务模型中增加任务依赖
字段。期货资产线只等待所列公共契约和自身产物，不等待其他资产插件完成。

公共冻结点：

- `C1 身份与插件`：`AssetResearchPlugin` 方法签名、公共资产类型、`identity_level`、
  `canonical_id` 和 `identity_version`；
- `C2 证据与时点`：`RawObservation/RawAssetSnapshot`、来源注册、内容哈希和
  `observed_at/published_at/available_at/retrieved_at` 语义；
- `C3 质量与决策`：`GateResult`、公共枚举、`ReasonCode`、`ResearchDecision`、
  候选/发布隔离和 `access_principal`；
- `C4 预测与结果`：`PredictionHead`、`HorizonSpec`、结果唯一键、`OutcomeStatus`、
  `MaturityReason` 和 `head_spec_hash`；
- `C5 调度与幂等`：schedule/run/prediction 生命周期、cutoff、租约、固定
  CONTRACT 身份及 `run_key/decision_input_hash/prediction_key`；
- `C6 发布与晋级`：模型状态机、`PromotionScope`、报告/导出/知识库发布边界和审计。

| 任务 | 最小前置产物 | 可并行条件 | 开始前必须冻结 |
| --- | --- | --- | --- |
| 1 合约主数据 | P0 身份插件骨架、合法主数据来源可用 | 品种规则夹具与真实合约解析可并行，汇合时使用同一身份版本 | `C1`、`C2` |
| 2 日历和映射 | 任务 1 的精确 CONTRACT 身份和合约版本 | 交易日历与 point-in-time 映射可并行，映射集成等待日历 cutoff 语义 | `C1`、`C2` |
| 3 行情和特征 | 任务 1 的合约字段、任务 2 的会话/映射 Schema | 股指、商品、国债、外汇适配器可并行；首个完整样例不强制其他类别串行 | `C2` |
| 4 质量和策略 | 任务 3 的可空特征/报价 Schema | 原因码、真值表和类别策略可用冻结夹具并行，发布前统一过 gate | `C3`、`C4` 的 head 口径 |
| 5 报告和页面 | 任务 4 的 published decision 与公共报告 envelope | 前后端在 DTO、证据 ID 冻结后并行 | `C3`、`C6` |
| 6 结果 | 任务 1 的真实合约、任务 2 的日历、任务 3/4 的成本与信号口径 | 各 horizon/outcome 评估器可并行，共用 head spec 黄金夹具 | `C4` |
| 7 调度和晋级 | 任务 1/2 的精确身份与 cutoff、任务 4 的安全发布；晋级另等待任务 6 | 固定合约 scheduler 可与任务 5/6 并行，晋级状态切换等待成熟结果 | `C5`、`C6` |

## 2. 任务

### 任务 1：合约主数据

- [ ] 先写真实合约、连续序列、未知规则和到期失败测试；
- [ ] 建立版本化合约、乘数、tick、到期、交割、保证金和限制模型；
- [ ] 不通过代码字符串猜字段；
- [ ] 实现品种/合约/连续三层搜索和身份确认。

### 任务 2：日历和映射

- [ ] 建立交易所/品种会话和节假日规则；
- [ ] 验证 19:10 后夜盘、无夜盘和节前取消夜盘；
- [ ] 实现 point-in-time 主力/近月映射，按 cutoff 冻结有序
  `normalization_chain`、`chain_vintage_at`、来源快照/链哈希和复权规则；
- [ ] feature hash 绑定 cutoff、真实映射合约、normalization chain/source hash 和
  feature version；
- [ ] 用同一 cutoff 前后各追加一次未来换月和来源修订，证明过去 mapped contract、
  feature value 和 feature hash 均不变。

### 任务 3：行情、曲线和专属特征

- [ ] 收集真实合约双边报价、结算、量仓和深度；
- [ ] 实现期限结构、基差、carry 和流动性迁移；
- [ ] 先完成股指和一个商品插件，再完成国债和外汇期货；
- [ ] 所有库存、COT、排名和宏观保存发布时间。

### 任务 4：质量和策略

- [ ] 实现全部硬拒绝和降级原因；
- [ ] 实现类别独立的确定性策略和成本门槛；
- [ ] 只用公共方向、建议、持仓和意图枚举，并测试完整真值表；
- [ ] 内部候选可生成 LONG/SHORT，SHADOW 普通用户发布决定固定为 HOLD/AVOID；
- [ ] 注册主 head 的 `target_spec_version/scoreability_rule_version`，冻结版本化
  neutral band、HorizonSpec 的 session/day 计数和可执行报价边；
- [ ] 所有动作保持 `execution_disabled=true`。

### 任务 5：报告和页面

- [ ] 实现十三章节、期限结构、换月、基差、压力和交割组件；
- [ ] 显示下一有效会话和数据 cutoff；
- [ ] 历史列表同时显示连续序列及冻结真实合约；
- [ ] 完成导出与证据一致性测试。

### 任务 6：结果

- [ ] 1/5/20 `TRADING_SESSION` 与 `TRADING_DAY` 分别按交易所日历、真实合约和
  冻结成本评分；多头使用 entry ask/exit bid，空头使用 entry bid/exit ask；
- [ ] 用 `outcome_kind` 分开合同级、规避损失和 roll-aware 结果；
- [ ] 保存结果时点、价格/成本口径、币种、状态和成熟原因；
- [ ] 覆盖 LONG/SHORT/NEUTRAL 黄金标签，以及到期、单边涨跌停、无报价和换月；
- [ ] 冻结 `probability_model_version/probability_artifact_hash`、
  `calibration_version/calibration_artifact_hash/training_cutoff_at` 和同 spec 类别
  先验的 `baseline_code/baseline_version`，按公共规则生成 `head_spec_hash`；
- [ ] mixed `head_spec_hash` 的评分或 cohort 必须整批拒绝。

### 任务 7：每日影子和晋级

- [ ] 建立审批资产清单、日历感知 cutoff、租约锁、幂等和原时点补跑；
- [ ] 每条每日 schedule 在配置/审批时固定 `identity_level=CONTRACT`、
  `canonical_id` 和 `identity_version`；runner 的请求 Schema 和
  持久化输入不接受运行时 selector、连续品种、主力/近月选择或重新映射参数；
- [ ] 原时点补跑必须读取原 schedule/run 冻结的同一
  `canonical_id/identity_version` 和 cutoff，禁止按当前主力、最新映射或新合约替换；
- [ ] 自动化验证运行时 selector 输入被拒绝，正常重试和历史补跑均命中原精确合约；
- [ ] `decision_input_hash` 包含持仓、真实合约、连续映射及 chain vintage/source hash、
  HorizonSpec、`target_spec_version/scoreability_rule_version` 及 target spec 内的
  neutral band、成本、快照、
  probability model/calibration artifact、`training_cutoff_at`、
  `baseline_code/baseline_version` 和 `head_spec_hash`；
- [ ] 注册 `POOLED` 或 `INSTRUMENT_SPECIFIC` `promotion_scope_key`；
- [ ] 进入影子验证并生成不可变晋级证据。

## 3. 测试命令

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base pytest -q \
  tests/asset_research/futures
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base ruff check \
  app/services/asset_research/plugins/futures \
  tests/asset_research/futures

cd ../../src/frontend
npm run typecheck
npm run test -- --run src/__tests__/asset-analysis/FuturesPanel.test.ts
```

## 4. 退出条件

- [ ] FUT-FR-001 至 013 全部实现；
- [ ] 股指和商品完整样例通过，国债/外汇未达专属数据条件时明确保持研究；
- [ ] 无连续复权价进入建议或评分；
- [ ] 同 cutoff 在未来换月后重放的连续特征及哈希完全相同；
- [ ] 每日 schedule 固定到精确 `CONTRACT` 身份，runner 无运行时 selector 接口，
  重试和补跑保持原 `canonical_id/identity_version`；
- [ ] 主 head 的三类黄金标签、两种日历 unit、missing/limit/expiry 和 mixed-spec
  固定夹具全部通过；
- [ ] [验收文档](./ACCEPTANCE.md)T1 全部通过；
- [ ] 模型未晋级前保持 `SHADOW`。
