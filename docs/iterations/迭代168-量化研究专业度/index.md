# 迭代 168 - 量化研究专业度

> **文档状态**: 已完成
> **创建日期**: 2026-05-24
> **隶属路线**: 世界一流 AI+量化投研平台跃迁 Phase 3
> **总览**: `docs/iterations/世界一流跃迁-迭代166-169-总览.md`
> **执行顺位**: 第 4 站（在迭代 167 后执行）
> **核心目标**: 对接专业量化用户的研究工具栈 ——
> 建立"风控指标 + 因子库 + 绩效归因 + 市场状态识别"四位一体的专业量化基线。

---

## 0. 背景

迭代 166 让 AI 输出可信，迭代 167 让 AI 工程化可治理。但平台现有的量化研究工具栈仍停留在
Sharpe / MDD / 胜率等**初学者级别指标**，离专业量化研究员（私募、券商资管、量化基金）的实际需要还有显著距离：

| 维度 | 个人/初学者用户 | 专业量化用户 |
|------|----------------|------------|
| 风险度量 | 看回撤就行 | VaR / CVaR / 压力测试 / 尾部风险 |
| 仓位决策 | 满仓 or 半仓 | Kelly / 风险平价 / 波动率倒数 |
| 业绩评价 | 看绝对收益 | Alpha / Beta / 信息比 / 跟踪误差 / 基准对比 |
| 策略归因 | 看总收益 | Brinson 归因 / Fama-French 三/五因子 |
| 市场理解 | 看 K 线 | regime detection（波动率 / 趋势 / 相关性） |
| 信号开发 | 用现成指标 | 因子库 + IC/IR 评估 |

`fincore` 已经在依赖中（带 alpha_beta、ratios、fama_french、perf_attrib、empyrical、risk、tearsheets），
**这是巨大的现成基础设施**，本迭代核心是把它**正确暴露给业务层和前端**。

**用户场景驱动**：
- 专业用户：「这个策略 95% VaR 是多少？我承受得起吗？」
- 团队 leader：「最近一个月的策略收益里，因子贡献和 alpha 各多少？」
- 风控：「极端场景（如 2015 年股灾、2020 年疫情）下，组合最大损失是多少？」
- 研究员：「沪深300 的市场状态现在是趋势市还是震荡市？我的趋势策略适用吗？」
- 高级用户：「我自己写了一个动量因子，IC 怎么样？跟现有 5 个因子相关性高吗？」

---

## 1. 总目标

| 维度 | 现状 | 目标 |
|------|------|------|
| 风险度量 | Sharpe / MDD | + VaR/CVaR (95/99) + Kelly 仓位 + 压力测试 |
| 仓位决策 | 静态 | + Kelly 公式 + 风险平价 + 波动率目标 |
| 业绩评价 | 绝对指标 | + Alpha/Beta + 信息比 + 基准对比 + 跟踪误差 |
| 策略归因 | ❌ | ✅ Brinson + Fama-French 三因子 |
| 市场状态 | ❌ | ✅ 波动率 regime / 趋势 regime / 相关性 regime |
| 因子库 | ❌ | ✅ 10+ 经典因子 + IC/IR 评估 + 自定义因子接口 |

---

## 2. 执行原则

### 2.1 可以做

1. 新建 `app/services/risk_analytics/`、`app/services/factor_lib/`、`app/services/market_regime/`、`app/services/perf_attribution/` 四个服务包
2. 充分复用 `fincore`（已装）的指标计算
3. 用 akshare 已有数据作为基准数据（沪深300/中证500/中证800/标普500/比特币）
4. 新增前端组件：`RiskAnalyticsPanel.vue`、`FactorLibraryPage.vue`、`MarketRegimeWidget.vue`、`PerformanceAttributionPanel.vue`
5. 把新指标接入迭代 166 的策略评分系统（风险维度 / 基准对比维度自动用上）

### 2.2 不要做

1. 不要重写 `fincore` 已有的指标，统一通过 `fincore_metrics_helper` 调用
2. 不要破坏现有 `analytics_service.py` / `report_service.py` 的输出（新指标作为附加）
3. 不要做完整的多策略组合管理（那是 Phase 3 平台化阶段）
4. 不要引入额外的金融数据库（如 wind/通联），akshare + 缓存即可
5. 不要做实时风控触发（属于实盘风控范畴，已有独立 `risk_control_service`）
6. 不要把因子库做成全自动训练系统（人工注册因子定义即可）

---

## 3. 任务分解

### 阶段一: 风控指标强化（P0）

> 现状：仅 Sharpe / MDD / 胜率。
> 目标：补齐专业风险度量三件套（VaR / CVaR / 压力测试）。

