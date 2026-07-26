# AI for Investor 核心目标并行迭代计划 - 验收结论

> **验收对象**: `docs/plans/2026-07-05/ai-for-investor-core-goal-parallel-iteration-plan.md`
> **验收日期**: 2026-07-17
> **验收方法**: 三方向并行静态核查（模型/服务/API/schema/前端/测试逐项对照计划交付物，带 `file:line` 证据）+ Definition of Done 复核 + 端到端链路验证
> **结论**: ❌ **未完成**。主体已实现（三方向平均约 73%），核心闭环可运行，但未达到计划自定义的 Definition of Done 与若干验收标准。缺口移入迭代 184 收尾。

---

## 一、总体结论

核心闭环（投资需求 -> 结构化确认 -> AI 生成 -> 回测 -> 优化 -> 稳健性 -> 模拟交易 -> 复核 -> 人工审核 -> 风控下实盘准备）**已打通并可运行**。三方向的后端服务、Pydantic schema、API 端点、前端主流程均已落地，方向 C 测试覆盖较扎实（后端 40+ / 前端 27+ 用例）。

但存在 **DoD 硬性缺口**（方向 A/C 无 Alembic 迁移、方向 B 服务层测试几乎全缺、方向 C 三个模型缺失）和 **若干验收标准部分达标**（时间线下钻、版本结构化对比、指标口径统一、预检自动化、稳健性门控默认非强制、资金曲线持久化、模拟交易详情页、风控监控 UI）。因此判定**未完成**。

| 方向 | 完成度 | 验收标准 | 主闭环 |
| --- | --- | --- | --- |
| A 投研闭环与策略版本轨迹 | ~80% | 3/5 全达、2/5 部分 | ✅ |
| B 数据、回测与稳健性可信度 | ~70% | 1/5 全达、4/5 部分 | ✅（稳健性默认 opt-in） |
| C 模拟交易、人工审核与实盘风控 | ~68% | 4/5 全达、1/5 部分 | ✅ |

---

## 二、方向 A 验收（投研闭环与策略版本轨迹）

### 已完成 ✅

- **模型**（`models/ai_research.py`）：`InvestmentMandate`(:15)、`ResearchPipelineEvent`(:36)、`AIStrategyResearchVersion`(:57)、`AIStrategyResearchVersionComparison`(:91)。后两者命名与计划不同（计划为 `StrategyVersion`/`StrategyVersionComparison`），功能等价。
- **服务**：`investment_mandate_service.py`（规则解析资产/周期/目标/风险/质量门槛，失败保留原 prompt）、`research_pipeline_event_service.py`（`list_events` 按 run_id+workspace_id 查询、`synthesize_from_run_record` 历史回补）、`ai_strategy_research_version_service.py`（`create_from_iteration` 每轮回写、`compare_versions` 计算 deltas/diff/verdict）。
- **AIStrategyResearchService 改造**（`ai_strategy_research_service.py`）：`ensure_for_request` 贯穿 mandate_id(:535)；`_record_pipeline_event`(:465) 在 mandate/初始化/草稿/回测/审查/优化/验证/稳健性/模拟交易/取消等 20+ 阶段写事件，失败路径也写；`_persist_iteration_version`(:496) 每轮写版本。
- **API**（`api/strategy/base.py`）：6 个端点全部实现--mandates POST/GET(:301/:316)、timeline(:622)、versions 列表(:657)、version 详情(:711)、compare(:690)。
- **Schema**（`schemas/ai_strategy_research.py`）：mandate/event/timeline/version/compare 全套。
- **前端**（`StrategyPage.vue`）：投资需求确认区(:893-941)、投研时间线(:1624-1679)、策略版本视图(:1681-1789)、方案切换同步(`selectAIResearchConfigProfile`:4382 / `selectAIResearchRunRecord`:5402)。API 客户端 6 方法在 `api/strategy.ts`。
- **测试**：`test_ai_research_direction_a.py` 覆盖需求解析/事件写入查询/版本创建对比/API（mandate+timeline）。

### 部分完成 🟡

- 时间线渲染阶段/状态/摘要/失败原因，但**未渲染指标快照**（`event.metrics` 有数据未展示），事件**不可点击**查看输入/输出/代码/回测指标。
- 版本视图缺**生成时间**列；对比结果仅 summary 文本 + code_diff，**未结构化渲染 metric_deltas/gate_deltas**。
- "AI 投研失败时事件落库"缺端到端集成测试（service 单测覆盖 failed 事件，但 `test_ai_strategy_research_service.py` 失败用例未注入 event_service 也未断言 DB 事件行）。
- API 测试未覆盖 versions/compare 端点 HTTP 层；前端无时间线渲染/版本列表对比专门测试；`api/strategy.test.ts` 未覆盖 6 个新方法。

