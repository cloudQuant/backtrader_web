# 迭代 166 - AI 可信度内核与策略评分

> **文档状态**: 已完成
> **创建日期**: 2026-05-24
> **隶属路线**: 世界一流 AI+量化投研平台跃迁 Phase 1
> **总览**: `docs/iterations/世界一流跃迁-迭代166-169-总览.md`
> **执行顺位**: 第 1 站（已确认采用推荐 B）
> **核心目标**: 让用户能信任 AI 生成的策略 —— 建立"评分 + 过拟合检测 + 策略解释"三位一体的可信度内核。

---

## 0. 背景

迭代 165 完成了代码健康巡检：Airflow/Audit 落地、quote 切片、mypy/B904 棘轮起步、仓库卫生。
基线稳定后，进入差异化能力建设阶段。

**用户场景驱动**：
- 用户：「AI 生成了一个策略，回测年化 35%，我能信吗？」
- 当前：只有 Sharpe / MDD / 胜率等单点指标，缺乏综合可信度判断
- 缺失：策略评分、过拟合检测、可解释性

这三项是世界一流 AI 量化平台（QuantConnect、Numerai、Kensho）的**核心差异化基线**。

---

## 1. 总目标

| 维度 | 现状 | 目标 |
|------|------|------|
| 策略可信度评估 | 仅基础指标 (Sharpe/MDD/胜率) | 6 维综合评分 + 等级 (S/A/B/C/D) + 可解释依据 |
| 过拟合检测 | 完全缺失 | Walk-forward + 样本外 + 蒙特卡洛三种方法可选 |
| 策略可解释性 | 用户看不懂 AI 生成的代码 | AST 静态分析 + LLM 自然语言解释 |
| 用户体验 | 看完回测后无信号判断"该不该用" | 评分卡片 + 诊断面板一目了然 |

---

## 2. 执行原则

### 2.1 可以做

1. 新建 `app/services/strategy_score/`、`app/services/overfitting/`、`app/services/strategy_explainer/` 三个新服务包
2. 新建对应 schema 和 API 路由
3. 复用 `fincore`（已装）、`backtest_service`、`workspace_service` 等现有基础设施
4. 前端新增评分卡片、过拟合诊断、解释面板三个组件
5. 新增数据库表用于评分历史和过拟合检测结果缓存
6. 添加配置项以支持评分权重可调（保持向后兼容）

### 2.2 不要做

1. 不要修改 Backtrader 引擎核心
2. 不要修改既有回测 API 的入参/出参（评分作为新端点）
3. 不要在评分服务中嵌入交易决策逻辑
4. 不要在过拟合检测中重新实现回测，必须复用现有 `backtest_service`
5. 不要把"评分高=值得交易"作为系统结论 —— 所有输出附 disclaimer
6. 不要把过拟合检测做成同步阻塞（必须异步任务化）

---

## 3. 任务分解

### 阶段一: 策略评分系统（P0）

> 现状：用户拿到回测结果只有 Sharpe / MDD / 胜率等数值，无法快速判断"这个策略整体怎么样"。
> 目标：用一个综合评分（0-100）+ 等级（S/A/B/C/D），加 6 维明细评分让用户秒判断。

- [ ] **T1**: 评分模型设计与 Schema
  - 新增 `app/schemas/strategy_score.py`，定义 `StrategyScoreRequest` / `StrategyScoreResponse` / `ScoreDimension` / `ScoreLevel`
  - 6 维评分：**收益质量** / **风险控制** / **稳定性** / **过拟合风险** / **可执行性** / **基准对比**
  - 评分公式：`total_score = Σ(weight_i × dimension_score_i)`，默认权重在 `app/config.py` 暴露 `STRATEGY_SCORE_WEIGHTS`
  - 等级映射：S (≥85) / A (70-84) / B (55-69) / C (40-54) / D (<40)
  - 每个维度返回 `{score: 0-100, sub_metrics: {...}, explanation: "..."}` 三元组