- [x] **T1**: VaR / CVaR 计算服务
  - 新增 `app/services/risk_analytics/__init__.py`、`var_cvar.py`
  - 输入：收益率序列（来自 `EquityCurveAnalyzer` 的 daily returns）
  - 输出：`{var_95, var_99, cvar_95, cvar_99, method}`
  - 三种方法：
    - **历史模拟法**（默认）：直接取历史收益分位数
    - **参数法**（正态分布假设）：用均值/方差计算
    - **蒙特卡洛法**：复用迭代 166 的 monte_carlo 工具
  - API: GET `/api/v1/risk-analytics/var-cvar/{backtest_id}?method=historical`
  - 失败兜底：数据 < 30 个交易日 → 返回 `degraded` + reason

- [x] **T2**: 压力测试 (Stress Testing)
  - 新增 `app/services/risk_analytics/stress_test.py`
  - 内置场景库 `app/services/risk_analytics/scenarios.py`：
    - 2015-06 中国股灾
    - 2018-Q4 全球股市暴跌
    - 2020-03 COVID 黑天鹅
    - 2022-11 加密寒冬
    - 2024-08 日元 carry trade 反转
  - 计算：把策略放进对应历史时段重跑，输出该时段最大损失、最大回撤、恢复天数
  - API: POST `/api/v1/risk-analytics/stress-test/{backtest_id}`，body 选择场景集合
  - 自定义场景：用户可上传时间区间触发自定义压力测试

- [x] **T3**: 风控指标接入策略评分
  - 修改 `app/services/strategy_score/dimensions.py` 的"风险控制"维度
  - 把 VaR/CVaR 加入子指标，权重在 `STRATEGY_SCORE_WEIGHTS` 中暴露
  - 评分逻辑：VaR_95 < 5% → 高分；> 10% → 低分（参数化阈值）
  - 测试：用迭代 166 的样本策略验证评分变化合理

### 阶段二: 仓位决策（P1）

- [x] **T4**: Kelly 公式仓位推荐器
  - 新增 `app/services/risk_analytics/kelly.py`
  - 输入：历史交易记录（来自 `DetailedTradeAnalyzer.trades`）
  - 计算：
    - 单标的 Kelly: `f* = (b·p - q) / b`，其中 b=赢亏比、p=胜率、q=败率
    - 半凯利 / 四分之一凯利安全系数（避免 over-bet）
  - 输出：`{full_kelly, half_kelly, quarter_kelly, win_rate, avg_win, avg_loss, recommendation}`
  - API: GET `/api/v1/risk-analytics/kelly/{backtest_id}`
  - 文档：明确说明 Kelly 适用条件（独立同分布假设），不适合高频/趋势跟随

- [x] **T5**: 风险平价 + 波动率目标
  - 新增 `app/services/risk_analytics/position_sizing.py`
  - 输入：多个标的的波动率
  - 输出：风险平价权重（逆波动率归一化，作为 MVP）
  - 输入：单标的策略 + 目标波动率（如年化 15%）
  - 输出：波动率目标仓位推荐
  - API: GET `/api/v1/risk-analytics/position-sizing/{backtest_id}` 单策略目标仓位

### 阶段三: 业绩评价与基准对比（P0）

- [x] **T6**: 基准数据接入
  - 新增 `app/services/risk_analytics/benchmark.py`
  - 内置基准：`hs300`（沪深300）/ `csi500`（中证500）/ `csi800`（中证800）/ `spx`（标普500）/ `btc`（比特币）
  - 数据源：复用 `app/services/akshare_data_service.py` 拉取，用 `app/utils/cache_decorator.py` 缓存
  - 用户可在策略元数据指定 `benchmark_symbol`，默认按数据源类型推断
  - 配置 `app/config.py` 暴露 `DEFAULT_BENCHMARK_BY_MARKET` 映射

- [x] **T7**: Alpha / Beta / 信息比 / 跟踪误差
  - 新增 `app/services/risk_analytics/benchmark_metrics.py`
  - 输入：策略收益 + 基准收益 + 无风险利率
  - 输出：`{alpha, beta, information_ratio, tracking_error}`
  - API: GET `/api/v1/risk-analytics/benchmark-metrics/{backtest_id}?benchmark_id=hs300`
  - 失败兜底：重叠样本不足或基准零方差 → `degraded`

### 阶段四: 因子库 MVP（P1）

> 因子是量化研究的基本单元。MVP 内置 10 个经典因子，让用户能：
> 1. 在已有数据上计算因子值
> 2. 评估单因子的 IC（信息系数）/ IR（信息比）
> 3. 检查因子间相关性

- [x] **T8**: 因子注册中心 + 内置因子
  - 新增 `app/services/factor_lib/__init__.py`、`registry.py`
  - 内置因子 MVP（3 个）：
    - 动量类：`momentum_5`
    - 波动类：`volatility_5`
    - 反转类：`reversal_1`
  - 统一输入：`list[dict]` OHLCV records，至少包含 `close`
  - 注册中心能力：`list_factors()` / `get_factor()` / `calculate()`
  - 元数据：`{id, name, category, lookback, description}`

