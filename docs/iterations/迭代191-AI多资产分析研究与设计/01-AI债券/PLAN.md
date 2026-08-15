# 191A AI 债券实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 交付可按债项/上市实例研究、每日影子运行、生成可追溯债券研报并用多结果头实证评分的 long-only AI 债券分析能力。

**Architecture:** 复用总计划的 `AssetResearchPlugin`、公共决策枚举、不可变预测、结果评估和模型注册底座；债券插件负责合同现金流、曲线、信用、估值、质量门控和资产原因码，发布策略在候选层与普通用户层之间实施强隔离。

**Tech Stack:** Python 3.10+、FastAPI、SQLAlchemy 2.0、Pydantic、Decimal、QuantLib（锁版本候选）、Vue 3、TypeScript、Vitest、pytest。

## Global Constraints

- 前置条件：总计划 P0 公共底座和 `AssetResearchPlugin` 契约已完成；
- 实施阻断 Gate：在任务 1 开始前提交获批的债券来源 capability manifest，证明 v1
  目标范围至少能按同一 `canonical_id/cutoff` 取得合同现金流与条款、曲线、官方估值
  或合规可执行代理价、信用事件和交易日历，并记录许可用途、地域、再分发和保留限制；
  必须有一条成功、一条数据不足和一条许可拒绝证据。未通过时 191A 只能做来源 spike、
  纯函数/固定夹具和 fail-closed 契约实现；不得启用 provider capability、接入真实来源、
  创建真实影子调度、宣称 T1 可验收或公开方向性建议；
- 只使用公共 `normalized_direction/position_context/trade_intent/recommendation`，不创建 `BondAction`；
- `normalized_direction` 只允许 `LONG/SHORT/NEUTRAL/INDETERMINATE`；
- `ReasonCode` 的通用原因使用 `COMMON.*`、债券专属原因使用 `BOND.*`，`outcome_kind` 使用稳定小写命名空间 `bond.*`；
- 采集字段缺失不是请求校验错误；`RawBondIdentityCandidate/RawBondSnapshot` 必须先
  不可变落库，只有门控后的 `PostGateBondSnapshot` 收紧关键字段；
- `quality_status` 只取 `ELIGIBLE/DEGRADED/REJECTED`；`actionability` 只取
  `ACTIONABLE/RESEARCH_ONLY/INSUFFICIENT_DATA/REGION_RESTRICTED`，`NONE` 仅属于
  `trade_intent`；
- 所有预测幂等键使用
  `access_principal=owner_scope|coalesce(user_id,"SYSTEM")`，禁止跨用户复用；
- SHADOW 候选不可由普通 API、LLM、前端、导出或知识库读取；
- 不接账户、订单或交易执行接口。

---

## 1. 文件所有权

```text
src/backend/app/services/asset_research/plugins/bond/
├── __init__.py
├── identity.py
├── collector.py
├── valuation.py
├── credit.py
├── features.py
├── quality.py
├── policy.py
├── publication.py
├── report.py
├── outcomes.py
├── scheduler.py
└── promotion.py
src/backend/tests/asset_research/bond/
├── test_identity.py
├── test_cashflows.py
├── test_valuation.py
├── test_quality.py
├── test_policy.py
├── test_publication.py
├── test_outcomes.py
├── test_scheduler.py
├── test_promotion.py
└── test_api.py
src/frontend/src/components/asset-analysis/panels/BondPanel.vue
src/frontend/src/__tests__/asset-analysis/BondPanel.test.ts
```

## 1.1 任务依赖、并行条件与公共契约冻结点

本节只描述可验证产物之间的实施门槛，不要求在数据库、API 或任务模型中增加任务依赖
字段。债券与基金不互为前置；公共底座冻结后，两条资产线可独立并行实施。

公共冻结点：

- `C1 身份与插件`：`AssetResearchPlugin` 方法签名、公共资产类型、`identity_level`、
  `canonical_id` 和 `identity_version`；
- `C2 证据与时点`：`RawObservation/RawAssetSnapshot`、来源注册、内容哈希和
  `observed_at/published_at/available_at/retrieved_at` 语义；
- `C3 质量与决策`：`GateResult`、公共枚举、`ReasonCode`、`ResearchDecision`、
  候选/发布隔离和 `access_principal`；
- `C4 预测与结果`：`PredictionHead`、`HorizonSpec`、结果唯一键、`OutcomeStatus`、
  `MaturityReason` 和 `head_spec_hash`；
- `C5 调度与幂等`：schedule/run/prediction 生命周期、cutoff、租约、
  `run_key/decision_input_hash/prediction_key`；
- `C6 发布与晋级`：模型状态机、`PromotionScope`、报告/导出/知识库发布边界和审计。