### 缺失 ❌

- **Alembic 迁移完全缺失**：方向 A 的 4 张表（`investment_mandates`/`research_pipeline_events`/`ai_strategy_research_versions`/`ai_strategy_research_version_comparisons`）无任何迁移文件，仅靠 `Base.metadata.create_all()` 建表。**生产 Alembic 升级不会建表**，违反 DoD"有数据库迁移"。

### 验收标准

1. ✅ 输入需求 -> 结构化需求并要求确认
2. ✅ 每次投研运行有完整时间线
3. ✅ 每轮策略代码有版本记录
4. 🟡 用户能看到"为什么这版比上版好/差"（对比未结构化展示）
5. ✅ 失败任务能从时间线定位失败阶段和原因

---

## 三、方向 B 验收（数据、回测与稳健性可信度）

### 已完成 ✅

- **模型 + 迁移**（`models/market_data_trust.py` + `alembic/versions/20260705_b_data_backtest_trust.py`）：`AssetSpecModel`(:13)、`MarketDataCoverageModel`(:46)、`MarketDataQualityReportModel`(:80)、`RobustnessTestResultModel`(:97)，4 表迁移带 `20260705_b_` 前缀（符合计划约定），并给 backtest_results 增指标列。**本方向是唯一有迁移的方向**。
- **服务**：`asset_spec_service.py`（合并 `trading_asset_info_service`，含 futures fee 解析）、`market_data_coverage_service.py`（覆盖率 + 质量检查 `_inspect_csv`:278）、`market_data_precheck_service.py`（回测前预检 + gate_evaluations，`backtest/service.py:288` 始终调用且失败抛错）、`backtest/execution_model.py`（手续费/滑点/最小下单/乘数/保证金/成交量限制/涨跌停停牌）、稳健性 4 方法（`overfitting/walk_forward.py`/`out_of_sample.py`/`parameter_sensitivity.py`/`monte_carlo.py`）+ 过拟合评分（`overfitting/service.py:279`）、`robustness_validation_service.py`。
- **AI 投研接入稳健性**（`ai_strategy_research_service.py:1299`）：基础门槛通过后自动运行稳健性，失败且 `require_robustness_validation=True` 则 `passed=False` 不进模拟交易。
- **Schema**（`schemas/market_data_trust.py` + `overfitting.py`）：含统一 `QualityGateEvaluation` 格式。
- **前端**：`/data/market` 覆盖矩阵（`DataPage.vue:172-320`）、回测结果稳健性区域（`BacktestResultPage.vue:247-310` + `OverfittingPanel.vue`）、AI 投研稳健性配置、资产下拉筛选（股票/期货/债券/基金/期权/外汇/加密）。
- **测试**：`test_overfitting_walk_forward.py`/`test_overfitting_monte_carlo.py`/`test_overfitting_api.py` 覆盖底层方法与 API。

### 部分完成 🟡

- **指标口径未统一**：`MetricsService`(`metrics_service.py:32`) 存在，但 `AnalyticsService.calculate_metrics`(`analytics_service.py:34`) 是平行路径，字段名分裂（`annualized_return` vs `annual_return`、`profit_factor` vs `profit_loss_ratio`、`trade_count` vs `total_trades`）；前端 `BacktestResultPage` 同时消费两套。
- **预检非自动**：需手动点"运行预检"按钮（`StrategyPage.vue:773-793`），选资产/周期后不自动触发，只显示问题计数不列具体缺口；AI 投研 schema 无 `require_data_precheck`。
- **首屏仍加载完整明细**：`BacktestResultPage.vue:811` `await getBacktestDetail` 返回完整 equity_curve+trades+drawdown_curve，无轻量 summary 优先端点（后端 `result_summary` 已缓存但前端不先取）。
- **期货数据无专项检查**：`_inspect_csv` 只做通用缺口/重复/异常，无连续合约换月缺口、夜盘覆盖专项。
- **稳健性门控默认 opt-in**：`robustness_validation`/`require_robustness_validation` 默认 `False`（`schemas/ai_strategy_research.py:549,553`），不勾选则跳过稳健性直接进模拟交易。
- `OverfittingPanel.vue` 方法选项不含 `parameter_sensitivity`（AI 投研配置含）。

### 缺失 ❌