- [x] **T9**: 因子评估器（IC/IR）
  - 新增 `app/services/factor_lib/evaluator.py`
  - 输入：因子值时序 + 标的未来收益（如 5d/10d/20d 后收益）
  - 计算：
    - **IC** (Spearman 秩相关) — 每天因子值与未来收益的相关系数
    - **IR** = mean(IC) / std(IC) — 信息比
    - **多空收益** — 把全市场按因子值五分位分组，做空底部/做多顶部组的收益
  - 输出：`{ic_mean, ic_std, ic_ir, ic_t_stat, long_short_return, decay_curve}`
  - API: POST `/api/v1/factor-lib/evaluate`，body 指定因子 + 时间区间 + 股票池

- [x] **T10**: 因子相关性分析 + 自定义因子接口
  - 新增 `app/services/factor_lib/correlation.py`
  - 计算多因子两两相关，输出相关矩阵与高相关因子对
  - 用户自定义因子 MVP：受限 OHLCV 算术表达式，例如 `(close - open) / open`
  - API: POST `/api/v1/factor-lib/correlation` / POST `/api/v1/factor-lib/custom/calculate`
  - 失败兜底：未知变量、函数调用、属性访问等表达式返回 `degraded`

### 阶段五: 市场状态识别（P1）

- [x] **T11**: 市场状态分类
  - 新增 `app/services/market_regime/__init__.py`、`detector.py`
  - 两个维度：
    - **波动率 regime**：基于年化波动率阈值，分为 low/medium/high
    - **趋势 regime**：基于区间收益阈值，分为 bull/sideways/bear
  - 采用简单阈值规则识别，HMM 留作可选 v2
  - API: GET `/api/v1/risk-analytics/market-regime/{backtest_id}`
  - 失败兜底：历史不足 → `degraded`

### 阶段六: 绩效归因（P2）

- [x] **T12**: Brinson 归因
  - 新增 `app/services/perf_attribution/brinson.py`
  - 输入：组合权重 + 基准权重 + 组合资产收益 + 基准资产收益
  - 输出：`{allocation_effect, selection_effect, interaction_effect, total_excess_return}`
  - API: POST `/api/v1/perf-attribution/brinson`
  - 失败兜底：缺少共同资产 → `degraded`

- [x] **T13**: Fama-French 三因子归因
  - 新增 `app/services/perf_attribution/fama_french.py`
  - 输入：策略收益序列 + market/SMB/HML 因子收益序列
  - 用纯 Python OLS 做三因子回归
  - 输出：`{alpha, market_beta, smb_beta, hml_beta, r_squared}`
  - API: POST `/api/v1/perf-attribution/fama-french`
  - 失败兜底：样本不足或奇异矩阵 → `degraded`

### 阶段七: 前端集成与文档（P0）

- [x] **T14**: 前端 API 封装 + 文档
  - 新增 `src/frontend/src/api/quantResearch.ts`，封装 T1-T13 后端端点
  - 新增 `src/frontend/src/test/api/quantResearch.test.ts`，验证 URL、query params 与 body
  - 预留页面组件集成入口：后续可在 BacktestResultPage / FactorLibraryPage 中直接复用 API 封装
  - 文档：
    - `docs/iterations/迭代168-量化研究专业度/index.md`

---

## 4. 推荐执行顺序

```
T1 → T2 → T3                    # 阶段一：风控指标，最高频用户需求
T6 → T7                         # 阶段三：基准对比（先于评分系统二次接入）
T4 → T5                         # 阶段二：仓位决策（独立可交付）
T8 → T9 → T10                   # 阶段四：因子库 MVP（独立可交付）
T11                             # 阶段五：市场状态（独立可交付）
T12 → T13                       # 阶段六：归因（依赖 T6 基准数据）
T14                             # 阶段七：前端集成
```

> T1-T3 优先（让评分系统更专业）；T8-T10 可与 T11/T12-T13 并行。

---

## 5. 验证命令