| 任务 | 最小前置产物 | 可并行条件 | 开始前必须冻结 |
| --- | --- | --- | --- |
| 1 身份和合同 | P0 身份插件骨架、已批准债券来源 manifest 和覆盖证据 | 可与基金任务 1、债券现金流纯函数黄金夹具并行 | `C1`、`C2` 的字段级 provenance 语义 |
| 2 快照和数据 | 任务 1 的候选/规范身份及合同版本规则 | 各合法数据源适配器可并行；均先写入同一 raw envelope | `C1`、`C2` |
| 3 估值和特征 | 任务 1 的合同/现金流 Schema、任务 2 的价格/曲线输入 Schema | 手工现金流黄金测试与数据适配器可并行，集成前对齐版本哈希 | `C2`、`C4` 的目标与成本口径 |
| 4 质量和建议 | 任务 2 的 raw snapshot 契约、任务 3 的可空估值输出 | 原因码/真值表可先用冻结夹具并行，发布集成等待估值输出 | `C3` |
| 5 报告和页面 | 任务 4 的 published decision 及公共报告 envelope | 前后端可在报告 DTO 和证据 ID 冻结后并行 | `C3`、`C6` |
| 6 结果闭环 | 任务 3 的估值口径、任务 4 的决策与成本口径 | 各 `outcome_kind` 评估器可并行，共用黄金样本和 head spec | `C4` |
| 7 调度和回补 | 任务 1 的精确身份、任务 2 的 point-in-time 快照、任务 4 的安全发布 | 调度器可与任务 5/6 并行；启用前必须通过幂等和历史 cutoff 测试 | `C5` 及 `C1` 的身份版本语义 |
| 8 晋级和治理 | 任务 6 的成熟结果、任务 7 的连续 SHADOW 证据 | scope 规范化与证据包生成可并行，状态切换等待全部门槛 | `C4`、`C6` |

## 2. 任务

### 任务 1：原始身份和合同

- [ ] 先编写同代码跨市场、多期债、含权债和未知日计数失败测试；
- [ ] 实现字段值可空的 `RawBondIdentityCandidate`，每个叶子字段保存
  `provenance/observed_at/published_at/available_at/retrieved_at`；
- [ ] 实现 `candidate_kind=ISSUER/ISSUE/LISTING` 候选搜索、规范 ID 和门控后债券
  合同 Schema；不得收紧或改名公共 `identity_level` 映射；
- [ ] 将 `ISSUE/LISTING` 分别映射为公共 `identity_level=ASSET/PRODUCT`，断言发行人
  候选不可持久化或分析、债项仅跨场所估值研究允许空 `venue`、上市实例必须有 `venue`；
- [ ] 用 `COMMON.INSTRUMENT_AMBIGUOUS` 拒绝多候选，禁止默认第一条；
- [ ] 建立合同字段来源优先级和版本哈希；
- [ ] 完成固定利率、零息和分期偿还现金流黄金用例。

### 任务 2：原始快照、市场、曲线和信用数据

- [ ] 为合法的中债/交易所/财政部数据建立适配器，AKShare 只作开发回退；
- [ ] 建立 `RawBondSnapshot`，允许 maturity、terms、prices、curve/benchmark 的
  叶子值为空，并逐字段保存来源与四类时点；
- [ ] 在任何质量判断和估值前，以内容哈希 append-only 保存原始候选、原始载荷和
  `RawBondSnapshot`，断言门控不能回写；
- [ ] 实现政府债/信用债路由，政府债不触发公司财务缺失；
- [ ] 实现评级、披露和信用事件新鲜度。

### 任务 3：估值和特征

- [ ] 以失败测试驱动净价/全价、应计、YTM/YTW、久期、凸性和 DV01；
- [ ] 接入锁版本 QuantLib 或同等纯函数引擎，并与独立手工现金流交叉验证；
- [ ] 实现 carry/roll-down/曲线/利差/成本分解；
- [ ] 对 Z-spread/OAS 不支持场景返回明确空值。

### 任务 4：质量和建议

- [ ] 质量门控只读已提交的 `RawBondSnapshot`，按冻结优先级产出稳定且有序的
  `COMMON.*` / `BOND.*`；只有关键字段完整时构造 `PostGateBondSnapshot`；
- [ ] 覆盖 `is_perpetual=true + maturity=null` 的
  `quality_status` 为 `ELIGIBLE` 或 `DEGRADED`、
  `actionability=RESEARCH_ONLY/BOND.PERPETUAL_MODEL_REQUIRED`，以及普通债缺到期的
  `REJECTED + INSUFFICIENT_DATA + AVOID/NONE/BOND.MATURITY_MISSING`；
- [ ] 参数化验证 GateResult 只接受公共 `quality_status/actionability` 枚举，拒绝
  `quality_status=RESEARCH_ONLY` 和 `actionability=NONE`；覆盖
  `REGION_RESTRICTED > INSUFFICIENT_DATA > RESEARCH_ONLY > ACTIONABLE` 发布优先级；
- [ ] 覆盖缺合同、价格、曲线和基准的安全拒绝，断言原始快照仍可按 ID 读取，API
  不返回领域缺失型 Pydantic 422 或未捕获 500；
