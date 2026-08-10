# 191B AI 基金实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 交付按基金产品、份额和上市实例识别，按 ETF/开放式/货币/债券/QDII 专属机制研究，每日影子运行并以多结果头实证评分的 long-only AI 基金能力。

**Architecture:** 复用总计划的 `AssetResearchPlugin`、公共决策枚举、不可变预测、结果评估和模型注册底座；基金插件先解析交易机制，再执行专属数据、特征、门控和结果规则，发布策略强隔离候选层和普通用户层。

**Tech Stack:** Python 3.10+、FastAPI、SQLAlchemy 2.0、Pydantic、Decimal、pandas、Vue 3、TypeScript、Vitest、pytest。

## Global Constraints

- 前置条件：P0 公共底座完成，基金数据许可注册表可用；
- 实施阻断 Gate：在任务 1 开始前提交获批的基金来源 capability manifest。对声明支持
  的每种基金 route，必须用真实覆盖样本证明可取得份额类别、官方 NAV/估值日、基准、
  费用、交易/申赎状态，以及该 route 必需的持仓披露或 ETF 价格/PCF；同时记录许可
  用途、地域、再分发、披露滞后和保留限制，并提供成功、数据不足和许可拒绝证据。
  未通过的 route 必须从 capability 关闭；此时仅允许纯函数/固定夹具和 fail-closed
  契约实现，不得接入真实来源、创建真实影子调度、宣称 T1 可验收或公开方向性建议；若
  开放式基金 Gate 未通过，191B 不得宣称已支持开放式基金，也不得用 ETF 数据代替；