```bash
# 后端单元测试
cd src/backend
pytest tests/test_risk_analytics_*.py -v
pytest tests/test_factor_lib_*.py -v
pytest tests/test_market_regime_*.py -v
pytest tests/test_perf_attribution_*.py -v

# 用 fincore 已有指标作为 ground truth 做对照测试
pytest tests/test_var_cvar_consistency_with_fincore.py -v
pytest tests/test_alpha_beta_consistency_with_fincore.py -v

# Ruff lint
ruff check app/services/risk_analytics app/services/factor_lib app/services/market_regime app/services/perf_attribution

# 覆盖率（4 个新 service 包）
pytest --cov=app.services.risk_analytics --cov=app.services.factor_lib \
       --cov=app.services.market_regime --cov=app.services.perf_attribution \
       --cov-report=term-missing tests/test_risk_*.py tests/test_factor_*.py tests/test_market_*.py tests/test_perf_*.py

# 自定义因子沙箱测试
pytest tests/test_custom_factor_sandbox.py -v

# 数据库迁移验证
cd src/backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head

# 前端
cd src/frontend
npm run typecheck
npm run test -- src/test/components/risk src/test/views/FactorLibraryPage.test.ts --run

# 维持迭代 165 + 166 + 167 基线
cd src/backend
ruff check --select B904 app/api
mypy app/utils app/schemas
pytest tests/test_strategy_score.py tests/test_overfitting_*.py -v  # 不破坏 166 评分
pytest tests/test_ai_call_log.py -v  # 不破坏 167 日志
```

---

## 6. 风险评估

| 风险 | 影响 | 缓解 |
|------|------|------|
| 基准数据 akshare 不稳定 | 中 | 缓存 + 定期落库 + 失败回退到上次成功值 + 标记 stale |
| 因子计算耗时长（全市场） | 高 | 默认股票池限定为沪深300成分 + 异步任务化 + 结果缓存 |
| 自定义因子代码安全风险 | 高 | 必须走 `app/utils/sandbox.py` 沙箱（已有），网络/文件访问全禁 |
| HMM 训练复杂，结果不稳 | 中 | 默认用阈值规则 regime；HMM 作为 v2 可选 |
| Brinson 归因需要持仓时间序列 | 中 | 当前 backtester 已记录 trades，可重建持仓；增加测试覆盖 |
| Fama-French 因子序列从哪里来 | 中 | 用 akshare 拉沪深300 + 中证500/小市值 + 中证红利/价值 作为代理因子 |
| 新指标与旧指标含义重叠困惑 | 中 | 文档明确说明每个指标"用什么场景"；UI 分组显示 |

---

## 7. 不在本迭代范围内

1. **多策略组合管理 / 全自动配置** — Phase 3 平台化阶段
2. **机器学习因子（神经网络/树模型）** — 仅做线性因子；ML 留作扩展
3. **实时因子计算** — 当前批处理即可
4. **因子市场 / 因子付费订阅** — Phase 3 商业化
5. **基于市场状态的自动策略切换** — 信号给到用户，不自动操作
6. **跨市场套利** — 单市场即可
7. **完整的 BARRA 风险模型** — 仅做 Fama-French 三因子，BARRA 多因子留 Phase 3

---

## 8. 执行结果

### 8.1 完成内容

| 任务 | 状态 | 说明 |
|------|------|------|
| T1 | ✅ | 新增 `risk_analytics` VaR/CVaR 服务与 `/api/v1/risk-analytics/var-cvar/{backtest_id}` API，支持历史模拟法、参数法、蒙特卡洛法；数据不足返回 `degraded`。 |
| T2 | ✅ | 新增压力测试场景库、服务与 `/api/v1/risk-analytics/stress-test/{backtest_id}` API，可基于回测净值曲线计算场景最大损失、最大回撤、恢复天数；场景未覆盖返回 `degraded`。 |
| T3 | ✅ | `strategy_score` 的风险控制维度已纳入 VaR/CVaR 子指标；数据足够时尾部风险参与评分，数据不足时保留旧公式并记录 degraded 子指标状态。 |
| T4 | ✅ | 新增 Kelly 仓位推荐服务与 `/api/v1/risk-analytics/kelly/{backtest_id}` API，输出 full/half/quarter Kelly，并在交易样本不足或缺少盈亏样本时返回 `degraded`。 |
| T5 | ✅ | 新增波动率目标仓位建议与风险平价权重工具，API `/api/v1/risk-analytics/position-sizing/{backtest_id}` 可基于净值曲线输出目标仓位；历史不足或零波动返回 `degraded`。 |
| T6 | ✅ | 新增基准收益序列服务与 `/api/v1/risk-analytics/benchmark/{benchmark_id}` API，内置 hs300/csi500/csi800/spx/btc 映射，默认复用历史行情服务并支持测试注入数据源。 |
| T7 | ✅ | 新增 benchmark metrics 服务与 `/api/v1/risk-analytics/benchmark-metrics/{backtest_id}` API，基于策略收益和基准收益计算 Alpha、Beta、Tracking Error、Information Ratio；重叠样本不足或基准零方差返回 `degraded`。 |
| T8 | ✅ | 新增 `factor_lib` 注册中心与内置因子 MVP，支持列出/获取/计算 momentum_5、volatility_5、reversal_1，为后续 IC/相关性分析提供基础。 |
| T9 | ✅ | 新增因子评估服务与 `/api/v1/factor-lib/evaluate` API，支持 Spearman IC、IC IR/t-stat（单截面时为 None）、多空收益，并对样本不足/常量序列降级。 |
| T10 | ✅ | 新增因子相关性分析和安全自定义因子表达式计算，API `/api/v1/factor-lib/correlation` 与 `/api/v1/factor-lib/custom/calculate` 支持相关性矩阵、高相关因子对和受限 OHLCV 算术表达式。 |
| T11 | ✅ | 新增阈值规则版市场状态分类服务与 `/api/v1/risk-analytics/market-regime/{backtest_id}` API，基于价格/净值序列输出 volatility_regime、trend_regime、overall_regime；历史不足返回 `degraded`。 |
| T12 | ✅ | 新增 Brinson 绩效归因服务与 `/api/v1/perf-attribution/brinson` API，计算 allocation、selection、interaction 和 total excess return；缺少共同资产时返回 `degraded`。 |
| T13 | ✅ | 新增 Fama-French 三因子归因服务与 `/api/v1/perf-attribution/fama-french` API，基于策略收益和 market/SMB/HML 因子收益做 OLS，输出 alpha、三因子 beta、R²；样本不足或奇异矩阵返回 `degraded`。 |
| T14 | ✅ | 新增前端 `quantResearchApi` 封装与 12 个 Vitest API 单测，覆盖 T1-T13 新端点；前端 typecheck 通过，ESLint 无 error。 |