- [ ] 实现设计文档全部 `COMMON.*` / `BOND.*` 硬拒绝和降级原因，并用版本化码表生成中文；
- [ ] 建立版本化久期/评级/流动性阈值配置；
- [ ] 以公共四元组实现持仓感知策略，覆盖空仓、已有多头、未知和不支持的空头上下文；
- [ ] 实现 `candidate_decision_json/published_decision_json`、概率上限和模型未晋级回退；
- [ ] 断言 SHADOW 普通用户只见 `HOLD/AVOID`，空仓负向候选不发布 `SELL`；
- [ ] 断言 LLM 无法读取候选层或改变结构化发布结果。

### 任务 5：报告、页面和导出

- [ ] 实现十四个报告章节和证据映射；
- [ ] 新增现金流、曲线、久期、信用和情景组件；
- [ ] 复用公共历史和成绩单组件，增加债券分组；
- [ ] 验证页面、Markdown、PDF 和知识库内容一致。

### 任务 6：结果闭环

- [ ] 注册 `bond.executable_total_return` 主 `PredictionHead` 和可选
  `bond.credit_event` head，完整继承公共 `target_spec_version`、
  `scoreability_rule_version`、`probability_model_version/probability_artifact_hash`、
  `calibration_version/calibration_artifact_hash/training_cutoff_at`、
  `baseline_code/baseline_version` 及 `head_spec_hash`；
- [ ] cohort 聚合前校验 `head_spec_hash` 和公共 spec 版本，mixed-spec 样本必须
  拒绝，不能合并 Brier、基线或晋级分母；
- [ ] 实现 `bond.executable_total_return`、`bond.valuation_total_return`、`bond.credit_event` 三类结果头；
- [ ] 结果唯一键包含 `outcome_kind`，实现完整 `OutcomeStatus` 语义和独立 `MaturityReason`；
- [ ] 实现 20/60/120 日成熟评估和含息总回报；
- [ ] 覆盖付息、赎回、本金、估值不可执行和无成交；
- [ ] 计算财富指数超额、成本和分层统计；
- [ ] 断言同评估器重跑不重复、新评估器版本只追加。

### 任务 7：每日影子调度和回补

- [ ] 为中国 19:10/19:00 和美国 18:30/18:15 的时区、节假日、夏令时编写测试；
- [ ] 每条 schedule 只绑定一个 `canonical_id`，静态审批清单只在配置阶段展开，运行时禁止市场/宇宙扫描；
- [ ] 以含 `access_principal` 的 schedule/manual scope、schedule 版本、触发/截止
  时间、截止策略和策略版本生成 `run_key`；
- [ ] 以全部冻结输入生成 `decision_input_hash`，再生成
  `prediction_key=SHA-256(access_principal|decision_input_hash)`；验证同主体重试复用、
  相同 `owner_scope` 下不同 `user_id` 绝不复用；
- [ ] 实现显式历史截止时间回补，断言当前修订数据不会回灌历史预测；
- [ ] 未授权美国数据时不注册对应调度。

### 任务 8：晋级和样本治理

- [ ] 由规范化 `PromotionScope` 生成包含范围模式、债券分类、币种、场所组、
  久期/信用桶、期限和主 head 的 `promotion_scope_key`，版本使用注册表独立列；
- [ ] 两类 scope 均校验 200 个成熟行动主结果头、至少 60 个去重日期、3 个市场
  状态、walk-forward、purge/embargo 和 60 个交易日前瞻影子日；
- [ ] `POOLED` 按债项合并跨场所记录，并额外校验 5 个实体组、政府/信用两类、
  3 个久期桶、3 个流动性桶、单组不超过 40% 和 HHI；
- [ ] `INSTRUMENT_SPECIFIC` 将 `canonical_id` 固化到键中，允许 100% 单券且不套用
  政府/信用、久期、流动性或实体多样性，禁止结果外推；
- [ ] 隔离池化/单券证据、审批和回退，运行影子模式并生成 T2 证据包。

## 3. 测试命令

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base pytest -q \
  tests/asset_research/bond
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base ruff check \
  app/services/asset_research/plugins/bond \
  tests/asset_research/bond

cd ../../src/frontend
npm run typecheck
npm run test -- --run src/__tests__/asset-analysis/BondPanel.test.ts
```

## 4. 退出条件

- [ ] [需求文档](./REQUIREMENTS.md)的 BOND-FR-001 至 017 全部实现；
- [ ] [验收文档](./ACCEPTANCE.md)全部 T1 条目通过；
- [ ] 缺到期/合同/价格/曲线/基准夹具均先保存原始审计快照，再返回
  `REJECTED + INSUFFICIENT_DATA + AVOID/NONE`；永续/复杂品种返回
  `quality_status` 为 `ELIGIBLE` 或 `DEGRADED` 且
  `actionability=RESEARCH_ONLY`，无领域缺失型 422/500；
- [ ] 同输入同主体可复用预测，不同 `user_id` 不共享 `prediction_key`、候选或发布
  决定；
- [ ] 数据许可登记完成；
- [ ] 模型默认为 `SHADOW`，未满足精确 `promotion_scope_key` 的 T2 门槛前普通用户只见 `HOLD/AVOID`；
- [ ] 无账户、订单或交易接口调用。