- 只使用公共 `normalized_direction/position_context/trade_intent/recommendation`，不创建 `FundAction`；
- `normalized_direction` 只允许 `LONG/SHORT/NEUTRAL/INDETERMINATE`；
- `ReasonCode` 的通用原因使用 `COMMON.*`、基金专属原因使用 `FUND.*`，`outcome_kind` 使用稳定小写命名空间 `fund.*`；
- 采集字段缺失不是请求校验错误；`RawFundIdentityCandidate/RawFundSnapshot` 必须先
  不可变落库，只有门控后的 `PostGateFundSnapshot` 收紧类型关键字段；
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
src/backend/app/services/asset_research/plugins/fund/
├── __init__.py
├── identity.py
├── collector.py
├── router.py
├── etf.py
├── open_end.py
├── money_market.py
├── bond_fund.py
├── qdii.py
├── quality.py
├── policy.py
├── publication.py
├── report.py
├── outcomes.py
├── scheduler.py
└── promotion.py
src/backend/tests/asset_research/fund/
├── test_identity.py
├── test_router.py
├── test_etf.py
├── test_open_end.py
├── test_quality.py
├── test_policy.py
├── test_publication.py
├── test_outcomes.py
├── test_scheduler.py
├── test_promotion.py
└── test_api.py
src/frontend/src/components/asset-analysis/panels/FundPanel.vue
src/frontend/src/__tests__/asset-analysis/FundPanel.test.ts
```

## 1.1 任务依赖、并行条件与公共契约冻结点

本节只描述可验证产物之间的实施门槛，不要求在数据库、API 或任务模型中增加任务依赖
字段。基金与债券不互为前置；公共底座冻结后，两条资产线可独立并行实施。

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
| 1 身份和路由 | P0 身份插件骨架、已批准基金来源 manifest 和逐 route 覆盖证据 | 可与债券任务 1、各基金类型路由夹具并行 | `C1`、`C2` 的字段级 provenance 语义 |
| 2 快照和数据 | 任务 1 的产品/份额/上市实例身份及类型路由 Schema | NAV、持仓、基准、费用和 ETF 数据适配器可并行；均先写同一 raw envelope | `C1`、`C2` |
| 3 特征和质量 | 任务 1 的类型路由、任务 2 的 raw snapshot 契约 | 各基金类型特征可并行；质量门控集成等待各类型关键字段矩阵 | `C3` |
| 4 策略和报告 | 任务 3 的 GateResult、特征与版本化阈值 | 结构质量/战术进入策略和报告章节可并行，发布前汇合 | `C3`、`C6` |
| 5 页面 | 任务 4 的 published decision 与报告 DTO | ETF、开放式及公共成绩单组件可在 DTO 冻结后并行 | `C3`、`C6` |
| 6 结果闭环 | 任务 2 的 point-in-time NAV/行情、任务 3/4 的成本与决策口径 | 各基金类型和 `outcome_kind` 评估器可并行，共用 head spec 校验 | `C4` |
| 7 调度和回补 | 任务 1 的精确身份、任务 2 的时点规则、任务 4 的安全发布 | 各日历 schedule 与 NAV catch-up 可并行；启用前统一验证幂等 | `C5` 及 `C1` 的身份版本语义 |
| 8 晋级和治理 | 任务 6 的成熟结果、任务 7 的连续 SHADOW 证据 | pooled/specific scope 证据可并行，状态切换等待全部门槛 | `C4`、`C6` |

## 2. 任务

### 任务 1：原始身份和类型路由

- [ ] 先写 A/C/I/ETF 份额不合并和未知类型拒绝测试；
- [ ] 建立字段值可空的 `RawFundIdentityCandidate`，每个叶子字段保存
  `provenance/observed_at/published_at/available_at/retrieved_at`；
- [ ] 建立 `candidate_kind=FUND_PRODUCT/SHARE_CLASS/LISTING` 候选和
  门控后 `fund_identity_kind=SHARE_CLASS/LISTING` 持久化模型，不改变公共
  `identity_level=PRODUCT` 映射；
- [ ] 将两类可分析基金映射为公共 `identity_level=PRODUCT`，断言基金产品候选不可
  持久化或分析、开放式份额 `venue=null` 且通道/cutoff/日历必填、场内实例
  `venue` 必填；
- [ ] 用 `FUND.SHARE_CLASS_AMBIGUOUS` 拒绝多份额候选，禁止默认第一条；
- [ ] 实现 ETF、开放式、货币、债券、QDII 和特殊基金路由；
- [ ] 对杠杆/反向/商品基金强制研究模式。

### 任务 2：原始快照、官方数据和时点

- [ ] 接入官方 NAV、合同、费用、基准、持仓、经理和规模；
- [ ] ETF 接入授权行情、NAV/IOPV、PCF 和申赎状态；
- [ ] 建立 `RawFundSnapshot`，允许 official benchmark、NAV、fees、holdings、
  dealing 和 market 的叶子值为空，逐字段保存来源与四类时点；
- [ ] 在任何 gate、路由或特征计算前，以内容哈希 append-only 保存原始候选、原始
  载荷和 `RawFundSnapshot`，断言重跑不能覆盖；
- [ ] 禁止第三方估算覆盖官方 NAV。

### 任务 3：特征和质量

- [ ] quality gate 只读已提交的 raw snapshot，按冻结优先级生成稳定且有序的
  `COMMON.*` / `FUND.*`，关键字段通过后才构造对应 `PostGateFundSnapshot`；
- [ ] 参数化覆盖缺 official benchmark、NAV、fees、holdings 和特殊类型，断言每例
  都能回读 raw 审计快照；缺数据发布
  `REJECTED + INSUFFICIENT_DATA + AVOID/NONE`，特殊类型发布
  `quality_status` 为 `ELIGIBLE` 或 `DEGRADED` 且
  `actionability=RESEARCH_ONLY`，API 无领域缺失型 Pydantic 422 或未捕获 500；
- [ ] 参数化验证 GateResult 只接受公共 `quality_status/actionability` 枚举，拒绝
  `quality_status=RESEARCH_ONLY` 和 `actionability=NONE`；覆盖
  `REGION_RESTRICTED > INSUFFICIENT_DATA > RESEARCH_ONLY > ACTIONABLE` 发布优先级；
- [ ] 实现总回报、基准超额、回撤、风险调整和滚动稳定性；
- [ ] 实现持仓集中、风格漂移、管理稳定和费用；
- [ ] 实现 ETF 溢折价、流动性、跟踪和战术进入；
- [ ] 完成短轨迹、暂停、过期、无基准和特殊类型门控。

### 任务 4：策略和报告

- [ ] 输出结构质量与战术进入两个独立结果；
- [ ] 实现版本化阈值和持仓感知公共四元组，覆盖空仓、已有多头、未知和不支持的空头上下文；
- [ ] 实现 `candidate_decision_json/published_decision_json` 和全部 `COMMON.*` / `FUND.*` 门控；
- [ ] 断言 SHADOW 普通用户只见 `HOLD/AVOID`，空仓负向候选不发布 `SELL`；
- [ ] 生成十五个报告章节和证据 ID；
- [ ] 固定“非评级/非保证”表述，LLM 不得读取候选层或改写发布建议。

### 任务 5：页面

- [ ] 实现类型自适应 `FundPanel`；
- [ ] ETF 展示 PCF/IOPV/溢折价，开放式展示申赎和 NAV；
- [ ] 所有持仓明确 `holdings_as_of`；
- [ ] 验证路由、空状态、导出和历史成绩单。

### 任务 6：结果闭环

- [ ] 按基金类型注册唯一收益主 `PredictionHead` 和可选
  `fund.dealing_event` head，完整继承公共 `target_spec_version`、
  `scoreability_rule_version`、`probability_model_version/probability_artifact_hash`、
  `calibration_version/calibration_artifact_hash/training_cutoff_at`、
  `baseline_code/baseline_version` 及 `head_spec_hash`；
- [ ] cohort 聚合前校验公共 `head_spec_hash`，混合 target/scoreability、概率模型、
  校准或基线版本形成的 mixed-spec cohort 必须拒绝而不是合并；
- [ ] 实现 `fund.etf_market_return`、`fund.open_end_nav_return`、`fund.money_market_cash_return`、`fund.qdii_nav_fx_return` 和 `fund.dealing_event`；
- [ ] 结果唯一键包含 `outcome_kind`，实现完整 `OutcomeStatus` 语义和独立 `MaturityReason`；
- [ ] 分别实现 ETF 和开放式执行/成熟规则；
- [ ] 覆盖分红、费用、暂停、QDII 双日历和货币基金；
- [ ] 统计按类型/份额/基准分层；
- [ ] 断言同评估器重跑不重复、新评估器版本只追加。

### 任务 7：每日影子调度和回补

- [ ] 为中国 ETF 19:10/19:00、开放式 23:30/23:15、美国 ETF 18:30/18:15 编写时区和日历测试；
- [ ] 实现次日 08:30/08:15 官方 NAV catch-up，并用新截止时间和预测键保存；
- [ ] 按 QDII 合同 NAV lag 和双日历判断新鲜度，禁止误判合法延迟；
- [ ] 每条 schedule 只绑定一个 `canonical_id`，静态许可清单只在配置阶段展开，运行时禁止市场/宇宙扫描；
- [ ] 以含 `access_principal` 的 schedule/manual scope、schedule 版本、触发/截止
  时间、截止策略和策略版本生成 `run_key`；
- [ ] 以全部冻结输入生成 `decision_input_hash`，再生成
  `prediction_key=SHA-256(access_principal|decision_input_hash)`；验证同主体重试复用、
  相同 `owner_scope` 下不同 `user_id` 绝不复用，并保持历史 point-in-time 回补幂等。

### 任务 8：晋级和样本治理

- [ ] 由规范化 `PromotionScope` 生成包含范围模式、基金类型、地区、执行机制、
  基准族、期限和主 head 的 `promotion_scope_key`，版本使用注册表独立列；
- [ ] 两类 scope 均校验 200 个成熟行动主结果头、60 个去重日期、冻结的 3 个
  regime、walk-forward、purge/embargo 和 60 个交易日/估值日前瞻影子期；
- [ ] `POOLED` 按基金产品合并 A/C/I、ETF/联接和多场所实例，并额外校验 5 个产品
  组、单组不超过 40% 和 HHI；
- [ ] `INSTRUMENT_SPECIFIC` 将 `canonical_id` 固化到键中，允许 100% 单基金且不
  套 5 产品/40% 规则，禁止结果外推；
- [ ] 冻结 regime 来源/算法/区间/version、主 head、基线、成本与 10,000 次
  moving-block bootstrap 参数；自动判定净效用为正、95% CI 下界非劣、
  `Brier Skill > 0`、回撤和 1.5 倍成本压力 guardrail；
- [ ] `LONG_TERM_QUALITY` 要求冻结区间内 BULL/BEAR 各有连续 60 个适用估值日；
  `TACTICAL_SIGNAL` 即使通过也禁止展示为基金评级；
- [ ] 隔离池化/单基金证据、审批和回退，启动影子模式并生成 T2 证据包。

## 3. 测试命令

```bash
cd src/backend
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base pytest -q \
  tests/asset_research/fund
/Users/yunjinqi/opt/anaconda3/bin/conda run -n base ruff check \
  app/services/asset_research/plugins/fund \
  tests/asset_research/fund

cd ../../src/frontend
npm run typecheck
npm run test -- --run src/__tests__/asset-analysis/FundPanel.test.ts
```

## 4. 退出条件

- [ ] FUND-FR-001 至 017 全部实现；
- [ ] ETF、开放式、货币、债券、QDII 固定样例通过；
- [ ] 基金交易机制未被统一为股票开盘模型；
- [ ] [验收文档](./ACCEPTANCE.md)T1 全部通过；
- [ ] 缺 benchmark/NAV/fees/holdings 夹具先保存 raw 审计快照，再返回
  `REJECTED + INSUFFICIENT_DATA + AVOID/NONE`；复杂基金返回
  `quality_status` 为 `ELIGIBLE` 或 `DEGRADED` 且
  `actionability=RESEARCH_ONLY`，无领域缺失型 422/500；
- [ ] 同输入同主体可复用预测，不同 `user_id` 不共享 `prediction_key`、候选或发布
  决定；
- [ ] 模型保持 `SHADOW`，未满足精确 `promotion_scope_key` 的 T2 门槛前普通用户只见 `HOLD/AVOID`。