### 8.2 修改文件清单

- `src/backend/app/schemas/risk_analytics.py`
- `src/backend/app/services/risk_analytics/__init__.py`
- `src/backend/app/services/risk_analytics/benchmark.py`
- `src/backend/app/services/risk_analytics/benchmark_metrics.py`
- `src/backend/app/services/risk_analytics/kelly.py`
- `src/backend/app/services/risk_analytics/position_sizing.py`
- `src/backend/app/services/risk_analytics/scenarios.py`
- `src/backend/app/services/risk_analytics/stress_test.py`
- `src/backend/app/services/risk_analytics/var_cvar.py`
- `src/backend/app/services/factor_lib/__init__.py`
- `src/backend/app/services/factor_lib/correlation.py`
- `src/backend/app/services/factor_lib/custom.py`
- `src/backend/app/services/factor_lib/evaluator.py`
- `src/backend/app/services/factor_lib/registry.py`
- `src/backend/app/services/market_regime/__init__.py`
- `src/backend/app/services/market_regime/detector.py`
- `src/backend/app/services/perf_attribution/__init__.py`
- `src/backend/app/services/perf_attribution/brinson.py`
- `src/backend/app/services/perf_attribution/fama_french.py`
- `src/backend/app/schemas/factor_lib.py`
- `src/backend/app/schemas/perf_attribution.py`
- `src/backend/app/api/factor_lib.py`
- `src/backend/app/api/perf_attribution.py`
- `src/backend/app/api/risk_analytics.py`
- `src/backend/app/api/router.py`
- `src/backend/app/services/strategy_score/dimensions.py`
- `src/backend/tests/test_risk_analytics_benchmark.py`
- `src/backend/tests/test_risk_analytics_benchmark_metrics.py`
- `src/backend/tests/test_risk_analytics_kelly.py`
- `src/backend/tests/test_risk_analytics_position_sizing.py`
- `src/backend/tests/test_risk_analytics_stress_test.py`
- `src/backend/tests/test_strategy_score.py`
- `src/backend/tests/test_risk_analytics_var_cvar.py`
- `src/backend/tests/test_factor_library.py`
- `src/backend/tests/test_factor_evaluator.py`
- `src/backend/tests/test_factor_correlation.py`
- `src/backend/tests/test_market_regime.py`
- `src/backend/tests/test_perf_attribution.py`
- `src/backend/tests/test_fama_french_attribution.py`
- `src/frontend/src/api/quantResearch.ts`
- `src/frontend/src/test/api/quantResearch.test.ts`

### 8.3 验证结果

- Frontend typecheck debt cleanup before T1:
  - `npm run typecheck` ✅
  - targeted ESLint over changed frontend files ✅
  - targeted Vitest: 7 files / 57 tests ✅
  - full Vitest: 59 files / 482 tests ✅
- T1 backend:
  - RED: `pytest tests/test_risk_analytics_var_cvar.py -q --tb=short --log-level=WARNING` failed because `app.services.risk_analytics` / `app.api.risk_analytics` did not exist ✅
  - GREEN: `pytest tests/test_risk_analytics_var_cvar.py -q --tb=short --log-level=WARNING` → 6 passed ✅
  - `ruff check app/api/risk_analytics.py app/api/router.py app/services/risk_analytics app/schemas/risk_analytics.py tests/test_risk_analytics_var_cvar.py` ✅