- [ ] **T2**: 评分核心服务实现
  - 新增 `app/services/strategy_score/__init__.py`、`scorer.py`、`dimensions.py`
  - `dimensions.py` 实现 6 个 `score_*_dimension(backtest_result, benchmark) -> ScoreDimension` 函数
  - `scorer.py` 编排调用并加权聚合
  - 收益质量：年化收益、Calmar、Sortino
  - 风险控制：最大回撤、波动率、VaR(95)、连续亏损天数
  - 稳定性：月度收益方差、滚动 Sharpe 一致性、Win/Loss 比例稳定性
  - 过拟合风险：引用 `app/services/overfitting/` 的结果，无检测则给中位评分 + degraded flag
  - 可执行性：换手率、平均持仓时长、最小交易数、流动性约束
  - 基准对比：Alpha、信息比、相对最大回撤、跟踪误差

- [ ] **T3**: 评分 API + 历史缓存
  - 新增 `app/api/strategy_score.py`，POST `/api/v1/strategy/score` 接收回测任务 ID 或 backtest result payload
  - 评分结果落库 `app/models/strategy_score.py`（含 backtest_id / score / dimensions JSON / created_at / model_version）
  - GET `/api/v1/strategy/score/{backtest_id}` 查询历史
  - 多用户共享同一 backtest_id 的评分（评分函数纯函数 + 缓存）
  - 在 `app/api/router.py` 注册路由

### 阶段二: 过拟合检测（P0）

> 现状：完全缺失，是 AI 量化的核心痛点。
> 目标：提供三种正交方法的检测能力，给出"过拟合风险等级 + 证据"。

- [ ] **T4**: Walk-forward 分析
  - 新增 `app/services/overfitting/__init__.py`、`walk_forward.py`、`schemas.py`
  - 输入：策略代码 + 完整数据期 + 滚动窗口配置（默认 IS=180d / OOS=60d / step=30d）
  - 输出：每个窗口的 IS 和 OOS 指标对比、Sharpe 衰减率、收益衰减率
  - 计算：复用 `backtest_service.run_backtest` 多次跑回测，期间用 `asyncio.Semaphore` 限制并发
  - 评分逻辑：IS 与 OOS Sharpe 衰减 >50% 标记高风险，30-50% 中风险，<30% 低风险

- [ ] **T5**: 样本外验证 (Out-of-Sample)
  - 新增 `app/services/overfitting/out_of_sample.py`
  - 输入：策略代码 + 数据期 + IS/OOS 切分比例（默认 70/30）
  - 输出：IS 与 OOS 指标对比、统计显著性（t-test）
  - 计算：跑两次回测（IS / OOS），用 `scipy.stats` 做收益均值差异检验
  - 评分逻辑：p-value < 0.05 且 OOS Sharpe 显著低于 IS → 高风险

- [ ] **T6**: 蒙特卡洛模拟
  - 新增 `app/services/overfitting/monte_carlo.py`
  - 输入：策略实际交易记录 + 随机化次数（默认 1000）
  - 方法：
    - **方法 A**：随机重排交易顺序，构造收益分布
    - **方法 B**：bootstrap 抽样交易，构造 confidence interval
  - 输出：实际收益在随机分布中的分位数（P99/P95/P50）、随机化年化收益的 mean/std
  - 评分逻辑：实际收益 < 随机分布 P75 → 高过拟合可能；> P95 → 低过拟合可能
  - 实现：用 numpy `random.permutation` 和 `random.choice(size=n, replace=True)`，避免外部依赖

- [ ] **T7**: 过拟合检测异步任务化 + API
  - 新增 `app/api/overfitting.py`
  - POST `/api/v1/strategy/overfitting/{backtest_id}` 接收检测请求（指定方法集合：walk_forward / out_of_sample / monte_carlo）
  - 异步任务返回 `task_id`，结果通过 WebSocket `ws://.../overfitting/{task_id}` 推送进度
  - GET `/api/v1/strategy/overfitting/task/{task_id}` 查询状态和结果
  - 结果落库 `app/models/overfitting_result.py`
  - 复用 `app/services/audit_service.py` 模式做异步任务管理

### 阶段三: 策略解释器（P0）