- **服务层单元测试几乎全缺**：`asset_spec_service`/`market_data_coverage_service`/`market_data_precheck_service`/`robustness_validation_service`/`execution_model`/`metrics_service` 均无直接测试；`/data/trust` API 无测试；无"稳健性失败阻止模拟交易"端到端测试；无指标统一口径测试。**违反 DoD"有服务层单元测试 + API 测试"**。

### 验收标准

1. 🟡 提交前能知道数据是否足够（有预检能力但非自动、不列缺口）
2. ✅ 股票/期货/债券等可通过下拉框筛选
3. 🟡 回测指标口径一致（存在双路径字段分裂）
4. 🟡 达标必须经稳健性验证才能进模拟交易（默认 opt-in 非强制）
5. 🟡 回测结果打开速度提升（标题/异步加载有，但首屏仍取完整明细）

---

## 四、方向 C 验收（模拟交易、人工审核与实盘风控）

### 已完成 ✅

- **paper_trading 核心**（`paper_trading_service.py` 1955 行）：账户/订单/成交/持仓/资金（`create_account`/`submit_order`/`_fill_order`/`_update_position`/`_update_account`）。
- **AI 投研接入模拟交易**（`ai_strategy_research_service.py:1649-1672`）：achieved 时进 paper_trading stage 并写事件；`_start_paper_trading`(:3600) 创建/复用 workspace + 创建 paper unit + `run_units` 启动；失败写 `paper_trading_failed` 事件。
- **模拟交易复核**（`ai_strategy_research_service.py`）：`_evaluate_paper_monitoring_plan`(:9812) 覆盖 rolling Sharpe/回撤/交易样本/执行成本/观察期；`paper_observation_period` 规则未达标不进 ready_for_live。
- **实盘审核门禁**（`:2655-2661`）：强制 `approved_for_live && approval.approved`，否则 raise；实盘 unit 创建 `lock_trading=True, lock_running=True`(:8163)；`start_units`(:1936) 调 `assert_trading_unit_pre_run` 校验 `live_handoff_approved`/`risk_limits_confirmed`/`prepared_risk_gate_passed`。
- **风控 gate**（`risk_gate_service.py`）：`evaluate_live_preparation`/`evaluate_trading_unit_pre_run`/`assert_trading_unit_pre_run`，下单前检查覆盖最大仓位/单笔金额/日亏损/回撤/保证金/黑名单。
- **Schema**（`schemas/ai_strategy_research.py` + `paper_trading.py`）：paper trading 启停/规则评估/复核/实盘审核/交接包/实盘准备全套。
- **前端**：AI 投研结果区展示模拟交易状态/复核/实盘交接（`StrategyPage.vue:1357-1552`）、实盘审核通过/拒绝（:1424-1436）。
- **测试**：后端 40+ 用例（账户资金/订单成交/持仓/复核规则/审核通过拒绝/风控拒单/观察期门禁）、前端 27+ 用例（模拟交易启动/复核/审核动作/锁定）。

### 部分完成 🟡

- **模型命名不同**：`Account`/`Order`/`Position`（`paper_trading.py:43,146,91`）而非 `PaperAccount`/`PaperOrder`/`PaperPosition`，功能等价。
- **服务未拆 `paper_trading/` 子包**：broker/runner/review_service/live_handoff_review 全合并进 `paper_trading_service.py` + `ai_strategy_research_service.py`，未按计划拆为 `broker.py`/`runner.py`/`review_service.py`。
- **审核决策**：仅 `approved`/`rejected`（`:4366-4367`），无"要求继续优化"独立决策。
- **风控**：启动前静态评估完整，**非每笔下单/成交后实时拦截**。
- **告警**：`RiskControlService`(`risk_control_service.py:18-26`) 存在但**未接入 paper/live 运行时**。

### 缺失 ❌

- **三个模型与迁移缺失**：`PaperReviewReport`/`LiveHandoffReview`/`RiskRule` 无模型/表，以 JSON 字段挂在 `AIStrategyResearchRunRecord`(`schemas:905-909`) 与 `workspace.settings`、`_DEFAULT_RISK_LIMITS` 字典(`risk_gate_service.py:9-17`) 替代；无 `20260705_c_*` 迁移。**违反 DoD"有数据库迁移"**。
- **资金曲线无持久化**：`Account` 仅当前 `total_equity` 单值，无 equity_curve 表/方法。
- **无模拟交易详情页**：router 无 paper 路由，无独立页面（账户权益/持仓/订单/成交/资金曲线/信号聚合）。
- **无风控配置与监控 UI**：无策略级/账户级风控配置、无一键暂停、无风控告警列表（`risk_control.py` API 存在但前端无页面）。

### 验收标准