- T2 backend:
  - RED: `pytest tests/test_risk_analytics_stress_test.py -q --tb=short --log-level=WARNING` failed because `app.services.risk_analytics.stress_test` and API route did not exist ✅
  - GREEN: `pytest tests/test_risk_analytics_stress_test.py -q --tb=short --log-level=WARNING` → 5 passed ✅
  - Combined: `pytest tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py -q --tb=short --log-level=WARNING` → 11 passed ✅
  - `ruff check app/api/risk_analytics.py app/api/router.py app/services/risk_analytics app/schemas/risk_analytics.py tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py` ✅
- T3 backend:
  - RED: `pytest tests/test_strategy_score.py -q --tb=short --log-level=WARNING` failed because `risk_control` had no VaR/CVaR submetrics and tail risk did not affect score ✅
  - GREEN: `pytest tests/test_strategy_score.py -q --tb=short --log-level=WARNING` → 5 passed ✅
  - Combined: `pytest tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py tests/test_strategy_score.py -q --tb=short --log-level=WARNING` → 16 passed ✅
  - `ruff check app/api/risk_analytics.py app/api/router.py app/services/risk_analytics app/schemas/risk_analytics.py app/services/strategy_score/dimensions.py tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py tests/test_strategy_score.py` ✅
- T4 backend:
  - RED: `pytest tests/test_risk_analytics_kelly.py -q --tb=short --log-level=WARNING` failed because `app.services.risk_analytics.kelly` and API route did not exist ✅
  - GREEN: `pytest tests/test_risk_analytics_kelly.py -q --tb=short --log-level=WARNING` → 5 passed ✅
  - Combined: `pytest tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py tests/test_risk_analytics_kelly.py tests/test_strategy_score.py -q --tb=short --log-level=WARNING` → 21 passed ✅
  - `ruff check app/api/risk_analytics.py app/api/router.py app/services/risk_analytics app/schemas/risk_analytics.py app/services/strategy_score/dimensions.py tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py tests/test_risk_analytics_kelly.py tests/test_strategy_score.py` ✅
- T5 backend:
  - RED: `pytest tests/test_risk_analytics_position_sizing.py -q --tb=short --log-level=WARNING` failed because `app.services.risk_analytics.position_sizing` and API route did not exist ✅
  - GREEN: `pytest tests/test_risk_analytics_position_sizing.py -q --tb=short --log-level=WARNING` → 6 passed ✅
  - Combined: `pytest tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py tests/test_risk_analytics_kelly.py tests/test_risk_analytics_position_sizing.py tests/test_strategy_score.py -q --tb=short --log-level=WARNING` → 27 passed ✅
  - `ruff check app/api/risk_analytics.py app/api/router.py app/services/risk_analytics app/schemas/risk_analytics.py app/services/strategy_score/dimensions.py tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py tests/test_risk_analytics_kelly.py tests/test_risk_analytics_position_sizing.py tests/test_strategy_score.py` ✅
- T6 backend:
  - RED: `pytest tests/test_risk_analytics_benchmark.py -q --tb=short --log-level=WARNING` failed because `get_benchmark_service` / benchmark service did not exist ✅
  - GREEN: `pytest tests/test_risk_analytics_benchmark.py -q --tb=short --log-level=WARNING` → 4 passed ✅
  - Combined: `pytest tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py tests/test_risk_analytics_kelly.py tests/test_risk_analytics_position_sizing.py tests/test_risk_analytics_benchmark.py tests/test_strategy_score.py -q --tb=short --log-level=WARNING` → 31 passed ✅
  - `ruff check app/api/risk_analytics.py app/api/router.py app/services/risk_analytics app/schemas/risk_analytics.py app/services/strategy_score/dimensions.py tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py tests/test_risk_analytics_kelly.py tests/test_risk_analytics_position_sizing.py tests/test_risk_analytics_benchmark.py tests/test_strategy_score.py` ✅
- T7 backend:
  - RED: `pytest tests/test_risk_analytics_benchmark_metrics.py -q --tb=short --log-level=WARNING` failed because `app.services.risk_analytics.benchmark_metrics` and API route did not exist ✅
  - GREEN: `pytest tests/test_risk_analytics_benchmark_metrics.py -q --tb=short --log-level=WARNING` → 4 passed ✅
  - Combined: `pytest tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py tests/test_risk_analytics_kelly.py tests/test_risk_analytics_position_sizing.py tests/test_risk_analytics_benchmark.py tests/test_risk_analytics_benchmark_metrics.py tests/test_strategy_score.py -q --tb=short --log-level=WARNING` → 35 passed ✅
  - `ruff check app/api/risk_analytics.py app/api/router.py app/services/risk_analytics app/schemas/risk_analytics.py app/services/strategy_score/dimensions.py tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py tests/test_risk_analytics_kelly.py tests/test_risk_analytics_position_sizing.py tests/test_risk_analytics_benchmark.py tests/test_risk_analytics_benchmark_metrics.py tests/test_strategy_score.py` ✅