> 现状：AI 生成的策略代码用户看不懂，导致信任度低。
> 目标：从代码中抽取结构化信号，用自然语言解释"这个策略在做什么、什么时候买、什么时候卖、用了什么风控"。

- [ ] **T8**: 策略代码 AST 静态分析
  - 新增 `app/services/strategy_explainer/__init__.py`、`ast_extractor.py`
  - 输入：Backtrader 策略源码（字符串）
  - 输出结构：
    ```python
    {
      "indicators": [{"name": "SMA", "params": {"period": 20}, "alias": "sma_short"}, ...],
      "entry_signals": [{"condition": "close > sma_long", "side": "buy"}, ...],
      "exit_signals": [{"condition": "trailing_stop_pct=0.05", "side": "stop_loss"}, ...],
      "risk_controls": [{"type": "position_size", "value": 0.95}, ...],
      "params": [...],
      "data_sources": [...]
    }
    ```
  - 用 Python `ast` 模块解析 `next()` / `__init__()` 方法体
  - 识别常见模式：`self.sma_short = bt.indicators.SMA(...)`、`self.buy(size=...)`、`if/elif` 结构等
  - **优雅降级**：解析失败的代码返回 `{parsable: false, raw_code: "..."}`，让 LLM 处理原始代码

- [ ] **T9**: AI 策略解释器（结合 AST + LLM）
  - 新增 `app/services/strategy_explainer/llm_explainer.py`
  - 输入：T8 的 AST 输出 + 策略元数据（name/category/params）
  - Prompt 模板：「请基于以下结构化分析，用 6 段话向非编程用户解释这个量化策略：
    1. 一句话总结策略思想
    2. 用了哪些技术指标，含义是什么
    3. 什么情况下买入
    4. 什么情况下卖出（含止损止盈）
    5. 关键参数说明和调整建议
    6. 这类策略适合什么市场环境」
  - 复用 `app/services/ai_chat_service.py` 的 endpoint 配置
  - 输出：`StrategyExplanation { summary, indicators_explanation, entry_explanation, exit_explanation, params_explanation, market_fit }`
  - 缓存：相同代码 hash → 相同解释，落库 `app/models/strategy_explanation.py`

- [ ] **T10**: 解释器 API
  - 新增 `app/api/strategy_explainer.py`
  - POST `/api/v1/strategy/explain` 接收 `{code | strategy_id | backtest_id}` 任一
  - GET `/api/v1/strategy/explain/cached/{code_hash}` 查询缓存
  - 同步返回（解释一般 < 5s），无需异步化
  - 失败路径：AI 未配置 → 返回 `reason_code: ai_not_configured` + AST 静态解释 fallback

### 阶段四: 前端集成（P0）

- [ ] **T11**: 策略评分卡片
  - 新增 `src/frontend/src/components/strategy/StrategyScoreCard.vue`
  - 显示：总分大数字 + 等级徽章 + 6 维雷达图（ECharts）
  - 每维支持点击展开看子指标
  - 顶部 disclaimer：「评分仅作研究参考，不构成投资建议」
  - 集成位置：`BacktestResultPage.vue` 顶部、`AIChatPage.vue` 策略草稿卡片右侧

- [ ] **T12**: 过拟合诊断面板
  - 新增 `src/frontend/src/components/strategy/OverfittingPanel.vue`
  - 显示：风险等级徽章 + 三种检测方法 tab（Walk-forward / OOS / Monte Carlo）
  - 每个 tab 内显示该方法的图表 + 证据明细
  - Walk-forward：IS vs OOS Sharpe 双折线图
  - OOS：IS/OOS 收益曲线对比 + p-value 显示
  - Monte Carlo：随机分布直方图 + 实际收益分位数标注
  - "开始检测"按钮 + 异步进度展示（复用现有 WebSocket 进度组件）

- [ ] **T13**: 策略解释面板
  - 新增 `src/frontend/src/components/strategy/StrategyExplanationCard.vue`
  - 显示：6 段说明 + 关键指标可视化 + 信号示意图
  - 集成位置：`BacktestResultPage.vue` 中部、`StrategyPage.vue` 策略详情 Tab