1. ✅ AI 投研达标后能创建并启动模拟交易实例
2. 🟡 持续记录订单/成交/持仓/权益（权益仅当前单值，无资金曲线）
3. ✅ 观察期后能生成模拟交易复核报告
4. ✅ 未通过人工审核不能进入实盘准备（门禁 + 默认锁定已落实）
5. ✅ 实盘准备/运行前必须通过风控检查

---

## 五、Definition of Done 复核（计划第九节）

| DoD 项 | A | B | C |
| --- | --- | --- | --- |
| 有数据库迁移 | ❌ | ✅ | ❌ |
| 有 Pydantic schema | ✅ | ✅ | ✅ |
| 有服务层单元测试 | 🟡 | ❌ | ✅ |
| 有 API 测试 | 🟡 | ❌ | ✅ |
| 有前端基础测试 | 🟡 | 🟡 | ✅ |
| 错误路径有明确失败原因 | ✅ | ✅ | ✅ |
| 关键动作写入投研事件/审计 | ✅ | - | ✅ |
| 不硬编码密钥 | 🟡 `ibkr_cookies.json` 仍含真实设备 MAC/会话 token | | |
| 不提交 .env/logs/artifacts/临时数据 | 🟡 `MagicMock/`、`lost_codes.pkl` 被跟踪；`reports/` 133MB 入库 | | |

后两项（密钥/仓库卫生）为 183 调研已实测的遗留问题，与迭代 183 的 183-A/183-G/183-I 同源，184 不重复，仅跟踪 DoD 闭环。

---

## 六、端到端联调链路（计划第七节第 4 阶段，10 步）

| 步骤 | 状态 |
| --- | --- |
| 1 用户输入投资需求 | ✅ |
| 2 系统解析并确认需求 | ✅ |
| 3 AI 生成策略 | ✅ |
| 4 自动回测 | ✅ |
| 5 自动优化 | ✅ |
| 6 样本外和稳健性验证 | 🟡 默认 opt-in，不勾选则跳过 |
| 7 自动进入模拟交易 | ✅ |
| 8 模拟交易复核 | ✅ |
| 9 生成人工审核包 | ✅ |
| 10 审核通过后进入实盘准备 | ✅ 实盘默认锁定 + 风控 gate |

主闭环可跑通；第 6 步稳健性默认非强制是唯一链路级缺口。

---

## 七、缺口清单（移入迭代 184）

### 硬缺口（阻塞"完成"判定）

1. 方向 A 补 Alembic 迁移（4 表）。
2. 方向 C 补 `PaperReviewReport`/`LiveHandoffReview`/`RiskRule` 模型与迁移（或正式化 JSON 方案并记入文档）。
3. 方向 B 补服务层 + API 测试（6 个服务 + `/data/trust`）。
4. 稳健性门控默认强制（`require_robustness_validation` 默认 True 或提交时强制预检）。
5. 仓库卫生/密钥（与 183 同源，183 主导，184 跟踪 DoD 闭环）。

### 部分缺口（影响体验/合规）

- 方向 A：时间线指标快照与点击下钻；版本结构化对比；失败事件落库 e2e 测试；前端测试与 API 客户端测试补齐。
- 方向 B：指标字段统一（消除 `AnalyticsService` 平行路径）；预检自动化与缺口展示；首屏轻量 summary 优先；期货连续合约/换月/夜盘专项检查；`OverfittingPanel` 补 parameter_sensitivity。
- 方向 C：资金曲线持久化；模拟交易详情页；风控配置/监控 UI；告警接线；"要求继续优化"决策；实时风控拦截；服务拆 `paper_trading/` 子包。

详见 `docs/iterations/迭代184-核心目标并行迭代计划验收收尾/PLAN.md`。

---

## 八、残余风险

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 方向 A/C 无迁移，新部署不建表 | 高 | 184-A/C 优先补迁移，补前在文档标注"仅 create_all 可用" |
| 稳健性默认 opt-in，策略可能未经验证进模拟 | 中高 | 184-B 将 `require_robustness_validation` 默认 True，并加提交时强制预检 |
| 方向 C 模型以 JSON 字段替代，查询/审计困难 | 中 | 184-C 决策：建表 or 正式化 JSON 并加索引/校验 |
| 指标双路径字段分裂，前端展示不一致 | 中 | 184-B 收敛到 `MetricsService` 唯一入口，`AnalyticsService` 改为只读其输出 |
| `ai_strategy_research_service.py` 12206 行，C 服务又往里加 | 中 | 与 183-B 协调，先拆 `paper_trading/` 子包再继续 |