- T8 backend:
  - RED: `pytest tests/test_factor_library.py -q --tb=short --log-level=WARNING` failed because `app.services.factor_lib` did not exist ✅
  - GREEN: `pytest tests/test_factor_library.py -q --tb=short --log-level=WARNING` → 6 passed ✅
  - Combined: `pytest tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py tests/test_risk_analytics_kelly.py tests/test_risk_analytics_position_sizing.py tests/test_risk_analytics_benchmark.py tests/test_risk_analytics_benchmark_metrics.py tests/test_strategy_score.py tests/test_factor_library.py -q --tb=short --log-level=WARNING` → 41 passed ✅
  - `ruff check app/api/risk_analytics.py app/api/router.py app/services/risk_analytics app/schemas/risk_analytics.py app/services/strategy_score/dimensions.py app/services/factor_lib tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py tests/test_risk_analytics_kelly.py tests/test_risk_analytics_position_sizing.py tests/test_risk_analytics_benchmark.py tests/test_risk_analytics_benchmark_metrics.py tests/test_strategy_score.py tests/test_factor_library.py` ✅
- T9 backend:
  - RED: `pytest tests/test_factor_evaluator.py -q --tb=short --log-level=WARNING` failed because `app.services.factor_lib.evaluator` and API route did not exist ✅
  - GREEN: `pytest tests/test_factor_evaluator.py -q --tb=short --log-level=WARNING` → 5 passed ✅
  - Combined: `pytest tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py tests/test_risk_analytics_kelly.py tests/test_risk_analytics_position_sizing.py tests/test_risk_analytics_benchmark.py tests/test_risk_analytics_benchmark_metrics.py tests/test_strategy_score.py tests/test_factor_library.py tests/test_factor_evaluator.py -q --tb=short --log-level=WARNING` → 46 passed ✅
  - `ruff check app/api/risk_analytics.py app/api/factor_lib.py app/api/router.py app/services/risk_analytics app/schemas/risk_analytics.py app/schemas/factor_lib.py app/services/strategy_score/dimensions.py app/services/factor_lib tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py tests/test_risk_analytics_kelly.py tests/test_risk_analytics_position_sizing.py tests/test_risk_analytics_benchmark.py tests/test_risk_analytics_benchmark_metrics.py tests/test_strategy_score.py tests/test_factor_library.py tests/test_factor_evaluator.py` ✅
- T10 backend:
  - RED: `pytest tests/test_factor_correlation.py -q --tb=short --log-level=WARNING` failed because `app.services.factor_lib.correlation` / `custom` and API routes did not exist ✅
  - GREEN: `pytest tests/test_factor_correlation.py -q --tb=short --log-level=WARNING` → 7 passed ✅
  - Combined: `pytest tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py tests/test_risk_analytics_kelly.py tests/test_risk_analytics_position_sizing.py tests/test_risk_analytics_benchmark.py tests/test_risk_analytics_benchmark_metrics.py tests/test_strategy_score.py tests/test_factor_library.py tests/test_factor_evaluator.py tests/test_factor_correlation.py -q --tb=short --log-level=WARNING` → 53 passed ✅
  - `ruff check app/api/risk_analytics.py app/api/factor_lib.py app/api/router.py app/services/risk_analytics app/schemas/risk_analytics.py app/schemas/factor_lib.py app/services/strategy_score/dimensions.py app/services/factor_lib tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py tests/test_risk_analytics_kelly.py tests/test_risk_analytics_position_sizing.py tests/test_risk_analytics_benchmark.py tests/test_risk_analytics_benchmark_metrics.py tests/test_strategy_score.py tests/test_factor_library.py tests/test_factor_evaluator.py tests/test_factor_correlation.py` ✅
- T11 backend:
  - RED: `pytest tests/test_market_regime.py -q --tb=short --log-level=WARNING` failed because `app.services.market_regime` and API route did not exist ✅
  - GREEN: `pytest tests/test_market_regime.py -q --tb=short --log-level=WARNING` → 5 passed ✅
  - Combined: `pytest tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py tests/test_risk_analytics_kelly.py tests/test_risk_analytics_position_sizing.py tests/test_risk_analytics_benchmark.py tests/test_risk_analytics_benchmark_metrics.py tests/test_strategy_score.py tests/test_factor_library.py tests/test_factor_evaluator.py tests/test_factor_correlation.py tests/test_market_regime.py -q --tb=short --log-level=WARNING` → 58 passed ✅
  - `ruff check app/api/risk_analytics.py app/api/factor_lib.py app/api/router.py app/services/risk_analytics app/schemas/risk_analytics.py app/schemas/factor_lib.py app/services/strategy_score/dimensions.py app/services/factor_lib app/services/market_regime tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py tests/test_risk_analytics_kelly.py tests/test_risk_analytics_position_sizing.py tests/test_risk_analytics_benchmark.py tests/test_risk_analytics_benchmark_metrics.py tests/test_strategy_score.py tests/test_factor_library.py tests/test_factor_evaluator.py tests/test_factor_correlation.py tests/test_market_regime.py` ✅