### 阶段五: 文档与验证（P1）

- [ ] **T14**: 评分模型说明文档
  - 新增 `docs/guides/STRATEGY_SCORE_MODEL.md`
  - 说明 6 维评分的计算公式、权重默认值、可调范围
  - 说明等级映射逻辑
  - 附评分与实盘表现相关性的初步验证方法（用 118 内置策略做样本）

- [ ] **T15**: 过拟合检测方法说明文档
  - 新增 `docs/guides/OVERFITTING_DETECTION.md`
  - 说明三种方法的适用场景、计算方法、解读方式
  - 附常见误区（"过拟合 = 一定亏损" 等）警示

- [ ] **T16**: 测试覆盖
  - 新增 `tests/test_strategy_score.py` - 单维评分函数 + 聚合评分
  - 新增 `tests/test_overfitting_walk_forward.py` - 用 mock 回测函数
  - 新增 `tests/test_overfitting_monte_carlo.py` - 用固定 seed 验证分位数计算
  - 新增 `tests/test_strategy_explainer_ast.py` - 用 5 个内置策略代码做样本
  - 新增 `tests/test_strategy_score_api.py` - API 集成测试
  - 覆盖率目标：4 个新 service 包均 ≥ 85%

---

## 4. 推荐执行顺序

```
阶段一 (T1 → T2 → T3)           # 评分系统先落，作为后续过拟合分数的接收者
阶段二 (T4 → T5 → T6 → T7)      # 过拟合检测独立可交付
阶段三 (T8 → T9 → T10)          # 解释器独立可交付
阶段四 (T11 → T12 → T13)        # 前端集成（依赖后端 API 完成）
阶段五 (T14 → T15 → T16)        # 文档和测试收尾
```

> T2 中"过拟合维度"先返回 degraded flag + 中位分；等 T4-T7 落地后，T2 在小补丁中接入。
> 这样 T2 不被 T4-T7 阻塞。

---

## 5. 验证命令

```bash
# 后端单元测试
cd src/backend
pytest tests/test_strategy_score.py tests/test_overfitting_*.py tests/test_strategy_explainer_ast.py -v

# 后端 API 集成测试
pytest tests/test_strategy_score_api.py tests/test_overfitting_api.py tests/test_strategy_explainer_api.py -v

# Ruff lint（新增文件）
ruff check app/services/strategy_score app/services/overfitting app/services/strategy_explainer

# mypy（新增 schema）
mypy app/schemas/strategy_score.py app/schemas/overfitting.py app/schemas/strategy_explanation.py

# 评分服务覆盖率
pytest --cov=app.services.strategy_score --cov=app.services.overfitting --cov=app.services.strategy_explainer \
  --cov-report=term-missing tests/test_strategy_score*.py tests/test_overfitting*.py tests/test_strategy_explainer*.py

# 前端组件测试
cd src/frontend
npm run test -- src/test/components/strategy/StrategyScoreCard.test.ts \
                src/test/components/strategy/OverfittingPanel.test.ts \
                src/test/components/strategy/StrategyExplanationCard.test.ts --run

# 前端 typecheck
npm run typecheck

# 维持迭代 165 已有基线
cd src/backend
ruff check --select B904 app/api
mypy app/utils app/schemas
```

---

## 6. 风险评估

| 风险 | 影响 | 缓解 |
|------|------|------|
| 评分维度权重过于主观 | 中 | 默认权重在配置层暴露，文档说明依据；附"专家权重 / 保守权重 / 激进权重"三套预设 |
| Walk-forward 跑 N 次回测耗时长 | 高 | 异步任务化 + 单任务并发限流（默认 4 worker）+ WebSocket 进度推送 + 结果缓存 |
| 蒙特卡洛随机性导致结果不可复现 | 中 | 固定 random seed = backtest_id hash；前端展示分布而非单点 |
| AST 解析失败率高（用户写法千差万别） | 中 | 失败自动 fallback 到 LLM 直接读代码；标记 `parsable: false` 让用户感知 |
| LLM 解释结果质量参差 | 中 | 用 4-shot 例子作为 prompt，限制温度 0.2；提供"重试解释"按钮 |
| 评分被用户当成"投资建议"导致法律风险 | 高 | 所有输出强制 disclaimer + 注册条款显式提示「不构成投资建议」 |

---

## 7. 不在本迭代范围内

1. **策略市场 / 策略评分排行榜** — Phase 3 平台化阶段
2. **AI 自动改写策略以提高评分** — Phase 2 后续迭代
3. **多策略组合评分** — 当前只评估单策略；组合在迭代 168 风险分析中处理
4. **历史评分趋势分析** — 留作下一轮 incremental feature
5. **基于评分自动调参** — 评分先稳定，再考虑自动化
6. **评分 API rate limit / 计费** — 在迭代 167 AI 工程化中统一处理

---

## 8. 执行结果（持续回填）

### 8.1 完成内容

| 任务 | 状态 | 说明 |
|------|------|------|
| T1 | ✅ | `strategy_score` schema、等级、维度结构与权重配置已落地 |
| T2 | ✅ | 6 维评分服务已落地，`overfitting_risk` 维度支持优先消费真实检测缓存，无结果时 degraded 回退 |
| T3 | ✅ | 评分 API、缓存落库、`BacktestResultPage` 评分卡片已可用 |
| T4 | ✅ | Walk-forward 已支持基于原始 backtest request 复跑 IS/OOS 窗口、并发限流、窗口级进度推送和窗口明细输出 |
| T5 | ✅ | 样本外验证已支持按 holdout ratio 复跑 IS/OOS，并输出 Welch t 统计量、自由度和近似 p-value |
| T6 | ✅ | Monte Carlo 已落地，基于交易收益 bootstrap 分布输出风险等级、稳健性分数和前端可视化分布数组 |
| T7 | ✅ | 异步任务 + REST API + 结果落库 + `/ws/overfitting/{task_id}` 进度推送已完成，前端已支持 WS/轮询双路径监听 |
| T8 | ✅ | 策略源码 AST 静态分析已落地，可抽取指标、tuple/dict 参数、买卖信号、目标仓位、止损参数，并支持解析失败降级 |
| T9 | ✅ | 策略解释器已支持 LLM JSON 解释路径；AI 未配置、返回异常或 JSON 解析失败时自动回退静态解释 |
| T10 | ✅ | `/api/v1/strategy/explain` 与缓存查询 API 已落地，解释结果按 code hash 缓存 |
| T11 | ✅ | 评分卡片已集成到 `BacktestResultPage.vue` |
| T12 | ✅ | 过拟合诊断面板已支持实时进度文案、方法选择、显式重新检测、方法 tab、Walk-forward/OOS/Monte Carlo 证据图与证据卡 |
| T13 | ✅ | `StrategyExplanationCard.vue` 已集成到 `BacktestResultPage.vue`，展示 6 段解释、静态证据、买卖信号与仓位/风控提示 |
| T14 | ✅ | `docs/guides/STRATEGY_SCORE_MODEL.md` 已补 |
| T15 | ✅ | `docs/guides/OVERFITTING_DETECTION.md` 已补 |
| T16 | ✅ | 后端/前端关键链路测试已覆盖评分、过拟合 runtime/交互/证据卡、策略解释器 AST/API/前端卡片 |

### 8.2 修改文件清单