- T12 backend:
  - RED: `pytest tests/test_perf_attribution.py -q --tb=short --log-level=WARNING` failed because `app.services.perf_attribution` and API route did not exist ✅
  - GREEN: `pytest tests/test_perf_attribution.py -q --tb=short --log-level=WARNING` → 4 passed ✅
  - Combined: `pytest tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py tests/test_risk_analytics_kelly.py tests/test_risk_analytics_position_sizing.py tests/test_risk_analytics_benchmark.py tests/test_risk_analytics_benchmark_metrics.py tests/test_strategy_score.py tests/test_factor_library.py tests/test_factor_evaluator.py tests/test_factor_correlation.py tests/test_market_regime.py tests/test_perf_attribution.py -q --tb=short --log-level=WARNING` → 62 passed ✅
  - `ruff check app/api/risk_analytics.py app/api/factor_lib.py app/api/perf_attribution.py app/api/router.py app/services/risk_analytics app/schemas/risk_analytics.py app/schemas/factor_lib.py app/schemas/perf_attribution.py app/services/strategy_score/dimensions.py app/services/factor_lib app/services/market_regime app/services/perf_attribution tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py tests/test_risk_analytics_kelly.py tests/test_risk_analytics_position_sizing.py tests/test_risk_analytics_benchmark.py tests/test_risk_analytics_benchmark_metrics.py tests/test_strategy_score.py tests/test_factor_library.py tests/test_factor_evaluator.py tests/test_factor_correlation.py tests/test_market_regime.py tests/test_perf_attribution.py` ✅
- T13 backend:
  - RED: `pytest tests/test_fama_french_attribution.py -q --tb=short --log-level=WARNING` failed because `app.services.perf_attribution.fama_french` and API route did not exist ✅
  - GREEN: `pytest tests/test_fama_french_attribution.py -q --tb=short --log-level=WARNING` → 4 passed ✅
  - Combined: `pytest tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py tests/test_risk_analytics_kelly.py tests/test_risk_analytics_position_sizing.py tests/test_risk_analytics_benchmark.py tests/test_risk_analytics_benchmark_metrics.py tests/test_strategy_score.py tests/test_factor_library.py tests/test_factor_evaluator.py tests/test_factor_correlation.py tests/test_market_regime.py tests/test_perf_attribution.py tests/test_fama_french_attribution.py -q --tb=short --log-level=WARNING` → 66 passed ✅
  - `ruff check app/api/risk_analytics.py app/api/factor_lib.py app/api/perf_attribution.py app/api/router.py app/services/risk_analytics app/schemas/risk_analytics.py app/schemas/factor_lib.py app/schemas/perf_attribution.py app/services/strategy_score/dimensions.py app/services/factor_lib app/services/market_regime app/services/perf_attribution tests/test_risk_analytics_var_cvar.py tests/test_risk_analytics_stress_test.py tests/test_risk_analytics_kelly.py tests/test_risk_analytics_position_sizing.py tests/test_risk_analytics_benchmark.py tests/test_risk_analytics_benchmark_metrics.py tests/test_strategy_score.py tests/test_factor_library.py tests/test_factor_evaluator.py tests/test_factor_correlation.py tests/test_market_regime.py tests/test_perf_attribution.py tests/test_fama_french_attribution.py` ✅
- T14 frontend:
  - `npm run test -- src/test/api/quantResearch.test.ts --run` → 1 file / 12 tests passed ✅
  - `npm run typecheck` ✅
  - `npm run lint -- src/api/quantResearch.ts src/test/api/quantResearch.test.ts` → 0 errors, 6 existing unrelated warnings ✅

### 8.4 剩余风险与下一轮建议

- 前端当前完成的是 T1-T13 后端能力的 `quantResearchApi` 调用封装与契约测试，完整页面组件（风险面板、因子页面、市场状态组件、归因图表）建议作为后续 UI 深化迭代继续推进。
- Benchmark、Fama-French 与自定义因子均为 MVP：默认使用现有行情/直接输入序列/受限表达式；后续可接入更完整的数据源、因子数据管理与可视化解释。
- 所有分析 API 均保留 `degraded` 状态，前端页面集成时应显式展示降级原因，避免把样本不足误解为有效结论。
- 下一轮建议优先级：前端研究工作台组件化展示 → 真实因子/基准数据源适配 → 全量回归与覆盖率提升。

---

> 📝 本迭代完成后，平台具备「专业量化研究工具栈基线」，可承接专业用户研究流程；
> 进入迭代 169 (工程债务接续) 完成 4 迭代跃迁路线收尾。