- 后端评分：`app/services/strategy_score/dimensions.py`、`app/services/strategy_score/scorer.py`
- 后端过拟合：`app/schemas/overfitting.py`、`app/models/overfitting_result.py`、`app/services/overfitting/`、`app/api/overfitting.py`、`app/main.py`
- 后端解释器：`app/schemas/strategy_explanation.py`、`app/models/strategy_explanation.py`、`app/services/strategy_explainer/`、`app/api/strategy_explainer.py`
- 路由与模型注册：`app/api/router.py`、`app/models/__init__.py`
- 后端测试：`tests/test_overfitting_monte_carlo.py`、`tests/test_overfitting_walk_forward.py`、`tests/test_overfitting_api.py`、`tests/test_overfitting_websocket_runtime.py`、`tests/test_strategy_score.py`、`tests/test_strategy_score_api.py`、`tests/test_strategy_explainer_ast.py`、`tests/test_strategy_explainer_api.py`
- 前端 API 与页面：`src/frontend/src/api/strategy.ts`、`src/frontend/src/views/BacktestResultPage.vue`
- 前端组件与测试：`src/frontend/src/components/backtest/StrategyScoreCard.vue`、`src/frontend/src/components/backtest/OverfittingPanel.vue`、`src/frontend/src/components/backtest/StrategyExplanationCard.vue`、`src/frontend/src/composables/useOverfittingRuntime.ts`、`src/frontend/src/test/components/StrategyScoreCard.test.ts`、`src/frontend/src/test/components/OverfittingPanel.test.ts`、`src/frontend/src/test/components/StrategyExplanationCard.test.ts`、`src/frontend/src/test/composables/useOverfittingRuntime.test.ts`、`src/frontend/src/test/api/strategy.test.ts`、`src/frontend/src/test/views/BacktestResultPage.test.ts`
- 指南文档：`docs/guides/STRATEGY_SCORE_MODEL.md`、`docs/guides/OVERFITTING_DETECTION.md`、`docs/guides/STRATEGY_EXPLAINER.md`

### 8.3 验证结果

- 后端：`pytest -n 8 tests/test_overfitting_walk_forward.py tests/test_overfitting_monte_carlo.py tests/test_overfitting_api.py tests/test_overfitting_websocket_runtime.py tests/test_strategy_score.py tests/test_strategy_score_api.py tests/test_strategy_explainer_ast.py tests/test_strategy_explainer_api.py -q --tb=short` 通过（32 passed）
- 前端：`npm run test -- src/test/components/OverfittingPanel.test.ts src/test/components/StrategyScoreCard.test.ts src/test/components/StrategyExplanationCard.test.ts src/test/api/strategy.test.ts src/test/views/BacktestResultPage.test.ts --run` 通过（26 passed）
- 后端静态检查：`ruff check app/schemas/overfitting.py app/models/overfitting_result.py app/services/overfitting app/api/overfitting.py app/services/strategy_score/dimensions.py app/services/strategy_score/scorer.py app/schemas/strategy_explanation.py app/models/strategy_explanation.py app/services/strategy_explainer app/api/strategy_explainer.py app/api/router.py app/models/__init__.py tests/test_overfitting_walk_forward.py tests/test_overfitting_monte_carlo.py tests/test_overfitting_api.py tests/test_overfitting_websocket_runtime.py tests/test_strategy_score.py tests/test_strategy_score_api.py tests/test_strategy_explainer_ast.py tests/test_strategy_explainer_api.py` 通过
- 前端静态检查：`npx eslint src/api/strategy.ts src/components/backtest/StrategyScoreCard.vue src/components/backtest/OverfittingPanel.vue src/components/backtest/StrategyExplanationCard.vue src/views/BacktestResultPage.vue src/test/components/StrategyScoreCard.test.ts src/test/components/OverfittingPanel.test.ts src/test/components/StrategyExplanationCard.test.ts src/test/api/strategy.test.ts src/test/views/BacktestResultPage.test.ts` 通过（当前无 error）
- 前端类型检查：`npm run typecheck` 仍受仓库既有类型债影响失败；过滤本轮迭代 166 相关文件结果为 `NONE`，无新增 typecheck 错误

### 8.4 剩余风险与下一轮建议

- 过拟合检测三条主链路已都有后端切片、任务进度推送和前端可视化；OOS 目前使用 Welch t 的正态近似 p-value，后续可在确定直接依赖后切换精确 t 分布
- 策略解释器已具备 AST + LLM JSON 路径，但 LLM 输出质量仍依赖 AI 配置与 prompt 稳定性；静态解释是可信 fallback，不等同完整语义理解
- 下一步建议：进入迭代 169 前做一次最终 targeted 验证、静态检查与已知类型债说明归档

---

> 📝 本迭代完成后，进入迭代 167 (AI 能力工程化) 或迭代 169 (工程债务接续)。
